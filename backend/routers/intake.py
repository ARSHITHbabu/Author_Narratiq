import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from middleware.rate_limit import limiter, get_user_id
from models import Story, StoryIntake, GenreProfile
from schemas import IntakeRequest, IntakeResponse, IntakeConfirm, GenreProfile as GenreProfileSchema
from routers.auth import get_current_user, User
from services.ai_service import detect_genre

logger = logging.getLogger(__name__)

router = APIRouter(tags=["intake"])


@router.post("/{story_id}", response_model=IntakeResponse)
@limiter.limit(settings.rate_limit_heavy_ai, key_func=get_user_id)
async def analyze_story(
    request: Request,
    story_id: str,
    data: IntakeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    story = db.query(Story).filter(Story.story_id == story_id, Story.user_id == current_user.user_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    if len(data.description.strip()) < 20:
        raise HTTPException(status_code=400, detail="Description must be at least 20 characters")

    try:
        result = await detect_genre(data.description, data.audience_hint)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    intake = db.query(StoryIntake).filter(StoryIntake.story_id == story_id).first()
    if not intake:
        intake = StoryIntake(story_id=story_id)
        db.add(intake)

    intake.raw_description     = data.description
    intake.detected_genre      = result["genre"]
    intake.detected_sub_genre  = result["sub_genre"]
    intake.detected_tone       = result["tone"]
    intake.detected_audience   = result["audience"]
    intake.detected_structure  = result["structure"]
    conflict = result["conflict"]
    intake.detected_conflict   = json.dumps(conflict) if isinstance(conflict, list) else conflict
    intake.theme_hints         = result["themes"]
    intake.author_confirmed    = False
    db.commit()
    db.refresh(intake)

    logger.info("[intake] genre detected for story=%s: %s", story_id[:8], result["genre"])

    profile = GenreProfileSchema(
        genre=result["genre"],
        sub_genre=result["sub_genre"],
        tone=result["tone"],
        audience=result["audience"],
        structure=result["structure"],
        conflict=result["conflict"],
        themes=result["themes"],
        writing_direction=result.get("writing_direction"),
        confidence=result["confidence"],
        secondary_genres=result.get("secondary_genres", []),
        comparable_titles=result.get("comparable_titles", []),
        marketing_category=result.get("marketing_category") or None,
        emotional_arc=result.get("emotional_arc") or None,
        narrative_pov=result.get("narrative_pov") or None,
        pacing=result.get("pacing") or None,
        content_warnings=result.get("content_warnings", []),
        intelligence_notes=result.get("intelligence_notes") or None,
    )

    return IntakeResponse(intake_id=intake.intake_id, genre_profile=profile, model=settings.vllm_model_name)


@router.post("/{story_id}/confirm")
def confirm_intake(
    story_id: str,
    data: IntakeConfirm,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    intake = db.query(StoryIntake).filter(
        StoryIntake.intake_id == data.intake_id,
        StoryIntake.story_id  == story_id,
    ).first()
    if not intake:
        raise HTTPException(status_code=404, detail="Intake not found")

    intake.author_confirmed = True
    intake.author_overrides = data.overrides or {}

    genre     = data.overrides.get("genre",             intake.detected_genre)
    sub_genre = data.overrides.get("sub_genre",         intake.detected_sub_genre)
    tone      = data.overrides.get("tone",              intake.detected_tone)
    audience  = data.overrides.get("audience",          intake.detected_audience)
    direction = data.overrides.get("writing_direction", "")

    gp = db.query(GenreProfile).filter(GenreProfile.story_id == story_id).first()
    if not gp:
        gp = GenreProfile(story_id=story_id)
        db.add(gp)

    gp.genre             = genre
    gp.sub_genre         = sub_genre
    gp.tone              = tone
    gp.target_audience   = audience
    gp.writing_direction = direction
    db.commit()

    logger.info("[intake] confirmed for story=%s genre=%s", story_id[:8], genre)

    try:
        from services.story_intel_orchestrator import run_analysis_background
        asyncio.create_task(
            run_analysis_background(
                story_id=story_id,
                user_id=current_user.user_id,
                triggered_by="intake",
                passes=["P01", "P02", "P03", "P04", "P05", "P06", "P07"],
            )
        )
    except Exception as exc:
        logger.error(
            "[intake] failed to schedule background passes for story=%s: %s",
            story_id[:8], exc,
        )

    return {"confirmed": True, "story_id": story_id}


@router.get("/{story_id}/genre-profile")
def get_genre_profile(
    story_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    gp = db.query(GenreProfile).filter(GenreProfile.story_id == story_id).first()
    if not gp:
        return None
    return {
        "genre":             gp.genre,
        "sub_genre":         gp.sub_genre,
        "tone":              gp.tone,
        "target_audience":   gp.target_audience,
        "writing_direction": gp.writing_direction,
    }
