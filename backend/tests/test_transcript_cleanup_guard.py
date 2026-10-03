"""
Stage 12 Tranche 3 (A21) — the transcript clean-up may not drop the author's words.

The live model dropped a whole dictated opening sentence in 19 of 20 runs
(docs/testing/stage-12/tranche3/transcript-cleanup-*.json); the cleaned text is
what an author appends to a note. No model here: `_complete` is stubbed.

    DATABASE_URL=...narratiq_test pytest backend/tests/test_transcript_cleanup_guard.py -q
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from services import ai_service, audio_service  # noqa: E402
from services.audio_service import cleanup_kept_share  # noqa: E402

FIXTURE = ("Audio note for chapter 3. The lighthouse keeper, Marigold, lit the lantern at midnight. "
           "She wrote in the logbook that the fishing boats came home safely before the storm.")
# The model's real output (the opening sentence is gone).
DROPPED = ("The lighthouse keeper, Marigold, lit the lantern at midnight. She wrote in the logbook "
           "that the fishing boats came home safely before the storm.")
FILLERS = "um so the the scene opens at the docks you know and uh Mara is waiting for the ferry"
FILLERS_CLEAN = "The scene opens at the docks. Mara is waiting for the ferry."


def _run(monkeypatch, raw: str, model_output: str | Exception) -> str:
    async def fake_complete(**_kw):
        if isinstance(model_output, Exception):
            raise model_output
        return model_output
    monkeypatch.setattr(ai_service, "_complete", fake_complete)
    return asyncio.run(audio_service.clean_transcript(raw))


def test_dropped_sentence_keeps_the_raw_transcript(monkeypatch):
    assert cleanup_kept_share(FIXTURE, DROPPED) < audio_service.CLEANUP_MIN_KEPT
    assert _run(monkeypatch, FIXTURE, DROPPED) == FIXTURE


def test_filler_removal_and_punctuation_are_kept(monkeypatch):
    # Dropping a conjunction ("and") with the fillers is legitimate: 10 of 11 words kept.
    assert cleanup_kept_share(FILLERS, FILLERS_CLEAN) >= audio_service.CLEANUP_MIN_KEPT
    assert _run(monkeypatch, FILLERS, FILLERS_CLEAN) == FILLERS_CLEAN


def test_dialogue_punctuation_is_kept(monkeypatch):
    raw = "Then Ada says I never wanted the lighthouse. And Wren answers you never wanted anything"
    clean = 'Then Ada says, "I never wanted the lighthouse." And Wren answers, "You never wanted anything."'
    assert _run(monkeypatch, raw, clean) == clean


def test_long_dictation_is_not_truncated(monkeypatch):
    # Only the first 3000 characters reach the model; its cleaned text must not
    # replace a transcript whose later part it never saw.
    raw = " ".join(f"Sentence {i} about the harbour, the ferry and lantern number {i}." for i in range(120))
    assert len(raw) > 3000
    cleaned = raw[:3000]
    assert _run(monkeypatch, raw, cleaned) == raw


@pytest.mark.parametrize("output", ["", "   ", RuntimeError("model down")])
def test_empty_or_failed_cleanup_keeps_raw(monkeypatch, output):
    assert _run(monkeypatch, FIXTURE, output) == FIXTURE


def test_short_transcript_skips_the_model(monkeypatch):
    assert _run(monkeypatch, "four words only here", "should not be used") == "four words only here"


def test_accented_words_count_as_words():
    assert cleanup_kept_share("Café déjà vu, naïve Zoë", "café déjà vu naïve Zoë") == 1.0
