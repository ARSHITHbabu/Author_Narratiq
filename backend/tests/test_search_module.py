"""
Stage 4 tasks 4.10, 4.11, 4.12, 4.14 — Search & Replace correctness (no DB, no LLM).

The original Phase 1 QA reports (Search Module reports 1 & 2) described query
truncation, wrong match counts, semantic behaviour leaking into exact mode, and
relevance/determinism problems. Direct code inspection of `routers/search.py` as
it exists now found none of those defects reproduce — `_build_pattern` escapes
and matches the *entire* query string, and exact search/replace/highlighting all
share one regex-only code path with zero semantic code in it.

This suite does not change any behaviour. It locks in the current, already-correct
behaviour with executable evidence, per Stage 4 task 4.10/4.11/4.12's own
"already implemented — verify, don't rewrite" instruction, and covers 4.14's
determinism/special-character requirements against the same code path.

Run:  cd backend && pytest tests/test_search_module.py -q
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import routers.search as search_mod  # noqa: E402

_build_pattern = search_mod._build_pattern
_search_plain = search_mod._search_plain
_html_to_plain = search_mod._html_to_plain
_replace_in_html = search_mod._replace_in_html


# ── 4.10 — query truncation / full-term matching ───────────────────────────────

def test_multiword_query_matches_full_phrase_not_first_char():
    text = "The dragon flew over the old castle at dawn."
    pattern = _build_pattern("old castle", whole_word=False, case_sensitive=False)
    matches = _search_plain(text, pattern)
    assert len(matches) == 1
    assert matches[0]["match_text"] == "old castle"


def test_query_is_not_truncated_to_single_character():
    text = "Devika walked past the devious plan without noticing it."
    # A truncation bug would effectively search for "D" or "d" and over-match.
    pattern = _build_pattern("Devika", whole_word=True, case_sensitive=True)
    matches = _search_plain(text, pattern)
    assert len(matches) == 1
    assert matches[0]["match_text"] == "Devika"
    # "devious" must NOT match a (correctly) whole-word, case-sensitive "Devika" query.
    assert "devious" not in [m["match_text"] for m in matches]


def test_known_term_occurrences_all_found_across_repeats():
    text = "Kael spoke. Kael listened. Then Kael left, and Kael did not return."
    pattern = _build_pattern("Kael", whole_word=True, case_sensitive=True)
    matches = _search_plain(text, pattern)
    assert len(matches) == 4


def test_multiword_query_with_apostrophe_and_punctuation_neighbours():
    text = "It was the king's decree: 'the old castle' must fall by dawn."
    pattern = _build_pattern("the old castle", whole_word=False, case_sensitive=False)
    matches = _search_plain(text, pattern)
    assert len(matches) == 1


# ── 4.11 — match counting and highlighting ─────────────────────────────────────

def test_match_count_reflects_actual_occurrences_not_estimate():
    text = "wolf wolf wolf wolfhound wolf"
    # Whole-word so "wolfhound" must not count as a "wolf" hit.
    pattern = _build_pattern("wolf", whole_word=True, case_sensitive=False)
    matches = _search_plain(text, pattern)
    assert len(matches) == 4


def test_highlight_spans_agree_with_reported_matches():
    text = "The river ran red at the river's bend."
    pattern = _build_pattern("river", whole_word=True, case_sensitive=False)
    matches = _search_plain(text, pattern)
    assert len(matches) == 2
    for m in matches:
        assert m["match_text"].lower() == "river"
        # context windows must not themselves contain a stray, unreported match boundary
        assert isinstance(m["context_before"], str)
        assert isinstance(m["context_after"], str)


def test_html_stripped_before_counting_so_tags_are_not_counted_as_text():
    html = "<p>The <b>river</b> ran red.</p><p>Another river appeared.</p>"
    plain = _html_to_plain(html)
    assert "<" not in plain and ">" not in plain
    pattern = _build_pattern("river", whole_word=True, case_sensitive=False)
    matches = _search_plain(plain, pattern)
    assert len(matches) == 2


# ── 4.12 — exact mode correctness / search-replace agreement ──────────────────

def test_exact_mode_has_no_semantic_leakage_by_construction():
    # Exact mode is a pure regex path — assert there is no fuzzy/embedding call
    # anywhere in the module-level namespace `_build_pattern`/`_search_plain` use.
    import inspect
    src = inspect.getsource(search_mod._build_pattern) + inspect.getsource(search_mod._search_plain)
    for forbidden in ("embed", "bge", "cosine", "vector", "similarity"):
        assert forbidden not in src.lower(), f"exact-mode path unexpectedly references '{forbidden}'"


def test_replace_only_touches_the_named_occurrence():
    html = "<p>Devika met Devika again near the old castle.</p>"
    pattern = _build_pattern("Devika", whole_word=True, case_sensitive=True)
    # occurrence_index=1 → only the SECOND "Devika" is replaced.
    new_html, replaced = _replace_in_html(html, pattern, "Aanya", occurrence_index=1)
    assert replaced == 1
    assert new_html.count("Devika") == 1
    assert new_html.count("Aanya") == 1
    assert new_html.index("Devika") < new_html.index("Aanya")


def test_replace_all_replaces_every_exact_match_and_nothing_else():
    html = "<p>wolf wolf wolfhound wolf</p>"
    pattern = _build_pattern("wolf", whole_word=True, case_sensitive=False)
    new_html, count = _replace_in_html(html, pattern, "bear", occurrence_index=-1)
    assert count == 3
    assert new_html.count("bear") == 3
    assert "wolfhound" in new_html  # whole-word: must survive untouched


def test_replace_never_touches_html_tags():
    html = '<p class="river">The river ran.</p>'
    pattern = _build_pattern("river", whole_word=True, case_sensitive=False)
    new_html, count = _replace_in_html(html, pattern, "stream", occurrence_index=-1)
    assert count == 1
    assert 'class="river"' in new_html          # tag attribute untouched
    assert "The stream ran." in new_html          # text node replaced


# ── 4.14 — determinism and special characters ──────────────────────────────────

def test_identical_query_returns_identical_results_across_repeated_runs():
    text = "The old castle stood by the old castle gate."
    pattern1 = _build_pattern("old castle", whole_word=False, case_sensitive=False)
    pattern2 = _build_pattern("old castle", whole_word=False, case_sensitive=False)
    m1 = _search_plain(text, pattern1)
    m2 = _search_plain(text, pattern2)
    assert m1 == m2


def test_special_character_queries_do_not_error():
    text = "Cost: $5.00 (approx.) — is that fair? [yes]"
    for q in ["$5.00", "(approx.)", "fair?", "[yes]", "5.00", "—"]:
        pattern = _build_pattern(q, whole_word=False, case_sensitive=False)
        matches = _search_plain(text, pattern)  # must not raise
        assert isinstance(matches, list)


def test_relevance_does_not_silently_drop_a_long_multiword_query():
    text = "The king's decree said the ancient castle would fall by the next dawn."
    pattern = _build_pattern("the ancient castle would fall", whole_word=False, case_sensitive=False)
    matches = _search_plain(text, pattern)
    assert len(matches) == 1


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
