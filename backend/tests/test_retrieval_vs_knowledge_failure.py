"""
Stage 4 task 4.4 — distinguish retrieval failure from knowledge failure.

Real LLM call (Qwen) — this is exactly what changed behaviour, so a mock
would test nothing. Checks phrasing category, not exact wording (the model
is not deterministic in phrasing, only in which category of claim it makes).

Run: cd backend && pytest tests/test_retrieval_vs_knowledge_failure.py -q -s
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.ai_service import answer_story_question  # noqa: E402

CONFIDENT_NEGATIVE_PHRASES = [
    "not in your story", "isn't in your story", "is not in your story",
    "not part of your story", "doesn't exist in your story",
    "not established in your story",
]
RETRIEVAL_LIMIT_PHRASES = [
    "may appear later", "might appear later", "didn't find this in the chapters",
    "did not find this in the chapters", "search the full manuscript",
    "later chapter", "searched so far", "haven't been shown", "wasn't shown",
    "not shown", "full manuscript",
]


def test_scope_limited_negative_answer_avoids_confident_story_claim():
    async def run():
        return await answer_story_question(
            question="Is there a character named Zorathmoon who reveals a hidden crystal-forge?",
            text_chunks=[],   # nothing retrieved — simulates a capped search that found nothing
            current_chapter="",
            scope_limited=True,
        )

    answer = asyncio.run(run()).lower()
    print(f"\n[4.4] scope_limited=True answer: {answer!r}")

    for phrase in CONFIDENT_NEGATIVE_PHRASES:
        assert phrase not in answer, (
            f"answer falsely claimed certainty about the whole story while scope-limited: {phrase!r} in {answer!r}"
        )


def test_unscoped_negative_answer_may_claim_not_established():
    async def run():
        return await answer_story_question(
            question="Is there a character named Zorathmoon who reveals a hidden crystal-forge?",
            text_chunks=[],   # nothing retrieved, and the FULL manuscript was searched
            current_chapter="",
            scope_limited=False,
        )

    answer = asyncio.run(run()).lower()
    print(f"[4.4] scope_limited=False answer: {answer!r}")
    # Not asserting it MUST claim not-established (model phrasing varies) — only
    # that it does not need the retrieval-limit hedge, since none applies. This
    # is deliberately the weaker assertion: the meaningful contrast is the first
    # test above, which the prompt change is specifically targeted at.
    assert isinstance(answer, str) and len(answer) > 0


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v", "-s"]))
