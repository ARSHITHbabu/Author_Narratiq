"""
Phase 2 Writing Tools Router
Handles: P2-02 Chapter Continuation Suggestion, P2-04 Scene Outline Generator
All endpoints enforce story ownership and use existing RAG pipelines.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from middleware.rate_limit import limiter, get_user_id
from models import Story, Chapter, ChapterSummary, GenreProfile
from schemas import (
    ContinuationRequest, ContinuationSuggestion, ContinuationResponse,
    OutlineRequest, OutlineBeat, OutlineResponse,
)
from routers.auth import get_current_user, User
from services.genre_context import build_genre_context
from services.ai_service import (
    generate_continuations,
    generate_chapter_outline,
    retrieve_relevant_chunks,
    retrieve_character_context,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["writing-tools"])

_MAX_TAIL_WORDS = 1500
_MAX_GOAL_WORDS = 500


def _get_owned_story(story_id: str, user_id: str, db: Session) -> Story:
    story = db.query(Story).filter(
        Story.story_id == story_id,
        Story.user_id  == user_id,
    ).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return story


def _get_genre_context(story_id: str, db: Session) -> str:
    # Delegates to the shared, reusable genre-context builder so every AI tool
    # injects the genre profile identically (see services/genre_context.py).
    return build_genre_context(story_id, db)


def _trim_to_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[-max_words:])


# ── P2-02: Chapter Continuation Suggestion ────────────────────────────────────

@router.post("/{story_id}/chapters/{chapter_id}/continue", response_model=ContinuationResponse)
@limiter.limit(settings.rate_limit_heavy_ai, key_func=get_user_id)
async def generate_chapter_continuation(
    request: Request,
    story_id: str,
    chapter_id: str,
    body: ContinuationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Generate 3 continuation options for the current chapter.
    tail_text: the last 3–5 paragraphs provided by the frontend editor.
    Uses retrieve_relevant_chunks + retrieve_character_context for grounding.
    """
    story = _get_owned_story(story_id, current_user.user_id, db)

    # Verify chapter belongs to story
    chapter = db.query(Chapter).filter(
        Chapter.chapter_id == chapter_id,
        Chapter.story_id   == story_id,
    ).first()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    if not body.tail_text or not body.tail_text.strip():
        raise HTTPException(status_code=400, detail="tail_text must not be empty.")

    # Trim tail_text to avoid context overflow
    tail_trimmed = _trim_to_words(body.tail_text.strip(), _MAX_TAIL_WORDS)

    # Retrieve story context
    story_context_chunks = await retrieve_relevant_chunks(
        query=tail_trimmed,
        story_id=story_id,
        db=db,
        max_chapter_number=chapter.chapter_number,
    )
    story_context = "\n\n".join(
        f"[Ch{c.get('chapter_number', '')}] {c.get('text', '')}"
        for c in story_context_chunks[:4]
    )

    # Retrieve character context if names detected
    char_context_str = await retrieve_character_context(
        query=tail_trimmed,
        story_id=story_id,
        db=db,
    )

    genre_ctx = _get_genre_context(story_id, db)

    continuation_length = max(50, min(body.continuation_length or 200, 500))

    suggestions_raw = await generate_continuations(
        tail_text=tail_trimmed,
        story_context=story_context,
        character_context=char_context_str,
        genre_context=genre_ctx,
        continuation_length=continuation_length,
    )

    suggestions = [
        ContinuationSuggestion(
            direction=s["direction"],
            text=s["text"],
            rationale=s["rationale"],
        )
        for s in suggestions_raw
    ]

    # Pad to 3 if Qwen returned fewer
    while len(suggestions) < 3:
        suggestions.append(ContinuationSuggestion(
            direction="Alternative direction",
            text="",
            rationale="Could not generate this suggestion — please retry.",
        ))

    return ContinuationResponse(chapter_id=chapter_id, suggestions=suggestions[:3])


# ── P2-04: Chapter / Scene Outline Generator ──────────────────────────────────

@router.post("/{story_id}/chapters/{chapter_id}/outline", response_model=OutlineResponse)
@limiter.limit(settings.rate_limit_heavy_ai, key_func=get_user_id)
async def generate_outline(
    request: Request,
    story_id: str,
    chapter_id: str,
    body: OutlineRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Generate a scene-by-scene outline for a chapter based on the author's goal.
    scene_count capped at 8. chapter_goal must be at least 10 words.
    """
    _get_owned_story(story_id, current_user.user_id, db)

    chapter = db.query(Chapter).filter(
        Chapter.chapter_id == chapter_id,
        Chapter.story_id   == story_id,
    ).first()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    goal = body.chapter_goal.strip()
    if len(goal.split()) < 10:
        raise HTTPException(
            status_code=400,
            detail="chapter_goal must be at least 10 words. Provide more detail about what you want to happen.",
        )

    goal_trimmed = _trim_to_words(goal, _MAX_GOAL_WORDS)
    scene_count  = max(1, min(body.scene_count or 4, 8))

    # Retrieve context
    story_context_chunks = await retrieve_relevant_chunks(
        query=goal_trimmed,
        story_id=story_id,
        db=db,
        max_chapter_number=chapter.chapter_number,
    )
    story_context = "\n\n".join(
        f"[Ch{c.get('chapter_number', '')}] {c.get('text', '')}"
        for c in story_context_chunks[:4]
    )

    char_context_str = await retrieve_character_context(
        query=goal_trimmed,
        story_id=story_id,
        db=db,
    )

    genre_ctx = _get_genre_context(story_id, db)

    beats_raw = await generate_chapter_outline(
        chapter_goal=goal_trimmed,
        scene_count=scene_count,
        story_context=story_context,
        character_context=char_context_str,
        genre_context=genre_ctx,
    )

    beats = [
        OutlineBeat(
            scene_number=b["scene_number"],
            beat_description=b["beat_description"],
            characters_present=b["characters_present"],
            location=b["location"],
            pacing_note=b["pacing_note"],
        )
        for b in beats_raw
    ]

    return OutlineResponse(chapter_id=chapter_id, outline=beats)
