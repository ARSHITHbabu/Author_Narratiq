"""
Regression guard for the voice recording endpoints (corrective plan A, 2026-07-26).

Why this file exists: `routers/voice_agent.py` used `datetime.utcnow()` in
`_resync_workflow` without a module-level import. Every call to
`POST /voice/commands/{id}/confirm` and
`POST /voice/commands/{id}/nodes/{key}/result` raised `NameError` → HTTP 500,
and 44 passing voice tests never noticed, because they exercised helper logic in
isolation and never drove the routes through the application.

So these tests go through the real FastAPI app with a real request:
  - the module imports and every name it uses at call time resolves;
  - both routes return 2xx and actually commit;
  - approval and outcome remain separate facts;
  - a failure report is recorded as a failure.

Run: python3 tests/test_voice_recording_routes.py     (or under pytest)
"""

import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_results = []


def test(fn):
    _results.append(fn)
    return fn


# ── Live-app fixtures ────────────────────────────────────────────────────────

def _app_client():
    from fastapi.testclient import TestClient
    import main
    return TestClient(main.app)


def _seed_command(db, user_id, story_id):
    """A session + command + workflow + one awaiting-confirmation task, exactly the
    shape `interpret` leaves behind when a mutating step needs approval."""
    from models import VoiceSession, VoiceCommand, VoiceWorkflow, VoiceTask
    sess = VoiceSession(session_id=str(uuid.uuid4()), user_id=user_id, story_id=story_id)
    db.add(sess)
    db.flush()
    cmd = VoiceCommand(
        command_id=str(uuid.uuid4()), session_id=sess.session_id, user_id=user_id,
        story_id=story_id, raw_transcript="create a chapter called Storm",
        status="needs_confirmation",
    )
    db.add(cmd)
    db.flush()
    wf = VoiceWorkflow(workflow_id=str(uuid.uuid4()), command_id=cmd.command_id,
                       session_id=sess.session_id, node_count=1,
                       status="awaiting_confirmation")
    db.add(wf)
    db.flush()
    task = VoiceTask(task_id=str(uuid.uuid4()), workflow_id=wf.workflow_id, node_key="n1",
                     capability="chapter_mgmt", action="create",
                     status="awaiting_confirmation")
    db.add(task)
    db.commit()
    return cmd, wf, task, sess


_ACCOUNTS: dict = {}


def _auth(client, db, slot="primary"):
    """A throwaway account created through the app. Cached per slot: the auth
    endpoints are rate-limited to 5/minute per IP, so registering once per test
    would fail the suite for reasons that have nothing to do with the routes."""
    from models import User
    if slot in _ACCOUNTS:
        headers, email = _ACCOUNTS[slot]
        return headers, db.query(User).filter(User.email == email).first()
    email = f"voice-route-test-{slot}-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/register", json={
        "email": email, "username": f"u{uuid.uuid4().hex[:8]}", "password": "RouteTest!2026",
    })
    assert r.status_code in (200, 201), r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    _ACCOUNTS[slot] = (headers, email)
    return headers, db.query(User).filter(User.email == email).first()


def _story(db, user_id):
    from models import Story
    s = Story(story_id=str(uuid.uuid4()), user_id=user_id, title="voice route test")
    db.add(s)
    db.commit()
    return s


def _cleanup(db, user, story, cmd, wf, sess=None):
    from models import VoiceTask, VoiceWorkflow, VoiceCommand, VoiceSession, Story, User
    db.query(VoiceTask).filter(VoiceTask.workflow_id == wf.workflow_id).delete()
    db.query(VoiceWorkflow).filter(VoiceWorkflow.workflow_id == wf.workflow_id).delete()
    db.query(VoiceCommand).filter(VoiceCommand.command_id == cmd.command_id).delete()
    if sess is not None:
        db.query(VoiceSession).filter(VoiceSession.session_id == sess.session_id).delete()
    db.query(Story).filter(Story.story_id == story.story_id).delete()
    db.commit()


# ── The defect that got through: a name that only fails at call time ─────────

@test
def test_resync_workflow_resolves_every_name_it_uses():
    """`datetime` must be importable at module scope — the exact 500's cause."""
    import routers.voice_agent as va
    assert hasattr(va, "datetime"), "voice_agent has no module-level datetime"
    assert callable(va.datetime.utcnow)


@test
def test_no_function_local_datetime_import_remains():
    """A local import inside one function masked the missing module-level one."""
    src = open(os.path.join(os.path.dirname(__file__), "..", "routers", "voice_agent.py")).read()
    assert "    from datetime import datetime" not in src, "redundant local import still present"


# ── The routes, driven through the real application ─────────────────────────

@test
def test_confirm_and_result_routes_succeed_and_commit():
    from database import SessionLocal
    client = _app_client()
    db = SessionLocal()
    headers, user = _auth(client, db)
    story = _story(db, user.user_id)
    cmd, wf, task, sess = _seed_command(db, user.user_id, story.story_id)
    try:
        # Approval — recorded as approval, NOT as success.
        r = client.post(f"/api/voice/commands/{cmd.command_id}/confirm",
                        json={"confirmed": True, "node_key": "n1"}, headers=headers)
        assert r.status_code == 200, f"confirm returned {r.status_code}: {r.text}"
        db.expire_all()
        assert task.status == "executing", task.status
        assert cmd.confirmed is True

        # Outcome — the separate fact.
        r2 = client.post(f"/api/voice/commands/{cmd.command_id}/nodes/n1/result",
                         json={"ok": True, "message": "Chapter created"}, headers=headers)
        assert r2.status_code == 200, f"result returned {r2.status_code}: {r2.text}"
        body = r2.json()
        assert body["recorded"] is True
        assert body["node_status"] == "succeeded", body
        db.expire_all()
        assert task.status == "succeeded", task.status
    finally:
        _cleanup(db, user, story, cmd, wf, sess)
        db.close()


@test
def test_a_failure_report_is_recorded_as_a_failure():
    from database import SessionLocal
    client = _app_client()
    db = SessionLocal()
    headers, user = _auth(client, db)
    story = _story(db, user.user_id)
    cmd, wf, task, sess = _seed_command(db, user.user_id, story.story_id)
    try:
        client.post(f"/api/voice/commands/{cmd.command_id}/confirm",
                    json={"confirmed": True, "node_key": "n1"}, headers=headers)
        r = client.post(f"/api/voice/commands/{cmd.command_id}/nodes/n1/result",
                        json={"ok": False, "message": "the chapter could not be created"},
                        headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["node_status"] == "failed", r.json()
        db.expire_all()
        assert task.status == "failed", task.status
    finally:
        _cleanup(db, user, story, cmd, wf, sess)
        db.close()


@test
def test_declining_is_recorded_as_skipped_not_failed():
    from database import SessionLocal
    client = _app_client()
    db = SessionLocal()
    headers, user = _auth(client, db)
    story = _story(db, user.user_id)
    cmd, wf, task, sess = _seed_command(db, user.user_id, story.story_id)
    try:
        r = client.post(f"/api/voice/commands/{cmd.command_id}/confirm",
                        json={"confirmed": False, "node_key": "n1"}, headers=headers)
        assert r.status_code == 200, r.text
        db.expire_all()
        assert task.status == "skipped", task.status
    finally:
        _cleanup(db, user, story, cmd, wf, sess)
        db.close()


@test
def test_a_late_duplicate_report_changes_nothing():
    from database import SessionLocal
    client = _app_client()
    db = SessionLocal()
    headers, user = _auth(client, db)
    story = _story(db, user.user_id)
    cmd, wf, task, sess = _seed_command(db, user.user_id, story.story_id)
    try:
        client.post(f"/api/voice/commands/{cmd.command_id}/confirm",
                    json={"confirmed": True, "node_key": "n1"}, headers=headers)
        client.post(f"/api/voice/commands/{cmd.command_id}/nodes/n1/result",
                    json={"ok": True, "message": "done"}, headers=headers)
        late = client.post(f"/api/voice/commands/{cmd.command_id}/nodes/n1/result",
                           json={"ok": False, "message": "late failure"}, headers=headers)
        assert late.status_code == 200, late.text
        assert late.json()["recorded"] is False, late.json()
        db.expire_all()
        assert task.status == "succeeded", "a late report resurrected a terminal node"
    finally:
        _cleanup(db, user, story, cmd, wf, sess)
        db.close()


@test
def test_another_users_command_is_refused():
    from database import SessionLocal
    client = _app_client()
    db = SessionLocal()
    owner_headers, owner = _auth(client, db, slot="primary")
    intruder_headers, intruder = _auth(client, db, slot="intruder")
    story = _story(db, owner.user_id)
    cmd, wf, task, sess = _seed_command(db, owner.user_id, story.story_id)
    try:
        r = client.post(f"/api/voice/commands/{cmd.command_id}/nodes/n1/result",
                        json={"ok": True, "message": "not mine"}, headers=intruder_headers)
        assert r.status_code in (403, 404), f"cross-user report returned {r.status_code}"
        db.expire_all()
        assert task.status == "awaiting_confirmation", task.status
    finally:
        _cleanup(db, owner, story, cmd, wf, sess)
        db.close()


if __name__ == "__main__":
    passed = failed = 0
    for fn in _results:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
            passed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL  {fn.__name__}: {type(exc).__name__}: {exc}")
            failed += 1
    print(f"\n{passed}/{passed + failed} passed")
    sys.exit(1 if failed else 0)
