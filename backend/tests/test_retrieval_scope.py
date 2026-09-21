"""
Stage 4 task 4.1 — Plot Assistant retrieval scope (D-1, option b).

Real integration test against the live local PostgreSQL + pgvector + BGE-M3 —
these functions embed text and run vector similarity queries, so a fake
session cannot exercise the actual scoping SQL. Everything created here is a
disposable fixture (self-labelled, cleaned up in a `finally` block, and
verified orphan-free afterward) — this never touches real author data.

Covers the checklist's own verification items for 4.1:
  - a question about a late chapter returns late-chapter evidence under
    story-wide ("full") scope
  - capped ("chapter") scope excludes later chapters as designed
  - retrieve_character_context's story-evidence passages respect the same cap

Run: cd backend && pytest tests/test_retrieval_scope.py -q -s
(requires PostgreSQL + pgvector reachable via backend/.env DATABASE_URL, and
BGE-M3 loadable — same requirements as the running backend.)
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from database import SessionLocal  # noqa: E402
from models import User, Story, Chapter, Character  # noqa: E402
from services.ai_service import (  # noqa: E402
    embed_and_store_chunks,
    retrieve_chunks_from_store,
    retrieve_character_context,
    index_character_mentions,
)

FIXTURE_TAG = "[4.1-SCOPE-TEST-FIXTURE]"


@pytest.fixture
def scope_fixture():
    db = SessionLocal()
    user = User(
        email=f"scope-test-{id(db)}@narratiq-internal-test.com",
        username=f"scopetest{id(db)}",
        hashed_password="x",
    )
    db.add(user)
    db.flush()

    story = Story(user_id=user.user_id, title=f"{FIXTURE_TAG} Scope Test Story")
    db.add(story)
    db.flush()

    ch1 = Chapter(story_id=story.story_id, chapter_number=1, title="Ch1",
                  content="<p>Mira walked into the quiet village at dawn, uncertain of what lay ahead.</p>")
    ch2 = Chapter(story_id=story.story_id, chapter_number=2, title="Ch2",
                  content="<p>Mira met an old merchant who spoke of distant mountains and old trade routes.</p>")
    ch3 = Chapter(story_id=story.story_id, chapter_number=3, title="Ch3",
                  content=(
                      "<p>Zorathmoon the hidden sorcerer revealed the buried crystal-forge secret "
                      "beneath the ruined tower, a revelation no earlier chapter foreshadowed.</p>"
                  ))
    db.add_all([ch1, ch2, ch3])
    db.flush()

    zorath = Character(story_id=story.story_id, user_id=user.user_id,
                        name="Zorathmoon", aliases=["the hidden sorcerer"])
    db.add(zorath)
    db.commit()

    async def _index():
        for ch in (ch1, ch2, ch3):
            from routers.search import _html_to_plain
            plain = _html_to_plain(ch.content)
            await embed_and_store_chunks(ch.chapter_id, story.story_id, ch.chapter_number, plain, db)
            await index_character_mentions(ch.chapter_id, story.story_id, ch.chapter_number, db)

    asyncio.run(_index())

    try:
        yield {"db": db, "story_id": story.story_id, "user_id": user.user_id,
               "character_id": zorath.character_id}
    finally:
        # Cleanup: delete via ORM so relationship cascades fire, matching the
        # orphan-free discipline used throughout this session's persistence work.
        db2 = SessionLocal()
        try:
            s = db2.query(Story).filter(Story.story_id == story.story_id).first()
            if s:
                db2.delete(s)
            u = db2.query(User).filter(User.user_id == user.user_id).first()
            if u:
                db2.delete(u)
            db2.commit()

            # Orphan check across every story_id/user_id-bearing table, same
            # pattern used for the persistence-verification fixture cleanup.
            from sqlalchemy import text as sqltext
            rows = db2.execute(sqltext("""
                SELECT table_name, column_name FROM information_schema.columns
                WHERE table_schema='public' AND column_name IN ('story_id','user_id')
            """)).fetchall()
            orphans = []
            for table_name, column_name in rows:
                val = story.story_id if column_name == "story_id" else user.user_id
                cnt = db2.execute(
                    sqltext(f'SELECT count(*) FROM "{table_name}" WHERE "{column_name}" = :v'),
                    {"v": val},
                ).scalar()
                if cnt:
                    orphans.append((table_name, column_name, cnt))
            assert not orphans, f"orphan rows left behind by scope_fixture cleanup: {orphans}"
        finally:
            db2.close()
        db.close()


def test_capped_scope_excludes_later_chapter_chunks(scope_fixture):
    db = scope_fixture["db"]
    story_id = scope_fixture["story_id"]

    async def run():
        return await retrieve_chunks_from_store(
            "What secret was revealed beneath the ruined tower?",
            story_id, db, top_k=8, max_chapter_number=1,
        )

    chunks = asyncio.run(run())
    chapters_hit = {c["chapter"] for c in chunks}
    assert 3 not in chapters_hit, "chapter-3 content leaked through a chapter=1 cap"


def test_full_scope_includes_later_chapter_chunks(scope_fixture):
    db = scope_fixture["db"]
    story_id = scope_fixture["story_id"]

    async def run():
        return await retrieve_chunks_from_store(
            "What secret was revealed beneath the ruined tower?",
            story_id, db, top_k=8, max_chapter_number=None,
        )

    chunks = asyncio.run(run())
    chapters_hit = {c["chapter"] for c in chunks}
    assert 3 in chapters_hit, "full-scope search failed to find the chapter-3 revelation"


def test_character_context_story_evidence_respects_chapter_cap(scope_fixture):
    db = scope_fixture["db"]
    story_id = scope_fixture["story_id"]

    async def run_capped():
        return await retrieve_character_context(
            story_id, "Tell me about Zorathmoon the hidden sorcerer", db,
            top_k=3, token_budget=800, max_chapter_number=1,
        )

    async def run_full():
        return await retrieve_character_context(
            story_id, "Tell me about Zorathmoon the hidden sorcerer", db,
            top_k=3, token_budget=800, max_chapter_number=None,
        )

    capped = asyncio.run(run_capped())
    full = asyncio.run(run_full())

    capped_text = "\n".join(capped)
    full_text = "\n".join(full)

    # The character block itself may still appear (character existence isn't
    # scoped — only which story-evidence passages get quoted), but the
    # chapter-3 crystal-forge evidence text must not appear under the cap.
    assert "crystal-forge" not in capped_text, "chapter-3 evidence leaked under a chapter=1 cap"
    assert "crystal-forge" in full_text, "full scope failed to surface the chapter-3 evidence"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v", "-s"]))
