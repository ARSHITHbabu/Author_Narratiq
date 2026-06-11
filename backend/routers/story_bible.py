"""
Phase 2 — P2-06 Story Bible Generator
Synthesises all manuscript data into a structured story bible via Qwen.
Stored in story_bibles table. Exportable as DOCX.
Background task with polling-compatible status approach.
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from exceptions import AIServiceUnavailableError
from middleware.rate_limit import limiter, get_user_id
from middleware.concurrency import bg_ai_semaphore
from models import Story, ChapterSummary, CharacterProfile, Character, StoryNote, NoteCard, GenreProfile, StoryBible
from schemas import StoryBibleOut, StoryBibleJobResponse
from routers.auth import get_current_user, User
from services.ai_service import generate_story_bible_section

logger = logging.getLogger(__name__)

router = APIRouter(tags=["story-bible"])

_BIBLE_SECTIONS = ["characters", "locations", "timeline", "world_rules", "themes"]

# In-process guard: prevent concurrent bible generation for the same story
_generating: set[str] = set()


def _get_owned_story(story_id: str, user_id: str, db: Session) -> Story:
    story = db.query(Story).filter(
        Story.story_id == story_id,
        Story.user_id  == user_id,
    ).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return story


def _build_full_context(story_id: str, db: Session) -> str:
    """
    Assemble all manuscript data (summaries, character profiles, notes, cards)
    into a single context string for Qwen. Truncated per item to avoid blowing
    the context window on very large manuscripts.
    """
    lines = []

    # Chapter summaries (most important)
    summaries = (
        db.query(ChapterSummary)
        .filter(ChapterSummary.story_id == story_id)
        .order_by(ChapterSummary.chapter_number)
        .all()
    )
    if summaries:
        lines.append("=== CHAPTER SUMMARIES ===")
        for s in summaries:
            lines.append(
                f"Chapter {s.chapter_number}: "
                f"events={s.key_events}, "
                f"characters={s.characters_present}, "
                f"locations={s.locations}, "
                f"tone={s.emotional_tone}, "
                f"summary={str(s.raw_summary or '')[:300]}"
            )

    # Character profiles
    chars = (
        db.query(Character, CharacterProfile)
        .outerjoin(CharacterProfile, Character.character_id == CharacterProfile.character_id)
        .filter(Character.story_id == story_id)
        .all()
    )
    if chars:
        lines.append("\n=== CHARACTER PROFILES ===")
        for c, p in chars:
            if p:
                lines.append(
                    f"{c.name} ({c.role}): "
                    f"appearance={p.appearance[:150]}, "
                    f"personality={p.personality[:150]}, "
                    f"goals={p.goals[:100]}, "
                    f"backstory={p.backstory[:200]}"
                )
            else:
                lines.append(f"{c.name} ({c.role}): no profile")

    # Story notes
    notes = db.query(StoryNote).filter(StoryNote.story_id == story_id).all()
    if notes:
        lines.append("\n=== STORY NOTES ===")
        for n in notes:
            lines.append(f"[{n.title}]: {n.content[:300]}")

    # Note cards
    cards = db.query(NoteCard).filter(NoteCard.story_id == story_id).all()
    if cards:
        lines.append("\n=== NOTE CARDS ===")
        for c in cards:
            lines.append(f"[{c.card_type} — {c.title}]: {c.content[:200]}")

    # Genre
    genre = db.query(GenreProfile).filter(GenreProfile.story_id == story_id).first()
    if genre:
        lines.append(f"\n=== GENRE ===\nGenre: {genre.genre}, Sub-genre: {genre.sub_genre}, Tone: {genre.tone}")

    return "\n".join(lines)


async def _generate_bible_pipeline(story_id: str, user_id: str, existing_bible_id: str | None) -> None:
    """
    Background task: generate all 5 sections of the story bible, store result.
    If existing_bible_id is provided, the existing row is updated (regeneration).
    Runs under bg_ai_semaphore to prevent vLLM queue flooding.
    """
    from database import SessionLocal
    db = SessionLocal()
    try:
        _generating.add(story_id)
        context = _build_full_context(story_id, db)

        content: dict[str, str] = {}
        async with bg_ai_semaphore():
            for section in _BIBLE_SECTIONS:
                try:
                    text = await generate_story_bible_section(section=section, context=context)
                    content[section] = text
                except AIServiceUnavailableError as exc:
                    logger.warning("[story_bible] AI unavailable for section %s (story=%s): %s", section, story_id[:8], exc)
                    content[section] = f"[AI temporarily unavailable — please regenerate]"
                except Exception as exc:
                    content[section] = f"[Error generating {section}: {exc}]"

        content_json = json.dumps(content, ensure_ascii=False)

        if existing_bible_id:
            bible = db.query(StoryBible).filter(StoryBible.bible_id == existing_bible_id).first()
            if bible:
                bible.content_json = content_json
                bible.version      = (bible.version or 1) + 1
                bible.updated_at   = datetime.utcnow()
                db.commit()
                logger.info("[story_bible] regenerated v%d for %s", bible.version, story_id[:8])
                return

        bible = StoryBible(
            story_id=story_id,
            user_id=user_id,
            content_json=content_json,
        )
        db.add(bible)
        db.commit()
        logger.info("[story_bible] generated v1 for %s", story_id[:8])
    except Exception as exc:
        logger.error("[story_bible] generation failed for %s: %s", story_id[:8], exc)
    finally:
        _generating.discard(story_id)
        db.close()


@router.post("/{story_id}/story-bible", response_model=StoryBibleJobResponse)
@limiter.limit(settings.rate_limit_background_ai, key_func=get_user_id)
async def create_or_regenerate_bible(
    request: Request,
    story_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Trigger story bible generation (or regeneration if one already exists).
    Returns a job_id immediately. Poll GET /story-bible until the bible appears.
    Background task: Qwen synthesises characters, locations, timeline, world rules, themes.
    """
    _get_owned_story(story_id, current_user.user_id, db)

    if story_id in _generating:
        existing = (
            db.query(StoryBible)
            .filter(StoryBible.story_id == story_id)
            .order_by(StoryBible.version.desc())
            .first()
        )
        return StoryBibleJobResponse(
            job_id="in-progress",
            status="already_generating",
            bible_id=existing.bible_id if existing else None,
        )

    summaries_count = (
        db.query(ChapterSummary)
        .filter(ChapterSummary.story_id == story_id)
        .count()
    )
    if summaries_count == 0:
        raise HTTPException(
            status_code=422,
            detail="No indexed chapters found. Index at least one chapter first.",
        )

    # Check for existing bible (for regeneration tracking)
    existing = (
        db.query(StoryBible)
        .filter(StoryBible.story_id == story_id)
        .order_by(StoryBible.version.desc())
        .first()
    )
    existing_id = existing.bible_id if existing else None

    job_id = str(uuid.uuid4())
    asyncio.create_task(
        _generate_bible_pipeline(story_id, current_user.user_id, existing_id)
    )

    return StoryBibleJobResponse(
        job_id=job_id,
        status="processing",
        bible_id=existing_id,
    )


@router.get("/{story_id}/story-bible", response_model=StoryBibleOut)
def get_story_bible(
    story_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve the latest generated story bible."""
    _get_owned_story(story_id, current_user.user_id, db)

    bible = (
        db.query(StoryBible)
        .filter(StoryBible.story_id == story_id)
        .order_by(StoryBible.version.desc())
        .first()
    )
    if not bible:
        raise HTTPException(
            status_code=404,
            detail="No story bible found. Generate one first via POST /story-bible.",
        )
    return bible


@router.get("/{story_id}/story-bible/export")
def export_story_bible_docx(
    story_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Export the story bible as a formatted DOCX document."""
    import io
    from docx import Document as DocxDocument
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    story = _get_owned_story(story_id, current_user.user_id, db)

    bible = (
        db.query(StoryBible)
        .filter(StoryBible.story_id == story_id)
        .order_by(StoryBible.version.desc())
        .first()
    )
    if not bible:
        raise HTTPException(status_code=404, detail="No story bible found.")

    try:
        content = json.loads(bible.content_json)
    except (json.JSONDecodeError, TypeError):
        content = {}

    doc = DocxDocument()

    # Title page
    title_para = doc.add_heading(f"{story.title} — Story Bible", level=0)
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER

    subtitle = doc.add_paragraph(f"Version {bible.version}  |  Generated by NarratIQ AI")
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_page_break()

    section_titles = {
        "characters":  "Characters",
        "locations":   "Locations",
        "timeline":    "Timeline",
        "world_rules": "World Rules",
        "themes":      "Themes & Motifs",
    }

    for key in _BIBLE_SECTIONS:
        text = content.get(key, "")
        if not text:
            continue

        doc.add_heading(section_titles.get(key, key.title()), level=1)
        for line in text.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("---"):
                doc.add_paragraph("—" * 30)
            else:
                doc.add_paragraph(stripped)

        doc.add_page_break()

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)

    safe_title = "".join(c if c.isalnum() or c in "-_ " else "_" for c in story.title)[:60]
    filename = f"{safe_title}_story_bible_v{bible.version}.docx"

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
