"""
Stage 5 task 5.14 — deterministic continuity citation validation (no DB, no LLM).

Pins the two-tier contract (see validate_continuity_citations' own docstring
in services/ai_service.py):
  Tier 1 (existence) — a fabricated/out-of-range/missing chapter_ref is
    SUPPRESSED outright (dropped from the output entirely).
  Tier 2 (groundedness) — a real chapter citation whose claim isn't found in
    that chapter's own structured data is FLAGGED (citation_verified=False),
    never suppressed — a genuine distinction the approved design requires.

Run: cd backend && pytest tests/test_continuity_citation_validation.py -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.ai_service import validate_continuity_citations, _arc_notes_str, _rel_changes_str  # noqa: E402

CHAPTER_SUMMARIES = [
    {"chapter_number": 1, "locations": ["Greyharn"], "characters_present": ["Mira"],
     "key_events": ["Mira arrives at the gate"]},
    {"chapter_number": 2, "locations": ["Hessa's shop"], "characters_present": ["Mira", "Hessa"],
     "key_events": ["Hessa reveals her sister was the Cartographer"]},
    {"chapter_number": 5, "locations": ["Cistern"], "characters_present": ["Mira", "Vell"],
     "key_events": ["Vell is revealed alive"]},
]


def test_no_citation_at_all_is_suppressed():
    issues = [{"description": "Some contradiction.", "chapter_refs": []}]
    result = validate_continuity_citations(issues, CHAPTER_SUMMARIES)
    assert result == []


def test_fabricated_out_of_range_chapter_is_suppressed():
    issues = [{"description": "Mira is in two places at once.", "chapter_refs": [47]}]
    result = validate_continuity_citations(issues, CHAPTER_SUMMARIES)
    assert result == []


def test_partially_fabricated_ref_set_is_suppressed():
    # One real chapter (1) plus one fake (99) — the whole finding is still
    # suppressed; a mix of real and fake refs is not "half trustworthy".
    issues = [{"description": "x", "chapter_refs": [1, 99]}]
    result = validate_continuity_citations(issues, CHAPTER_SUMMARIES)
    assert result == []


def test_real_chapter_grounded_claim_is_verified():
    issues = [{"description": "Mira arrives at the gate of Greyharn.", "chapter_refs": [1]}]
    result = validate_continuity_citations(issues, CHAPTER_SUMMARIES)
    assert len(result) == 1
    assert result[0]["citation_verified"] is True


def test_real_chapter_ungrounded_claim_is_flagged_not_suppressed():
    # Chapter 1 is real, but nothing in its structured data supports this
    # specific claim — Tier 2 failure: flagged, still shown.
    issues = [{"description": "A dragon burns down the entire city.", "chapter_refs": [1]}]
    result = validate_continuity_citations(issues, CHAPTER_SUMMARIES)
    assert len(result) == 1, "a Tier-2-only failure must still be shown, not suppressed"
    assert result[0]["citation_verified"] is False


def test_multi_chapter_citation_grounded_by_either_cited_chapter():
    issues = [{"description": "Vell is revealed alive at the Cistern.", "chapter_refs": [1, 5]}]
    result = validate_continuity_citations(issues, CHAPTER_SUMMARIES)
    assert len(result) == 1
    assert result[0]["citation_verified"] is True


def test_cross_chunk_citation_survives_when_validated_against_full_manuscript():
    """Regression guard for the real bug caught during implementation: a
    finding citing a chapter OUTSIDE some hypothetical chunk must still
    validate correctly when checked against the FULL chapter_summaries
    list — this is exactly why validation must run once, post-aggregation,
    never per-chunk."""
    issues = [{"description": "Vell is revealed alive at the Cistern.", "chapter_refs": [5]}]
    # Simulates the caller passing the FULL manuscript's summaries even
    # though chapter 5 might have been generated in a different "chunk"
    # than chapters 1-2 during the actual chunked continuity run.
    result = validate_continuity_citations(issues, CHAPTER_SUMMARIES)
    assert len(result) == 1
    assert result[0]["citation_verified"] is True


def test_empty_issues_list_returns_empty():
    assert validate_continuity_citations([], CHAPTER_SUMMARIES) == []


def test_original_fields_preserved_on_verified_issue():
    issues = [{"description": "Mira arrives at the gate of Greyharn.", "chapter_refs": [1],
               "type": "character_location", "severity": "high", "resolution_hint": "fix it"}]
    result = validate_continuity_citations(issues, CHAPTER_SUMMARIES)
    assert result[0]["type"] == "character_location"
    assert result[0]["severity"] == "high"
    assert result[0]["resolution_hint"] == "fix it"


# ── Task 5.14 — arc/relationship data wired into check_continuity's prompt ──

def test_arc_notes_str_formats_present_notes():
    s = {"character_arc_notes": {"c1": "grows bolder", "c2": "loses faith"}}
    out = _arc_notes_str(s)
    assert "grows bolder" in out and "loses faith" in out


def test_arc_notes_str_empty_when_absent_or_empty():
    assert _arc_notes_str({}) == ""
    assert _arc_notes_str({"character_arc_notes": {}}) == ""
    assert _arc_notes_str({"character_arc_notes": None}) == ""


def test_rel_changes_str_formats_present_changes():
    s = {"relationship_changes": [{"characters": ["Mira", "Vell"], "change": "reconcile"}]}
    out = _rel_changes_str(s)
    assert "Mira+Vell" in out and "reconcile" in out


def test_rel_changes_str_empty_when_absent_or_empty():
    assert _rel_changes_str({}) == ""
    assert _rel_changes_str({"relationship_changes": []}) == ""


def test_citation_groundedness_recognizes_arc_note_claims():
    # Tier 2 must now also ground a motivation/arc-based claim, not just
    # locations/characters/key_events (task 5.14's arc-notes wiring).
    summaries = [
        {"chapter_number": 1, "locations": [], "characters_present": ["Mira"],
         "key_events": [], "character_arc_notes": {"c1": "Mira swears off violence"}},
    ]
    issues = [{"description": "Mira swears off violence in chapter one.", "chapter_refs": [1]}]
    result = validate_continuity_citations(issues, summaries)
    assert result[0]["citation_verified"] is True


def test_citation_groundedness_recognizes_relationship_change_claims():
    summaries = [
        {"chapter_number": 1, "locations": [], "characters_present": [],
         "key_events": [], "relationship_changes": [{"characters": ["Mira", "Vell"], "change": "they reconcile"}]},
    ]
    issues = [{"description": "Mira and Vell they reconcile in this chapter.", "chapter_refs": [1]}]
    result = validate_continuity_citations(issues, summaries)
    assert result[0]["citation_verified"] is True


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
