"""
Stage 10 — task 10.2 (built-in error tracking, live health, ops metrics) and
task 10.4 (single-worker guard, client-ip keying).

  * /api/health probes vLLM LIVE: vLLM going down after startup turns health
    into 503 "degraded"; coming back turns it into 200 "ok";
  * an unhandled exception becomes an author-readable 500 and ONE scrubbed
    error record — no manuscript text, email, token or id survives scrubbing;
  * /api/ops/* and /api/stats need the ops token and 404 when none is set;
  * frontend error reports are accepted, scrubbed and size-capped;
  * the worker guard refuses >1 worker unless explicitly allowed.

    DATABASE_URL=...narratiq_test pytest backend/tests/test_monitoring_stage10.py -q
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from fastapi import APIRouter  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from config import settings  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import ErrorEvent  # noqa: E402
from services import error_tracking, health_probe  # noqa: E402
from startup import worker_guard  # noqa: E402

MANUSCRIPT = ("Elara pressed her palm to the cold glass and whispered the name of the drowned "
              "city she had sworn never to speak aloud again")


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch):
    from middleware.rate_limit import limiter
    monkeypatch.setattr(limiter, "enabled", False)


@pytest.fixture
def ops(monkeypatch):
    token = uuid.uuid4().hex
    monkeypatch.setattr(settings, "ops_token", token)
    return {"X-Ops-Token": token}


def _set_vllm(monkeypatch, ok: bool):
    async def fake(force: bool = False):
        return ok
    monkeypatch.setattr(health_probe, "vllm_ready", fake)
    main.app.state.embeddings_ready = True


# ── health ───────────────────────────────────────────────────────────────────

def test_health_reports_vllm_loss_after_startup_and_recovery(monkeypatch):
    c = TestClient(main.app)
    _set_vllm(monkeypatch, True)
    r = c.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok" and r.json()["vllm"] == "ready"
    _set_vllm(monkeypatch, False)                       # vLLM dies after startup
    r = c.get("/api/health")
    assert r.status_code == 503
    assert r.json()["status"] == "degraded" and r.json()["vllm"] == "unavailable"
    assert r.json()["backend"] == "ready"
    _set_vllm(monkeypatch, True)                        # and comes back
    assert c.get("/api/health").status_code == 200


def test_health_no_longer_exposes_internal_configuration(monkeypatch):
    _set_vllm(monkeypatch, True)
    body = TestClient(main.app).get("/api/health").json()
    assert "config" not in body and "gpu" not in body
    assert settings.vllm_base_url not in str(body)


@pytest.mark.asyncio
async def test_live_probe_against_an_unreachable_vllm(monkeypatch):
    monkeypatch.setattr(settings, "vllm_base_url", "http://127.0.0.1:9/v1")   # discard port: nothing listens
    health_probe.reset_cache()
    try:
        assert await health_probe.vllm_ready(force=True) is False
    finally:
        health_probe.reset_cache()


# ── error tracking ───────────────────────────────────────────────────────────

_boom = APIRouter()


@_boom.get("/api/_stage10_boom/{story_id}")
def _raise(story_id: str):
    raise ValueError(f"could not parse '{MANUSCRIPT}' for author jane.doe@example.com "
                     f"token=eyJhbGciOi.eyJzdWIiOi.sig story {story_id}")




@pytest.fixture
def mounted():
    """Mount probe routes for one test only, so the Stage 9 route-inventory
    sweeps (which enumerate main.app) never see them."""
    added = []

    def mount(router: APIRouter):
        before = list(main.app.router.routes)
        main.app.include_router(router)
        added.extend(r for r in main.app.router.routes if r not in before)
    yield mount
    for r in added:
        main.app.router.routes.remove(r)


def _events_for(route: str):
    db = SessionLocal()
    try:
        return db.query(ErrorEvent).filter(ErrorEvent.route == route).all()
    finally:
        db.close()


def _purge(route: str):
    db = SessionLocal()
    try:
        db.query(ErrorEvent).filter(ErrorEvent.route == route).delete()
        db.commit()
    finally:
        db.close()


def test_unhandled_error_is_recorded_scrubbed_and_author_readable(mounted):
    mounted(_boom)
    route = "/api/_stage10_boom/{story_id}"
    _purge(route)
    c = TestClient(main.app, raise_server_exceptions=False)
    sid = str(uuid.uuid4())
    try:
        r = c.get(f"/api/_stage10_boom/{sid}")
        assert r.status_code == 500
        body = r.json()
        assert body["error"] == "internal_error" and "saved work is unaffected" in body["message"]
        assert "Traceback" not in r.text and "ValueError" not in r.text
        assert body["request_id"] and r.headers["x-request-id"] == body["request_id"]
        c.get(f"/api/_stage10_boom/{uuid.uuid4()}")          # same fault, different request
        events = _events_for(route)
        assert len(events) == 1 and events[0].occurrences == 2    # de-duplicated
        e = events[0]
        stored = " ".join(str(v) for v in (e.kind, e.route, e.message, e.stack))
        for secret in ("Elara", "drowned", "jane.doe", "example.com", "eyJhbGciOi", sid):
            assert secret not in stored, f"{secret!r} leaked into the error record"
        assert e.kind == "ValueError" and e.route == route and e.status_code == 500
        assert "in _raise" in e.stack                     # frame locations are kept
    finally:
        _purge(route)


def test_scrub_rules():
    s = error_tracking.scrub
    assert "<email>" in s("mail a@b.co now")
    assert "hunter2" not in s("password=hunter2 failed")
    assert "abc.def.ghi" not in s("Bearer abc.def.ghi")
    assert "postgres:pw@" not in s("postgresql://postgres:pw@localhost/db")
    assert "<id>" in s(f"row {uuid.uuid4()} missing")
    out = s(" ".join(["word"] * 40))
    assert out.endswith("…[truncated]") and out.count("word") == error_tracking.MESSAGE_MAX_WORDS
    assert s(None) == ""


def test_error_recording_never_raises(monkeypatch):
    import database

    class Broken:
        def __call__(self):
            raise RuntimeError("db down")
    monkeypatch.setattr(database, "SessionLocal", Broken())
    with pytest.raises(RuntimeError):
        database.SessionLocal()
    monkeypatch.undo()
    # A real failure inside the session is swallowed and reported as False.
    assert error_tracking.record_event(source="backend", kind="X" * 10, route="/r",
                                       message="m", stack="s") in (True, False)


def test_prune_respects_row_cap():
    db = SessionLocal()
    marker = f"prune-{uuid.uuid4().hex[:6]}"
    try:
        for i in range(3):
            error_tracking.record_event(source="backend", kind=marker, route=f"/p/{i}", stack=f"f.py:{i} in x")
        total = db.query(ErrorEvent).count()
        removed = error_tracking.prune_events(retention_days=30, max_rows=total - 2)
        assert removed >= 2
        assert db.query(ErrorEvent).count() == total - 2
    finally:
        db.query(ErrorEvent).filter(ErrorEvent.kind == marker).delete()
        db.commit()
        db.close()


def test_rolling_counters_window():
    now = [1_000_000.0]
    rc = error_tracking.RollingCounters(clock=lambda: now[0])
    rc.incr("requests", 5)
    rc.incr("server_errors")
    now[0] += 10 * 60
    rc.incr("requests")
    assert rc.window(5)["requests"] == 1
    assert rc.window(15) == {**rc.window(15), "requests": 6, "server_errors": 1}
    now[0] += 3 * 3600
    rc.incr("requests")
    assert rc.window(60)["requests"] == 1               # older buckets pruned


# ── client error intake ──────────────────────────────────────────────────────

def test_client_error_report_is_scrubbed_and_accepted():
    kind = f"ClientStage10{uuid.uuid4().hex[:6]}"
    c = TestClient(main.app)
    r = c.post("/api/client-errors", json={
        "kind": kind, "message": f"Failed on '{MANUSCRIPT}' for jane.doe@example.com",
        "stack": f"Error: boom\n    at render (webpack://app/page.js:10:5)\n{MANUSCRIPT}",
        "route": f"/projects/{uuid.uuid4()}/write"})
    assert r.status_code == 202
    db = SessionLocal()
    try:
        e = db.query(ErrorEvent).filter(ErrorEvent.kind == kind).one()
        stored = f"{e.message} {e.stack} {e.route}"
        assert "Elara" not in stored and "jane.doe" not in stored
        assert e.route == "/projects/<id>/write" and "at render" in e.stack and e.source == "frontend"
        db.delete(e)
        db.commit()
    finally:
        db.close()


def test_client_error_report_size_is_capped():
    r = TestClient(main.app).post("/api/client-errors", json={"message": "x" * 5000})
    assert r.status_code == 422


# ── ops endpoints ────────────────────────────────────────────────────────────

def test_ops_endpoints_hidden_without_token_config(monkeypatch):
    monkeypatch.setattr(settings, "ops_token", "")
    c = TestClient(main.app)
    for path in ("/api/ops/status", "/api/ops/metrics", "/api/ops/errors", "/api/stats"):
        assert c.get(path).status_code == 404, path


def test_ops_endpoints_require_the_token(ops, monkeypatch):
    _set_vllm(monkeypatch, True)
    c = TestClient(main.app)
    for path in ("/api/ops/status", "/api/ops/metrics", "/api/ops/errors", "/api/stats"):
        assert c.get(path).status_code == 403, path
        assert c.get(path, headers={"X-Ops-Token": "wrong"}).status_code == 403, path
        assert c.get(path, headers=ops).status_code == 200, path
    m = c.get("/api/ops/metrics", headers=ops).json()
    assert m["vllm"] == "ready"
    assert set(m["http"]["last_15m"]) >= set(error_tracking.COUNTERS)
    assert set(m["background_jobs"]) == {"manuscript_jobs", "story_intel_jobs", "story_bibles",
                                         "narrative_thread_scans", "audio_uploads"}
    assert "ai_parse" in m and "backups" in m and "error_events_last_60m" in m
    s = c.get("/api/ops/status", headers=ops).json()
    assert s["config"]["vllm_model"] == settings.vllm_model_name


def test_ai_unavailable_is_counted(monkeypatch, mounted):
    from exceptions import AIServiceUnavailableError
    router = APIRouter()

    @router.get("/api/_stage10_ai_down")
    def _down():
        raise AIServiceUnavailableError()
    mounted(router)
    before = error_tracking.counters.window(5)["ai_unavailable"]
    r = TestClient(main.app).get("/api/_stage10_ai_down")
    assert r.status_code == 503
    assert error_tracking.counters.window(5)["ai_unavailable"] == before + 1


# ── 10.4: worker guard and client-ip keying ──────────────────────────────────

def test_worker_count_detection():
    wa = worker_guard.workers_from_argv
    assert wa(["uvicorn", "main:app", "--workers", "1"]) == 1
    assert wa(["uvicorn", "main:app", "--workers=4"]) == 4
    assert wa(["gunicorn", "-w", "3"]) == 3
    assert wa(["gunicorn", "-w2"]) == 2
    assert wa(["uvicorn", "main:app"]) is None
    d = worker_guard.detect_worker_count
    assert d(env={}, own=["uvicorn", "--workers", "1"], parent=[]) == 1
    assert d(env={}, own=[], parent=["uvicorn", "--workers", "2"]) == 2
    assert d(env={"WEB_CONCURRENCY": "3"}, own=[], parent=[]) == 3
    assert d(env={"WEB_CONCURRENCY": "junk"}, own=[], parent=[]) == 1


def test_worker_guard_refuses_multiple_workers_unless_allowed():
    kw = dict(env={}, own=["uvicorn", "--workers", "2"], parent=[])
    with pytest.raises(RuntimeError, match="exactly one"):
        worker_guard.enforce_single_worker("", **kw)
    with pytest.raises(RuntimeError):
        worker_guard.enforce_single_worker("true", **kw)       # only the exact word "yes"
    assert worker_guard.enforce_single_worker("yes", **kw) == 2
    assert worker_guard.enforce_single_worker("", env={}, own=["uvicorn", "--workers", "1"], parent=[]) == 1


def test_client_ip_uses_cloudflare_client_only_behind_a_trusted_proxy():
    """Header shapes measured on the pod in the Stage 10 live check."""
    from starlette.requests import Request
    from middleware.rate_limit import client_ip

    def req(peer, **headers):
        raw = [(k.replace("_", "-").encode(), v.encode()) for k, v in headers.items()]
        return Request({"type": "http", "client": (peer, 1), "headers": raw})
    # Browser → Cloudflare → RunPod proxy → Next.js → backend: the edge hop varies,
    # CF-Connecting-IP does not.
    for edge in ("104.23.1.1", "104.23.9.9"):
        assert client_ip(req("127.0.0.1", x_forwarded_for=f"203.0.113.9, {edge}",
                             cf_connecting_ip="203.0.113.9")) == "203.0.113.9"
    # Direct to :8000 through the RunPod proxy (peer in 100.64.0.0/10).
    assert client_ip(req("100.64.1.1", cf_connecting_ip="203.0.113.9")) == "203.0.113.9"
    # Without CF-Connecting-IP, the right-most X-Forwarded-For hop.
    assert client_ip(req("127.0.0.1", x_forwarded_for="6.6.6.6, 203.0.113.9")) == "203.0.113.9"
    # From an untrusted peer every forwarding header is ignored.
    assert client_ip(req("198.51.100.4", cf_connecting_ip="1.2.3.4", x_forwarded_for="1.2.3.4")) == "198.51.100.4"
    assert client_ip(req("127.0.0.1")) == "127.0.0.1"


def test_uvicorn_proxy_headers_warning():
    assert worker_guard.warn_if_uvicorn_proxy_headers(
        own=["python3", "-m", "uvicorn", "main:app", "--workers", "1"], parent=[]) is True
    assert worker_guard.warn_if_uvicorn_proxy_headers(
        own=["python3", "-m", "uvicorn", "main:app", "--no-proxy-headers"], parent=[]) is False
    assert worker_guard.warn_if_uvicorn_proxy_headers(own=["pytest"], parent=["bash"]) is False
