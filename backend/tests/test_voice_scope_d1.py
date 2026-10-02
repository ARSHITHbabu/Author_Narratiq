"""
Stage 12 — D-1 for voice Q&A (correction after Tranche 2a).

Voice story / character / relationship questions follow the Plot Assistant's
spoiler boundary: the open chapter caps every retrieval (passages, character
evidence, Story Intelligence); the whole manuscript only on an explicit
request; no chapter open and no explicit request → an honest refusal, never a
silent unlimited search. Retrieval is stubbed: these tests check what the
adapters ASK for. The live planted-secret check is tests/live_voice_spoiler_d1.py.

    DATABASE_URL=...narratiq_test pytest backend/tests/test_voice_scope_d1.py -q
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from services.voice import adapters  # noqa: E402
from services.voice.context import ContextBundle  # noqa: E402

WHOLE = ["What happens to Vell in the whole book?",
         "Across the whole manuscript, who betrays Mira?",
         "Throughout the entire novel, how does Hessa change?",
         "Summarise the whole book", "Search all chapters for the key",
         "Does Corvin appear in every chapter?", "in the entire book, who dies?"]
NOT_WHOLE = ["What is this story about?", "What happens to Vell?", "Tell me everything about Mira.",
             "What's the whole point of the key?", "Who is the main character overall?",
             "Is the story getting better?", "What has happened so far?", "Summarise the book so far",
             "What's the full story behind the key?", "Tell me the whole story of the flood."]


@pytest.mark.parametrize("q", WHOLE)
def test_explicit_whole_book_requests_are_recognised(q):
    assert adapters.wants_whole_book(q)


@pytest.mark.parametrize("q", NOT_WHOLE)
def test_broad_questions_are_not_whole_book(q):
    assert not adapters.wants_whole_book(q)


@pytest.fixture
def spy(monkeypatch):
    from services import ai_service, story_intel_service
    calls: dict[str, list] = {"chunks": [], "chars": [], "intel": [], "answer": []}

    async def chunks(q, sid, db, top_k=8, max_chapter_number=None, diversify_chapters=False):
        calls["chunks"].append(max_chapter_number)
        return [{"text": "x", "chapter_number": 1, "score": 0.5}]

    async def chars(sid, q, db, max_chapter_number=None, **k):
        calls["chars"].append(max_chapter_number)
        return ["Mira: a traveller"]

    async def notes(sid, q, db, *a, **k):
        return []

    async def intel(db, sid, query=None, top_k=12, max_chapter_number=None):
        calls["intel"].append(max_chapter_number)
        return {"memory": []}

    async def answer(q, chunks, **k):
        calls["answer"].append(k)
        return "ok"

    monkeypatch.setattr(ai_service, "retrieve_chunks_from_store", chunks)
    monkeypatch.setattr(ai_service, "retrieve_character_context", chars)
    monkeypatch.setattr(ai_service, "retrieve_note_context", notes)
    monkeypatch.setattr(ai_service, "answer_story_question", answer)
    monkeypatch.setattr(story_intel_service, "build_integration_context", intel)
    monkeypatch.setattr(adapters, "_genre_dict", lambda sid, db: None)
    return calls


class _NoDB:
    """Stands in for the session: the relationship query returns nothing."""
    def query(self, *a):
        return self
    def filter(self, *a):
        return self
    def all(self):
        return []
    def first(self):
        return None


def _run(fn, q, chapter_number):
    b = ContextBundle(story_id="s1", chapter_id=None, chapter_number=chapter_number, chapter_text="Chapter text.")
    return asyncio.run(fn(q, b, _NoDB(), None))


ADAPTERS = [adapters._adapt_story_qa, adapters._adapt_character_qa, adapters._adapt_character_relationship]


@pytest.mark.parametrize("fn", ADAPTERS)
def test_open_chapter_caps_every_retrieval(spy, fn):
    out = _run(fn, "What happened to Vell?", 3)
    assert out["answer"] == "ok"
    for kind in ("chunks", "chars", "intel"):
        assert all(c == 3 for c in spy[kind]), (kind, spy[kind])
    assert spy["chunks"] or spy["chars"]
    assert all(a.get("scope_limited") is True for a in spy["answer"])
    assert "chapters 1–3" in out["context_used"]


def test_story_qa_uses_capped_story_intelligence(spy):
    _run(adapters._adapt_story_qa, "What happened to Vell?", 2)
    assert spy["intel"] == [2] and spy["answer"][0]["intel_context"] == {"memory": []}


@pytest.mark.parametrize("fn", ADAPTERS)
def test_explicit_whole_book_lifts_the_cap(spy, fn):
    out = _run(fn, "In the whole book, what happens to Vell?", 3)
    for kind in ("chunks", "chars", "intel"):
        assert all(c is None for c in spy[kind])
    assert all(a.get("scope_limited") is False for a in spy["answer"])
    assert "whole manuscript" in out["context_used"]


@pytest.mark.parametrize("fn", ADAPTERS)
def test_no_open_chapter_is_refused_not_searched(spy, fn):
    out = _run(fn, "What happened to Vell?", None)
    assert out["answer"] == adapters.NO_CHAPTER_MESSAGE
    assert spy["chunks"] == spy["chars"] == spy["intel"] == spy["answer"] == []


def test_no_open_chapter_with_explicit_request_searches_everything(spy):
    out = _run(adapters._adapt_story_qa, "Across the whole manuscript, what happens to Vell?", None)
    assert out["answer"] == "ok" and spy["chunks"] == [None]


def test_chapter_number_is_resolved_from_the_open_chapter_id():
    from _phase3_helpers import two_authors
    from models import Chapter
    with two_authors() as (db, a, b, _client):
        ch = db.query(Chapter).filter(Chapter.story_id == a.sid).order_by(Chapter.chapter_number).first()
        bundle = ContextBundle(story_id=a.sid, chapter_id=ch.chapter_id, chapter_number=None)
        assert adapters.voice_scope("What happened?", bundle, db) == (True, ch.chapter_number)
        # another author's story never resolves the chapter
        foreign = ContextBundle(story_id=b.sid, chapter_id=ch.chapter_id, chapter_number=None)
        assert adapters.voice_scope("What happened?", foreign, db) == (False, None)


def test_relationship_graph_is_used_only_for_whole_book_requests(spy, monkeypatch):
    """The recorded graph has no chapter provenance — hidden under a cap."""
    queried = []

    class _DB(_NoDB):
        def query(self, model):
            queried.append(model.__name__)
            return self

    b = ContextBundle(story_id="s1", chapter_number=3, chapter_text="t")
    asyncio.run(adapters._adapt_character_relationship("How are Mira and Vell related?", b, _DB(), None))
    assert "CharacterRelationship" not in queried
    queried.clear()
    asyncio.run(adapters._adapt_character_relationship(
        "Across the whole manuscript, how are Mira and Vell related?", b, _DB(), None))
    assert "CharacterRelationship" in queried
