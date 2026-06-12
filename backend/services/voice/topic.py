"""
Topic classifier for routing (D).

Replaces the old "any question → plot_assistant" fallback. Given a command, it
maps the TOPIC to the correct feature capability. Deterministic patterns first
(high precision); the planner falls back to embedding shortlist + Qwen only when
no topic matches. plot_assistant is reachable ONLY via brainstorming intent.

Generic — keyed on topic words, never on specific story/character names.
"""
from __future__ import annotations

import re

# Ordered most-specific first; first match wins. Each entry: (regex, capability, action)
_TOPIC_RULES: list[tuple[re.Pattern, str, str]] = [
    # ── character relationship ────────────────────────────────────────────────
    (re.compile(r"\b(relationship|connection|related|know each other|allies?|enemies|rivals?)\b"
                r".*\bbetween\b|\bbetween\b.*\b(relationship|connection)\b"
                r"|\bhow (are|do) .* (related|connected|know each other)\b", re.I),
     "character_relationship", "ask"),

    # ── plot brainstorming (the ONLY path to plot_assistant) ──────────────────
    (re.compile(r"\b(brainstorm|what should happen|what could happen|give me (some )?ideas|"
                r"plot ideas?|suggest .*(plot|direction|twist)|where (could|should) the story go|"
                r"ideas for the (next )?(chapter|plot|story))\b", re.I),
     "plot_assistant", "brainstorm"),

    # ── analysis topics (route to their analysis features) ────────────────────
    (re.compile(r"\b(continuity|consistent|contradiction)\b", re.I), "continuity_check", "analyze"),
    (re.compile(r"\b(plot hole|plot-hole|logic (problem|error|gap)|inconsisten)\b", re.I), "plot_holes", "analyze"),
    (re.compile(r"\b(style drift|writing style chang|tone drift)\b", re.I), "style_drift", "analyze"),
    (re.compile(r"\b(duplicate|repeated|redundant) scenes?\b", re.I), "duplicate_scenes", "analyze"),
    (re.compile(r"\bemotional (arc|curve|journey)\b", re.I), "emotional_arc", "analyze"),
    (re.compile(r"\bpacing\b", re.I), "pacing_goals", "get"),

    # ── character question (who/what/where about a character) ─────────────────
    (re.compile(r"\b(who is|who'?s|who are)\b"
                r"|\b(character|protagonist|antagonist|villain|hero)\b"
                r".*\b(want|like|goal|appear|describe|is)\b"
                r"|\b(what does|what do|where does|where do|describe|tell me about)\b"
                r".*\b(character|he|she|they|him|her)\b", re.I),
     "character_qa", "ask"),
]

# Words that mean the user wants an ACTION, not a question (skip topic Q&A routing).
_ACTION_OVERRIDE = re.compile(
    r"\b(create|make|add|open|delete|remove|rename|replace|swap|export|set|"
    r"generate|continue|outline|scan|import|upload|refine|polish|translate|rewrite|"
    r"check|run|analyze|detect|search|find all|set a)\b", re.I)


def classify_topic(command: str):
    """Return (capability, action) for a clear topic, else None."""
    if not command:
        return None
    c = command.strip()
    for rx, cap, action in _TOPIC_RULES:
        if rx.search(c):
            return (cap, action)
    return None


def is_action_command(command: str) -> bool:
    return bool(_ACTION_OVERRIDE.search(command or ""))
