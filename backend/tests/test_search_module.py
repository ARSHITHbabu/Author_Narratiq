"""
Search & Replace correctness — Stage 4 tasks 4.10–4.14, rebuilt in Stage 12
remediation A9 (SEARCH-4 / SEARCH-5). No DB, no LLM.

Stage 4 locked in the regex path with tests over flattened text. Stage 12 found
that the flattened text (every tag → a space) disagreed with what the editor
highlights and with what replace rewrote, and that replace could corrupt the
manuscript (`&amp;` → `&X;` when replacing "amp"; Replace One changing the wrong
occurrence across formatting; the replacement inserted as raw HTML). Search and
replace now share one text model, `services/search_match.py`, mirrored by
`frontend/lib/searchMatch.ts`. Every original Stage 4 intent is kept below and
the A9 data-integrity cases are added.

The shared fixture file `fixtures/search_match_cases.json` is also asserted by
the Studio suite against the real editor, so both sides find the same matches.

Run:  cd backend && pytest tests/test_search_module.py -q
"""
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from services import search_match as sm  # noqa: E402
import routers.search as search_mod  # noqa: E402

CASES = json.loads((Path(__file__).parent / "fixtures" / "search_match_cases.json").read_text())["cases"]
TAGS = re.compile(r"<!--.*?-->|<[^>]*>", re.S)


def count(html, q, ww=False, cs=False):
    return len(sm.find_matches(html, q, ww, cs))


def p(text):
    return f"<p>{text}</p>"


class _Balance(HTMLParser):
    VOID = {"br", "hr", "img", "input", "meta", "link"}

    def __init__(self):
        super().__init__()
        self.stack, self.ok = [], True

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if not self.stack or self.stack.pop() != tag:
            self.ok = False


def balanced(html):
    b = _Balance()
    b.feed(html)
    b.close()
    return b.ok and not b.stack


# ── shared fixtures (backend half of the equivalence check) ──────────────────

@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_shared_fixture_counts(case):
    assert count(case["html"], case["query"], case["whole_word"], case["case_sensitive"]) == case["count"]


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_count_equals_replace_all_and_markup_stays_valid(case):
    new, n = sm.replace(case["html"], case["query"], "Ω", whole_word=case["whole_word"],
                        case_sensitive=case["case_sensitive"])
    assert n == case["count"]
    assert TAGS.findall(new) == TAGS.findall(case["html"])        # no tag touched
    assert balanced(new)
    assert count(new, case["query"], case["whole_word"], case["case_sensitive"]) == 0 or case["query"] == "Ω"


# ── 4.10 — full-term matching, no truncation ─────────────────────────────────

def test_multiword_query_matches_full_phrase_not_first_char():
    ms = sm.find_matches(p("The dragon flew over the old castle at dawn."), "old castle")
    assert [m.text for m in ms] == ["old castle"]


def test_query_is_not_truncated_to_single_character():
    ms = sm.find_matches(p("Devika walked past the devious plan."), "Devika", True, True)
    assert [m.text for m in ms] == ["Devika"]


def test_known_term_occurrences_all_found_across_repeats():
    assert count(p("Kael spoke. Kael listened. Then Kael left, and Kael did not return."), "Kael", True, True) == 4


def test_multiword_query_with_apostrophe_and_punctuation_neighbours():
    assert count(p("It was the king's decree: 'the old castle' must fall."), "the old castle") == 1


def test_long_multiword_query_is_not_dropped():
    assert count(p("The king's decree said the ancient castle would fall by dawn."),
                 "the ancient castle would fall") == 1


# ── 4.11 — counts and highlights ─────────────────────────────────────────────

def test_whole_word_excludes_partial_words():
    assert count(p("wolf wolf wolf wolfhound wolf"), "wolf", ww=True) == 4


def test_whole_word_is_off_by_default_in_the_api():
    from schemas import ExactSearchRequest, ReplaceRequest
    assert ExactSearchRequest(query="x").whole_word is False
    assert ReplaceRequest(query="x", replacement="y").whole_word is False


def test_matches_inside_formatting_are_found():
    html = "<p>The <b>ri</b>ver ran. <em>River</em> again.</p>"
    assert count(html, "river") == 2


def test_tags_are_never_counted_as_text():
    assert count('<p class="river">Not here.</p>', "river") == 0


def test_context_comes_from_the_matching_paragraph():
    m = sm.find_matches("<p>First paragraph.</p><p>The river bends.</p>", "river")[0]
    assert m.context_before == "The " and m.context_after == " bends."   # spacing kept, as the panel joins them


# ── 4.12 / A9 — replace integrity ────────────────────────────────────────────

def test_replacing_amp_never_corrupts_an_entity():
    html = p("Tom &amp; Jerry, ampersand.")
    new, n = sm.replace(html, "amp", "X")
    assert n == 1
    assert new == p("Tom &amp; Jerry, Xersand.")


def test_replacement_is_inserted_as_author_text_not_html():
    new, n = sm.replace(p("Hi there"), "Hi", "<b>hello</b>")
    assert n == 1
    assert new == p("&lt;b&gt;hello&lt;/b&gt; there")
    assert "<b>" not in new


def test_replace_one_across_formatting_changes_the_selected_occurrence():
    html = "<p>old <em>castle</em> then old castle</p>"
    first, n1 = sm.replace(html, "old castle", "X", occurrence_index=0)
    assert n1 == 1 and first == "<p>X<em></em> then old castle</p>"
    second, n2 = sm.replace(html, "old castle", "X", occurrence_index=1)
    assert n2 == 1 and second == "<p>old <em>castle</em> then X</p>"


def test_replace_one_targets_exactly_the_nth_occurrence():
    html = p("Devika met Devika again near Devika's house.")
    new, n = sm.replace(html, "Devika", "Aanya", whole_word=True, case_sensitive=True, occurrence_index=1)
    assert n == 1
    assert new == p("Devika met Aanya again near Devika's house.")


def test_replace_one_out_of_range_changes_nothing():
    html = p("one match")
    assert sm.replace(html, "match", "x", occurrence_index=5) == (html, 0)


def test_replace_inside_nested_formatting_keeps_tags_balanced():
    html = "<p>the <strong>old <em>cas</em></strong>tle stands</p>"
    new, n = sm.replace(html, "old castle", "keep")
    assert n == 1 and balanced(new) and TAGS.findall(new) == TAGS.findall(html)
    assert "keep" in new and "cas" not in new


def test_replace_keeps_links_and_attributes():
    html = '<p>See <a href="https://example.org/harbour">the harbour</a> now.</p>'
    new, n = sm.replace(html, "harbour", "port", whole_word=True)
    assert n == 1
    assert 'href="https://example.org/harbour"' in new and ">the port</a>" in new


def test_replace_never_crosses_paragraphs_or_line_breaks():
    for html in ("<p>end here.</p><p>Next one</p>", "<p>line one<br>two</p>"):
        new, n = sm.replace(html, "here. Next" if "Next" in html else "one two", "X")
        assert n == 0 and new == html


def test_replace_in_headings_and_lists():
    html = "<h2>The Harbour</h2><ul><li><p>harbour lights</p></li></ul>"
    new, n = sm.replace(html, "harbour", "port", whole_word=True)
    assert n == 2 and new == "<h2>The port</h2><ul><li><p>port lights</p></li></ul>"


def test_replace_entity_text_with_plain_text():
    new, n = sm.replace(p("a &amp; b &amp; c"), "&", "and")
    assert n == 2 and new == p("a and b and c")


def test_unicode_whole_word_replace():
    new, n = sm.replace(p("Café, cafés and the café."), "café", "bar", whole_word=True)
    assert n == 2 and new == p("bar, cafés and the bar.")


def test_malformed_markup_is_not_made_worse():
    html = "<p>open <b>bold text without close</p><p>bold again</p>"
    new, n = sm.replace(html, "bold", "X")
    assert n == 2
    assert TAGS.findall(new) == TAGS.findall(html)


def test_special_character_queries_do_not_error():
    html = p("Cost: $5.00 (approx.) — is that fair? [yes] a+b ^c")
    for q in ["$5.00", "(approx.)", "fair?", "[yes]", "5.00", "—", "a+b", "^c", "\\", "*"]:
        assert isinstance(sm.find_matches(html, q), list)


def test_identical_query_returns_identical_results():
    html = p("The old castle stood by the old castle gate.")
    assert sm.find_matches(html, "old castle") == sm.find_matches(html, "old castle")


def test_whitespace_collapses_like_the_editor():
    assert count("<p>two  spaces\nhere</p>", "two spaces here") == 1
    assert count("<p>   leading</p>", " leading") == 0


# ── exact mode stays deterministic ───────────────────────────────────────────

def test_exact_mode_has_no_semantic_leakage_by_construction():
    import inspect
    src = inspect.getsource(sm)
    for forbidden in ("embed", "bge", "cosine", "vector", "similarity"):
        assert forbidden not in src.lower()


def test_router_no_longer_carries_the_old_split_text_helpers():
    for name in ("_replace_in_html", "_build_pattern", "_search_plain"):
        assert not hasattr(search_mod, name), name


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
