"""
Orphan job recovery for NarratIQ AI.

Called during lifespan() startup BEFORE the app starts accepting requests.
On pod restart, uvicorn restart, or OOM kill, all asyncio background tasks
die instantly. The DB records remain stuck in processing/pending/running states
indefinitely. This sweep finds them and marks them as failed so authors can retry.

What is swept:
  AudioUpload:   status='processing'           → status='failed'
  ManuscriptJob: status='processing'           → status='error'
  StoryIntelJob: status in ('pending','running') → status='error'
  StoryBible:    status='running'              → status='failed'

What is NOT done:
  - No content is deleted
  - No retries are attempted (that belongs in Celery — Phase B)
  - narrative_thread scans have no persistent job record — authors re-trigger via UI
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)

_ORPHAN_MESSAGE = "Job interrupted by server restart — please retry"


async def recover_orphaned_jobs() -> dict[str, int]:
    """
    Sweep all stuck job records and mark them failed.
    Returns a dict of {table: count_recovered} for logging.
    Designed to be called once at startup; safe to call again (idempotent).
    """
    from database import SessionLocal
    from models import AudioUpload, ManuscriptJob, StoryIntelJob, VoiceSession, VoiceWorkflow, StoryBible

    db = SessionLocal()
    counts: dict[str, int] = {}
    now = datetime.utcnow()

    try:
        # ── AudioUpload ───────────────────────────────────────────────────────
        stuck_audio = (
            db.query(AudioUpload)
            .filter(AudioUpload.status == "processing")
            .all()
        )
        for upload in stuck_audio:
            upload.status     = "failed"
            upload.updated_at = now
        counts["audio_uploads"] = len(stuck_audio)

        # ── ManuscriptJob ─────────────────────────────────────────────────────
        stuck_manuscript = (
            db.query(ManuscriptJob)
            .filter(ManuscriptJob.status == "processing")
            .all()
        )
        for job in stuck_manuscript:
            job.status     = "error"
            job.message    = _ORPHAN_MESSAGE
            job.updated_at = now
        counts["manuscript_jobs"] = len(stuck_manuscript)

        # ── StoryIntelJob ─────────────────────────────────────────────────────
        stuck_intel = (
            db.query(StoryIntelJob)
            .filter(StoryIntelJob.status.in_(["pending", "running"]))
            .all()
        )
        for job in stuck_intel:
            job.status     = "error"
            job.error_message = _ORPHAN_MESSAGE
            job.updated_at = now
        counts["story_intel_jobs"] = len(stuck_intel)

        # ── StoryBible (running → failed) ─────────────────────────────────────
        stuck_bibles = (
            db.query(StoryBible)
            .filter(StoryBible.status == "running")
            .all()
        )
        for bible in stuck_bibles:
            bible.status     = "failed"
            bible.updated_at = now
        counts["story_bibles"] = len(stuck_bibles)

        # ── VoiceSession (active → failed) ────────────────────────────────────
        stuck_sessions = (
            db.query(VoiceSession)
            .filter(VoiceSession.status == "active")
            .all()
        )
        for sess in stuck_sessions:
            sess.status        = "failed"
            sess.ended_at      = now
            sess.error_message = _ORPHAN_MESSAGE
        counts["voice_sessions"] = len(stuck_sessions)

        # ── VoiceWorkflow (running / executing / awaiting_confirmation → abandoned) ──
        stuck_workflows = (
            db.query(VoiceWorkflow)
            .filter(VoiceWorkflow.status.in_(["running", "executing", "awaiting_confirmation"]))
            .all()
        )
        for wf in stuck_workflows:
            wf.status     = "abandoned"
            wf.updated_at = now
        counts["voice_workflows"] = len(stuck_workflows)

        # ── VoiceTask (executing → failed) ────────────────────────────────────
        # A client-side step whose browser never reported back. It must not
        # survive a restart still claiming to be in progress, and it must never
        # be resolved as success on the author's behalf (task 3.7).
        from models import VoiceTask
        from services.voice import lifecycle

        stuck_tasks = (
            db.query(VoiceTask)
            .filter(VoiceTask.status == lifecycle.EXECUTING)
            .all()
        )
        for task in stuck_tasks:
            lifecycle.transition(task, lifecycle.FAILED, source="orphan_recovery",
                                 reason="server restarted before the step reported", strict=False)
            task.result_summary = lifecycle.TIMEOUT_REASON
        counts["voice_tasks"] = len(stuck_tasks)

        if any(v > 0 for v in counts.values()):
            db.commit()

        total = sum(counts.values())
        if total > 0:
            logger.warning(
                "[startup] Orphan recovery: %d stuck jobs found and marked failed — %s",
                total,
                ", ".join(f"{v} {k}" for k, v in counts.items() if v > 0),
            )
        else:
            logger.info("[startup] Orphan recovery: no stuck jobs found")

    except Exception as exc:
        logger.error("[startup] Orphan recovery failed: %s", exc)
        db.rollback()
    finally:
        db.close()

    return counts
