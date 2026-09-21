"""
Stage 4 task 4.3 — context prioritisation and ranking (plot-importance weighting).

_plot_importance_by_chapter is a pure-ish function (one DB read, no LLM, no
embeddings) — tested directly against real ChapterSummary rows so the boost
math is pinned with real data shapes, not fakes standing in for the ORM.

Run: cd backend && pytest tests/test_plot_importance_ranking.py -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from database import SessionLocal  # noqa: E402
from models import User, Story, Chapter, ChapterSummary  # noqa: E402
from services.ai_service import _plot_importance_by_chapter, _PLOT_IMPORTANCE_CAP  # noqa: E402


@pytest.fixture
def importance_fixture():
    db = SessionLocal()
    user = User(email=f"importance-test-{id(object())}@narratiq-internal-test.com",
                username=f"importancetest{id(object())}", hashed_password="x")
    db.add(user)
    db.flush()
    story = Story(user_id=user.user_id, title="[4.3-IMPORTANCE-FIXTURE] Test Story")
    db.add(story)
    db.flush()

    # Chapter 1: quiet — no events, no arc, no relationship movement.
    ch1 = Chapter(story_id=story.story_id, chapter_number=1, title="Quiet", content="<p>...</p>")
    # Chapter 2: plot-critical — many events, arc movement, relationship movement.
    ch2 = Chapter(story_id=story.story_id, chapter_number=2, title="Critical", content="<p>...</p>")
    # Chapter 3: never summarised at all (no ChapterSummary row).
    ch3 = Chapter(story_id=story.story_id, chapter_number=3, title="Unsummarised", content="<p>...</p>")
    db.add_all([ch1, ch2, ch3])
    db.flush()

    db.add(ChapterSummary(
        chapter_id=ch1.chapter_id, story_id=story.story_id, chapter_number=1,
        key_events=[], character_arc_notes={}, relationship_changes=[],
        raw_summary="Nothing much happens.",
    ))
    db.add(ChapterSummary(
        chapter_id=ch2.chapter_id, story_id=story.story_id, chapter_number=2,
        key_events=["a", "b", "c", "d", "e"],
        character_arc_notes={"Kael": "Decides to betray the guild."},
        relationship_changes=[{"characters": ["Kael", "Mira"], "change": "Trust broken."}],
        raw_summary="Everything happens.",
    ))
    db.commit()

    try:
        yield {"db": db, "story_id": story.story_id, "user_id": user.user_id}
    finally:
        from tests.fixtures.retrieval_fixture import cleanup_fixture
        cleanup_fixture(db, story.story_id, user.user_id)
        db.close()


def test_quiet_chapter_gets_zero_boost(importance_fixture):
    boosts = _plot_importance_by_chapter(
        importance_fixture["story_id"], {1, 2, 3}, importance_fixture["db"],
    )
    assert boosts.get(1, 0.0) == 0.0


def test_plot_critical_chapter_gets_higher_boost_than_quiet_chapter(importance_fixture):
    boosts = _plot_importance_by_chapter(
        importance_fixture["story_id"], {1, 2, 3}, importance_fixture["db"],
    )
    assert boosts.get(2, 0.0) > boosts.get(1, 0.0)


def test_boost_is_bounded_by_the_cap(importance_fixture):
    boosts = _plot_importance_by_chapter(
        importance_fixture["story_id"], {1, 2, 3}, importance_fixture["db"],
    )
    assert boosts.get(2, 0.0) <= _PLOT_IMPORTANCE_CAP


def test_unsummarised_chapter_defaults_to_no_boost_not_a_crash(importance_fixture):
    boosts = _plot_importance_by_chapter(
        importance_fixture["story_id"], {1, 2, 3}, importance_fixture["db"],
    )
    assert boosts.get(3, 0.0) == 0.0


def test_empty_chapter_set_returns_empty_without_querying(importance_fixture):
    boosts = _plot_importance_by_chapter(importance_fixture["story_id"], set(), importance_fixture["db"])
    assert boosts == {}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
