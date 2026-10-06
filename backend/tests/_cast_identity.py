"""
Character IDENTITY check for the retrieval-fixture cast (Stage 12.3, owner-approved
cast-test treatment, 2026-10-06).

Identity is a hard correctness requirement: every named character of the fixture
appears exactly once — never lost, never merged into someone else, never replaced
by an invented character. Only the Cartographer (dead before the story begins) may
appear as an extra, and only labelled off-page.

The presence LABEL of a living character (on_page vs historical) is deliberately
NOT part of identity: the model occasionally labels the living antagonist
`historical` (CAST-H10, owner-accepted model variability, 2026-10-03; measured
21/25 correct in docs/testing/stage-12/tranche3/cast-variability-probe.json). That
behaviour is measured separately and must never turn into a lost or merged
character, which is what this check guards.

Shared by the live test (test_cast_classification_accuracy.py) and the
deterministic replay of the observed failure shape (test_cast_t2a.py).
"""
from __future__ import annotations

# name fragment (lower case, matched as a substring so "Magistrate Ondrej Vell"
# and "Mira Okoye" count) -> the fixture's narrative fact.
EXPECTED_CHARACTERS = ("mira", "corvin ashe", "hessa lin", "ondrej vell")

# The only extra entry allowed, and only as an off-page figure.
PERMITTED_OFF_PAGE_EXTRA = "cartographer"
OFF_PAGE = ("historical", "referenced")

_MERGE_FLAGS = ("_possible_combined_with", "_possible_duplicate_in_batch")


def identity_problems(cast: list[dict]) -> list[str]:
    """Every way `cast` breaks character identity on the retrieval fixture.
    Empty list = identity correct. Presence labels of the expected characters
    are not judged here (CAST-H10)."""
    problems: list[str] = []
    names = [str(c.get("name") or "").strip().lower() for c in cast]

    for frag in EXPECTED_CHARACTERS:
        hits = [n for n in names if frag in n]
        if not hits:
            problems.append(f"LOST: no entry for {frag!r}")
        elif len(hits) > 1:
            problems.append(f"DUPLICATED: {frag!r} appears {len(hits)} times: {hits}")

    for c, n in zip(cast, names):
        matched = [frag for frag in EXPECTED_CHARACTERS if frag in n]
        if len(matched) > 1:
            problems.append(f"MERGED: one entry {c.get('name')!r} carries {matched}")
        if not matched:
            if PERMITTED_OFF_PAGE_EXTRA in n:
                if c.get("presence") not in OFF_PAGE:
                    problems.append(f"CARTOGRAPHER ON PAGE: {c.get('name')!r} presence={c.get('presence')!r}")
            else:
                problems.append(f"INVENTED: unexpected character {c.get('name')!r}")
        if c.get("presence") in OFF_PAGE and c.get("role") == "protagonist":
            problems.append(f"OFF-PAGE PROTAGONIST: {c.get('name')!r}")
        if matched:
            for flag in _MERGE_FLAGS:
                if c.get(flag):
                    problems.append(f"MERGE FLAG: {c.get('name')!r} {flag}={c.get(flag)!r}")
    return problems
