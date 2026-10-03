"""
Stage 12.1 (Gate 2: "Story Bible never asserts unsupported facts") — a prompt
example must never become a fact in a generated Story Bible.

Live, the World Rules section of the fixture story's Story Bible contained
"Lattice sessions require an induction collar [Ch 1]": the prompt's own example,
with a false citation. Same class as the phantom character task 4.16 fixed.
No model here: `_complete_ex` is stubbed, so the REAL prompts are inspected and
the REAL post-processing runs.

    DATABASE_URL=...narratiq_test pytest backend/tests/test_story_bible_prompt_examples.py -q
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from services import ai_service  # noqa: E402
from services.ai_service import _BIBLE_PROMPT_EXAMPLES, _drop_prompt_example_leaks  # noqa: E402

SECTIONS = ["characters", "locations", "timeline", "world_rules", "themes"]
CONTEXT = "[Ch 1] Devika met Mara on the archive steps. [Ch 3] The Bureau keeps a public ledger."
LEAK = "- Lattice sessions require an induction collar [Ch 1]"
REAL = "- The Bureau maintains a public ledger of contracts [Ch 3]"


def _run(monkeypatch, section: str, model_output: str, context: str = CONTEXT):
    seen = {}

    async def fake(system, user, **kw):
        seen["system"], seen["user"] = system, user
        return model_output, "stop"
    monkeypatch.setattr(ai_service, "_complete_ex", fake)
    text, _ = asyncio.run(ai_service.generate_story_bible_section(section=section, context=context))
    return text, seen


@pytest.mark.parametrize("section", SECTIONS)
def test_prompts_carry_no_realistic_example_facts(monkeypatch, section):
    _, seen = _run(monkeypatch, section, "x")
    prompt = (seen["system"] + "\n" + seen["user"]).lower()
    for old in ("lattice sessions", "induction collar", "the archive burns", "burns the archive"):
        assert old not in prompt, f"{section}: realistic example {old!r} is back in the prompt"


@pytest.mark.parametrize("section", SECTIONS)
def test_leaked_example_line_is_removed_and_real_lines_kept(monkeypatch, section):
    text, _ = _run(monkeypatch, section, f"{LEAK}\n{REAL}")
    assert "induction collar" not in text.lower()
    assert REAL in text


def test_a_story_that_really_has_the_phrase_keeps_its_rule():
    ctx = CONTEXT + " [Ch 2] Lattice sessions require an induction collar, Vance warned."
    text, dropped = _drop_prompt_example_leaks(f"{LEAK}\n{REAL}", ctx)
    assert dropped == 0 and LEAK in text


def test_every_example_in_the_characters_prompt_is_guarded(monkeypatch):
    # The characters prompt still carries two worked examples (task 4.16).
    _, seen = _run(monkeypatch, "characters", "x")
    prompt = ai_service._norm(seen["system"] + " " + seen["user"])
    for ex in _BIBLE_PROMPT_EXAMPLES[1:]:
        assert f" {ex} " in prompt, f"{ex!r} is no longer in the prompt — remove it from the guard list"
    leaked = "- **Arc status:** Chose to leave Vell in the dark rather than accept his bribe [Ch 5]"
    text, dropped = _drop_prompt_example_leaks(leaked + "\n" + REAL, CONTEXT)
    assert dropped == 1 and text == REAL


def test_matching_ignores_case_and_punctuation():
    text, dropped = _drop_prompt_example_leaks("* LATTICE sessions — require an induction-collar. [Ch 1]", CONTEXT)
    assert dropped == 1 and text == ""


def test_literal_placeholder_citation_is_removed():
    # Live, the model wrote "Not established in the manuscript [Ch N]" once the
    # prompts used "[Ch N]" as the placeholder citation (5 of 10 runs).
    text, n = _drop_prompt_example_leaks("- Not established in the manuscript [Ch N]\n" + REAL, CONTEXT)
    assert n == 1 and "[Ch N]" not in text
    assert text.splitlines() == ["- Not established in the manuscript", REAL]
    assert _drop_prompt_example_leaks("- A rule [Ch 12]", CONTEXT) == ("- A rule [Ch 12]", 0)
