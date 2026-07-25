"""
Intent classification — BGE-M3 shortlist + Qwen classify/extract.

Two-stage by design (keeps the Qwen prompt small and scalable as capabilities
grow): catalog.shortlist() narrows ~25 capabilities to the top-k candidates via
BGE-M3 cosine, then Qwen picks the capability+action and extracts a parameter
hint over just those candidates.

This module provides the single-step classifier (also used as the planner's
fallback). The multi-step graph is produced by planner.py.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from . import catalog
from .capabilities import CAPABILITY_REGISTRY, get_action, disambiguate_action

logger = logging.getLogger(__name__)


@dataclass
class DetectedIntent:
    capability: str
    action: str
    confidence: float
    params: dict[str, Any] = field(default_factory=dict)
    candidates: list[str] = field(default_factory=list)
    reasoning: str = ""

    @property
    def intent_key(self) -> str:
        return f"{self.capability}.{self.action}"


_SYSTEM = (
    "You are the intent classifier for a novel-writing voice assistant. "
    "Given the author's spoken command and a list of candidate capabilities "
    "(each with allowed actions), choose the SINGLE best capability and action. "
    "Extract any obvious parameters the author stated (title, tone, emotion, "
    "target_age, target_language, query, replacement, name, chapter_goal, etc.). "
    "Respond with ONLY a JSON object:\n"
    '{"capability": "...", "action": "...", "confidence": 0.0-1.0, '
    '"params": {..}, "reasoning": "short"}\n'
    "Rules: capability and action MUST come from the candidate list. "
    "confidence reflects how clearly the command maps to that action. "
    "If the command does not match any candidate, use capability \"none\"."
)


def coerce_intent(parsed) -> tuple[dict | None, int]:
    """
    Coerce a classification response.

    Returns None when the model produced nothing recognisable — which used to
    become ``{}`` via _extract_json's fallback, and from there a *guess*: the
    top shortlist candidate at confidence 0.4. Below the 0.55 threshold that
    guess becomes a clarification prompt, so an unreadable classification looked
    to the author exactly like "the agent didn't understand me" — a plausible
    contributor to Phase 2 Issue 4's intermittency.
    """
    if not isinstance(parsed, dict):
        return None, 0
    if not str(parsed.get("capability") or "").strip():
        return None, 0
    return parsed, 0


async def classify(command: str, context_brief: str = "",
                   k: int | None = None) -> DetectedIntent:
    from config import settings
    from services.ai_service import complete_structured

    k = k or settings.voice_intent_shortlist_k
    shortlisted = catalog.shortlist(command, k=k)
    cand_names = [c for c, _ in shortlisted]
    brief = catalog.candidate_brief(cand_names)

    user = (
        f"Command: {command!r}\n\n"
        f"Candidate capabilities:\n{brief}\n\n"
        f"{('Context: ' + context_brief) if context_brief else ''}\n\n"
        "Return the JSON object."
    )
    # Structured-output contract (task 3.4): one bounded reprompt, then an
    # honest failure. Metadata only in logs — never the command text, which is
    # the author's own words about their manuscript.
    data, meta = await complete_structured(
        _SYSTEM, user, coerce=coerce_intent,
        temperature=0.0, max_tokens=300, label="voice_intent",
    )
    if data is None:
        logger.warning("[voice.intent] stage=classify outcome=unreadable candidates=%d",
                       len(cand_names))
        return DetectedIntent("none", "", 0.0, {}, cand_names,
                              "classification could not be read")

    cap = (data.get("capability") or "").strip()
    action = (data.get("action") or "").strip()
    conf = float(data.get("confidence") or 0.0)
    params = data.get("params") or {}
    reasoning = data.get("reasoning") or ""

    # Validate against the registry; repair where possible.
    if cap == "none":
        return DetectedIntent("none", "", conf, params, cand_names, reasoning)

    if cap not in CAPABILITY_REGISTRY:
        # repair: take the top shortlist candidate
        if not cand_names:
            return DetectedIntent("none", "", 0.0, {}, cand_names, "no candidates")
        cap = cand_names[0]
        conf = min(conf, 0.4)
        reasoning = (reasoning + " [repaired capability]").strip()

    # Pick the action by verb cues (never blindly default to the first action —
    # that turned "delete" into "create"). Disambiguation falls back safely.
    action = disambiguate_action(cap, command, action)

    # Stage decision log (task 3.6.1). Metadata only: which capability won, how
    # confident, how many candidates it chose from. An intermittent fault is
    # diagnosable from this line; the author's words are not in it.
    logger.info("[voice.intent] stage=classify capability=%s action=%s confidence=%.2f "
                "candidates=%d repaired=%s",
                cap, action, conf, len(cand_names), "[repaired" in reasoning)

    return DetectedIntent(cap, action, conf, params if isinstance(params, dict) else {},
                          cand_names, reasoning)
