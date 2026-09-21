"""
Stage 5 task 5.14 — deterministic citation validation extended from
continuity-check to the manuscript report (no DB, no LLM).

Pins validate_manuscript_report_citations' contract (see its own docstring
in services/ai_service.py): a finding whose chapter references are ALL
fabricated is dropped; a finding with at least one real reference keeps
only the real ones. Measures false positives (a real, correctly-cited
finding wrongly suppressed) and false negatives (a fabricated-only finding
wrongly kept) with controlled fixtures, per the required "measure false
positives before/after" instruction — "before" here is the unvalidated
raw LLM output (every finding kept regardless of citation validity, the
prior behavior), "after" is this function's output.

Run: cd backend && pytest tests/test_manuscript_report_citations.py -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.ai_service import validate_manuscript_report_citations  # noqa: E402

REAL_CHAPTERS = {1, 2, 3, 4, 5}


def _raw_report(**overrides) -> dict:
    base = {
        "character_arcs": [],
        "pacing": {"slow_chapters": [], "intense_chapters": [], "assessment": "steady"},
        "unresolved_threads": [],
        "strengths": [],
        "improvements": [],
        "themes": [],
        "stakes": None,
    }
    base.update(overrides)
    return base


# ── Baseline "before": everything survives regardless of citation validity ──

def test_before_validation_every_finding_would_be_kept_baseline_check():
    # Sanity check on the fixture itself, not the function under test — this
    # documents what "before" (raw model output, no validation) looked like:
    # a fabricated chapter 99 reference would reach the author unfiltered.
    raw = _raw_report(strengths=[{"text": "Great pacing", "chapters": [99]}])
    assert raw["strengths"][0]["chapters"] == [99]   # unvalidated — the old behavior


# ── character_arcs ───────────────────────────────────────────────────────────

def test_character_arc_with_real_chapters_is_kept_and_unchanged_otherwise():
    raw = _raw_report(character_arcs=[
        {"name": "Devika", "appears_in": [1, 3], "arc_summary": "grows bolder", "completeness": "partial"},
    ])
    cleaned, suppressed = validate_manuscript_report_citations(raw, REAL_CHAPTERS)
    assert suppressed == 0
    assert cleaned["character_arcs"][0]["appears_in"] == [1, 3]
    assert cleaned["character_arcs"][0]["name"] == "Devika"  # non-citation fields untouched


def test_character_arc_with_partially_fabricated_chapters_keeps_only_real_ones():
    raw = _raw_report(character_arcs=[
        {"name": "Devika", "appears_in": [1, 99], "arc_summary": "x", "completeness": "partial"},
    ])
    cleaned, suppressed = validate_manuscript_report_citations(raw, REAL_CHAPTERS)
    assert suppressed == 0   # at least one real ref survives — not a suppression
    assert cleaned["character_arcs"][0]["appears_in"] == [1]


def test_character_arc_with_entirely_fabricated_chapters_is_suppressed():
    raw = _raw_report(character_arcs=[
        {"name": "Ghost", "appears_in": [42, 99], "arc_summary": "x", "completeness": "partial"},
    ])
    cleaned, suppressed = validate_manuscript_report_citations(raw, REAL_CHAPTERS)
    assert suppressed == 1
    assert cleaned["character_arcs"] == []


# ── pacing — filtered, not suppressed (aggregate field, not a single claim) ──

def test_pacing_chapters_are_filtered_to_real_ones():
    raw = _raw_report(pacing={"slow_chapters": [2, 50], "intense_chapters": [4, 4], "assessment": "x"})
    cleaned, suppressed = validate_manuscript_report_citations(raw, REAL_CHAPTERS)
    assert cleaned["pacing"]["slow_chapters"] == [2]
    assert cleaned["pacing"]["intense_chapters"] == [4, 4]


# ── unresolved_threads ───────────────────────────────────────────────────────

def test_thread_with_real_introduced_in_and_chapters_is_kept():
    raw = _raw_report(unresolved_threads=[
        {"description": "the missing letter", "introduced_in": 1, "chapters": [1, 3]},
    ])
    cleaned, suppressed = validate_manuscript_report_citations(raw, REAL_CHAPTERS)
    assert suppressed == 0
    assert cleaned["unresolved_threads"][0]["chapters"] == [1, 3]


def test_thread_with_fabricated_introduced_in_but_real_chapters_is_kept_and_repaired():
    raw = _raw_report(unresolved_threads=[
        {"description": "x", "introduced_in": 99, "chapters": [2, 3]},
    ])
    cleaned, suppressed = validate_manuscript_report_citations(raw, REAL_CHAPTERS)
    assert suppressed == 0
    assert cleaned["unresolved_threads"][0]["introduced_in"] == 2   # repaired from the real chapters list


def test_thread_entirely_fabricated_is_suppressed():
    raw = _raw_report(unresolved_threads=[
        {"description": "x", "introduced_in": 99, "chapters": [98, 99]},
    ])
    cleaned, suppressed = validate_manuscript_report_citations(raw, REAL_CHAPTERS)
    assert suppressed == 1
    assert cleaned["unresolved_threads"] == []


# ── strengths / improvements ─────────────────────────────────────────────────

def test_strength_with_no_valid_chapters_is_suppressed():
    raw = _raw_report(strengths=[{"text": "Great pacing", "chapters": [99]}])
    cleaned, suppressed = validate_manuscript_report_citations(raw, REAL_CHAPTERS)
    assert suppressed == 1
    assert cleaned["strengths"] == []


def test_improvement_with_no_chapters_at_all_is_suppressed():
    # Mirrors continuity's Tier-1 "no chapter_refs at all" suppression case.
    raw = _raw_report(improvements=[{"text": "Vary sentence structure in the opening", "chapters": []}])
    cleaned, suppressed = validate_manuscript_report_citations(raw, REAL_CHAPTERS)
    assert suppressed == 1
    assert cleaned["improvements"] == []


def test_improvement_with_valid_chapters_survives_with_its_text_intact():
    raw = _raw_report(improvements=[{"text": "Tighten the pacing in the middle act", "chapters": [3]}])
    cleaned, suppressed = validate_manuscript_report_citations(raw, REAL_CHAPTERS)
    assert suppressed == 0
    assert cleaned["improvements"][0]["text"] == "Tighten the pacing in the middle act"


# ── themes ───────────────────────────────────────────────────────────────────

def test_theme_with_fabricated_chapters_only_is_suppressed():
    raw = _raw_report(themes=[{"theme": "isolation", "chapters": [77]}])
    cleaned, suppressed = validate_manuscript_report_citations(raw, REAL_CHAPTERS)
    assert suppressed == 1
    assert cleaned["themes"] == []


def test_theme_with_real_chapters_is_kept():
    raw = _raw_report(themes=[{"theme": "isolation", "chapters": [1, 2]}])
    cleaned, suppressed = validate_manuscript_report_citations(raw, REAL_CHAPTERS)
    assert suppressed == 0
    assert cleaned["themes"][0]["chapters"] == [1, 2]


# ── stakes escalation points ─────────────────────────────────────────────────

def test_stakes_escalation_point_with_fabricated_chapter_is_dropped_but_stakes_survives():
    raw = _raw_report(stakes={
        "summary": "the town's survival is at risk",
        "escalation": [{"chapter": 2, "note": "threat becomes explicit"}, {"chapter": 99, "note": "fabricated"}],
    })
    cleaned, suppressed = validate_manuscript_report_citations(raw, REAL_CHAPTERS)
    assert suppressed == 1
    assert cleaned["stakes"]["summary"] == "the town's survival is at risk"
    assert cleaned["stakes"]["escalation"] == [{"chapter": 2, "note": "threat becomes explicit"}]


def test_stakes_none_is_passed_through_untouched():
    raw = _raw_report(stakes=None)
    cleaned, suppressed = validate_manuscript_report_citations(raw, REAL_CHAPTERS)
    assert suppressed == 0
    assert cleaned["stakes"] is None


# ── Aggregate false-positive / false-negative measurement ──────────────────

def test_mixed_report_false_positive_and_false_negative_count():
    """A single report mixing genuinely-cited and fabricated-only findings —
    the deterministic measurement the approved corrections asked for."""
    raw = _raw_report(
        character_arcs=[
            {"name": "Real", "appears_in": [1, 2], "arc_summary": "x", "completeness": "partial"},
            {"name": "Fake", "appears_in": [50], "arc_summary": "x", "completeness": "partial"},
        ],
        strengths=[
            {"text": "real", "chapters": [3]},
            {"text": "fake", "chapters": [60]},
        ],
        improvements=[
            {"text": "real", "chapters": [4]},
        ],
    )
    cleaned, suppressed = validate_manuscript_report_citations(raw, REAL_CHAPTERS)
    # False negatives after validation: fabricated-only findings that still
    # leaked through — must be zero.
    assert len(cleaned["character_arcs"]) == 1 and cleaned["character_arcs"][0]["name"] == "Real"
    assert len(cleaned["strengths"]) == 1 and cleaned["strengths"][0]["text"] == "real"
    # False positives after validation: genuinely-cited findings wrongly
    # dropped — must be zero.
    assert len(cleaned["improvements"]) == 1
    assert suppressed == 2   # exactly the two fabricated-only findings


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
