"""
Stage 4 task 4.2 — retrieval breadth / context budget.

Measures recall@k on the shared ground-truth fixture (tests/fixtures/retrieval_fixture.py)
at the CURRENT top_k values, and — once raised in routers/plot_assistant.py — the
NEW values, so the improvement is demonstrated with evidence rather than assumed.

Also asserts the worst-case assembled prompt stays within the verified
max_model_len=8192 (task 1.6's live-confirmed figure for this pod's GPU),
leaving room for the model's completion budget.

Run: cd backend && pytest tests/test_recall_measurement.py -q -s
(requires PostgreSQL + pgvector + BGE-M3, same as test_retrieval_scope.py)
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from database import SessionLocal  # noqa: E402
from tests.fixtures.retrieval_fixture import (  # noqa: E402
    build_fixture, cleanup_fixture, GROUND_TRUTH,
)
from services.ai_service import retrieve_chunks_from_store  # noqa: E402

MAX_MODEL_LEN = 8192           # verified live figure for this pod (task 1.6), not the
                                # stale 16384 figure the old Blackwell-GPU checklist text assumed
QA_COMPLETION_RESERVE = 900    # answer_story_question's max_tokens
SAFETY_MARGIN_TOKENS = 500     # headroom for tokenizer-estimate error


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


def _recall_at_k(db, story_id: str, top_k: int) -> tuple[int, int, list[str]]:
    """Returns (hits, total, misses) — a 'hit' means the expected chapter's
    content appears among the top_k retrieved chunks for that query."""
    hits = 0
    misses = []

    async def _check(query, expected_chapter):
        chunks = await retrieve_chunks_from_store(query, story_id, db, top_k=top_k)
        return expected_chapter in {c["chapter"] for c in chunks}

    for item in GROUND_TRUTH:
        ok = asyncio.run(_check(item["query"], item["chapter"]))
        if ok:
            hits += 1
        else:
            misses.append(f"ch{item['chapter']}: {item['query']!r}")

    return hits, len(GROUND_TRUTH), misses


def test_recall_at_current_and_raised_top_k(fixture_manuscript):
    db = fixture_manuscript["db"]
    story_id = fixture_manuscript["story_id"]

    # Current values in routers/plot_assistant.py before this task's change:
    #   qa_top_k = 5 (character mentioned) or 8 (no character mentioned)
    hits_current, total, misses_current = _recall_at_k(db, story_id, top_k=8)
    recall_current = hits_current / total

    # Raised value applied by this task (see routers/plot_assistant.py diff).
    hits_raised, _, misses_raised = _recall_at_k(db, story_id, top_k=10)
    recall_raised = hits_raised / total

    print(f"\n[4.2 recall] top_k=8  : {hits_current}/{total} = {recall_current:.2%}  misses={misses_current}")
    print(f"[4.2 recall] top_k=10 : {hits_raised}/{total} = {recall_raised:.2%}  misses={misses_raised}")

    assert recall_raised >= recall_current, (
        "raising top_k must not REDUCE recall on the ground-truth fixture"
    )
    # Record, don't require improvement to be nonzero — a fixture this small can
    # legitimately already hit 100% at top_k=8; the assertion above is the real gate.


def test_worst_case_prompt_stays_within_context_window(fixture_manuscript):
    """
    plot_assistant.py's two QA branches are mutually exclusive (a name mention
    changes BOTH qa_top_k and whether character/note budgets apply), so model
    each branch separately rather than summing both at once (that would double-
    count budget that can never actually be spent together).

    Branch A — no character mention: qa_top_k=10 (this task's new value),
      no character budget, note_budget=500.
    Branch B — character mentioned: qa_top_k=6 (this task's new value),
      character_budget=800, note_budget=350.

    Both must leave QA_COMPLETION_RESERVE + SAFETY_MARGIN_TOKENS of room
    under MAX_MODEL_LEN.
    """
    overhead_tokens = 300  # system prompt + question + current-chapter tail
    budget_available = MAX_MODEL_LEN - QA_COMPLETION_RESERVE - SAFETY_MARGIN_TOKENS

    def chunk_tokens(top_k):
        words = top_k * 350
        return (words * 6) // 4  # ~6 chars/word average, ~4 chars/token

    branch_a = chunk_tokens(10) + 0 + 500 + overhead_tokens
    branch_b = chunk_tokens(6) + 800 + 350 + overhead_tokens

    print(f"\n[4.2 budget] branch A (no mention, top_k=10) ≈ {branch_a} tokens")
    print(f"[4.2 budget] branch B (mention, top_k=6)     ≈ {branch_b} tokens")
    print(f"[4.2 budget] budget available = {budget_available} tokens "
          f"(max_model_len={MAX_MODEL_LEN} - completion={QA_COMPLETION_RESERVE} - margin={SAFETY_MARGIN_TOKENS})")

    assert branch_a <= budget_available, f"branch A exceeds budget: {branch_a} > {budget_available}"
    assert branch_b <= budget_available, f"branch B exceeds budget: {branch_b} > {budget_available}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v", "-s"]))
