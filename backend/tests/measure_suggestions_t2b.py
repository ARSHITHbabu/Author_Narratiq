#!/usr/bin/env python3
"""
Stage 12 Tranche 2b — A17 suggestion hygiene, measured against live Qwen.

Variants (same prompts, same passages):
  current        what production did before A17: v3 resolves, so the Stage 5
                 sharpening pass never ran; no hygiene filter
  hygiene        + services/suggestion_hygiene.clean_suggestions
  hygiene+sharp  + the sharpening pass restored for every non-v1 version

Passages: the 5-passage golden set (recall = the known weakness is named) and
3 passages of deliberately strong prose that tempt a model into praise.
Metrics per variant: recall, distinct categories, in-response near-duplicate
pairs, items without a real recommendation, praise in observations (outside
quotes), items dropped by hygiene, empty results.

  cd backend && python3 tests/measure_suggestions_t2b.py [--runs 3]
Writes tests/fixtures/suggestions_quality_t2b.json.
"""
from __future__ import annotations

import argparse
import asyncio
import itertools
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

STRONG_PROSE = [
    ("strong-1", "The kettle had been cold for an hour before Ada noticed. She stood at the window with "
                 "the letter folded small in her fist, watching the postman's bicycle wobble down the lane, "
                 "and did not open it, because opening it would make it true."),
    ("strong-2", "Rain again. Tomas counted the drips from the cracked gutter — forty-one, forty-two — and "
                 "thought about the boy who used to live upstairs, who had counted them too, out loud, every "
                 "night of the winter his father did not come home."),
    ("strong-3", "'You kept it,' she said. The music box sat between them on the table, its lid chipped, "
                 "its dancer missing an arm. He shrugged as if it were nothing. It played four notes before "
                 "it caught, and neither of them reached to wind it again."),
]


def _metrics(items):
    from services.suggestion_hygiene import DUPLICATE_JACCARD, MIN_RECOMMENDATION_WORDS, _similar, _rec_words, praise_only, _PRAISE, _QUOTED
    dups = sum(1 for a, b in itertools.combinations(items, 2) if _similar(a, b) >= DUPLICATE_JACCARD)
    no_rec = sum(1 for s in items if _rec_words(s) < MIN_RECOMMENDATION_WORDS)
    praise_obs = sum(1 for s in items if _PRAISE.search(_QUOTED.sub(" ", s.get("observation") or "")))
    return {"n": len(items), "dup_pairs": dups, "no_recommendation": no_rec,
            "praise_in_observation": praise_obs, "praise_only": sum(praise_only(s) for s in items)}


async def run_variant(name, runs):
    from services import ai_service as ai
    from services import suggestion_hygiene as hy
    from tests.fixtures.suggestions_golden_set import PASSAGES
    orig_clean, orig_sharpen = hy.clean_suggestions, ai._SHARPEN_SUGGESTIONS
    dropped_log = []

    def logging_clean(items):
        kept, dropped = orig_clean(items)
        dropped_log.extend(dropped)
        return kept, dropped

    hy.clean_suggestions = (lambda items: (items, [])) if name == "current" else logging_clean
    ai._SHARPEN_SUGGESTIONS = name == "hygiene+sharp"
    rows = []
    try:
        cases = [(p["id"], p["text"], p["expected_keywords"]) for p in PASSAGES] + \
                [(cid, t, None) for cid, t in STRONG_PROSE]
        for cid, text, kws in cases:
            for i in range(runs):
                try:
                    items = await ai.generate_suggestions(text)
                    err = None
                except ValueError as exc:
                    items, err = [], str(exc)
                blob = " ".join(f"{s.get('category', '')} {s.get('observation', '')} {s.get('recommendation', '')}"
                                for s in items).lower()
                rows.append({"case": cid, "run": i, "error": err,
                             "detected": (any(k in blob for k in kws) if kws else None),
                             "categories": sorted({s.get("category", "") for s in items}),
                             **_metrics(items), "items": items})
    finally:
        hy.clean_suggestions, ai._SHARPEN_SUGGESTIONS = orig_clean, orig_sharpen
    golden = [r for r in rows if r["detected"] is not None]
    summary = {
        "recall": round(sum(r["detected"] for r in golden) / len(golden), 3),
        "distinct_categories": len({c for r in golden for c in r["categories"]}),
        "dup_pairs": sum(r["dup_pairs"] for r in rows),
        "no_recommendation_items": sum(r["no_recommendation"] for r in rows),
        "praise_in_observation_items": sum(r["praise_in_observation"] for r in rows),
        "items_total": sum(r["n"] for r in rows),
        "empty_or_error": sum(1 for r in rows if not r["n"]),
        "hygiene_dropped": [d["why"] for d in dropped_log],
    }
    return {"summary": summary, "rows": rows,
            "dropped_items": [{"why": d["why"], "item": d["item"]} for d in dropped_log]}


async def main(runs):
    from config import settings
    report = {"prompt_version": settings.prompt_version, "runs": runs, "variants": {}}
    for name in ("current", "hygiene", "hygiene+sharp"):
        print(f"variant {name}…", flush=True)
        report["variants"][name] = await run_variant(name, runs)
        print(name, json.dumps(report["variants"][name]["summary"]), flush=True)
    (Path(__file__).parent / "fixtures" / "suggestions_quality_t2b.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    asyncio.run(main(ap.parse_args().runs))
