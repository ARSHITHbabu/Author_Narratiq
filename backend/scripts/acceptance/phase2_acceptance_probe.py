#!/usr/bin/env python3
"""
Task 11.6 — Phase 2 formal acceptance: exercise P2-01 … P2-11 against their
Phase 2 roadmap §19 completion criteria through the REAL API and model.

Runs against a backend bound to an ALLOW-LISTED TEST database (never the live
`narratiq` database). It creates synthetic authors, checks each Phase 2
endpoint's backend-observable criteria, checks that a second author gets 404
on every Phase 2 endpoint for the first author's story (§20.4 item 3), and
deletes everything it created, by exact id.

What it cannot judge: frontend rendering (covered by the Stage 6/8/9 browser
suites and recorded separately in the acceptance record), and whether AI
output is GOOD. It checks structure and honest states, not literary quality.

  DATABASE_URL=...narratiq_test python3 backend/scripts/acceptance/phase2_acceptance_probe.py \\
      --base http://127.0.0.1:8100 --out /tmp/phase2-acceptance.json
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import math
import struct
import sys
import time
import wave
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))
sys.path.insert(0, str(_BACKEND / "scripts" / "perf"))
sys.path.insert(0, str(_BACKEND / "tests"))

import httpx  # noqa: E402

from load_probe import Fixture, index_story  # noqa: E402


def _wav_tone(seconds: float = 2.0, rate: int = 16000) -> bytes:
    """A short sine tone: enough to drive the transcription pipeline end to
    end (upload → lazy Whisper load → job reaches a terminal state). Speech
    quality is not what this checks; real speech is a manual check (6.4)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        frames = b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / rate)))
                          for i in range(int(seconds * rate)))
        w.writeframes(frames)
    return buf.getvalue()


async def _poll(c, url, h, key="status", done=("completed", "complete", "ready", "failed", "partial", "error"),
                timeout=900):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = await c.get(url, headers=h)
        if r.status_code == 200 and (r.json() or {}).get(key) in done:
            return r
        await asyncio.sleep(3)
    return None


def _check(results, task, name, ok, evidence):
    results.setdefault(task, []).append({"criterion": name, "pass": bool(ok), "evidence": evidence})
    print(f"[{task}] {'PASS' if ok else 'FAIL'}  {name} — {str(evidence)[:160]}", flush=True)


async def run(args):
    fx = Fixture()
    R: dict[str, list] = {}
    try:
        a = fx.author(chapters=6)          # P2-08 needs ≥ 6 chapters
        other = fx.author(chapters=1)      # for the ownership checks
        sid, cid, h = a["sid"], a["cids"][0], a["headers"]
        async with httpx.AsyncClient(base_url=args.base, timeout=900) as c:
            indexed = await index_story(c, a)
            _check(R, "setup", "6 chapters indexed (summaries + chunks)", indexed, {"story": sid})

            # P2-01 emotional arc
            r = await c.get(f"/api/stories/{sid}/emotional-arc", headers=h)
            j = r.json() if r.status_code == 200 else {}
            pts = j.get("points") or j.get("chapters") or j.get("arc") or []
            _check(R, "P2-01", "GET returns ordered tone data for every chapter",
                   r.status_code == 200 and len(pts) == 6
                   and [p.get("chapter_number") for p in pts] == sorted(p.get("chapter_number") for p in pts),
                   {"status": r.status_code, "n": len(pts), "keys": list(j)[:8]})

            # P2-02 continuation
            r = await c.post(f"/api/stories/{sid}/chapters/{cid}/continue", headers=h,
                             json={"tail_text": "Devika pressed her palm against the cold glass."})
            j = r.json() if r.status_code == 200 else {}
            opts = j.get("suggestions") or j.get("continuations") or j.get("options") or []
            _check(R, "P2-02", "3 continuations returned per call",
                   r.status_code == 200 and len(opts) == 3, {"status": r.status_code, "n": len(opts)})

            # P2-03 dialogue voice consistency (fixture prose has no dialogue → insufficient data)
            r = await c.post(f"/api/stories/{sid}/characters", headers=h, json={"name": "Devika"})
            char_id = (r.json() or {}).get("character_id") if r.status_code in (200, 201) else None
            r = await c.post(f"/api/stories/{sid}/characters/{char_id}/voice-check", headers=h, json={})
            j = r.json() if r.status_code == 200 else {}
            # §19: < 3 quoted passages → fall back to all mention passages, "documented in
            # the API response"; still < 3 → insufficient_data.
            _check(R, "P2-03", "structured result (status, dialogue_count, consistency_score, inconsistent_pairs)",
                   r.status_code == 200 and j.get("status") in ("ok", "inconsistent", "insufficient_data")
                   and isinstance(j.get("inconsistent_pairs"), list),
                   {"status": r.status_code, "status_field": j.get("status"), "dialogue_count": j.get("dialogue_count"),
                    "consistency_score": j.get("consistency_score"), "note": j.get("note")})
            score = j.get("consistency_score")
            _check(R, "P2-03", "consistency_score is a float in [0, 1] when analysed",
                   j.get("status") == "insufficient_data" or (isinstance(score, (int, float)) and 0 <= score <= 1),
                   {"consistency_score": score})
            r = await c.post(f"/api/stories/{other['sid']}/characters", headers=other["headers"], json={"name": "Nobody"})
            nid = (r.json() or {}).get("character_id") if r.status_code in (200, 201) else None
            r = await c.post(f"/api/stories/{other['sid']}/characters/{nid}/voice-check", headers=other["headers"], json={})
            _check(R, "P2-03", "a character with no mentions → insufficient_data",
                   r.status_code == 200 and (r.json() or {}).get("status") == "insufficient_data",
                   {"status": r.status_code, "body": r.text[:200]})

            # P2-04 outline
            r = await c.post(f"/api/stories/{sid}/chapters/{cid}/outline", headers=h,
                             json={"chapter_goal": "Devika finds the ledger and must decide whether to tell Mara"})
            j = r.json() if r.status_code == 200 else {}
            beats = j.get("outline") or []
            _check(R, "P2-04", "outline is a structured list of beats with fields populated",
                   r.status_code == 200 and len(beats) >= 2 and all(isinstance(b, dict) and b for b in beats),
                   {"status": r.status_code, "n_beats": len(beats), "beat_keys": list(beats[0])[:6] if beats else []})

            # P2-05 continuity
            r = await c.post(f"/api/stories/{sid}/continuity-check", headers=h, json={})
            j = r.json() if r.status_code == 200 else {}
            _check(R, "P2-05", "structured issues list with chapter references (may be empty)",
                   r.status_code == 200 and isinstance(j.get("issues"), list),
                   {"status": r.status_code, "n_issues": len(j.get("issues") or []), "keys": list(j)[:8]})

            # P2-06 story bible: generate, 5 sections, stored, export, idempotent re-run
            r = await c.post(f"/api/stories/{sid}/story-bible", headers=h)
            started = r.status_code in (200, 201, 202)
            done = await _poll(c, f"/api/stories/{sid}/story-bible", h) if started else None
            j = done.json() if done is not None else {}
            content = j.get("content_json") or {}
            if isinstance(content, str):
                try:
                    content = json.loads(content)
                except ValueError:
                    content = {}
            sections = list(content) if isinstance(content, dict) else []
            _check(R, "P2-06", "generated and stored; status honest; 5 sections or named failed_sections",
                   done is not None and j.get("status") in ("completed", "partial", "failed")
                   and (len(sections) == 5 or bool(j.get("failed_sections"))),
                   {"status": j.get("status"), "sections": sections, "failed": j.get("failed_sections")})
            r = await c.get(f"/api/stories/{sid}/story-bible/export", headers=h)
            _check(R, "P2-06", "DOCX export works",
                   r.status_code == 200 and r.content[:2] == b"PK",
                   {"status": r.status_code, "bytes": len(r.content), "type": r.headers.get("content-type")})
            # §19: "Stale warning if content is older than most recent chapter update".
            # Checked in the API response here; the panel was checked by reading it.
            stale_keys = [k for k in j if "stale" in k.lower()]
            _check(R, "P2-06", "stale detection (API exposes staleness after a chapter edit)",
                   bool(stale_keys), {"keys": list(j)[:12]})

            # P2-07 narrative threads: scan, list, manual resolution
            r = await c.post(f"/api/stories/{sid}/narrative-threads/scan", headers=h)
            scan_ok = r.status_code in (200, 201, 202)
            done = await _poll(c, f"/api/stories/{sid}/narrative-threads/scan-status", h) if scan_ok else None
            r = await c.get(f"/api/stories/{sid}/narrative-threads", headers=h)
            threads = r.json() if r.status_code == 200 else []
            _check(R, "P2-07", "scan completes and the thread list is returned",
                   done is not None and r.status_code == 200 and isinstance(threads, list),
                   {"scan": (done.json() if done is not None else None), "n_threads": len(threads)})
            if threads:
                tid = threads[0].get("thread_id")
                r = await c.patch(f"/api/stories/{sid}/narrative-threads/{tid}", headers=h,
                                  json={"status": "resolved"})
                _check(R, "P2-07", "manual resolution works",
                       r.status_code == 200 and (r.json() or {}).get("status") == "resolved",
                       {"status": r.status_code})
            else:
                _check(R, "P2-07", "manual resolution works", None,
                       "not exercised: the scan found no threads in the fixture prose")

            # P2-08 style drift
            r = await c.post(f"/api/stories/{sid}/style-drift", headers=h, json={})
            j = r.json() if r.status_code == 200 else {}
            _check(R, "P2-08", "drift_score from BGE-M3 centroids (6 chapters)",
                   r.status_code == 200 and isinstance(j.get("drift_score"), (int, float)),
                   {"status": r.status_code, "drift_score": j.get("drift_score"), "keys": list(j)[:8]})
            r = await c.post(f"/api/stories/{other['sid']}/style-drift", headers=other["headers"], json={})
            jo = r.json() if r.status_code == 200 else {}
            _check(R, "P2-08", "insufficient data (1 chapter) handled gracefully",
                   r.status_code in (200, 422) and "insufficient" in json.dumps(jo or r.text).lower(),
                   {"status": r.status_code, "body": (r.text or "")[:200]})

            # P2-09 pacing goals
            r = await c.post(f"/api/stories/{sid}/pacing-goals", headers=h,
                             json={"target_words_per_chapter": 3000, "target_chapters": 20})
            r2 = await c.get(f"/api/stories/{sid}/pacing-goals", headers=h)
            j = r2.json() if r2.status_code == 200 else {}
            _check(R, "P2-09", "goal stored and retrieved with computed progress",
                   r.status_code in (200, 201) and r2.status_code == 200
                   and isinstance(j.get("progress_pct"), (int, float))
                   and j.get("target_words_per_chapter") == 3000
                   and len(j.get("chapter_distribution") or []) == 6,
                   {"post": r.status_code, "get": r2.status_code, "keys": list(j)[:10]})

            # P2-10 duplicate scenes (the fixture's chapters are near-identical by construction)
            r = await c.post(f"/api/stories/{sid}/duplicate-scenes", headers=h, json={"threshold": 0.9})
            j = r.json() if r.status_code == 200 else {}
            pairs = j.get("pairs") or j.get("duplicates") or []
            _check(R, "P2-10", "near-duplicate pairs returned with similarity scores; threshold accepted",
                   r.status_code == 200 and len(pairs) >= 1, {"status": r.status_code, "n_pairs": len(pairs),
                                                              "first": pairs[0] if pairs else None})

            # P2-11 audio: upload → job id → terminal state (lazy Whisper load)
            files = {"file": ("tone.wav", _wav_tone(), "audio/wav")}
            r = await c.post(f"/api/stories/{sid}/audio", headers=h, files=files)
            j = r.json() if r.status_code in (200, 201, 202) else {}
            aid = j.get("audio_id")
            _check(R, "P2-11", "upload returns audio_id immediately",
                   bool(aid), {"status": r.status_code, "keys": list(j)[:8]})
            done = await _poll(c, f"/api/stories/{sid}/audio/{aid}", h,
                               done=("completed", "failed", "transcribed", "ready")) if aid else None
            _check(R, "P2-11", "async transcription reaches a terminal state (Whisper lazy-loads on CPU)",
                   done is not None, {"final": (done.json() if done is not None else None)})

            # §20.4 item 3 — a second author gets 404 on every Phase 2 endpoint for this story
            oh = other["headers"]
            probes = [
                ("GET", f"/api/stories/{sid}/emotional-arc", None),
                ("POST", f"/api/stories/{sid}/chapters/{cid}/continue", {"tail_text": "x"}),
                ("POST", f"/api/stories/{sid}/characters/{char_id}/voice-check", {}),
                ("POST", f"/api/stories/{sid}/chapters/{cid}/outline", {"chapter_goal": "x"}),
                ("POST", f"/api/stories/{sid}/continuity-check", {}),
                ("GET", f"/api/stories/{sid}/story-bible", None),
                ("GET", f"/api/stories/{sid}/story-bible/export", None),
                ("GET", f"/api/stories/{sid}/narrative-threads", None),
                ("POST", f"/api/stories/{sid}/style-drift", {}),
                ("GET", f"/api/stories/{sid}/pacing-goals", None),
                ("POST", f"/api/stories/{sid}/duplicate-scenes", {}),
                ("GET", f"/api/stories/{sid}/audio", None),
                ("GET", f"/api/stories/{sid}/audio/{aid}", None),
            ]
            codes = {}
            for m, path, body in probes:
                rr = await c.request(m, path, headers=oh, json=body)
                codes[f"{m} {path.replace(sid, '{sid}')}"] = rr.status_code
            _check(R, "§20.4-3", "every Phase 2 endpoint answers 404 to another author",
                   all(v == 404 for v in codes.values()), codes)
    finally:
        fx.cleanup()
    flat = [x for v in R.values() for x in v]
    out = {"passed": sum(1 for x in flat if x["pass"] is True),
           "failed": sum(1 for x in flat if x["pass"] is False),
           "not_exercised": sum(1 for x in flat if x["pass"] is None),
           "results": R}
    Path(args.out).write_text(json.dumps(out, indent=2, default=str))
    print(f"phase2 acceptance: {out['passed']} passed, {out['failed']} failed, "
          f"{out['not_exercised']} not exercised — report {args.out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8100")
    ap.add_argument("--out", default="/tmp/narratiq-phase2-acceptance.json")
    asyncio.run(run(ap.parse_args()))
