"""
Stage 5 task 5.15 — writing analytics (no DB, no LLM).

Pins the two real bugs fixed relative to the old frontend-only implementation
(see services/analytics_service.py's own module docstring), plus the
genre-benchmark resolution and story-intelligence integration added by the
approved design.

Run: cd backend && pytest tests/test_analytics_service.py -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.analytics_service import (  # noqa: E402
    _count_syllables,
    _resolve_benchmark,
    avg_sentence_length,
    compute_story_analytics,
    dialogue_ratio,
    readability_label,
    readability_score,
)


# ── Bug 1: vowel-GROUP syllable counting, not vowel-LETTER counting ────────

def test_queue_scores_one_syllable_not_four():
    # The old frontend regex counted vowel LETTERS: q-u-e-u-e -> 4. A
    # vowel-GROUP count treats the whole "ueue" run as one group -> 1.
    assert _count_syllables("queue") == 1


def test_concise_scores_two_syllables():
    # con-cise: two vowel groups ("o", "i"), trailing silent 'e' doesn't add
    # a third.
    assert _count_syllables("concise") == 2


def test_every_word_scores_at_least_one_syllable():
    assert _count_syllables("a") == 1
    assert _count_syllables("strengths") == 1


# ── Bug 2: dialogue-ratio must match straight AND curly quotes ─────────────

def test_dialogue_ratio_matches_straight_quotes():
    text = 'She said, "hello there" and left.'
    assert dialogue_ratio(text) > 0.0


def test_dialogue_ratio_matches_curly_quotes():
    text = "She said, “hello there” and left."
    assert dialogue_ratio(text) > 0.0


def test_dialogue_ratio_equal_for_equivalent_straight_and_curly_text():
    straight = 'She said, "hello there" and left.'
    curly = "She said, “hello there” and left."
    assert dialogue_ratio(straight) == dialogue_ratio(curly)


def test_dialogue_ratio_zero_for_no_dialogue():
    assert dialogue_ratio("No quotes in this sentence at all.") == 0.0


def test_dialogue_ratio_empty_text():
    assert dialogue_ratio("") == 0.0


# ── Readability score + label ───────────────────────────────────────────────

def test_readability_score_empty_text_is_zero():
    assert readability_score("") == 0.0
    assert readability_score("   ") == 0.0


def test_readability_score_in_bounds():
    text = "The cat sat on the mat. It was a sunny day. Birds sang in the trees."
    score = readability_score(text)
    assert 0.0 <= score <= 100.0


def test_readability_label_bands():
    assert "Very easy" in readability_label(95)
    assert "Easy" in readability_label(75)
    assert "Standard" in readability_label(65)
    assert "Fairly difficult" in readability_label(55)
    assert "Difficult" in readability_label(35)
    assert "Very difficult" in readability_label(10)


# ── Sentence length ──────────────────────────────────────────────────────────

def test_avg_sentence_length_basic():
    text = "This is four words. This one has six words total."
    length = avg_sentence_length(text)
    assert length > 0.0


def test_avg_sentence_length_ignores_short_fragments():
    # Fragments <=5 chars after stripping are excluded (e.g. leftover "Ok"
    # from abbreviations or list artifacts) so they don't skew the average.
    text = "Ok. This is a real sentence with several words in it."
    length = avg_sentence_length(text)
    assert length > 0.0


def test_avg_sentence_length_no_sentences_is_zero():
    assert avg_sentence_length("") == 0.0


# ── Genre benchmark resolution ──────────────────────────────────────────────

def test_known_genre_resolves_its_own_benchmark():
    bench = _resolve_benchmark("romance")
    assert bench["target_words"] == 80000
    assert bench["dialogue_ratio_range"] == (25, 45)


def test_genre_lookup_is_case_and_whitespace_insensitive():
    assert _resolve_benchmark("  Fantasy ") == _resolve_benchmark("fantasy")


def test_unknown_genre_falls_back_to_default():
    from services.analytics_service import _DEFAULT_BENCHMARK
    assert _resolve_benchmark("made-up genre") == _DEFAULT_BENCHMARK


def test_no_genre_falls_back_to_default():
    from services.analytics_service import _DEFAULT_BENCHMARK
    assert _resolve_benchmark(None) == _DEFAULT_BENCHMARK


# ── compute_story_analytics: full payload shape ─────────────────────────────

def test_compute_story_analytics_without_db_has_no_story_intelligence():
    result = compute_story_analytics(
        total_words=50000, chapter_count=10,
        full_text="A simple story. It has two sentences.",
        genre="thriller", db=None, story_id=None,
    )
    assert result["story_intelligence"] is None
    assert result["story_intelligence_available"] is False
    assert "readability" in result["metrics"]
    assert "dialogue_ratio" in result["metrics"]
    assert "word_count_progress" in result["metrics"]
    assert result["metrics"]["word_count_progress"]["target_words"] == 90000


def test_compute_story_analytics_avg_words_per_chapter():
    result = compute_story_analytics(
        total_words=10000, chapter_count=5, full_text="text", genre=None,
    )
    assert result["metrics"]["avg_words_per_chapter"]["value"] == 2000


def test_compute_story_analytics_zero_chapters_no_divide_by_zero():
    result = compute_story_analytics(
        total_words=0, chapter_count=0, full_text="", genre=None,
    )
    assert result["metrics"]["avg_words_per_chapter"]["value"] == 0


def test_dialogue_note_flags_below_range():
    result = compute_story_analytics(
        total_words=1000, chapter_count=1,
        full_text="No dialogue anywhere in this narration heavy text at all.",
        genre="romance",
    )
    note = result["metrics"]["dialogue_ratio"]["explanation"]
    assert "Below" in note


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
