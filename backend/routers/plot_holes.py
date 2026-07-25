import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from openai import APIConnectionError, APIStatusError

from config import settings
from database import get_db
from middleware.rate_limit import limiter, get_user_id
from models import Story, ChapterSummary
from schemas import PlotHoleIssue, PlotHoleResponse
from routers.auth import get_current_user, User
from services.ai_service import detect_plot_holes

logger = logging.getLogger(__name__)

router = APIRouter(tags=["plot-holes"])


def _check_story_access(story_id: str, user_id: str, db: Session) -> Story:
    story = db.query(Story).filter(
        Story.story_id == story_id,
        Story.user_id  == user_id,
    ).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return story


@router.post("/{story_id}/plot-holes", response_model=PlotHoleResponse)
@limiter.limit(settings.rate_limit_heavy_ai, key_func=get_user_id)
async def analyze_plot_holes(
    request: Request,
    story_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Run plot hole detection over all indexed chapter summaries for the story.
    Uses the single_pass strategy by default.
    """
    _check_story_access(story_id, current_user.user_id, db)

    summaries = (
        db.query(ChapterSummary)
        .filter(ChapterSummary.story_id == story_id)
        .order_by(ChapterSummary.chapter_number)
        .all()
    )

    if len(summaries) < 2:
        raise HTTPException(
            status_code=422,
            detail=(
                "Plot hole detection requires at least 2 indexed chapters. "
                "Use Sync Summaries in the chapter list to index your story first."
            ),
        )

    stale_count = sum(1 for s in summaries if s.is_stale)

    chapter_data = [
        {
            "chapter":    s.chapter_number,
            "events":     s.key_events         or [],
            "characters": s.characters_present or [],
            "locations":  s.locations          or [],
            "timeline":   s.timeline_markers   or [],
            "purpose":    s.chapter_purpose    or "",
        }
        for s in summaries
    ]

    try:
        result = await detect_plot_holes(
            story_id  = story_id,
            summaries = chapter_data,
            strategy  = "single_pass",
        )
    except (APIConnectionError, APIStatusError) as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "The AI model is currently unavailable. "
                f"Please wait a moment and try again. ({type(exc).__name__})"
            ),
        )
    except ValueError as exc:
        # Fixed author-facing text. str(exc) previously went straight to the
        # client, which is safe only while every ValueError on this path happens
        # to carry a hand-written message — one internal error and the author
        # reads our internals. Detail belongs in the log.
        logger.warning("[plot_holes] analysis failed for %s: %s", story_id[:8], exc)
        raise HTTPException(
            status_code=503,
            detail="Plot hole analysis could not be completed. Please try again.",
        )

    note_parts = []
    if result["note"]:
        note_parts.append(result["note"])
    if stale_count:
        note_parts.append(
            f"{stale_count} chapter(s) have stale summaries — re-sync for best accuracy."
        )
    analysis_note = " ".join(note_parts) or f"Analyzed {result['chapters_analyzed']} chapter(s)."

    issues: list[PlotHoleIssue] = []
    for i, raw in enumerate(result.get("issues", [])):
        try:
            issues.append(PlotHoleIssue(
                issue_id    = raw.get("issue_id", i + 1),
                type        = raw.get("type", "other"),
                severity    = raw.get("severity", "low"),
                chapters    = raw.get("chapters", []),
                description = raw.get("description", ""),
                suggestion  = raw.get("suggestion", ""),
            ))
        except Exception as exc:
            logger.warning("[plot_holes] skipping malformed issue #%d: %s", i, exc)

    return PlotHoleResponse(
        story_id          = story_id,
        chapters_analyzed = result["chapters_analyzed"],
        issues_found      = len(issues),
        issues            = issues,
        analysis_note     = analysis_note,
        degraded          = bool(result.get("degraded")),
        degraded_reason   = result.get("degraded_reason"),
    )
