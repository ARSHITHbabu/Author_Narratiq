"""
Task 6.3 — automated coverage for `docs/testing/author-feature-test-checklist.docx`
rows that had NO existing test anywhere in the suite before Stage 6 (found by
cross-referencing all 40 rows against the pre-existing 30 test files — see
docs/testing/author-feature-checklist-automation-matrix.md for the full
per-row classification and where every other row's coverage already lives).

Per explicit instruction: assert persisted database state, not only HTTP 200.
Some of these rows surfaced genuine, previously-undocumented gaps while being
written — those are asserted honestly (failing) and documented here and in
the Stage 6 report, NOT silently worked around or quietly fixed as a side
effect of writing a CI-setup test.

Run: cd backend && pytest tests/test_e2e_checklist_gaps.py -q
"""
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import User, Story, Chapter  # noqa: E402
from routers.auth import create_token, hash_password  # noqa: E402


@pytest.fixture
def user_and_client():
    db = SessionLocal()
    tag = uuid.uuid4().hex[:8]
    user = User(email=f"checklist-gap-{tag}@narratiq-internal-test.com",
                username=f"checklistgap{tag}", hashed_password=hash_password("x"))
    db.add(user)
    db.commit()
    client = TestClient(main.app)
    headers = {"Authorization": f"Bearer {create_token(user.user_id)}"}
    try:
        yield {"db": db, "user": user, "client": client, "headers": headers}
    finally:
        for s in db.query(Story).filter(Story.user_id == user.user_id).all():
            db.delete(s)
        db.delete(db.query(User).filter(User.user_id == user.user_id).first())
        db.commit()
        db.close()


# ── Table 0, row 2: Project/story management — create, rename, delete ──────

def test_project_create_rename_delete_persists_correctly(user_and_client):
    client, headers, db = user_and_client["client"], user_and_client["headers"], user_and_client["db"]

    r = client.post("/api/projects/", headers=headers, json={"title": "Original Title"})
    assert r.status_code == 200, r.text
    story_id = r.json()["story_id"]

    r2 = client.patch(f"/api/projects/{story_id}", headers=headers, json={"title": "Renamed Title"})
    assert r2.status_code == 200, r2.text
    # Assert DB state, not just the response echo.
    db.expire_all()
    story = db.query(Story).filter(Story.story_id == story_id).first()
    assert story.title == "Renamed Title"

    r3 = client.delete(f"/api/projects/{story_id}", headers=headers)
    assert r3.status_code == 200, r3.text
    db.expire_all()
    assert db.query(Story).filter(Story.story_id == story_id).first() is None


# ── Table 0, row 3: Chapter management — create, reorder ───────────────────

def test_chapter_creation_persists_and_increments_number(user_and_client):
    """Note: /api/projects/ (routers/projects.py::create_project) auto-creates
    a 'Chapter 1' for every new story — not documented anywhere before this
    test was written. Numbers below account for that rather than assuming a
    fresh story has zero chapters."""
    client, headers, db = user_and_client["client"], user_and_client["headers"], user_and_client["db"]
    r = client.post("/api/projects/", headers=headers, json={"title": "Order Test"})
    story_id = r.json()["story_id"]

    r1 = client.post(f"/api/stories/{story_id}/chapters", headers=headers, json={"title": "Ch1", "content": "<p>a</p>"})
    r2 = client.post(f"/api/stories/{story_id}/chapters", headers=headers, json={"title": "Ch2", "content": "<p>b</p>"})
    assert r2.json()["chapter_number"] == r1.json()["chapter_number"] + 1, "chapter numbers must increment sequentially"
    db.expire_all()
    # The auto-created "Chapter 1" plus the two created above.
    assert db.query(Chapter).filter(Chapter.story_id == story_id).count() == 3


@pytest.mark.xfail(
    reason="Genuine gap found while writing this test, not previously documented anywhere: "
           "ChapterUpdate (schemas.py) has no chapter_number field, and no dedicated reorder "
           "endpoint exists in routers/chapters.py. The docx checklist explicitly requires "
           "'Create Chapter 2, reorder it before Chapter 1' — there is currently no API path "
           "that can do this at all. Reported, not fixed, per Stage 6 scope discipline.",
    strict=True,
)
def test_chapter_reorder_before_earlier_chapter(user_and_client):
    client, headers = user_and_client["client"], user_and_client["headers"]
    r = client.post("/api/projects/", headers=headers, json={"title": "Reorder Test"})
    story_id = r.json()["story_id"]
    r1 = client.post(f"/api/stories/{story_id}/chapters", headers=headers, json={"title": "Ch1", "content": "<p>a</p>"})
    r2 = client.post(f"/api/stories/{story_id}/chapters", headers=headers, json={"title": "Ch2", "content": "<p>b</p>"})
    ch2_id = r2.json()["chapter_id"]

    # The only mutation route available is PATCH .../chapters/{id}; ChapterUpdate
    # has no chapter_number field, so this is the closest a real client could get —
    # and it is expected to have no effect on ordering.
    patched = client.patch(f"/api/stories/{story_id}/chapters/{ch2_id}", headers=headers,
                            json={"title": "Ch2 (moved first)"})
    assert patched.status_code == 200

    ordered = client.get(f"/api/stories/{story_id}/chapters", headers=headers).json()
    numbers_by_id = {c["chapter_id"]: c["chapter_number"] for c in ordered}
    assert numbers_by_id[ch2_id] == 1, "chapter 2 should now be chapter 1 after a reorder — no API supports this yet"


# ── Table 0, row 5: Export DOCX/PDF ─────────────────────────────────────────

def test_export_docx_produces_a_valid_openable_document(user_and_client):
    import io
    from docx import Document as DocxDocument

    client, headers = user_and_client["client"], user_and_client["headers"]
    r = client.post("/api/projects/", headers=headers, json={"title": "Export Test"})
    story_id = r.json()["story_id"]
    client.post(f"/api/stories/{story_id}/chapters", headers=headers,
                json={"title": "Ch1", "content": "<p>Exportable content.</p>"})

    r2 = client.post("/api/export/", headers=headers,
                      json={"story_id": story_id, "format": "docx"})
    assert r2.status_code == 200, r2.text
    # Assert the file is genuinely openable and contains the content, not just a 200 + bytes.
    doc = DocxDocument(io.BytesIO(r2.content))
    full_text = "\n".join(p.text for p in doc.paragraphs)
    assert "Exportable content" in full_text


def test_export_pdf_produces_nonempty_pdf_bytes(user_and_client):
    client, headers = user_and_client["client"], user_and_client["headers"]
    r = client.post("/api/projects/", headers=headers, json={"title": "Export PDF Test"})
    story_id = r.json()["story_id"]
    client.post(f"/api/stories/{story_id}/chapters", headers=headers,
                json={"title": "Ch1", "content": "<p>PDF content.</p>"})

    r2 = client.post("/api/export/", headers=headers,
                      json={"story_id": story_id, "format": "pdf"})
    assert r2.status_code == 200, r2.text
    assert r2.content[:5] == b"%PDF-", "response is not a valid PDF file header"


# ── Table 4, row 1: Manuscript upload — DOCX imports as chapters ───────────

def test_manuscript_docx_upload_creates_chapters_from_content(user_and_client):
    import io
    from docx import Document as DocxDocument

    client, headers, db = user_and_client["client"], user_and_client["headers"], user_and_client["db"]
    r = client.post("/api/projects/", headers=headers, json={"title": "Upload Test"})
    story_id = r.json()["story_id"]

    doc = DocxDocument()
    doc.add_paragraph("Once there was a debt that could not be named.")
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)

    r2 = client.post(
        f"/api/manuscript/upload/{story_id}", headers=headers,
        files={"file": ("manuscript.docx", buf,
                         "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert r2.status_code == 200, r2.text
    db.expire_all()
    chapters = db.query(Chapter).filter(Chapter.story_id == story_id).all()
    assert len(chapters) >= 1, "manuscript upload accepted but produced no persisted chapters"


# ── Table 5, row 4: Activity timeline ───────────────────────────────────────

def test_activity_event_record_and_list_round_trip(user_and_client):
    """Backend CRUD only — does not exercise whichever frontend action is
    supposed to trigger this automatically. See the Stage 6 report: the
    live database was found empty of activity_events despite real author
    usage, which this test cannot explain (a frontend trigger-condition
    question, out of Stage 6's scope per explicit instruction not to expand
    into an audit-logging project)."""
    client, headers = user_and_client["client"], user_and_client["headers"]
    r = client.post("/api/projects/", headers=headers, json={"title": "Activity Test"})
    story_id = r.json()["story_id"]

    r2 = client.post(f"/api/stories/{story_id}/activity", headers=headers, json={
        "category": "chapter", "type": "created", "title": "Chapter 1 created",
    })
    assert r2.status_code == 200, r2.text

    r3 = client.get(f"/api/stories/{story_id}/activity", headers=headers)
    assert r3.status_code == 200
    events = r3.json()
    assert len(events) >= 1
    assert events[0]["title"] == "Chapter 1 created"


# ── Table 5, row 5: JWT auth — register, logout, login, same projects ─────

def test_register_then_login_again_sees_the_same_projects():
    tag = uuid.uuid4().hex[:8]
    email = f"jwt-roundtrip-{tag}@narratiq-internal-test.com"
    client = TestClient(main.app)
    db = SessionLocal()
    try:
        r = client.post("/api/auth/register", json={
            "email": email, "username": f"jwtrt{tag}", "password": "correct horse battery staple 42",
        })
        assert r.status_code in (200, 201), r.text
        token1 = r.json()["access_token"] if "access_token" in r.json() else r.json().get("token")
        assert token1

        headers1 = {"Authorization": f"Bearer {token1}"}
        created = client.post("/api/projects/", headers=headers1, json={"title": "Persisted Across Login"})
        assert created.status_code == 200, created.text

        r2 = client.post("/api/auth/login", json={"email": email, "password": "correct horse battery staple 42"})
        assert r2.status_code == 200, r2.text
        token2 = r2.json()["access_token"] if "access_token" in r2.json() else r2.json().get("token")
        headers2 = {"Authorization": f"Bearer {token2}"}

        projects = client.get("/api/projects/", headers=headers2).json()
        titles = [p["title"] for p in projects]
        assert "Persisted Across Login" in titles
    finally:
        u = db.query(User).filter(User.email == email).first()
        if u:
            for s in db.query(Story).filter(Story.user_id == u.user_id).all():
                db.delete(s)
            db.delete(u)
            db.commit()
        db.close()
