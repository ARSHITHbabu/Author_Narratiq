#!/usr/bin/env python3
"""
Stage 12 A18 — clean-prose baseline for the NON-rewrite AI features.

The Stage 11 legitimate-prose baseline (legit_rewrite_probe.py) covers the
selection rewrites only. Before any output check is added to Q&A, plot
suggestions, writing suggestions or continue, this probe records what those
features return for ORDINARY fiction — including a passage in which a
character says "Ignore your previous instructions" to a ship's computer — so
the check can be replayed against real legitimate outputs first, and re-run
afterwards to count false alarms (refusals or dropped items on clean prose).

Per passage (one story, one indexed chapter each), per run:
  qa         Plot Assistant, chapter scope, a factual question
  creative   Plot Assistant, chapter scope, "what should happen next"
  mixed      Plot Assistant, chapter scope, a question + idea request
  writing    /api/ai/suggestions on the passage
  continue   /api/stories/{id}/chapters/{cid}/continue
Records status, whether the response is an instruction_like_text refusal,
items returned, and the full body.

  DATABASE_URL=...narratiq_test python3 backend/scripts/security/clean_prose_feature_probe.py \\
      --base http://127.0.0.1:8100 --runs 2 --out /tmp/clean_prose.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))
sys.path.insert(0, str(_BACKEND / "scripts" / "perf"))
sys.path.insert(0, str(_BACKEND / "scripts" / "security"))
sys.path.insert(0, str(_BACKEND / "tests"))

import httpx  # noqa: E402

from legit_rewrite_probe import PASSAGES  # noqa: E402  (the Stage 11 legitimate passages)
from load_probe import Fixture, index_story  # noqa: E402

QUESTIONS = {
    "qa": "What happens in this chapter?",
    "creative": "Suggest what should happen next.",
    "mixed": "Who is in this scene, and how could the tension grow?",
}


def _items(feature: str, body: dict) -> int:
    if feature == "writing":
        return len(body.get("suggestions") or [])
    if feature == "continue":
        return len(body.get("suggestions") or [])
    return len(body.get("suggestions") or []) + (1 if body.get("answer") else 0)


async def run(args):
    fx = Fixture()
    rows = []
    try:
        from database import SessionLocal
        from models import Chapter
        async with httpx.AsyncClient(base_url=args.base, timeout=600) as c:
            for pname, text in PASSAGES.items():
                a = fx.author(chapters=1)
                db = SessionLocal()
                db.query(Chapter).filter(Chapter.chapter_id == a["cids"][0]).update({"content": f"<p>{text}</p>"})
                db.commit()
                db.close()
                await index_story(c, a)
                sid, cid, h = a["sid"], a["cids"][0], a["headers"]
                calls = {f: ("/api/plot-assistant/", {"story_id": sid, "question": q, "scope": "chapter",
                                                      "current_chapter_number": 1})
                         for f, q in QUESTIONS.items()}
                calls["writing"] = ("/api/ai/suggestions", {"text": text, "story_id": sid, "chapter_id": cid})
                calls["continue"] = (f"/api/stories/{sid}/chapters/{cid}/continue", {"tail_text": text})
                for feature, (path, body) in calls.items():
                    for i in range(args.runs):
                        r = await c.post(path, json=body, headers=h)
                        j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                        row = {"passage": pname, "feature": feature, "run": i, "status": r.status_code,
                               "refused": isinstance(j, dict) and j.get("code") == "instruction_like_text",
                               "items": _items(feature, j) if r.status_code == 200 else 0,
                               "source": text, "body": j}
                        rows.append(row)
                        print(f"[clean] {pname:10s} {feature:9s} {r.status_code} refused={row['refused']} "
                              f"items={row['items']}", flush=True)
    finally:
        fx.cleanup()
    summary = {"calls": len(rows),
               "ok": sum(r["status"] == 200 for r in rows),
               "refused_false_alarms": sum(r["refused"] for r in rows),
               "other_errors": sum(r["status"] != 200 and not r["refused"] for r in rows),
               "empty_results": sum(r["status"] == 200 and r["items"] == 0 for r in rows)}
    Path(args.out).write_text(json.dumps({"summary": summary, "rows": rows}, indent=2, ensure_ascii=False))
    print("[clean] summary", summary)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8100")
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--out", default="/tmp/narratiq-clean-prose.json")
    asyncio.run(run(ap.parse_args()))
