"""
Stage 5 task 5.13 — before/after measurement for the AI-suggestions overhaul.

Runs the golden set (tests/fixtures/suggestions_golden_set.py) through
generate_suggestions() against the real backend/vLLM and records, per
passage:
  - weakness_detected: at least one suggestion's observation+recommendation
    text contains one of that passage's expected_keywords (a deterministic
    RECALL proxy for "did it catch the specific known weakness", not a
    judgment of suggestion quality in general)
  - category_variety: number of DISTINCT categories used across the run's
    suggestions (High 8 — over-reliance on fixed categories)
  - has_priority: whether every suggestion carries a priority field
    (Medium 13 — recommendation prioritisation)
  - soft_praise_count: suggestions whose text contains a soft-praise phrase
    ("great job", "well done", "shows real", "impressive") — should trend
    toward zero; a cheap, deterministic proxy for "not just praise",
    reusing the same measurement spirit as the rest of Stage 5, not a new
    LLM-judge layer.

Usage:
    cd backend && python3 tests/measure_suggestions_quality.py --label before
    cd backend && python3 tests/measure_suggestions_quality.py --label after
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.ai_service import generate_suggestions  # noqa: E402
from tests.fixtures.suggestions_golden_set import PASSAGES  # noqa: E402

_SOFT_PRAISE_PHRASES = ["great job", "well done", "shows real", "impressive", "nicely done", "excellent work"]


async def run_all() -> dict:
    results = []
    for p in PASSAGES:
        suggestions = await generate_suggestions(p["text"])
        # Category is checked too — a category of "Exposition" is itself
        # evidence of detecting an info-dump, not just the observation prose.
        all_text = " ".join(
            f"{s.get('category', '')} {s.get('observation', '')} {s.get('recommendation', '')} {s.get('text', '')}".lower()
            for s in suggestions
        )
        detected = any(kw in all_text for kw in p["expected_keywords"])
        categories = {s.get("category", "") for s in suggestions}
        has_priority = bool(suggestions) and all("priority" in s for s in suggestions)
        soft_praise = sum(1 for phrase in _SOFT_PRAISE_PHRASES if phrase in all_text)
        results.append({
            "passage_id": p["id"], "weakness": p["weakness"],
            "n_suggestions": len(suggestions),
            "weakness_detected": detected,
            "categories": sorted(categories),
            "has_priority_field": has_priority,
            "soft_praise_hits": soft_praise,
            "raw_suggestions": suggestions,
        })
        print(f"  {p['id']:24s} detected={detected} categories={sorted(categories)} "
              f"priority={has_priority} soft_praise={soft_praise}")
    all_categories = set()
    for r in results:
        all_categories.update(r["categories"])
    return {
        "results": results,
        "recall_rate": sum(1 for r in results if r["weakness_detected"]) / len(results),
        "distinct_categories_across_set": sorted(all_categories),
        "distinct_category_count": len(all_categories),
        "any_soft_praise": any(r["soft_praise_hits"] > 0 for r in results),
        "all_have_priority": all(r["has_priority_field"] for r in results),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    args = parser.parse_args()

    print(f"Suggestions quality measurement — label={args.label}")
    report = asyncio.run(run_all())

    out_path = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / f"suggestions_quality_{args.label}.json"
    out_path.write_text(json.dumps(report, indent=2))
    print(f"\nWrote {out_path}")
    print(f"recall_rate={report['recall_rate']:.2f} "
          f"distinct_categories={report['distinct_category_count']} "
          f"any_soft_praise={report['any_soft_praise']} "
          f"all_have_priority={report['all_have_priority']}")


if __name__ == "__main__":
    main()
