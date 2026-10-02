"""
Possible-duplicate character detection — Stage 12 remediation A7 (CAST-C4).

Finds pairs of characters in one story that MAY be the same person and says
why. It never merges anything: the author confirms every merge through the
existing merge endpoint (services/character_merge.py), because two similarly
named characters can be deliberately different people (decision, 2026-10-02).

Signals, strongest first. A pair is reported when any of them fires:

  same_name     a normalised name or alias of one equals a name or alias of
                the other ("Mara" registered twice, or "Mara" as an alias of
                "Mara Halloran" and as its own character).
  name_part     with honorifics removed (_name_tokens), one name's words are
                all part of the other's: "Captain Mara" / "Mara Halloran"
                share {mara}; "Mara" ⊂ "Mara Halloran". A single shared word
                that is the WHOLE of neither name ("John Smith" / "John Doe")
                does not fire.
  similar_spelling
                normalised names (or aliases) with a similarity ratio
                >= HINT_SIMILARITY_THRESHOLD (0.85): "Marek" / "Marekk".
                A spelling variant is a strong hint, not proof.
  similar_profile
                the BGE-M3 profile embeddings (already stored, no new model
                call) have cosine similarity >= PROFILE_SIMILARITY_THRESHOLD.
                Catches "the Magistrate" / "Vell" when both have profiles. It
                is reported on its own only above the threshold, which was
                calibrated so that distinct characters in the same story fall
                below it (see tests/test_character_duplicates.py).

Scores order the list for the author; they are not probabilities.
"""
from __future__ import annotations

from difflib import SequenceMatcher
from itertools import combinations
from typing import Iterable

from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from services.ai_service import _name_tokens
from services.character_names import HINT_SIMILARITY_THRESHOLD, normalise_name

# Calibrated on the pod with real BGE-M3 (Stage 12, A7; 2026-10-02): six distinct
# characters of one story peaked at 0.510 cosine with each other, while a
# restated profile of the same character scored 0.888. 0.80 sits between with
# margin on both sides (test_profile_threshold_separates_distinct_characters_live).
# A false positive costs the author one "Not the same person" click; nothing merges.
PROFILE_SIMILARITY_THRESHOLD = 0.80

_SCORES = {"same_name": 1.0, "name_part": 0.9, "similar_spelling": 0.8, "similar_profile": 0.7}

REASON_TEXT = {
    "same_name": "They share the name or alias “{x}”.",
    "name_part": "“{x}” and “{y}” could be the same person's shorter and longer name.",
    "similar_spelling": "“{x}” and “{y}” are spelled almost the same.",
    "similar_profile": "Their character profiles describe someone very similar.",
}


def _names(character) -> list[str]:
    out = [character.name or ""]
    out.extend(character.aliases or [])
    return [n for n in out if n and str(n).strip()]


def name_signals(a_names: Iterable[str], b_names: Iterable[str]) -> list[tuple[str, str, str]]:
    """Deterministic name signals between two characters' names and aliases.
    Returns (signal, a_name, b_name) triples, strongest signal first."""
    a_names, b_names = list(a_names), list(b_names)
    found: dict[str, tuple[str, str, str]] = {}

    for x in a_names:
        for y in b_names:
            nx, ny = normalise_name(x), normalise_name(y)
            if not nx or not ny:
                continue
            if nx == ny:
                found.setdefault("same_name", ("same_name", x, y))
                continue
            tx, ty = _name_tokens(x), _name_tokens(y)
            # Subset only: "John Smith" / "John Doe" share a word but neither
            # name is contained in the other, so they do not fire.
            if tx and ty and (tx <= ty or ty <= tx):
                found.setdefault("name_part", ("name_part", x, y))
            if SequenceMatcher(None, nx, ny).ratio() >= HINT_SIMILARITY_THRESHOLD:
                found.setdefault("similar_spelling", ("similar_spelling", x, y))

    return sorted(found.values(), key=lambda t: -_SCORES[t[0]])


def _profile_similarities(db: Session, story_id: str) -> dict[tuple[str, str], float]:
    """Pairwise cosine similarity of stored profile embeddings, in one SQL
    round trip (pgvector; Phase 2 rule R12). Keys are (smaller_id, larger_id)."""
    rows = db.execute(sql_text(
        "SELECT a.character_id AS a, b.character_id AS b, "
        "1 - (a.embedding <=> b.embedding) AS sim "
        "FROM character_profiles a JOIN character_profiles b "
        "  ON a.story_id = b.story_id AND a.character_id < b.character_id "
        "WHERE a.story_id = :sid AND a.embedding IS NOT NULL AND b.embedding IS NOT NULL"
    ), {"sid": story_id}).fetchall()
    return {(r.a, r.b): float(r.sim) for r in rows}


def find_duplicate_candidates(db: Session, story_id: str, limit: int = 50) -> list[dict]:
    """Possible duplicate pairs for one story, strongest first. The caller has
    already verified the story belongs to the requesting author; every
    character and profile read here is filtered by that story_id."""
    from models import Character

    chars = (
        db.query(Character)
        .filter(Character.story_id == story_id)
        .order_by(Character.created_at, Character.character_id)
        .all()
    )
    if len(chars) < 2:
        return []

    try:
        profile_sim = _profile_similarities(db, story_id)
    except Exception:
        db.rollback()
        profile_sim = {}

    out: list[dict] = []
    for a, b in combinations(chars, 2):
        signals = name_signals(_names(a), _names(b))
        key = (a.character_id, b.character_id) if a.character_id < b.character_id \
            else (b.character_id, a.character_id)
        sim = profile_sim.get(key)
        kinds = [s[0] for s in signals]
        if sim is not None and sim >= PROFILE_SIMILARITY_THRESHOLD:
            kinds.append("similar_profile")
        if not kinds:
            continue

        reasons = []
        for kind, x, y in signals:
            reasons.append({"kind": kind, "text": REASON_TEXT[kind].format(x=x, y=y)})
        if "similar_profile" in kinds:
            reasons.append({"kind": "similar_profile", "text": REASON_TEXT["similar_profile"]})

        score = max(_SCORES[k] for k in kinds) + 0.02 * (len(kinds) - 1)
        out.append({
            "character_a": a,
            "character_b": b,
            "score": round(min(score, 1.0), 3),
            "profile_similarity": round(sim, 3) if sim is not None else None,
            "reasons": reasons,
        })

    out.sort(key=lambda p: (-p["score"], p["character_a"].name.casefold(), p["character_b"].name.casefold()))
    return out[:limit]


def possible_duplicate_for_name(name: str, aliases: Iterable[str], existing) -> object | None:
    """For cast generation: the existing character a NEW suggestion may duplicate
    (name signals only — a suggestion has no stored embedding). Exact matches
    are handled by the caller as `already_exists`; this catches the rest."""
    best, best_score = None, 0.0
    cand_names = [name, *[a for a in aliases if a and a.strip()]]
    for c in existing:
        signals = name_signals(cand_names, _names(c))
        if not signals:
            continue
        s = _SCORES[signals[0][0]]
        if s > best_score:
            best, best_score = c, s
    return best
