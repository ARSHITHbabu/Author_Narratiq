"""
Stage 7 tasks 7.13 (P3-11 similarity) and 7.7 (P3-04 merge smoothing
constraints) — pure unit tests plus one DB test for the semantic stage.

    DATABASE_URL=...narratiq_test pytest backend/tests/test_similarity_and_merge.py -q
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402

from config import settings  # noqa: E402
from services import similarity  # noqa: E402
from services.similarity import lexical_label, lexical_score  # noqa: E402
from services.version_tools import MAX_WORD_DELTA, validate_smoothing  # noqa: E402

A = "Her pulse found her throat and stayed there. Four doors, and not one of them she trusted."


# ── Stage 1 (lexical, zero model cost) ───────────────────────────────────────

def test_near_identical_regeneration_is_a_near_duplicate():
    b = "Her pulse found her throat and stayed there. Four doors — and not one of them she trusted!"
    assert lexical_score(A, b) >= settings.similarity_lexical_hi
    assert lexical_label(lexical_score(A, b)) == "near_duplicate"


def test_fresh_idea_is_distinct_without_embedding():
    c = "The harbour bells rang twice before the smugglers cut the anchor rope."
    assert lexical_label(lexical_score(A, c)) == "distinct"


def test_ambiguous_band_escalates():
    d = "Her pulse stayed in her throat. She did not trust the four doors at all, not one."
    s = lexical_score(A, d)
    assert settings.similarity_lexical_lo < s < settings.similarity_lexical_hi
    assert lexical_label(s) is None


def test_stage1_resolves_without_touching_the_embedder(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("stage 2 must not run for decisive stage-1 cases")
    monkeypatch.setattr(similarity, "_semantic_scores", boom)
    matches, embedded = asyncio.run(similarity.compare_against(
        A, pins=[], texts=[A, "Completely unrelated sentence about ships."], story_id="s", user_id="u", db=None))
    assert embedded is False
    assert [m.label for m in matches] == ["near_duplicate", "distinct"]


# ── Stage 2 (semantic, pgvector) with pin_store_embedding on / off ──────────

def test_semantic_stage_on_and_off(monkeypatch):
    from _phase3_helpers import pin_payload, two_authors
    from models import AiGenerationPin
    from services.ai_service import embed_text_sync
    ambiguous = "Her pulse stayed in her throat. She did not trust the four doors at all, not one."
    with two_authors() as (db, a, _b, client):
        monkeypatch.setattr(settings, "pin_store_embedding", False)
        pid = client.post(f"/api/stories/{a.sid}/ai/pins", headers=a.headers, json=pin_payload(content=A)).json()["pin"]["pin_id"]
        row = db.query(AiGenerationPin).filter(AiGenerationPin.pin_id == pid).one()
        assert row.embedding is None                              # off → nothing stored
        r = client.post(f"/api/stories/{a.sid}/ai/similarity", headers=a.headers, json={"text": ambiguous})
        assert r.json()["embedded"] is False and r.json()["matches"][0]["method"] == "lexical"
        # Turn it on: store the pin's vector (as the background task would).
        monkeypatch.setattr(settings, "pin_store_embedding", True)
        row.embedding = embed_text_sync(A)
        db.commit()
        r = client.post(f"/api/stories/{a.sid}/ai/similarity", headers=a.headers, json={"text": ambiguous})
        body = r.json()
        assert body["embedded"] is True and body["matches"][0]["method"] == "semantic"
        assert body["matches"][0]["label"] in ("near_duplicate", "related")
        # Similarity stores nothing about the candidate.
        assert db.query(AiGenerationPin).filter(AiGenerationPin.user_id == a.uid).count() == 1


# ── P3-04 merge-smoothing fidelity guard ─────────────────────────────────────

BLOCKS = ["The corridor breathed. ", "Elara counted four doors. ", "She trusted none of them."]


def test_smoothing_within_tolerance_passes():
    smoothed = ["The corridor breathed.", "So Elara counted four doors.", "She trusted none of them."]
    ok, delta, sim = validate_smoothing([b.strip() for b in BLOCKS], smoothed)
    assert ok and delta <= MAX_WORD_DELTA and sim >= 0.9


def test_smoothing_that_rewrites_a_chosen_block_is_rejected():
    smoothed = ["The corridor breathed.", "Elara, terrified, ran from the endless hall.", "She trusted none of them."]
    ok, _delta, sim = validate_smoothing([b.strip() for b in BLOCKS], smoothed)
    assert not ok and sim < 0.9


def test_smoothing_that_changes_length_too_much_is_rejected():
    smoothed = [b.strip() + " And then, after a long and weary pause, more." for b in BLOCKS]
    ok, delta, _ = validate_smoothing([b.strip() for b in BLOCKS], smoothed)
    assert not ok and delta > MAX_WORD_DELTA


def test_wrong_block_count_or_empty_block_is_rejected():
    assert validate_smoothing(["a b"], ["a b", "c"])[0] is False
    assert validate_smoothing(["a b", "c d"], ["a b", " "])[0] is False


def test_merge_retries_once_then_returns_unsmoothed(monkeypatch):
    from services import ai_service, version_tools
    calls = []

    async def rewriting_model(system, user, temperature=0.0, max_tokens=512, response_format=None):
        calls.append(temperature)
        return '{"blocks": ["Totally different.", "Nothing like it.", "Another thing."]}'
    monkeypatch.setattr(ai_service, "_complete", rewriting_model)
    out = asyncio.run(version_tools.smooth_merge(BLOCKS))
    assert len(calls) == 2                                   # one retry, bounded
    assert out["smoothed"] is False and out["merged"] == "".join(BLOCKS)
    assert out["warnings"][0]["kind"] == "merge_unsmoothed"


def test_merge_accepts_faithful_smoothing_and_keeps_whitespace(monkeypatch):
    from services import ai_service, version_tools

    async def gentle(system, user, temperature=0.0, max_tokens=512, response_format=None):
        return '{"blocks": ["The corridor breathed.", "So Elara counted four doors.", "She trusted none of them."]}'
    monkeypatch.setattr(ai_service, "_complete", gentle)
    out = asyncio.run(version_tools.smooth_merge(BLOCKS))
    assert out["smoothed"] is True
    assert out["merged"] == "The corridor breathed. So Elara counted four doors. She trusted none of them."


def test_compare_summary_is_best_effort(monkeypatch):
    from services import ai_service, version_tools

    async def garbage(system, user, temperature=0.0, max_tokens=512, response_format=None):
        assert len(user) < 6100                               # both sides capped at 3,000 chars
        return "not json at all", "stop"
    monkeypatch.setattr(ai_service, "_complete_ex", garbage)
    assert asyncio.run(version_tools.compare_summary("a" * 9000, "b" * 9000)) == {"available": False}
