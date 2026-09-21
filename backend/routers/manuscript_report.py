import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from openai import APIConnectionError, APIStatusError

from database import get_db
from models import Story, ChapterSummary
from schemas import (
    CharacterArcEntry, PacingAnalysis, UnresolvedThread,
    StrengthEntry, ImprovementEntry, ManuscriptReport,
    StakesAssessment, StakesEscalationPoint, ThemeEntry,
)
from routers.auth import get_current_user, User
from services.ai_service import analyze_manuscript

logger = logging.getLogger(__name__)

router = APIRouter(tags=["manuscript-report"])


def _check_story_access(story_id: str, user_id: str, db: Session) -> Story:
    story = db.query(Story).filter(
        Story.story_id == story_id,
        Story.user_id  == user_id,
    ).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return story


@router.post("/{story_id}/manuscript-report", response_model=ManuscriptReport)
async def get_manuscript_report(
    story_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Generate a full editorial analysis report for the story.

    Aggregates all indexed ChapterSummary records and produces a structured
    report covering character arcs, pacing, unresolved threads, strengths,
    and areas for improvement.  Every finding includes the specific chapter
    numbers that support it — giving authors verifiable, auditable evidence.

    Requires at least 2 indexed chapter summaries.
    Uses the summary_pass strategy by default; future strategies are selectable
    without endpoint or schema changes — see analyze_manuscript() in ai_service.py.
    """
    story = _check_story_access(story_id, current_user.user_id, db)

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
                "Manuscript analysis requires at least 2 indexed chapters. "
                "Use Sync Summaries in the chapter list to index your story first."
            ),
        )

    stale_count = sum(1 for s in summaries if s.is_stale)

    chapter_data = []
    for s in summaries:
        wc = 0
        try:
            if s.chapter:
                wc = s.chapter.word_count or 0
        except Exception:
            pass
        chapter_data.append({
            "chapter":     s.chapter_number,
            "events":      s.key_events         or [],
            "characters":  s.characters_present or [],
            "locations":   s.locations          or [],
            "tone":        s.emotional_tone     or "",
            "purpose":     s.chapter_purpose    or "",
            "word_count":  wc,
            "raw_summary": s.raw_summary        or "",
        })

    try:
        result = await analyze_manuscript(
            story_id = story_id,
            chapters = chapter_data,
            strategy = "summary_pass",
            db       = db,
        )
    except (APIConnectionError, APIStatusError) as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "The AI model (Qwen/vLLM) is currently unavailable. "
                f"Please wait a moment and try again. ({type(exc).__name__})"
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    note_parts = []
    if result.get("mode_note"):
        note_parts.append(result["mode_note"])
    if result.get("note"):
        note_parts.append(result["note"])
    if stale_count:
        note_parts.append(
            f"{stale_count} chapter(s) have stale summaries — re-sync for best accuracy."
        )
    if result.get("citations_suppressed"):
        note_parts.append(
            f"{result['citations_suppressed']} finding(s) were dropped for citing a chapter "
            "number that doesn't exist in this manuscript."
        )
    analysis_note = " ".join(note_parts)

    arcs: list[CharacterArcEntry] = []
    for raw in result.get("character_arcs", []):
        try:
            arcs.append(CharacterArcEntry(
                name         = raw.get("name",         "Unknown"),
                appears_in   = raw.get("appears_in",   []),
                arc_summary  = raw.get("arc_summary",  ""),
                completeness = raw.get("completeness", "partial"),
            ))
        except Exception as exc:
            logger.warning(f"[manuscript] skipping malformed arc: {exc}")
    raw_pacing = result.get("pacing") or {}
    pacing = PacingAnalysis(
        slow_chapters    = raw_pacing.get("slow_chapters",    []),
        intense_chapters = raw_pacing.get("intense_chapters", []),
        assessment       = raw_pacing.get("assessment",       ""),
    )

    threads: list[UnresolvedThread] = []
    for raw in result.get("unresolved_threads", []):
        try:
            threads.append(UnresolvedThread(
                description   = raw.get("description",   ""),
                introduced_in = raw.get("introduced_in", 0),
                chapters      = raw.get("chapters",      []),
            ))
        except Exception as exc:
            logger.warning(f"[manuscript] skipping malformed thread: {exc}")
    strengths: list[StrengthEntry] = []
    for raw in result.get("strengths", []):
        try:
            strengths.append(StrengthEntry(
                text     = raw.get("text",     ""),
                chapters = raw.get("chapters", []),
            ))
        except Exception as exc:
            logger.warning(f"[manuscript] skipping malformed strength: {exc}")
    improvements: list[ImprovementEntry] = []
    for raw in result.get("improvements", []):
        try:
            improvements.append(ImprovementEntry(
                text     = raw.get("text",     ""),
                chapters = raw.get("chapters", []),
            ))
        except Exception as exc:
            logger.warning(f"[manuscript] skipping malformed improvement: {exc}")

    stakes = None
    raw_stakes = result.get("stakes")
    if isinstance(raw_stakes, dict):
        try:
            stakes = StakesAssessment(
                summary=raw_stakes.get("summary", ""),
                escalation=[
                    StakesEscalationPoint(chapter=e.get("chapter"), note=e.get("note", ""))
                    for e in (raw_stakes.get("escalation") or [])
                    if isinstance(e, dict) and e.get("chapter") is not None
                ],
            )
        except Exception as exc:
            logger.warning(f"[manuscript] skipping malformed stakes: {exc}")

    themes: list[ThemeEntry] = []
    for raw in result.get("themes", []):
        try:
            themes.append(ThemeEntry(theme=raw.get("theme", ""), chapters=raw.get("chapters", [])))
        except Exception as exc:
            logger.warning(f"[manuscript] skipping malformed theme: {exc}")

    wc_total = story.word_count or result.get("word_count_total", 0)

    return ManuscriptReport(
        story_id           = story_id,
        chapters_analyzed  = result["chapters_analyzed"],
        word_count_total   = wc_total,
        character_arcs     = arcs,
        pacing             = pacing,
        unresolved_threads = threads,
        strengths          = strengths,
        improvements       = improvements,
        analysis_note      = analysis_note,
        stakes                     = stakes,
        themes                     = themes,
        chapter_plot_importance    = result.get("chapter_plot_importance", {}),
        deterministic_open_threads = result.get("deterministic_open_threads", []),
        citations_suppressed       = result.get("citations_suppressed", 0),
    )
