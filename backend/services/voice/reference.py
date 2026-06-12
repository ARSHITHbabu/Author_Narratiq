"""
Reference / anaphora resolution (B).

Resolves conversational references in a command against session memory so the
author can say "make it darker", "use the second option", "same character",
"the chapter we discussed" without repeating context.

Deterministic-first: pattern matches against memory slots. Returns a structured
result the ContextResolver merges into parameters. When a reference is used but
nothing in memory can satisfy it, it is reported as `unresolved` so the agent can
ask a targeted clarification instead of guessing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .normalize import extract_ordinal

_PRONOUN_RE = re.compile(r"\b(it|this|that|them|those|the result|previous result|the (?:last|previous) (?:one|output|result))\b", re.IGNORECASE)
_OPTION_RE = re.compile(r"\b(option|one|suggestion|version|choice)\b", re.IGNORECASE)
_SAME_CHAR_RE = re.compile(r"\b(same character|that character|this character|the character)\b", re.IGNORECASE)
_SAME_CHAP_RE = re.compile(r"\b(same chapter|that chapter|this chapter|the chapter we discussed|the chapter)\b", re.IGNORECASE)
_PREV_VERSION_RE = re.compile(r"\b(previous version|earlier version|last version|the previous one)\b", re.IGNORECASE)


@dataclass
class ResolvedRefs:
    references: dict[str, Any] = field(default_factory=dict)
    selected_text: str | None = None
    chapter_id: str | None = None
    character_id: str | None = None
    character_name: str | None = None
    option_index: int | None = None
    option_text: str | None = None
    used_memory: bool = False
    unresolved: list[str] = field(default_factory=list)


def _option_list(memory) -> list:
    """Pull the most recent list the author might index into."""
    cont = memory.get("last_continuation")
    if isinstance(cont, list) and cont:
        return cont
    out = memory.get("last_output")
    if isinstance(out, list) and out:
        return out
    if isinstance(out, dict):
        for key in ("suggestions", "options", "results"):
            if isinstance(out.get(key), list) and out[key]:
                return out[key]
    return []


def resolve(command: str, memory, context) -> ResolvedRefs:
    """
    command : normalized command string
    memory  : VoiceSessionContextManager
    context : VoiceContext (client snapshot)
    """
    res = ResolvedRefs()
    low = (command or "").lower()

    # ── "second option" / "use the third one" ────────────────────────────────
    if _OPTION_RE.search(low):
        idx = extract_ordinal(low)
        if idx is not None:
            options = _option_list(memory)
            if options:
                real_idx = idx if idx >= 0 else len(options) + idx
                if 0 <= real_idx < len(options):
                    opt = options[real_idx]
                    res.option_index = real_idx
                    res.option_text = opt.get("text") if isinstance(opt, dict) else str(opt)
                    res.references["option"] = f"index:{real_idx}"
                    res.used_memory = True
                else:
                    res.unresolved.append("option")
            else:
                res.unresolved.append("option")

    # ── pronoun → last output / selection ─────────────────────────────────────
    if _PRONOUN_RE.search(low):
        # Prefer a live selection in the editor; else fall back to last output.
        if getattr(context, "selected_text", None):
            res.selected_text = context.selected_text
            res.references["it"] = "current_selection"
            res.used_memory = True
        elif res.option_text:
            res.selected_text = res.option_text
            res.references["it"] = f"option:{res.option_index}"
        elif memory.get("last_selected_text"):
            res.selected_text = memory.get("last_selected_text")
            res.references["it"] = "last_selection"
            res.used_memory = True
        elif memory.get("last_output") is not None:
            res.references["it"] = "last_output"
            res.used_memory = True
        else:
            res.unresolved.append("it")

    # ── same character ────────────────────────────────────────────────────────
    if _SAME_CHAR_RE.search(low):
        cid = getattr(context, "active_character_id", None) or memory.get("last_character_id")
        if cid:
            res.character_id = cid
            res.character_name = memory.get("last_character_name")
            res.references["character"] = cid
            res.used_memory = True
        else:
            res.unresolved.append("character")

    # ── same chapter ──────────────────────────────────────────────────────────
    if _SAME_CHAP_RE.search(low):
        chid = getattr(context, "chapter_id", None) or memory.get("last_chapter_id")
        if chid:
            res.chapter_id = chid
            res.references["chapter"] = chid
            res.used_memory = True
        else:
            res.unresolved.append("chapter")

    # ── previous version ──────────────────────────────────────────────────────
    if _PREV_VERSION_RE.search(low):
        res.references["version"] = "previous"

    return res
