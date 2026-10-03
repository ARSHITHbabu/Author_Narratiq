#!/usr/bin/env python3
"""
Stage 12.1 — PA-C6 (context prioritisation) / PA-H12 (plot importance) on a
realistic long manuscript (the A13 follow-up: the 6-chapter fixture saturates).

Fixture: tests/fixtures/long_manuscript_pa.json (40 chapters, ~32k words,
model-written prose with PLANTED critical and decoy paragraphs; ground truth in
long_manuscript_spec.py). Indexed with the production summariser/embedder, then
every scenario is retrieved through the PRODUCTION Plot Assistant Q&A path:
`retrieve_chunks_from_store(top_k=6 if a character is named else 10,
diversify_chapters=True)`, with the production name detector deciding top_k.

Acceptance (fixed before running, from task 4.3's own wording):
  A  the planted critical passage is among the passages delivered to the model
     ("known plot-critical passages appear in the top results")
  B  it is ranked above every planted decoy that was delivered
     ("the highest-ranked evidence is the most relevant evidence")
Scopes: full manuscript, and capped at the critical chapter (an author asking
while working in that chapter; D-1 default scope).

  DATABASE_URL=...narratiq_test python3 tests/measure_long_manuscript_ranking.py out.json [--keep]
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures"))

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "long_manuscript_pa.json"


async def build(db):
    from models import Chapter, Character, Story, User
    from routers.auth import hash_password
    data = json.loads(FIXTURE.read_text())
    tag = uuid.uuid4().hex[:8]
    u = User(email=f"long-ms-{tag}@narratiq-internal-test.com", username=f"longms{tag}",
             hashed_password=hash_password(uuid.uuid4().hex))
    db.add(u); db.flush()
    s = Story(user_id=u.user_id, title=data["title"])
    db.add(s); db.flush()
    chapters = []
    for c in data["chapters"]:
        html = "".join(f"<p>{p}</p>" for p in c["paragraphs"])
        ch = Chapter(story_id=s.story_id, title=c["title"], chapter_number=c["number"], content=html,
                     word_count=sum(len(p.split()) for p in c["paragraphs"]))
        db.add(ch); chapters.append(ch)
    for name, role in data["characters"]:
        db.add(Character(story_id=s.story_id, user_id=u.user_id, name=name, role=role))
    db.commit()
    return u.user_id, s.story_id, [(ch.chapter_id, ch.chapter_number, ch.content) for ch in chapters], data["words"]


async def index(story_id, chapters):
    from database import SessionLocal
    from services import ai_service as ai
    sem = asyncio.Semaphore(4)

    async def one(cid, n, html):
        async with sem:
            db = SessionLocal()
            try:
                await ai.summarize_and_embed_chapter(cid, story_id, n, html, db)
            finally:
                db.close()
    await asyncio.gather(*[one(*c) for c in chapters])


async def measure(db, story_id):
    from models import Character
    from services.ai_service import retrieve_chunks_from_store
    from services.character_names import detect_named_characters
    from long_manuscript_spec import SCENARIOS
    chars = db.query(Character).filter(Character.story_id == story_id).all()
    rows = []
    for sc in SCENARIOS:
        top_k = 6 if detect_named_characters(sc["query"], chars) else 10
        for scope, cap in (("full", None), ("capped_at_critical", sc["critical"]["chapter"])):
            t0 = time.perf_counter()
            got = await retrieve_chunks_from_store(sc["query"], story_id, db, top_k=top_k,
                                                   max_chapter_number=cap, diversify_chapters=True)
            ms = round((time.perf_counter() - t0) * 1000)
            crit_rank = next((i + 1 for i, g in enumerate(got) if sc["critical"]["key"] in g["text"]), None)
            decoys = [d for d in sc["decoys"] if cap is None or d["chapter"] <= cap]
            decoy_ranks = {d["key"][:40]: next((i + 1 for i, g in enumerate(got) if d["key"] in g["text"]), None)
                           for d in decoys}
            above = [k for k, r in decoy_ranks.items() if r is not None and (crit_rank is None or r < crit_rank)]
            rows.append({
                "id": sc["id"], "kind": sc["kind"], "scope": scope, "query": sc["query"], "top_k": top_k,
                "critical_chapter": sc["critical"]["chapter"], "critical_rank": crit_rank,
                "A_delivered": crit_rank is not None, "B_above_all_decoys": crit_rank is not None and not above,
                "decoys_above_critical": above, "decoy_ranks": decoy_ranks,
                "delivered_chapters": [g["chapter"] for g in got], "scores": [g["score"] for g in got],
                "latency_ms": ms,
            })
            print(f"{sc['id']:16s} {scope:19s} k={top_k:2d} crit_rank={crit_rank} A={crit_rank is not None} "
                  f"B={rows[-1]['B_above_all_decoys']} decoys_above={len(above)} {ms}ms", flush=True)
    return rows


async def main(out: str, keep: bool):
    from database import SessionLocal, engine
    from db_safety_guard import allowed_test_dbs, is_allowed_test_db_name
    assert is_allowed_test_db_name(engine.url.database, allowed_test_dbs()), engine.url.database
    db = SessionLocal()
    uid, sid, chapters, words = await build(db)
    try:
        t0 = time.perf_counter()
        await index(sid, chapters)
        index_s = round(time.perf_counter() - t0)
        from sqlalchemy import text
        n_chunks = db.execute(text("select count(*) from chapter_chunks where story_id=:s"), {"s": sid}).scalar()
        rows = await measure(db, sid)
        summary = {}
        for scope in ("full", "capped_at_critical"):
            r = [x for x in rows if x["scope"] == scope]
            summary[scope] = {"A_delivered": f"{sum(x['A_delivered'] for x in r)}/{len(r)}",
                              "B_above_all_decoys": f"{sum(x['B_above_all_decoys'] for x in r)}/{len(r)}",
                              "critical_rank_1": f"{sum(x['critical_rank'] == 1 for x in r)}/{len(r)}",
                              "median_latency_ms": sorted(x["latency_ms"] for x in r)[len(r) // 2]}
        report = {"manuscript": {"chapters": len(chapters), "words": words, "chunks": n_chunks,
                                 "index_seconds": index_s}, "summary": summary, "rows": rows}
        Path(out).write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print(json.dumps({"manuscript": report["manuscript"], "summary": summary}, indent=2))
    finally:
        if not keep:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from test_cross_user_isolation import _delete_owned
            _delete_owned(db, {uid})
        db.close()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], "--keep" in sys.argv))
