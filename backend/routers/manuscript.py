import logging
import uuid
import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Request
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from exceptions import AIServiceUnavailableError, UploadTooLargeError
from middleware.rate_limit import limiter, get_user_id
from middleware.upload_guard import enforce_upload_size
from middleware.concurrency import bg_ai_semaphore
from models import Story, Chapter, ManuscriptJob
from schemas import ManuscriptUploadResponse, JobStatus
from routers.auth import get_current_user, User
from services.ai_service import summarize_and_embed_chapter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["manuscript"])


@router.post("/upload/{story_id}", response_model=ManuscriptUploadResponse)
@limiter.limit(settings.rate_limit_upload, key_func=get_user_id)
async def upload_manuscript(
    request: Request,
    story_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Pre-check Content-Length before reading body
    enforce_upload_size(request, limit_mb=settings.max_manuscript_upload_mb)

    story = db.query(Story).filter(
        Story.story_id == story_id,
        Story.user_id == current_user.user_id,
    ).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    allowed = {
        "text/plain",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    if file.content_type not in allowed:
        raise HTTPException(status_code=400, detail="Only TXT and DOCX files are accepted")

    content = await file.read()

    # Byte-level size guard (defense-in-depth for clients without Content-Length)
    actual_mb = len(content) / (1024 * 1024)
    if actual_mb > settings.max_manuscript_upload_mb:
        raise UploadTooLargeError(limit_mb=settings.max_manuscript_upload_mb, actual_mb=actual_mb)

    _DOCX_CT = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if file.content_type == _DOCX_CT:
        try:
            import io
            from docx import Document as DocxDocument
            doc = DocxDocument(io.BytesIO(content))
            text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except Exception as exc:
            logger.warning("[manuscript] DOCX extraction failed: %s", exc)
            raise HTTPException(
                status_code=422,
                detail=f"Failed to read DOCX file. Ensure the file is a valid Word document. ({exc})",
            )
        if not text.strip():
            raise HTTPException(
                status_code=422,
                detail="The DOCX file contains no readable text paragraphs. Please check the file.",
            )
    else:
        text = content.decode("utf-8", errors="ignore")
    raw_chapters = _segment_chapters(text)

    job = ManuscriptJob(
        job_id=str(uuid.uuid4()),
        story_id=story_id,
        user_id=current_user.user_id,
        status="processing",
        stage="Parsing chapters",
        percent=10,
        message="",
        chapter_count=len(raw_chapters),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    logger.info(
        "[manuscript] upload accepted: job=%s, story=%s, chapters=%d, size=%.1f MB",
        job.job_id[:8], story_id[:8], len(raw_chapters), actual_mb,
    )
    asyncio.create_task(_ingest_pipeline(job.job_id, story_id, raw_chapters))

    return ManuscriptUploadResponse(
        job_id=job.job_id,
        story_id=story_id,
        chapter_count=len(raw_chapters),
        estimated_minutes=max(1, len(raw_chapters) // 5),
        status="processing",
    )


def _segment_chapters(text: str) -> list[dict]:
    import re
    parts = re.split(r"\n(?:Chapter\s+\d+[:\.\s]|CHAPTER\s+\d+)", text, flags=re.IGNORECASE)
    chapters = []
    for i, part in enumerate(parts):
        if part.strip():
            title_match = re.match(r"^(.{0,60})\n", part.strip())
            title = title_match.group(1).strip() if title_match else f"Chapter {i + 1}"
            chapters.append({"title": title or f"Chapter {i + 1}", "content": part.strip()})
    return chapters if chapters else [{"title": "Chapter 1", "content": text}]


async def _ingest_pipeline(job_id: str, story_id: str, raw_chapters: list) -> None:
    from database import SessionLocal
    local_db = SessionLocal()
    try:
        total = len(raw_chapters)
        for i, ch in enumerate(raw_chapters):
            _update_job(local_db, job_id, {
                "status":  "processing",
                "stage":   f"Indexing chapter {i + 1}/{total}",
                "percent": int(10 + (i / total) * 80),
                "message": ch["title"],
            })

            chapter = Chapter(
                story_id       = story_id,
                chapter_number = i + 1,
                title          = ch["title"],
                content        = ch["content"],
                word_count     = len(ch["content"].split()),
            )
            local_db.add(chapter)
            local_db.commit()
            local_db.refresh(chapter)

            async with bg_ai_semaphore():
                await summarize_and_embed_chapter(
                    chapter.chapter_id, story_id, i + 1, ch["content"], local_db
                )
            await asyncio.sleep(0.05)

        _update_job(local_db, job_id, {
            "status":  "complete",
            "stage":   "Story indexed and ready",
            "percent": 100,
            "message": "",
        })
        logger.info("[manuscript] ingest complete: job=%s, %d chapters", job_id[:8], total)
    except AIServiceUnavailableError as exc:
        logger.warning("[manuscript] AI unavailable during ingest: job=%s: %s", job_id[:8], exc)
        _update_job(local_db, job_id, {
            "status":  "error",
            "stage":   "Error",
            "percent": 0,
            "message": "AI temporarily unavailable — please retry",
        })
    except Exception as exc:
        logger.error("[manuscript] ingest failed: job=%s: %s", job_id[:8], exc)
        _update_job(local_db, job_id, {
            "status":  "error",
            "stage":   "Error",
            "percent": 0,
            "message": str(exc),
        })
    finally:
        local_db.close()


def _update_job(db: Session, job_id: str, data: dict) -> None:
    job = db.query(ManuscriptJob).filter(ManuscriptJob.job_id == job_id).first()
    if job is None:
        return
    for key, val in data.items():
        setattr(job, key, val)
    job.updated_at = datetime.utcnow()
    db.commit()


@router.get("/job/{job_id}", response_model=JobStatus)
def job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = db.query(ManuscriptJob).filter(
        ManuscriptJob.job_id == job_id,
        ManuscriptJob.user_id == current_user.user_id,
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatus(
        job_id=job.job_id,
        status=job.status,
        stage=job.stage,
        percent=job.percent,
        message=job.message or "",
    )
