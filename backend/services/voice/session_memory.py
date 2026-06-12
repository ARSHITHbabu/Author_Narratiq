"""
Voice Session Memory / Conversational Context (B).

VoiceSessionContextManager wraps a VoiceSession.context_state JSON blob and
exposes the session-level memory slots that let follow-up commands resolve
references ("make it darker", "use the second option", "same character",
"the chapter we discussed") without the author repeating themselves.

Persistence model: the authoritative store is voice_sessions.context_state in
the DB, so ANY backend replica can rehydrate after a WS reconnect. An in-process
LRU mirrors the hot session to avoid a DB read on every turn. The agent loads at
the start of a turn and saves at the end.
"""
from __future__ import annotations

import logging
from collections import OrderedDict
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# Memory slot keys (documented surface)
SLOTS = (
    "last_command", "last_intent", "last_capability",
    "last_output", "last_result_kind",
    "last_selected_text", "last_chapter_id", "last_chapter_number",
    "last_character_id", "last_character_name",
    "last_analysis", "last_continuation", "last_bible",
    "last_workflow", "pending_clarification",
)

# Small in-process LRU mirror of hot sessions {session_id: context_state}
_LRU_MAX = 512
_lru: "OrderedDict[str, dict]" = OrderedDict()


def _lru_get(session_id: str) -> dict | None:
    if session_id in _lru:
        _lru.move_to_end(session_id)
        return _lru[session_id]
    return None


def _lru_put(session_id: str, state: dict) -> None:
    _lru[session_id] = state
    _lru.move_to_end(session_id)
    while len(_lru) > _LRU_MAX:
        _lru.popitem(last=False)


class VoiceSessionContextManager:
    """In-memory view over a session's context_state with typed accessors."""

    def __init__(self, session_id: str, state: dict | None = None):
        self.session_id = session_id
        self.state: dict[str, Any] = dict(state or {})

    # ── factory ───────────────────────────────────────────────────────────────
    @classmethod
    def load(cls, session_id: str, db) -> "VoiceSessionContextManager":
        cached = _lru_get(session_id)
        if cached is not None:
            return cls(session_id, cached)
        from models import VoiceSession
        row = db.query(VoiceSession).filter(VoiceSession.session_id == session_id).first()
        state = dict(row.context_state or {}) if row else {}
        _lru_put(session_id, state)
        return cls(session_id, state)

    def save(self, db) -> None:
        """Persist back to DB + LRU. Caller commits."""
        from models import VoiceSession
        row = db.query(VoiceSession).filter(VoiceSession.session_id == self.session_id).first()
        if row:
            row.context_state = dict(self.state)
            row.command_count = (row.command_count or 0) + 1
        _lru_put(self.session_id, dict(self.state))

    # ── generic accessors ─────────────────────────────────────────────────────
    def get(self, key: str, default=None):
        return self.state.get(key, default)

    def set(self, key: str, value) -> None:
        self.state[key] = value

    # ── slot updates after a turn ─────────────────────────────────────────────
    def record_turn(self, *, command: str, intent: str, capability: str,
                    result_kind: str | None = None, output: Any = None) -> None:
        self.state["last_command"] = command
        self.state["last_intent"] = intent
        self.state["last_capability"] = capability
        if result_kind:
            self.state["last_result_kind"] = result_kind
        if output is not None:
            self.state["last_output"] = output
            if result_kind == "continuation":
                self.state["last_continuation"] = output
            elif result_kind == "analysis":
                self.state["last_analysis"] = output
            elif result_kind == "bible":
                self.state["last_bible"] = output

    def remember_context(self, context) -> None:
        """Capture targets the author may refer back to (chapter, character, selection)."""
        if getattr(context, "chapter_id", None):
            self.state["last_chapter_id"] = context.chapter_id
            self.state["last_chapter_number"] = getattr(context, "chapter_number", None)
        if getattr(context, "active_character_id", None):
            self.state["last_character_id"] = context.active_character_id
        sel = getattr(context, "selected_text", None)
        if sel:
            self.state["last_selected_text"] = sel

    def set_pending_clarification(self, payload: dict | None) -> None:
        self.state["pending_clarification"] = payload

    def pop_pending_clarification(self) -> dict | None:
        return self.state.pop("pending_clarification", None)

    def set_workflow(self, graph: dict) -> None:
        self.state["last_workflow"] = graph
        self.state["_workflow_ts"] = datetime.utcnow().isoformat()
