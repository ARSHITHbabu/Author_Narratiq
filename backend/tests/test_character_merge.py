"""
Stage 4 task 4.8 — character deduplication and consolidation.

Real integration tests against the live PostgreSQL DB — the merge touches 8
FK-enforced tables and 3 denormalized JSON-array columns; a fake session
cannot exercise real unique-constraint collisions or FK integrity errors,
which are exactly the failure modes this task exists to handle safely.

Every fixture here is disposable, self-labelled, and cleaned up (or already
gone, since deletion IS the operation under test) with an explicit orphan
scan afterward — never touches real author data.

Run: cd backend && pytest tests/test_character_merge.py -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from sqlalchemy import text as sqltext  # noqa: E402

from database import SessionLocal  # noqa: E402
from models import (  # noqa: E402
    User, Story, Chapter, Character, CharacterProfile, CharacterIntelligence,
    CharacterArcSnapshot, CharacterMention, CharacterRelationship,
    RelationshipIntelligence, ChapterChunk, ChapterSummary,
)
from services.character_merge import merge_characters, MergeError  # noqa: E402


def _orphan_scan(db, story_id: str, user_id: str) -> list:
    rows = db.execute(sqltext("""
        SELECT table_name, column_name FROM information_schema.columns
        WHERE table_schema='public' AND column_name IN ('story_id','user_id')
    """)).fetchall()
    orphans = []
    for table_name, column_name in rows:
        val = story_id if column_name == "story_id" else user_id
        cnt = db.execute(
            sqltext(f'SELECT count(*) FROM "{table_name}" WHERE "{column_name}" = :v'),
            {"v": val},
        ).scalar()
        if cnt:
            orphans.append((table_name, column_name, cnt))
    return orphans


@pytest.fixture
def merge_fixture():
    """
    A rich fixture exercising every table 4.8 enumerated:
      - two characters (Kael = survivor, Kaelin = duplicate — deliberately
        confusable names, the real-world case this task targets)
      - both have profiles (conflicting + complementary fields)
      - both have intelligence rows
      - both have arc snapshots (one shared chapter, one duplicate-only chapter)
      - both have mentions, including co_character_ids referencing each other
      - relationships: one that must reassign, one that must collide+drop,
        one that must self-collapse+drop (duplicate -> a third character that
        is ALSO the survivor's existing relationship target)
      - chunk/summary character_ids arrays containing the duplicate's id
    """
    db = SessionLocal()
    tag = str(id(object()))
    user = User(email=f"merge-test-{tag}@narratiq-internal-test.com",
                username=f"mergetest{tag}", hashed_password="x")
    db.add(user)
    db.flush()
    story = Story(user_id=user.user_id, title="[4.8-FIXTURE] Merge Test Story")
    db.add(story)
    db.flush()
    ch1 = Chapter(story_id=story.story_id, chapter_number=1, title="Ch1", content="<p>...</p>")
    ch2 = Chapter(story_id=story.story_id, chapter_number=2, title="Ch2", content="<p>...</p>")
    db.add_all([ch1, ch2])
    db.flush()

    survivor = Character(story_id=story.story_id, user_id=user.user_id,
                          name="Kael", aliases=["The Smith"], role="supporting", status="active")
    duplicate = Character(story_id=story.story_id, user_id=user.user_id,
                           name="Kaelin", aliases=["Kael the Younger"], role="protagonist", status="active")
    third = Character(story_id=story.story_id, user_id=user.user_id,
                       name="Mira", aliases=[], role="supporting", status="active")
    db.add_all([survivor, duplicate, third])
    db.flush()

    # Profiles — survivor missing 'goals', duplicate has it (richer wins);
    # both have 'appearance' set differently (survivor's must NOT be overwritten).
    db.add(CharacterProfile(
        character_id=survivor.character_id, story_id=story.story_id,
        appearance="Survivor's appearance.", goals="", traits=["stubborn"],
    ))
    db.add(CharacterProfile(
        character_id=duplicate.character_id, story_id=story.story_id,
        appearance="Duplicate's appearance (must be discarded).",
        goals="Duplicate's goal (must be adopted).", traits=["loyal"],
    ))

    # Intelligence — both present; survivor's must be kept (marked stale).
    db.add(CharacterIntelligence(character_id=survivor.character_id, story_id=story.story_id,
                                  arc_stage="setup"))
    db.add(CharacterIntelligence(character_id=duplicate.character_id, story_id=story.story_id,
                                  arc_stage="climax"))

    # Arc snapshots — chapter 1: BOTH have one (duplicate's must be dropped,
    # cascade-deleted). chapter 2: only duplicate has one (must reassign).
    db.add(CharacterArcSnapshot(character_id=survivor.character_id, story_id=story.story_id,
                                 chapter_id=ch1.chapter_id, chapter_number=1))
    db.add(CharacterArcSnapshot(character_id=duplicate.character_id, story_id=story.story_id,
                                 chapter_id=ch1.chapter_id, chapter_number=1))
    db.add(CharacterArcSnapshot(character_id=duplicate.character_id, story_id=story.story_id,
                                 chapter_id=ch2.chapter_id, chapter_number=2))

    db.flush()

    # Mentions — one for duplicate, with co_character_ids referencing survivor
    # AND third (survivor's own id must not be duplicated after the swap).
    m = CharacterMention(
        character_id=duplicate.character_id, story_id=story.story_id,
        chapter_id=ch1.chapter_id, chapter_number=1, passage_text="Kaelin spoke.",
        mention_type="reference", co_character_ids=[survivor.character_id, third.character_id],
    )
    db.add(m)
    # A DIFFERENT character's mention that co-lists the duplicate — exercises
    # the "duplicate appears inside someone else's co_character_ids" path,
    # which the mention above (duplicate's own) cannot cover.
    m_third = CharacterMention(
        character_id=third.character_id, story_id=story.story_id,
        chapter_id=ch1.chapter_id, chapter_number=1, passage_text="Mira and Kaelin spoke.",
        mention_type="reference", co_character_ids=[duplicate.character_id],
    )
    db.add(m_third)

    # Relationships:
    #  A) duplicate -> third  : must be REASSIGNED to survivor -> third
    #     (survivor has no existing edge to third of this type)
    rel_reassign = CharacterRelationship(
        story_id=story.story_id, from_character_id=duplicate.character_id,
        to_character_id=third.character_id, relationship_type="ally",
    )
    #  B) duplicate -> survivor : must SELF-COLLAPSE and be DROPPED
    rel_self = CharacterRelationship(
        story_id=story.story_id, from_character_id=duplicate.character_id,
        to_character_id=survivor.character_id, relationship_type="rival",
    )
    db.add_all([rel_reassign, rel_self])
    db.flush()

    #  C) survivor -> third (family) already exists; duplicate -> third
    #     (family) must COLLIDE with it after rewrite and be DROPPED.
    rel_existing = CharacterRelationship(
        story_id=story.story_id, from_character_id=survivor.character_id,
        to_character_id=third.character_id, relationship_type="family",
    )
    rel_collide = CharacterRelationship(
        story_id=story.story_id, from_character_id=duplicate.character_id,
        to_character_id=third.character_id, relationship_type="family",
    )
    db.add_all([rel_existing, rel_collide])
    db.flush()

    db.add(RelationshipIntelligence(
        relationship_id=rel_reassign.relationship_id, story_id=story.story_id,
        from_character_id=duplicate.character_id, to_character_id=third.character_id,
    ))
    db.add(RelationshipIntelligence(
        relationship_id=rel_collide.relationship_id, story_id=story.story_id,
        from_character_id=duplicate.character_id, to_character_id=third.character_id,
    ))

    # Chunk + summary character_ids arrays containing the duplicate.
    chunk = ChapterChunk(chapter_id=ch1.chapter_id, story_id=story.story_id, chapter_number=1,
                          chunk_index=0, text="Kaelin appeared.", word_count=2,
                          character_ids=[duplicate.character_id, third.character_id])
    db.add(chunk)
    cs = ChapterSummary(chapter_id=ch1.chapter_id, story_id=story.story_id, chapter_number=1,
                         raw_summary="x", character_ids=[duplicate.character_id])
    db.add(cs)

    db.commit()

    ids = {
        "story_id": story.story_id, "user_id": user.user_id,
        "survivor_id": survivor.character_id, "duplicate_id": duplicate.character_id,
        "third_id": third.character_id,
        "rel_reassign_id": rel_reassign.relationship_id,
        "rel_collide_id": rel_collide.relationship_id,
        "ch1_id": ch1.chapter_id, "ch2_id": ch2.chapter_id,
        "chunk_id": chunk.chunk_id, "summary_id": cs.summary_id, "mention_id": m.mention_id,
        "mention_third_id": m_third.mention_id,
    }

    try:
        yield {**ids, "db": db}
    finally:
        db2 = SessionLocal()
        s = db2.query(Story).filter(Story.story_id == story.story_id).first()
        if s:
            db2.delete(s)
        u = db2.query(User).filter(User.user_id == user.user_id).first()
        if u:
            db2.delete(u)
        db2.commit()
        orphans = _orphan_scan(db2, story.story_id, user.user_id)
        db2.close()
        db.close()
        assert not orphans, f"orphan rows left behind by merge_fixture cleanup: {orphans}"


def test_merge_rejects_self_merge(merge_fixture):
    with pytest.raises(MergeError):
        merge_characters(merge_fixture["db"], merge_fixture["story_id"],
                          merge_fixture["survivor_id"], merge_fixture["survivor_id"])


def test_merge_rejects_unknown_character(merge_fixture):
    with pytest.raises(MergeError):
        merge_characters(merge_fixture["db"], merge_fixture["story_id"],
                          merge_fixture["survivor_id"], "does-not-exist")


def test_full_merge_end_to_end(merge_fixture):
    db = merge_fixture["db"]
    story_id = merge_fixture["story_id"]
    survivor_id = merge_fixture["survivor_id"]
    duplicate_id = merge_fixture["duplicate_id"]

    summary = merge_characters(db, story_id, survivor_id, duplicate_id)
    db.commit()

    # ── Character itself ────────────────────────────────────────────────────
    survivor = db.query(Character).filter(Character.character_id == survivor_id).first()
    duplicate_gone = db.query(Character).filter(Character.character_id == duplicate_id).first()
    assert duplicate_gone is None, "duplicate character must be deleted"
    assert survivor.role == "protagonist", "higher-priority role must win (duplicate was protagonist)"
    alias_lower = {a.lower() for a in survivor.aliases}
    assert "kaelin" in alias_lower, "duplicate's name must become an alias"
    assert "kael the younger" in alias_lower, "duplicate's own aliases must be preserved"
    assert "the smith" in alias_lower, "survivor's own aliases must be preserved"

    # ── Profile: richer-wins, survivor's non-empty field never overwritten ─
    profile = db.query(CharacterProfile).filter(CharacterProfile.character_id == survivor_id).first()
    assert profile.appearance == "Survivor's appearance.", "non-empty survivor field must not be overwritten"
    assert profile.goals == "Duplicate's goal (must be adopted).", "empty survivor field must adopt duplicate's value"
    assert set(profile.traits) == {"stubborn", "loyal"}, "traits must be unioned"
    dup_profile_gone = db.query(CharacterProfile).filter(CharacterProfile.character_id == duplicate_id).first()
    assert dup_profile_gone is None, "duplicate's own profile row must be gone (cascade-deleted)"

    # ── Intelligence: survivor's kept, marked stale, not field-spliced ─────
    intel = db.query(CharacterIntelligence).filter(CharacterIntelligence.character_id == survivor_id).first()
    assert intel.arc_stage == "setup", "survivor's intelligence row must be kept as-is, not merged field-by-field"
    assert intel.is_stale is True, "kept intelligence must be flagged for regeneration"

    # ── Arc snapshots: ch1 collision dropped, ch2 reassigned ───────────────
    ch1_snapshots = db.query(CharacterArcSnapshot).filter(
        CharacterArcSnapshot.chapter_id == merge_fixture["ch1_id"]
    ).all()
    assert len(ch1_snapshots) == 1 and ch1_snapshots[0].character_id == survivor_id, (
        "chapter with both characters' snapshots must keep only the survivor's"
    )
    ch2_snapshots = db.query(CharacterArcSnapshot).filter(
        CharacterArcSnapshot.chapter_id == merge_fixture["ch2_id"]
    ).all()
    assert len(ch2_snapshots) == 1 and ch2_snapshots[0].character_id == survivor_id, (
        "duplicate-only chapter's snapshot must be reassigned to survivor"
    )

    # ── Mentions: reassigned, co_character_ids deduplicated ────────────────
    mention = db.query(CharacterMention).filter(
        CharacterMention.mention_id == merge_fixture["mention_id"]
    ).first()
    assert mention.character_id == survivor_id, "mention must be reassigned to survivor"
    assert mention.co_character_ids.count(survivor_id) == 1, (
        "co_character_ids must not contain the survivor twice after the swap "
        f"(got {mention.co_character_ids})"
    )
    assert merge_fixture["third_id"] in mention.co_character_ids

    mention_third = db.query(CharacterMention).filter(
        CharacterMention.mention_id == merge_fixture["mention_third_id"]
    ).first()
    assert mention_third.co_character_ids == [survivor_id], (
        "a DIFFERENT character's co_character_ids referencing the duplicate must "
        f"also be swapped to the survivor (got {mention_third.co_character_ids})"
    )

    # ── Relationships: reassign / self-collapse-drop / collide-drop ────────
    remaining_rels = db.query(CharacterRelationship).filter(
        CharacterRelationship.story_id == story_id,
    ).all()
    pairs = {(r.from_character_id, r.to_character_id, r.relationship_type) for r in remaining_rels}
    assert (survivor_id, merge_fixture["third_id"], "ally") in pairs, "reassignable edge must survive, rewritten"
    assert (survivor_id, survivor_id, "rival") not in pairs, "self-collapsed edge must never exist"
    assert not any(
        r.relationship_type == "rival" and duplicate_id in (r.from_character_id, r.to_character_id)
        for r in remaining_rels
    ), "the duplicate->survivor self-edge must be gone entirely"
    # Only ONE family edge between survivor and third must remain (the
    # pre-existing one) — the colliding duplicate edge must be dropped, not duplicated.
    family_edges = [r for r in remaining_rels
                    if r.relationship_type == "family"
                    and {r.from_character_id, r.to_character_id} == {survivor_id, merge_fixture["third_id"]}]
    assert len(family_edges) == 1, f"colliding relationship must be dropped, not duplicated (found {len(family_edges)})"

    # RelationshipIntelligence must follow: one for the reassigned edge, none
    # for the dropped collision.
    ri_reassigned = db.query(RelationshipIntelligence).filter(
        RelationshipIntelligence.relationship_id == merge_fixture["rel_reassign_id"]
    ).first()
    assert ri_reassigned is not None and ri_reassigned.from_character_id == survivor_id
    ri_dropped = db.query(RelationshipIntelligence).filter(
        RelationshipIntelligence.relationship_id == merge_fixture["rel_collide_id"]
    ).first()
    assert ri_dropped is None, "relationship_intelligence for a dropped edge must be gone too"

    # ── Denormalized JSON arrays ─────────────────────────────────────────────
    chunk = db.query(ChapterChunk).filter(ChapterChunk.chunk_id == merge_fixture["chunk_id"]).first()
    assert duplicate_id not in chunk.character_ids
    assert survivor_id in chunk.character_ids
    assert chunk.character_ids.count(survivor_id) == 1

    cs = db.query(ChapterSummary).filter(ChapterSummary.summary_id == merge_fixture["summary_id"]).first()
    assert cs.character_ids == [survivor_id]

    # ── No orphan references anywhere (the general scan, not just this test's) ─
    rows = db.execute(sqltext("""
        SELECT table_name, column_name FROM information_schema.columns
        WHERE table_schema='public' AND (column_name = 'character_id'
              OR column_name IN ('from_character_id', 'to_character_id'))
    """)).fetchall()
    for table_name, column_name in rows:
        cnt = db.execute(
            sqltext(f'SELECT count(*) FROM "{table_name}" WHERE "{column_name}" = :v'),
            {"v": duplicate_id},
        ).scalar()
        assert cnt == 0, f"orphan reference to deleted character in {table_name}.{column_name}"

    print(f"\n[4.8] merge summary: {summary}")


def test_merge_is_transactional_a_failure_rolls_back_everything(merge_fixture, monkeypatch):
    """
    Force a failure AFTER merge_characters has already mutated several tables
    in-session (role/aliases/profile/intelligence/arc-snapshots all run before
    relationships) but BEFORE the caller commits, then roll back — proving the
    router's own try/except/rollback pattern (routers/characters.py's
    merge_character endpoint) actually prevents a partial merge.
    """
    db = merge_fixture["db"]
    story_id = merge_fixture["story_id"]
    survivor_id = merge_fixture["survivor_id"]
    duplicate_id = merge_fixture["duplicate_id"]

    import services.character_merge as merge_mod
    from models import RelationshipIntelligence

    # Fail during step 6/7 (relationships), which runs after steps 1-5 have
    # already mutated the session — the realistic "partway through" case.
    # Monkeypatch db.query itself, but only fail once RelationshipIntelligence
    # is the target — everything before that (profile, intelligence, arc
    # snapshots) must be allowed to run and actually mutate the session.
    original_query = db.query

    def query_with_late_failure(model, *a, **kw):
        if model is RelationshipIntelligence:
            raise RuntimeError("simulated failure partway through the merge")
        return original_query(model, *a, **kw)

    monkeypatch.setattr(db, "query", query_with_late_failure)

    with pytest.raises(RuntimeError):
        try:
            merge_mod.merge_characters(db, story_id, survivor_id, duplicate_id)
        finally:
            db.rollback()

    monkeypatch.undo()  # restore db.query before further use in this test

    # After rollback: nothing from the aborted merge must have stuck —
    # survivor's role must be unchanged (duplicate was "protagonist", which
    # WOULD have won), and the duplicate character must still exist.
    db.expire_all()
    survivor = db.query(Character).filter(Character.character_id == survivor_id).first()
    duplicate = db.query(Character).filter(Character.character_id == duplicate_id).first()
    assert survivor.role == "supporting", "rollback must undo the in-session role mutation"
    assert duplicate is not None, "rollback must leave the duplicate character in place"
    dup_profile = db.query(CharacterProfile).filter(
        CharacterProfile.character_id == duplicate_id
    ).first()
    assert dup_profile is not None, "rollback must leave the duplicate's profile in place"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v", "-s"]))
