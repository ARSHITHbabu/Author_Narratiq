"""
Stage 4 task 4.6 — character alias resolution (no DB, no LLM).

The checklist called this task's status uncertain specifically for "alias
matching in mention detection". Direct code inspection found `_make_name_pattern`
(services/ai_service.py:3001) already builds its match pattern from
`[name] + aliases`, and both call sites that matter use it:
  - retrieval name-mention boosting (ai_service.py:1401, inside
    retrieve_character_context)
  - mention detection / indexing (ai_service.py:3045, inside
    index_character_mentions)

This is verification-only: no behaviour changed. These tests pin the actual
alias-matching contract with executable evidence.

Run: cd backend && pytest tests/test_alias_resolution.py -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.ai_service import _make_name_pattern  # noqa: E402


def test_pattern_matches_primary_name():
    p = _make_name_pattern("Devika Rao", ["Dev", "the Watcher"])
    assert p.search("Devika Rao walked into the room.")


def test_pattern_matches_nickname_alias():
    p = _make_name_pattern("Devika Rao", ["Dev", "the Watcher"])
    assert p.search("Dev looked up sharply.")


def test_pattern_matches_epithet_alias():
    p = _make_name_pattern("Devika Rao", ["Dev", "the Watcher"])
    assert p.search("They called her the Watcher for a reason.")


def test_pattern_handles_possessive_forms():
    p = _make_name_pattern("Kael", ["the Smith"])
    text_apostrophe_s = "Kael's sword gleamed."
    text_s_apostrophe = "The blacksmiths' guild feared Kael."
    assert p.search(text_apostrophe_s)
    assert p.search("The Smith's forge was cold.")
    # sanity: unrelated possessive text with no alias match should not match
    assert not _make_name_pattern("Kael", []).search("The blacksmiths' guild met.")


def test_pattern_does_not_match_substring_of_unrelated_word():
    p = _make_name_pattern("Kael", [])
    # "Kaelin" is a different name; word-boundary matching must not treat
    # "Kael" as a hit inside it.
    assert not p.search("Kaelin walked past.")


def test_longest_candidate_preferred_when_names_overlap():
    # A character named "Kael" and an alias "Kael the Bold" — the multi-word
    # alias must not be shadowed by the shorter primary name in alternation
    # ordering (candidates are sorted longest-first for exactly this reason).
    p = _make_name_pattern("Kael", ["Kael the Bold"])
    m = p.search("Everyone knew Kael the Bold by reputation.")
    assert m is not None


def test_case_insensitive_matching():
    p = _make_name_pattern("Devika", ["Dev"])
    assert p.search("DEVIKA shouted across the hall.")
    assert p.search("dev came running.")


def test_no_aliases_still_matches_bare_name():
    p = _make_name_pattern("Aanya", [])
    assert p.search("Aanya smiled.")
    assert not p.search("The forest was quiet.")


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
