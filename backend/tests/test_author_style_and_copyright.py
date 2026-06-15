"""
Unit tests for the Author-Inspired Style Rewrite and Copyright/Plagiarism Risk
features (no DB, no LLM, no GPU — Qwen is stubbed via monkeypatch).

Run: pytest backend/tests/test_author_style_and_copyright.py -q
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import ai_service


# ── Author style resolution / safeguards ──────────────────────────────────────

def test_public_domain_author_resolves_to_named_descriptor():
    r = ai_service._resolve_author_style("Shakespeare")
    assert r["key"] == "shakespeare"
    assert r["public_domain"] is True
    assert "Shakespeare" in r["descriptor"]


def test_living_or_incopyright_author_maps_to_safe_generic():
    # Hemingway / Woolf / Christie must NOT become a named-imitation instruction.
    for name, expected_key in [
        ("Ernest Hemingway", "generic_minimalist"),
        ("Virginia Woolf", "generic_stream"),
        ("Agatha Christie", "generic_mystery"),
    ]:
        r = ai_service._resolve_author_style(name)
        assert r["key"] == expected_key
        assert r["group"] == "generic"
        # The descriptor must not instruct imitation of the living author by name.
        assert name.split()[-1].lower() not in r["descriptor"].lower()


def test_unknown_author_falls_back_to_generic_literary():
    r = ai_service._resolve_author_style("Some Random Living Novelist 2024")
    assert r["key"] == "generic_literary"


def test_author_style_system_prompt_carries_safeguards():
    sys_prompt = ai_service._author_style_system("poe", genre_context="")
    # Influence-only, preserve-meaning, no-copy guardrails must be present.
    assert "inspired by" in sys_prompt.lower() or "influenced by" in sys_prompt.lower()
    assert "do not" in sys_prompt.lower()
    assert "preserve the original meaning" in sys_prompt.lower()


def test_catalog_has_no_named_living_authors():
    keys = {o["id"] for o in ai_service.author_style_catalog()}
    for forbidden in ("hemingway", "woolf", "christie"):
        assert forbidden not in keys


@pytest.mark.asyncio
async def test_rewrite_in_author_style_calls_complete(monkeypatch):
    captured = {}

    async def fake_complete(system, user, **kw):
        captured["system"] = system
        captured["user"] = user
        return "Hark, the rewritten prose."

    monkeypatch.setattr(ai_service, "_complete", fake_complete)
    out = await ai_service.rewrite_in_author_style("The man walked in.", "shakespeare")
    assert out == "Hark, the rewritten prose."
    assert "Shakespeare" in captured["system"]


# ── Copyright / plagiarism risk analysis ──────────────────────────────────────

@pytest.mark.asyncio
async def test_analyze_copyright_risk_parses_json(monkeypatch):
    payload = (
        '{"overall_risk": "medium", "findings": ['
        '{"risk_type": "character", "risk_score": "high", "description": "Resembles a known wizard.",'
        ' "problematic_excerpt": "the boy with the scar", "is_generic_trope": false,'
        ' "rewrite_suggestion": "Change the distinctive marks and backstory."}],'
        ' "note": "One notable similarity."}'
    )

    async def fake_complete(system, user, **kw):
        return payload

    monkeypatch.setattr(ai_service, "_complete", fake_complete)
    result = await ai_service.analyze_copyright_risk("selection", "the boy with the scar")

    assert result["overall_risk"] == "medium"
    assert len(result["findings"]) == 1
    f = result["findings"][0]
    assert f["finding_id"] == 1
    assert f["risk_type"] == "character"
    assert f["risk_score"] == "high"
    assert f["is_generic_trope"] is False
    # Disclaimer always present, non-legal-advice framing.
    assert "not legal advice" in result["disclaimer"].lower()


@pytest.mark.asyncio
async def test_analyze_copyright_risk_derives_overall_when_missing(monkeypatch):
    payload = (
        '{"findings": ['
        '{"risk_type": "trope_overuse", "risk_score": "high", "description": "x",'
        ' "problematic_excerpt": "", "is_generic_trope": true, "rewrite_suggestion": "y"}]}'
    )

    async def fake_complete(system, user, **kw):
        return payload

    monkeypatch.setattr(ai_service, "_complete", fake_complete)
    result = await ai_service.analyze_copyright_risk("project", "digest")
    # overall_risk absent in payload → derived from max finding level.
    assert result["overall_risk"] == "high"


@pytest.mark.asyncio
async def test_analyze_copyright_risk_invalid_json_raises(monkeypatch):
    async def fake_complete(system, user, **kw):
        return "not json at all"

    monkeypatch.setattr(ai_service, "_complete", fake_complete)
    with pytest.raises(ValueError):
        await ai_service.analyze_copyright_risk("selection", "text")


def test_normalize_risk_clamps_unknown_values():
    assert ai_service._normalize_risk("HIGH") == "high"
    assert ai_service._normalize_risk("bogus") == "low"
    assert ai_service._normalize_risk(None, default="medium") == "medium"
