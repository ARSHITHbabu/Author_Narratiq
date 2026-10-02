#!/usr/bin/env python3
"""
Stage 12 Tranche 2b — A15: what do Light / Moderate / Strong actually do?

Runs the 12 golden-set passages through tone (suspenseful), age adaptation
(children) and style (cinematic) at every strength, N runs each, against the
CURRENTLY CONFIGURED prompt version, plus emotion (always run at Strong) as a
reference. Every output gets services.transform_preservation.light_edit_profile
and the existing count-based strength check. Nothing here sets a threshold:
the report shows the distributions so a human can decide what "acceptable
Light" is.

  cd backend && python3 tests/measure_strength_t2b.py --label before_v3 [--runs 5]
  PROMPT_VERSION=v4 python3 tests/measure_strength_t2b.py --label after_v4
Writes tests/fixtures/strength_t2b_<label>.json.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TRANSFORMS = [("tone", "suspenseful"), ("age_adapt", "children"), ("style", "cinematic")]
STRENGTHS = ("light", "moderate", "strong")
METRICS = ("kept_share", "new_share", "word_order", "min_sentence_kept")


async def _one(ai, tp, kind, target, strength, text, sem):
    async with sem:
        if kind == "tone":
            r = await ai.transform_tone(text, target, strength=strength)
        elif kind == "age_adapt":
            r = await ai.adapt_for_age(text, target, strength=strength)
        elif kind == "style":
            r = await ai.transform_style(text, target, strength=strength)
        else:
            r = await ai.rewrite_emotion(text, "dread", "medium")
    out = r["transformed"]
    return {"output": out, "no_change": r["no_change"], "failed": r["failed"],
            "strength_violation": r["strength_violation"],
            "profile": tp.light_edit_profile(text, out)}


def _q(vals, p):
    vals = sorted(vals)
    if not vals:
        return None
    k = (len(vals) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(vals) - 1)
    return round(vals[lo] + (vals[hi] - vals[lo]) * (k - lo), 3)


def summarise(rows):
    out = {}
    for kind in [t for t, _ in TRANSFORMS] + ["emotion"]:
        for strength in STRENGTHS:
            rs = [r for r in rows if r["transform"] == kind and r["strength"] == strength
                  and not r["no_change"] and not r["failed"] and r["profile"].get("measured")]
            allr = [r for r in rows if r["transform"] == kind and r["strength"] == strength]
            if not allr:
                continue
            s = {"runs": len(allr), "changed_runs": len(rs),
                 "no_change": sum(r["no_change"] for r in allr), "failed": sum(r["failed"] for r in allr),
                 "count_check_flagged": sum(r["strength_violation"] for r in allr)}
            for m in METRICS:
                v = [r["profile"][m] for r in rs if r["profile"].get(m) is not None]
                s[m] = {"p05": _q(v, .05), "p25": _q(v, .25), "median": _q(v, .5), "p75": _q(v, .75),
                        "p95": _q(v, .95)} if v else None
            out[f"{kind}/{strength}"] = s
        # overlap: how many Light outputs keep fewer words than the median Strong output
        light = [r["profile"]["kept_share"] for r in rows if r["transform"] == kind and r["strength"] == "light"
                 and not r["no_change"] and not r["failed"] and r["profile"].get("measured")]
        strong = [r["profile"]["kept_share"] for r in rows if r["transform"] == kind and r["strength"] == "strong"
                  and not r["no_change"] and not r["failed"] and r["profile"].get("measured")]
        if light and strong:
            ms = statistics.median(strong)
            out[f"{kind}/overlap"] = {
                "light_below_strong_median": round(sum(v < ms for v in light) / len(light), 3),
                "light_minus_strong_median_kept": round(statistics.median(light) - ms, 3)}
    return out


async def main(label: str, runs: int, concurrency: int, only=None):
    from config import settings
    from services import ai_service as ai
    from services import transform_preservation as tp
    from tests.fixtures.transform_golden_set import PASSAGES

    sem = asyncio.Semaphore(concurrency)
    jobs, meta = [], []
    for p in PASSAGES:
        for kind, target in TRANSFORMS:
            if only and kind not in only:
                continue
            for strength in STRENGTHS:
                for i in range(runs):
                    jobs.append(_one(ai, tp, kind, target, strength, p["text"], sem))
                    meta.append({"passage": p["id"], "transform": kind, "target": target,
                                 "strength": strength, "run": i})
        for i in range(runs if not only or "emotion" in only else 0):
            jobs.append(_one(ai, tp, "emotion", "dread", "strong", p["text"], sem))
            meta.append({"passage": p["id"], "transform": "emotion", "target": "dread",
                         "strength": "strong", "run": i})
    print(f"A15 strength measurement — prompt_version={settings.prompt_version}, {len(jobs)} generations", flush=True)
    results = await asyncio.gather(*jobs, return_exceptions=True)
    rows = []
    for m, r in zip(meta, results):
        if isinstance(r, Exception):
            rows.append({**m, "error": f"{type(r).__name__}: {r}", "no_change": False, "failed": True,
                         "strength_violation": False, "profile": {"measured": False}})
        else:
            rows.append({**m, **r})
    report = {"label": label, "prompt_version": settings.prompt_version, "runs": runs,
              "summary": summarise(rows), "rows": rows}
    out = Path(__file__).parent / "fixtures" / f"strength_t2b_{label}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--only", nargs="*", default=None, help="transforms to run (default: all)")
    a = ap.parse_args()
    asyncio.run(main(a.label, a.runs, a.concurrency, a.only))
