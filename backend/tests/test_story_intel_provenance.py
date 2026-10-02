"""
Stage 12 Tranche 2a — chapter provenance for Story Intelligence memory.

Meaning (owner decision 2026-10-02): an entry tagged chapter N was derived only
from material in chapters 1..N — no later chapter contributed. It does NOT mean
every chapter up to N was analysed, nor that the fact came from chapter N.

These tests run the real P25 consolidation against the database (embedding
stubbed) and read back through build_integration_context, the function the
Plot Assistant uses:
  * an entry with bound N is hidden below N and available at and above N;
  * material from a later analysis run cannot reach an earlier chapter scope;
  * author-added entries (no trustworthy provenance) stay hidden under any cap;
  * deleting a chapter can only make the stored bound too high (hides more).

    DATABASE_URL=...narratiq_test pytest backend/tests/test_story_intel_provenance.py -q
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402

from _phase3_helpers import two_authors  # noqa: E402
from models import Chapter, StoryDNA, StoryMemoryEntry, StoryRiskRegister  # noqa: E402

DIM = 1024
VEC = [1.0] + [0.0] * (DIM - 1)
EARLY = "A harbour pilot searches for her missing brother"
SECRET = "The magistrate faked his own death and returns in the final chapter"


@pytest.fixture(autouse=True)
def stub_embeddings(monkeypatch):
    from services import story_intel_service as sis

    async def fake(_t):
        return VEC

    monkeypatch.setattr(sis, "embed_text_sync", lambda _t: VEC)
    monkeypatch.setattr(sis, "embed_text", fake)


def _consolidate(db, story):
    from services.story_intel_service import run_p25_memory_consolidation
    n = asyncio.run(run_p25_memory_consolidation(db, story))
    db.commit()
    return n


def _ctx(db, sid, cap):
    from services.story_intel_service import build_integration_context
    return asyncio.run(build_integration_context(db, sid, query="what happens", top_k=20, max_chapter_number=cap))


def _hits(db, sid, cap):
    return [h["content"] for h in _ctx(db, sid, cap).get("memory_hits", [])]


def _drop(db, sid):
    db.rollback()
    for model in (StoryMemoryEntry, StoryDNA, StoryRiskRegister):
        db.query(model).filter(model.story_id == sid).delete(synchronize_session=False)
    db.commit()


def test_p25_tags_every_entry_with_the_current_highest_chapter():
    with two_authors() as (db, a, _b, _c):         # 3 chapters
        try:
            db.add(StoryDNA(story_id=a.sid, premise=EARLY, central_question="Will she find him?"))
            db.add(StoryRiskRegister(story_id=a.sid, plot_holes=["The ferry schedule never changes"]))
            db.commit()
            assert _consolidate(db, a.story) >= 3
            rows = db.query(StoryMemoryEntry).filter(StoryMemoryEntry.story_id == a.sid).all()
            assert rows and all(r.chapter_last_updated == 3 for r in rows)
            assert all(r.chapter_first_established == 3 for r in rows)
        finally:
            _drop(db, a.sid)


def test_bound_n_is_hidden_below_and_available_at_and_above():
    with two_authors() as (db, a, _b, _c):
        try:
            db.add(StoryDNA(story_id=a.sid, premise=EARLY))
            db.commit()
            _consolidate(db, a.story)
            assert EARLY not in _hits(db, a.sid, 2)
            assert EARLY in _hits(db, a.sid, 3)
            assert EARLY in _hits(db, a.sid, 5)
            assert EARLY in _hits(db, a.sid, None)       # full scope
        finally:
            _drop(db, a.sid)


def test_a_later_analysis_run_cannot_reach_an_earlier_chapter_scope():
    with two_authors() as (db, a, _b, _c):
        try:
            db.add(StoryDNA(story_id=a.sid, premise=EARLY))
            db.commit()
            _consolidate(db, a.story)                    # run 1: chapters 1-3
            assert EARLY in _hits(db, a.sid, 3)

            # The author writes chapter 4, which reveals the secret; a new
            # analysis folds it into the same memory keys.
            db.add(Chapter(story_id=a.sid, chapter_number=4, title="Four", content="<p>He was alive.</p>"))
            dna = db.query(StoryDNA).filter(StoryDNA.story_id == a.sid).one()
            dna.premise = SECRET
            db.commit()
            db.refresh(a.story)
            _consolidate(db, a.story)                    # run 2: chapters 1-4

            for cap in (1, 2, 3):
                assert not any(SECRET in h for h in _hits(db, a.sid, cap)), cap
                assert SECRET not in repr(_ctx(db, a.sid, cap))
            assert SECRET in _hits(db, a.sid, 4)
        finally:
            _drop(db, a.sid)


def test_author_added_entries_stay_hidden_under_any_chapter_cap():
    with two_authors() as (db, a, _b, _c):
        try:
            db.add(StoryMemoryEntry(story_id=a.sid, memory_type="plot", memory_key="author.note.1",
                                    content="Author's own note about the ending", embedding=VEC,
                                    is_ai_generated=False, is_author_added=True))
            db.add(StoryDNA(story_id=a.sid, premise=EARLY))
            db.commit()
            _consolidate(db, a.story)
            note = db.query(StoryMemoryEntry).filter(StoryMemoryEntry.memory_key == "author.note.1").one()
            assert note.chapter_last_updated is None
            for cap in (1, 3, 99):
                assert "Author's own note about the ending" not in _hits(db, a.sid, cap)
            assert "Author's own note about the ending" in _hits(db, a.sid, None)
        finally:
            _drop(db, a.sid)


def test_deleting_a_chapter_only_makes_the_bound_too_high():
    with two_authors() as (db, a, _b, client):
        try:
            db.add(StoryDNA(story_id=a.sid, premise=EARLY))
            db.commit()
            _consolidate(db, a.story)                    # bound 3
            first = a.chapters[0].chapter_id
            assert client.delete(f"/api/stories/{a.sid}/chapters/{first}", headers=a.headers).status_code in (200, 204)
            db.expire_all()
            assert max(c.chapter_number for c in db.query(Chapter).filter(Chapter.story_id == a.sid)) == 2
            # Stored bound stays 3 (>= the truth): the entry is hidden at chapter 2.
            assert EARLY not in _hits(db, a.sid, 2)
        finally:
            _drop(db, a.sid)


def test_a_story_with_no_chapters_gets_no_tag():
    from services.story_intel_service import _tag_memory_upper_bound
    with two_authors() as (db, a, _b, _c):
        try:
            for ch in db.query(Chapter).filter(Chapter.story_id == a.sid).all():
                db.delete(ch)
            db.add(StoryMemoryEntry(story_id=a.sid, memory_type="plot", memory_key="k", content="c", embedding=VEC))
            db.commit()
            assert _tag_memory_upper_bound(db, a.sid, ["k"]) is None
            db.commit()
            assert db.query(StoryMemoryEntry).filter(StoryMemoryEntry.memory_key == "k").one().chapter_last_updated is None
        finally:
            _drop(db, a.sid)
