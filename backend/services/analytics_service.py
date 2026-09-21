"""
Stage 5 task 5.15 — writing analytics, computed server-side.

Moves metric calculation from the frontend (where it lived entirely, with
two real bugs — see below) to the backend, and adds the explanation,
genre-aware benchmark, and story-intelligence integration the checklist's 6
issues call for. No new AI call for any of this — genre benchmarks are a
small hand-curated lookup table, and story-intelligence data is READ from
tables Stage 4/Phase-2 passes already populate (StoryEmotionalArc,
StoryPacingMap), never generated here.

Bugs fixed relative to the old frontend implementation:
  1. Syllable counting counted vowel LETTERS, not syllable groups
     (`word.replace(/[^aeiou]/gi, '').length` scored "queue" as 4 syllables;
     it has 1). Fixed with a vowel-GROUP count (consecutive vowels count
     once), a standard cheap heuristic — still not a dictionary lookup, but
     no new dependency, matching "do not overengineer".
  2. Dialogue-ratio matched curly quotes only. The live editor's
     `@tiptap/extension-typography` (frontend/components/editor/
     StoryEditor.tsx:65) auto-converts straight quotes to curly ones for
     content typed in-app, so this wasn't actively broken for normal
     authoring — but pasted or OCR-imported text can bypass that
     conversion. Fixed to match both quote styles.
"""
from __future__ import annotations

import re

# ── Genre-aware benchmarks (task 5.15, Medium 3/4) ──────────────────────────
# Small, hand-curated — not AI-generated, deliberately: a benchmark table is
# exactly the kind of thing that should be reviewable and stable, not
# regenerated per request.
_GENRE_BENCHMARKS = {
    "romance":       {"target_words": 80000,  "dialogue_ratio_range": (25, 45)},
    "thriller":      {"target_words": 90000,  "dialogue_ratio_range": (20, 35)},
    "mystery":       {"target_words": 80000,  "dialogue_ratio_range": (20, 35)},
    "fantasy":       {"target_words": 110000, "dialogue_ratio_range": (15, 30)},
    "science fiction": {"target_words": 100000, "dialogue_ratio_range": (15, 30)},
    "literary fiction": {"target_words": 90000, "dialogue_ratio_range": (10, 25)},
    "young adult":   {"target_words": 70000,  "dialogue_ratio_range": (20, 40)},
    "horror":        {"target_words": 80000,  "dialogue_ratio_range": (15, 30)},
}
_DEFAULT_BENCHMARK = {"target_words": 80000, "dialogue_ratio_range": (15, 35)}


def _resolve_benchmark(genre: str | None) -> dict:
    if not genre:
        return _DEFAULT_BENCHMARK
    return _GENRE_BENCHMARKS.get(genre.strip().lower(), _DEFAULT_BENCHMARK)


# ── Corrected metric calculations ───────────────────────────────────────────

_VOWEL_GROUP_RE = re.compile(r"[aeiouy]+", re.IGNORECASE)


def _count_syllables(word: str) -> int:
    """Vowel-GROUP count (consecutive vowels = one syllable), not vowel-
    LETTER count. Still a heuristic, not a dictionary lookup — but "queue"
    now correctly scores 1 group instead of 4 letters."""
    groups = _VOWEL_GROUP_RE.findall(word)
    n = len(groups)
    # Silent trailing 'e' doesn't add a syllable of its own in most English
    # words (e.g. "concise") — cheap, standard adjustment.
    if word.lower().endswith("e") and n > 1:
        n -= 1
    return max(1, n)


def readability_score(text: str) -> float:
    if not text.strip():
        return 0.0
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    words = text.strip().split()
    if not sentences or not words:
        return 0.0
    syllables = sum(_count_syllables(w) for w in words)
    fk = 206.835 - 1.015 * (len(words) / len(sentences)) - 84.6 * (syllables / len(words))
    return round(max(0.0, min(100.0, fk)), 1)


_DIALOGUE_RE = re.compile(r'["“][^"“”]*["”]')  # straight OR curly quotes


def dialogue_ratio(text: str) -> float:
    if not text:
        return 0.0
    dialogue_chars = sum(len(m.group()) for m in _DIALOGUE_RE.finditer(text))
    return round((dialogue_chars / len(text)) * 100, 1) if text else 0.0


def avg_sentence_length(text: str) -> float:
    sentences = [s for s in re.split(r"[.!?]+", text) if len(s.strip()) > 5]
    if not sentences:
        return 0.0
    total = sum(len(s.strip().split()) for s in sentences)
    return round(total / len(sentences), 1)


def readability_label(score: float) -> str:
    """Task 5.15 Medium 2 — explain the scale, not just the number (Flesch
    Reading Ease's own standard bands)."""
    if score >= 90:
        return "Very easy to read (5th grade level)"
    if score >= 70:
        return "Easy to read (7th-8th grade level)"
    if score >= 60:
        return "Standard (9th-10th grade level, general fiction)"
    if score >= 50:
        return "Fairly difficult (college level)"
    if score >= 30:
        return "Difficult (college graduate level)"
    return "Very difficult (professional/academic level)"


def compute_story_analytics(
    total_words: int, chapter_count: int, full_text: str,
    genre: str | None, db=None, story_id: str | None = None,
) -> dict:
    """
    Returns the full analytics payload: every metric paired with an
    explanation and, where applicable, a genre-aware benchmark comparison
    (task 5.15's Medium 1-5), plus story-intelligence data when it exists
    (Medium 6) — read-only, never generated here.
    """
    benchmark = _resolve_benchmark(genre)
    readability = readability_score(full_text)
    dialogue = dialogue_ratio(full_text)
    avg_sentence = avg_sentence_length(full_text)
    avg_words_per_chapter = round(total_words / chapter_count) if chapter_count else 0

    dlo, dhi = benchmark["dialogue_ratio_range"]
    if dialogue < dlo:
        dialogue_note = f"Below the typical {dlo}-{dhi}% range for this genre — more dialogue may help pacing."
    elif dialogue > dhi:
        dialogue_note = f"Above the typical {dlo}-{dhi}% range for this genre — consider more narrative/description."
    else:
        dialogue_note = f"Within the typical {dlo}-{dhi}% range for this genre."

    metrics = {
        "total_words": {
            "value": total_words,
            "explanation": "Total word count across all chapters.",
        },
        "chapters": {
            "value": chapter_count,
            "explanation": "Number of chapters saved for this story.",
        },
        "avg_words_per_chapter": {
            "value": avg_words_per_chapter,
            "explanation": "Total words divided by chapter count.",
        },
        "readability": {
            "value": readability,
            "explanation": (
                f"Flesch Reading Ease (0-100, higher = easier to read). {readability_label(readability)}. "
                "Estimated from sentence length and syllable count — a guide, not a precise measure."
            ),
        },
        "dialogue_ratio": {
            "value": dialogue,
            "explanation": (
                f"Percentage of manuscript text inside quoted dialogue. {dialogue_note}"
            ),
        },
        "avg_sentence_length": {
            "value": avg_sentence,
            "explanation": "Average words per sentence, across sentences longer than 5 characters.",
        },
        "word_count_progress": {
            "value": round(min(100, (total_words / benchmark["target_words"]) * 100), 1) if benchmark["target_words"] else 0,
            "explanation": f"Progress toward a typical {benchmark['target_words']:,}-word manuscript for this genre.",
            "target_words": benchmark["target_words"],
        },
    }

    # Task 5.15 Medium 6 — integrate story intelligence, read-only.
    story_intelligence = None
    if db is not None and story_id:
        from models import StoryEmotionalArc, StoryPacingMap
        arc = db.query(StoryEmotionalArc).filter(StoryEmotionalArc.story_id == story_id).first()
        pacing = db.query(StoryPacingMap).filter(StoryPacingMap.story_id == story_id).first()
        if arc or pacing:
            story_intelligence = {
                "emotional_arc_shape": arc.overall_arc_shape if arc else None,
                "dominant_emotions": arc.dominant_emotions if arc else None,
                "overall_pacing": pacing.overall_pacing if pacing else None,
                "pacing_score": pacing.pacing_score if pacing else None,
                "slow_zones": pacing.slow_zones if pacing else None,
            }

    return {
        "metrics": metrics,
        "story_intelligence": story_intelligence,
        "story_intelligence_available": story_intelligence is not None,
    }
