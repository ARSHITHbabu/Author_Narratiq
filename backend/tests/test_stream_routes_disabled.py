"""
Stage 12 remediation A3 — the /api/ai/<tool>/stream routes are off by default.

They return raw model tokens and skip sentence locks, strength limits, the
no-change check, the preservation checks and the prompt-injection output
check. No frontend code calls them, so AI_STREAM_ROUTES_ENABLED defaults to
false and every one answers 404 — before any model call is made.

    DATABASE_URL=...narratiq_test pytest backend/tests/test_stream_routes_disabled.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402

from _phase3_helpers import two_authors  # noqa: E402

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"

STREAM_ROUTES = {
    "/api/ai/refine/stream":       {"text": "One two."},
    "/api/ai/tone/stream":         {"text": "One two.", "tone": "dark"},
    "/api/ai/emotion/stream":      {"text": "One two.", "emotion": "joy"},
    "/api/ai/age-adapt/stream":    {"text": "One two.", "target_age": "children"},
    "/api/ai/style/stream":        {"text": "One two.", "style": "cinematic"},
    "/api/ai/author-style/stream": {"text": "One two.", "author": "generic_minimalist"},
    "/api/ai/translate/stream":    {"text": "One two.", "target_language": "French"},
}


def test_every_stream_route_is_listed():
    from routers.ai_transform import router
    found = {r.path for r in router.routes if r.path.endswith("/stream")}
    assert {p.removeprefix("/api/ai") for p in STREAM_ROUTES} == found


def test_flag_defaults_off():
    from config import Settings
    assert Settings.model_fields["ai_stream_routes_enabled"].default is False


@pytest.mark.parametrize("url,body", list(STREAM_ROUTES.items()))
def test_stream_route_is_404_by_default_and_never_calls_the_model(url, body, monkeypatch):
    from middleware.rate_limit import limiter
    from services import ai_service

    monkeypatch.setattr(limiter, "enabled", False)

    def boom(*_a, **_k):
        raise AssertionError("model reached while streaming is disabled")

    for name in dir(ai_service):
        if name.startswith("stream_"):
            monkeypatch.setattr(ai_service, name, boom)

    with two_authors() as (_db, a, _b, client):
        r = client.post(url, headers=a.headers, json={**body, "story_id": a.sid})
        assert r.status_code == 404, (url, r.status_code, r.text[:200])


def test_unauthenticated_stream_call_is_401_like_every_other_route():
    with two_authors() as (_db, _a, _b, client):
        r = client.post("/api/ai/tone/stream", json={"text": "x", "tone": "dark"})
        assert r.status_code == 401


def test_non_streaming_routes_are_unaffected(monkeypatch):
    """The routes the frontend actually uses keep working with the flag off."""
    from middleware.rate_limit import limiter
    from services import ai_service

    monkeypatch.setattr(limiter, "enabled", False)

    async def fake_refine(text, mode="standard", genre_context=""):
        return text + " Refined."

    monkeypatch.setattr(ai_service, "refine_text", fake_refine)
    with two_authors() as (_db, a, _b, client):
        r = client.post("/api/ai/refine", headers=a.headers,
                        json={"text": "The rain fell on the harbour.", "story_id": a.sid})
        assert r.status_code == 200, r.text[:200]


def test_frontend_does_not_call_stream_routes():
    hits = []
    for path in list(FRONTEND.joinpath("lib").rglob("*.ts")) + list(FRONTEND.joinpath("components").rglob("*.tsx")) \
            + list(FRONTEND.joinpath("app").rglob("*.tsx")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for route in STREAM_ROUTES:
            if route.removeprefix("/api") in text:
                hits.append((str(path), route))
    assert hits == [], hits
