"""
Stage 9 task 9.2 — targeted tests for Phase 1 release-blocking issues that had
no direct automated evidence when the QA reports were reconciled.

  PA-H10 (High)  "Major revelations omitted from summaries" — task 4.5's
                 verification box cites test_chapter_arc_fields.py, which by
                 its own header does not assert content. This asserts the
                 revelation itself reaches the stored summary (live model).
  SUG-H9 (High)  "Missing story-specific analysis" — task 5.13 wired retrieved
                 manuscript passages and the genre into suggestions; nothing
                 asserted that wiring. This does, with the model stubbed.

    DATABASE_URL=...narratiq_test pytest backend/tests/test_stage9_targeted_issues.py -q
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402


@pytest.mark.skipif(os.environ.get("SKIP_LLM_TESTS") == "1", reason="SKIP_LLM_TESTS=1 — live Qwen call")
@pytest.mark.parametrize("attempt", [1, 2, 3])
def test_PA_H10_revelation_reaches_the_stored_summary(attempt):
    """Chapter 5 of the retrieval fixture reveals that Magistrate Vell, believed
    dead for eleven years, is alive and faked his death. A summary that omits
    that has lost the chapter's central revelation."""
    from database import SessionLocal
    from models import ChapterSummary
    from services.ai_service import summarize_and_embed_chapter
    from tests.fixtures.retrieval_fixture import CHAPTERS, build_fixture, cleanup_fixture

    db = SessionLocal()

    async def run():
        info = await build_fixture(db)
        ch5 = next(c for c in CHAPTERS if c["number"] == 5)
        await summarize_and_embed_chapter(info["chapter_ids"][5], info["story_id"], 5, ch5["content"], db)
        return info

    info = asyncio.run(run())
    try:
        cs = db.query(ChapterSummary).filter(ChapterSummary.chapter_id == info["chapter_ids"][5]).one()
        stored = " ".join([
            cs.raw_summary or "", cs.chapter_purpose or "",
            json.dumps(cs.key_events or []), json.dumps(cs.character_arc_notes or {}),
        ]).lower()
        print(f"\n[PA-H10 attempt {attempt}] {stored[:400]}")
        assert "vell" in stored, "the revealed character is not named in the summary"
        assert any(w in stored for w in ("alive", "faked", "survived", "not dead", "living", "hiding")), \
            "the summary does not record that Vell is alive / faked his death"
    finally:
        cleanup_fixture(db, info["story_id"], info["user_id"])
        db.close()


def test_SUG_H9_suggestions_receive_story_passages_and_genre(monkeypatch):
    from _phase3_helpers import two_authors
    from middleware.rate_limit import limiter
    from models import GenreProfile
    from services import ai_service

    monkeypatch.setattr(limiter, "enabled", False)
    seen = {}

    async def fake_retrieve(query, story_id, db, top_k=3):
        seen["retrieved_for"] = story_id
        return [{"text": "Kira kept the brass key hidden in the lighthouse."}]

    async def fake_generate(text, story_context="", genre=""):
        seen["story_context"] = story_context
        seen["genre"] = genre
        return [{"id": 1, "category": "plot", "text": "Use the key.", "reason": "It was set up.",
                 "priority": "high"}]

    monkeypatch.setattr(ai_service, "retrieve_chunks_from_store", fake_retrieve)
    monkeypatch.setattr(ai_service, "generate_suggestions", fake_generate)
    with two_authors() as (db, a, _b, client):
        db.add(GenreProfile(story_id=a.sid, genre="mystery"))
        db.commit()
        r = client.post("/api/ai/suggestions", headers=a.headers,
                        json={"text": "Elara walked down the corridor.", "story_id": a.sid,
                              "chapter_id": a.chapters[0].chapter_id})
        db.query(GenreProfile).filter(GenreProfile.story_id == a.sid).delete()
        db.commit()
    assert r.status_code == 200, r.text[:300]
    assert seen.get("retrieved_for") == a.sid
    assert "brass key" in seen.get("story_context", "")
    assert seen.get("genre") == "mystery"


def test_PA_C4_CAST_C3_alias_in_question_retrieves_that_character():
    """PA-C4 / CAST-C3 — "alias resolution failure". The existing tests cover the
    alias regex only; this goes through retrieve_character_context itself: a
    question that uses ONLY an alias must put that character's block first."""
    import uuid
    from database import SessionLocal
    from models import Character, Story, User
    from services.ai_service import retrieve_character_context

    db = SessionLocal()
    tag = uuid.uuid4().hex[:8]
    user = User(email=f"s9-alias-{tag}@narratiq-internal-test.com", username=f"s9alias{tag}", hashed_password="x")
    db.add(user); db.flush()
    story = Story(user_id=user.user_id, title="alias probe"); db.add(story); db.flush()
    cast = [("Ondrej Vell", ["the Magistrate", "Vell"]), ("Mira Okoye", ["Mira"]), ("Hessa Lin", ["Hessa"]),
            ("Tomas Reyne", []), ("Elsbet Crane", []), ("Dorran Vey", []), ("Pell Ashgrove", [])]
    for name, aliases in cast:
        db.add(Character(story_id=story.story_id, user_id=user.user_id, name=name, aliases=aliases, role="supporting"))
    db.commit()
    try:
        blocks = asyncio.run(retrieve_character_context(story.story_id, "What does the Magistrate want from her?", db))
        assert blocks, "no character context returned for an alias-only question"
        assert "Ondrej Vell" in blocks[0], blocks[0][:200]
    finally:
        db.rollback()
        db.query(Character).filter(Character.story_id == story.story_id).delete(synchronize_session=False)
        db.delete(db.get(Story, story.story_id)); db.delete(db.get(User, user.user_id)); db.commit(); db.close()


_ABSENT = ("not mentioned", "isn't mentioned", "is not mentioned", "not in the story", "not established",
           "no information", "does not appear", "doesn't appear", "not specified", "never mentioned")


@pytest.mark.skipif(os.environ.get("SKIP_LLM_TESTS") == "1", reason="SKIP_LLM_TESTS=1 — live Qwen call")
@pytest.mark.parametrize("attempt", [1, 2, 3])
def test_PA_C7_fact_in_the_story_is_not_reported_missing(attempt, monkeypatch):
    """PA-C7 — "existing information reported as missing". Chapter 5 states who
    emerged in the Cistern (Vell, alive). Asked from chapter 5 with full scope,
    the answer must not claim the manuscript does not say."""
    from fastapi.testclient import TestClient
    import main
    from database import SessionLocal
    from middleware.rate_limit import limiter
    from routers.auth import create_token
    from tests.fixtures.retrieval_fixture import build_fixture, cleanup_fixture

    monkeypatch.setattr(limiter, "enabled", False)
    db = SessionLocal()
    info = asyncio.run(build_fixture(db))
    try:
        client = TestClient(main.app)
        r = client.post("/api/plot-assistant/", headers={"Authorization": f"Bearer {create_token(info['user_id'])}"},
                        json={"story_id": info["story_id"], "question": "Who emerged from behind the Cistern's far wall?",
                              "current_chapter_number": 5, "scope": "full"})
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        text = " ".join([body.get("answer") or ""] + [s["text"] for s in body.get("suggestions", [])]).lower()
        print(f"\n[PA-C7 attempt {attempt}] {text[:300]}")
        assert not any(p in text for p in _ABSENT), "answer claims an in-story fact is missing"
        assert "vell" in text, "answer does not name the character the manuscript names"
    finally:
        cleanup_fixture(db, info["story_id"], info["user_id"])
        db.close()
