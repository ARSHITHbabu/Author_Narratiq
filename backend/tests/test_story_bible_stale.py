"""
Stage 11 — Story Bible stale detection (Phase 2 roadmap §19 P2-06, found
missing by the Phase 2 acceptance, task 11.6). The bible records the
fingerprint of the indexed chapters it was generated from; GET reports
is_stale when the chapters have changed since. No model: the section generator
is stubbed.

    DATABASE_URL=...narratiq_test pytest backend/tests/test_story_bible_stale.py -q
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import Chapter, ChapterSummary, Story, StoryBible, User  # noqa: E402
from routers import story_bible as sb  # noqa: E402
from routers.auth import create_token, hash_password  # noqa: E402
from services.account_deletion import delete_account  # noqa: E402
from services.source_fingerprint import chapter_source_fingerprint  # noqa: E402

SECTION_TEXT = "Devika — keeper of the lighthouse (Chapter 1)."


@pytest.fixture()
def author():
    db = SessionLocal()
    tag = uuid.uuid4().hex[:8]
    u = User(email=f"s11-bible-{tag}@narratiq-internal-test.com", username=f"s11b{tag}",
             hashed_password=hash_password("x"))
    db.add(u); db.flush()
    s = Story(user_id=u.user_id, title="Bible staleness")
    db.add(s); db.flush()
    chapters = []
    for n in (1, 2, 3):
        ch = Chapter(story_id=s.story_id, title=f"Chapter {n}", chapter_number=n,
                     content=f"<p>Devika climbed the stairs in chapter {n}.</p>")
        db.add(ch); db.flush()
        db.add(ChapterSummary(chapter_id=ch.chapter_id, story_id=s.story_id, chapter_number=n,
                              raw_summary=f"Chapter {n} summary.", key_events=[], characters_present=["Devika"]))
        chapters.append(ch)
    db.commit()
    yield {"db": db, "user": u, "story": s, "chapters": chapters,
           "headers": {"Authorization": f"Bearer {create_token(u.user_id)}"}}
    db.rollback()
    delete_account(db, u.user_id)
    db.close()


def _bible(db, story, *, fingerprint, status="completed"):
    b = StoryBible(story_id=story.story_id, user_id=story.user_id, content_json='{"characters": "x"}',
                   status=status, source_fingerprint=fingerprint)
    db.add(b); db.commit()
    return b


def _get(a):
    r = TestClient(main.app).get(f"/api/stories/{a['story'].story_id}/story-bible", headers=a["headers"])
    assert r.status_code == 200, r.text
    return r.json()


def test_fresh_bible_is_not_stale(author):
    db, s = author["db"], author["story"]
    _bible(db, s, fingerprint=chapter_source_fingerprint(s.story_id, db))
    assert _get(author)["is_stale"] is False


def test_editing_a_chapter_makes_the_bible_stale(author):
    db, s = author["db"], author["story"]
    _bible(db, s, fingerprint=chapter_source_fingerprint(s.story_id, db))
    ch = author["chapters"][1]
    ch.content = "<p>Devika turned back at the door.</p>"
    ch.updated_at = datetime.utcnow() + timedelta(seconds=1)   # explicit: onupdate granularity
    db.commit()
    assert _get(author)["is_stale"] is True


def test_re_indexing_a_chapter_makes_the_bible_stale(author):
    db, s = author["db"], author["story"]
    _bible(db, s, fingerprint=chapter_source_fingerprint(s.story_id, db))
    summ = db.query(ChapterSummary).filter(ChapterSummary.chapter_id == author["chapters"][0].chapter_id).one()
    summ.generated_at = datetime.utcnow() + timedelta(seconds=1)
    db.commit()
    assert _get(author)["is_stale"] is True


def test_deleting_the_last_chapter_makes_the_bible_stale(author):
    """The case a timestamp comparison would miss: deleting the LAST chapter
    renumbers nothing, so no remaining row's updated_at changes."""
    db, s = author["db"], author["story"]
    _bible(db, s, fingerprint=chapter_source_fingerprint(s.story_id, db))
    last = author["chapters"][-1]
    r = TestClient(main.app).delete(f"/api/stories/{s.story_id}/chapters/{last.chapter_id}",
                                    headers=author["headers"])
    assert r.status_code == 200, r.text
    assert _get(author)["is_stale"] is True


def test_bible_without_a_fingerprint_reports_unknown_not_stale(author):
    db, s = author["db"], author["story"]
    _bible(db, s, fingerprint=None)                     # generated before migration 0025
    assert _get(author)["is_stale"] is None


def test_running_bible_reports_unknown(author):
    db, s = author["db"], author["story"]
    _bible(db, s, fingerprint="0" * 64, status="running")
    assert _get(author)["is_stale"] is None


@pytest.mark.asyncio
async def test_generation_records_the_fingerprint_it_read(author, monkeypatch):
    db, s = author["db"], author["story"]

    async def fake_section(section: str, context: str):
        return SECTION_TEXT, "stop"

    monkeypatch.setattr(sb, "generate_story_bible_section", fake_section)
    b = _bible(db, s, fingerprint=None, status="running")
    await sb._generate_bible_pipeline(s.story_id, b.bible_id, bump_version=False)
    db.expire_all()
    stored = db.query(StoryBible).filter(StoryBible.bible_id == b.bible_id).one()
    assert stored.source_fingerprint == chapter_source_fingerprint(s.story_id, db)
    assert _get(author)["is_stale"] is False


@pytest.mark.asyncio
async def test_an_edit_during_generation_leaves_the_result_stale(author, monkeypatch):
    """The fingerprint is taken BEFORE the bible reads the manuscript, so a
    chapter edited while the bible is being written is not silently included
    as if it had been read."""
    db, s = author["db"], author["story"]
    edited = {"done": False}

    async def edit_midway(section: str, context: str):
        if not edited["done"]:
            other = SessionLocal()
            ch = other.query(Chapter).filter(Chapter.chapter_id == author["chapters"][0].chapter_id).one()
            ch.content = "<p>Rewritten while the bible was generating.</p>"
            ch.updated_at = datetime.utcnow() + timedelta(seconds=1)
            other.commit(); other.close()
            edited["done"] = True
        return SECTION_TEXT, "stop"

    monkeypatch.setattr(sb, "generate_story_bible_section", edit_midway)
    b = _bible(db, s, fingerprint=None, status="running")
    await sb._generate_bible_pipeline(s.story_id, b.bible_id, bump_version=False)
    assert _get(author)["is_stale"] is True


@pytest.mark.asyncio
async def test_regenerating_one_section_does_not_clear_staleness(author, monkeypatch):
    db, s = author["db"], author["story"]

    async def fake_section(section: str, context: str):
        return SECTION_TEXT, "stop"

    monkeypatch.setattr(sb, "generate_story_bible_section", fake_section)
    old = chapter_source_fingerprint(s.story_id, db)
    b = _bible(db, s, fingerprint=old)
    ch = author["chapters"][2]
    ch.content = "<p>Changed.</p>"; ch.updated_at = datetime.utcnow() + timedelta(seconds=1)
    db.commit()
    await sb._regenerate_section_pipeline(s.story_id, b.bible_id, "themes")
    db.expire_all()
    assert db.query(StoryBible).filter(StoryBible.bible_id == b.bible_id).one().source_fingerprint == old
    assert _get(author)["is_stale"] is True


@pytest.mark.asyncio
async def test_a_fingerprint_error_never_fails_generation(author, monkeypatch):
    db, s = author["db"], author["story"]

    async def fake_section(section: str, context: str):
        return SECTION_TEXT, "stop"

    def broken(story_id, db):
        raise RuntimeError("database hiccup")

    monkeypatch.setattr(sb, "generate_story_bible_section", fake_section)
    monkeypatch.setattr(sb, "chapter_source_fingerprint", broken)
    b = _bible(db, s, fingerprint=None, status="running")
    await sb._generate_bible_pipeline(s.story_id, b.bible_id, bump_version=False)
    db.expire_all()
    stored = db.query(StoryBible).filter(StoryBible.bible_id == b.bible_id).one()
    assert stored.status == "completed"
    assert stored.source_fingerprint is None
    monkeypatch.undo()
    assert _get(author)["is_stale"] is None          # unknown, so no warning
