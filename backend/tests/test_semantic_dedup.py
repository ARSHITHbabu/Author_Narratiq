"""
Stage 4 task 4.13 — semantic search deduplication and diversity (no DB, no LLM).

_dedupe_chunks_by_content is a pure function over already-fetched rows, so it
is testable with lightweight fakes standing in for SQLAlchemy result rows —
matching this project's own convention (see test_character_hint_sync.py).

Run: cd backend && pytest tests/test_semantic_dedup.py -q
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.ai_service import _dedupe_chunks_by_content  # noqa: E402


def _row(text, score, chapter=1, chunk_index=0):
    return SimpleNamespace(text=text, score=score, chapter_number=chapter, chunk_index=chunk_index)


PASSAGE_A = (
    "The old castle stood on the hill overlooking the village, its towers "
    "worn by centuries of wind and rain, silent witness to every secret "
    "the villagers below tried to keep from each other."
)
# A 350-word-overlap-style near-duplicate: same core sentence, shifted window.
PASSAGE_A_OVERLAP = (
    "overlooking the village, its towers worn by centuries of wind and rain, "
    "silent witness to every secret the villagers below tried to keep from "
    "each other, and from themselves most of all."
)
PASSAGE_B = (
    "Deep in the eastern forest, the river ran cold and fast, carving a path "
    "no map had ever correctly traced, feeding the marshes where the old "
    "hermit kept his solitary watch."
)


def test_near_duplicate_overlap_is_dropped():
    rows = [_row(PASSAGE_A, 0.90), _row(PASSAGE_A_OVERLAP, 0.85), _row(PASSAGE_B, 0.80)]
    deduped = _dedupe_chunks_by_content(rows, top_k=3)
    texts = [r.text for r in deduped]
    assert PASSAGE_A in texts
    assert PASSAGE_A_OVERLAP not in texts, "near-duplicate overlapping chunk must be dropped"
    assert PASSAGE_B in texts


def test_distinct_passages_all_survive():
    rows = [_row(PASSAGE_A, 0.90), _row(PASSAGE_B, 0.80)]
    deduped = _dedupe_chunks_by_content(rows, top_k=2)
    assert len(deduped) == 2


def test_best_scoring_duplicate_is_the_one_kept():
    # PASSAGE_A_OVERLAP ranks higher — it must be the one KEPT, the lower-
    # ranked A dropped, proving dedup respects score order rather than
    # input order.
    rows = [_row(PASSAGE_A_OVERLAP, 0.95), _row(PASSAGE_A, 0.70)]
    deduped = _dedupe_chunks_by_content(rows, top_k=2)
    assert len(deduped) == 1
    assert deduped[0].text == PASSAGE_A_OVERLAP


def test_respects_top_k_after_dedup():
    # Genuinely distinct vocabulary per row (not just one differing token) —
    # low word-set overlap, so none of these should be deduped against each
    # other, and top_k should be the only thing limiting the result count.
    topics = [
        "The dragon slept beneath the mountain for a thousand years.",
        "Traders haggled over spices in the crowded harbor market.",
        "A single candle burned in the abandoned lighthouse window.",
        "The council debated taxes long into the frozen winter night.",
        "Children chased fireflies through the orchard after sunset.",
        "The blacksmith hammered steel until sparks lit the forge.",
        "Soldiers marched along the coastal road toward the capital.",
        "An old fisherman mended nets beside the quiet grey pier.",
        "The scholar deciphered runes carved into the temple wall.",
        "Wind swept sand across the dunes surrounding the oasis.",
    ]
    rows = [_row(t, 1.0 - i * 0.01) for i, t in enumerate(topics)]
    deduped = _dedupe_chunks_by_content(rows, top_k=3)
    assert len(deduped) == 3


def test_empty_input_returns_empty():
    assert _dedupe_chunks_by_content([], top_k=5) == []


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
