"""
Stage 12 remediation A1 — the Plot Assistant must not receive later-chapter
Story Intelligence under the default chapter scope (decision D-1).

Before the fix, ``build_integration_context`` was called with no chapter cap:
a chapter-scoped creative/mixed request received the whole-manuscript premise,
themes, conflict, character secrets/arc stages, unresolved threads and every
story-memory entry (none of which records the chapter it came from). Stage 11
made Story Intelligence actually populate, which turned this into a live leak.

Hermetic: no vLLM and no BGE-M3 — embedding and every model call are stubbed.
Each test creates its own user/story and deletes exactly those rows.

    DATABASE_URL=...narratiq_test pytest backend/tests/test_plot_assistant_intel_scope.py -q
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402

from _phase3_helpers import two_authors  # noqa: E402
from models import (  # noqa: E402
    StoryDNA, StoryGenreHierarchy, StoryMemoryEntry, StoryRiskRegister,
)

DIM = 1024
VEC = [1.0] + [0.0] * (DIM - 1)

SECRET = "Magistrate Vell faked his own death in chapter five"
EARLY = "The lighthouse key was hidden in chapter one"
PREMISE = "A presumed-dead magistrate returns to reclaim the harbour"
THREAD = "Who forged the drowning record"


def _seed_intel(db, story_id: str) -> None:
    db.add(StoryDNA(story_id=story_id, premise=PREMISE, central_question="Will Vell be exposed?",
                    pov_style="third limited", tense="past"))
    db.add(StoryGenreHierarchy(story_id=story_id, primary_genre="mystery", tone_markers=["brooding"]))
    db.add(StoryRiskRegister(story_id=story_id, unresolved_threads=[THREAD], critical_issues=["x"]))
    # Whole-manuscript memory: no chapter provenance (how every writer stores it today).
    db.add(StoryMemoryEntry(story_id=story_id, memory_type="character", memory_key="character.vell.secret",
                            content=SECRET, embedding=VEC))
    # Provenance-tagged memory: one inside, one beyond a chapter-2 cap.
    db.add(StoryMemoryEntry(story_id=story_id, memory_type="plot", memory_key="plot.key",
                            content=EARLY, chapter_first_established=1, chapter_last_updated=1, embedding=VEC))
    db.add(StoryMemoryEntry(story_id=story_id, memory_type="plot", memory_key="plot.late",
                            content=SECRET + " (tagged)", chapter_first_established=1,
                            chapter_last_updated=5, embedding=VEC))
    db.commit()


def _drop_intel(db, story_ids) -> None:
    db.rollback()
    for model in (StoryMemoryEntry, StoryDNA, StoryGenreHierarchy, StoryRiskRegister):
        db.query(model).filter(model.story_id.in_(story_ids)).delete(synchronize_session=False)
    db.commit()


@pytest.fixture
def stub_embedding(monkeypatch):
    from services import story_intel_service

    async def fake_embed(_text):
        return VEC

    monkeypatch.setattr(story_intel_service, "embed_text", fake_embed)


def _flatten(ctx: dict) -> str:
    return repr(ctx)


def test_capped_context_contains_no_whole_manuscript_analysis(stub_embedding):
    from services.story_intel_service import build_integration_context

    with two_authors() as (db, a, _b, client):
        try:
            _seed_intel(db, a.sid)
            ctx = asyncio.run(build_integration_context(db, a.sid, query="Where is Vell?", top_k=8,
                                                        max_chapter_number=2))
            text = _flatten(ctx)
            assert SECRET not in text, "chapter-scoped context leaked a whole-manuscript secret"
            assert PREMISE not in text and THREAD not in text
            for key in ("story_premise", "central_question", "primary_theme", "primary_conflict",
                        "characters", "critical_issues", "unresolved_threads"):
                assert key not in ctx, f"{key} reached a chapter-scoped request"
            # Provenance-tagged memory inside the cap survives; beyond it does not.
            assert [h["content"] for h in ctx["memory_hits"]] == [EARLY]
            # Spoiler-neutral style facts are still provided.
            assert ctx["genre"] == "mystery" and ctx["pov_style"] == "third limited"
        finally:
            _drop_intel(db, [a.sid])


def test_full_scope_still_returns_everything(stub_embedding):
    from services.story_intel_service import build_integration_context

    with two_authors() as (db, a, _b, client):
        try:
            _seed_intel(db, a.sid)
            ctx = asyncio.run(build_integration_context(db, a.sid, query="Where is Vell?", top_k=8))
            contents = {h["content"] for h in ctx["memory_hits"]}
            assert SECRET in contents and EARLY in contents and SECRET + " (tagged)" in contents
            assert ctx["story_premise"] == PREMISE
            assert ctx["unresolved_threads"] == [THREAD]
        finally:
            _drop_intel(db, [a.sid])


def test_cap_never_returns_another_authors_memory(stub_embedding):
    from services.story_intel_service import build_integration_context

    with two_authors() as (db, a, b, client):
        try:
            _seed_intel(db, b.sid)          # only author B has intelligence
            for cap in (None, 2):
                ctx = asyncio.run(build_integration_context(db, a.sid, query="Vell", top_k=8,
                                                            max_chapter_number=cap))
                assert ctx.get("memory_hits", []) == []
                assert SECRET not in _flatten(ctx)
        finally:
            _drop_intel(db, [b.sid])


@pytest.mark.parametrize("intent", ["creative", "mixed"])
@pytest.mark.parametrize("scope,leaks", [("chapter", False), ("full", True)])
def test_router_passes_the_scope_cap_to_story_intelligence(intent, scope, leaks, stub_embedding, monkeypatch):
    """End to end through POST /api/plot-assistant/ with every model call stubbed:
    the intel context handed to the suggestion generator is capped exactly when
    the request is chapter-scoped."""
    from middleware.rate_limit import limiter
    from routers import plot_assistant as pa

    monkeypatch.setattr(limiter, "enabled", False)
    seen: dict = {}

    async def fake_intent(_q):
        return intent

    async def no_chunks(*_a, **_k):
        return []

    async def fake_suggestions(**kw):
        seen["intel"] = kw.get("intel_context")
        return [{"id": 1, "text": "An idea.", "rationale": "Because."}]

    async def fake_answer(**_kw):
        return "An answer."

    monkeypatch.setattr(pa, "detect_query_intent", fake_intent)
    monkeypatch.setattr(pa, "retrieve_relevant_chunks", no_chunks)
    monkeypatch.setattr(pa, "retrieve_chunks_from_store", no_chunks)
    monkeypatch.setattr(pa, "retrieve_character_context", no_chunks)
    monkeypatch.setattr(pa, "retrieve_note_context", no_chunks)
    monkeypatch.setattr(pa, "generate_plot_suggestions", fake_suggestions)
    monkeypatch.setattr(pa, "answer_story_question", fake_answer)

    with two_authors() as (db, a, _b, client):
        try:
            _seed_intel(db, a.sid)
            r = client.post(
                "/api/plot-assistant/", headers=a.headers,
                json={"story_id": a.sid, "question": "What should Vell do next?",
                      "current_chapter_number": 2, "scope": scope})
            assert r.status_code == 200, r.text[:300]
            text = _flatten(seen["intel"])
            assert (SECRET in text) is leaks
            assert (PREMISE in text) is leaks
            assert r.json()["scope_used"] == scope
        finally:
            _drop_intel(db, [a.sid])


def test_router_refuses_another_authors_story():
    from middleware.rate_limit import limiter

    limiter.enabled = False
    try:
        with two_authors() as (_db, a, b, client):
            r = client.post(
                "/api/plot-assistant/", headers=a.headers,
                json={"story_id": b.sid, "question": "Anything?", "current_chapter_number": 1})
            assert r.status_code == 404
    finally:
        limiter.enabled = True


# ── Stage 12 A13 part 1 — D-1: chapter scope without a chapter number ────────

@pytest.mark.parametrize("chapter", [None, 0, -1])
def test_chapter_scope_without_a_chapter_is_refused_before_any_retrieval(chapter, monkeypatch):
    """It used to mean "no cap at all" — a silent whole-manuscript search."""
    from middleware.rate_limit import limiter
    from routers import plot_assistant as pa

    monkeypatch.setattr(limiter, "enabled", False)

    async def boom(*_a, **_k):
        raise AssertionError("retrieval ran for a chapter-scoped request with no chapter")

    for name in ("retrieve_relevant_chunks", "retrieve_chunks_from_store", "retrieve_character_context",
                 "retrieve_note_context", "detect_query_intent"):
        monkeypatch.setattr(pa, name, boom)

    with two_authors() as (db, a, _b, client):
        body = {"story_id": a.sid, "question": "What happens to Vell?", "scope": "chapter"}
        if chapter is not None:
            body["current_chapter_number"] = chapter
        r = client.post("/api/plot-assistant/", headers=a.headers, json=body)
        assert r.status_code == 422, r.text[:200]
        assert r.json()["detail"] == "Open a chapter or choose Full manuscript."

        # The default scope is chapter, so omitting scope is refused too.
        body.pop("scope")
        assert client.post("/api/plot-assistant/", headers=a.headers, json=body).status_code == 422


def test_full_scope_without_a_chapter_still_works(stub_embedding, monkeypatch):
    from middleware.rate_limit import limiter
    from routers import plot_assistant as pa

    monkeypatch.setattr(limiter, "enabled", False)

    async def fake_intent(_q):
        return "creative"

    async def no_chunks(*_a, **_k):
        return []

    async def fake_suggestions(**_kw):
        return [{"id": 1, "text": "An idea.", "rationale": "Because."}]

    monkeypatch.setattr(pa, "detect_query_intent", fake_intent)
    for name in ("retrieve_relevant_chunks", "retrieve_chunks_from_store", "retrieve_character_context",
                 "retrieve_note_context"):
        monkeypatch.setattr(pa, name, no_chunks)
    monkeypatch.setattr(pa, "generate_plot_suggestions", fake_suggestions)
    with two_authors() as (db, a, _b, client):
        r = client.post("/api/plot-assistant/", headers=a.headers,
                        json={"story_id": a.sid, "question": "Ideas?", "scope": "full"})
        assert r.status_code == 200 and r.json()["scope_used"] == "full"
