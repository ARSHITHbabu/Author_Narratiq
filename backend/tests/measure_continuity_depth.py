"""
Stage 5 task 5.14 — before/after measurement for check_continuity's deepened
reasoning (motivation/relationship contradiction types + arc/relationship
data wired into the prompt).

"Before" reconstructs the EXACT prompt check_continuity used prior to this
round's change (character_appearance/character_location/world_rule/timeline
only, no arc/relationship data in chap_block — copied verbatim from the
pre-change source, not paraphrased). "After" calls the real, current
check_continuity(). Both run against the same controlled fixtures
(tests/fixtures/continuity_depth_fixture.py) against the real backend/vLLM
— no mocking, since the question is genuine model behavior, not wiring.

Usage:
    cd backend && python3 tests/measure_continuity_depth.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.ai_service import check_continuity, complete_structured, coerce_continuity_issues  # noqa: E402
from tests.fixtures.continuity_depth_fixture import (  # noqa: E402
    CHARACTER_PROFILES, MOTIVATION_CASE, RELATIONSHIP_CASE, SURFACE_CONTROL_CASE, CLEAN_CONTROL_CASE,
)

CASES = {
    "motivation_contradiction": MOTIVATION_CASE,
    "relationship_contradiction": RELATIONSHIP_CASE,
    "surface_control (should still be caught)": SURFACE_CONTROL_CASE,
    "clean_control (should stay empty)": CLEAN_CONTROL_CASE,
}


async def run_old_prompt(chapter_summaries: list[dict]) -> list[dict]:
    """The EXACT pre-this-round prompt — no motivation/relationship type,
    no arc_notes/relationship_changes in chap_block. Copied verbatim, not
    reconstructed from memory."""
    char_block = "\n".join(
        f"- {p['name']}: appearance={p.get('appearance','')}, status={p.get('status','')}, goals={p.get('goals','')}"
        for p in CHARACTER_PROFILES
    ) or "(no characters)"
    chap_block = "\n".join(
        f"- Ch{s['chapter_number']}: locations={s.get('locations','')}, "
        f"characters_present={s.get('characters_present','')}, "
        f"key_events={s.get('key_events','')}"
        for s in chapter_summaries
    ) or "(no summaries)"
    system = (
        "You are a continuity editor reviewing a manuscript for internal contradictions. "
        "Be specific: quote the conflicting facts and cite chapter numbers."
    )
    user = (
        "## Character Profiles\n" + char_block + "\n\n"
        "## Chapter-by-Chapter Summary\n" + chap_block + "\n\n"
        "## World/Story Notes\n(none)\n\n"
        "## Location/World Cards\n(none)\n\n"
        "Identify contradictions in: character appearance, character locations, "
        "world rules, and timeline. Return a JSON array of objects with keys:\n"
        '  "type": one of character_appearance | character_location | world_rule | timeline\n'
        '  "description": specific description of the contradiction\n'
        '  "chapter_refs": array of chapter numbers involved\n'
        '  "severity": high | medium | low\n'
        '  "resolution_hint": one sentence suggestion for the author\n'
        "If no contradictions found, return an empty array []. "
        "Return ONLY the JSON array."
    )
    issues, meta = await complete_structured(
        system, user, coerce=coerce_continuity_issues,
        temperature=0.1, max_tokens=1200, label="continuity_depth_before",
    )
    return issues or []


async def run_all() -> dict:
    report = {}
    for label, case in CASES.items():
        old_issues = await run_old_prompt(case["chapter_summaries"])
        new_issues, _meta = await check_continuity(
            CHARACTER_PROFILES, case["chapter_summaries"], [], [],
        )
        expected = case["expected_type_keywords"]
        old_found = any(
            any(kw in str(i.get("type", "")).lower() for kw in expected) for i in old_issues
        ) if expected else (len(old_issues) == 0)
        new_found = any(
            any(kw in str(i.get("type", "")).lower() for kw in expected) for i in new_issues
        ) if expected else (len(new_issues) == 0)
        report[label] = {
            "expected_type_keywords": expected,
            "old_prompt_issues": old_issues,
            "new_prompt_issues": new_issues,
            "old_prompt_detected_expected": old_found,
            "new_prompt_detected_expected": new_found,
        }
        print(f"{label}: before={old_found} after={new_found} "
              f"(old={len(old_issues)} issue(s), new={len(new_issues)} issue(s))")
    return report


def main():
    report = asyncio.run(run_all())
    out_path = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "continuity_depth_report.json"
    out_path.write_text(json.dumps(report, indent=2))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
