import asyncio
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Story, Chapter, ChapterSummary, StoryVersion
from schemas import ChapterCreate, ChapterUpdate, ChapterOut, ChapterWithContent, VersionOut, VersionWithContent
from routers.auth import get_current_user, User

router = APIRouter(tags=["chapters"])


def _word_count(text: str) -> int:
    return len(text.split()) if text else 0


def _check_story_access(story_id: str, user_id: str, db: Session) -> Story:
    story = db.query(Story).filter(Story.story_id == story_id, Story.user_id == user_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return story


@router.get("/{story_id}/chapters", response_model=list[ChapterOut])
def list_chapters(story_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _check_story_access(story_id, current_user.user_id, db)
    return (
        db.query(Chapter)
        .filter(Chapter.story_id == story_id)
        .order_by(Chapter.chapter_number)
        .all()
    )


@router.get("/{story_id}/chapters/{chapter_id}", response_model=ChapterWithContent)
def get_chapter(story_id: str, chapter_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _check_story_access(story_id, current_user.user_id, db)
    chapter = db.query(Chapter).filter(Chapter.chapter_id == chapter_id, Chapter.story_id == story_id).first()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return chapter


@router.post("/{story_id}/chapters", response_model=ChapterOut)
def create_chapter(story_id: str, data: ChapterCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _check_story_access(story_id, current_user.user_id, db)
    last = db.query(Chapter).filter(Chapter.story_id == story_id).order_by(Chapter.chapter_number.desc()).first()
    next_num = (last.chapter_number + 1) if last else 1
    chapter = Chapter(
        story_id=story_id,
        chapter_number=next_num,
        title=data.title,
        content=data.content or "",
        word_count=_word_count(data.content or ""),
    )
    db.add(chapter)
    db.commit()
    db.refresh(chapter)
    return chapter


@router.patch("/{story_id}/chapters/{chapter_id}", response_model=ChapterOut)
async def update_chapter(
    story_id: str,
    chapter_id: str,
    data: ChapterUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_story_access(story_id, current_user.user_id, db)
    chapter = db.query(Chapter).filter(Chapter.chapter_id == chapter_id, Chapter.story_id == story_id).first()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    content_changed = False
    if data.content is not None:
        # Save version before overwriting
        last_version = (
            db.query(StoryVersion)
            .filter(StoryVersion.chapter_id == chapter_id)
            .order_by(StoryVersion.version_number.desc())
            .first()
        )
        next_ver = (last_version.version_number + 1) if last_version else 1
        if chapter.content:  # only save version if there was existing content
            version = StoryVersion(
                chapter_id=chapter_id,
                content=chapter.content,
                version_number=next_ver,
                label=f"Auto-save v{next_ver}",
            )
            db.add(version)

        chapter.content = data.content
        chapter.word_count = _word_count(data.content)
        content_changed = True

    if data.title is not None:
        chapter.title = data.title

    chapter.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(chapter)

    # Update story word count
    story = db.query(Story).filter(Story.story_id == story_id).first()
    total = sum(c.word_count for c in story.chapters)
    story.word_count = total
    story.updated_at = datetime.utcnow()
    db.commit()

    # Kick off background summary + BGE-M3 embedding after content changes
    if content_changed and data.content and data.content.strip():
        asyncio.create_task(
            _regenerate_summary(
                chapter_id=chapter_id,
                story_id=story_id,
                chapter_number=chapter.chapter_number,
                content=data.content,
            )
        )

    return chapter


async def _regenerate_summary(
    chapter_id: str,
    story_id: str,
    chapter_number: int,
    content: str,
) -> None:
    """
    Background task: generate chapter summary via Qwen and embed it with BGE-M3.
    Uses its own DB session so the request session can close immediately.
    """
    from database import SessionLocal
    from services.ai_service import summarize_and_embed_chapter
    db = SessionLocal()
    try:
        await summarize_and_embed_chapter(chapter_id, story_id, chapter_number, content, db)
    except Exception as exc:
        print(f"[summary bg] Failed for chapter {chapter_id[:8]}...: {exc}")
    finally:
        db.close()


@router.delete("/{story_id}/chapters/{chapter_id}")
def delete_chapter(story_id: str, chapter_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _check_story_access(story_id, current_user.user_id, db)
    chapter = db.query(Chapter).filter(Chapter.chapter_id == chapter_id, Chapter.story_id == story_id).first()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    db.delete(chapter)
    db.commit()
    # Re-number remaining chapters
    remaining = db.query(Chapter).filter(Chapter.story_id == story_id).order_by(Chapter.chapter_number).all()
    for i, c in enumerate(remaining, 1):
        c.chapter_number = i
    db.commit()
    return {"deleted": chapter_id}


@router.get("/{story_id}/chapters/{chapter_id}/versions", response_model=list[VersionOut])
def list_versions(story_id: str, chapter_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _check_story_access(story_id, current_user.user_id, db)
    return (
        db.query(StoryVersion)
        .filter(StoryVersion.chapter_id == chapter_id)
        .order_by(StoryVersion.version_number.desc())
        .all()
    )


@router.get("/{story_id}/chapters/{chapter_id}/versions/{version_id}", response_model=VersionWithContent)
def get_version(story_id: str, chapter_id: str, version_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _check_story_access(story_id, current_user.user_id, db)
    version = db.query(StoryVersion).filter(StoryVersion.version_id == version_id, StoryVersion.chapter_id == chapter_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    return version


# ── Backfill: generate summaries + embeddings for all existing chapters ────────

@router.post("/{story_id}/chapters/sync-summaries")
async def sync_chapter_summaries(
    story_id: str,
    force: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Trigger background summary + BGE-M3 embedding generation.
    By default, only processes chapters missing a summary or embedding.
    Pass ?force=true to regenerate ALL chapter summaries (picks up prompt improvements).
    """
    _check_story_access(story_id, current_user.user_id, db)

    chapters = (
        db.query(Chapter)
        .filter(Chapter.story_id == story_id)
        .order_by(Chapter.chapter_number)
        .all()
    )

    from models import ChapterChunk

    to_process = []
    for ch in chapters:
        if not ch.content or not ch.content.strip():
            continue
        if force:
            to_process.append(ch)
        else:
            existing = db.query(ChapterSummary).filter(
                ChapterSummary.chapter_id == ch.chapter_id
            ).first()
            has_chunks = db.query(ChapterChunk).filter(
                ChapterChunk.chapter_id == ch.chapter_id
            ).count() > 0
            # Queue if summary is missing, embedding is missing, OR chunks are missing
            if existing is None or existing.embedding is None or not has_chunks:
                to_process.append(ch)

    print(
        f"[sync-summaries] story={story_id[:8]}... — "
        f"{len(to_process)}/{len(chapters)} chapters need indexing"
    )

    for ch in to_process:
        asyncio.create_task(
            _regenerate_summary(
                chapter_id=ch.chapter_id,
                story_id=story_id,
                chapter_number=ch.chapter_number,
                content=ch.content,
            )
        )

    return {
        "story_id":        story_id,
        "total_chapters":  len(chapters),
        "chapters_queued": len(to_process),
        "message": (
            f"Indexing {len(to_process)} chapter(s) in the background "
            "(summary + chapter-level embedding + paragraph chunks). "
            "Wait ~15–30s per chapter, then re-ask Plot Assistant."
        ) if to_process else "All chapters are fully indexed.",
    }
