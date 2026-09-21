"""
Stage 4 task 4.14 — search relevance, ranking and stability (semantic path).

test_search_module.py already covers determinism and special characters for
the EXACT (regex) search path. This covers the one part that couldn't be
tested there: whether the SEMANTIC path (BGE-M3 embedding + pgvector + the
4.3 plot-importance re-rank + the 4.13 content dedup, all now layered
together) is still deterministic end to end against a real database.

Run: cd backend && pytest tests/test_semantic_search_stability.py -q -s
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from database import SessionLocal  # noqa: E402
from tests.fixtures.retrieval_fixture import build_fixture, cleanup_fixture  # noqa: E402
from services.ai_service import retrieve_chunks_from_store  # noqa: E402


@pytest.fixture(scope="module")
def fixture_manuscript():
    db = SessionLocal()

    async def _build():
        return await build_fixture(db)

    info = asyncio.run(_build())
    try:
        yield {**info, "db": db}
    finally:
        cleanup_fixture(db, info["story_id"], info["user_id"])
        db.close()


def test_identical_semantic_query_returns_identical_ordered_results(fixture_manuscript):
    db = fixture_manuscript["db"]
    story_id = fixture_manuscript["story_id"]

    async def run():
        r1 = await retrieve_chunks_from_store(
            "What secret was revealed beneath the ruined tower?", story_id, db, top_k=5,
        )
        r2 = await retrieve_chunks_from_store(
            "What secret was revealed beneath the ruined tower?", story_id, db, top_k=5,
        )
        return r1, r2

    r1, r2 = asyncio.run(run())
    key = lambda results: [(c["chapter"], c["chunk_index"], c["score"]) for c in results]
    assert key(r1) == key(r2), "identical semantic queries must return identical ordered results"


def test_special_characters_in_semantic_query_do_not_error(fixture_manuscript):
    db = fixture_manuscript["db"]
    story_id = fixture_manuscript["story_id"]

    async def run(q):
        return await retrieve_chunks_from_store(q, story_id, db, top_k=5)

    for query in ["What's the secret? (crystal-forge)", "eleven years — flood!", "[Vell] & \"the notebook\""]:
        result = asyncio.run(run(query))  # must not raise
        assert isinstance(result, list)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v", "-s"]))
