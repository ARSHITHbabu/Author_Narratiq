"""
End-to-end smoke verification for the Voice Agent against the REAL stack
(PostgreSQL + BGE-M3 shortlist + Qwen planner via vLLM). Not a pytest — run:

    cd backend && python3 tests/voice_e2e_smoke.py

Creates a throwaway user/story/chapters/character, runs the plan §13 command
matrix through services.voice.agent.interpret, prints a routing table, and
asserts the critical safety + routing invariants. Exits non-zero on failure.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import SessionLocal
from models import User, Story, Chapter, Character
from routers.auth import hash_password
from schemas import VoiceContext
from services.ai_service import get_bge
from services.voice.catalog import build_catalog_embeddings
from services.voice import agent as voice_agent

TEST_EMAIL = "voice-e2e@narratiq.test"


def purge(db, user):
    from models import VoiceSession, VoiceCommand
    sids = [s.story_id for s in db.query(Story).filter_by(user_id=user.user_id).all()]
    db.query(VoiceCommand).filter_by(user_id=user.user_id).delete()
    db.query(VoiceSession).filter_by(user_id=user.user_id).delete()
    for sid in sids:
        db.query(Chapter).filter_by(story_id=sid).delete()
        db.query(Character).filter_by(story_id=sid).delete()
    db.query(Story).filter_by(user_id=user.user_id).delete()
    db.query(User).filter_by(user_id=user.user_id).delete()
    db.commit()


def setup(db):
    prior = db.query(User).filter(User.email == TEST_EMAIL).first()
    if prior:
        purge(db, prior)
    user = User(email=TEST_EMAIL, username="voice-e2e", hashed_password=hash_password("x" * 12))
    db.add(user); db.flush()
    story = Story(user_id=user.user_id, title="Smoke Story", description="thriller test")
    db.add(story); db.flush()
    ch1 = Chapter(story_id=story.story_id, chapter_number=1, title="One", content="<p>Raj walked in.</p>", word_count=3)
    ch2 = Chapter(story_id=story.story_id, chapter_number=2, title="Two", content="<p>Long slow chapter.</p>", word_count=900)
    db.add_all([ch1, ch2])
    char = Character(story_id=story.story_id, user_id=user.user_id, name="Mr. Dinesh", role="supporting")
    db.add(char); db.flush()
    db.commit()
    return user, story, ch1, ch2, char


async def run():
    print("Loading BGE-M3 + building capability index…")
    get_bge()
    build_catalog_embeddings()

    db = SessionLocal()
    user, story, ch1, ch2, char = setup(db)
    sid = story.story_id

    def ctx(**kw):
        base = dict(story_id=sid, chapter_id=ch2.chapter_id, chapter_number=2)
        base.update(kw)
        return VoiceContext(**base)

    # (command, context, expected_capabilities_subset, expect_confirm, note)
    matrix = [
        ("Create a new thriller story called The Silent Floor", VoiceContext(), {"project_mgmt"}, True, "create=write"),
        ("Open chapter one", ctx(), {"chapter_mgmt"}, None, ""),
        ("Make this paragraph darker and more emotional", ctx(selected_text="He left.", has_selection=True), {"text_transform"}, None, "selection transform"),
        ("Generate three continuation options for this scene", ctx(), {"continuation"}, None, ""),
        ("Check if this chapter has style drift", ctx(), {"style_drift"}, False, "analyze"),
        ("Find repeated scenes", ctx(), {"duplicate_scenes"}, False, "analyze"),
        ("Generate a story bible", ctx(), {"story_bible"}, None, ""),
        ("Summarize the emotional arc", ctx(), {"emotional_arc"}, False, "analyze"),
        ("Set a pacing goal of 1500 words per chapter", ctx(), {"pacing_goals"}, None, "write"),
        ("Find all scenes where Mr. Dinesh appears", ctx(), {"search_replace", "character_mgmt"}, None, "entity"),
        ("Replace the name Raj with Arjun in chapter one", ctx(), {"search_replace"}, True, "destructive"),
        ("Export this story", ctx(), {"export"}, True, "export"),
        ("Delete this story", ctx(), {"project_mgmt"}, True, "destructive"),
        ("What are the plot holes so far?", ctx(), {"plot_holes"}, False, "analyze"),
        ("Check continuity issues between chapter two and chapter five", ctx(), {"continuity_check"}, False, "analyze"),
    ]

    print(f"\n{'COMMAND':<52} {'CAPABILITY.ACTION':<28} {'TYPE':<10} {'STATUS':<20} CONF")
    print("-" * 130)
    failures = []
    session_id = None
    for command, c, expect_caps, expect_confirm, note in matrix:
        resp = await voice_agent.interpret(db, user, command, c, session_id=session_id)
        session_id = resp.session_id
        cap = resp.capability or "—"
        intent = resp.detected_intent or "—"
        print(f"{command[:50]:<52} {intent:<28} {resp.action_type:<10} {resp.status:<20} {resp.confidence:.2f}")

        if resp.status != "needs_clarification" and expect_caps and cap not in expect_caps:
            failures.append(f"  ROUTING: {command!r} → {cap}, expected one of {expect_caps}")
        if expect_confirm is True and not resp.requires_confirmation and resp.status != "needs_clarification":
            failures.append(f"  SAFETY: {command!r} should require confirmation but did not")
        if expect_confirm is False and resp.requires_confirmation:
            failures.append(f"  SAFETY: {command!r} should NOT require confirmation but did")

    # ── Unclear command → clarification / low confidence ─────────────────────
    unclear = await voice_agent.interpret(db, user, "xyzzy quantum banana sprocket", ctx(), session_id=session_id)
    print(f"{'(unclear) xyzzy quantum banana':<52} {unclear.detected_intent or '—':<28} "
          f"{unclear.action_type:<10} {unclear.status:<20} {unclear.confidence:.2f}")

    # ── Multi-step (A) ───────────────────────────────────────────────────────
    multi = await voice_agent.interpret(
        db, user, "Analyze the pacing, find the slow sections, then rewrite them", ctx(), session_id=session_id)
    print(f"\nMulti-step: is_multi_step={multi.is_multi_step} "
          f"nodes={multi.workflow.node_count if multi.workflow else 0} status={multi.status}")
    if multi.workflow:
        for n in multi.workflow.nodes:
            print(f"   - {n.node_key}: {n.capability}.{n.action} [{n.action_type}] "
                  f"locus={n.execution_locus} deps={n.depends_on} confirm={n.requires_confirmation}")
    if multi.workflow and any(n.action_type in ("write", "destructive", "export") and not n.requires_confirmation
                              for n in multi.workflow.nodes):
        failures.append("  SAFETY: a mutating node in the multi-step graph lacked confirmation")

    # ── Session continuity (B) ───────────────────────────────────────────────
    sess = db.query(__import__("models").VoiceSession).filter_by(session_id=session_id).first()
    print(f"\nSession continuity: session_id stable={session_id is not None}, "
          f"command_count={sess.command_count if sess else 'NA'}")
    if not sess or (sess.command_count or 0) < len(matrix):
        failures.append("  SESSION: command_count did not accumulate across turns")

    # ── Cleanup ──────────────────────────────────────────────────────────────
    try:
        purge(db, user)
    except Exception as exc:
        print("cleanup warning:", exc)
        db.rollback()
    finally:
        db.close()

    print("\n" + ("=" * 60))
    if failures:
        print(f"FAILURES ({len(failures)}):")
        print("\n".join(failures))
        sys.exit(1)
    print("ALL CRITICAL CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(run())
