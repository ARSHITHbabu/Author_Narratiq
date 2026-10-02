#!/usr/bin/env python3
"""
Stage 12 — live D-1 check for VOICE Q&A, real models end to end.

On the TEST database: the shared retrieval fixture (6 chapters) with PLANTED
secrets that exist only after chapter 3:
  * a sentence added to chapter 6 (embedded like any other passage),
  * a Story Intelligence memory entry tagged chapter 6,
  * an untagged (author-added) memory entry,
  * a recorded character relationship whose description reveals the secret,
plus real summaries and a REAL Story Intelligence analysis (P01–P29). Then
real voice turns through POST /api/voice/interpret (real planner, BGE-M3
retrieval, Qwen answers) with chapter 3 open. Every retrieval result and every
prompt sent to the model is captured and checked for the secrets.

Expect: chapter 3 open → no secret and no chapter > 3 passage in any retrieval
or prompt; an explicit "whole book" turn → the secrets ARE visible (the check
can see them); no chapter open → refusal, no retrieval, no model answer call.

  DATABASE_URL=...narratiq_test python3 tests/live_voice_spoiler_d1.py
Writes tests/fixtures/live_voice_spoiler_d1.json.
"""
from __future__ import annotations

import asyncio
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

PLANTED_CH6 = ("<p>Nobody but Vell knew that the tidewater vault beneath the customs house "
               "held the obsidian ledger of every bribe he had ever taken.</p>")
SECRETS = ["tidewater vault", "obsidian ledger", "violet heron", "secret half-brother"]
LATE_MARKERS = ["faked", "tharsk", "never left office", "still the harbor magistrate"]
TURNS = [
    ("story_qa", "What happened to Magistrate Vell after the flood?", 3),
    ("story_qa", "What is hidden beneath the customs house?", 3),
    ("character_qa", "Who is Ondrej Vell?", 3),
    ("relationship", "How are Corvin Ashe and Ondrej Vell related?", 3),
    ("story_qa_whole", "In the whole book, what is hidden beneath the customs house?", 3),
    ("story_qa_whole_2", "Across the whole manuscript, what does Vell keep in the tidewater vault?", 3),
    ("no_chapter", "What happened to Magistrate Vell after the flood?", None),
]


def main():
    from fastapi.testclient import TestClient
    import main as app_main
    from config import settings
    from database import SessionLocal, engine
    from db_safety_guard import allowed_test_dbs, is_allowed_test_db_name
    from middleware.rate_limit import limiter
    from models import Character, CharacterProfile, CharacterRelationship, StoryMemoryEntry
    from routers.auth import create_token
    from services import ai_service as ai
    from services import story_intel_service as sis
    from services.story_intel_orchestrator import run_full_analysis
    from tests.fixtures import retrieval_fixture as rf

    assert is_allowed_test_db_name(engine.url.database, allowed_test_dbs()), engine.url.database
    limiter.enabled = False
    settings.voice_agent_enabled = True
    original_chapters = copy.deepcopy(rf.CHAPTERS)
    rf.CHAPTERS[5]["content"] += PLANTED_CH6           # in memory only, for this run
    db = SessionLocal()
    info = asyncio.run(rf.build_fixture(db))
    rf.CHAPTERS[:] = original_chapters
    sid, uid = info["story_id"], info["user_id"]

    prompts: list[str] = []
    retrieved: list[dict] = []
    orig = {"complete_ex": ai._complete_ex, "chunks": ai.retrieve_chunks_from_store,
            "chars": ai.retrieve_character_context, "intel": sis.build_integration_context}

    async def spy_complete(system, user, *a, **k):
        prompts.append((system or "") + "\n" + (user or ""))
        return await orig["complete_ex"](system, user, *a, **k)

    async def spy_chunks(*a, **k):
        out = await orig["chunks"](*a, **k)
        retrieved.append({"kind": "passages", "cap": k.get("max_chapter_number"),
                          "chapters": sorted({c.get("chapter") for c in out}, key=str),
                          "text": " ".join(c.get("text", "") for c in out)})
        return out

    async def spy_chars(*a, **k):
        out = await orig["chars"](*a, **k)
        retrieved.append({"kind": "characters", "cap": k.get("max_chapter_number"), "text": " ".join(out or [])})
        return out

    async def spy_intel(*a, **k):
        out = await orig["intel"](*a, **k)
        retrieved.append({"kind": "story_intelligence", "cap": k.get("max_chapter_number"),
                          "text": json.dumps(out, default=str)})
        return out

    report = {"turns": []}
    try:
        async def prep():
            for c in rf.CHAPTERS:
                content = c["content"] + (PLANTED_CH6 if c["number"] == 6 else "")
                await ai.summarize_and_embed_chapter(info["chapter_ids"][c["number"]], sid, c["number"], content, db)
            ids = {}
            for name, role in (("Mira Okoye", "protagonist"), ("Hessa Lin", "supporting"),
                               ("Corvin Ashe", "supporting"), ("Ondrej Vell", "antagonist")):
                ch = Character(story_id=sid, user_id=uid, name=name, role=role, aliases=[])
                db.add(ch)
                db.flush()
                db.add(CharacterProfile(character_id=ch.character_id, story_id=sid))
                ids[name] = ch.character_id
            db.add(CharacterRelationship(story_id=sid, from_character_id=ids["Corvin Ashe"],
                                         to_character_id=ids["Ondrej Vell"], relationship_type="family",
                                         description="Corvin is Vell's secret half-brother (revealed in chapter 6)."))
            db.commit()
            res = await run_full_analysis(sid, db)
            db.add(StoryMemoryEntry(story_id=sid, memory_type="plot_fact", memory_key="planted_tagged",
                                    content="The obsidian ledger is kept in the tidewater vault.",
                                    chapter_first_established=6, chapter_last_updated=6, importance=1.0))
            db.add(StoryMemoryEntry(story_id=sid, memory_type="plot_fact", memory_key="planted_untagged",
                                    content="Author note: the violet heron is Vell's signal to the smugglers.",
                                    importance=1.0))
            db.commit()
            return res

        result = asyncio.run(prep())
        report["analysis"] = {k: result.get(k) for k in ("status", "passes_completed", "passes_failed") if k in result}
        ai._complete_ex = spy_complete
        ai.retrieve_chunks_from_store = spy_chunks
        ai.retrieve_character_context = spy_chars
        sis.build_integration_context = spy_intel
        client = TestClient(app_main.app)
        headers = {"Authorization": f"Bearer {create_token(uid)}"}
        ch3_text = rf._html_to_plain(rf.CHAPTERS[2]["content"]) if hasattr(rf, "_html_to_plain") else None
        if ch3_text is None:
            from routers.search import _html_to_plain
            ch3_text = _html_to_plain(rf.CHAPTERS[2]["content"])
        for label, q, cap in TURNS:
            prompts.clear()
            retrieved.clear()
            ctx = {"story_id": sid}
            if cap is not None:
                ctx.update(chapter_id=info["chapter_ids"][cap], chapter_number=cap, full_chapter_text=ch3_text)
            r = client.post("/api/voice/interpret", headers=headers,
                            json={"transcript": q, "context": ctx, "skip_clean": True})
            body = r.json() if r.status_code == 200 else {"detail": r.text[:300]}
            joined_prompts = "\n".join(prompts).lower()
            joined_retrieval = "\n".join(x["text"] for x in retrieved).lower()
            answer = json.dumps(body.get("result", {}), default=str)[:600]
            rec = {"turn": label, "question": q, "open_chapter": cap, "status": r.status_code,
                   "turn_status": body.get("status"), "clarification": body.get("clarification"),
                   "capability": body.get("capability"), "context_used": body.get("context_used"),
                   "model_calls": len(prompts),
                   "retrievals": [{k: v for k, v in x.items() if k != "text"} for x in retrieved],
                   "passage_chapters_over_cap": sorted({c for x in retrieved if x["kind"] == "passages"
                                                        for c in x["chapters"]
                                                        if cap is not None and isinstance(c, int) and c > cap}),
                   "secrets_in_retrieval": [s for s in SECRETS if s in joined_retrieval],
                   "secrets_in_prompts": [s for s in SECRETS if s in joined_prompts],
                   "late_markers_in_prompts": [m for m in LATE_MARKERS if m in joined_prompts],
                   "answer": answer}
            report["turns"].append(rec)
            print(json.dumps({k: rec[k] for k in ("turn", "status", "turn_status", "capability", "model_calls",
                                                   "passage_chapters_over_cap", "secrets_in_retrieval",
                                                   "secrets_in_prompts", "late_markers_in_prompts")}), flush=True)
    finally:
        ai._complete_ex = orig["complete_ex"]
        ai.retrieve_chunks_from_store = orig["chunks"]
        ai.retrieve_character_context = orig["chars"]
        sis.build_integration_context = orig["intel"]
        rf.CHAPTERS[:] = original_chapters
        db.rollback()
        db.query(StoryMemoryEntry).filter(StoryMemoryEntry.story_id == sid).delete()
        db.commit()
        rf.cleanup_fixture(db, sid, uid)
        db.close()
    out = Path(__file__).parent / "fixtures" / "live_voice_spoiler_d1.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print("analysis:", report.get("analysis"))


if __name__ == "__main__":
    main()
