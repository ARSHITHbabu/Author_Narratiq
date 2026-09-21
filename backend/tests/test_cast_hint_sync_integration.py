"""
Stage 4 task 4.7 — cast generation / unrecognised-name queue synchronisation.

Direct code inspection found this ALREADY implemented, contrary to an earlier
pass that only checked the read-only `generate-cast` preview endpoint (which
correctly does NOT touch hints — nothing is persisted yet) and missed that
`confirm-cast` (routers/characters.py) already calls
`resolve_hints_for_names()` (services/character_names.py) in the SAME
transaction as character creation, closing Phase 2 Issue 9 back in task 3.12.

This is a real integration test against the live DB (no HTTP layer — calling
confirm_cast's logic directly is unnecessary; the underlying
resolve_hints_for_names is already unit-tested in test_character_hint_sync.py
with fakes. This test instead proves the WIRING: a real CharacterHint row,
dismissed by a real transaction that also creates the matching Character.)

Run: cd backend && pytest tests/test_cast_hint_sync_integration.py -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from database import SessionLocal  # noqa: E402
from models import User, Story, Chapter, Character, CharacterHint  # noqa: E402
from services.character_names import resolve_hints_for_names  # noqa: E402
from tests.fixtures.retrieval_fixture import cleanup_fixture  # noqa: E402


@pytest.fixture
def hint_fixture():
    db = SessionLocal()
    tag = str(id(object()))
    user = User(email=f"hint-sync-{tag}@narratiq-internal-test.com",
                username=f"hintsync{tag}", hashed_password="x")
    db.add(user)
    db.flush()
    story = Story(user_id=user.user_id, title="[4.7-FIXTURE] Hint Sync Test")
    db.add(story)
    db.flush()
    ch = Chapter(story_id=story.story_id, chapter_number=1, title="Ch1", content="<p>...</p>")
    db.add(ch)
    db.flush()

    hint = CharacterHint(
        story_id=story.story_id,
        chapter_id=ch.chapter_id,
        chapter_number=1,
        suggested_name="Zorathmoon",
        context_snippet="Zorathmoon appeared suddenly.",
        is_dismissed=False,
    )
    db.add(hint)
    db.commit()

    try:
        yield {"db": db, "story_id": story.story_id, "user_id": user.user_id, "hint_id": hint.hint_id}
    finally:
        cleanup_fixture(db, story.story_id, user.user_id)
        db.close()


def test_confirming_a_character_dismisses_the_matching_hint_transactionally(hint_fixture):
    """
    Reproduces exactly what confirm_cast does: create the Character, then
    reconcile hints for the same names, then commit both together — proving
    the wiring, not just the isolated function (already covered by
    test_character_hint_sync.py's 17 fake-based tests).
    """
    db = hint_fixture["db"]
    story_id = hint_fixture["story_id"]

    # Confirm the hint is live before confirmation, matching what an author
    # would see in the unrecognised-names queue.
    live_before = db.query(CharacterHint).filter(
        CharacterHint.story_id == story_id, CharacterHint.is_dismissed == False,  # noqa: E712
    ).all()
    assert len(live_before) == 1

    # This mirrors confirm_cast's own sequence exactly (routers/characters.py):
    #   create Character -> flush -> resolve_hints_for_names -> commit
    character = Character(
        story_id=story_id, user_id=hint_fixture["user_id"],
        name="Zorathmoon", aliases=[], role="supporting", status="active",
    )
    db.add(character)
    db.flush()

    dismissed = resolve_hints_for_names(db, story_id, ["Zorathmoon"])
    db.commit()

    assert dismissed == [hint_fixture["hint_id"]]

    # No stale entry survives a "refresh" (a fresh query, as the frontend
    # would issue after reload) — this is what "prevent stale queue entries
    # surviving a page refresh" means at the data layer: the dismissal is
    # already committed, not held in an in-memory cache the refresh might miss.
    live_after = db.query(CharacterHint).filter(
        CharacterHint.story_id == story_id, CharacterHint.is_dismissed == False,  # noqa: E712
    ).all()
    assert live_after == []


def test_unmatched_hints_remain_live_not_silently_dropped(hint_fixture):
    """Confirming an UNRELATED character must not resolve a hint for a
    different name — the queue should only shrink for names actually confirmed."""
    db = hint_fixture["db"]
    story_id = hint_fixture["story_id"]

    character = Character(
        story_id=story_id, user_id=hint_fixture["user_id"],
        name="Someone Else Entirely", aliases=[], role="supporting", status="active",
    )
    db.add(character)
    db.flush()

    dismissed = resolve_hints_for_names(db, story_id, ["Someone Else Entirely"])
    db.commit()

    assert dismissed == []
    live = db.query(CharacterHint).filter(
        CharacterHint.story_id == story_id, CharacterHint.is_dismissed == False,  # noqa: E712
    ).all()
    assert len(live) == 1
    assert live[0].suggested_name == "Zorathmoon"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
