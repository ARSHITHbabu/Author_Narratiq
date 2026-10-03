"""
Stage 12.1 (PA-H10 / PA-H11) — a chapter summary covers the WHOLE chapter.

generate_chapter_summary used to send only `chapter_text[:8000]` (about the first
1,400 words), so in a realistic 3,000–5,000-word chapter every later event and
revelation was missing from the summary and from everything built on it. No
model here: the structured call and the merge call are stubbed; the real
tokenizer sizes the windows.

    DATABASE_URL=...narratiq_test pytest backend/tests/test_chapter_summary_windows.py -q
"""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


from services import ai_service  # noqa: E402
from services.ai_service import _summary_windows, count_tokens  # noqa: E402
from config import settings  # noqa: E402

SENTENCE = "Wren walked the harbour wall at dusk and counted the boats coming home one by one. "
LATE = "At the very end Tobin confessed that Liesel Marr had ordered the lamp's oil line cut."


class _Meta:
    degraded = False
    discarded = 0


def _run(monkeypatch, text, merge_output="MERGED SUMMARY", merge_raises=False, fail_window=None):
    calls = []

    async def fake_structured(system, user, **kw):
        calls.append(user)
        if fail_window is not None and len(calls) - 1 == fail_window:
            return None, _Meta()
        events = ["the confession about the oil line"] if LATE in user else [f"part event {len(calls)}"]
        return ({"key_events": events, "characters_present": ["Wren"], "locations": ["harbour"],
                 "timeline_markers": [], "emotional_tone": "tense", "chapter_purpose": "build tension",
                 "raw_summary": f"summary of part {len(calls)}", "character_arc_notes": {"Wren": f"note {len(calls)}"},
                 "relationship_changes": []}, _Meta())

    async def fake_complete(**kw):
        if merge_raises:
            raise RuntimeError("model down")
        return merge_output
    monkeypatch.setattr(ai_service, "complete_structured", fake_structured)
    monkeypatch.setattr(ai_service, "_complete", fake_complete)
    try:
        result = asyncio.run(ai_service.generate_chapter_summary(text, 7))
    except ValueError as exc:
        result = exc
    return result, calls


def test_short_chapter_is_one_call_with_the_full_text(monkeypatch):
    text = SENTENCE * 20 + LATE
    result, calls = _run(monkeypatch, text)
    assert len(calls) == 1 and calls[0].startswith("Chapter 7:") and calls[0].endswith(LATE)
    assert "the confession about the oil line" in result["key_events"]


def test_text_beyond_the_old_8000_characters_is_read(monkeypatch):
    text = SENTENCE * 140 + LATE                        # ~12,000 characters
    assert len(text) > 8000
    result, calls = _run(monkeypatch, text)
    assert any(LATE in c for c in calls), "the end of the chapter never reached the summariser"
    assert "the confession about the oil line" in result["key_events"]


def test_long_chapter_windows_cover_everything_and_fit_the_model(monkeypatch):
    text = SENTENCE * 900 + LATE                        # ~5,000 words: needs several windows
    windows = _summary_windows(text, "SYSTEM PROMPT " * 300, 7)
    assert len(windows) > 1
    assert re.sub(r"\s+", "", "".join(windows)) == re.sub(r"\s+", "", text)    # nothing dropped
    budget = settings.max_model_len - count_tokens("SYSTEM PROMPT " * 300) - 900 - 300
    assert all(count_tokens(w) <= budget for w in windows)
    result, calls = _run(monkeypatch, text)
    assert len(calls) > 1 and "part 1 of" in calls[0]
    assert "the confession about the oil line" in result["key_events"]          # from the LAST window
    assert result["raw_summary"] == "MERGED SUMMARY"
    assert result["characters_present"] == ["Wren"]                             # merged, not repeated
    assert result["character_arc_notes"]["Wren"].startswith("note 1 Later:")


def test_merge_failure_keeps_every_part(monkeypatch):
    text = SENTENCE * 900 + LATE
    result, calls = _run(monkeypatch, text, merge_raises=True)
    for i in range(1, len(calls) + 1):
        assert f"summary of part {i}" in result["raw_summary"]


def test_a_failed_window_fails_the_chapter_honestly(monkeypatch):
    result, _ = _run(monkeypatch, SENTENCE * 900 + LATE, fail_window=1)
    assert isinstance(result, ValueError)
