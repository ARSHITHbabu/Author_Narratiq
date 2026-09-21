"""
Stage 5 task 5.13 — reconstructs the EXACT pre-this-round suggestions prompt
and coercer (copied verbatim from the source before this round's edits, not
paraphrased) to produce a genuine "before" baseline, run against the SAME
measurement logic as measure_suggestions_quality.py's "after" run. This
exists because the live _suggestions_v2/coerce_writing_suggestions were
edited in place (no new prompt_registry version — matching how 5.5's
no-change-assessment fix-and-revert was handled earlier in this session),
so the ordinary before/after harness can no longer produce a true "before"
without this reconstruction.

Usage:
    cd backend && python3 tests/measure_suggestions_quality_before.py
"""
import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.ai_service import complete_structured, _issue_list_from  # noqa: E402
from tests.fixtures.suggestions_golden_set import PASSAGES  # noqa: E402

_OLD_SUGGESTIONS_SYSTEM = (
    "You are a developmental editor giving direct, specific manuscript "
    "feedback — not a cheerleader. Analyse the excerpt and identify the "
    "2-4 most significant WEAKNESSES a working novelist would actually want "
    "to fix. Do not lead with praise; only mention a strength if it's "
    "necessary to explain why a weakness matters in context. Each item must "
    "separate what you OBSERVED (the specific issue, quoting or pointing at "
    "the actual text) from what you RECOMMEND (a concrete, actionable "
    "change) — these are different things, do not merge them into one "
    "vague sentence. Avoid generic craft-book language ('show don't tell') "
    "unless you also say exactly where and how it applies to THIS excerpt. "
    "Return ONLY a JSON array of 2-4 objects: {id: int, category: string, "
    "observation: string, recommendation: string}."
)


def _old_coerce_writing_suggestions(parsed) -> tuple[Optional[list], int]:
    """Verbatim copy of coerce_writing_suggestions as it existed before this
    round's priority/sorting addition."""
    items = _issue_list_from(parsed, "suggestions")
    if items is None:
        return None, 0
    kept, discarded = [], 0
    for position, item in enumerate(items, 1):
        if not isinstance(item, dict):
            discarded += 1
            continue
        observation = str(item.get("observation") or item.get("text") or "").strip()
        recommendation = str(item.get("recommendation") or "").strip()
        if not observation and not recommendation:
            discarded += 1
            continue
        reason = " ".join(p for p in (observation, recommendation) if p) or str(item.get("reason") or "")
        kept.append({
            "id": item.get("id", position),
            "category": str(item.get("category") or "General"),
            "observation": observation or reason,
            "recommendation": recommendation,
            "text": observation or reason,
            "reason": reason,
        })
    return kept, discarded


async def _old_generate_suggestions(text: str) -> list:
    result, meta = await complete_structured(
        _OLD_SUGGESTIONS_SYSTEM, f"Excerpt:\n{text}",
        coerce=_old_coerce_writing_suggestions,
        temperature=0.0, max_tokens=600, label="writing_suggestions_before_reconstruction",
    )
    return result or []


async def run_all() -> dict:
    results = []
    for p in PASSAGES:
        suggestions = await _old_generate_suggestions(p["text"])
        all_text = " ".join(
            f"{s.get('category', '')} {s.get('observation', '')} {s.get('recommendation', '')} {s.get('text', '')}".lower()
            for s in suggestions
        )
        detected = any(kw in all_text for kw in p["expected_keywords"])
        categories = {s.get("category", "") for s in suggestions}
        has_priority = bool(suggestions) and all("priority" in s for s in suggestions)
        results.append({
            "passage_id": p["id"], "weakness": p["weakness"],
            "n_suggestions": len(suggestions),
            "weakness_detected": detected,
            "categories": sorted(categories),
            "has_priority_field": has_priority,
            "raw_suggestions": suggestions,
        })
        print(f"  {p['id']:24s} detected={detected} categories={sorted(categories)} priority={has_priority}")
    all_categories = set()
    for r in results:
        all_categories.update(r["categories"])
    return {
        "results": results,
        "recall_rate": sum(1 for r in results if r["weakness_detected"]) / len(results),
        "distinct_categories_across_set": sorted(all_categories),
        "distinct_category_count": len(all_categories),
        "all_have_priority": all(r["has_priority_field"] for r in results),
    }


def main():
    print("Suggestions quality measurement — TRUE before (reconstructed pre-round prompt)")
    report = asyncio.run(run_all())
    out_path = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "suggestions_quality_before.json"
    out_path.write_text(json.dumps(report, indent=2))
    print(f"\nWrote {out_path}")
    print(f"recall_rate={report['recall_rate']:.2f} distinct_categories={report['distinct_category_count']} "
          f"all_have_priority={report['all_have_priority']}")


if __name__ == "__main__":
    main()
