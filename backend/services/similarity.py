"""
Phase 3 P3-11 — duplicate / near-duplicate detection (spec §29).

Two stages, cheap first:

  Stage 1 (lexical, free, in-process): normalise, then average
    difflib.SequenceMatcher ratio over word sequences with token-set Jaccard
    over content words. >= similarity_lexical_hi → near_duplicate;
    <= similarity_lexical_lo → distinct. No model cost.
  Stage 2 (semantic, only for the ambiguous band, only for PINS with a
    stored embedding): embed the candidate ONCE with BGE-M3 and compare via
    pgvector `<=>` in SQL (CLAUDE.md: no numpy retrieval). Free-text
    comparands (session generations, avoid-set) have no stored vector and
    are never embedded — they stay lexical, by design (R1: nothing about an
    unpinned generation is computed for storage).

Nothing about the candidate text is stored or logged. Results are
informative only — never blocking (spec §40 P3-11).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Optional

from config import settings

_STOP = frozenset(
    "the a an and or but of to in on at for with from by as is was were are be been it its "
    "he she they we you i his her their our my your this that not no so then there here".split()
)


def _words(text: str) -> list[str]:
    return re.sub(r"[^\w\s]", " ", (text or "").lower()).split()


def lexical_score(a: str, b: str) -> float:
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return 0.0
    ratio = SequenceMatcher(None, wa, wb, autojunk=False).ratio()
    ca, cb = {w for w in wa if w not in _STOP}, {w for w in wb if w not in _STOP}
    jaccard = (len(ca & cb) / len(ca | cb)) if (ca or cb) else ratio
    return round((ratio + jaccard) / 2, 4)


def lexical_label(score: float) -> Optional[str]:
    """near_duplicate / distinct when stage 1 is decisive, None when ambiguous."""
    if score >= settings.similarity_lexical_hi:
        return "near_duplicate"
    if score <= settings.similarity_lexical_lo:
        return "distinct"
    return None


def semantic_label(score: float) -> str:
    if score >= settings.similarity_semantic_hi:
        return "near_duplicate"
    if score >= settings.similarity_semantic_mid:
        return "related"
    return "distinct"


@dataclass
class Match:
    score: float
    method: str
    label: str
    pin_id: Optional[str] = None
    text_index: Optional[int] = None

    def as_dict(self) -> dict:
        return {"pin_id": self.pin_id, "text_index": self.text_index,
                "score": self.score, "method": self.method, "label": self.label}


async def compare_against(
    text: str, *, pins: list, texts: list[str], story_id: str, user_id: str, db,
    allow_semantic: bool = True,
) -> tuple[list[Match], bool]:
    """Compare `text` against owned pins (already ownership-resolved by the
    caller) and free texts. Returns (matches, embedded_flag)."""
    from services.pin_store import get_pin_store
    store = get_pin_store()
    matches: list[Match] = []
    ambiguous_pin_ids: list[str] = []

    for pin in pins:
        score = lexical_score(text, store.get(pin))
        label = lexical_label(score)
        if label is None and allow_semantic and settings.pin_store_embedding and pin.embedding is not None:
            ambiguous_pin_ids.append(pin.pin_id)
        matches.append(Match(score, "lexical", label or "related", pin_id=pin.pin_id))

    for i, t in enumerate(texts or []):
        score = lexical_score(text, t)
        matches.append(Match(score, "lexical", lexical_label(score) or "related", text_index=i))

    embedded = False
    if ambiguous_pin_ids:
        try:
            semantic = await _semantic_scores(text, ambiguous_pin_ids, story_id, user_id, db)
            embedded = True
            for m in matches:
                if m.pin_id in semantic:
                    m.score, m.method = semantic[m.pin_id], "semantic"
                    m.label = semantic_label(m.score)
        except Exception as exc:  # stage 2 failure degrades to stage 1, never fails the request
            import logging
            logging.getLogger(__name__).warning("[similarity] semantic stage failed (%s) — lexical only", type(exc).__name__)

    matches.sort(key=lambda m: m.score, reverse=True)
    return matches, embedded


async def _semantic_scores(text: str, pin_ids: list[str], story_id: str, user_id: str, db) -> dict[str, float]:
    from sqlalchemy import text as sql
    from services.ai_service import embed_text, vector_literal, vector_similarity
    from middleware.concurrency import embedding_semaphore
    async with embedding_semaphore():
        q = vector_literal(await embed_text(text))
    rows = db.execute(
        sql(f"""
            SELECT pin_id, {vector_similarity('embedding')} AS score
            FROM ai_generation_pins
            WHERE pin_id = ANY(:ids) AND user_id = :uid AND story_id = :sid
              AND embedding IS NOT NULL
        """),
        {"q": q, "ids": pin_ids, "uid": user_id, "sid": story_id},
    ).fetchall()
    return {r.pin_id: round(float(r.score), 4) for r in rows}


def anti_echo_score(output: str, source: str) -> float:
    """P3-06: how much of the SOURCE DRAFT's wording the derived output kept
    (lexical, 0..1). Used to warn when a 'variation' came back as a near-copy."""
    return lexical_score(output, source)
