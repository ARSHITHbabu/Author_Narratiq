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

What is NOT done:
  - No content is deleted
  - No retries are attempted (that belongs in Celery — Phase B)
  - story_bibles._generating is an in-memory set; it is empty on fresh process start,
    so no sweep needed — the guard resets automatically
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
    from models import AudioUpload, ManuscriptJob, StoryIntelJob

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
            job.error      = _ORPHAN_MESSAGE
            job.updated_at = now
        counts["story_intel_jobs"] = len(stuck_intel)

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
