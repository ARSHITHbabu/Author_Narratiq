import logging
import uuid
import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Request
from sqlalchemy import func
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
                detail="This file could not be read as a Word document. "
                       "Nothing was imported. Save it again as .docx or .txt and retry.",
            )
        if not text.strip():
            raise HTTPException(
                status_code=422,
                detail="The DOCX file contains no readable text paragraphs. Please check the file.",
            )
    else:
        text = content.decode("utf-8", errors="ignore")
    if not text.strip():
        raise HTTPException(
            status_code=422,
            detail="This file contains no text. Nothing was imported.",
        )
    raw_chapters = _segment_chapters(text)

    # Stage 12 remediation A8: one import at a time per story. Two concurrent
    # imports would interleave their chapter numbers.
    running = db.query(ManuscriptJob).filter(
        ManuscriptJob.story_id == story_id,
        ManuscriptJob.status.in_(("pending", "processing")),
    ).first()
    if running:
        raise HTTPException(
            status_code=409,
            detail="A manuscript import is already running for this story. "
                   "Wait for it to finish, then try again.",
        )

    # Save every chapter's text BEFORE answering, in one transaction, numbered
    # after the story's existing chapters (previously each chapter was created
    # later, in the background, numbered from 1 — an import into a story that
    # already had chapters produced duplicate chapter numbers, and a failure
    # half-way left an unreported partial import). Either all chapters are
    # saved or none are; only AI indexing happens in the background.
    base = db.query(func.max(Chapter.chapter_number)).filter(
        Chapter.story_id == story_id
    ).scalar() or 0
    created: list[tuple[str, int, str]] = []   # (chapter_id, number, html)
    try:
        for i, ch in enumerate(raw_chapters):
            number = base + i + 1
            html = _text_to_html(ch["content"], title=ch["title"])
            chapter = Chapter(
                story_id       = story_id,
                chapter_number = number,
                title          = ch["title"] or f"Chapter {number}",
                content        = html,
                word_count     = len(ch["content"].split()),
            )
            db.add(chapter)
            db.flush()
            created.append((chapter.chapter_id, number, html))
        story.word_count = (story.word_count or 0) + sum(
            len(ch["content"].split()) for ch in raw_chapters
        )
        story.updated_at = datetime.utcnow()

        job = ManuscriptJob(
            job_id=str(uuid.uuid4()),
            story_id=story_id,
            user_id=current_user.user_id,
            status="processing",
            stage="Preparing chapters for AI tools",
            percent=10,
            message="",
            chapter_count=len(raw_chapters),
        )
        db.add(job)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("[manuscript] saving imported chapters failed: story=%s: %s",
                     story_id[:8], type(exc).__name__)
        raise HTTPException(
            status_code=500,
            detail="Your manuscript could not be saved. Nothing was imported — "
                   "your existing chapters are unchanged. Please try again.",
        )

    logger.info(
        "[manuscript] upload saved: job=%s, story=%s, chapters=%d (numbered %d-%d), size=%.1f MB",
        job.job_id[:8], story_id[:8], len(created), base + 1, base + len(created), actual_mb,
    )
    asyncio.create_task(_index_pipeline(job.job_id, story_id, created))

    return ManuscriptUploadResponse(
        job_id=job.job_id,
        story_id=story_id,
        chapter_count=len(created),
        estimated_minutes=max(1, len(created) // 5),
        status="processing",
    )


def _text_to_html(text: str, title: str = "") -> str:
    """Plain manuscript text -> the editor's HTML (one <p> per paragraph).

    Paragraphs are separated by blank lines when the file has any (single
    newlines inside them are hard wraps and become spaces); otherwise every
    line is a paragraph, which is how DOCX paragraphs arrive. A first line that
    is the chapter's title stays its own paragraph. No text is ever dropped."""
    import html
    import re

    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    head = ""
    first, _, rest = text.partition("\n")
    if title and first.strip() == title and rest.strip():
        head, text = f"<p>{html.escape(first.strip(), quote=False)}</p>", rest.strip()
    if re.search(r"\n\s*\n", text):
        paras = [re.sub(r"\s*\n\s*", " ", p).strip() for p in re.split(r"\n\s*\n", text)]
    else:
        paras = [p.strip() for p in text.split("\n")]
    return head + "".join(f"<p>{html.escape(p, quote=False)}</p>" for p in paras if p)


def _segment_chapters(text: str) -> list[dict]:
    import re
    # Leading "\n" so a heading on the file's very first line is recognised
    # like every later one (previously "Chapter 1: …" stayed inside chapter 1).
    parts = re.split(r"\n(?:Chapter\s+\d+[:\.\s]|CHAPTER\s+\d+)", "\n" + text, flags=re.IGNORECASE)
    chapters = []
    for i, part in enumerate(parts):
        if part.strip():
            title_match = re.match(r"^(.{0,60})\n", part.strip())
            title = title_match.group(1).strip() if title_match else ""
            chapters.append({"title": title, "content": part.strip()})
    return chapters if chapters else [{"title": "", "content": text}]


async def _index_pipeline(job_id: str, story_id: str, created: list) -> None:
    """Background AI indexing (summary + embeddings) of chapters that are
    already saved. A failure here never loses text: the job ends "partial",
    says how many chapters are ready for AI tools, and the rest are indexed
    the next time the author saves them."""
    from database import SessionLocal
    local_db = SessionLocal()
    total = len(created)
    done = 0
    try:
        for chapter_id, number, html in created:
            _update_job(local_db, job_id, {
                "status":  "processing",
                "stage":   f"Preparing chapter {done + 1} of {total} for AI tools",
                "percent": int(10 + (done / total) * 85),
                "message": "",
            })
            async with bg_ai_semaphore():
                await summarize_and_embed_chapter(chapter_id, story_id, number, html, local_db)
            done += 1
            await asyncio.sleep(0.05)

        _update_job(local_db, job_id, {
            "status":  "complete",
            "stage":   "Story imported and ready",
            "percent": 100,
            "message": f"{total} chapter{'s' if total != 1 else ''} imported.",
        })
        logger.info("[manuscript] indexing complete: job=%s, %d chapters", job_id[:8], total)
    except Exception as exc:
        local_db.rollback()
        reason = ("the AI service was temporarily unavailable"
                  if isinstance(exc, AIServiceUnavailableError) else "of an unexpected problem")
        logger.warning("[manuscript] indexing stopped: job=%s at %d/%d: %s",
                       job_id[:8], done, total, type(exc).__name__)
        _update_job(local_db, job_id, {
            "status":  "partial",
            "stage":   "Imported — AI preparation incomplete",
            "percent": 100,
            "message": (
                f"All {total} chapters were imported and saved. AI tools could not finish "
                f"preparing {total - done} of them because {reason}; those chapters are "
                f"prepared again the next time you save them."
            ),
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
