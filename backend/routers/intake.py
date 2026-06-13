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
    # Persist the full Story-Intelligence snapshot so the richer fields
    # (emotional_arc, pacing, narrative_pov, comparable_titles, market category,
    # writing_direction, etc.) survive past intake and feed the shared genre
    # context builder. Without this they were returned to the UI then discarded.
    intake.analysis            = result
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

    overrides = data.overrides or {}
    genre     = overrides.get("genre",     intake.detected_genre)
    sub_genre = overrides.get("sub_genre", intake.detected_sub_genre)
    tone      = overrides.get("tone",      intake.detected_tone)
    audience  = overrides.get("audience",  intake.detected_audience)

    gp = db.query(GenreProfile).filter(GenreProfile.story_id == story_id).first()
    if not gp:
        gp = GenreProfile(story_id=story_id)
        db.add(gp)

    # writing_direction precedence: explicit author override → existing manual
    # value (never silently overwritten) → AI-detected direction from the intake
    # analysis snapshot → empty. This auto-persists the detected direction on
    # first confirm while preserving any edit the author made later.
    analysis = intake.analysis if isinstance(intake.analysis, dict) else {}
    override_dir = (overrides.get("writing_direction") or "").strip()
    existing_dir = (gp.writing_direction or "").strip()
    detected_dir = (analysis.get("writing_direction") or "").strip()
    direction = override_dir or existing_dir or detected_dir

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


@router.get("/{story_id}/report")
def get_intake_report(
    story_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the saved Story Intake / Genre Detection report so the intake page
    can display the previous result instead of behaving like a blank first run.

    Merges the author-confirmed core (genre_profiles) over the full detection
    snapshot (story_intakes.analysis). ``exists`` is False only when neither a
    genre profile nor an intake record is present.
    """
    story = db.query(Story).filter(
        Story.story_id == story_id, Story.user_id == current_user.user_id,
    ).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    gp = db.query(GenreProfile).filter(GenreProfile.story_id == story_id).first()
    intake = db.query(StoryIntake).filter(StoryIntake.story_id == story_id).first()

    if not gp and not intake:
        return {"exists": False, "confirmed": False, "genre_profile": None}

    analysis = (intake.analysis if (intake and isinstance(intake.analysis, dict)) else {}) or {}

    # Base on the detection snapshot, then fall back to the StoryIntake columns
    # for older records saved before the snapshot column existed.
    def _detected_conflict():
        c = intake.detected_conflict if intake else None
        if not c:
            return ""
        try:
            parsed = json.loads(c)
            return ", ".join(parsed) if isinstance(parsed, list) else str(parsed)
        except (json.JSONDecodeError, TypeError):
            return str(c)

    profile = {
        "genre":              analysis.get("genre")              or (intake.detected_genre if intake else "") or "",
        "sub_genre":          analysis.get("sub_genre")          or (intake.detected_sub_genre if intake else "") or "",
        "tone":               analysis.get("tone")               or (intake.detected_tone if intake else []) or [],
        "audience":           analysis.get("audience")           or (intake.detected_audience if intake else "") or "",
        "structure":          analysis.get("structure")          or (intake.detected_structure if intake else "") or "",
        "conflict":           analysis.get("conflict")           or _detected_conflict(),
        "themes":             analysis.get("themes")             or (intake.theme_hints if intake else []) or [],
        "writing_direction":  analysis.get("writing_direction")  or "",
        "confidence":         analysis.get("confidence", 0.85),
        "secondary_genres":   analysis.get("secondary_genres", []),
        "comparable_titles":  analysis.get("comparable_titles", []),
        "marketing_category": analysis.get("marketing_category") or None,
        "emotional_arc":      analysis.get("emotional_arc") or None,
        "narrative_pov":      analysis.get("narrative_pov") or None,
        "pacing":             analysis.get("pacing") or None,
        "content_warnings":   analysis.get("content_warnings", []),
        "intelligence_notes": analysis.get("intelligence_notes") or None,
    }

    # Overlay the author-confirmed core so the report matches what the AI tools use.
    if gp:
        profile["genre"]             = gp.genre or profile["genre"]
        profile["sub_genre"]         = gp.sub_genre or profile["sub_genre"]
        if gp.tone:
            profile["tone"]          = gp.tone
        profile["audience"]          = gp.target_audience or profile["audience"]
        profile["writing_direction"] = gp.writing_direction or profile["writing_direction"]

    return {
        "exists": True,
        "confirmed": bool(intake.author_confirmed) if intake else bool(gp),
        "intake_id": intake.intake_id if intake else None,
        "raw_description": intake.raw_description if intake else "",
        "genre_profile": profile,
    }
