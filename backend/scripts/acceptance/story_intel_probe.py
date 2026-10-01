#!/usr/bin/env python3
"""
Stage 11 — Story Intelligence works end to end against the REAL model.

Creates a synthetic author with a short, realistic three-chapter story, two
characters and a relationship in an allow-listed TEST database. It triggers a
full analysis (P01–P29) through the API, polls the job to its end, then reads
the results back through the public endpoints and checks they hold real
content (not the empty shells a failed pass used to leave). Everything created
is deleted afterwards.

  DATABASE_URL=...narratiq_test python3 backend/scripts/acceptance/story_intel_probe.py \\
      --base http://127.0.0.1:8100 --out /tmp/intel.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))
sys.path.insert(0, str(_BACKEND / "scripts" / "perf"))
sys.path.insert(0, str(_BACKEND / "tests"))

import httpx  # noqa: E402

from load_probe import Fixture  # noqa: E402

CHAPTERS = [
    ("The Lamp Room",
     "<p>Devika had kept the lighthouse on Carrow Point for nine years, and in all that time the lamp had "
     "never once gone dark. Tonight it had. She climbed the iron stairs with a hand lamp, counting each step "
     "the way her father had taught her, and found the lamp room empty, the great lens cold, and the keeper's "
     "logbook torn in half.</p><p>\"Someone was here,\" she said aloud, to no one. The missing pages were the "
     "ones from the week the Marisol went down.</p>"),
    ("The Ledger",
     "<p>Mara ran the harbour office and trusted no one, least of all Devika, whose father had testified at "
     "the inquiry. But when Devika laid the torn logbook on her desk, Mara went pale. \"These dates match my "
     "ledger,\" she said. \"Two shipments that never arrived. Somebody paid to keep the light dark.\"</p>"
     "<p>They agreed, reluctantly, to search the archive together. Neither of them mentioned the inquiry.</p>"),
    ("The Archive",
     "<p>The archive smelled of salt and mould. In a crate marked with the Marisol's name they found the "
     "missing pages, and with them a letter in Devika's father's hand: he had known the light would fail. "
     "Devika read it twice, then folded it into her coat. \"You can't hide that,\" Mara said quietly. "
     "Devika did not answer. Outside, the storm was coming in from the west.</p>"),
]


def seed() -> dict:
    from database import SessionLocal
    from models import Chapter, Character, CharacterRelationship, Story

    fx = Fixture()
    a = fx.author(chapters=0)
    db = SessionLocal()
    s = db.query(Story).filter_by(story_id=a["sid"]).one()
    s.description = "A lighthouse keeper and a harbour clerk uncover who let a ship sink."
    for n, (title, html) in enumerate(CHAPTERS, 1):
        db.add(Chapter(story_id=a["sid"], title=title, chapter_number=n, content=html,
                       word_count=len(html.split())))
    dev = Character(story_id=a["sid"], user_id=a["uid"], name="Devika", aliases=[], role="protagonist")
    mara = Character(story_id=a["sid"], user_id=a["uid"], name="Mara", aliases=[], role="supporting")
    db.add_all([dev, mara]); db.flush()
    db.add(CharacterRelationship(story_id=a["sid"], from_character_id=dev.character_id,
                                 to_character_id=mara.character_id, relationship_type="rival",
                                 description="Distrust from the inquiry, forced into alliance"))
    db.commit(); db.close()
    a["fixture"] = fx
    return a


def run(args) -> int:
    a = seed()
    sid, h = a["sid"], a["headers"]
    out: dict = {}
    try:
        with httpx.Client(base_url=args.base, timeout=120) as c:
            t0 = time.time()
            # --voice-style sends exactly what the voice action sends: passes=[]
            r = c.post(f"/api/stories/{sid}/intelligence/analyze", headers=h,
                       json={"passes": [], "force_refresh": False} if args.voice_style else {})
            job = r.json()
            out["trigger"] = {"status": r.status_code, "job_status": job.get("status")}
            jid = job.get("job_id")
            while time.time() - t0 < 1800:
                j = c.get(f"/api/stories/{sid}/intelligence/jobs/{jid}", headers=h).json()
                if j.get("status") in ("complete", "complete_with_errors", "failed", "error"):
                    break
                time.sleep(5)
            out["job"] = {k: j.get(k) for k in ("status", "passes_completed", "passes_failed", "error_message")}
            out["seconds"] = round(time.time() - t0, 1)
            print(f"[intel] job {j.get('status')} in {out['seconds']}s — failed={j.get('passes_failed')}", flush=True)
            checks = {}
            for ep in ("genre", "dna", "audience", "themes", "conflicts", "world", "structure", "emotional-arc",
                       "pacing", "strengths", "risks", "characters", "relationships", "timeline", "memory", "graph"):
                rr = c.get(f"/api/stories/{sid}/intelligence/{ep}", headers=h)
                body = rr.json() if rr.headers.get("content-type", "").startswith("application/json") else None
                text = json.dumps(body) if body is not None else ""
                checks[ep] = {"status": rr.status_code, "bytes": len(text), "sample": text[:700],
                              "mentions_story": any(w in text for w in ("Devika", "Mara", "lighthouse", "Marisol",
                                                                        "harbour", "archive", "ledger"))}
                print(f"[intel] GET {ep:14s} {rr.status_code} bytes={len(text)} "
                      f"mentions_story={checks[ep]['mentions_story']}", flush=True)
            out["reads"] = checks
    finally:
        a["fixture"].cleanup()
    Path(args.out).write_text(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8100")
    ap.add_argument("--out", default="/tmp/narratiq-story-intel.json")
    ap.add_argument("--voice-style", action="store_true", help="trigger with passes=[] like the voice action")
    sys.exit(run(ap.parse_args()))
