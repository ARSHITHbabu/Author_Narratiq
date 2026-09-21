"""
Stage 4 task 4.5 — chapter summary depth (character_arc_notes, relationship_changes).

Part 1: pure coercer tests (no DB, no LLM) — pins the new optional-field
contract without touching the existing degradation counting that
test_extract_json_audit.py already guards (discarded stays == 6 for a
raw_summary-only response; these two fields never count toward it).

Part 2: a real end-to-end test — re-summarises one chapter of the shared
retrieval fixture through the actual Qwen + BGE-M3 pipeline
(summarize_and_embed_chapter) and asserts the new columns are always
present and well-typed on the persisted row, regardless of what content
the model produced. Content correctness is not asserted (that would be
tuning to one model's phrasing); *shape* correctness is.

Run: cd backend && pytest tests/test_chapter_arc_fields.py -q -s
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from services.ai_service import coerce_chapter_summary  # noqa: E402

FULL_SUMMARY = {
    "key_events": ["The archive burns"],
    "characters_present": ["Devika"],
    "locations": ["The Archive"],
    "timeline_markers": ["night"],
    "emotional_tone": "tense",
    "chapter_purpose": "Destroys the evidence",
    "raw_summary": "Devika burns the archive to stop the ledger being read.",
}


# ── Part 1: coercer contract ────────────────────────────────────────────────

def test_arc_and_relationship_fields_default_when_absent():
    value, discarded = coerce_chapter_summary(FULL_SUMMARY)
    assert value["character_arc_notes"] == {}
    assert value["relationship_changes"] == []
    assert discarded == 0, "new optional fields must not affect the existing discard count"


def test_arc_notes_parsed_when_present():
    value, discarded = coerce_chapter_summary({
        **FULL_SUMMARY,
        "character_arc_notes": {"Devika": "Chooses destruction over exposure."},
    })
    assert value["character_arc_notes"] == {"Devika": "Chooses destruction over exposure."}
    assert discarded == 0


def test_relationship_changes_parsed_when_present():
    value, discarded = coerce_chapter_summary({
        **FULL_SUMMARY,
        "relationship_changes": [
            {"characters": ["Devika", "Arun"], "change": "Trust broken over the ledger."}
        ],
    })
    assert value["relationship_changes"] == [
        {"characters": ["Devika", "Arun"], "change": "Trust broken over the ledger."}
    ]
    assert discarded == 0


def test_malformed_arc_notes_degrade_to_empty_not_a_crash():
    # Model returns a string instead of an object — must not raise, must not
    # count against discarded (this field is optional-and-forgiving by design).
    value, discarded = coerce_chapter_summary({**FULL_SUMMARY, "character_arc_notes": "not an object"})
    assert value["character_arc_notes"] == {}
    assert discarded == 0


def test_malformed_relationship_entries_are_filtered_not_fatal():
    value, discarded = coerce_chapter_summary({
        **FULL_SUMMARY,
        "relationship_changes": [
            {"characters": ["A", "B"], "change": "reconciled"},
            {"characters": "not a list", "change": "should be dropped"},
            {"change": "missing characters key — dropped"},
            "not even a dict",
        ],
    })
    assert value["relationship_changes"] == [{"characters": ["A", "B"], "change": "reconciled"}]
    assert discarded == 0


def test_still_matches_existing_degradation_contract_exactly():
    """Guards against silently widening or narrowing the pinned contract in
    test_extract_json_audit.py — raw_summary-only must still discard exactly 6."""
    value, discarded = coerce_chapter_summary({"raw_summary": "She burns the archive."})
    assert discarded == 6
    assert value["character_arc_notes"] == {}
    assert value["relationship_changes"] == []


# ── Part 2: real end-to-end persistence shape check ─────────────────────────

@pytest.mark.skipif(
    __import__("os").environ.get("SKIP_LLM_TESTS") == "1",
    reason="SKIP_LLM_TESTS=1 set — skipping live Qwen call",
)
def test_resummarize_real_chapter_persists_well_typed_new_columns():
    from database import SessionLocal
    from services.ai_service import summarize_and_embed_chapter
    from tests.fixtures.retrieval_fixture import build_fixture, cleanup_fixture, CHAPTERS
    from models import ChapterSummary

    db = SessionLocal()

    async def run():
        info = await build_fixture(db)
        # Chapter 5 has real arc movement (Vell revealed alive) — a fair test
        # of whether the model has something to report, without asserting
        # WHAT it reports.
        ch5 = next(c for c in CHAPTERS if c["number"] == 5)
        chapter_id = info["chapter_ids"][5]
        await summarize_and_embed_chapter(
            chapter_id, info["story_id"], 5, ch5["content"], db,
        )
        return info

    info = asyncio.run(run())
    try:
        cs = db.query(ChapterSummary).filter(
            ChapterSummary.chapter_id == info["chapter_ids"][5]
        ).first()
        assert cs is not None, "summarize_and_embed_chapter must have written a row"
        assert isinstance(cs.character_arc_notes, dict), "character_arc_notes must always be a dict, never null/missing"
        assert isinstance(cs.relationship_changes, list), "relationship_changes must always be a list, never null/missing"
        print(f"\n[4.5] Ch5 character_arc_notes = {cs.character_arc_notes}")
        print(f"[4.5] Ch5 relationship_changes = {cs.relationship_changes}")
        # Functional, not just structural: chapter 5 has unambiguous arc movement
        # (Vell revealed alive, Mira's refusal) — a prompt that reliably produces
        # nothing here would be structurally fine but functionally inert. This
        # is not content-tuning: it doesn't check WHAT was said, only that
        # something was captured when something clearly happened.
        assert cs.character_arc_notes or cs.relationship_changes, (
            "expected at least one arc note or relationship change for a chapter "
            "with unambiguous character/relationship movement — got neither"
        )
    finally:
        cleanup_fixture(db, info["story_id"], info["user_id"])
        db.close()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v", "-s"]))
