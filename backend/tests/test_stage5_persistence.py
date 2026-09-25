"""
Stage 5 live-review fixes D1 (Narrative Threads scan is observable) and D2
(Manuscript Report is saved), plus review items M2 (one scan / one report
row per story), M3 (both new tables cascade on story delete) and the orphan
sweep. Integration tests against the allow-listed test database; the model
is never called (the analysis and scan pipeline are replaced by fakes).

    DATABASE_URL=...narratiq_test pytest backend/tests/test_stage5_persistence.py -q
"""
import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402

from _phase3_helpers import two_authors  # noqa: E402
from models import (  # noqa: E402
    Chapter, ChapterSummary, Character, ManuscriptReportRecord, NarrativeThread, NarrativeThreadScan, Story,
)
import routers.manuscript_report as mr  # noqa: E402
import routers.narrative_threads as nt  # noqa: E402


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _index(db, author, relationship=True):
    """Give each of the author's 3 chapters an indexed summary."""
    chars = {c.name: c.character_id for c in db.query(Character).filter(Character.story_id == author.sid)}
    for ch in author.chapters:
        rel = ([{"characters": [chars["Elara"], chars["Kira"]], "change": f"trust shifts in {ch.chapter_number}"}]
               if relationship else None)
        db.add(ChapterSummary(
            chapter_id=ch.chapter_id, story_id=author.sid, chapter_number=ch.chapter_number,
            key_events=["Elara walks the corridor"], characters_present=["Elara", "Kira"] if ch.chapter_number < 2 else [],
            locations=["corridor"], timeline_markers=[], emotional_tone="tense",
            chapter_purpose="Raises the stakes", raw_summary="summary", relationship_changes=rel,
        ))
    db.commit()


FAKE_RESULT = {
    "character_arcs": [{"name": "Elara", "appears_in": [1, 2], "arc_summary": "grows bolder", "completeness": "partial"}],
    "pacing": {"slow_chapters": [2], "intense_chapters": [3], "assessment": "steady"},
    "unresolved_threads": [], "strengths": [{"text": "vivid corridor", "chapters": [1]}],
    "improvements": [{"text": "tighten chapter 2", "chapters": [2]}],
    "stakes": None, "themes": [], "chapters_analyzed": 3, "word_count_total": 90,
    "chapter_plot_importance": {}, "deterministic_open_threads": [], "citations_suppressed": 0,
}


@pytest.fixture
def fake_analysis(monkeypatch):
    calls = []

    async def fake(story_id, chapters, strategy="summary_pass", db=None):
        calls.append(story_id)
        return dict(FAKE_RESULT)
    monkeypatch.setattr(mr, "analyze_manuscript", fake)
    return calls


# ── D2: the report is saved and re-fetchable ─────────────────────────────────

def test_report_round_trip_post_then_get(fake_analysis):
    with two_authors() as (db, a, _b, client):
        _index(db, a)
        assert client.get(f"/api/stories/{a.sid}/manuscript-report", headers=a.headers).status_code == 404
        r = client.post(f"/api/stories/{a.sid}/manuscript-report", headers=a.headers)
        assert r.status_code == 200, r.text
        posted = r.json()
        got = client.get(f"/api/stories/{a.sid}/manuscript-report", headers=a.headers)
        assert got.status_code == 200
        saved = got.json()
        for key in ("chapters_analyzed", "strengths", "improvements", "character_arcs", "pacing",
                    "relationship_arcs", "narrative_signals"):
            assert saved[key] == posted[key], key
        assert saved["is_stale"] is False and saved["generated_at"]
        # Deterministic sections are present and cite chapters.
        assert saved["relationship_arcs"][0]["characters"] == ["Elara", "Kira"]
        assert [c["chapter"] for c in saved["relationship_arcs"][0]["changes"]] == [1, 2, 3]


def test_regenerating_replaces_the_single_row(fake_analysis):
    with two_authors() as (db, a, _b, client):
        _index(db, a)
        client.post(f"/api/stories/{a.sid}/manuscript-report", headers=a.headers)
        first = db.query(ManuscriptReportRecord).filter(ManuscriptReportRecord.story_id == a.sid).one()
        first_id, first_updated = first.report_id, first.updated_at
        db.expire_all()
        client.post(f"/api/stories/{a.sid}/manuscript-report", headers=a.headers)
        rows = db.query(ManuscriptReportRecord).filter(ManuscriptReportRecord.story_id == a.sid).all()
        assert len(rows) == 1 and rows[0].report_id == first_id and rows[0].updated_at >= first_updated
        assert len(fake_analysis) == 2


def test_editing_a_chapter_marks_the_saved_report_stale(fake_analysis):
    with two_authors() as (db, a, _b, client):
        _index(db, a)
        client.post(f"/api/stories/{a.sid}/manuscript-report", headers=a.headers)
        ch = db.query(Chapter).filter(Chapter.chapter_id == a.chapters[1].chapter_id).one()
        ch.updated_at = datetime.utcnow() + timedelta(seconds=5)
        db.commit()
        assert client.get(f"/api/stories/{a.sid}/manuscript-report", headers=a.headers).json()["is_stale"] is True


def test_reindexing_marks_the_saved_report_stale(fake_analysis):
    with two_authors() as (db, a, _b, client):
        _index(db, a)
        client.post(f"/api/stories/{a.sid}/manuscript-report", headers=a.headers)
        s = db.query(ChapterSummary).filter(ChapterSummary.story_id == a.sid, ChapterSummary.chapter_number == 3).one()
        s.is_stale = True
        db.commit()
        assert client.get(f"/api/stories/{a.sid}/manuscript-report", headers=a.headers).json()["is_stale"] is True


def test_another_author_cannot_read_or_generate_the_report(fake_analysis):
    with two_authors() as (db, a, b, client):
        _index(db, a)
        client.post(f"/api/stories/{a.sid}/manuscript-report", headers=a.headers)
        assert client.get(f"/api/stories/{a.sid}/manuscript-report", headers=b.headers).status_code == 404
        assert client.post(f"/api/stories/{a.sid}/manuscript-report", headers=b.headers).status_code == 404
        assert len(fake_analysis) == 1


def test_analysis_error_text_is_never_echoed(monkeypatch):
    async def boom(*a, **kw):
        raise ValueError("internal detail /workspace/secret-path")
    monkeypatch.setattr(mr, "analyze_manuscript", boom)
    with two_authors() as (db, a, _b, client):
        _index(db, a)
        r = client.post(f"/api/stories/{a.sid}/manuscript-report", headers=a.headers)
        assert r.status_code == 503 and "secret-path" not in r.text


def test_unreadable_saved_row_is_treated_as_missing(fake_analysis):
    with two_authors() as (db, a, _b, client):
        _index(db, a)
        client.post(f"/api/stories/{a.sid}/manuscript-report", headers=a.headers)
        row = db.query(ManuscriptReportRecord).filter(ManuscriptReportRecord.story_id == a.sid).one()
        row.content_json = "{not json"
        db.commit()
        assert client.get(f"/api/stories/{a.sid}/manuscript-report", headers=a.headers).status_code == 404


# ── D1: the thread scan is observable, one at a time ─────────────────────────

class _DummyTask:
    def add_done_callback(self, cb):
        pass


class _Capture:
    """Stands in for asyncio inside the router so the background coroutine is
    captured (TestClient would cancel a real task) and run explicitly."""

    def __init__(self):
        self.coros = []

    def create_task(self, coro):
        self.coros.append(coro)
        return _DummyTask()


@pytest.fixture
def captured(monkeypatch):
    cap = _Capture()
    monkeypatch.setattr(nt, "asyncio", cap)
    return cap


def _fake_pipeline(monkeypatch, count=0, stats=None, exc=None):
    async def fake(story_id, user_id, stats=None, _preset=stats):
        if stats is not None:
            stats.update(_preset or {})
        if exc is not None:
            raise exc
        return count
    monkeypatch.setattr(nt, "_run_scan_pipeline", fake)


def _status(client, author):
    r = client.get(f"/api/stories/{author.sid}/narrative-threads/scan-status", headers=author.headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_scan_requires_indexed_chapters(captured):
    with two_authors() as (_db, a, _b, client):
        assert client.post(f"/api/stories/{a.sid}/narrative-threads/scan", headers=a.headers).status_code == 422
        assert _status(client, a)["status"] == "none"


def test_scan_lifecycle_pending_to_completed(captured, monkeypatch):
    _fake_pipeline(monkeypatch, count=2, stats={"chapters_scanned": 3, "batches": 1})
    with two_authors() as (db, a, _b, client):
        _index(db, a)
        r = client.post(f"/api/stories/{a.sid}/narrative-threads/scan", headers=a.headers)
        assert r.status_code == 200 and r.json()["status"] == "pending"
        assert _status(client, a)["status"] == "pending"
        run(captured.coros[0])
        st = _status(client, a)
        assert st["status"] == "completed" and st["threads_written"] == 2 and st["chapters_scanned"] == 3
        assert st["finished_at"] and st["scan_id"] == r.json()["job_id"]


def test_second_scan_while_active_returns_the_same_scan(captured, monkeypatch):
    _fake_pipeline(monkeypatch, count=1)
    with two_authors() as (db, a, _b, client):
        _index(db, a)
        first = client.post(f"/api/stories/{a.sid}/narrative-threads/scan", headers=a.headers).json()
        second = client.post(f"/api/stories/{a.sid}/narrative-threads/scan", headers=a.headers)
        assert second.status_code == 200 and second.json()["job_id"] == first["job_id"]
        assert len(captured.coros) == 1, "no second scan was started"
        assert db.query(NarrativeThreadScan).filter(NarrativeThreadScan.story_id == a.sid).count() == 1
        run(captured.coros[0])
        # Once finished, a new scan reuses the one row with a fresh id.
        third = client.post(f"/api/stories/{a.sid}/narrative-threads/scan", headers=a.headers).json()
        assert third["job_id"] != first["job_id"] and len(captured.coros) == 2
        assert db.query(NarrativeThreadScan).filter(NarrativeThreadScan.story_id == a.sid).count() == 1
        captured.coros[1].close()


@pytest.mark.parametrize("count, stats, exc, expected, code", [
    (0, {"batches": 2, "batches_failed": 0}, None, "completed_empty", None),
    (0, {"batches": 2, "batches_failed": 2}, None, "failed", "unreadable"),
    (0, {}, "ai", "failed", "ai_unavailable"),
    (0, {}, "boom", "failed", "scan_error"),
])
def test_scan_outcomes_are_reported_honestly(captured, monkeypatch, count, stats, exc, expected, code):
    from exceptions import AIServiceUnavailableError
    err = {"ai": AIServiceUnavailableError(), "boom": RuntimeError("x")}.get(exc)
    _fake_pipeline(monkeypatch, count=count, stats=stats, exc=err)
    with two_authors() as (db, a, _b, client):
        _index(db, a)
        client.post(f"/api/stories/{a.sid}/narrative-threads/scan", headers=a.headers)
        run(captured.coros[0])
        st = _status(client, a)
        assert (st["status"], st["error_code"]) == (expected, code)


def test_scan_status_is_owner_only(captured, monkeypatch):
    _fake_pipeline(monkeypatch)
    with two_authors() as (db, a, b, client):
        _index(db, a)
        client.post(f"/api/stories/{a.sid}/narrative-threads/scan", headers=a.headers)
        assert client.get(f"/api/stories/{a.sid}/narrative-threads/scan-status",
                          headers=b.headers).status_code == 404
        assert client.post(f"/api/stories/{a.sid}/narrative-threads/scan", headers=b.headers).status_code == 404
        assert len(captured.coros) == 1
        captured.coros[0].close()


def test_scan_pipeline_writes_threads_from_extracted_events(monkeypatch):
    """The real pipeline with a fake extractor: the name filter no longer drops
    two-word specific names, and the lifecycle is computed."""
    async def fake_extract(summaries, stats=None):
        stats.update({"batches": 1})
        return [{"thread_name": "Forged contract", "chapter_number": 1, "action": "introduced", "description": "d"},
                {"thread_name": "Forged contract", "chapter_number": 3, "action": "developed", "description": ""},
                {"thread_name": "Mystery", "chapter_number": 1, "action": "introduced", "description": ""}]

    async def no_cluster(names):
        return {n: n for n in names}
    monkeypatch.setattr(nt, "extract_narrative_threads_from_summaries", fake_extract)
    monkeypatch.setattr(nt, "_cluster_thread_names", no_cluster)
    with two_authors() as (db, a, _b, _client):
        _index(db, a)
        stats = {}
        assert run(nt._run_scan_pipeline(a.sid, a.uid, stats=stats)) == 1
        t = db.query(NarrativeThread).filter(NarrativeThread.story_id == a.sid).one()
        assert (t.name, t.introduced_chapter, t.last_seen_chapter, t.status) == ("Forged contract", 1, 3, "open")
        assert stats["chapters_scanned"] == 3


# ── Orphan sweep and cascade (M3) ────────────────────────────────────────────

def test_orphan_recovery_fails_interrupted_scans():
    from startup.orphan_recovery import recover_orphaned_jobs
    with two_authors() as (db, a, b, _client):
        db.add(NarrativeThreadScan(story_id=a.sid, user_id=a.uid, status="running"))
        db.add(NarrativeThreadScan(story_id=b.sid, user_id=b.uid, status="completed"))
        db.commit()
        run(recover_orphaned_jobs())
        db.expire_all()
        sa = db.query(NarrativeThreadScan).filter(NarrativeThreadScan.story_id == a.sid).one()
        sb = db.query(NarrativeThreadScan).filter(NarrativeThreadScan.story_id == b.sid).one()
        assert (sa.status, sa.error_code) == ("failed", "interrupted") and sb.status == "completed"


def test_deleting_a_project_removes_its_scan_and_saved_report(fake_analysis):
    with two_authors() as (db, a, b, client):
        _index(db, a)
        client.post(f"/api/stories/{a.sid}/manuscript-report", headers=a.headers)
        db.add(NarrativeThreadScan(story_id=a.sid, user_id=a.uid, status="completed"))
        db.add(NarrativeThreadScan(story_id=b.sid, user_id=b.uid, status="completed"))
        db.commit()
        sid = a.sid
        r = client.delete(f"/api/projects/{sid}", headers=a.headers)
        assert r.status_code == 200, r.text
        db.expire_all()
        assert db.query(ManuscriptReportRecord).filter(ManuscriptReportRecord.story_id == sid).count() == 0
        assert db.query(NarrativeThreadScan).filter(NarrativeThreadScan.story_id == sid).count() == 0
        assert db.query(Story).filter(Story.story_id == sid).count() == 0
        assert db.query(NarrativeThreadScan).filter(NarrativeThreadScan.story_id == b.sid).count() == 1


def test_db_level_cascade_also_removes_rows():
    """ON DELETE CASCADE on the FK, not only the ORM relationship."""
    from sqlalchemy import text
    with two_authors() as (db, a, _b, _client):
        db.add(NarrativeThreadScan(story_id=a.sid, user_id=a.uid, status="completed"))
        db.add(ManuscriptReportRecord(story_id=a.sid, user_id=a.uid, content_json="{}", source_fingerprint=""))
        db.commit()
        rules = dict(db.execute(text(
            "SELECT conrelid::regclass::text, confdeltype FROM pg_constraint "
            "WHERE contype='f' AND confrelid='stories'::regclass "
            "AND conrelid IN ('narrative_thread_scans'::regclass, 'manuscript_reports'::regclass)")).all())
        assert rules == {"narrative_thread_scans": "c", "manuscript_reports": "c"}


# ── 5.14: the continuity check receives the signals ──────────────────────────

def test_continuity_check_passes_timeline_and_flash_suppressed_signals(monkeypatch):
    import routers.analysis as an
    from models import StoryTimelineEvent
    from services.ai_service import DegradedMeta
    seen = []

    async def fake_check(profiles, summaries, notes, cards, signals_block=""):
        seen.append(signals_block)
        return [], DegradedMeta(False, None, 1, 0)
    monkeypatch.setattr(an, "check_continuity", fake_check)
    with two_authors() as (db, a, _b, client):
        _index(db, a)
        for n, marker in ((1, "1998"), (2, "1995"), (3, "1990")):
            s = db.query(ChapterSummary).filter(ChapterSummary.story_id == a.sid,
                                                ChapterSummary.chapter_number == n).one()
            s.timeline_markers = [marker]
        # Story Intelligence marks chapter 3 as a flashback (non-stale) → suppressed.
        db.add(StoryTimelineEvent(story_id=a.sid, chapter_number=3, is_flashback=True, is_stale=False))
        db.commit()
        r = client.post(f"/api/stories/{a.sid}/continuity-check", headers=a.headers)
        assert r.status_code == 200, r.text
        block = seen[0]
        assert "chapters 1 and 2" in block and "chapters 1 and 3" not in block
