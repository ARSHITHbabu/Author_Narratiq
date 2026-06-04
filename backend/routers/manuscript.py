import uuid
import asyncio
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Story, Chapter, ChapterSummary
from schemas import ManuscriptUploadResponse, JobStatus
from routers.auth import get_current_user, User
from services.ai_service import summarize_and_embed_chapter

router = APIRouter(tags=["manuscript"])

# In-memory job store (Redis in production)
_jobs: dict = {}


@router.post("/upload/{story_id}", response_model=ManuscriptUploadResponse)
async def upload_manuscript(
    story_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    story = db.query(Story).filter(Story.story_id == story_id, Story.user_id == current_user.user_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    allowed = {"text/plain", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    if file.content_type not in allowed:
        raise HTTPException(status_code=400, detail="Only TXT and DOCX files are accepted")

    content = await file.read()
    text = content.decode("utf-8", errors="ignore")

    # Simple chapter segmentation by "Chapter" headings or blank lines
    raw_chapters = _segment_chapters(text)
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "processing", "stage": "Parsing chapters", "percent": 10, "message": ""}

    # Process asynchronously (in production: RQ background job)
    asyncio.create_task(_ingest_pipeline(job_id, story_id, raw_chapters, db))

    return ManuscriptUploadResponse(
        job_id=job_id,
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


async def _ingest_pipeline(job_id: str, story_id: str, raw_chapters: list, db: Session):
    from database import SessionLocal
    local_db = SessionLocal()
    try:
        total = len(raw_chapters)
        for i, ch in enumerate(raw_chapters):
            _jobs[job_id] = {
                "status":  "processing",
                "stage":   f"Indexing chapter {i + 1}/{total}",
                "percent": int(10 + (i / total) * 80),
                "message": ch["title"],
            }
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

            # One call handles summary + chapter-level embedding + paragraph chunks
            await summarize_and_embed_chapter(
                chapter.chapter_id, story_id, i + 1, ch["content"], local_db
            )
            await asyncio.sleep(0.05)  # yield

        _jobs[job_id] = {"status": "complete", "stage": "Story indexed and ready", "percent": 100, "message": ""}
    except Exception as e:
        _jobs[job_id] = {"status": "error", "stage": "Error", "percent": 0, "message": str(e)}
    finally:
        local_db.close()


@router.get("/job/{job_id}", response_model=JobStatus)
def job_status(job_id: str, current_user: User = Depends(get_current_user)):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    j = _jobs[job_id]
    return JobStatus(
        job_id=job_id,
        status=j["status"],
        stage=j["stage"],
        percent=j["percent"],
        message=j.get("message", ""),
    )
