"""
Stage 12 remediation A8 — manuscript import (POST /api/manuscript/upload/{story_id}).

Defects fixed and guarded here:
  * Imported chapters were numbered from 1 regardless of the story's existing
    chapters, so importing into a non-empty story created duplicate chapter
    numbers (no database constraint prevents it).
  * Chapters were created one by one in a background task, so a failure part
    way through left an unreported partial import; the author-facing job
    message was the raw exception text.
  * Plain text was stored as the chapter body with no paragraph markup.

Hermetic: AI indexing (summarize_and_embed_chapter) is stubbed; no vLLM or
BGE-M3 needed. Each test deletes exactly the rows it created.

    DATABASE_URL=...narratiq_test pytest backend/tests/test_manuscript_import.py -q
"""
from __future__ import annotations

import asyncio
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402

from _phase3_helpers import two_authors  # noqa: E402
from exceptions import AIServiceUnavailableError  # noqa: E402
from models import Chapter, ManuscriptJob, Story  # noqa: E402

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

THREE_CHAPTERS = (
    "Chapter 1: The Harbour\n"
    "The rain came in sideways off the harbour.\nIt soaked the ropes.\n\n"
    "Mara counted the boats.\n"
    "Chapter 2: The Key\n"
    "The key was brass & cold <script>alert(1)</script>.\n"
    "Chapter 3\n"
    "Nobody answered the bell.\n"
)


@pytest.fixture(autouse=True)
def no_rate_limit(monkeypatch):
    from middleware.rate_limit import limiter
    monkeypatch.setattr(limiter, "enabled", False)


@pytest.fixture
def stub_index(monkeypatch):
    """Record indexing calls instead of calling the model."""
    from routers import manuscript
    calls = []

    async def fake(chapter_id, story_id, number, content, db):
        calls.append((chapter_id, number, content))

    monkeypatch.setattr(manuscript, "summarize_and_embed_chapter", fake)
    return calls


def _empty_story(db, author) -> str:
    s = Story(user_id=author.uid, title="Import target")
    db.add(s)
    db.commit()
    return s.story_id


def _upload(client, headers, sid, data: bytes, name="book.txt", ctype="text/plain"):
    return client.post(f"/api/manuscript/upload/{sid}", headers=headers,
                       files={"file": (name, data, ctype)})


def _chapters(db, sid):
    db.expire_all()
    return db.query(Chapter).filter(Chapter.story_id == sid).order_by(Chapter.chapter_number).all()


def _drop_jobs(db, sids):
    db.rollback()
    db.query(ManuscriptJob).filter(ManuscriptJob.story_id.in_(sids)).delete(synchronize_session=False)
    db.commit()


def test_import_into_an_empty_story(stub_index):
    with two_authors() as (db, a, _b, client):
        sid = _empty_story(db, a)
        try:
            r = _upload(client, a.headers, sid, THREE_CHAPTERS.encode())
            assert r.status_code == 200, r.text
            assert r.json()["chapter_count"] == 3
            chs = _chapters(db, sid)
            assert [c.chapter_number for c in chs] == [1, 2, 3]
            assert [c.title for c in chs] == ["The Harbour", "The Key", "Chapter 3"]
            # Paragraphs: blank-line separated, hard wraps joined, HTML escaped.
            assert chs[0].content == ("<p>The Harbour</p><p>The rain came in sideways off the harbour. "
                                      "It soaked the ropes.</p><p>Mara counted the boats.</p>")
            assert "<script>" not in chs[1].content and "&lt;script&gt;" in chs[1].content
            assert "&amp;" in chs[1].content
            db.expire_all()
            assert db.get(Story, sid).word_count == sum(c.word_count for c in chs)
        finally:
            _drop_jobs(db, [sid])


def test_import_into_a_story_with_chapters_appends_after_them(stub_index):
    with two_authors() as (db, a, _b, client):
        try:
            before = _chapters(db, a.sid)
            assert [c.chapter_number for c in before] == [1, 2, 3]
            original = {c.chapter_id: c.content for c in before}

            r = _upload(client, a.headers, a.sid, THREE_CHAPTERS.encode())
            assert r.status_code == 200, r.text
            chs = _chapters(db, a.sid)
            numbers = [c.chapter_number for c in chs]
            assert numbers == [1, 2, 3, 4, 5, 6]
            assert len(set(numbers)) == len(numbers), "duplicate chapter numbers"
            # Existing chapters untouched.
            for c in chs[:3]:
                assert c.content == original[c.chapter_id]
            # Untitled imported chapter is named by its real number.
            assert chs[5].title == "Chapter 6"
        finally:
            _drop_jobs(db, [a.sid])


def test_docx_import(stub_index):
    from docx import Document as DocxDocument
    doc = DocxDocument()
    for line in ("Chapter 1", "First paragraph.", "Second paragraph."):
        doc.add_paragraph(line)
    buf = io.BytesIO()
    doc.save(buf)
    with two_authors() as (db, a, _b, client):
        sid = _empty_story(db, a)
        try:
            r = _upload(client, a.headers, sid, buf.getvalue(), "book.docx", DOCX)
            assert r.status_code == 200, r.text
            chs = _chapters(db, sid)
            assert len(chs) >= 1
            assert "<p>First paragraph.</p><p>Second paragraph.</p>" in chs[-1].content
        finally:
            _drop_jobs(db, [sid])


@pytest.mark.parametrize("data,name,ctype,code", [
    (b"%PDF-1.4 not allowed", "book.pdf", "application/pdf", 400),
    (b"PK\x03\x04 garbage that is not a docx", "book.docx", DOCX, 422),
    (b"   \n\n  ", "empty.txt", "text/plain", 422),
])
def test_rejected_uploads_import_nothing(data, name, ctype, code, stub_index):
    with two_authors() as (db, a, _b, client):
        sid = _empty_story(db, a)
        try:
            r = _upload(client, a.headers, sid, data, name, ctype)
            assert r.status_code == code, r.text
            detail = r.json()["detail"]
            assert "Traceback" not in detail and "Error" not in detail
            assert _chapters(db, sid) == []
            assert db.query(ManuscriptJob).filter(ManuscriptJob.story_id == sid).count() == 0
        finally:
            _drop_jobs(db, [sid])


def test_cannot_import_into_or_read_jobs_of_another_author(stub_index):
    with two_authors() as (db, a, b, client):
        try:
            r = _upload(client, a.headers, b.sid, THREE_CHAPTERS.encode())
            assert r.status_code == 404
            assert len(_chapters(db, b.sid)) == 3

            r = _upload(client, b.headers, b.sid, THREE_CHAPTERS.encode())
            assert r.status_code == 200
            job_id = r.json()["job_id"]
            assert client.get(f"/api/manuscript/job/{job_id}", headers=a.headers).status_code == 404
            assert client.get(f"/api/manuscript/job/{job_id}", headers=b.headers).status_code == 200
        finally:
            _drop_jobs(db, [a.sid, b.sid])


def test_a_second_import_while_one_is_running_is_refused(stub_index):
    with two_authors() as (db, a, _b, client):
        try:
            db.add(ManuscriptJob(story_id=a.sid, user_id=a.uid, status="processing"))
            db.commit()
            r = _upload(client, a.headers, a.sid, THREE_CHAPTERS.encode())
            assert r.status_code == 409
            assert len(_chapters(db, a.sid)) == 3
        finally:
            _drop_jobs(db, [a.sid])


def test_save_failure_rolls_back_every_chapter(stub_index, monkeypatch):
    """If saving fails part way, nothing is imported and the author is told so."""
    from routers import manuscript

    real = manuscript._text_to_html
    count = {"n": 0}

    def flaky(text):
        count["n"] += 1
        if count["n"] == 2:
            raise RuntimeError("disk full")
        return real(text)

    monkeypatch.setattr(manuscript, "_text_to_html", flaky)
    with two_authors() as (db, a, _b, client):
        try:
            r = _upload(client, a.headers, a.sid, THREE_CHAPTERS.encode())
            assert r.status_code == 500
            assert "Nothing was imported" in r.json()["detail"]
            assert "disk full" not in r.json()["detail"]
            assert [c.chapter_number for c in _chapters(db, a.sid)] == [1, 2, 3]
        finally:
            _drop_jobs(db, [a.sid])


def _run_index(db, a, sid, monkeypatch, fail_at=None):
    from routers import manuscript

    seen = []

    async def fake(chapter_id, story_id, number, content, db_):
        if fail_at is not None and len(seen) == fail_at:
            raise AIServiceUnavailableError("vLLM down")
        seen.append(number)

    monkeypatch.setattr(manuscript, "summarize_and_embed_chapter", fake)
    job = ManuscriptJob(story_id=sid, user_id=a.uid, status="processing", chapter_count=3)
    db.add(job)
    db.commit()
    created = [(c.chapter_id, c.chapter_number, c.content) for c in _chapters(db, sid)]
    asyncio.run(manuscript._index_pipeline(job.job_id, sid, created))
    db.expire_all()
    return db.get(ManuscriptJob, job.job_id), seen


def test_indexing_completes(monkeypatch):
    with two_authors() as (db, a, _b, _client):
        try:
            job, seen = _run_index(db, a, a.sid, monkeypatch)
            assert job.status == "complete" and job.percent == 100
            assert seen == [1, 2, 3]
            assert job.message == "3 chapters imported."
        finally:
            _drop_jobs(db, [a.sid])


def test_indexing_failure_is_reported_as_partial_and_keeps_every_chapter(monkeypatch):
    with two_authors() as (db, a, _b, _client):
        try:
            job, seen = _run_index(db, a, a.sid, monkeypatch, fail_at=1)
            assert job.status == "partial"
            assert "All 3 chapters were imported and saved" in job.message
            assert "2 of them" in job.message
            assert "vLLM" not in job.message
            assert len(_chapters(db, a.sid)) == 3
        finally:
            _drop_jobs(db, [a.sid])
