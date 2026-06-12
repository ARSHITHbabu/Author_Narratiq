"""
Deterministic fast-path router.

For a small set of HIGH-PRECISION command patterns we skip the LLM entirely and
route directly. This makes the most common (and most safety-sensitive) commands
deterministic and low-latency instead of depending on Qwen sampling — e.g.
"replace X with Y", "open chapter 3", "delete this story", "export".

Only single-intent commands are fast-routed; anything containing a chaining word
("then", "after that", "and also") falls through to the multi-step planner.
Returns (capability, action, params) or None.
"""
from __future__ import annotations

import re

_CHAIN = re.compile(r"\b(then|after that|and then|followed by|afterwards)\b", re.IGNORECASE)

# ── Selected-text transform intents → ai_transform actions (generic, not phrases) ──
# Ordered: the first matching intent wins. These map a transform REQUEST to the
# correct ai_transform action. Used to route selected-text transforms to the
# ai_transform FEATURE deterministically — never to RAG/Q&A/plot.
_TRANSFORM_INTENTS: list[tuple[str, re.Pattern]] = [
    ("translate", re.compile(r"\btranslate\b|\bin (spanish|french|german|hindi|tamil|japanese|chinese|italian|portuguese)\b", re.I)),
    ("age_adapt", re.compile(r"\b(younger|older|children|kids|child|teen|teens|young[- ]?adult|\bya\b|"
                             r"adult|audience|age[- ]?group|grade level|for kids)\b", re.I)),
    ("emotion",   re.compile(r"\b(emotion\w*|darker|sadder|happier|scar(y|ier)|tense\w*|angr(y|ier)|"
                             r"suspense\w*|dramatic|moody|gripping|chilling|intens\w*|"
                             r"more (fear\w*|tension|suspense\w*|dread|sadness|joy\w*|anger|feeling|powerful)|"
                             r"heighten|more (emotional|moving|visceral))\b", re.I)),
    ("style",     re.compile(r"\b(gothic|noir|lyrical|minimalist|poetic|hard[- ]?boiled|whimsical|"
                             r"\bstyle\b|in the style of)\b", re.I)),
    ("tone",      re.compile(r"\b(tone|mood|formal|informal|casual|lighter|serious|playful|"
                             r"more (formal|casual|serious|lighthearted))\b", re.I)),
    # generic rewrite/refine bucket (refine action) — simplify/expand/shorten/polish/rephrase
    ("refine",    re.compile(r"\b(refine|polish|improve|clean up|tighten|rewrite|rephrase|reword|"
                             r"simplify|simpler|plainer|expand|lengthen|flesh out|shorten|condense|"
                             r"trim|make (it|this) (better|clearer|smoother|stronger|flow))\b", re.I)),
]

# An imperative transform usually targets "this/that/it/the paragraph/selection".
_TRANSFORM_TARGET = re.compile(
    r"\b(this|that|it|the (paragraph|sentence|line|passage|text|selection|part|section)|"
    r"selected|highlighted|this (paragraph|sentence|bit|part))\b", re.I)
_IMPERATIVE = re.compile(r"\b(make|rewrite|rephrase|reword|change|turn|convert|adapt|refine|polish|"
                         r"improve|simplify|expand|shorten|translate|set|give)\b", re.I)
_QUESTION_OPENER = re.compile(r"^\s*(what|who|where|when|why|how|which|is|are|does|do|did|can|could)\b", re.I)


def transform_action(command: str, has_selection: bool) -> str | None:
    """Return the ai_transform action for a selected-text transform request, else None.

    Routes deterministically to text_transform so transforms NEVER fall through to
    RAG/story-QA/plot. Guarded so it doesn't hijack factual questions
    ('what is the tone of the story') — requires a selection OR an imperative target.
    """
    if not command:
        return None
    c = command.strip()
    # Don't treat a factual question as a transform unless text is selected.
    if _QUESTION_OPENER.match(c) and not has_selection:
        return None
    for action, rx in _TRANSFORM_INTENTS:
        if rx.search(c):
            # Require either a live selection, an imperative verb, or a "this/the paragraph" target.
            if has_selection or _IMPERATIVE.search(c) or _TRANSFORM_TARGET.search(c):
                return action
    return None

_REPLACE = re.compile(
    r"\breplace\s+(?:the\s+(?:name|word|phrase|term)\s+)?(.+?)\s+with\s+(.+?)"
    r"(?:\s+(?:in|throughout|across)\b.*)?$",
    re.IGNORECASE,
)
_OPEN_CHAPTER = re.compile(r"\b(?:open|go to|switch to|show|jump to)\s+chapter\s+(\w+)", re.IGNORECASE)
_CREATE_STORY = re.compile(r"\b(?:create|start|begin|make)\b.{0,30}\b(?:story|novel|book|manuscript)\b", re.IGNORECASE)
_DELETE_CHAPTER = re.compile(r"\b(?:delete|remove)\b.{0,20}\bchapter\b", re.IGNORECASE)
_DELETE_STORY = re.compile(r"\bdelete\b.{0,20}\b(?:story|project|novel|book)\b", re.IGNORECASE)
_RENAME_STORY = re.compile(r"\brename\b.{0,20}\b(?:story|project)\b", re.IGNORECASE)
_EXPORT = re.compile(r"\bexport\b", re.IGNORECASE)
_PACING_SET = re.compile(r"\b(?:set|target).{0,30}\b(?:pacing|words?\s+per\s+chapter)\b", re.IGNORECASE)
_CALLED = re.compile(r"\b(?:called|named|titled|entitled)\s+(.+)$", re.IGNORECASE)
_NUM = re.compile(r"(\d+)")


def fast_route(command: str):
    c = (command or "").strip()
    if not c or _CHAIN.search(c):
        return None
    low = c.lower()

    # replace X with Y → search_replace.replace (destructive)
    m = _REPLACE.search(c)
    if m:
        return ("search_replace", "replace",
                {"query": m.group(1).strip().strip('"\'.'),
                 "replacement": m.group(2).strip().strip('"\'.')})

    # open chapter N → chapter_mgmt.open
    m = _OPEN_CHAPTER.search(c)
    if m:
        return ("chapter_mgmt", "open", {"chapter_number": m.group(1)})

    # delete chapter → chapter_mgmt.delete (destructive); check BEFORE story
    m = _DELETE_CHAPTER.search(c)
    if m:
        params = {}
        n = re.search(r"chapter\s+(\w+)", c, re.IGNORECASE)
        if n:
            params["chapter_number"] = n.group(1)
        return ("chapter_mgmt", "delete", params)

    # delete story → project_mgmt.delete (destructive)
    if _DELETE_STORY.search(c):
        return ("project_mgmt", "delete", {})

    # rename story → project_mgmt.rename
    if _RENAME_STORY.search(c):
        params = {}
        t = _CALLED.search(c) or re.search(r"\bto\s+(.+)$", c, re.IGNORECASE)
        if t:
            params["title"] = t.group(1).strip().strip('"\'.')
        return ("project_mgmt", "rename", params)

    # create story → project_mgmt.create
    if _CREATE_STORY.search(c):
        params = {}
        t = _CALLED.search(c)
        if t:
            params["title"] = t.group(1).strip().strip('"\'.')
        return ("project_mgmt", "create", params)

    # export → export.export
    if _EXPORT.search(c):
        fmt = "pdf" if "pdf" in low else "docx"
        return ("export", "export", {"format": fmt})

    # set pacing goal of N words per chapter → pacing_goals.set
    if _PACING_SET.search(c):
        params = {}
        n = _NUM.search(c)
        if n:
            params["target_words_per_chapter"] = int(n.group(1))
        return ("pacing_goals", "set", params)

    return None
