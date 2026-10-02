#!/usr/bin/env python3
"""
Stage 12 Tranche 2a — live D-1 boundary check with real models end to end.

On the TEST database: the shared retrieval fixture (6 chapters; Vell is revealed
alive in chapter 5, still in office in chapter 6), real summaries, the main
characters, and a REAL Story Intelligence analysis (P01–P29). Then real Plot
Assistant requests through the router (real intent detection, BGE-M3 retrieval,
Qwen answers). Every prompt sent to the model is captured and checked for
material that exists only in chapters 5–6.

Expect: no late-chapter marker in any prompt at chapter scope 3; markers DO
appear at full scope (the check can see them); chapter scope without a number
is refused (422).

  DATABASE_URL=...narratiq_test python3 tests/live_spoiler_boundary_t2a.py
Writes tests/fixtures/live_spoiler_boundary_t2a.json.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Facts only in chapters 5–6 (or analysis derived from them).
LATE_MARKERS = ["faked", "tharsk", "weapons", "never left office", "still the harbor magistrate",
                "still the harbour magistrate", "loyal harbor guard"]
QUESTIONS = [
    ("qa", "What happened to Magistrate Vell after the flood?"),
    ("creative", "Suggest what Mira should do next."),
    ("mixed", "Who is Corvin Ashe, and how could his role grow?"),
]


def main():
    from fastapi.testclient import TestClient
    import main as app_main
    from database import SessionLocal, engine
    from db_safety_guard import allowed_test_dbs, is_allowed_test_db_name
    from middleware.rate_limit import limiter
    from models import Character, CharacterProfile, StoryMemoryEntry
    from routers.auth import create_token
    from services import ai_service as ai
    from services.story_intel_orchestrator import run_full_analysis
    from tests.fixtures.retrieval_fixture import CHAPTERS, build_fixture, cleanup_fixture

    assert is_allowed_test_db_name(engine.url.database, allowed_test_dbs()), engine.url.database
    limiter.enabled = False
    db = SessionLocal()
    info = asyncio.run(build_fixture(db))
    sid, uid = info["story_id"], info["user_id"]
    prompts: list[str] = []
    orig_complete_ex = ai._complete_ex

    async def spy(system, user, *a, **k):
        prompts.append((system or "") + "\n" + (user or ""))
        return await orig_complete_ex(system, user, *a, **k)

    report = {"requests": [], "memory": {}}
    try:
        async def prep():
            for c in CHAPTERS:
                await ai.summarize_and_embed_chapter(info["chapter_ids"][c["number"]], sid, c["number"], c["content"], db)
            for name, role in (("Mira Okoye", "protagonist"), ("Hessa Lin", "supporting"),
                               ("Corvin Ashe", "supporting"), ("Ondrej Vell", "antagonist")):
                ch = Character(story_id=sid, user_id=uid, name=name, role=role, aliases=[])
                db.add(ch)
                db.flush()
                db.add(CharacterProfile(character_id=ch.character_id, story_id=sid))
            db.commit()
            return await run_full_analysis(sid, db)

        result = asyncio.run(prep())
        report["analysis"] = {k: result.get(k) for k in ("status", "passes_completed", "passes_failed") if k in result}
        rows = db.query(StoryMemoryEntry).filter(StoryMemoryEntry.story_id == sid).all()
        report["memory"] = {"entries": len(rows), "tags": sorted({r.chapter_last_updated for r in rows}, key=str)}

        ai._complete_ex = spy
        client = TestClient(app_main.app)
        headers = {"Authorization": f"Bearer {create_token(uid)}"}
        for scope, cap in (("chapter", 3), ("full", None), ("chapter", 6)):
            for _intent, q in QUESTIONS:
                prompts.clear()
                body = {"story_id": sid, "question": q, "scope": scope}
                if cap is not None:
                    body["current_chapter_number"] = cap
                r = client.post("/api/plot-assistant/", headers=headers, json=body)
                joined = "\n".join(prompts).lower()
                hits = [m for m in LATE_MARKERS if m in joined]
                rec = {"scope": scope, "cap": cap, "question": q, "status": r.status_code,
                       "model_calls": len(prompts), "late_markers_in_prompts": hits}
                if r.status_code == 200:
                    b = r.json()
                    rec["answer"] = (b.get("answer") or "")[:400]
                    rec["suggestions"] = [s["text"][:160] for s in b.get("suggestions", [])]
                    ans = (rec["answer"] + " " + " ".join(rec["suggestions"])).lower()
                    rec["late_markers_in_answer"] = [m for m in LATE_MARKERS if m in ans]
                report["requests"].append(rec)
                print(json.dumps({k: rec[k] for k in ("scope", "cap", "question", "status", "model_calls",
                                                       "late_markers_in_prompts")}), flush=True)
        r = client.post("/api/plot-assistant/", headers=headers, json={"story_id": sid, "question": "Anything?"})
        report["chapter_scope_without_number"] = {"status": r.status_code, "detail": r.json().get("detail")}
        print("no-number:", report["chapter_scope_without_number"])
    finally:
        ai._complete_ex = orig_complete_ex
        db.rollback()
        db.query(StoryMemoryEntry).filter(StoryMemoryEntry.story_id == sid).delete()
        db.commit()
        cleanup_fixture(db, sid, uid)
        db.close()
    out = Path(__file__).parent / "fixtures" / "live_spoiler_boundary_t2a.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print("memory:", report["memory"], "analysis:", report.get("analysis"))


if __name__ == "__main__":
    main()
