"""
Regression tests for genre detection robustness (no DB, no LLM — Qwen stubbed).

Guards the guided-JSON fix and the field-normalization contract so the intake
flow can never regress to the "Analysis failed" malformed-JSON failure.

Run: pytest backend/tests/test_genre_detection.py -q
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import ai_service


def _stub_complete(monkeypatch, payload: str, capture: dict | None = None):
    async def fake(system, user, **kwargs):
        if capture is not None:
            capture.update(kwargs)
        return payload
    monkeypatch.setattr(ai_service, "_complete", fake)


# A realistic, VALID guided-JSON payload (comp titles as single strings — the
# shape vLLM produces under response_format={"type":"json_object"}).
VALID = (
    '{"genre": "Science Fiction", "sub_genre": "Cyberpunk", '
    '"tone": ["Tense", "Mysterious"], "audience": "Adult", '
    '"structure": "Linear with flashbacks", "conflict": "identity vs institution", '
    '"themes": ["Memory", "Power"], "writing_direction": "build tension gradually", '
    '"secondary_genres": ["Mystery"], '
    '"comparable_titles": ["Never Let Me Go by Kazuo Ishiguro", "The Circle by Dave Eggers"], '
    '"marketing_category": "Sci-Fi Thriller", "emotional_arc": "fear to resolve", '
    '"narrative_pov": "Third-person limited", "pacing": "Slow-burn", '
    '"content_warnings": ["Violence"], "intelligence_notes": "ethics-driven", '
    '"confidence": 1.7}'  # deliberately out of range to test clamping
)


@pytest.mark.asyncio
async def test_detect_genre_normalizes_valid_output(monkeypatch):
    _stub_complete(monkeypatch, VALID)
    r = await ai_service.detect_genre("A long, valid description of a story.", "Adult")
    assert r["genre"] == "Science Fiction"
    assert isinstance(r["tone"], list) and r["tone"] == ["Tense", "Mysterious"]
    assert isinstance(r["comparable_titles"], list)
    assert all(isinstance(c, str) for c in r["comparable_titles"])
    # confidence clamped into [0,1]
    assert 0.0 <= r["confidence"] <= 1.0


@pytest.mark.asyncio
async def test_detect_genre_requests_guided_json(monkeypatch):
    cap: dict = {}
    _stub_complete(monkeypatch, VALID, capture=cap)
    await ai_service.detect_genre("A long, valid description of a story.")
    # The hardened path must ask vLLM for guided JSON output.
    assert cap.get("response_format") == {"type": "json_object"}


@pytest.mark.asyncio
async def test_detect_genre_raises_valueerror_on_garbage(monkeypatch):
    _stub_complete(monkeypatch, "this is not json at all, sorry")
    with pytest.raises(ValueError):
        await ai_service.detect_genre("A long, valid description of a story.")


@pytest.mark.asyncio
async def test_complete_json_returns_fallback_on_garbage(monkeypatch):
    _stub_complete(monkeypatch, "definitely not json")
    parsed, raw = await ai_service._complete_json("sys", "user", fallback={"ok": False})
    assert parsed == {"ok": False}
    assert raw == "definitely not json"


@pytest.mark.asyncio
async def test_complete_json_parses_valid(monkeypatch):
    _stub_complete(monkeypatch, '{"a": 1, "b": [2, 3]}')
    parsed, raw = await ai_service._complete_json("sys", "user", fallback=None)
    assert parsed == {"a": 1, "b": [2, 3]}
