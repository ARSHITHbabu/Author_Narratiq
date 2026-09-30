#!/usr/bin/env python3
"""
Stage 9 task 9.3 — performance baseline probe (production gap PG-12).

Measures, against a running backend that is bound to an ALLOW-LISTED TEST
database (never the live `narratiq` database):

  single   p50/p95 latency per AI endpoint, N sequential calls each
  concurrent   the same foreground endpoint from C simultaneous synthetic
           authors (one user per client, so per-user rate limits do not
           distort the measurement), C in --levels
  background   C simultaneous background jobs (story bible) to observe the
           BG_AI_CONCURRENCY semaphore: queueing time vs failures
  vllm     vLLM queue depth sampled from :9001/metrics during every phase
  ramp     (Stage 10, task 10.8) capacity: C simultaneous ACTIVE authors, each
           looping for --ramp-seconds with a think time between actions and a
           realistic mix (70% rewrite tools, 20% Plot Assistant Q&A, 10%
           search); a --pro-share of them run on the pro plan with Tier-2
           strict consistency (decision D6: one extra LLM call per generation).
           Per level: p95 per class, errors, vLLM queue depth.

Every synthetic user/story it creates is deleted at the end, by the exact ids
it created. Output: one JSON report (--out).

Usage (see docs/testing/performance-baselines.md for the exact run):
  DATABASE_URL=...narratiq_test python3 backend/scripts/perf/load_probe.py \
      --base http://127.0.0.1:8100 --out /tmp/perf.json --phase all
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import statistics
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))
sys.path.insert(0, str(_BACKEND / "tests"))

import httpx  # noqa: E402

from db_safety_guard import allowed_test_dbs, is_allowed_test_db_name  # noqa: E402

PASSAGE = (
    "Devika pressed her palm against the cold glass of the observatory window. Below, the harbour "
    "lights trembled in the rain, and somewhere beyond them Mara was still searching for the ledger "
    "that would ruin them both. She had promised Sant she would wait. She had never been good at "
    "waiting. The clock behind her ticked past midnight, and the storm pulled at the old shutters "
    "as if it, too, wanted to be let in."
)


def _chapter_html(n: int) -> str:
    paras = [f"<p>{PASSAGE} (Chapter {n}, part {i}.)</p>" for i in range(1, 9)]
    return "".join(paras)


class Fixture:
    """Synthetic authors created directly in the test DB (same SECRET_KEY as
    the backend under test, so create_token() yields valid tokens)."""

    def __init__(self):
        from database import SessionLocal, engine
        if not is_allowed_test_db_name(engine.url.database, allowed_test_dbs()):
            sys.exit(f"refusing: database {engine.url.database!r} is not an allow-listed test database")
        self.db = SessionLocal()
        self.user_ids: list[str] = []

    def author(self, chapters: int = 3, plan: str | None = None) -> dict:
        from models import Chapter, Story, User
        from routers.auth import create_token, hash_password
        tag = uuid.uuid4().hex[:10]
        u = User(email=f"perf-{tag}@narratiq-internal-test.com", username=f"perf{tag}",
                 hashed_password=hash_password(uuid.uuid4().hex), plan=plan)
        self.db.add(u); self.db.flush()
        s = Story(user_id=u.user_id, title=f"Perf probe {tag}")
        self.db.add(s); self.db.flush()
        chs = [Chapter(story_id=s.story_id, title=f"Chapter {n}", chapter_number=n, content=_chapter_html(n))
               for n in range(1, chapters + 1)]
        self.db.add_all(chs)
        self.db.commit()
        self.user_ids.append(u.user_id)
        return {"uid": u.user_id, "sid": s.story_id, "cids": [c.chapter_id for c in chs],
                "headers": {"Authorization": f"Bearer {create_token(u.user_id)}"}}

    def cleanup(self):
        sys.path.insert(0, str(_BACKEND / "tests"))
        from test_cross_user_isolation import _delete_owned
        _delete_owned(self.db, set(self.user_ids))
        self.db.close()


def _endpoints(a: dict) -> list[tuple[str, str, str, dict]]:
    sid, cid = a["sid"], a["cids"][0]
    text = PASSAGE
    return [
        ("refine", "POST", "/api/ai/refine", {"text": text, "story_id": sid, "chapter_id": cid}),
        ("tone", "POST", "/api/ai/tone", {"text": text, "tone": "suspenseful", "story_id": sid, "chapter_id": cid}),
        ("emotion", "POST", "/api/ai/emotion", {"text": text, "emotion": "fear", "story_id": sid, "chapter_id": cid}),
        ("age-adapt", "POST", "/api/ai/age-adapt", {"text": text, "target_age": "ya", "story_id": sid, "chapter_id": cid}),
        ("style", "POST", "/api/ai/style", {"text": text, "style": "noir", "story_id": sid, "chapter_id": cid}),
        ("author-style", "POST", "/api/ai/author-style", {"text": text, "author": "austen", "story_id": sid}),
        ("translate", "POST", "/api/ai/translate", {"text": text, "target_language": "French", "story_id": sid}),
        ("suggestions", "POST", "/api/ai/suggestions", {"text": text, "story_id": sid, "chapter_id": cid}),
        ("plot-assistant", "POST", "/api/plot-assistant/", {"story_id": sid, "question": "What does Mara want?",
                                                            "current_chapter_number": 2}),
        ("continue", "POST", f"/api/stories/{sid}/chapters/{cid}/continue", {"tail_text": text}),
        ("outline", "POST", f"/api/stories/{sid}/chapters/{cid}/outline",
         {"chapter_goal": "Devika finds the stolen ledger in the observatory and must decide whether to tell Mara"}),
        ("semantic-search", "POST", f"/api/search/semantic/{sid}", {"query": "storm at the observatory"}),
        ("continuity", "POST", f"/api/stories/{sid}/continuity-check", {}),
        ("plot-holes", "POST", f"/api/stories/{sid}/plot-holes", {}),
    ]


async def _vllm_sampler(url: str, stop: asyncio.Event, out: list):
    rx = re.compile(r'^vllm:(num_requests_waiting|num_requests_running)\{[^}]*\}\s+([0-9.eE+-]+)', re.M)
    async with httpx.AsyncClient(timeout=5) as c:
        while not stop.is_set():
            try:
                t = (await c.get(url)).text
                vals = {k: float(v) for k, v in rx.findall(t)}
                out.append({"t": time.time(), **vals})
            except Exception:
                pass
            await asyncio.sleep(0.5)


async def index_story(client, a: dict, timeout_s: int = 900) -> bool:
    """Index the author's chapters through the real endpoint (continuity, plot
    holes and the story bible refuse an unindexed story with 422, correctly)."""
    from database import SessionLocal
    from models import ChapterSummary
    r = await client.post(f"/api/stories/{a['sid']}/chapters/sync-summaries", headers=a["headers"])
    if r.status_code not in (200, 202):
        return False
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        db = SessionLocal()
        try:
            n = db.query(ChapterSummary).filter(ChapterSummary.story_id == a["sid"]).count()
        finally:
            db.close()
        if n >= len(a["cids"]):
            return True
        await asyncio.sleep(3)
    return False


def _stats(samples: list[float]) -> dict:
    if not samples:
        return {"n": 0}
    s = sorted(samples)
    p95 = s[min(len(s) - 1, int(round(0.95 * (len(s) - 1))))]
    return {"n": len(s), "p50_ms": round(statistics.median(s)), "p95_ms": round(p95),
            "min_ms": round(s[0]), "max_ms": round(s[-1])}


async def _timed(client, method, path, body, headers) -> tuple[float, int]:
    t = time.perf_counter()
    try:
        r = await client.request(method, path, json=body, headers=headers)
        code = r.status_code
    except httpx.HTTPError:
        code = -1
    return (time.perf_counter() - t) * 1000, code


async def phase_single(base, fx, n, report):
    a = fx.author(chapters=6)
    out = {}
    async with httpx.AsyncClient(base_url=base, timeout=600) as c:
        t0 = time.perf_counter()
        indexed = await index_story(c, a)
        out["_indexing"] = {"chapters": len(a["cids"]), "ok": indexed,
                            "seconds": round(time.perf_counter() - t0, 1)}
        print(f"[single] indexing 6 chapters: {out['_indexing']}", flush=True)
        for name, method, path, body in _endpoints(a):
            lat, codes = [], []
            for _ in range(n):
                ms, code = await _timed(c, method, path, body, a["headers"])
                codes.append(code)
                if 200 <= code < 300:
                    lat.append(ms)
                await asyncio.sleep(0.2)
            out[name] = {**_stats(lat), "status_codes": codes}
            print(f"[single] {name:16s} {out[name]}", flush=True)
    report["single"] = out


async def phase_concurrent(base, fx, levels, endpoint, report):
    out = {}
    authors = [fx.author(chapters=3) for _ in range(max(levels))]
    async with httpx.AsyncClient(base_url=base, timeout=900,
                                 limits=httpx.Limits(max_connections=200)) as c:
        for level in levels:
            calls = []
            for a in authors[:level]:
                name, method, path, body = next(e for e in _endpoints(a) if e[0] == endpoint)
                calls.append(_timed(c, method, path, body, a["headers"]))
            t0 = time.perf_counter()
            res = await asyncio.gather(*calls)
            wall = (time.perf_counter() - t0) * 1000
            ok = [ms for ms, code in res if 200 <= code < 300]
            out[str(level)] = {**_stats(ok), "wall_ms": round(wall),
                               "errors": sorted(code for _ms, code in res if not 200 <= code < 300)}
            print(f"[concurrent:{endpoint}] c={level} {out[str(level)]}", flush=True)
    report[f"concurrent_{endpoint}"] = out


async def phase_background(base, fx, levels, report):
    """Story-bible generation is a background job behind bg_ai_semaphore."""
    out = {}
    async with httpx.AsyncClient(base_url=base, timeout=60) as c:
        for level in levels:
            authors = [fx.author(chapters=3) for _ in range(level)]
            async with httpx.AsyncClient(base_url=base, timeout=600) as ic:
                await asyncio.gather(*[index_story(ic, a) for a in authors])
            t0 = time.time()
            starts = await asyncio.gather(*[c.post(f"/api/stories/{a['sid']}/story-bible", headers=a["headers"])
                                            for a in authors])
            accepted = [a for a, r in zip(authors, starts) if r.status_code in (200, 201, 202)]
            done: dict[str, tuple[float, str]] = {}
            deadline = time.time() + 1800
            while len(done) < len(accepted) and time.time() < deadline:
                for a in accepted:
                    if a["sid"] in done:
                        continue
                    r = await c.get(f"/api/stories/{a['sid']}/story-bible", headers=a["headers"])
                    st = (r.json() or {}).get("status") if r.status_code == 200 else None
                    if st in ("completed", "complete", "ready", "failed", "partial", "error"):
                        done[a["sid"]] = (time.time() - t0, st)
                await asyncio.sleep(2)
            finals = [v for v in done.values()]
            out[str(level)] = {
                "accepted": len(accepted), "finished": len(finals),
                "statuses": sorted(s for _t, s in finals),
                "completion_s": sorted(round(t, 1) for t, _s in finals),
                "start_codes": sorted(r.status_code for r in starts),
            }
            print(f"[background] c={level} {out[str(level)]}", flush=True)
    report["background_story_bible"] = out


RAMP_MIX = [("rewrite", 0.70), ("qa", 0.20), ("search", 0.10)]
REWRITE_TOOLS = ["tone", "refine", "style"]


async def phase_ramp(base, fx, levels, seconds, think, pro_share, vllm_samples, report, settle=0):
    """Capacity ramp (Stage 10, 10.8). An 'active author' performs one AI action,
    then thinks for `think` seconds (uniform ±50%), for `seconds` seconds."""
    import random
    rng = random.Random(10)
    out = {}
    max_level = max(levels)
    n_pro = int(round(max_level * pro_share))
    # One indexed chapter per author: Q&A and search then retrieve over real
    # embeddings; the chapter count barely changes per-request cost.
    authors = [fx.author(chapters=1, plan="pro" if i < n_pro else None) for i in range(max_level)]
    async with httpx.AsyncClient(base_url=base, timeout=900, limits=httpx.Limits(max_connections=400)) as c:
        # Index once, so Q&A and search retrieve over real embeddings, then let the
        # follow-on background work (mentions, hints) finish so it does not
        # contaminate the first level (seen in the first Stage 10 run).
        await asyncio.gather(*[index_story(c, a) for a in authors])
        await asyncio.sleep(settle)
        for level in levels:
            samples: dict[str, list[float]] = {k: [] for k, _ in RAMP_MIX}
            errors: dict[str, int] = {}
            v_before = len(vllm_samples)
            deadline = time.monotonic() + seconds

            async def author_loop(a, is_pro):
                await asyncio.sleep(rng.uniform(0, think))          # stagger starts
                while time.monotonic() < deadline:
                    r = rng.random()
                    cls = "rewrite" if r < 0.70 else ("qa" if r < 0.90 else "search")
                    eps = {e[0]: e for e in _endpoints(a)}
                    if cls == "rewrite":
                        _n, m, path, body = eps[rng.choice(REWRITE_TOOLS)]
                        if is_pro and path in ("/api/ai/tone", "/api/ai/style"):
                            body = {**body, "controls": {"consistency": "strict"}}
                    elif cls == "qa":
                        _n, m, path, body = eps["plot-assistant"]
                    else:
                        _n, m, path, body = eps["semantic-search"]
                    ms, code = await _timed(c, m, path, body, a["headers"])
                    if 200 <= code < 300:
                        samples[cls].append(ms)
                    else:
                        errors[str(code)] = errors.get(str(code), 0) + 1
                    await asyncio.sleep(rng.uniform(think * 0.5, think * 1.5))

            await asyncio.gather(*[author_loop(a, i < n_pro) for i, a in enumerate(authors[:level])])
            vs = vllm_samples[v_before:]
            out[str(level)] = {
                **{cls: _stats(v) for cls, v in samples.items()},
                "errors": errors,
                "requests": sum(len(v) for v in samples.values()) + sum(errors.values()),
                "vllm_max_waiting": max((x.get("num_requests_waiting", 0) for x in vs), default=None),
                "vllm_max_running": max((x.get("num_requests_running", 0) for x in vs), default=None),
            }
            print(f"[ramp] authors={level} {out[str(level)]}", flush=True)
    report["ramp"] = {"seconds_per_level": seconds, "think_seconds": think, "pro_share": pro_share, "settle": settle,
                      "mix": dict(RAMP_MIX), "levels": out}


async def main_async(args):
    fx = Fixture()
    report = {"started": datetime.utcnow().isoformat() + "Z", "base": args.base,
              "bg_ai_concurrency": None, "embedding_concurrency": None}
    try:
        from config import settings
        report["bg_ai_concurrency"] = settings.bg_ai_concurrency
        report["embedding_concurrency"] = settings.embedding_concurrency
    except Exception:
        pass
    stop = asyncio.Event()
    vllm: list = []
    sampler = asyncio.create_task(_vllm_sampler(args.vllm_metrics, stop, vllm))
    try:
        phases = args.phase.split(",") if args.phase != "all" else ["single", "concurrent", "background"]
        if "single" in phases:
            await phase_single(args.base, fx, args.n, report)
        if "concurrent" in phases:
            for ep in args.concurrent_endpoints.split(","):
                await phase_concurrent(args.base, fx, args.levels, ep, report)
        if "background" in phases:
            await phase_background(args.base, fx, args.bg_levels, report)
        if "ramp" in phases:
            await phase_ramp(args.base, fx, args.ramp_levels, args.ramp_seconds, args.think,
                             args.pro_share, vllm, report, settle=args.settle)
    finally:
        stop.set()
        await sampler
        fx.cleanup()
    waiting = [s.get("num_requests_waiting", 0) for s in vllm]
    running = [s.get("num_requests_running", 0) for s in vllm]
    report["vllm_queue"] = {"samples": len(vllm), "max_waiting": max(waiting, default=None),
                            "max_running": max(running, default=None),
                            "mean_waiting": round(statistics.mean(waiting), 2) if waiting else None}
    report["finished"] = datetime.utcnow().isoformat() + "Z"
    Path(args.out).write_text(json.dumps(report, indent=2))
    print(f"report: {args.out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8100")
    ap.add_argument("--vllm-metrics", default="http://127.0.0.1:9001/metrics")
    ap.add_argument("--out", default="/tmp/narratiq-perf.json")
    ap.add_argument("--phase", default="all")
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--levels", type=lambda s: [int(x) for x in s.split(",")], default=[1, 3, 6, 10])
    ap.add_argument("--bg-levels", type=lambda s: [int(x) for x in s.split(",")], default=[1, 3, 6])
    ap.add_argument("--concurrent-endpoints", default="tone,plot-assistant")
    ap.add_argument("--ramp-levels", type=lambda s: [int(x) for x in s.split(",")], default=[10, 20, 40, 60])
    ap.add_argument("--ramp-seconds", type=int, default=120)
    ap.add_argument("--think", type=float, default=30.0, help="mean seconds between one author's AI actions")
    ap.add_argument("--settle", type=int, default=0, help="seconds to wait after indexing before the first level")
    ap.add_argument("--pro-share", type=float, default=0.0, help="share of authors on pro with Tier-2 consistency")
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    main()
