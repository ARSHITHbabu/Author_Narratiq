"""
Phase 2 — P2-09 Pacing & Word Count Goal Tracker
Pure arithmetic on existing DB data — no AI invocation.
One pacing_goals row per story (upsert semantics).
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Story, Chapter, PacingGoal
from schemas import PacingGoalCreate, PacingGoalResponse, ChapterWordCount
from routers.auth import get_current_user, User

router = APIRouter(tags=["pacing"])


def _get_owned_story(story_id: str, user_id: str, db: Session) -> Story:
    story = db.query(Story).filter(
        Story.story_id == story_id,
        Story.user_id  == user_id,
    ).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return story


def _compute_response(story: Story, goal: PacingGoal, db: Session) -> PacingGoalResponse:
    chapters = (
        db.query(Chapter)
        .filter(Chapter.story_id == story.story_id)
        .order_by(Chapter.chapter_number)
        .all()
    )

    actual_chapter_count = len(chapters)

    # Fallback: sum chapter word counts if story.word_count is 0 or None
    actual_word_count = story.word_count or 0
    if actual_word_count == 0:
        actual_word_count = sum(c.word_count or 0 for c in chapters)

    avg_words = (
        actual_word_count // actual_chapter_count
        if actual_chapter_count > 0
        else 0
    )

    target_wc = goal.target_word_count or 0
    progress_pct = (
        round(min(actual_word_count / target_wc * 100, 100), 1)
        if target_wc > 0
        else 0.0
    )

    target_cc = goal.target_chapter_count or 0
    estimated_remaining = max(0, target_cc - actual_chapter_count)

    distribution = [
        ChapterWordCount(
            chapter_number=c.chapter_number,
            chapter_title=c.title or f"Chapter {c.chapter_number}",
            word_count=c.word_count or 0,
        )
        for c in chapters
    ]

    return PacingGoalResponse(
        story_id=story.story_id,
        target_word_count=goal.target_word_count or 0,
        target_chapter_count=goal.target_chapter_count or 0,
        target_words_per_chapter=goal.target_words_per_chapter or 0,
        actual_word_count=actual_word_count,
        actual_chapter_count=actual_chapter_count,
        avg_words_per_chapter=avg_words,
        progress_pct=progress_pct,
        estimated_chapters_remaining=estimated_remaining,
        chapter_distribution=distribution,
        current_streak_days=goal.current_streak_days or 0,
    )


@router.post("/{story_id}/pacing-goals", response_model=PacingGoalResponse)
def set_pacing_goal(
    story_id: str,
    body: PacingGoalCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create or update the pacing goal for a story.
    One row per story (upsert). Returns computed progress alongside stored targets.
    """
    story = _get_owned_story(story_id, current_user.user_id, db)

    goal = db.query(PacingGoal).filter(PacingGoal.story_id == story_id).first()
    if goal:
        goal.target_word_count        = body.target_word_count or 0
        goal.target_chapter_count     = body.target_chapter_count or 0
        goal.target_words_per_chapter = body.target_words_per_chapter or 0
        goal.updated_at               = datetime.utcnow()
    else:
        goal = PacingGoal(
            story_id=story_id,
            user_id=current_user.user_id,
            target_word_count=body.target_word_count or 0,
            target_chapter_count=body.target_chapter_count or 0,
            target_words_per_chapter=body.target_words_per_chapter or 0,
        )
        db.add(goal)

    db.commit()
    db.refresh(goal)
    return _compute_response(story, goal, db)


@router.get("/{story_id}/pacing-goals", response_model=PacingGoalResponse)
def get_pacing_goal(
    story_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve current pacing goal and computed progress.
    Returns zero targets if no goal has been set yet (author sees current state).
    """
    story = _get_owned_story(story_id, current_user.user_id, db)

    goal = db.query(PacingGoal).filter(PacingGoal.story_id == story_id).first()
    if not goal:
        goal = PacingGoal(
            story_id=story_id,
            user_id=current_user.user_id,
        )

    return _compute_response(story, goal, db)
