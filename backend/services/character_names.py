"""
Character-name normalisation and unresolved-hint reconciliation.

One place decides whether a name the author has registered (a character name or
alias) is the same name as an entry in the unrecognised-names queue
(`CharacterHint`). Phase 2 Issue 9 was that nothing made that decision at all
outside hint *creation*: a name added by hand, confirmed from cast generation or
gained as an alias stayed in the unrecognised list forever, so the same character
appeared as both recognised and unrecognised.

Matching semantics — deliberately asymmetric, and the asymmetry is the point:

  * CREATION   (`hint_is_redundant`) suppresses a *new* hint on an exact
    normalised match OR a similarity ratio >= HINT_SIMILARITY_THRESHOLD.
    Being generous here only costs the author a hint they never see.

  * RECONCILE  (`resolve_hints_for_names`) dismisses an *existing* hint only on
    an EXACT normalised match of a character name or alias.
    Being generous here would silently hide a genuinely distinct character —
    "Marek" must never dismiss a hint for "Marekk". A hint that survives is
    visible and one click from dismissal; a hint wrongly removed is invisible.

Normalisation is shared by both: trim, collapse internal whitespace, casefold.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Iterable

# Used at hint-creation time only. Documented here so there is a single definition.
HINT_SIMILARITY_THRESHOLD = 0.85

_WHITESPACE = re.compile(r"\s+")


def normalise_name(name: str | None) -> str:
    """Trim, collapse internal whitespace, casefold. '  Marek   Halvorsen ' → 'marek halvorsen'."""
    if not name:
        return ""
    return _WHITESPACE.sub(" ", str(name).strip()).casefold()


def known_names(characters: Iterable) -> set[str]:
    """Every normalised name and alias currently registered for a story."""
    known: set[str] = set()
    for character in characters:
        norm = normalise_name(getattr(character, "name", None))
        if norm:
            known.add(norm)
        for alias in (getattr(character, "aliases", None) or []):
            alias_norm = normalise_name(alias)
            if alias_norm:
                known.add(alias_norm)
    return known


def hint_is_redundant(name: str, known: set[str]) -> bool:
    """Creation-time test: would this hint duplicate something already registered?
    Exact match, or close enough that hinting it would be noise."""
    norm = normalise_name(name)
    if not norm:
        return True
    if norm in known:
        return True
    return any(SequenceMatcher(None, norm, k).ratio() >= HINT_SIMILARITY_THRESHOLD for k in known)


def resolve_hints_for_names(db, story_id: str, names: Iterable[str]) -> list[str]:
    """Dismiss every live hint whose name is EXACTLY (normalised) one of `names`.

    Does not commit — the caller owns the transaction, so the character mutation
    and this reconciliation land together or not at all.

    Returns the hint ids dismissed, for logging and for the caller's response.
    """
    from models import CharacterHint

    targets = {normalise_name(n) for n in names if normalise_name(n)}
    if not targets:
        return []

    live = (
        db.query(CharacterHint)
        .filter(
            CharacterHint.story_id == story_id,
            CharacterHint.is_dismissed == False,  # noqa: E712
        )
        .all()
    )

    dismissed: list[str] = []
    for hint in live:
        if normalise_name(hint.suggested_name) in targets:
            hint.is_dismissed = True
            dismissed.append(hint.hint_id)
    return dismissed


def names_of(character) -> list[str]:
    """A character's name plus its aliases — what reconciliation matches against."""
    names = [getattr(character, "name", "") or ""]
    names.extend(getattr(character, "aliases", None) or [])
    return [n for n in names if n and str(n).strip()]
