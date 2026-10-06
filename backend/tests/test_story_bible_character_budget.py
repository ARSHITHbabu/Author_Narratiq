"""
Stage 12.3 — found in the owner-authorised agent review (HR-10, 2026-10-06): on a
40-chapter manuscript the Story Bible's characters section was cut off
("truncated") in 6 of 8 live samples. The model wrote a full card for every named
townsperson (14-18 cards) and ran out of its 1,900-token answer. Now: full cards for
at most BIBLE_MAX_CHARACTER_CARDS characters, the rest on one tagged "Also appears"
line, and one fresh sample when a section still stops at the length limit
(2/8 → measured live, evidence in docs/testing/stage-12/stage-12.3/agent-review/).
No model here: `_complete_ex` is stubbed.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from services import ai_service  # noqa: E402

CONTEXT = "[Ch 1] Wren met Ada on the harbour wall. [Ch 18] Mayor Thompson spoke at the meeting."


def _run(monkeypatch, section, replies):
    calls = []

    async def fake(system, user, **kw):
        calls.append((system, user, kw))
        return replies[len(calls) - 1]
    monkeypatch.setattr(ai_service, "_complete_ex", fake)
    out = asyncio.run(ai_service.generate_story_bible_section(section=section, context=CONTEXT))
    return out, calls


def test_the_characters_prompt_caps_full_cards_and_lists_the_rest():
    assert ai_service.BIBLE_MAX_CHARACTER_CARDS == 10


def test_characters_prompt_text(monkeypatch):
    _, calls = _run(monkeypatch, "characters", [("**Name:** Wren [Ch 1]", "stop")])
    prompt = calls[0][0] + calls[0][1]
    assert f"at most {ai_service.BIBLE_MAX_CHARACTER_CARDS} characters" in prompt
    assert "**Also appears:**" in prompt


@pytest.mark.parametrize("section", ["characters", "locations", "timeline", "world_rules", "themes"])
def test_a_section_cut_off_once_is_sampled_again_and_the_finished_answer_kept(monkeypatch, section):
    (text, finish), calls = _run(monkeypatch, section, [("- cut off mid-", "length"), ("- Wren met Ada [Ch 1]", "stop")])
    assert len(calls) == 2
    assert finish == "stop" and "Wren met Ada" in text
    assert calls[0][:2] == calls[1][:2]                      # the same prompt, a fresh sample


def test_a_section_cut_off_twice_is_still_reported_truncated(monkeypatch):
    (text, finish), calls = _run(monkeypatch, "characters", [("a", "length"), ("b", "length")])
    assert len(calls) == 2 and finish == "length"         # never passed off as complete


def test_a_finished_section_is_not_sampled_twice(monkeypatch):
    _, calls = _run(monkeypatch, "themes", [("- Loyalty [Ch 1]", "stop")])
    assert len(calls) == 1


def test_the_also_appears_instruction_carries_no_placeholder_to_copy(monkeypatch):
    # A literal "<name> [Ch N]" example survived the leak filter when the model copied it.
    _, calls = _run(monkeypatch, "characters", [("x", "stop")])
    line = next(l for l in calls[0][0].splitlines() + calls[0][1].splitlines() if "Also appears" in l)
    assert "<" not in line and "[Ch N]" not in line


CARD = ("**Name:** Wren Halloway [Ch 1]\n**Role:** Harbour pilot's daughter [Ch 1]\n"
        "**Arc status:** Chooses to expose Silas [Ch 39]\n---\n")
LOOP = ("**Also appears:**\n- Captain Harlow [Ch 28]\n- Tom [Ch 6]\n- Martha [Ch 6]\n"
        + "- Tom [Ch 6]\n- Martha [Ch 6]\n- Captain Harlow [Ch 28]\n" * 30 + "- Mrs. Eliza")


def test_a_runaway_also_appears_list_is_closed_and_the_cards_kept(monkeypatch):
    """The live failure (agent-review/hr10-characters-truncation-*.json): cards whole, list looping."""
    (text, finish), calls = _run(monkeypatch, "characters", [(CARD + LOOP, "length"), (CARD + LOOP, "length")])
    assert finish == "stop"
    assert text.startswith(CARD.rstrip("-\n").rstrip())
    assert text.endswith("**Also appears:** Captain Harlow [Ch 28]; Tom [Ch 6]; Martha [Ch 6]")
    assert "Mrs. Eliza" not in text                         # the item cut off mid-way is not invented whole


def test_a_card_cut_off_mid_way_is_still_truncated(monkeypatch):
    cut = CARD + "**Name:** Ada Pell [Ch 2]\n**Role:** Ferry"
    (text, finish), _ = _run(monkeypatch, "characters", [(cut, "length"), (cut, "length")])
    assert finish == "length"


def test_a_card_written_after_the_list_is_not_thrown_away(monkeypatch):
    out = CARD + "**Also appears:** Tom [Ch 6]\n---\n**Name:** Ada Pell [Ch 2]\n**Role:** Ferry"
    (text, finish), _ = _run(monkeypatch, "characters", [(out, "length"), (out, "length")])
    assert finish == "length"


def test_other_sections_are_never_salvaged(monkeypatch):
    (text, finish), _ = _run(monkeypatch, "locations", [(LOOP, "length"), (LOOP, "length")])
    assert finish == "length"
