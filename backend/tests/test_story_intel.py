"""
Stage 11 — Story Intelligence (P01–P29) end to end, with the model stubbed.

Story Intelligence never worked: every pass called _complete(prompt, ...)
without the required `user` argument, the TypeError was swallowed by the
orchestrator, and per-chapter / character passes were still reported as
completed. These tests pin the repaired behaviour:

  * every model call sends instructions in `system` and the author's material
    in `user` (so the Stage 11 prompt-injection fence protects it);
  * a full run completes every pass and stores real results;
  * unusable model output makes the pass FAIL (not "complete" with empty data);
  * failures are visible: recorded in the Stage 10 error tracker.

    DATABASE_URL=...narratiq_test pytest backend/tests/test_story_intel.py -q
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402

from database import SessionLocal  # noqa: E402
from models import (  # noqa: E402
    Chapter, Character, CharacterRelationship, ErrorEvent, Story, StoryDNA, StoryGenreHierarchy,
    StoryThemes, User,
)
from routers.auth import hash_password  # noqa: E402
from services import story_intel_orchestrator as orch  # noqa: E402
from services import story_intel_service as sis  # noqa: E402
from services.account_deletion import delete_account  # noqa: E402

MARKER = "the lamp room was empty and the logbook torn in half"


@pytest.fixture()
def story():
    db = SessionLocal()
    tag = uuid.uuid4().hex[:8]
    u = User(email=f"s11-intel-{tag}@narratiq-internal-test.com", username=f"s11i{tag}",
             hashed_password=hash_password("x"))
    db.add(u); db.flush()
    s = Story(user_id=u.user_id, title="Intel", description="A lighthouse mystery.")
    db.add(s); db.flush()
    for n in (1, 2, 3):
        db.add(Chapter(story_id=s.story_id, title=f"Chapter {n}", chapter_number=n,
                       content=f"<p>Devika climbed the stairs in chapter {n}; {MARKER}. Mara waited.</p>"))
    a = Character(story_id=s.story_id, user_id=u.user_id, name="Devika", aliases=[])
    b = Character(story_id=s.story_id, user_id=u.user_id, name="Mara", aliases=[])
    db.add_all([a, b]); db.flush()
    db.add(CharacterRelationship(story_id=s.story_id, from_character_id=a.character_id,
                                 to_character_id=b.character_id, relationship_type="ally"))
    db.commit()
    yield db, s
    db.rollback()
    delete_account(db, u.user_id)
    db.close()


def _good_model(calls):
    async def fake(system, user, temperature=0.0, max_tokens=512, response_format=None, task=None):
        calls.append((system, user))
        if "JSON format (array)" in system:
            return json.dumps([{"event_type": "action", "event_description": "Devika climbs",
                                "characters_involved": ["Devika"], "is_flashback": False}])
        return json.dumps({"primary_genre": "Mystery", "primary_genre_confidence": 0.8,
                           "premise": "A keeper finds the lamp room empty.", "primary_theme": "trust",
                           "confidence": 0.7, "emotional_tone": "tense", "pacing": "steady"})
    return fake


@pytest.mark.asyncio
async def test_every_pass_sends_instructions_as_system_and_material_as_user(story, monkeypatch):
    db, s = story
    calls: list = []
    monkeypatch.setattr(sis, "_complete", _good_model(calls))
    result = await orch.run_full_analysis(s.story_id, db)

    assert calls, "no model call was made"
    for system, user in calls:
        assert "JSON" in system                     # the task and format are instructions
        assert MARKER not in system                 # manuscript text never sits in the instructions
    assert any(MARKER in user for _s, user in calls)   # ...it is in the material
    assert result["passes_failed"] == [], result
    assert set(orch.ALL_PASSES) - set(result["passes_completed"]) <= {"P27"} or result["status"] == "complete"


@pytest.mark.asyncio
async def test_a_full_run_stores_real_analyses(story, monkeypatch):
    db, s = story
    monkeypatch.setattr(sis, "_complete", _good_model([]))
    result = await orch.run_full_analysis(s.story_id, db, passes=["P01", "P02", "P04"])
    assert result["status"] == "complete" and sorted(result["passes_completed"]) == ["P01", "P02", "P04"]
    db.expire_all()
    assert db.query(StoryGenreHierarchy).filter_by(story_id=s.story_id).one().primary_genre == "Mystery"
    assert db.query(StoryDNA).filter_by(story_id=s.story_id).one().premise.startswith("A keeper")
    assert db.query(StoryThemes).filter_by(story_id=s.story_id).one().primary_theme == "trust"


@pytest.mark.asyncio
async def test_unusable_output_fails_the_pass_honestly(story, monkeypatch):
    db, s = story

    async def garbage(system, user, **kw):
        return "I'm sorry, I can't produce JSON for that."

    monkeypatch.setattr(sis, "_complete", garbage)
    result = await orch.run_full_analysis(s.story_id, db, passes=["P01", "P08", "P09", "P23", "P24"])
    assert result["status"] == "complete_with_errors"
    # Before Stage 11, P08-P12, P23 and P24 were reported completed even when every item failed.
    assert set(result["passes_failed"]) == {"P01", "P08", "P09", "P23", "P24"}
    assert result["passes_completed"] == []
    db.expire_all()
    assert db.query(StoryGenreHierarchy).filter_by(story_id=s.story_id).first() is None   # nothing empty stored


@pytest.mark.asyncio
async def test_a_programming_error_is_recorded_not_just_logged(story, monkeypatch, caplog):
    db, s = story

    async def broken(*a, **kw):
        raise TypeError("_complete() missing 1 required positional argument: 'user'")

    monkeypatch.setattr(sis, "_complete", broken)
    before = db.query(ErrorEvent).filter(ErrorEvent.route == "story_intel:P01").count()
    with caplog.at_level("ERROR"):
        result = await orch.run_full_analysis(s.story_id, db, passes=["P01"])
    assert result["passes_failed"] == ["P01"]
    assert any("programming error" in r.getMessage() and r.exc_info for r in caplog.records)
    db.expire_all()
    rows = db.query(ErrorEvent).filter(ErrorEvent.route == "story_intel:P01").all()
    assert rows and sum(r.occurrences or 1 for r in rows) > before
    assert any(r.kind == "TypeError" for r in rows)


@pytest.mark.asyncio
async def test_an_empty_pass_list_means_all_passes(story, monkeypatch):
    """The voice action sends passes=[]; it must run the analysis, not nothing."""
    db, s = story
    calls: list = []
    monkeypatch.setattr(sis, "_complete", _good_model(calls))
    result = await orch.run_full_analysis(s.story_id, db, passes=[])
    assert calls, "an empty pass list ran no analysis at all"
    assert "P01" in result["passes_completed"] and result["passes_failed"] == []
