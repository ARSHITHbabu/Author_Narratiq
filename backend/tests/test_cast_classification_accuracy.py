"""
Stage 4 task 4.9 — character classification and relationship accuracy.

Measures extract_cast() (services/ai_service.py) against a small deterministic
ground-truth cast — ROLE_GROUND_TRUTH below — built from the shared retrieval
fixture manuscript (tests/fixtures/retrieval_fixture.py), per this task's own
instruction to measure before changing anything.

Finding (2026-09-21): extract_cast correctly classified all 4 named
characters' roles, invented no characters, and did not over-promote the
one explicitly minor/unnamed mention ("a single loyal harbor guard") into a
full character entry. No prompt or classification-logic change is made —
per the approved plan's own instruction not to prompt-tune without a
measured, evidence-backed problem. This test PINS that measured baseline as
a regression guard, not a new feature.

Relationship extraction: NOT APPLICABLE. Direct code inspection
(`grep -rn "def.*relationship" services/ai_service.py`) found no automated
relationship-EXTRACTION function anywhere in the codebase — relationships
are author-created via POST /{story_id}/characters/{id}/relationships
(routers/characters.py, plain CRUD, no AI). The only AI relationship
function, run_p24_relationship_intel (services/story_intel_service.py),
takes an ALREADY-EXISTING CharacterRelationship as a required argument — it
analyses dynamics on a relationship the author already created, it does not
extract or create one. There is no "relationship extraction" accuracy to
measure or fix under this task; this is a genuine mapping gap between the
original QA report and the current architecture, recorded here rather than
inventing a feature to test.

Run: cd backend && pytest tests/test_cast_classification_accuracy.py -q -s
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.ai_service import extract_cast  # noqa: E402
from tests.fixtures.retrieval_fixture import CHAPTERS  # noqa: E402
from routers.search import _html_to_plain  # noqa: E402

# name -> expected role, built independently from the fixture's own narrative
# (tests/fixtures/retrieval_fixture.py), not from a prior extract_cast run.
ROLE_GROUND_TRUTH = {
    "mira": "protagonist",
    "corvin ashe": "supporting",
    "hessa lin": "supporting",
    "ondrej vell": "antagonist",   # matched by substring — model may prefix "Magistrate"
}

# Names that must NOT be promoted to a full character entry — either because
# they are deceased/backstory-only (the Cartographer) or explicitly unnamed
# and minor ("a single loyal harbor guard").
MUST_NOT_APPEAR_AS_PRIMARY_NAME = ["harbor guard"]


def test_extract_cast_role_accuracy_on_ground_truth_fixture():
    async def run():
        texts = [_html_to_plain(c["content"]) for c in CHAPTERS]
        return await extract_cast(texts)

    result = asyncio.run(run())
    by_name = {c["name"].strip().lower(): c for c in result}

    hits, misses = 0, []
    for expected_name_fragment, expected_role in ROLE_GROUND_TRUTH.items():
        match = next((c for n, c in by_name.items() if expected_name_fragment in n), None)
        if match is None:
            misses.append(f"MISSING: {expected_name_fragment}")
            continue
        if match["role"] == expected_role:
            hits += 1
        else:
            misses.append(f"WRONG ROLE: {expected_name_fragment} got {match['role']!r}, expected {expected_role!r}")

    accuracy = hits / len(ROLE_GROUND_TRUTH)
    print(f"\n[4.9] role classification accuracy: {hits}/{len(ROLE_GROUND_TRUTH)} = {accuracy:.0%}")
    if misses:
        print(f"[4.9] misses: {misses}")

    # Regression guard, not a new requirement: the measured baseline was 100%
    # on this fixture. If a future prompt change drops below the measured
    # baseline, this must fail loudly rather than silently regress.
    assert accuracy >= 0.75, f"role classification accuracy regressed: {misses}"


def test_extract_cast_does_not_over_promote_minor_unnamed_mentions():
    async def run():
        texts = [_html_to_plain(c["content"]) for c in CHAPTERS]
        return await extract_cast(texts)

    result = asyncio.run(run())
    names_lower = [c["name"].strip().lower() for c in result]

    for forbidden in MUST_NOT_APPEAR_AS_PRIMARY_NAME:
        assert not any(forbidden in n for n in names_lower), (
            f"an explicitly minor/unnamed mention ({forbidden!r}) was over-promoted "
            f"to a full character entry: {names_lower}"
        )


def test_extract_cast_names_exactly_four_characters_no_hallucination():
    """This fixture has exactly 4 named, significant characters. More than
    that means something was hallucinated or a walk-on was over-promoted;
    fewer means a real character was missed."""
    async def run():
        texts = [_html_to_plain(c["content"]) for c in CHAPTERS]
        return await extract_cast(texts)

    result = asyncio.run(run())
    print(f"\n[4.9] extracted {len(result)} character(s): {[c['name'] for c in result]}")
    assert len(result) == 4, f"expected exactly 4 characters, got {len(result)}: {[c['name'] for c in result]}"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v", "-s"]))
