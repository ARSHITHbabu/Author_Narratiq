"""
Stage 12 A17 — writing-suggestion hygiene (v2+ suggestions design only).

A pure filter applied AFTER the sharpening pass (it cannot live inside the
coercer: the sharpening pass discards its own work whenever the item count
changes). It removes only items that give the author nothing to act on:

  * no real recommendation — fewer than MIN_RECOMMENDATION_WORDS content
    words in `recommendation` (praise-only items fall here: an observation
    that only compliments, with no change proposed);
  * a near-duplicate of a higher-priority item in the SAME response.

Deliberately NOT done: no phrase list is ever applied to a recommendation.
"Replace 'big' with 'impressive'" is real advice even though "impressive" is
on every praise list; positive words inside a concrete recommendation are
kept. Praise inside quotes (the excerpt itself) is never counted either.

Recall comes first: when the filter would remove EVERY item, the caller
retries once and otherwise returns the honest "could not be generated" error —
an empty list is never presented as "no weaknesses".
"""
from __future__ import annotations

import re

MIN_RECOMMENDATION_WORDS = 4
DUPLICATE_JACCARD = 0.6           # stored outputs: max pair similarity 0.40 (v1), 0.21 (v2)

_STOP = frozenset((
    "the a an and or but of to in on at for with as is are was were be been being this that "
    "these those it its into from by your you their they them his her he she we our not no "
    "more less than so very can could would should will just also there here which who what "
    "when where how about any some each such may might must do does did has have had").split())
_PRAISE = re.compile(
    r"\b(great job|well done|nicely done|excellent work|shows real|works (?:really )?well|"
    r"is (?:strong|excellent|effective|vivid|compelling)|beautifully|masterful|impressive)\b", re.I)
_QUOTED = re.compile(r"[\"“”‘’'][^\"“”‘’']{2,}[\"“”‘’']")


def content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z']+", (text or "").lower())
            if len(w) > 2 and w.strip("'") not in _STOP}


def _rec_words(item: dict) -> int:
    return len(content_words(item.get("recommendation", "")))


def praise_only(item: dict) -> bool:
    """Praise in the observation (outside quotes) with no actionable
    recommendation. Reported for transparency; such an item is also caught
    by the no-recommendation rule."""
    obs = _QUOTED.sub(" ", item.get("observation") or "")
    return bool(_PRAISE.search(obs)) and _rec_words(item) < MIN_RECOMMENDATION_WORDS


def _similar(a: dict, b: dict) -> float:
    wa = content_words(f"{a.get('observation', '')} {a.get('recommendation', '')}")
    wb = content_words(f"{b.get('observation', '')} {b.get('recommendation', '')}")
    return len(wa & wb) / len(wa | wb) if wa and wb else 0.0


def clean_suggestions(items: list[dict]) -> tuple[list[dict], list[dict]]:
    """Returns (kept, dropped) where each dropped entry is {item, why}.
    `items` must already be priority-ordered (coerce_writing_suggestions
    sorts high → low), so the first of a duplicate pair is the one kept."""
    kept: list[dict] = []
    dropped: list[dict] = []
    for item in items:
        if _rec_words(item) < MIN_RECOMMENDATION_WORDS:
            dropped.append({"item": item, "why": "praise_only" if praise_only(item) else "no_recommendation"})
            continue
        dup = next((k for k in kept if _similar(k, item) >= DUPLICATE_JACCARD), None)
        if dup is not None:
            dropped.append({"item": item, "why": f"duplicate_of:{dup.get('id')}"})
            continue
        kept.append(item)
    return kept, dropped


# Stage 12.3 (agent review HR-11, 2026-10-06): live, on a 40-chapter synthetic
# manuscript, an item said "The phrase 'Wren pushed her way through the throng'
# is repeated verbatim" — the phrase occurs once. A repetition claim about a
# quoted phrase is the one kind of observation that can be checked mechanically,
# so it is: the claim survives only if some quoted phrase it names really occurs
# at least twice in the excerpt. An item that quotes nothing is left alone.
_REPEAT_CLAIM = re.compile(
    r"\b(repeat(?:s|ed|ing)?|repetition|verbatim|appears (?:twice|again|more than once)|"
    r"used (?:twice|again|more than once)|recurs|duplicated)\b", re.I)
_QUOTE_SPANS = re.compile(
    r"[\"“]([^\"“”]{3,}?)[\"”]|(?:(?<=^)|(?<=[\s(]))[‘']([^‘’]{3,}?)[’'](?=[\s.,;:!?)]|$)")


def _norm(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip().lower()


def false_repetition_claim(item: dict, excerpt: str) -> bool:
    """True when the item claims a quoted phrase repeats but no quoted phrase does."""
    said = " ".join(str(item.get(k) or "") for k in ("observation", "reason", "category"))
    if not _REPEAT_CLAIM.search(said):
        return False
    quotes = [q.strip(" .,;:!?") for m in _QUOTE_SPANS.finditer(str(item.get("observation") or item.get("reason") or ""))
              for q in m.groups() if q]
    quotes = [q for q in quotes if len(q.split()) >= 2]
    if not quotes:
        return False                       # nothing quoted: cannot check, keep it
    text = _norm(excerpt)
    return all(text.count(_norm(q)) < 2 for q in quotes)
