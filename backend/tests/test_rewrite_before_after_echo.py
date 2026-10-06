"""
Stage 12.3 — found in the owner-authorised agent review (HR-18, 2026-10-06): with
"Match my voice closely", a live Tone rewrite of chapter 35 came back as
'Before: "<the original paragraph>"  After: "<the rewrite>"' — the shape of the
surrounding-text block in the prompt. Applied, it would paste the original, the
rewrite and two labels into the chapter. The rewrite path now keeps only the After
part. Evidence: docs/testing/stage-12/stage-12.3/agent-review/hr18-blind-texts.json.
No model here: `_complete` is stubbed.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from services import ai_service  # noqa: E402
from services.ai_service import _unwrap_before_after  # noqa: E402

SOURCE = ("The third letter was a plea for help. Eliza had heard rumors of a safe house in Greymouth. "
          "“If you can find it,” Eliza wrote, “please see if there is any truth to these stories.”")
REWRITE = ("The third letter was a desperate cry for aid. Eliza had heard whispers of a sanctuary in Greymouth. "
           "“If you can find it,” Eliza wrote, “verify these rumors.”")
LIVE_SHAPE = f'Before: "{SOURCE}"\n\nAfter: "{REWRITE}"'


def test_the_live_shape_keeps_only_the_rewrite():
    assert _unwrap_before_after(LIVE_SHAPE, SOURCE) == REWRITE


def test_bold_labels_and_unquoted_parts():
    out = f"**Before:** {SOURCE}\n**After:** {REWRITE}"
    assert _unwrap_before_after(out, SOURCE) == REWRITE


def test_a_normal_rewrite_is_untouched():
    assert _unwrap_before_after(REWRITE, SOURCE) == REWRITE


def test_a_passage_that_itself_uses_the_labels_is_left_alone():
    src = "Before: the storm.\nAfter: the quiet."
    out = "Before: the gale.\nAfter: the hush."
    assert _unwrap_before_after(out, src) == out


def test_a_dialogue_paragraph_keeps_its_own_opening_quote():
    src = '"Indeed, they did," she said. "It was a tale of betrayal."'
    out = f'Before: {src}\nAfter: "Indeed, they did," she whispered. "A tale of betrayal."'
    assert _unwrap_before_after(out, src) == '"Indeed, they did," she whispered. "A tale of betrayal."'


@pytest.mark.asyncio
async def test_a_tone_rewrite_returned_in_before_after_shape_is_cleaned(monkeypatch):
    async def fake_complete(system, user, temperature=0.0, max_tokens=512, response_format=None,
                            task=None, datamark=False):
        return LIVE_SHAPE
    monkeypatch.setattr(ai_service, "_complete", fake_complete)
    result = await ai_service._run_constrained_transform_once(
        transform_type="tone", text=SOURCE, temperature=0.3, max_tokens=400,
        builder_kwargs={"tone": "suspenseful", "genre_context": ""}, strength="moderate")
    assert result["transformed"] == REWRITE
    assert "Before:" not in result["transformed"] and "After:" not in result["transformed"]
