"""
Stage 12.3 — task 6.6 "Reintroducing any closed defect turns the suite red".

The 2026-10-06 defect-reintroduction run
(docs/testing/stage-12/stage-12.3/defect-reintroduction/) found three realistic
regressions of closed Phase 2 issues that NO test caught. Each test below is
the missing guard; each was proven red against the recorded probe patch and
green on the fixed code (see that directory's README, "Guard gaps closed").

  P2-2  _extract_json's repair of JSON embedded in prose / fenced / trailing commas
  P2-9  the character routes' call to resolve_hints_for_names (router wiring —
        the existing "integration" test calls the service directly)
  P2-14 check_continuity reporting unreadable model output as a clean result
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402

from services import ai_service  # noqa: E402
from services.ai_service import _extract_json  # noqa: E402


# ── P2-2: the JSON repair the plot-hole / continuity fix relies on ──────────

@pytest.mark.parametrize("raw, expected", [
    ('Here is the analysis you asked for: {"issues": [{"description": "x"}]} Hope this helps!',
     {"issues": [{"description": "x"}]}),
    ('Sure.\n```json\n{"issues": []}\n```', {"issues": []}),
    ('{"issues": [{"description": "a",},],}', {"issues": [{"description": "a"}]}),
    ('Result:\n[{"name": "Mira"}, {"name": "Hessa"}]\nThat is all.', [{"name": "Mira"}, {"name": "Hessa"}]),
])
def test_extract_json_repairs_the_shapes_a_7b_model_actually_returns(raw, expected):
    assert _extract_json(raw, None) == expected


def test_extract_json_still_returns_the_fallback_when_nothing_parses():
    assert _extract_json("no json here at all", {"fallback": True}) == {"fallback": True}


# ── P2-14: unreadable continuity output must never read as "all clear" ──────

def test_unreadable_continuity_output_is_degraded_not_a_clean_result(monkeypatch):
    calls = []

    async def garbage(system, user, *a, **k):
        calls.append(1)
        return "I am sorry, I cannot produce that as JSON. The story is lovely.", "stop"

    monkeypatch.setattr(ai_service, "_complete_ex", garbage)
    issues, meta = asyncio.run(ai_service.check_continuity(
        [{"name": "Mira"}], [{"chapter_number": 1, "key_events": "x"}], [], []))
    assert issues == []
    assert meta.degraded is True, "unreadable output was reported as a clean manuscript (P2-14)"
    assert "could not be checked" in (meta.reason or "")
    assert calls, "the model call was not exercised"


# ── P2-9: every route that names a character reconciles pending hints ───────

@pytest.fixture(autouse=True)
def no_rate_limit(monkeypatch):
    from middleware.rate_limit import limiter
    monkeypatch.setattr(limiter, "enabled", False)


@pytest.fixture
def no_mention_index(monkeypatch):
    """The routes queue background mention indexing (embeddings); irrelevant here."""
    from routers import characters
    monkeypatch.setattr(characters, "_queue_mention_index", lambda *a, **k: 0, raising=False)


def _hint(db, a, name):
    from models import CharacterHint
    h = CharacterHint(story_id=a.sid, chapter_id=a.chapters[0].chapter_id, chapter_number=1,
                      suggested_name=name, context_snippet=f"{name} appeared.", is_dismissed=False)
    db.add(h)
    db.commit()
    return h.hint_id


def _dismissed(db, hint_id) -> bool:
    from models import CharacterHint
    db.expire_all()
    return bool(db.get(CharacterHint, hint_id).is_dismissed)


def test_create_character_route_dismisses_the_matching_hint(no_mention_index):
    from _phase3_helpers import two_authors
    with two_authors() as (db, a, _b, client):
        hid = _hint(db, a, "Tomas Reyne")
        r = client.post(f"/api/stories/{a.sid}/characters", headers=a.headers, json={"name": "Tomas Reyne"})
        assert r.status_code == 200, r.text
        assert _dismissed(db, hid), "create_character no longer reconciles hints (P2-9 wiring)"


def test_rename_route_dismisses_the_matching_hint(no_mention_index):
    from _phase3_helpers import two_authors
    from models import Character
    with two_authors() as (db, a, _b, client):
        hid = _hint(db, a, "Elara Voss")
        cid = db.query(Character).filter(Character.story_id == a.sid, Character.name == "Elara").one().character_id
        r = client.patch(f"/api/stories/{a.sid}/characters/{cid}", headers=a.headers, json={"name": "Elara Voss"})
        assert r.status_code == 200, r.text
        assert _dismissed(db, hid), "update_character no longer reconciles hints on rename (P2-9 wiring)"


def test_confirm_cast_route_dismisses_the_matching_hint(no_mention_index):
    from _phase3_helpers import two_authors
    with two_authors() as (db, a, _b, client):
        hid = _hint(db, a, "Hessa Lin")
        item = {"name": "Hessa Lin", "role": "supporting", "status": "active", "presence": "on_page",
                "description": "", "aliases": [], "evidence_snippet": ""}
        r = client.post(f"/api/stories/{a.sid}/characters/confirm-cast", headers=a.headers,
                        json={"suggestions": [item]})
        assert r.status_code == 201, r.text
        assert _dismissed(db, hid), "confirm-cast no longer reconciles hints (P2-9 wiring)"


def test_promote_route_dismisses_other_hints_for_the_same_name(no_mention_index):
    from _phase3_helpers import two_authors
    with two_authors() as (db, a, _b, client):
        promoted = _hint(db, a, "Corvin Ashe")
        same_name_elsewhere = _hint(db, a, "Corvin Ashe")
        r = client.post(f"/api/stories/{a.sid}/characters/hints/{promoted}/promote", headers=a.headers, json={})
        assert r.status_code == 200, r.text
        assert _dismissed(db, same_name_elsewhere), "promote_hint no longer reconciles other hints (P2-9 wiring)"
