"""
Stage 12.3 — found in the owner-authorised agent review (HR-09, 2026-10-06):
the Manuscript Report sent its whole chapter table to the model with no token
budget. On a 40-chapter, 32k-word manuscript the request was 6,820 prompt
tokens + 1,800 for the answer, over the 8,192 window; vLLM refused it (400) and
the author saw "The AI model is currently unavailable". The chapter data is now
fitted to the window, every chapter kept. No model is called here.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from config import settings  # noqa: E402
from services import ai_service  # noqa: E402
from services.ai_service import count_tokens  # noqa: E402

EVENT = ("Wren and Ada row out to the wreck site at slack water, argue about the coded list, and find a brass "
         "token stamped with a crest in the drowned man's boot while Liesel watches from the harbour wall")


def _chapters(n: int, events_per: int = 6) -> list[dict]:
    return [{"chapter": i, "events": [f"{EVENT} ({i}.{k})" for k in range(events_per)],
             "characters": ["Wren Halloway", "Ada Pell", "Liesel Marr", "Edric Thorne", "Silas Crane"],
             "locations": ["Greymouth"], "tone": "tense", "purpose": "advances the smuggling mystery",
             "word_count": 800, "raw_summary": EVENT * 3} for i in range(1, n + 1)]


def _capture(monkeypatch):
    seen = {}

    async def fake(system, user, *a, max_tokens=None, **k):
        seen.update(system=system, user=user, max_tokens=max_tokens)
        return {"character_arcs": [], "pacing": {"slow_chapters": [], "intense_chapters": [], "assessment": ""},
                "unresolved_threads": [], "strengths": [], "improvements": [], "themes": [], "note": "x"}, None

    monkeypatch.setattr(ai_service, "complete_structured", fake)
    return seen


@pytest.mark.parametrize("n", [40, 60])
def test_a_long_manuscript_report_fits_the_model_window_and_keeps_every_chapter(monkeypatch, n):
    seen = _capture(monkeypatch)
    result = asyncio.run(ai_service._strategy_manuscript_summary_pass(_chapters(n)))
    total = count_tokens(seen["system"]) + count_tokens(seen["user"]) + seen["max_tokens"]
    assert total <= settings.max_model_len, f"{total} tokens requested for a {settings.max_model_len} window"
    for i in range(1, n + 1):
        assert f"Ch{i} (WC:" in seen["user"], f"chapter {i} dropped"
    assert "shortened to fit" in result["mode_note"]
    assert result["chapters_analyzed"] == n


def test_a_short_manuscript_is_sent_unshortened_with_its_rich_summaries(monkeypatch):
    seen = _capture(monkeypatch)
    result = asyncio.run(ai_service._strategy_manuscript_summary_pass(_chapters(5, events_per=2)))
    assert "Summary: " in seen["user"]                      # rich mode kept (≤ 20 chapters, fits)
    assert "shortened" not in result["mode_note"]
    assert seen["user"].count("Wren and Ada row out") == 5 * 2 + 5 * 3   # nothing trimmed


def test_the_unfitted_prompt_really_overflowed_the_window():
    """Guards the premise: without fitting, the same 40-chapter data exceeds the window."""
    lines = [ai_service._manuscript_line(c, False, None, None) for c in _chapters(40)]
    assert count_tokens("\n".join(lines)) + 1800 > settings.max_model_len
