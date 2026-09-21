"""
Stage 5 task 5.2 — golden-set measurement harness.

Runs the golden set (tests/fixtures/transform_golden_set.py) against the
CURRENTLY CONFIGURED prompt_version and writes a JSON report. Used twice:
  1. Before any Stage 5 prompt/architecture change (prompt_version=v1) to
     capture the required baseline.
  2. After (prompt_version=v2) for task 5.16's re-measurement.

Metrics (raw, deterministic, explicitly NOT claiming to measure subjective
qualities directly — see the module docstring in transform_golden_set.py):
  - text_similarity   : difflib.SequenceMatcher ratio, original vs transformed
                        ("textual/edit similarity" — evidence FOR voice
                        preservation, not a direct measurement of it)
  - content_similarity: BGE-M3 cosine similarity, original vs transformed
                        embedding ("semantic/content preservation similarity"
                        — evidence, not a direct measurement of "genre drift")
  - byte_identical    : exact string equality (used for no-change/lock cases)

Each scenario runs N_TRIALS times (non-zero temperature means output varies
run to run); every raw trial is kept, not just the average, so sampling
variation can be told apart from a real change later.

Usage:
    cd backend && python3 tests/measure_transform_golden_set.py --label baseline_v1
    cd backend && python3 tests/measure_transform_golden_set.py --label after_v2
"""
import argparse
import asyncio
import json
import statistics
import sys
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import settings  # noqa: E402
from services.ai_service import (  # noqa: E402
    transform_tone, transform_style, adapt_for_age, embed_text,
)
from tests.fixtures.transform_golden_set import PASSAGES, ALREADY_SUITABLE_FOR, LOCK_SCENARIOS  # noqa: E402

N_TRIALS = 3


def text_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


async def content_similarity(a: str, b: str) -> float:
    import numpy as np
    ea = np.array(await embed_text(a))
    eb = np.array(await embed_text(b))
    return float(ea @ eb / (np.linalg.norm(ea) * np.linalg.norm(eb)))


async def _run_scenario(passage: dict, transform_type: str, target: str) -> dict:
    trials = []
    for _ in range(N_TRIALS):
        if transform_type == "tone":
            result = await transform_tone(passage["text"], target)
        elif transform_type == "style":
            result = await transform_style(passage["text"], target)
        elif transform_type == "age_adapt":
            result = await adapt_for_age(passage["text"], target)
        else:
            raise ValueError(transform_type)
        # v1's transform_tone/style/adapt_for_age returned a plain string;
        # since 5.4-5.6's orchestrator refactor they return the Stage 5
        # result dict (see _run_constrained_transform). Support both so a
        # v1-labeled re-run against old code paths would still work.
        out = result["transformed"] if isinstance(result, dict) else result

        trials.append({
            "output": out,
            "byte_identical": out.strip() == passage["text"].strip(),
            "text_similarity": text_similarity(passage["text"], out),
            "content_similarity": await content_similarity(passage["text"], out),
            "lock_target_preserved": (
                LOCK_SCENARIOS.get(passage["id"]) in out
                if passage["id"] in LOCK_SCENARIOS else None
            ),
        })

    avg = lambda key: sum(t[key] for t in trials) / len(trials)
    # Task 5.12 requirement "G: consistent across runs" — reuses these same
    # N_TRIALS runs rather than generating new ones. Low stdev = the trials
    # cluster together (consistent behavior); high stdev = one prompt/seed
    # combination produces wildly different outputs run to run.
    stdev = lambda key: statistics.stdev(t[key] for t in trials) if len(trials) > 1 else 0.0
    return {
        "passage_id": passage["id"], "genre": passage["genre"],
        "transform_type": transform_type, "target": target,
        "trials": trials,
        "avg_text_similarity": avg("text_similarity"),
        "avg_content_similarity": avg("content_similarity"),
        "stdev_text_similarity": stdev("text_similarity"),
        "stdev_content_similarity": stdev("content_similarity"),
        "byte_identical_rate": sum(1 for t in trials if t["byte_identical"]) / len(trials),
    }


async def run_all() -> list[dict]:
    scenarios = []
    for p in PASSAGES:
        if "distinctive_voice" in p["tags"]:
            scenarios.append((p, "tone", "suspenseful"))
        elif "plain_register" in p["tags"]:
            scenarios.append((p, "style", "cinematic"))
        elif "high_energy" in p["tags"]:
            scenarios.append((p, "age_adapt", "children"))
        # already-suitable passages get their OWN tagged transform, overriding
        # the genre-default above, since that's the specific case being measured
        if p["id"] in ALREADY_SUITABLE_FOR:
            transform_type, target = ALREADY_SUITABLE_FOR[p["id"]]
            scenarios = [s for s in scenarios if s[0]["id"] != p["id"]]
            scenarios.append((p, transform_type, target))

    results = []
    for p, transform_type, target in scenarios:
        print(f"  running {p['id']} / {transform_type} -> {target} ({N_TRIALS} trials)...", flush=True)
        results.append(await _run_scenario(p, transform_type, target))
    return results


def _consistency_summary(results: list[dict]) -> dict:
    """Task 5.12 'G: consistent across runs' — mean of each scenario's
    across-trial stdev, i.e. how much a single scenario's own N_TRIALS runs
    disagree with each other. Derived from the already-collected trials, not
    a new measurement."""
    text_stdevs = [r["stdev_text_similarity"] for r in results if "stdev_text_similarity" in r]
    content_stdevs = [r["stdev_content_similarity"] for r in results if "stdev_content_similarity" in r]
    return {
        "mean_stdev_text_similarity": round(statistics.mean(text_stdevs), 4) if text_stdevs else None,
        "mean_stdev_content_similarity": round(statistics.mean(content_stdevs), 4) if content_stdevs else None,
        "max_stdev_text_similarity": round(max(text_stdevs), 4) if text_stdevs else None,
        "max_stdev_content_similarity": round(max(content_stdevs), 4) if content_stdevs else None,
        "n_scenarios": len(results),
    }


def summarize_consistency(report_path: Path) -> dict:
    """Recomputes the consistency summary from an already-written report's
    raw trials — used for reports written before stdev fields existed
    (e.g. baseline_v1.json), so no regeneration is needed."""
    report = json.loads(report_path.read_text())
    for r in report["scenarios"]:
        if "stdev_text_similarity" not in r:
            r["stdev_text_similarity"] = (
                statistics.stdev(t["text_similarity"] for t in r["trials"]) if len(r["trials"]) > 1 else 0.0
            )
            r["stdev_content_similarity"] = (
                statistics.stdev(t["content_similarity"] for t in r["trials"]) if len(r["trials"]) > 1 else 0.0
            )
    return _consistency_summary(report["scenarios"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", help="e.g. baseline_v1 or after_v2")
    parser.add_argument("--summarize-consistency", metavar="REPORT_JSON",
                         help="Recompute the 5.12-G consistency summary from an existing report, no new generation.")
    args = parser.parse_args()

    if args.summarize_consistency:
        summary = summarize_consistency(Path(args.summarize_consistency))
        print(json.dumps(summary, indent=2))
        return

    if not args.label:
        parser.error("--label is required unless --summarize-consistency is given")

    print(f"Golden-set measurement — prompt_version={settings.prompt_version}, label={args.label}")
    results = asyncio.run(run_all())

    out_path = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / f"transform_golden_{args.label}.json"
    report = {
        "label": args.label,
        "prompt_version": settings.prompt_version,
        "n_trials_per_scenario": N_TRIALS,
        "scenarios": results,
        "consistency_summary": _consistency_summary(results),
    }
    out_path.write_text(json.dumps(report, indent=2))
    print(f"\nWrote {out_path}")

    print("\n=== Summary ===")
    for r in results:
        print(f"  {r['passage_id']:16s} {r['transform_type']:10s}->{r['target']:12s} "
              f"text_sim={r['avg_text_similarity']:.3f} content_sim={r['avg_content_similarity']:.3f} "
              f"byte_identical_rate={r['byte_identical_rate']:.2f} "
              f"stdev(text/content)={r['stdev_text_similarity']:.3f}/{r['stdev_content_similarity']:.3f}")

    print("\n=== Consistency summary (5.12-G) ===")
    print(json.dumps(report["consistency_summary"], indent=2))


if __name__ == "__main__":
    main()
