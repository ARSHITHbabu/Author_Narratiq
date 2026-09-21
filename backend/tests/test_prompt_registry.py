"""
Stage 5 task 5.1 — prompt versioning registry (no DB, no LLM).

Per the approved correction: a version identifier must resolve to ACTUAL
prompt content, not merely a logged label. These tests pin that contract:
  - v1 is byte-identical to the frozen pre-Stage-5 baseline
  - selecting a version actually changes which builder runs (not just a label)
  - an unknown version fails safe (falls back, never silently invents content)
  - a fallback that also lacks the transform_type is a hard configuration
    error, not a silent further degradation

Run: cd backend && pytest tests/test_prompt_registry.py -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from services.prompt_registry import (  # noqa: E402
    resolve_prompt_version, register_version, PROMPT_REGISTRY,
)

# The exact pre-Stage-5 baseline strings, copied verbatim from the functions
# as they existed at the close of Stage 4 (git history has the originals).
_EXPECTED_V1 = {
    "tone": (
        "You are a literary writing coach. Rewrite the passage in a dark tone. "
        "Keep all events and characters identical — only change style, word choice, and mood. "
        "Return ONLY the rewritten passage."
    ),
    "emotion": (
        "You are a fiction editor. Rewrite the passage so it deeply conveys joy at "
        "high intensity using sensory detail and interiority — not emotional labels. "
        "Return ONLY the rewritten passage."
    ),
    "style": (
        "Rewrite the passage in the literary style of noir — capturing their characteristic "
        "sentence structure, diction, rhythm, and voice. Return ONLY the rewritten passage."
    ),
    "translate": (
        "You are a professional literary translator. Translate from en to fr, "
        "preserving tone, style, and literary quality. Return ONLY the translation."
    ),
}


def test_v1_tone_byte_identical_to_frozen_baseline():
    builder, resolved = resolve_prompt_version("tone", "v1", "v1")
    assert resolved == "v1"
    assert builder(tone="dark", genre_context="") == _EXPECTED_V1["tone"]


def test_v1_emotion_byte_identical_to_frozen_baseline():
    builder, _ = resolve_prompt_version("emotion", "v1", "v1")
    assert builder(emotion="joy", intensity="high", genre_context="") == _EXPECTED_V1["emotion"]


def test_v1_style_byte_identical_to_frozen_baseline():
    builder, _ = resolve_prompt_version("style", "v1", "v1")
    assert builder(style="noir", genre_context="") == _EXPECTED_V1["style"]


def test_v1_translate_byte_identical_to_frozen_baseline():
    builder, _ = resolve_prompt_version("translate", "v1", "v1")
    assert builder(source_language="en", target_language="fr") == _EXPECTED_V1["translate"]


def test_age_adapt_and_suggestions_v1_produce_nonempty_deterministic_output():
    builder, _ = resolve_prompt_version("age_adapt", "v1", "v1")
    out1 = builder(target_age="ya", genre_context="")
    out2 = builder(target_age="ya", genre_context="")
    assert out1 == out2 and out1  # pure function: same input, same output, every time

    builder, _ = resolve_prompt_version("suggestions", "v1", "v1")
    assert builder() == builder()


def test_selecting_a_version_actually_changes_the_builder_not_just_a_label():
    """The core contract of this task: version selection must change WHICH
    FUNCTION RUNS, proven here by registering a real, distinct v2 builder and
    confirming its actual return value differs from v1's — not a relabeled
    v1 output."""
    if "v2-test-only" not in PROMPT_REGISTRY:
        register_version("v2-test-only", {"tone": lambda **kw: "COMPLETELY DIFFERENT CONTENT"})

    v1_builder, v1_resolved = resolve_prompt_version("tone", "v1", "v1")
    v2_builder, v2_resolved = resolve_prompt_version("tone", "v2-test-only", "v1")

    assert v1_resolved == "v1"
    assert v2_resolved == "v2-test-only"
    assert v1_builder(tone="dark", genre_context="") != v2_builder(tone="dark", genre_context="")
    assert v2_builder(tone="dark", genre_context="") == "COMPLETELY DIFFERENT CONTENT"


def test_unknown_version_fails_safe_to_the_configured_fallback():
    builder, resolved = resolve_prompt_version("tone", "v999-does-not-exist", "v1")
    assert resolved == "v1", "an unknown version must resolve to the real fallback, not itself"
    # And the content is the REAL v1 content, not empty/arbitrary:
    assert builder(tone="dark", genre_context="") == _EXPECTED_V1["tone"]


def test_unknown_transform_type_also_fails_safe():
    # v1 has no "not_a_real_transform_type" entry, so falling back to itself
    # for the same missing key must raise — there is nothing safe to fall
    # back TO, which is exactly the "hard configuration bug" case.
    with pytest.raises(RuntimeError):
        resolve_prompt_version("not_a_real_transform_type", "v1", "v1")


def test_register_version_refuses_to_silently_overwrite_an_existing_version():
    with pytest.raises(RuntimeError):
        register_version("v1", {"tone": lambda **kw: "should never be allowed"})
    # v1's real content must survive the attempted overwrite:
    builder, _ = resolve_prompt_version("tone", "v1", "v1")
    assert builder(tone="dark", genre_context="") == _EXPECTED_V1["tone"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
