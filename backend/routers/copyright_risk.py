"""
Copyright / Plagiarism Risk Detection (on-demand analysis).

Mirrors the plot-holes analysis pattern: ownership check, heavy-AI rate limit,
strict-JSON service call, mapped Pydantic response. Works at three scopes:

  * selection / chapter — the client sends the prose in `text`.
  * project             — the server assembles a digest from indexed
                          ChapterSummary rows (run *Sync Summaries* first).

This is RISK guidance, not legal advice (disclaimer always returned).
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from openai import APIConnectionError, APIStatusError

from config import settings
from database import get_db
from middleware.rate_limit import limiter, get_user_id
from models import Story, ChapterSummary
from schemas import CopyrightRiskRequest, CopyrightRiskFinding, CopyrightRiskResponse
from routers.auth import get_current_user, User
from services import ai_service
from services.genre_context import build_genre_context

logger = logging.getLogger(__name__)

router = APIRouter(tags=["copyright-risk"])

_MAX_SELECTION_CHARS = 12000
_VALID_SCOPES = ("selection", "chapter", "project")


def _check_story_access(story_id: str, user_id: str, db: Session) -> Story:
    story = db.query(Story).filter(
        Story.story_id == story_id,
        Story.user_id  == user_id,
    ).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return story


def _build_project_digest(story_id: str, db: Session) -> tuple[str, int]:
    """Assemble a structured digest of the whole story from chapter summaries.

    Returns (digest_text, units_analyzed). Raises 422 when nothing is indexed.
    """
    summaries = (
        db.query(ChapterSummary)
        .filter(ChapterSummary.story_id == story_id)
        .order_by(ChapterSummary.chapter_number)
        .all()
    )
    if not summaries:
        raise HTTPException(
            status_code=422,
            detail=(
                "Whole-story analysis needs at least 1 indexed chapter. "
                "Use Sync Summaries in the chapter list to index your story first."
            ),
        )

    lines = []
    for s in summaries:
        events = "; ".join(s.key_events or []) or "—"
        chars  = ", ".join(s.characters_present or []) or "—"
        locs   = ", ".join(s.locations or []) or "—"
        purpose = (s.chapter_purpose or "").strip() or "—"
        summ    = (s.raw_summary or "").strip()
        block = (
            f"Ch{s.chapter_number} | Purpose: {purpose} | Characters: {chars} | "
            f"Locations: {locs} | Events: {events}"
        )
        if summ:
            block += f"\n  Summary: {summ}"
        lines.append(block)

    return "\n".join(lines), len(summaries)


@router.post("/{story_id}/copyright-risk", response_model=CopyrightRiskResponse)
@limiter.limit(settings.rate_limit_heavy_ai, key_func=get_user_id)
async def analyze_copyright_risk(
    request: Request,
    story_id: str,
    data: CopyrightRiskRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_story_access(story_id, current_user.user_id, db)

    scope = (data.scope or "selection").strip().lower()
    if scope not in _VALID_SCOPES:
        raise HTTPException(status_code=422, detail=f"Invalid scope. Use one of: {', '.join(_VALID_SCOPES)}.")

    if scope == "project":
        text, units = _build_project_digest(story_id, db)
    else:
        text = (data.text or "").strip()
        if not text:
            raise HTTPException(status_code=422, detail="No text provided to analyze. Select text or write a chapter first.")
        if len(text) > _MAX_SELECTION_CHARS:
            text = text[:_MAX_SELECTION_CHARS]
        units = 1

    # Genre context never breaks the analysis if lookup fails.
    try:
        genre_context = build_genre_context(story_id, db)
    except Exception:
        genre_context = ""

    try:
        result = await ai_service.analyze_copyright_risk(scope, text, genre_context=genre_context)
    except (APIConnectionError, APIStatusError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"The AI model is currently unavailable. Please try again shortly. ({type(exc).__name__})",
        )
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    findings: list[CopyrightRiskFinding] = []
    for raw in result.get("findings", []):
        try:
            findings.append(CopyrightRiskFinding(**raw))
        except Exception as exc:  # skip malformed finding, keep the rest
            logger.warning("[copyright_risk] skipping malformed finding: %s", exc)

    return CopyrightRiskResponse(
        story_id        = story_id,
        scope           = scope,
        units_analyzed  = units,
        overall_risk    = result["overall_risk"],
        findings_count  = len(findings),
        findings        = findings,
        note            = result.get("note", ""),
        disclaimer      = result["disclaimer"],
    )
