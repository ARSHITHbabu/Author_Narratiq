import uuid
from fastapi import APIRouter, Depends, HTTPException
import json
import json
from sqlalchemy.orm import Session

from database import get_db
from models import Story, StoryIntake, GenreProfile
from schemas import IntakeRequest, IntakeResponse, IntakeConfirm, GenreProfile as GenreProfileSchema
from routers.auth import get_current_user, User
from services.ai_service import detect_genre

router = APIRouter(tags=["intake"])


@router.post("/{story_id}", response_model=IntakeResponse)
async def analyze_story(
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

    result = await detect_genre(data.description, data.audience_hint)

    # Upsert intake record
    intake = db.query(StoryIntake).filter(StoryIntake.story_id == story_id).first()
    if not intake:
        intake = StoryIntake(story_id=story_id)
        db.add(intake)

    intake.raw_description = data.description
    intake.detected_genre = result["genre"]
    intake.detected_sub_genre = result["sub_genre"]
    intake.detected_tone = result["tone"]
    intake.detected_audience = result["audience"]
    intake.detected_structure = result["structure"]
    conflict = result["conflict"]
    intake.detected_conflict = json.dumps(conflict) if isinstance(conflict, list) else conflict
    intake.theme_hints = result["themes"]
    intake.author_confirmed = False
    db.commit()
    db.refresh(intake)

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
    )

    return IntakeResponse(intake_id=intake.intake_id, genre_profile=profile, model="placeholder-v1")


@router.post("/{story_id}/confirm")
def confirm_intake(
    story_id: str,
    data: IntakeConfirm,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    intake = db.query(StoryIntake).filter(StoryIntake.intake_id == data.intake_id, StoryIntake.story_id == story_id).first()
    if not intake:
        raise HTTPException(status_code=404, detail="Intake not found")

    intake.author_confirmed = True
    intake.author_overrides = data.overrides or {}

    # Apply overrides and save to genre_profiles
    genre = data.overrides.get("genre", intake.detected_genre)
    sub_genre = data.overrides.get("sub_genre", intake.detected_sub_genre)
    tone = data.overrides.get("tone", intake.detected_tone)
    audience = data.overrides.get("audience", intake.detected_audience)
    direction = data.overrides.get("writing_direction", "")

    gp = db.query(GenreProfile).filter(GenreProfile.story_id == story_id).first()
    if not gp:
        gp = GenreProfile(story_id=story_id)
        db.add(gp)

    gp.genre = genre
    gp.sub_genre = sub_genre
    gp.tone = tone
    gp.target_audience = audience
    gp.writing_direction = direction
    db.commit()

    return {"confirmed": True, "story_id": story_id}


@router.get("/{story_id}/genre-profile")
def get_genre_profile(story_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    gp = db.query(GenreProfile).filter(GenreProfile.story_id == story_id).first()
    if not gp:
        return None
    return {
        "genre": gp.genre,
        "sub_genre": gp.sub_genre,
        "tone": gp.tone,
        "target_audience": gp.target_audience,
        "writing_direction": gp.writing_direction,
    }
