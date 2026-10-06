"""
Stage 12.3 — found in the owner-authorised agent review (HR-11, 2026-10-06): live
Suggestions on chapter 21 of the synthetic 40-chapter manuscript said "The phrase
'Wren pushed her way through the throng' is repeated verbatim". It occurs once.
Repetition claims about a quoted phrase are now checked against the excerpt.
Pure functions plus a stubbed model; nothing here calls vLLM.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import ai_service  # noqa: E402
from services.suggestion_hygiene import false_repetition_claim  # noqa: E402

EXCERPT = ("The bell rang twice. Wren pushed her way through the throng to the quay. "
           "The tide was out, and the tide was out again by noon.")


def _item(obs, rec="Cut the second use and let the image stand once on its own."):
    return {"category": "Repetition", "observation": obs, "recommendation": rec, "priority": "medium"}


def test_the_live_false_claim_is_detected():
    assert false_repetition_claim(_item("The phrase 'Wren pushed her way through the throng' is repeated verbatim."), EXCERPT)


def test_a_real_repetition_is_kept():
    assert not false_repetition_claim(_item('The phrase "the tide was out" is repeated in two sentences.'), EXCERPT)


def test_curly_quotes_and_case_are_normalised():
    assert not false_repetition_claim(_item("“The Tide was out” appears twice in a row."), EXCERPT)


def test_an_item_that_quotes_nothing_is_left_alone():
    assert not false_repetition_claim(_item("The word choice is repetitive in the opening."), EXCERPT)


def test_a_non_repetition_item_is_never_touched():
    item = _item("'Wren pushed her way through the throng' is a strong active image, but the quay is never described.")
    item["category"] = "Setting"
    assert not false_repetition_claim(item, EXCERPT)


def test_possessive_apostrophes_inside_single_quotes():
    ex = "Wren's hand shook. Later, Wren's hand shook again."
    assert not false_repetition_claim(_item("'Wren's hand shook' is repeated."), ex)
    assert false_repetition_claim(_item("'Wren's hand trembled' is repeated."), ex)


def test_generate_suggestions_drops_the_false_item_and_keeps_the_rest(monkeypatch):
    false_item = _item("The phrase 'Wren pushed her way through the throng' is repeated verbatim.")
    real_item = {"category": "Narrative Risk", "priority": "high",
                 "observation": "The quay scene does not show what Wren wants from the crowd.",
                 "recommendation": "Give Wren one concrete goal on the quay before the bell rings."}

    async def fake(system, user, **kw):
        return [false_item, real_item], None
    monkeypatch.setattr(ai_service, "complete_structured", fake)
    monkeypatch.setattr(ai_service, "_SHARPEN_SUGGESTIONS", False)
    out = asyncio.run(ai_service.generate_suggestions(EXCERPT))
    assert [s["category"] for s in out] == ["Narrative Risk"]
