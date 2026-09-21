"""
Stage 5 task 5.13 — priority coercion/sorting and the bounded adversarial
sharpening pass (no DB, no GPU — Qwen is stubbed via monkeypatch).

Run: cd backend && pytest tests/test_suggestions_priority.py -q
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import ai_service  # noqa: E402
from services.ai_service import coerce_writing_suggestions, _adversarial_sharpen_suggestions  # noqa: E402


# ── coerce_writing_suggestions: priority default/validation/sort ───────────

def test_priority_passed_through_when_valid():
    parsed = {"suggestions": [
        {"id": 1, "category": "Pacing", "observation": "x", "recommendation": "y", "priority": "high"},
    ]}
    kept, discarded = coerce_writing_suggestions(parsed)
    assert kept[0]["priority"] == "high"


def test_priority_defaults_to_medium_when_missing():
    parsed = {"suggestions": [
        {"id": 1, "category": "Pacing", "observation": "x", "recommendation": "y"},
    ]}
    kept, discarded = coerce_writing_suggestions(parsed)
    assert kept[0]["priority"] == "medium"


def test_priority_defaults_to_medium_when_invalid_value():
    parsed = {"suggestions": [
        {"id": 1, "category": "Pacing", "observation": "x", "recommendation": "y", "priority": "urgent!!"},
    ]}
    kept, discarded = coerce_writing_suggestions(parsed)
    assert kept[0]["priority"] == "medium"


def test_suggestions_sorted_high_before_medium_before_low():
    parsed = {"suggestions": [
        {"id": 1, "category": "A", "observation": "a", "recommendation": "", "priority": "low"},
        {"id": 2, "category": "B", "observation": "b", "recommendation": "", "priority": "high"},
        {"id": 3, "category": "C", "observation": "c", "recommendation": "", "priority": "medium"},
    ]}
    kept, discarded = coerce_writing_suggestions(parsed)
    assert [s["id"] for s in kept] == [2, 3, 1]


def test_stable_sort_preserves_relative_order_within_same_priority():
    parsed = {"suggestions": [
        {"id": 1, "category": "A", "observation": "a", "recommendation": "", "priority": "high"},
        {"id": 2, "category": "B", "observation": "b", "recommendation": "", "priority": "high"},
        {"id": 3, "category": "C", "observation": "c", "recommendation": "", "priority": "high"},
    ]}
    kept, discarded = coerce_writing_suggestions(parsed)
    assert [s["id"] for s in kept] == [1, 2, 3]


def test_v1_shaped_item_still_gets_a_valid_default_priority():
    # A v1-shaped item (no observation/recommendation split, no priority at
    # all) must not crash the coercer — task 5.1's revert guarantee.
    parsed = {"suggestions": [{"id": 1, "category": "General", "text": "x", "reason": "x"}]}
    kept, discarded = coerce_writing_suggestions(parsed)
    assert kept[0]["priority"] == "medium"


# ── _adversarial_sharpen_suggestions: bounded, fails open ───────────────────

SAMPLE = [
    {"id": 1, "category": "Pacing", "observation": "slow", "recommendation": "trim it", "priority": "medium",
     "text": "slow", "reason": "slow trim it"},
]


@pytest.mark.asyncio
async def test_adversarial_pass_returns_revised_suggestions_on_success(monkeypatch):
    async def fake_complete_structured(system, user, coerce, **kw):
        import json
        parsed = json.loads(user)
        sharpened = [{**item, "observation": item["observation"] + " (sharpened)"} for item in parsed]
        return coerce({"suggestions": sharpened})

    monkeypatch.setattr(ai_service, "complete_structured", fake_complete_structured)
    result = await _adversarial_sharpen_suggestions(SAMPLE)
    assert "(sharpened)" in result[0]["observation"]


@pytest.mark.asyncio
async def test_adversarial_pass_fails_open_on_exception(monkeypatch):
    async def broken_complete_structured(*a, **kw):
        raise RuntimeError("vLLM unreachable")

    monkeypatch.setattr(ai_service, "complete_structured", broken_complete_structured)
    result = await _adversarial_sharpen_suggestions(SAMPLE)
    assert result == SAMPLE   # unchanged, not raised


@pytest.mark.asyncio
async def test_adversarial_pass_fails_open_on_none_result(monkeypatch):
    async def none_complete_structured(*a, **kw):
        return None, None

    monkeypatch.setattr(ai_service, "complete_structured", none_complete_structured)
    result = await _adversarial_sharpen_suggestions(SAMPLE)
    assert result == SAMPLE


@pytest.mark.asyncio
async def test_adversarial_pass_fails_open_on_item_count_mismatch(monkeypatch):
    async def fake_complete_structured(system, user, coerce, **kw):
        # Returns only one item's worth of shape but claims two — a shape
        # mismatch that must never be trusted.
        return [], None

    monkeypatch.setattr(ai_service, "complete_structured", fake_complete_structured)
    result = await _adversarial_sharpen_suggestions(SAMPLE)
    assert result == SAMPLE


@pytest.mark.asyncio
async def test_adversarial_pass_noop_on_empty_input():
    assert await _adversarial_sharpen_suggestions([]) == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
