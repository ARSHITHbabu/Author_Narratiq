#!/usr/bin/env python3
"""
Stage 12 Tranche 2a — A13 retrieval before/after on live BGE-M3 (+ Qwen summaries).

Builds the shared retrieval fixture on the TEST database, creates real chapter
summaries (so plot importance has data), then for every GROUND_TRUTH question
measures recall@k (was the expected chapter among the retrieved passages?)
for two rankings over the SAME candidate pool:
  before — cosine + capped boost (0.015/event, cap 0.08), no chapter quota
  after  — cosine + near-tie percentile boost (eps 0.02) + chapter quota
           (Plot Assistant Q&A path: diversify_chapters=True)
at chapter caps 3 and 6 and full scope. Also reports the cosine spread of the
candidate pool (to check the 0.02 epsilon) and the distinct chapters covered.

  DATABASE_URL=...narratiq_test python3 tests/measure_plot_retrieval_t2a.py
Writes tests/fixtures/plot_retrieval_t2a.json.
"""
from __future__ import annotations

import asyncio
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def _old_rank(rows, story_id, db, ai):
    boost = ai._plot_importance_by_chapter(story_id, {r.chapter_number for r in rows}, db)
    return sorted(rows, key=lambda r: float(r.score) + boost.get(r.chapter_number, 0.0), reverse=True)


async def main():
    from sqlalchemy import text
    from database import SessionLocal, engine
    from db_safety_guard import allowed_test_dbs, is_allowed_test_db_name
    from services import ai_service as ai
    from tests.fixtures.retrieval_fixture import CHAPTERS, GROUND_TRUTH, build_fixture, cleanup_fixture

    assert is_allowed_test_db_name(engine.url.database, allowed_test_dbs()), engine.url.database
    db = SessionLocal()
    info = await build_fixture(db)
    sid = info["story_id"]
    try:
        for c in CHAPTERS:                                  # real summaries → real importance
            await ai.summarize_and_embed_chapter(info["chapter_ids"][c["number"]], sid, c["number"], c["content"], db)
        report = {"cases": [], "summary": {}}
        for cap in (3, 6, None):
            for gt in GROUND_TRUTH:
                if cap is not None and gt["chapter"] > cap:
                    continue
                q_emb = await ai.embed_text(gt["query"])
                params = {"q": ai.vector_literal(q_emb), "story_id": sid, "limit": 40}
                filt = ""
                if cap is not None:
                    filt, params["max_ch"] = "AND chapter_number <= :max_ch", cap
                rows = db.execute(text(f"""
                    SELECT chunk_id, chapter_number, chunk_index, text, word_count,
                           {ai.vector_similarity('embedding')} AS score
                    FROM chapter_chunks WHERE story_id = :story_id AND embedding IS NOT NULL {filt}
                    ORDER BY {ai.vector_distance('embedding')} LIMIT :limit"""), params).fetchall()
                scores = sorted((float(r.score) for r in rows), reverse=True)
                spread = statistics.pstdev(scores[:30]) if len(scores) > 1 else 0.0
                for k in (6, 10):
                    before = ai._dedupe_chunks_by_content(_old_rank(rows, sid, db, ai), k)
                    raw = ai._plot_importance_raw_by_chapter(sid, {r.chapter_number for r in rows}, db)
                    ranked = ai._rerank_near_ties(rows, raw)
                    use_quota = cap is None or cap > 5
                    after = (ai._select_with_chapter_quota(ai._dedupe_chunks_by_content(ranked, len(ranked)), k)
                             if use_quota else ai._dedupe_chunks_by_content(ranked, k))
                    report["cases"].append({
                        "cap": cap, "k": k, "query": gt["query"], "expected": gt["chapter"],
                        "before_hit": gt["chapter"] in {r.chapter_number for r in before},
                        "after_hit": gt["chapter"] in {r.chapter_number for r in after},
                        "before_chapters": sorted({r.chapter_number for r in before}),
                        "after_chapters": sorted({r.chapter_number for r in after}),
                        "cosine_spread_top30": round(spread, 4),
                        "leak_after": any(cap is not None and r.chapter_number > cap for r in after),
                    })
        for cap in (3, 6, None):
            for k in (6, 10):
                cs = [c for c in report["cases"] if c["cap"] == cap and c["k"] == k]
                if not cs:
                    continue
                report["summary"][f"cap={cap} k={k}"] = {
                    "questions": len(cs),
                    "recall_before": round(sum(c["before_hit"] for c in cs) / len(cs), 3),
                    "recall_after": round(sum(c["after_hit"] for c in cs) / len(cs), 3),
                    "chapters_before": round(statistics.mean(len(c["before_chapters"]) for c in cs), 2),
                    "chapters_after": round(statistics.mean(len(c["after_chapters"]) for c in cs), 2),
                    "leaks_after": sum(c["leak_after"] for c in cs),
                }
        sp = [c["cosine_spread_top30"] for c in report["cases"]]
        report["summary"]["cosine_spread_top30"] = {"median": round(statistics.median(sp), 4),
                                                    "min": min(sp), "max": max(sp), "near_tie_eps": ai._NEAR_TIE_EPS}
        out = Path(__file__).parent / "fixtures" / "plot_retrieval_t2a.json"
        out.write_text(json.dumps(report, indent=2))
        print(json.dumps(report["summary"], indent=2))
    finally:
        cleanup_fixture(db, sid, info["user_id"])
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
