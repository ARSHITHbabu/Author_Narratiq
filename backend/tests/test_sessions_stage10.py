"""
Stage 10 — task 10.7 (HttpOnly cookie sessions, CSRF) and decision S10-F
(server-side revocation). Defines the session semantics by test:

  * sign-in sets an HttpOnly session cookie and a readable CSRF cookie; the
    token is never in a response body;
  * a cookie-authenticated state change needs the matching X-CSRF-Token and
    an allowed Origin; a Bearer request (API tooling) does not;
  * logout ends ONLY that session — another device stays signed in — and a
    copied token of the ended session stops working;
  * a password change ends EVERY other session and keeps this device signed in;
  * a pre-Stage-10 token (no jti/ver) is refused;
  * voice-socket tickets are single-use and expire; the old ?token= is refused.

    DATABASE_URL=...narratiq_test pytest backend/tests/test_sessions_stage10.py -q
"""
from __future__ import annotations

import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from jose import jwt  # noqa: E402

import main  # noqa: E402
from config import settings  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import RevokedSession, Story, User  # noqa: E402
from routers import auth as auth_mod  # noqa: E402

PASSWORD = "correct horse battery"


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch):
    from middleware.rate_limit import limiter
    monkeypatch.setattr(limiter, "enabled", False)


@pytest.fixture
def account():
    db = SessionLocal()
    tag = uuid.uuid4().hex[:8]
    user = User(email=f"s10-{tag}@narratiq-internal-test.com", username=f"s10{tag}",
                hashed_password=auth_mod.hash_password(PASSWORD))
    db.add(user)
    db.commit()
    db.refresh(user)
    try:
        yield user
    finally:
        db.rollback()
        db.query(RevokedSession).filter(RevokedSession.user_id == user.user_id).delete()
        for s in db.query(Story).filter(Story.user_id == user.user_id).all():
            db.delete(s)
        db.commit()
        u = db.query(User).filter(User.user_id == user.user_id).first()
        if u is not None:
            db.delete(u)
            db.commit()
        db.close()


def _signed_in(user) -> TestClient:
    c = TestClient(main.app, raise_server_exceptions=False)
    r = c.post("/api/auth/login", json={"email": user.email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return c


def _csrf(c: TestClient) -> dict:
    return {settings.csrf_header_name: c.cookies.get(settings.csrf_cookie_name)}


# ── sign-in ──────────────────────────────────────────────────────────────────

def test_login_sets_httponly_session_cookie_and_no_token_in_body(account):
    c = TestClient(main.app)
    r = c.post("/api/auth/login", json={"email": account.email, "password": PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert "access_token" not in body and set(body) == {"user"}
    assert body["user"]["user_id"] == account.user_id
    set_cookies = r.headers.get_list("set-cookie")
    session = [h for h in set_cookies if h.startswith(settings.session_cookie_name + "=")]
    csrf = [h for h in set_cookies if h.startswith(settings.csrf_cookie_name + "=")]
    assert len(session) == 1 and len(csrf) == 1
    assert "httponly" in session[0].lower() and "samesite=lax" in session[0].lower()
    assert "httponly" not in csrf[0].lower()          # the page must be able to read it
    # The token itself never appears in the body.
    assert c.cookies.get(settings.session_cookie_name) not in r.text


def test_session_cookie_is_secure_behind_https_proxy(account):
    c = TestClient(main.app)
    r = c.post("/api/auth/login", json={"email": account.email, "password": PASSWORD},
               headers={"X-Forwarded-Proto": "https"})
    session = [h for h in r.headers.get_list("set-cookie") if h.startswith(settings.session_cookie_name + "=")]
    assert "secure" in session[0].lower()


def test_register_sets_session_and_returns_only_user():
    c = TestClient(main.app)
    tag = uuid.uuid4().hex[:8]
    r = c.post("/api/auth/register", json={"email": f"s10r-{tag}@narratiq-internal-test.com",
                                           "username": f"s10r{tag}", "password": PASSWORD})
    try:
        assert r.status_code == 200 and set(r.json()) == {"user"}
        assert c.get("/api/auth/me").status_code == 200
    finally:
        db = SessionLocal()
        db.query(User).filter(User.user_id == r.json()["user"]["user_id"]).delete()
        db.commit()
        db.close()


def test_me_with_cookie_and_without(account):
    c = _signed_in(account)
    assert c.get("/api/auth/me").json()["user_id"] == account.user_id
    assert TestClient(main.app).get("/api/auth/me").status_code == 401


# ── CSRF ─────────────────────────────────────────────────────────────────────

def test_cookie_state_change_requires_matching_csrf_header(account):
    c = _signed_in(account)
    body = {"title": "CSRF probe"}
    r = c.post("/api/projects/", json=body)
    assert r.status_code == 403 and r.json()["error"] == "csrf_failed"
    r = c.post("/api/projects/", json=body, headers={settings.csrf_header_name: "wrong"})
    assert r.status_code == 403
    r = c.post("/api/projects/", json=body, headers=_csrf(c))
    assert r.status_code in (200, 201), r.text
    # Nothing was created by the refused attempts.
    db = SessionLocal()
    try:
        assert db.query(Story).filter(Story.user_id == account.user_id).count() == 1
    finally:
        db.close()


def test_cookie_state_change_from_foreign_origin_is_refused(account):
    c = _signed_in(account)
    r = c.post("/api/projects/", json={"title": "x"},
               headers={**_csrf(c), "Origin": "https://evil.example"})
    assert r.status_code == 403
    ok_origin = settings.cors_origins[0]
    r = c.post("/api/projects/", json={"title": "x"}, headers={**_csrf(c), "Origin": ok_origin})
    assert r.status_code in (200, 201)


def test_bearer_requests_are_not_subject_to_csrf(account):
    token = auth_mod.create_token(account.user_id, account.token_version)
    c = TestClient(main.app)
    r = c.post("/api/projects/", json={"title": "bearer"}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code in (200, 201)


def test_safe_methods_need_no_csrf(account):
    c = _signed_in(account)
    assert c.get("/api/projects/").status_code == 200


# ── logout: this session only ────────────────────────────────────────────────

def test_logout_ends_only_this_session_and_its_copies(account):
    laptop = _signed_in(account)
    phone = _signed_in(account)
    copied = laptop.cookies.get(settings.session_cookie_name)
    r = laptop.post("/api/auth/logout", headers=_csrf(laptop))
    assert r.status_code == 200
    assert laptop.cookies.get(settings.session_cookie_name) is None       # cleared
    # A copy of the ended session's token no longer works anywhere…
    assert TestClient(main.app).get("/api/auth/me",
                                    headers={"Authorization": f"Bearer {copied}"}).status_code == 401
    # …but the other device is still signed in.
    assert phone.get("/api/auth/me").status_code == 200


def test_logout_without_a_valid_session_still_clears_cookies():
    c = TestClient(main.app)
    c.cookies.set(settings.session_cookie_name, "not-a-jwt")
    r = c.post("/api/auth/logout")
    assert r.status_code == 200
    assert any(h.startswith(settings.session_cookie_name + "=") for h in r.headers.get_list("set-cookie"))


def test_revoked_rows_expire_with_the_token(account):
    c = _signed_in(account)
    c.post("/api/auth/logout", headers=_csrf(c))
    db = SessionLocal()
    try:
        row = db.query(RevokedSession).filter(RevokedSession.user_id == account.user_id).one()
        assert abs((row.expires_at - datetime.utcnow()).total_seconds()
                   - settings.jwt_expire_minutes * 60) < 120
    finally:
        db.close()


# ── password change: every other session ─────────────────────────────────────

def test_password_change_ends_every_other_session_and_keeps_this_device(account):
    laptop = _signed_in(account)
    phone = _signed_in(account)
    r = laptop.post("/api/auth/change-password", headers=_csrf(laptop),
                    json={"current_password": PASSWORD, "new_password": "a brand new password"})
    assert r.status_code == 200, r.text
    assert laptop.get("/api/auth/me").status_code == 200       # fresh session here
    assert phone.get("/api/auth/me").status_code == 401        # every other session ended
    fresh = TestClient(main.app)
    assert fresh.post("/api/auth/login", json={"email": account.email, "password": PASSWORD}).status_code == 401
    assert fresh.post("/api/auth/login", json={"email": account.email,
                                               "password": "a brand new password"}).status_code == 200


def test_password_change_validation(account):
    c = _signed_in(account)
    r = c.post("/api/auth/change-password", headers=_csrf(c),
               json={"current_password": "wrong", "new_password": "long enough pw"})
    assert r.status_code == 403
    r = c.post("/api/auth/change-password", headers=_csrf(c),
               json={"current_password": PASSWORD, "new_password": "short"})
    assert r.status_code == 422
    r = c.post("/api/auth/change-password", headers=_csrf(c),
               json={"current_password": PASSWORD, "new_password": PASSWORD})
    assert r.status_code == 422
    assert c.get("/api/auth/me").status_code == 200            # a refused change ends nothing


# ── token format ─────────────────────────────────────────────────────────────

def test_pre_stage10_token_without_jti_or_ver_is_refused(account):
    legacy = jwt.encode({"sub": account.user_id, "exp": datetime.utcnow() + timedelta(hours=1)},
                        settings.secret_key, algorithm=settings.jwt_algorithm)
    r = TestClient(main.app).get("/api/auth/me", headers={"Authorization": f"Bearer {legacy}"})
    assert r.status_code == 401


def test_token_claims(account):
    claims = jwt.get_unverified_claims(auth_mod.create_token(account.user_id, 3))
    assert claims["sub"] == account.user_id and claims["ver"] == 3
    assert claims["jti"] and "iat" in claims and "exp" in claims


# ── voice-socket tickets ─────────────────────────────────────────────────────

def test_ws_ticket_is_single_use_and_expires(account, monkeypatch):
    t = auth_mod.issue_ws_ticket(account.user_id)
    assert auth_mod.consume_ws_ticket(t) == account.user_id
    assert auth_mod.consume_ws_ticket(t) is None                # single use
    monkeypatch.setattr(settings, "ws_ticket_ttl_seconds", 0)
    t2 = auth_mod.issue_ws_ticket(account.user_id)
    time.sleep(0.01)
    assert auth_mod.consume_ws_ticket(t2) is None               # expired
    assert auth_mod.consume_ws_ticket(None) is None
    assert auth_mod.consume_ws_ticket("made-up") is None


def test_ws_ticket_endpoint_requires_a_session(account):
    assert TestClient(main.app).post("/api/auth/ws-ticket").status_code == 401
    c = _signed_in(account)
    r = c.post("/api/auth/ws-ticket", headers=_csrf(c))
    assert r.status_code == 200 and r.json()["ticket"] and r.json()["expires_in"] > 0


def test_voice_socket_accepts_ticket_and_refuses_token_or_foreign_origin(account, monkeypatch):
    monkeypatch.setattr(settings, "voice_agent_enabled", True)
    client = TestClient(main.app)
    token = auth_mod.create_token(account.user_id, account.token_version)
    with client.websocket_connect(f"/api/voice/stream?token={token}") as ws:
        assert ws.receive_json()["code"] == "unauthorized"
    with client.websocket_connect("/api/voice/stream?ticket=forged") as ws:
        assert ws.receive_json()["code"] == "unauthorized"
    ticket = auth_mod.issue_ws_ticket(account.user_id)
    with client.websocket_connect(f"/api/voice/stream?ticket={ticket}",
                                  headers={"Origin": "https://evil.example"}) as ws:
        assert ws.receive_json()["code"] == "forbidden_origin"
    ticket = auth_mod.issue_ws_ticket(account.user_id)
    with client.websocket_connect(f"/api/voice/stream?ticket={ticket}") as ws:
        ws.send_json({"type": "start", "context": {}})
        assert ws.receive_json() == {"type": "state", "value": "listening"}
        ws.send_json({"type": "cancel"})
