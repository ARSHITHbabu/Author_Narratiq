#!/usr/bin/env python3
"""
Stage 12 Tranche 3 (A20) — MV-5.14-A/B/C, live, scored against the criteria in
docs/testing/manual-verification/stage-05-manual-verification-guide.md
(section C). Nothing here changes those criteria; it runs the procedures and
records the evidence.

  A  Timeline reasoning. Two disposable stories:
       (a) chapters anchored "May 2, 2010", "May 9, 2010", "April 20, 2010",
           no flashback wording;
       (b) the same, but chapter 3 opens "In a flashback to April 20, 2010…"
           and chapter 4 returns to "May 10, 2010".
     Index both, Continuity Check each `--runs` times (guide: 3).
     PASS: (a) a `timeline` finding citing chapters 2 and 3 in >= 2 of 3 runs;
           (b) no timeline finding about chapter 3 in any run.
  B  Narrative reasoning. A disposable 8-chapter story where a named
     character appears in chapters 1–2 and never again. Index, thread scan,
     Manuscript Report, Continuity Check.
     PASS: "Things to check" (narrative_signals) lists the disappearance citing
           chapters 1–2; every continuity finding cites real chapters.
  C  Relationships section on the seed_fixture.py story: index, Manuscript
     Report. PASS: pairs named by current character names, changes in chapter
     order, no raw ids.

The screenshots the guide asks for (B, C) are taken by the browser step, not here.
Disposable authors are created in the allow-listed test database and deleted
afterwards; the seed_fixture.py account is read, indexed and reported on only.

  DATABASE_URL=...narratiq_test python3 backend/scripts/quality/mv514_live.py \\
      --base http://127.0.0.1:8100 --runs 3 --out-dir docs/testing/stage-12/tranche3
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))
sys.path.insert(0, str(_BACKEND / "scripts" / "perf"))
sys.path.insert(0, str(_BACKEND / "scripts" / "security"))
sys.path.insert(0, str(_BACKEND / "tests"))

import httpx  # noqa: E402

from load_probe import Fixture, index_story  # noqa: E402

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)

CH1 = ("<p>On May 2, 2010, Clara Voss opened the bakery on Mercer Street for the first time. "
       "Her brother Felix carried in the flour sacks and promised to help every morning.</p>")
CH2 = ("<p>By May 9, 2010, the bakery had regulars. Felix burned the first batch of rye, and Clara "
       "laughed until she cried. The landlord came by to talk about the rent.</p>")
CH3_PLAIN = ("<p>On April 20, 2010, Clara signed the lease with the landlord and paid the deposit with "
             "her last savings. Felix said the street was too quiet for a bakery.</p>")
CH3_FLASH = ("<p>In a flashback to April 20, 2010, Clara signed the lease with the landlord and paid the "
             "deposit with her last savings. Felix said the street was too quiet for a bakery.</p>")
CH4 = ("<p>On May 10, 2010, Clara and Felix reopened after the storm and sold every loaf of bread "
       "by noon.</p>")

# B: Tobias Wren is present in chapters 1 and 2 only.
B_CHAPTERS = [
    ("Arrival", "<p>Elena Marsh arrived at the mountain observatory with her mentor, Tobias Wren. Tobias "
                "showed her the great telescope and the cracked lens nobody had replaced.</p>"),
    ("The Lens", "<p>Tobias Wren and Elena spent the night measuring the cracked lens. Tobias swore he "
                 "knew who had broken it, but he would not say the name.</p>"),
    ("Snowfall", "<p>Snow closed the pass. Elena catalogued the star charts alone and found a page torn "
                 "from the observatory log.</p>"),
    ("The Courier", "<p>A courier named Ines Calder reached the observatory on skis with supplies. Elena "
                    "asked her about the torn page; Ines only shrugged.</p>"),
    ("Night Watch", "<p>Elena and Ines kept watch through a clear night and recorded a comet the old "
                    "charts never mentioned.</p>"),
    ("The Letter", "<p>Ines gave Elena a sealed letter addressed to the observatory director. Elena read "
                   "it by lamplight and learned the director had sold the telescope.</p>"),
    ("Thaw", "<p>The snow melted. Elena and Ines argued about whether to report the sale or hide the "
             "telescope in the cellar.</p>"),
    ("Departure", "<p>Elena locked the observatory, left the key under the stone, and walked down the "
                  "pass with Ines toward the village.</p>"),
]


async def _continuity(c, a):
    r = await c.post(f"/api/stories/{a['sid']}/continuity-check", json={}, headers=a["headers"], timeout=900)
    return r.status_code, (r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text)


def _set_chapters(a, chapters):
    from database import SessionLocal
    from models import Chapter
    db = SessionLocal()
    for cid, (title, html) in zip(a["cids"], chapters):
        db.query(Chapter).filter(Chapter.chapter_id == cid).update(
            {"content": html, "title": title, "word_count": len(re.sub(r"<[^>]+>", " ", html).split())})
    db.commit(); db.close()


def _summaries(sid):
    from database import SessionLocal
    from models import ChapterSummary
    db = SessionLocal()
    try:
        return [{"chapter": s.chapter_number, "timeline_markers": s.timeline_markers,
                 "characters_present": s.characters_present, "relationship_changes": s.relationship_changes}
                for s in db.query(ChapterSummary).filter(ChapterSummary.story_id == sid)
                .order_by(ChapterSummary.chapter_number).all()]
    finally:
        db.close()


async def mv_a(c, fx, runs):
    out = {}
    for label, chapters, expect in (
        ("a_plain", [("One", CH1), ("Two", CH2), ("Three", CH3_PLAIN)], "reported"),
        ("b_flashback", [("One", CH1), ("Two", CH2), ("Three", CH3_FLASH), ("Four", CH4)], "not_reported"),
    ):
        a = fx.author(chapters=len(chapters))
        _set_chapters(a, chapters)
        indexed = await index_story(c, a)
        rows = []
        for i in range(runs):
            status, body = await _continuity(c, a)
            issues = body.get("issues", []) if isinstance(body, dict) else []
            timeline = [x for x in issues if x.get("type") == "timeline"]
            rows.append({"run": i, "status": status, "issues": issues,
                         "degraded": body.get("degraded") if isinstance(body, dict) else None,
                         "timeline_2_3": any({2, 3} <= set(x.get("chapter_refs") or []) for x in timeline),
                         "timeline_about_3": any(3 in (x.get("chapter_refs") or []) for x in timeline)})
        if expect == "reported":
            hits = sum(r["timeline_2_3"] for r in rows)
            passed = indexed and hits >= 2 and all(r["status"] == 200 for r in rows)
            criterion = f"timeline finding citing chapters 2 and 3 in >= 2 of {runs} runs (got {hits})"
        else:
            hits = sum(r["timeline_about_3"] for r in rows)
            passed = indexed and hits == 0 and all(r["status"] == 200 for r in rows)
            criterion = f"no timeline finding about chapter 3 in any of {runs} runs (got {hits})"
        out[label] = {"indexed": indexed, "summaries": _summaries(a["sid"]), "runs": rows,
                      "criterion": criterion, "pass": passed}
    out["pass"] = all(v["pass"] for v in out.values() if isinstance(v, dict))
    return out


async def _scan(c, a, timeout=900):
    r = await c.post(f"/api/stories/{a['sid']}/narrative-threads/scan", headers=a["headers"])
    if r.status_code not in (200, 202):
        return {"status_code": r.status_code, "body": r.text[:500]}
    t0 = time.time()
    while time.time() - t0 < timeout:
        s = (await c.get(f"/api/stories/{a['sid']}/narrative-threads/scan-status", headers=a["headers"])).json()
        if s.get("status") in ("completed", "completed_empty", "failed"):
            return s
        await asyncio.sleep(3)
    return {"status": "timeout"}


async def mv_b(c, fx):
    a = fx.author(chapters=len(B_CHAPTERS))
    _set_chapters(a, B_CHAPTERS)
    indexed = await index_story(c, a)
    scan = await _scan(c, a)
    rep = await c.post(f"/api/stories/{a['sid']}/manuscript-report", headers=a["headers"], timeout=900)
    report = rep.json() if rep.status_code == 200 else {"status_code": rep.status_code, "body": rep.text[:500]}
    status, cont = await _continuity(c, a)
    signals = report.get("narrative_signals", []) if isinstance(report, dict) else []
    disappearance = [s for s in signals if s.get("kind") == "character_disappearance"
                     and "tobias" in s.get("subject", "").lower()]
    cites_1_2 = any(set(s.get("chapters") or []) == {1, 2} for s in disappearance)
    real = set(range(1, len(B_CHAPTERS) + 1))
    issues = cont.get("issues", []) if isinstance(cont, dict) else []
    bad_refs = [x for x in issues if not (x.get("chapter_refs") and set(x["chapter_refs"]) <= real)]
    signal_no_chapters = [s for s in signals if not s.get("chapters")]
    return {"indexed": indexed, "summaries": _summaries(a["sid"]), "scan": scan,
            "report_status": rep.status_code, "narrative_signals": signals,
            "continuity_status": status, "continuity": cont,
            "checks": {"disappearance_listed_citing_1_2": cites_1_2,
                       "continuity_findings_cite_real_chapters": not bad_refs,
                       "signals_without_chapters": len(signal_no_chapters)},
            "pass": bool(indexed and rep.status_code == 200 and status == 200 and cites_1_2
                         and not bad_refs and not signal_no_chapters),
            "story_id": a["sid"]}


async def mv_c(c, email):
    from database import SessionLocal
    from models import Character, Story, User
    from routers.auth import create_token
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        db.close()
        return {"pass": False, "error": f"fixture account {email!r} not found — run seed_fixture.py first"}
    story = db.query(Story).filter(Story.user_id == user.user_id).order_by(Story.created_at).first()
    names = {ch.name for ch in db.query(Character).filter(Character.story_id == story.story_id).all()}
    from models import Chapter
    cids = [ch.chapter_id for ch in db.query(Chapter).filter(Chapter.story_id == story.story_id).all()]
    db.close()
    a = {"sid": story.story_id, "cids": cids, "headers": {"Authorization": f"Bearer {create_token(user.user_id)}"}}
    indexed = await index_story(c, a)
    rep = await c.post(f"/api/stories/{a['sid']}/manuscript-report", headers=a["headers"], timeout=900)
    report = rep.json() if rep.status_code == 200 else {}
    arcs = report.get("relationship_arcs", [])
    raw_ids = [x for x in arcs if _UUID.search(json.dumps(x))]
    unknown_names = [x["characters"] for x in arcs if not set(x.get("characters") or []) <= names]
    out_of_order = [x["characters"] for x in arcs
                    if [ch.get("chapter") for ch in x.get("changes", [])]
                    != sorted(ch.get("chapter") for ch in x.get("changes", []))]
    return {"indexed": indexed, "story_id": a["sid"], "report_status": rep.status_code,
            "character_names": sorted(names), "relationship_arcs": arcs,
            "summaries": _summaries(a["sid"]),
            "checks": {"pairs": len(arcs), "raw_ids": len(raw_ids), "names_not_current": unknown_names,
                       "changes_out_of_order": out_of_order},
            "pass": bool(indexed and rep.status_code == 200 and arcs and not raw_ids
                         and not unknown_names and not out_of_order)}


async def run(args):
    from probe_meta import run_metadata
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fx = Fixture()
    results = {}
    try:
        async with httpx.AsyncClient(base_url=args.base, timeout=900) as c:
            if "A" in args.only:
                results["MV-5.14-A"] = await mv_a(c, fx, args.runs)
                print("[mv514] A pass:", results["MV-5.14-A"]["pass"], flush=True)
            if "B" in args.only:
                results["MV-5.14-B"] = await mv_b(c, fx)
                print("[mv514] B pass:", results["MV-5.14-B"]["pass"], results["MV-5.14-B"]["checks"], flush=True)
            if "C" in args.only:
                results["MV-5.14-C"] = await mv_c(c, args.fixture_email)
                print("[mv514] C pass:", results["MV-5.14-C"]["pass"], results["MV-5.14-C"].get("checks"), flush=True)
    finally:
        if not args.keep:
            fx.cleanup()
    for key, val in results.items():
        (out_dir / f"{key.lower()}.json").write_text(
            json.dumps({"run_metadata": run_metadata(), **val}, indent=2, ensure_ascii=False, default=str))
    print(json.dumps({k: v["pass"] for k, v in results.items()}))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8100")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--only", default="ABC")
    ap.add_argument("--keep", action="store_true", help="keep B's story for the screenshot step")
    ap.add_argument("--fixture-email", default=os.environ.get("FIXTURE_EMAIL", "e2e-fixture@narratiq-internal-test.com"))
    ap.add_argument("--out-dir", default="/tmp/narratiq-mv514")
    asyncio.run(run(ap.parse_args()))
