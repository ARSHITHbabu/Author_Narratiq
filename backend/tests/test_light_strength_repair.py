"""
Stage 12.3 (owner review A2) — Light strength must stay light.

The owner judged only 5 of 12 tone / age-adaptation Light rewrites both an
acceptable light edit and clearly lighter than Strong. From the owner's labels,
new_share (the share of output words not in the original) above 0.45 marks a
Light rewrite that is not light (4 of 6 rejected, 0 of 9 accepted). At Light,
such a rewrite is retried once with explicit feedback; the retry is kept only
if it is lighter and loses no character names; a result still too heavy is
flagged strength_violation. No model: `_complete` is scripted.

    DATABASE_URL=...narratiq_test pytest backend/tests/test_light_strength_repair.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from config import settings  # noqa: E402
from services import ai_service  # noqa: E402
from services.transform_preservation import LIGHT_NEW_SHARE_MAX, light_edit_too_heavy  # noqa: E402

ORIGINAL = ("The old guide had warned them about the pass, the weather, and the wolves, in that order, "
            "as if the order mattered. Nobody had listened, and the snow came early that year.")
LIGHT_OK = ("The old guide had warned them about the pass, the weather, and the wolves, in that grim order, "
            "as if the order mattered. Nobody had listened, and the snow came early that year.")
HEAVY = ("Long before the climb, a weathered mountain scout cautioned every traveller about treacherous "
         "ridges, brutal storms and prowling packs, insisting each peril be respected in sequence. "
         "Ignored entirely, he watched winter arrive weeks ahead of schedule.")
HEAVIER = ("Generations of wanderers whispered legends of a cursed ridge where blizzards devoured "
           "caravans whole; travellers mocked such superstition until frost swallowed everything.")


async def _run(monkeypatch, outputs, strength="light", locked_ranges=None):
    calls = []

    async def fake_complete(system, user, temperature=0.0, max_tokens=512, response_format=None,
                            task=None, datamark=False):
        calls.append(system)
        return outputs[min(len(calls) - 1, len(outputs) - 1)]

    monkeypatch.setattr(ai_service, "_complete", fake_complete)
    result = await ai_service._run_constrained_transform_once(
        transform_type="tone", text=ORIGINAL, temperature=0.3, max_tokens=400,
        builder_kwargs={"tone": "suspenseful", "genre_context": ""},
        strength=strength, locked_ranges=locked_ranges)
    return result, calls


@pytest.fixture(autouse=True)
def _repair_on(monkeypatch):
    monkeypatch.setattr(settings, "light_strength_repair", True)
    monkeypatch.setattr(settings, "light_new_share_max", LIGHT_NEW_SHARE_MAX)


def test_threshold_matches_the_owner_labelled_boundary():
    assert LIGHT_NEW_SHARE_MAX == 0.45
    assert light_edit_too_heavy(ORIGINAL, LIGHT_OK)[0] is False
    assert light_edit_too_heavy(ORIGINAL, HEAVY)[0] is True
    assert light_edit_too_heavy("Too short to judge.", HEAVY) == (False, None)


@pytest.mark.asyncio
async def test_a_light_rewrite_is_not_retried(monkeypatch):
    result, calls = await _run(monkeypatch, [LIGHT_OK])
    assert len(calls) == 1 and result["transformed"] == LIGHT_OK and result["strength_violation"] is False


@pytest.mark.asyncio
async def test_a_heavy_light_rewrite_is_retried_once_and_the_lighter_retry_kept(monkeypatch):
    result, calls = await _run(monkeypatch, [HEAVY, LIGHT_OK])
    assert len(calls) == 2
    assert "changed too much for a LIGHT edit" in calls[1]
    assert result["transformed"] == LIGHT_OK and result["strength_violation"] is False


@pytest.mark.asyncio
async def test_a_heavier_retry_is_discarded_and_the_result_flagged(monkeypatch):
    result, calls = await _run(monkeypatch, [HEAVY, HEAVIER])
    assert len(calls) == 2                       # bounded: never a third attempt
    assert result["transformed"] == HEAVY and result["strength_violation"] is True


@pytest.mark.asyncio
async def test_moderate_and_strong_are_never_repaired(monkeypatch):
    for strength in ("moderate", "strong"):
        result, calls = await _run(monkeypatch, [HEAVY, LIGHT_OK], strength=strength)
        assert len(calls) == 1 and result["transformed"] == HEAVY


@pytest.mark.asyncio
async def test_switch_off_restores_the_previous_behaviour(monkeypatch):
    monkeypatch.setattr(settings, "light_strength_repair", False)
    result, calls = await _run(monkeypatch, [HEAVY, LIGHT_OK])
    assert len(calls) == 1 and result["transformed"] == HEAVY
    assert result["strength_violation"] is False   # count-based check only, as before


@pytest.mark.asyncio
async def test_a_retry_that_loses_a_character_name_is_not_used(monkeypatch):
    def fake_names(original, transformed, story_id, db, rules=None):
        return ["Devika"] if transformed == LIGHT_OK else []
    monkeypatch.setattr(ai_service, "check_character_name_preservation", fake_names)
    result, _calls = await _run(monkeypatch, [HEAVY, LIGHT_OK])
    assert result["transformed"] == HEAVY and result["strength_violation"] is True


@pytest.mark.asyncio
async def test_locked_sentences_stay_byte_identical_through_the_repair(monkeypatch):
    first_sentence_end = ORIGINAL.index(".") + 1
    locked = [{"start": 0, "end": first_sentence_end}]
    marked, segments = __import__('services.transform_preservation', fromlist=['x']).mark_locked_segments(ORIGINAL, locked)
    rewrite_ids = [s for s in segments if not s["locked"]]
    assert rewrite_ids, "fixture needs an unlocked segment"

    def wrap(second: str) -> str:
        out = marked
        for seg in segments:
            if not seg["locked"]:
                out = out.replace(seg["text"], second, 1)
        return out
    heavy_second = "Ignored entirely, he watched winter arrive weeks ahead of schedule, cruel and certain."
    light_second = "Nobody had listened, and the snow came early that grim year."
    result, calls = await _run(monkeypatch, [wrap(heavy_second), wrap(light_second)], locked_ranges=locked)
    assert result["transformed"].startswith(ORIGINAL[:first_sentence_end])


# ── OD-13 (2026-10-06): per-transform boundary derived from the HR-07 labels ─────
# A rewrite that swaps several phrases (new-word share 0.286): too heavy for a
# Light TONE or STYLE edit (boundary 0.24), still within the age-adaptation
# boundary (0.45), where simplifying legitimately adds new words.
MID = ("The old guide had cautioned them about the pass, the storms, and the wolves, in that exact sequence, "
       "as if the sequence held meaning. Nobody had heeded him, and the snow arrived early that year.")


async def _run_as(monkeypatch, transform_type, builder_kwargs, outputs):
    calls = []

    async def fake_complete(system, user, temperature=0.0, max_tokens=512, response_format=None,
                            task=None, datamark=False):
        calls.append(system)
        return outputs[min(len(calls) - 1, len(outputs) - 1)]

    async def always_needs_change(*_a, **_k):
        return True, ""

    monkeypatch.setattr(ai_service, "_complete", fake_complete)
    monkeypatch.setattr(ai_service, "_assess_change_needed", always_needs_change)
    result = await ai_service._run_constrained_transform_once(
        transform_type=transform_type, text=ORIGINAL, temperature=0.3, max_tokens=400,
        builder_kwargs=builder_kwargs, strength="light", locked_ranges=None)
    return result, calls


def test_the_derived_boundaries_are_configured():
    assert settings.light_new_share_max_tone_style == 0.24
    assert light_edit_too_heavy(ORIGINAL, MID, None, 0.24)[0] is True
    assert light_edit_too_heavy(ORIGINAL, MID, None, 0.45)[0] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("transform_type, kwargs", [
    ("tone", {"tone": "suspenseful", "genre_context": ""}),
    ("style", {"style": "cinematic", "genre_context": ""}),
])
async def test_a_mid_band_light_rewrite_is_repaired_for_tone_and_style(monkeypatch, transform_type, kwargs):
    monkeypatch.setattr(settings, "light_new_share_max_tone_style", 0.24)
    result, calls = await _run_as(monkeypatch, transform_type, kwargs, [MID, LIGHT_OK])
    assert len(calls) == 2 and result["transformed"] == LIGHT_OK and result["strength_violation"] is False


@pytest.mark.asyncio
async def test_a_mid_band_light_rewrite_is_left_alone_for_age_adaptation(monkeypatch):
    monkeypatch.setattr(settings, "light_new_share_max_tone_style", 0.24)
    result, calls = await _run_as(monkeypatch, "age_adapt", {"target_age": "children", "genre_context": ""}, [MID])
    assert len(calls) == 1 and result["transformed"] == MID
