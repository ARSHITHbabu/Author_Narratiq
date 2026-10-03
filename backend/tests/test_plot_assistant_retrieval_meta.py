"""
Stage 12.1 — the Plot Assistant's structured retrieval metadata (task 4.4) must
describe the evidence the model actually received, for every intent.

Found live (task 4.1 check, PA-C1): a whole-story question classified
"creative" returned retrieval = {chunks_retrieved: 0, chapters_covered: []}
while context_used said "Ch1, Ch2, Ch3 retrieved": creative suggestions are
grounded on chapter SUMMARIES, which the metadata did not report.

Hermetic: every model and embedding call is stubbed.

    DATABASE_URL=...narratiq_test pytest backend/tests/test_plot_assistant_retrieval_meta.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402

from _phase3_helpers import two_authors  # noqa: E402
from routers.plot_assistant import suggestion_summary_chapters  # noqa: E402

SUMMARIES = [{"chapter": 3, "summary": "s3", "score": 0.6}, {"chapter": 1, "summary": "s1", "score": 0.5}]
PASSAGES = [{"chapter": 2, "text": "p2", "score": 0.7, "chunk_index": 0}]


def test_helper_reports_retrieved_summaries_for_creative_and_mixed():
    for intent in ("creative", "mixed"):
        assert suggestion_summary_chapters(intent, SUMMARIES, [{"chapter": 9}]) == [1, 3]


def test_helper_falls_back_to_the_recent_summaries_the_prompt_receives():
    assert suggestion_summary_chapters("creative", [], [{"chapter": 5}, {"chapter": 4}]) == [4, 5]


def test_helper_reports_no_summaries_for_qa():
    assert suggestion_summary_chapters("qa", SUMMARIES, [{"chapter": 5}]) == []


@pytest.mark.parametrize("intent,passages,summaries", [
    ("qa", [2], []),
    ("creative", [], [1, 3]),
    ("mixed", [2], [1, 3]),
])
def test_router_metadata_matches_the_evidence_used(intent, passages, summaries, monkeypatch):
    from middleware.rate_limit import limiter
    from routers import plot_assistant as pa

    monkeypatch.setattr(limiter, "enabled", False)

    async def fake_intent(_q):
        return intent

    async def summary_hits(*_a, **_k):
        return list(SUMMARIES)

    async def passage_hits(*_a, **_k):
        return list(PASSAGES)

    async def nothing(*_a, **_k):
        return []

    async def fake_suggestions(**_kw):
        return [{"id": 1, "text": "An idea.", "rationale": "Because."}]

    async def fake_answer(**_kw):
        return "An answer."

    monkeypatch.setattr(pa, "detect_query_intent", fake_intent)
    monkeypatch.setattr(pa, "retrieve_relevant_chunks", summary_hits)
    monkeypatch.setattr(pa, "retrieve_chunks_from_store", passage_hits)
    monkeypatch.setattr(pa, "retrieve_character_context", nothing)
    monkeypatch.setattr(pa, "retrieve_note_context", nothing)
    monkeypatch.setattr(pa, "generate_plot_suggestions", fake_suggestions)
    monkeypatch.setattr(pa, "answer_story_question", fake_answer)

    with two_authors() as (_db, a, _b, client):
        r = client.post("/api/plot-assistant/", headers=a.headers,
                        json={"story_id": a.sid, "question": "What happens across the story?", "scope": "full"})
        assert r.status_code == 200, r.text[:300]
        meta = r.json()["retrieval"]
        assert meta["chapters_covered"] == passages
        assert meta["chunks_retrieved"] == len(passages)
        assert meta["summary_chapters"] == summaries
