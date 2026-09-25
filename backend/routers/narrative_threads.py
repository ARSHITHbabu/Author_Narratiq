"""
Phase 2 — P2-07 Dead-End Narrative Thread Tracker
Scans chapter summaries via Qwen, clusters thread names via BGE-M3,
stores results in narrative_threads table.
"""
import asyncio
import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from exceptions import AIServiceUnavailableError
from middleware.rate_limit import limiter, get_user_id
from middleware.concurrency import bg_ai_semaphore
from models import Story, Chapter, ChapterSummary, NarrativeThread, NarrativeThreadScan
from schemas import NarrativeThreadOut, NarrativeThreadUpdate, NarrativeScanResponse, NarrativeScanStatus
from routers.auth import get_current_user, User
from services.ai_service import (
    extract_narrative_threads_from_summaries,
    embed_text,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["narrative-threads"])

# Stop-list for generic/vague thread names
_THREAD_STOP_LIST = frozenset({
    "the story", "the journey", "the conflict", "the quest",
    "the adventure", "the plot", "the narrative", "the events",
    "character development", "the mystery",
})

# Minimum cosine similarity to cluster two thread names as identical
_CLUSTER_THRESHOLD = 0.85

# Strong references to running scan tasks. asyncio keeps only a weak reference
# to a task, so a bare create_task() can be garbage-collected mid-scan.
_scan_tasks: set = set()

_ACTIVE_SCAN_STATUSES = ("pending", "running")


def _keep_thread_name(name: str) -> bool:
    """At least two words and not a generic stop-listed name."""
    cleaned = name.strip()
    return len(cleaned.split()) >= 2 and cleaned.lower() not in _THREAD_STOP_LIST


def _get_owned_story(story_id: str, user_id: str, db: Session) -> Story:
    story = db.query(Story).filter(
        Story.story_id == story_id,
        Story.user_id  == user_id,
    ).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return story


async def _cluster_thread_names(raw_names: list[str]) -> dict[str, str]:
    """
    Embed all thread names with BGE-M3 and cluster those with cosine > 0.85
    to a canonical representative. Returns {name → canonical_name}.
    """
    import numpy as np

    if len(raw_names) < 2:
        return {n: n for n in raw_names}

    embeddings = []
    for name in raw_names:
        emb = await embed_text(name)
        embeddings.append(np.array(emb, dtype=np.float32))

    canonical_map: dict[str, str] = {}
    assigned: set[int] = set()

    for i in range(len(raw_names)):
        if i in assigned:
            continue
        canonical = raw_names[i]
        canonical_map[raw_names[i]] = canonical
        assigned.add(i)
        for j in range(i + 1, len(raw_names)):
            if j in assigned:
                continue
            ni = np.linalg.norm(embeddings[i])
            nj = np.linalg.norm(embeddings[j])
            if ni < 1e-9 or nj < 1e-9:
                continue
            sim = float(np.dot(embeddings[i], embeddings[j]) / (ni * nj))
            if sim >= _CLUSTER_THRESHOLD:
                canonical_map[raw_names[j]] = canonical
                assigned.add(j)

    for name in raw_names:
        if name not in canonical_map:
            canonical_map[name] = name

    return canonical_map


async def _run_scan_pipeline(story_id: str, user_id: str, stats: Optional[dict] = None) -> int:
    """
    Full thread scan: extract → cluster → compute lifecycle → upsert DB.
    Returns the count of threads written. If ``stats`` is given it also gets
    "chapters_scanned" and the extraction counters (batches_degraded, …).
    """
    stats = stats if stats is not None else {}
    from database import SessionLocal

    db = SessionLocal()
    try:
        summaries = (
            db.query(ChapterSummary, Chapter.title)
            .join(Chapter, ChapterSummary.chapter_id == Chapter.chapter_id)
            .filter(ChapterSummary.story_id == story_id)
            .order_by(ChapterSummary.chapter_number)
            .all()
        )

        if not summaries:
            return 0

        total_chapters = max(s.chapter_number for s, _ in summaries)
        stats["chapters_scanned"] = len(summaries)

        summary_dicts = [
            {
                "chapter_number":    s.chapter_number,
                "title":             t or f"Chapter {s.chapter_number}",
                "key_events":        s.key_events,
                "characters_present": s.characters_present,
                "raw_summary":       s.raw_summary or "",
            }
            for s, t in summaries
        ]

        raw_thread_events = await extract_narrative_threads_from_summaries(summary_dicts, stats=stats)

        # Filter stop-list and one-word names. (Was >= 3 words, which also
        # dropped legitimate specific names like "Forged contract".)
        raw_thread_events = [
            e for e in raw_thread_events
            if _keep_thread_name(e["thread_name"])
        ]

        if not raw_thread_events:
            return 0

        # Collect unique names for clustering
        unique_names = list({e["thread_name"] for e in raw_thread_events})
        cluster_map = await _cluster_thread_names(unique_names)

        # Build thread lifecycle: canonical_name → {introduced, last_seen, resolved, descriptions}
        thread_lifecycle: dict[str, dict] = {}
        for event in raw_thread_events:
            canonical = cluster_map.get(event["thread_name"], event["thread_name"])
            ch_num = int(event.get("chapter_number", 0))
            action = event.get("action", "introduced")
            desc   = event.get("description", "")

            if canonical not in thread_lifecycle:
                thread_lifecycle[canonical] = {
                    "introduced":   ch_num,
                    "last_seen":    ch_num,
                    "resolved":     None,
                    "descriptions": [],
                }
            lc = thread_lifecycle[canonical]
            lc["last_seen"] = max(lc["last_seen"], ch_num)
            if lc["introduced"] > ch_num:
                lc["introduced"] = ch_num
            if action == "resolved":
                lc["resolved"] = ch_num
            if desc:
                lc["descriptions"].append(desc)

        # Dead-end threshold: N = max(3, 15% of total chapters)
        dead_end_threshold = max(3, int(total_chapters * 0.15))

        # Upsert threads
        written = 0
        for canonical_name, lc in thread_lifecycle.items():
            # Determine status
            if lc["resolved"] is not None:
                status = "resolved"
            elif (total_chapters - lc["last_seen"]) >= dead_end_threshold:
                status = "dead_end"
            else:
                status = "open"

            # Merge description
            description = " | ".join(dict.fromkeys(lc["descriptions"]))[:500]

            existing = (
                db.query(NarrativeThread)
                .filter(
                    NarrativeThread.story_id == story_id,
                    NarrativeThread.name     == canonical_name,
                )
                .first()
            )
            if existing:
                # Only update status/lifecycle if not manually set to resolved
                if existing.status != "resolved":
                    existing.status             = status
                    existing.last_seen_chapter  = lc["last_seen"]
                    existing.resolved_chapter   = lc["resolved"]
                existing.description = description or existing.description
                existing.updated_at  = datetime.utcnow()
            else:
                thread = NarrativeThread(
                    story_id=story_id,
                    user_id=user_id,
                    name=canonical_name,
                    description=description,
                    introduced_chapter=lc["introduced"],
                    last_seen_chapter=lc["last_seen"],
                    resolved_chapter=lc["resolved"],
                    status=status,
                )
                db.add(thread)
            written += 1

        db.commit()
        return written
    finally:
        db.close()


def _scan_outcome(threads_written: int, stats: dict) -> str:
    """completed | completed_empty | failed. Zero threads only counts as a real
    "nothing found" if at least one batch was actually read: when every batch
    was unreadable, saying "no threads" would be the silent-fallback lie."""
    if threads_written:
        return "completed"
    batches = int(stats.get("batches", 0))
    if batches and int(stats.get("batches_failed", 0)) >= batches:
        return "failed"
    return "completed_empty"


def _scan_status_out(scan: Optional[NarrativeThreadScan]) -> NarrativeScanStatus:
    if scan is None:
        return NarrativeScanStatus(status="none")
    return NarrativeScanStatus(
        scan_id=scan.scan_id, status=scan.status,
        threads_written=scan.threads_written or 0, chapters_scanned=scan.chapters_scanned or 0,
        batches_degraded=scan.batches_degraded or 0, error_code=scan.error_code,
        started_at=scan.started_at, finished_at=scan.finished_at,
    )


def _finish_scan(scan_id: str, *, status: str, threads: int = 0, stats: Optional[dict] = None,
                 error_code: Optional[str] = None) -> None:
    """Record a scan's outcome on its own short-lived session."""
    from database import SessionLocal

    db = SessionLocal()
    try:
        scan = db.query(NarrativeThreadScan).filter(NarrativeThreadScan.scan_id == scan_id).first()
        if scan is None:          # story deleted mid-scan (row cascaded away)
            return
        stats = stats or {}
        scan.status           = status
        scan.threads_written  = threads
        scan.chapters_scanned = int(stats.get("chapters_scanned", scan.chapters_scanned or 0))
        scan.batches_degraded = int(stats.get("batches_degraded", 0)) + int(stats.get("batches_failed", 0))
        scan.error_code       = error_code
        scan.finished_at      = datetime.utcnow()
        db.commit()
    finally:
        db.close()


def _mark_scan_running(scan_id: str) -> None:
    from database import SessionLocal

    db = SessionLocal()
    try:
        scan = db.query(NarrativeThreadScan).filter(NarrativeThreadScan.scan_id == scan_id).first()
        if scan is not None:
            scan.status = "running"
            db.commit()
    finally:
        db.close()


def _claim_scan(story_id: str, user_id: str, db: Session) -> tuple[NarrativeThreadScan, bool]:
    """Return (scan, started_new). One scan per story at a time: if the story's
    scan row is pending/running, it is returned unchanged and nothing new starts.
    The row is one-per-story (UNIQUE story_id); a new scan reuses it. Locking the
    row (FOR UPDATE) serialises two simultaneous requests; a first-ever insert
    race is caught by the unique constraint."""
    from sqlalchemy.exc import IntegrityError

    scan = (db.query(NarrativeThreadScan)
              .filter(NarrativeThreadScan.story_id == story_id)
              .with_for_update().first())
    if scan is not None and scan.status in _ACTIVE_SCAN_STATUSES:
        db.commit()   # release the row lock
        return scan, False
    now = datetime.utcnow()
    if scan is None:
        scan = NarrativeThreadScan(story_id=story_id, user_id=user_id)
        db.add(scan)
    scan.scan_id          = str(uuid.uuid4())
    scan.user_id          = user_id
    scan.status           = "pending"
    scan.threads_written  = 0
    scan.chapters_scanned = 0
    scan.batches_degraded = 0
    scan.error_code       = None
    scan.started_at       = now
    scan.finished_at      = None
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(NarrativeThreadScan).filter(NarrativeThreadScan.story_id == story_id).first()
        return existing, False
    db.refresh(scan)
    return scan, True


@router.post("/{story_id}/narrative-threads/scan", response_model=NarrativeScanResponse)
@limiter.limit(settings.rate_limit_background_ai, key_func=get_user_id)
async def scan_narrative_threads(
    request: Request,
    story_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Scan all chapter summaries with Qwen to extract and track narrative threads.
    Thread names are deduplicated via BGE-M3 cosine clustering.
    Dead-end threads are flagged automatically. Results are upserted — safe to re-run.

    Returns immediately; the scan runs in the background. Poll
    GET /{story_id}/narrative-threads/scan-status for the outcome. If a scan is
    already pending or running for this story, that scan's id is returned
    (HTTP 200, same job_id) and no second scan is started.
    """
    _get_owned_story(story_id, current_user.user_id, db)

    summaries = (
        db.query(ChapterSummary)
        .filter(ChapterSummary.story_id == story_id)
        .count()
    )
    if summaries == 0:
        raise HTTPException(
            status_code=422,
            detail="No indexed chapters found. Index at least one chapter first.",
        )

    scan, started_new = _claim_scan(story_id, current_user.user_id, db)
    if not started_new:
        return NarrativeScanResponse(job_id=scan.scan_id, status=scan.status)

    scan_id = scan.scan_id
    user_id = current_user.user_id

    async def _bg():
        stats: dict = {}
        try:
            async with bg_ai_semaphore():
                _mark_scan_running(scan_id)
                count = await _run_scan_pipeline(story_id, user_id, stats=stats)
            _finish_scan(scan_id, status=_scan_outcome(count, stats), threads=count, stats=stats,
                         error_code="unreadable" if _scan_outcome(count, stats) == "failed" else None)
            logger.info("[narrative_threads] scan complete for %s: %d thread(s) written", story_id[:8], count)
        except AIServiceUnavailableError as exc:
            logger.warning("[narrative_threads] AI unavailable for %s: %s", story_id[:8], exc)
            _finish_scan(scan_id, status="failed", stats=stats, error_code="ai_unavailable")
        except Exception as exc:
            logger.error("[narrative_threads] scan failed for %s: %s", story_id[:8], type(exc).__name__)
            _finish_scan(scan_id, status="failed", stats=stats, error_code="scan_error")

    task = asyncio.create_task(_bg())
    _scan_tasks.add(task)
    task.add_done_callback(_scan_tasks.discard)

    return NarrativeScanResponse(job_id=scan_id, status="pending")


@router.get("/{story_id}/narrative-threads/scan-status", response_model=NarrativeScanStatus)
def get_scan_status(
    story_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Latest thread scan for this story: none | pending | running | completed |
    completed_empty | failed. Lets the UI show an honest outcome, and resume
    waiting after the author navigates away and back."""
    _get_owned_story(story_id, current_user.user_id, db)
    scan = db.query(NarrativeThreadScan).filter(NarrativeThreadScan.story_id == story_id).first()
    return _scan_status_out(scan)


@router.get("/{story_id}/narrative-threads", response_model=list[NarrativeThreadOut])
def list_narrative_threads(
    story_id: str,
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all narrative threads for a story, optionally filtered by status."""
    _get_owned_story(story_id, current_user.user_id, db)

    q = db.query(NarrativeThread).filter(NarrativeThread.story_id == story_id)
    if status:
        q = q.filter(NarrativeThread.status == status)

    return q.order_by(NarrativeThread.introduced_chapter.asc().nullsfirst()).all()


@router.patch("/{story_id}/narrative-threads/{thread_id}", response_model=NarrativeThreadOut)
def update_thread_status(
    story_id:  str,
    thread_id: str,
    body: NarrativeThreadUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Manually set a thread's status (resolved | open | dead_end).
    Authors use this to mark threads they have intentionally resolved.
    """
    _get_owned_story(story_id, current_user.user_id, db)

    valid_statuses = {"open", "resolved", "dead_end"}
    if body.status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"status must be one of: {', '.join(sorted(valid_statuses))}",
        )

    thread = db.query(NarrativeThread).filter(
        NarrativeThread.thread_id == thread_id,
        NarrativeThread.story_id  == story_id,
    ).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Narrative thread not found")

    thread.status     = body.status
    thread.updated_at = datetime.utcnow()
    if body.status == "resolved" and thread.resolved_chapter is None:
        # Record the current last known chapter as the resolution point
        thread.resolved_chapter = thread.last_seen_chapter

    db.commit()
    db.refresh(thread)
    return thread
