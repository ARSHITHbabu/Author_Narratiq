#!/usr/bin/env python3
"""
Stage 11 — Phase 2 rule R7 ("a 3-chapter manuscript and a 200-chapter
manuscript must both work without errors") at the 200-chapter end.

Seeds ONE synthetic 200-chapter story in an allow-listed TEST database:
varied chapter prose, chapter summaries and paragraph chunks, embedded with the
real in-process BGE-M3 (the LLM summarisation step is skipped: 200 summaries
through Qwen would take ~40 minutes and is not what R7 tests). Then calls every
Phase 2 feature through the real API and model and records status, latency and
the honesty flags each returns. The story is deleted afterwards.

Latency matters because the production proxy (Cloudflare in front of RunPod)
closes requests at about 100 s. A synchronous endpoint slower than that fails
for the author even if the backend finishes.

  DATABASE_URL=...narratiq_test python3 backend/scripts/acceptance/large_manuscript_probe.py \\
      --base http://127.0.0.1:8100 --chapters 200 --out /tmp/large.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
import time
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))
sys.path.insert(0, str(_BACKEND / "scripts" / "perf"))
sys.path.insert(0, str(_BACKEND / "tests"))

import httpx  # noqa: E402

from load_probe import Fixture  # noqa: E402

PEOPLE = ["Devika", "Mara", "Sant", "Oriel", "Teodor", "Anna", "Halden", "Kira"]
PLACES = ["the lighthouse", "the harbour", "the archive", "the old mill", "the chapel", "the ferry",
          "the market", "the observatory"]
OBJECTS = ["the ledger", "a brass key", "the torn map", "a sealed letter", "the lantern", "a silver coin"]
TONES = ["tense", "hopeful", "grieving", "joyful", "fearful", "calm", "angry", "bittersweet"]
ACTS = ["argued about", "searched for", "hid", "lost", "found", "burned", "copied", "returned"]


def chapter_text(n: int, rng: random.Random) -> tuple[str, dict]:
    a, b = rng.sample(PEOPLE, 2)
    place, obj, act, tone = rng.choice(PLACES), rng.choice(OBJECTS), rng.choice(ACTS), rng.choice(TONES)
    paras = []
    for i in range(6):
        paras.append(
            f"In chapter {n}, {a} reached {place} before dawn. {b} had {act} {obj} the night before, and "
            f"the whole town seemed to know it. \"We cannot stay here,\" {a} said, watching the water. "
            f"{b} answered that the {obj.split()[-1]} mattered more than either of them. The mood was {tone}, "
            f"and by the time the bells rang the two of them had decided to go on together. (part {i + 1})"
        )
    summary = {
        "key_events": [f"{a} reaches {place}", f"{b} {act} {obj}"],
        "characters_present": [a, b],
        "locations": [place.replace("the ", "").title()],
        "emotional_tone": tone,
        "chapter_purpose": "advance the search",
        "raw_summary": f"Chapter {n}: {a} and {b} at {place}; {b} {act} {obj}; mood {tone}.",
    }
    return "".join(f"<p>{p}</p>" for p in paras), summary


def seed(n_chapters: int) -> dict:
    from database import SessionLocal
    from models import Chapter, ChapterChunk, ChapterSummary, Character
    from services.ai_service import embed_text_sync

    fx = Fixture()
    a = fx.author(chapters=0)
    db = SessionLocal()
    rng = random.Random(7)
    t0 = time.time()
    cids = []
    for n in range(1, n_chapters + 1):
        html, s = chapter_text(n, rng)
        ch = Chapter(story_id=a["sid"], title=f"Chapter {n}", chapter_number=n, content=html,
                     word_count=len(html.split()))
        db.add(ch); db.flush()
        cids.append(ch.chapter_id)
        plain = html.replace("<p>", "").replace("</p>", "\n")
        db.add(ChapterSummary(chapter_id=ch.chapter_id, story_id=a["sid"], chapter_number=n,
                              embedding=embed_text_sync(s["raw_summary"]), **s))
        paras = [p for p in plain.split("\n") if p.strip()]
        for idx, start in enumerate(range(0, len(paras), 3)):
            text = " ".join(paras[start:start + 3])
            db.add(ChapterChunk(chapter_id=ch.chapter_id, story_id=a["sid"], chapter_number=n,
                                chunk_index=idx, text=text, word_count=len(text.split()),
                                embedding=embed_text_sync(text)))
        if n % 25 == 0:
            db.commit()
            print(f"[seed] {n}/{n_chapters} chapters ({time.time() - t0:.0f}s)", flush=True)
    for name in PEOPLE:
        db.add(Character(story_id=a["sid"], user_id=a["uid"], name=name, aliases=[]))
    db.commit(); db.close()
    a["cids"] = cids
    a["fixture"] = fx
    return a


async def timed(c, method, path, h, **kw):
    t = time.time()
    r = await c.request(method, path, headers=h, **kw)
    return r, round(time.time() - t, 1)


async def poll(c, url, h, done, key="status", timeout=1800):
    t = time.time()
    while time.time() - t < timeout:
        r = await c.get(url, headers=h)
        if r.status_code == 200 and (r.json() or {}).get(key) in done:
            return r, round(time.time() - t, 1)
        await asyncio.sleep(5)
    return None, round(time.time() - t, 1)


async def run(args):
    a = seed(args.chapters)
    # Character mentions, as chapter indexing does (the voice check reads them).
    from database import SessionLocal
    from services.ai_service import index_character_mentions
    db = SessionLocal()
    t0 = time.time()
    for n, cid in enumerate(a["cids"], 1):
        await index_character_mentions(cid, a["sid"], n, db)
    db.close()
    print(f"[seed] mentions indexed ({time.time() - t0:.0f}s)", flush=True)
    sid, h, last = a["sid"], a["headers"], a["cids"][-1]
    out: dict[str, dict] = {"chapters": args.chapters}
    try:
        async with httpx.AsyncClient(base_url=args.base, timeout=1800) as c:
            r = await c.get(f"/api/stories/{sid}/characters", headers=h)
            char_id = next((x["character_id"] for x in (r.json() or []) if x.get("name") == "Devika"), None)
            sync = [
                ("P2-01 emotional-arc", "GET", f"/api/stories/{sid}/emotional-arc", None),
                ("P2-02 continue", "POST", f"/api/stories/{sid}/chapters/{last}/continue",
                 {"tail_text": "Devika watched the water."}),
                ("P2-03 voice-check", "POST", f"/api/stories/{sid}/characters/{char_id}/voice-check", {}),
                ("P2-04 outline", "POST", f"/api/stories/{sid}/chapters/{last}/outline",
                 {"chapter_goal": "Devika and Mara finally reach the ferry at dawn and decide whether to cross"}),
                ("P2-05 continuity", "POST", f"/api/stories/{sid}/continuity-check", {}),
                ("P2-08 style-drift", "POST", f"/api/stories/{sid}/style-drift", {}),
                ("P2-09 pacing-goals", "POST", f"/api/stories/{sid}/pacing-goals",
                 {"target_words_per_chapter": 3000, "target_chapters": 220}),
                ("P2-10 duplicate-scenes", "POST", f"/api/stories/{sid}/duplicate-scenes", {"threshold": 0.95}),
            ]
            for name, m, path, body in sync:
                r, secs = await timed(c, m, path, h, json=body)
                j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                out[name] = {"status": r.status_code, "seconds": secs, "over_100s_proxy_limit": secs > 100,
                             "degraded": j.get("degraded") if isinstance(j, dict) else None,
                             "note": (j.get("note") or j.get("degraded_reason")) if isinstance(j, dict) else None,
                             "chapters_scanned": j.get("chapters_scanned") if isinstance(j, dict) else None,
                             "voice_status": j.get("status") if isinstance(j, dict) else None,
                             "dialogue_count": j.get("dialogue_count") if isinstance(j, dict) else None,
                             "outline_beats": len(j.get("outline") or []) if isinstance(j, dict) else None}
                print(f"[large] {name:24s} {r.status_code} {secs}s", flush=True)
            # background jobs
            r = await c.post(f"/api/stories/{sid}/story-bible", headers=h)
            done, secs = await poll(c, f"/api/stories/{sid}/story-bible", h, ("completed", "partial", "failed"))
            j = done.json() if done is not None else {}
            out["P2-06 story-bible"] = {"start": r.status_code, "seconds": secs, "status": j.get("status"),
                                        "failed_sections": j.get("failed_sections")}
            print(f"[large] P2-06 story-bible  {j.get('status')} {secs}s", flush=True)
            r = await c.post(f"/api/stories/{sid}/narrative-threads/scan", headers=h)
            done, secs = await poll(c, f"/api/stories/{sid}/narrative-threads/scan-status", h,
                                    ("completed", "completed_empty", "failed", "partial", "error"))
            j = done.json() if done is not None else {}
            out["P2-07 thread-scan"] = {"start": r.status_code, "seconds": secs, "status": j.get("status"),
                                        "chapters_scanned": j.get("chapters_scanned"),
                                        "batches_degraded": j.get("batches_degraded")}
            print(f"[large] P2-07 thread-scan  {j.get('status')} {secs}s", flush=True)
    finally:
        a["fixture"].cleanup()
    Path(args.out).write_text(json.dumps(out, indent=2))
    print("[large] report", args.out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8100")
    ap.add_argument("--chapters", type=int, default=200)
    ap.add_argument("--out", default="/tmp/narratiq-large-manuscript.json")
    asyncio.run(run(ap.parse_args()))
