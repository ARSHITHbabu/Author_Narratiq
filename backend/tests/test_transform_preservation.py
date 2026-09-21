"""
Stage 5 tasks 5.3/5.4/5.6/5.11 — deterministic preservation/lock/strength
primitives, plus the orchestrator's bounded repair-retry path (no DB, no
GPU — Qwen is stubbed via monkeypatch, matching test_author_style_and_copyright.py's
convention).

Run: cd backend && pytest tests/test_transform_preservation.py -q
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import ai_service  # noqa: E402
from services.transform_preservation import (  # noqa: E402
    build_preservation_clause,
    build_strength_clause,
    check_character_name_preservation,
    check_strength_violation,
    check_translation_name_consistency,
    mark_locked_segments,
    reconstruct_with_locks,
    verify_lock_byte_identity,
)


# ── Fakes (no real DB) ───────────────────────────────────────────────────────

class _FakeCharacter:
    def __init__(self, name, aliases=None):
        self.name = name
        self.aliases = aliases or []


class _FakeSettings:
    def __init__(self, preserve_character_names=True, preserve_tone=True, author_notes=""):
        self.preserve_character_names = preserve_character_names
        self.preserve_tone = preserve_tone
        self.author_notes = author_notes


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *a, **kw):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeDB:
    def __init__(self, characters=None, settings=None):
        self._characters = characters or []
        self._settings = settings

    def query(self, model):
        name = getattr(model, "__name__", "")
        if name == "Character":
            return _FakeQuery(self._characters)
        if name == "StoryPreservationSettings":
            return _FakeQuery([self._settings] if self._settings else [])
        return _FakeQuery([])


# ── 5.4 — Sentence-level locking ─────────────────────────────────────────────

def test_no_locked_ranges_returns_text_unmarked():
    marked, segments = mark_locked_segments("Hello world.", None)
    assert marked == "Hello world."
    assert segments == [{"locked": False, "text": "Hello world."}]


def test_locked_range_is_wrapped_and_unlocked_spans_survive():
    text = "AAA BBB CCC"
    marked, segments = mark_locked_segments(text, [{"start": 4, "end": 7}])
    assert marked == "[REWRITE]AAA [/REWRITE][KEEP]BBB[/KEEP][REWRITE] CCC[/REWRITE]"
    assert segments == [
        {"locked": False, "text": "AAA "},
        {"locked": True, "text": "BBB"},
        {"locked": False, "text": " CCC"},
    ]


def test_reconstruct_splices_original_bytes_for_locked_segments_never_model_echo():
    text = "AAA BBB CCC"
    _, segments = mark_locked_segments(text, [{"start": 4, "end": 7}])
    # Model's output claims to echo BBB as "XXX" inside [KEEP] — must be ignored;
    # only the [REWRITE] contents are trusted, locked segments always come from
    # the ORIGINAL captured text.
    model_output = "[REWRITE]zzz [/REWRITE][KEEP]XXX[/KEEP][REWRITE] yyy[/REWRITE]"
    reconstructed, shape_ok = reconstruct_with_locks(model_output, segments)
    assert shape_ok is True
    assert reconstructed == "zzz BBB yyy"
    assert "XXX" not in reconstructed


def test_reconstruct_reports_shape_failure_on_wrong_rewrite_count():
    text = "AAA BBB CCC"
    _, segments = mark_locked_segments(text, [{"start": 4, "end": 7}])
    # Model only returned one [REWRITE] block instead of the expected two.
    model_output = "[REWRITE]zzz[/REWRITE][KEEP]BBB[/KEEP]"
    reconstructed, shape_ok = reconstruct_with_locks(model_output, segments)
    assert shape_ok is False
    assert reconstructed is None


def test_verify_lock_byte_identity_true_when_locked_bytes_present():
    segments = [{"locked": True, "text": "Devika read it twice"}, {"locked": False, "text": "x"}]
    assert verify_lock_byte_identity(segments, "prefix Devika read it twice suffix") is True


def test_verify_lock_byte_identity_false_when_locked_bytes_altered():
    segments = [{"locked": True, "text": "Devika read it twice"}, {"locked": False, "text": "x"}]
    assert verify_lock_byte_identity(segments, "prefix Devika read it THRICE suffix") is False


def test_lock_byte_identity_exact_including_whitespace_and_punctuation():
    # The approved contract requires EXACT equality, not normalized/trimmed —
    # a locked segment with trailing punctuation must survive byte-for-byte.
    segments = [{"locked": True, "text": "Aanya was not going to get a fifth chance,"}]
    assert verify_lock_byte_identity(segments, "...Aanya was not going to get a fifth chance, and she knew it.") is True
    assert verify_lock_byte_identity(segments, "...Aanya was not going to get a fifth chance and she knew it.") is False


# ── 5.6 — Strength control ──────────────────────────────────────────────────

def test_build_strength_clause_known_levels_differ():
    light = build_strength_clause("light")
    strong = build_strength_clause("strong")
    assert "light" in light.lower()
    assert "strong" in strong.lower()
    assert light != strong


def test_build_strength_clause_unknown_level_falls_back_to_light():
    assert build_strength_clause("nonsense") == build_strength_clause("light")


def test_light_strength_flags_sentence_count_change():
    original = "One sentence. Two sentences."
    transformed = "One. Two. Three. Four."
    assert check_strength_violation(original, transformed, "light") is True


def test_light_strength_allows_same_sentence_count():
    original = "One sentence. Two sentences."
    transformed = "A single line. A second line."
    assert check_strength_violation(original, transformed, "light") is False


def test_strong_strength_never_flags_a_violation():
    original = "One sentence."
    transformed = "A completely different structure. With three. New sentences."
    assert check_strength_violation(original, transformed, "strong") is False


# ── 5.11 — Translation's own preservation semantics ─────────────────────────

def test_translation_name_kept_as_source_form_is_not_a_violation():
    glossary = {"Devika": "देविका"}
    original = "Devika walked in."
    transformed = "Devika entered the room."  # left untransliterated — legitimate
    result = check_translation_name_consistency(original, transformed, glossary)
    assert result["missing"] == []


def test_translation_name_transliterated_per_glossary_is_not_a_violation():
    glossary = {"Devika": "देविका"}
    original = "Devika walked in."
    transformed = "देविका entered the room."
    result = check_translation_name_consistency(original, transformed, glossary)
    assert result["missing"] == []


def test_translation_name_missing_entirely_is_flagged():
    glossary = {"Devika": "देविका"}
    original = "Devika walked in."
    transformed = "Someone entered the room."
    result = check_translation_name_consistency(original, transformed, glossary)
    assert result["missing"] == ["Devika"]


def test_translation_name_not_in_original_is_never_checked():
    glossary = {"Priya": "प्रिया"}
    original = "Devika walked in."  # Priya never appears
    transformed = "Devika entered the room."
    result = check_translation_name_consistency(original, transformed, glossary)
    assert result["missing"] == []


# ── 5.3 — Character-name preservation check + prompt clause ────────────────

def test_check_character_name_preservation_detects_a_dropped_name():
    db = _FakeDB(characters=[_FakeCharacter("Devika")])
    violations = check_character_name_preservation(
        "Devika walked into the hall.", "She walked into the hall.", "story-1", db,
    )
    assert violations == ["Devika"]


def test_check_character_name_preservation_passes_when_name_survives():
    db = _FakeDB(characters=[_FakeCharacter("Devika")])
    violations = check_character_name_preservation(
        "Devika walked into the hall.", "Devika entered the hall.", "story-1", db,
    )
    assert violations == []


def test_check_character_name_preservation_matches_aliases():
    db = _FakeDB(characters=[_FakeCharacter("Devika", aliases=["Dev"])])
    violations = check_character_name_preservation(
        "Devika walked in.", "Dev entered the room.", "story-1", db,
    )
    assert violations == []  # alias counts as the name surviving


def test_check_character_name_preservation_disabled_by_settings_returns_no_violations():
    db = _FakeDB(
        characters=[_FakeCharacter("Devika")],
        settings=_FakeSettings(preserve_character_names=False),
    )
    violations = check_character_name_preservation(
        "Devika walked in.", "She walked in.", "story-1", db,
    )
    assert violations == []


def test_check_character_name_preservation_no_story_or_db_is_a_noop():
    assert check_character_name_preservation("Devika walked in.", "She walked in.", None, None) == []
    assert check_character_name_preservation("Devika walked in.", "She walked in.", "story-1", None) == []


def test_build_preservation_clause_includes_character_names():
    db = _FakeDB(characters=[_FakeCharacter("Devika"), _FakeCharacter("Priya")])
    clause = build_preservation_clause("story-1", db)
    assert "Devika" in clause
    assert "Priya" in clause


def test_build_preservation_clause_includes_author_notes_when_present():
    db = _FakeDB(
        characters=[],
        settings=_FakeSettings(author_notes="Never mention the ending twist early."),
    )
    clause = build_preservation_clause("story-1", db)
    assert "Never mention the ending twist early." in clause


def test_build_preservation_clause_empty_without_story_or_db():
    assert build_preservation_clause(None, None) == ""


# ── Orchestrator: bounded repair retry on a detected name violation ────────

@pytest.mark.asyncio
async def test_run_constrained_transform_repairs_a_dropped_name_and_clears_the_violation(monkeypatch):
    db = _FakeDB(characters=[_FakeCharacter("Devika")])
    calls = {"n": 0}

    async def fake_complete(system, user, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return "She walked into the hall."  # drops "Devika" — a real violation
        return "Devika walked into the hall, calmer now."  # repaired on retry

    monkeypatch.setattr(ai_service, "_complete", fake_complete)
    result = await ai_service._run_constrained_transform(
        transform_type="tone", text="Devika walked into the hall.",
        temperature=0.5, max_tokens=100,
        builder_kwargs={"tone": "suspenseful", "genre_context": ""},
        story_id="story-1", db=db, strength="light", locked_ranges=None,
        change_check_target="", extra_user_context="",
    )
    assert calls["n"] == 2, "must retry exactly once on a detected violation, not zero or more than once"
    assert result["preservation_violations"] == []
    assert "Devika" in result["transformed"]
    assert result["failed"] is False


@pytest.mark.asyncio
async def test_run_constrained_transform_reports_violation_when_retry_also_fails(monkeypatch):
    db = _FakeDB(characters=[_FakeCharacter("Devika")])
    calls = {"n": 0}

    async def fake_complete(system, user, **kw):
        calls["n"] += 1
        return "She walked into the hall."  # drops the name every time

    monkeypatch.setattr(ai_service, "_complete", fake_complete)
    result = await ai_service._run_constrained_transform(
        transform_type="tone", text="Devika walked into the hall.",
        temperature=0.5, max_tokens=100,
        builder_kwargs={"tone": "suspenseful", "genre_context": ""},
        story_id="story-1", db=db, strength="light", locked_ranges=None,
        change_check_target="", extra_user_context="",
    )
    assert calls["n"] == 2, "retry is bounded to exactly one attempt, never looped further"
    assert result["preservation_violations"] == ["Devika"]
    assert result["failed"] is False  # a reported violation is not the same as a hard failure


@pytest.mark.asyncio
async def test_run_constrained_transform_no_retry_when_no_violation(monkeypatch):
    db = _FakeDB(characters=[_FakeCharacter("Devika")])
    calls = {"n": 0}

    async def fake_complete(system, user, **kw):
        calls["n"] += 1
        return "Devika walked into the hall, more slowly this time."

    monkeypatch.setattr(ai_service, "_complete", fake_complete)
    result = await ai_service._run_constrained_transform(
        transform_type="tone", text="Devika walked into the hall.",
        temperature=0.5, max_tokens=100,
        builder_kwargs={"tone": "suspenseful", "genre_context": ""},
        story_id="story-1", db=db, strength="light", locked_ranges=None,
        change_check_target="", extra_user_context="",
    )
    assert calls["n"] == 1, "no retry should ever fire when there is no violation to repair"
    assert result["preservation_violations"] == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
