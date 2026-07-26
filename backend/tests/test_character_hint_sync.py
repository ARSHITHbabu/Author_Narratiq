"""
Task 3.12 — character recognition synchronisation (Phase 2 Issue 9).

Covers the matching semantics and the reconciliation contract without a database
server, an LLM or a GPU: `resolve_hints_for_names` takes any object exposing the
query interface it uses, so a fake session is enough to pin the behaviour.

Run: python3 tests/test_character_hint_sync.py     (or under pytest)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.character_names import (  # noqa: E402
    HINT_SIMILARITY_THRESHOLD, hint_is_redundant, known_names, names_of,
    normalise_name, resolve_hints_for_names,
)

_results = []


def test(fn):
    _results.append(fn)
    return fn


# ── Fakes ────────────────────────────────────────────────────────────────────

class FakeCharacter:
    def __init__(self, name, aliases=None):
        self.name = name
        self.aliases = aliases or []


class FakeHint:
    _n = 0

    def __init__(self, suggested_name, dismissed=False):
        FakeHint._n += 1
        self.hint_id = f"hint-{FakeHint._n}"
        self.suggested_name = suggested_name
        self.is_dismissed = dismissed


class FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *_args, **_kwargs):
        return self

    def all(self):
        return self._rows


class FakeSession:
    """Returns the live hints it was given; records whether anything committed."""

    def __init__(self, hints):
        self._hints = hints
        self.commits = 0

    def query(self, _model):
        return FakeQuery([h for h in self._hints if not h.is_dismissed])

    def commit(self):
        self.commits += 1


def dismiss(hints, names):
    session = FakeSession(hints)
    dismissed = resolve_hints_for_names(session, "story-1", names)
    return session, dismissed


# ── Normalisation ────────────────────────────────────────────────────────────

@test
def test_normalisation_trims_collapses_and_casefolds():
    assert normalise_name("  Marek   Halvorsen ") == "marek halvorsen"
    assert normalise_name("MAREK") == "marek"
    assert normalise_name("marek") == normalise_name("Marek")
    assert normalise_name(None) == ""
    assert normalise_name("   ") == ""


@test
def test_known_names_covers_names_and_aliases():
    chars = [FakeCharacter("Devika Rao", ["Dev", " THE  ARCHIVIST "])]
    assert known_names(chars) == {"devika rao", "dev", "the archivist"}


@test
def test_names_of_returns_name_plus_aliases_and_drops_blanks():
    assert names_of(FakeCharacter("Ilse", ["", "  ", "Ilsa Vance"])) == ["Ilse", "Ilsa Vance"]


# ── Reconciliation: the four required match forms ────────────────────────────

@test
def test_exact_name_match_dismisses_the_hint():
    hints = [FakeHint("Marek")]
    _, dismissed = dismiss(hints, ["Marek"])
    assert len(dismissed) == 1
    assert hints[0].is_dismissed is True


@test
def test_case_insensitive_match_dismisses_the_hint():
    hints = [FakeHint("MAREK")]
    dismiss(hints, ["marek"])
    assert hints[0].is_dismissed is True


@test
def test_whitespace_normalised_match_dismisses_the_hint():
    hints = [FakeHint("  Marek   Halvorsen  ")]
    dismiss(hints, ["Marek Halvorsen"])
    assert hints[0].is_dismissed is True


@test
def test_alias_match_dismisses_the_hint():
    character = FakeCharacter("Devika Rao", ["The Archivist"])
    hints = [FakeHint("the archivist")]
    dismiss(hints, names_of(character))
    assert hints[0].is_dismissed is True


# ── Reconciliation: what must NOT be dismissed ───────────────────────────────

@test
def test_a_similar_but_distinct_name_is_never_dismissed():
    """The required negative case. 'Marekk' is 0.909 similar to 'Marek' — above the
    creation-time threshold — and must still survive reconciliation, because
    dismissing it would hide a genuinely different character."""
    hints = [FakeHint("Marekk")]
    _, dismissed = dismiss(hints, ["Marek"])
    assert dismissed == []
    assert hints[0].is_dismissed is False
    # And prove the pair really is above the creation threshold, so this test is
    # exercising the asymmetry rather than a trivially different pair.
    from difflib import SequenceMatcher
    ratio = SequenceMatcher(None, "marekk", "marek").ratio()
    assert ratio >= HINT_SIMILARITY_THRESHOLD, ratio


@test
def test_other_near_misses_survive_too():
    for hint_name, registered in [("Ilsa", "Ilse"), ("Devika Rao", "Devika Roy"),
                                  ("Teodor", "Teodora"), ("Cal", "Caleb")]:
        hints = [FakeHint(hint_name)]
        dismiss(hints, [registered])
        assert hints[0].is_dismissed is False, f"{hint_name} was wrongly dismissed by {registered}"


@test
def test_an_unrelated_name_is_untouched():
    hints = [FakeHint("Halloran")]
    _, dismissed = dismiss(hints, ["Devika Rao"])
    assert dismissed == []
    assert hints[0].is_dismissed is False


@test
def test_already_dismissed_hints_are_not_revisited():
    hints = [FakeHint("Marek", dismissed=True)]
    _, dismissed = dismiss(hints, ["Marek"])
    assert dismissed == []


@test
def test_blank_names_resolve_nothing():
    hints = [FakeHint("Marek")]
    for names in ([], [""], ["   "], [None]):
        _, dismissed = dismiss(hints, names)
        assert dismissed == []
    assert hints[0].is_dismissed is False


# ── Multiple hints for one name (the promote case) ───────────────────────────

@test
def test_every_hint_for_the_same_name_is_resolved_at_once():
    hints = [FakeHint("Marek"), FakeHint("marek"), FakeHint("Ilse")]
    _, dismissed = dismiss(hints, ["Marek"])
    assert len(dismissed) == 2
    assert hints[0].is_dismissed and hints[1].is_dismissed
    assert hints[2].is_dismissed is False


@test
def test_a_batch_of_names_resolves_all_of_them():
    hints = [FakeHint("Marek"), FakeHint("Ilse"), FakeHint("Halloran")]
    _, dismissed = dismiss(hints, ["Marek", "Ilse"])
    assert len(dismissed) == 2
    assert hints[2].is_dismissed is False


# ── Transaction ownership ────────────────────────────────────────────────────

@test
def test_reconciliation_never_commits_on_its_own():
    """The caller owns the transaction so the character mutation and the hint
    reconciliation land together — a half-applied state is exactly the defect."""
    hints = [FakeHint("Marek")]
    session, _ = dismiss(hints, ["Marek"])
    assert session.commits == 0


# ── Creation-side rules (the generous side) ──────────────────────────────────

@test
def test_creation_suppresses_exact_and_near_identical_hints():
    known = {"marek", "devika rao"}
    assert hint_is_redundant("Marek", known) is True
    assert hint_is_redundant("  MAREK  ", known) is True
    assert hint_is_redundant("Marekk", known) is True          # fuzzy, creation only
    assert hint_is_redundant("Halloran", known) is False


@test
def test_creation_and_reconciliation_share_one_normalisation():
    """The rules may differ in strictness, but never in how a name is normalised."""
    known = {normalise_name("  Devika   Rao ")}
    assert hint_is_redundant("devika rao", known) is True
    hints = [FakeHint("  DEVIKA   RAO  ")]
    dismiss(hints, ["Devika Rao"])
    assert hints[0].is_dismissed is True


# ── Runner ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    passed = failed = 0
    for fn in _results:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
            passed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL  {fn.__name__}: {exc}")
            failed += 1
    print(f"\n{passed}/{passed + failed} passed")
    sys.exit(1 if failed else 0)
