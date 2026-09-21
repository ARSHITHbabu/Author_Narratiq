"""
Stage 5 task 5.15 — writing analytics, computed server-side.

Pure arithmetic + read-only DB queries — no AI invocation, matching
pacing.py's own precedent for a lightweight, always-fast analytics endpoint.
See services/analytics_service.py for the metric calculations, the two bugs
fixed relative to the old client-side version, and the genre/story-
intelligence integration.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Story, Chapter, GenreProfile
from schemas import StoryAnalyticsResponse
from routers.auth import get_current_user, User
from services.analytics_service import compute_story_analytics
from routers.search import _html_to_plain

router = APIRouter(tags=["analytics"])


@router.get("/{story_id}/analytics", response_model=StoryAnalyticsResponse)
def get_story_analytics(
    story_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    story = db.query(Story).filter(
        Story.story_id == story_id, Story.user_id == current_user.user_id,
    ).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    chapters = db.query(Chapter).filter(Chapter.story_id == story_id).all()
    full_text = " ".join(_html_to_plain(ch.content or "") for ch in chapters)

    genre_profile = db.query(GenreProfile).filter(GenreProfile.story_id == story_id).first()
    genre = genre_profile.genre if genre_profile else None

    result = compute_story_analytics(
        total_words=story.word_count or 0,
        chapter_count=len(chapters),
        full_text=full_text,
        genre=genre,
        db=db, story_id=story_id,
    )
    return StoryAnalyticsResponse(**result)
