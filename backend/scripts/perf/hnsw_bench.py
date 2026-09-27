#!/usr/bin/env python3
"""
Stage 9 task 9.3 — pgvector HNSW latency AND correctness at realistic corpus size.

Builds a synthetic multi-author corpus in an ALLOW-LISTED TEST database
(random unit vectors, 1024-dim — HNSW cost depends on row count and dimension,
not on meaning), then runs the exact retrieval SQL shape used by
`ai_service` (`WHERE story_id = :sid … ORDER BY embedding <=> :q LIMIT k`) and
reports, per target story size:

  * latency p50/p95 through the HNSW index (as the app runs it);
  * rows returned vs k — a filtered HNSW scan can return FEWER than k rows when
    the target story is a small fraction of the index (pgvector's
    `hnsw.ef_search` candidate list is filled with other stories' rows first);
  * recall@k against exact search (index disabled) for the same query.

Everything created belongs to one synthetic user and is deleted afterwards.

  DATABASE_URL=...narratiq_test python3 backend/scripts/perf/hnsw_bench.py \
      --stories 100 --chunks 580 --out /tmp/hnsw.json
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
import uuid
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))
sys.path.insert(0, str(_BACKEND / "tests"))

from sqlalchemy import text  # noqa: E402

from db_safety_guard import allowed_test_dbs, is_allowed_test_db_name  # noqa: E402

DIM = 1024
SQL = text("""
    SELECT chunk_id FROM chapter_chunks
    WHERE story_id = :sid AND embedding IS NOT NULL
    ORDER BY embedding <=> CAST(:q AS vector)
    LIMIT :k
""")


def _unit(rng) -> list[float]:
    v = [rng.gauss(0, 1) for _ in range(DIM)]
    n = sum(x * x for x in v) ** 0.5
    return [x / n for x in v]


def _vec(v) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stories", type=int, default=100)
    ap.add_argument("--chunks", type=int, default=580, help="chunks per filler story (~200k words)")
    ap.add_argument("--small", type=int, default=20, help="chunks in the small target story")
    ap.add_argument("--k", type=int, default=8)
    ap.add_argument("--queries", type=int, default=50)
    ap.add_argument("--out", default="/tmp/narratiq-hnsw.json")
    args = ap.parse_args()

    from database import SessionLocal, engine
    from models import Chapter, Story, User
    from routers.auth import hash_password
    if not is_allowed_test_db_name(engine.url.database, allowed_test_dbs()):
        sys.exit(f"refusing: {engine.url.database!r} is not an allow-listed test database")

    rng = random.Random(9)
    db = SessionLocal()
    user = User(email=f"hnsw-{uuid.uuid4().hex[:8]}@narratiq-internal-test.com",
                username=f"hnsw{uuid.uuid4().hex[:8]}", hashed_password=hash_password("x"))
    db.add(user); db.commit()
    report = {"stories": args.stories, "chunks_per_story": args.chunks, "k": args.k}
    try:
        def make_story(n_chunks: int) -> str:
            s = Story(user_id=user.user_id, title="hnsw bench")
            db.add(s); db.flush()
            ch = Chapter(story_id=s.story_id, title="c", chapter_number=1, content="")
            db.add(ch); db.flush()
            rows = [{"id": str(uuid.uuid4()), "cid": ch.chapter_id, "sid": s.story_id, "i": i,
                     "e": _vec(_unit(rng))} for i in range(n_chunks)]
            for j in range(0, len(rows), 500):
                db.execute(text("""INSERT INTO chapter_chunks
                    (chunk_id, chapter_id, story_id, chapter_number, chunk_index, text, word_count, embedding, character_ids)
                    VALUES (:id, :cid, :sid, 1, :i, 'synthetic', 350, CAST(:e AS vector), '[]')"""), rows[j:j + 500])
            db.commit()
            return s.story_id

        t0 = time.time()
        big = make_story(args.chunks)
        small = make_story(args.small)
        for i in range(args.stories - 2):
            make_story(args.chunks)
            if i % 10 == 0:
                print(f"  corpus: {i + 2}/{args.stories} stories", flush=True)
        total = db.execute(text("SELECT count(*) FROM chapter_chunks WHERE embedding IS NOT NULL")).scalar()
        db.execute(text("ANALYZE chapter_chunks")); db.commit()
        report["total_indexed_chunks"] = total
        report["build_seconds"] = round(time.time() - t0, 1)
        report["ef_search"] = db.execute(text("SHOW hnsw.ef_search")).scalar()
        try:
            report["iterative_scan"] = db.execute(text("SHOW hnsw.iterative_scan")).scalar()
        except Exception:
            db.rollback(); report["iterative_scan"] = "unsupported"
        plan = db.execute(text("EXPLAIN " + SQL.text), {"sid": big, "q": _vec(_unit(rng)), "k": args.k}).fetchall()
        report["plan"] = [r[0] for r in plan]

        for label, sid, size in (("large_story", big, args.chunks), ("small_story", small, args.small)):
            lat, counts, recalls = [], [], []
            for _ in range(args.queries):
                q = _vec(_unit(rng))
                t = time.perf_counter()
                got = [r[0] for r in db.execute(SQL, {"sid": sid, "q": q, "k": args.k})]
                lat.append((time.perf_counter() - t) * 1000)
                counts.append(len(got))
                db.execute(text("SET LOCAL enable_indexscan = off"))
                exact = [r[0] for r in db.execute(SQL, {"sid": sid, "q": q, "k": args.k})]
                db.rollback()
                recalls.append(len(set(got) & set(exact)) / max(1, len(exact)))
            s = sorted(lat)
            report[label] = {
                "chunks": size, "p50_ms": round(statistics.median(s), 2),
                "p95_ms": round(s[int(0.95 * (len(s) - 1))], 2),
                "min_rows_returned": min(counts), "mean_rows_returned": round(statistics.mean(counts), 2),
                "mean_recall_at_k": round(statistics.mean(recalls), 3),
            }
            print(f"[hnsw] {label}: {report[label]}", flush=True)
    finally:
        db.rollback()
        db.execute(text("DELETE FROM chapter_chunks WHERE story_id IN (SELECT story_id FROM stories WHERE user_id = :u)"),
                   {"u": user.user_id})
        db.execute(text("DELETE FROM chapters WHERE story_id IN (SELECT story_id FROM stories WHERE user_id = :u)"),
                   {"u": user.user_id})
        db.execute(text("DELETE FROM stories WHERE user_id = :u"), {"u": user.user_id})
        db.execute(text("DELETE FROM users WHERE user_id = :u"), {"u": user.user_id})
        db.commit()
        db.close()
    Path(args.out).write_text(json.dumps(report, indent=2))
    print(f"report: {args.out}")


if __name__ == "__main__":
    main()
