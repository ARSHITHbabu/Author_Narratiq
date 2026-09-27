#!/usr/bin/env python3
"""
Stage 9 task 9.3 — behaviour at the 60-chapter plot-hole cap (decision D-8).

Seeds two synthetic stories in an ALLOW-LISTED TEST database with realistic
chapter summaries (the input plot-hole detection reads — no chapter indexing or
model call needed to build them): one with exactly 60 chapters, one with 61.
Then calls POST /api/stories/{id}/plot-holes on a running backend bound to the
same database and records latency, status, chapters analysed, and whether the
cap note is shown to the author for the 61-chapter story.

  DATABASE_URL=...narratiq_test python3 backend/scripts/perf/plot_hole_cap_probe.py \
      --base http://127.0.0.1:8100 --out /tmp/plot-hole-cap.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))
sys.path.insert(0, str(_BACKEND / "tests"))
sys.path.insert(0, str(_BACKEND / "scripts" / "perf"))

import httpx  # noqa: E402

from load_probe import Fixture  # noqa: E402

NAMES = ["Devika", "Mara", "Sant", "Vance", "Oriel", "Hessa"]
PLACES = ["the archive", "the harbour", "Coopers Row", "the Bureau", "the lighthouse"]


def _seed_summaries(db, story_id: str, chapter_ids: list[str]) -> None:
    from models import ChapterSummary
    for i, cid in enumerate(chapter_ids, start=1):
        a, b = NAMES[i % len(NAMES)], NAMES[(i + 2) % len(NAMES)]
        db.add(ChapterSummary(
            chapter_id=cid, story_id=story_id, chapter_number=i,
            key_events=[f"{a} questions {b} about the second contract at {PLACES[i % len(PLACES)]}",
                        f"{b} admits a memory was taken as payment in chapter {max(1, i - 3)}",
                        f"{a} decides to confront the Bureau before the settlement day"],
            characters_present=[a, b], locations=[PLACES[i % len(PLACES)]],
            timeline_markers=[f"day {i * 2}"], emotional_tone="tense",
            chapter_purpose=f"Raise the stakes of the forged contract (chapter {i}).",
            raw_summary=(f"In chapter {i}, {a} and {b} meet at {PLACES[i % len(PLACES)]}. "
                         "The forged contract resurfaces and the debt grows heavier."),
        ))
    db.commit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8100")
    ap.add_argument("--out", default="/tmp/narratiq-plot-hole-cap.json")
    args = ap.parse_args()
    fx = Fixture()
    report = {}
    try:
        with httpx.Client(base_url=args.base, timeout=1200) as c:
            for n in (60, 61):
                a = fx.author(chapters=n)
                _seed_summaries(fx.db, a["sid"], a["cids"])
                t = time.perf_counter()
                r = c.post(f"/api/stories/{a['sid']}/plot-holes", headers=a["headers"])
                ms = round((time.perf_counter() - t) * 1000)
                body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                note = json.dumps(body)[:4000]
                report[str(n)] = {
                    "status": r.status_code, "latency_ms": ms,
                    "chapters_analyzed": body.get("chapters_analyzed"),
                    "issues": len(body.get("issues", []) or []),
                    "cap_note_shown": "60-chapter cap" in note,
                    "detail": body.get("detail") if r.status_code >= 400 else None,
                }
                print(f"[plot-hole-cap] {n} chapters: {report[str(n)]}", flush=True)
    finally:
        fx.cleanup()
    Path(args.out).write_text(json.dumps(report, indent=2))
    print(f"report: {args.out}")


if __name__ == "__main__":
    main()
