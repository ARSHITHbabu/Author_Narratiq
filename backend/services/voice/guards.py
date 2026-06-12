"""
Generic intent guards for the planner (D).

These are phrase-pattern heuristics, NOT hardcoded commands — they classify the
SHAPE of a request so the planner can keep simple things single-step and only
build multi-step workflows when the author clearly asked for multiple dependent
actions. They also keep questions from ever becoming write/destructive actions.
"""
from __future__ import annotations

import re

# Sequencing markers that signal a genuine compound (multi-step) request.
_COMPOUND = re.compile(
    r"\b(then|after that|and then|followed by|afterwards|next,|"
    r"once (?:that|you)|and also|as well as|after you)\b",
    re.IGNORECASE,
)

# Interrogative openers / shapes.
_QUESTION_OPENERS = (
    "who", "what", "whats", "what's", "where", "when", "why", "how", "which",
    "whose", "does", "do", "did", "is", "are", "was", "were", "can", "could",
    "should", "would", "tell me", "show me", "explain", "summarize", "describe",
    "list",
)

# Verbs that indicate a concrete action (vs a pure question) → keep their feature.
_ACTIONABLE = re.compile(
    r"\b(create|start|make|add|open|go to|rename|delete|remove|edit|update|"
    r"replace|swap|find|search|export|download|set|generate|continue|outline|"
    r"scan|translate|refine|polish|rewrite|adapt|import|upload|apply|restore|"
    r"check|detect|analyze|run)\b",
    re.IGNORECASE,
)


def is_compound(command: str) -> bool:
    """True only when the author chained multiple dependent actions."""
    if not command:
        return False
    if _COMPOUND.search(command):
        return True
    # Multiple distinct actionable verbs joined by 'and' also implies compound,
    # e.g. "rewrite chapter two and update the character profile".
    verbs = _ACTIONABLE.findall(command.lower())
    if len(verbs) >= 2 and re.search(r"\band\b", command, re.IGNORECASE):
        # distinct verbs only (two "find"s is one search, not compound)
        return len({v.lower() for v in verbs}) >= 2
    return False


def is_question(command: str) -> bool:
    if not command:
        return False
    c = command.strip().lower()
    if c.endswith("?"):
        return True
    first = c.split()[0] if c.split() else ""
    return first in _QUESTION_OPENERS or c.startswith(("tell me", "show me"))


def has_actionable_verb(command: str) -> bool:
    return bool(_ACTIONABLE.search(command or ""))
