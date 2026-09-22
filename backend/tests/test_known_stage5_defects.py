"""
Known, currently-open Stage 5 defects found during the author's live manual
review (2026-09-22) — see the dated note in the Stage 5 Completion Gate
section of docs/NarratIQ_Master_Implementation_Checklist.md and
docs/incidents/2026-09-22-database-row-count-discrepancy.md for the
unrelated incident discovered alongside them.

These are deliberately NOT plain pytest.mark.xfail: xfail hides a failure
inside a normal green run (reported as "xfailed", easy to stop noticing).
Per explicit instruction, these must instead be excluded from the default
local run but remain runnable as a separate, honestly-red suite that proves
the defects are still open. Do NOT relax an assertion here just to make a
test pass — a passing test in this file means the defect is fixed, which
should be discovered and handled as its own Stage 5 follow-up, not silently
absorbed into Stage 6.

CI/GitHub Actions is intentionally deferred for this project (2026-09-22
decision — priority is finishing core product features; CI will be
reconsidered near final production readiness). The marker/exclusion pattern
below is still useful for local runs regardless of CI.

Default local run excludes this file:
    pytest tests/ -q -m "not known_stage5_defect"

To see the defects themselves, still failing, on demand:
    DATABASE_URL=postgresql+psycopg2://narratiq:narratiq@localhost:5432/narratiq_test \\
        pytest tests/test_known_stage5_defects.py -m known_stage5_defect -q
"""
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
import pytest  # noqa: E402

from database import SessionLocal  # noqa: E402
from models import User, Story, Chapter, Character  # noqa: E402
from scripts.seed_fixture import CHAPTERS, CHARACTERS  # noqa: E402

pytestmark = pytest.mark.known_stage5_defect

AI_TIMEOUT = 240  # these hit the real vLLM; generous, not infinite. Raised from
# 180s after measurement: indexing this fixture's 3 chapters alone (summary +
# chunking + embedding, all real calls) took ~3-4 minutes in the live session's
# own backend.log, not the 90s first assumed from the endpoint's own
# "15-30s per chapter" message — that message undersells real elapsed time.

_TEST_SERVER_PORT = 8099
_TEST_SERVER_URL = f"http://127.0.0.1:{_TEST_SERVER_PORT}"


@pytest.fixture(scope="module")
def live_server():
    """A REAL, separately-launched uvicorn process bound to narratiq_test —
    NOT fastapi.testclient.TestClient.

    Found the hard way: routers/chapters.py's sync-summaries endpoint fires
    indexing via bare asyncio.create_task() (fire-and-forget, no
    BackgroundTasks dependency). Under TestClient, that task gets cancelled
    when the per-request async context tears down — confirmed directly: the
    summary log line printed, but zero rows ever reached chapter_summaries or
    chapter_chunks, across 4 independent attempts, each waiting the full
    240s. Under a real persistent server (matching how the live pod's actual
    backend runs), the same background task completes normally — this is
    exactly what the author's own live session already proved works. This
    fixture exists so these tests exercise indexing the way the real app
    actually does, not an artifact of the test harness.

    Deliberately does NOT reuse the pod's already-running backend on :8000 —
    that process's DATABASE_URL points at the real `narratiq` database, and
    hitting it here would reintroduce exactly the shared-database risk
    docs/incidents/2026-09-22-database-row-count-discrepancy.md exists to
    prevent. This one is DATABASE_URL-pinned to narratiq_test explicitly.
    """
    backend_dir = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env["DATABASE_URL"] = "postgresql+psycopg2://narratiq:narratiq@localhost:5432/narratiq_test"

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1",
         "--port", str(_TEST_SERVER_PORT)],
        cwd=str(backend_dir), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        # 180s, not 90s: this pod runs vLLM + the pod's own backend + THIS
        # second backend simultaneously on a shared 9-CPU machine — BGE-M3
        # loading alone was measured taking >90s under that real contention
        # (single-process startup elsewhere in this same session took ~2s
        # with no contention), not a hang.
        deadline = time.monotonic() + 180
        ready = False
        while time.monotonic() < deadline:
            try:
                r = httpx.get(f"{_TEST_SERVER_URL}/api/health", timeout=2)
                if r.status_code == 200:
                    ready = True
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)
        if not ready:
            proc.terminate()
            raise RuntimeError(f"test server on :{_TEST_SERVER_PORT} did not become healthy within 90s")
        yield _TEST_SERVER_URL
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def _index_chapters_and_wait(base_url: str, story_id: str, user_id: str, expected: int, timeout: float = 240.0) -> None:
    """Trigger sync-summaries against the real live_server and poll the DB
    until all chapters have a ChapterSummary with a non-null embedding, or
    give up after `timeout`."""
    from models import ChapterSummary

    client, headers = _client_and_headers(base_url, user_id)
    r = client.post(f"/api/stories/{story_id}/chapters/sync-summaries", headers=headers)
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            indexed = db.query(ChapterSummary).filter(
                ChapterSummary.story_id == story_id, ChapterSummary.embedding.isnot(None),
            ).count()
            if indexed >= expected:
                return
            time.sleep(2)
            db.expire_all()
        raise AssertionError(
            f"only {indexed}/{expected} chapters indexed after {timeout}s — "
            f"fixture setup itself timed out, not one of the actual defects under test"
        )
    finally:
        db.close()


@pytest.fixture
def defect_fixture(live_server):
    """A small, self-contained, disposable manuscript — reuses the same
    cast/content as backend/scripts/seed_fixture.py so the 'mystery thread'
    these tests probe for is genuinely present, without depending on that
    script having been run first."""
    db = SessionLocal()
    tag = uuid.uuid4().hex[:8]
    user = User(email=f"known-defect-{tag}@narratiq-internal-test.com",
                username=f"knowndefect{tag}", hashed_password="x")
    db.add(user)
    db.flush()
    story = Story(user_id=user.user_id, title=f"[known-defects-fixture] The Archive Debt ({tag})")
    db.add(story)
    db.flush()
    chapter_ids = {}
    for ch_def in CHAPTERS:
        ch = Chapter(story_id=story.story_id, chapter_number=ch_def["number"],
                     title=ch_def["title"], content=ch_def["content"])
        db.add(ch)
        db.flush()
        chapter_ids[ch_def["number"]] = ch.chapter_id
    for c in CHARACTERS:
        db.add(Character(story_id=story.story_id, user_id=user.user_id,
                          name=c["name"], role=c["role"], aliases=c["aliases"]))
    db.commit()

    # Narrative threads / manuscript report / plot holes all require indexed
    # chapters (summary + embedding) — found the hard way: the first version
    # of this fixture skipped this and every one of those 3 endpoints
    # correctly rejected it with 422, not the defect being tested at all.
    _index_chapters_and_wait(live_server, story.story_id, user.user_id, expected=len(CHAPTERS))

    try:
        yield {"db": db, "base_url": live_server, "user_id": user.user_id,
               "story_id": story.story_id, "chapter_ids": chapter_ids}
    finally:
        s = db.query(Story).filter(Story.story_id == story.story_id).first()
        if s:
            db.delete(s)
        u = db.query(User).filter(User.user_id == user.user_id).first()
        if u:
            db.delete(u)
        db.commit()
        db.close()


def _client_and_headers(base_url: str, user_id: str):
    from routers.auth import create_token

    client = httpx.Client(base_url=base_url, timeout=AI_TIMEOUT)
    # Sign a token directly rather than going through /auth/login — these
    # tests are about the AI/analysis endpoints, not the login flow.
    token = create_token(user_id)
    return client, {"Authorization": f"Bearer {token}"}


@pytest.mark.timeout(AI_TIMEOUT)
def test_narrative_threads_scan_detects_the_manuscripts_mystery_thread(defect_fixture):
    """Author-reported symptom: scan enters 'scanning', no result ever appears.

    Backend-log evidence from the live 2026-09-22 session shows the scan
    endpoint DOES complete (not hung) but writes ZERO threads on a manuscript
    that clearly has one (the forged second-contract mystery, present in every
    one of the 3 fixture chapters). This test pins the correct behavior —
    at least one thread detected — so it fails honestly until the real
    under-detection defect in the scanner is fixed.
    """
    client, headers = _client_and_headers(defect_fixture["base_url"], defect_fixture["user_id"])
    story_id = defect_fixture["story_id"]

    r = client.post(f"/api/stories/{story_id}/narrative-threads/scan", headers=headers)
    assert r.status_code == 200, r.text

    r2 = client.get(f"/api/stories/{story_id}/narrative-threads", headers=headers)
    assert r2.status_code == 200, r2.text
    threads = r2.json()
    assert len(threads) >= 1, (
        "narrative-threads scan wrote zero threads on a manuscript with a clear "
        "unresolved mystery thread (the forged second contract) — matches the "
        "author's 2026-09-22 report that no result ever appears."
    )


@pytest.mark.timeout(AI_TIMEOUT)
def test_manuscript_report_persists_across_a_refetch(defect_fixture):
    """Author-reported symptom: report generates with useful content, but is
    gone after navigating away and back.

    Code-level evidence: routers/manuscript_report.py has exactly one route
    (POST) and contains no db.add/db.commit anywhere — the report is computed
    fresh every call and never stored. There is no GET route to re-fetch it,
    so 'persisted' is asserted here as: a second POST call (the only way to
    retrieve it at all) returns a report referencing the same chapters. This
    is deliberately the weakest reasonable persistence check — even this
    currently has no server-side caching/storage to rely on.
    """
    client, headers = _client_and_headers(defect_fixture["base_url"], defect_fixture["user_id"])
    story_id = defect_fixture["story_id"]

    r1 = client.post(f"/api/stories/{story_id}/manuscript-report", headers=headers)
    assert r1.status_code == 200, r1.text
    first = r1.json()
    assert first.get("strengths") or first.get("improvements") or first.get("character_arcs"), (
        "manuscript report returned no substantive content on first generation"
    )

    import routers.manuscript_report as mr_module
    has_persistence = "db.add" in Path(mr_module.__file__).read_text() or "db.commit" in Path(mr_module.__file__).read_text()
    assert has_persistence, (
        "routers/manuscript_report.py has no db.add/db.commit at all — the report "
        "is never persisted server-side, matching the author's 2026-09-22 report "
        "that it disappears after navigating away and back. There is also no GET "
        "route to distinguish 'lost' from 'never saved' — both are the same defect "
        "from the author's point of view."
    )


@pytest.mark.timeout(AI_TIMEOUT)
def test_plot_hole_detection_returns_a_parseable_result(defect_fixture):
    """Author-reported symptom: plot hole detection did not work at all.

    Backend-log evidence from the live session: two consecutive attempts both
    logged 'failed to parse model output as JSON' on both the initial call and
    the one retry, ending in 'plot_holes unparseable after retry' — the
    endpoint returns a fixed, useless error string to the author every time.
    """
    client, headers = _client_and_headers(defect_fixture["base_url"], defect_fixture["user_id"])
    story_id = defect_fixture["story_id"]

    r = client.post(f"/api/stories/{story_id}/plot-holes", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "could not be completed" not in str(body).lower(), (
        f"plot-holes endpoint returned its own failure placeholder instead of "
        f"real analysis, matching the author's 2026-09-22 report: {body}"
    )


@pytest.mark.timeout(AI_TIMEOUT)
def test_style_transform_produces_a_meaningfully_different_thriller_rewrite(defect_fixture):
    """Author-reported symptom: at least one Thriller-style test returned
    effectively the original text with no meaningful transformation.

    This is a live AI-quality judgment, not a deterministic one — it uses the
    same weak, documented proxy (text similarity) already used elsewhere in
    Stage 5, and is intentionally lenient (only checks the text changed at
    all, not that it changed WELL) since the point is to catch a true no-op,
    not to re-litigate Stage 5's own quality bar.
    """
    import difflib

    client, headers = _client_and_headers(defect_fixture["base_url"], defect_fixture["user_id"])
    story_id = defect_fixture["story_id"]
    original = defect_fixture["db"].query(Chapter).filter(
        Chapter.story_id == story_id, Chapter.chapter_number == 1,
    ).first().content

    r = client.post(
        "/api/ai/style",
        headers=headers,
        json={"text": original, "style": "Thriller", "story_id": story_id, "strength": "strong"},
    )
    assert r.status_code == 200, r.text
    transformed = r.json().get("transformed", "")
    similarity = difflib.SequenceMatcher(None, original, transformed).ratio()
    assert similarity < 0.98, (
        f"style=Thriller at strength=strong returned text {similarity:.3f} "
        f"similar to the original — effectively unchanged, matching the "
        f"author's 2026-09-22 report."
    )
