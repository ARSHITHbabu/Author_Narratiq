import hashlib
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from openai import APIConnectionError, APIStatusError

from database import get_db
from models import Story, Chapter, ChapterSummary, Character, ManuscriptReportRecord, gen_uuid
from schemas import (
    CharacterArcEntry, PacingAnalysis, UnresolvedThread,
    StrengthEntry, ImprovementEntry, ManuscriptReport,
    StakesAssessment, StakesEscalationPoint, ThemeEntry,
    RelationshipArcEntry, NarrativeSignalEntry,
)
from routers.auth import get_current_user, User
from services import signal_inputs
from services.ai_service import analyze_manuscript
from services.narrative_signals import build_narrative_signals
from services.relationship_arcs import build_relationship_arcs

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


def _source_fingerprint(story_id: str, db: Session) -> str:
    """Hash of what a report is built from (D2 / review L3): every indexed
    chapter's id, the chapter's own updated_at, its summary's generated_at and
    stale flag. Any edit, re-index, addition or removal changes it."""
    rows = (
        db.query(ChapterSummary.chapter_id, Chapter.updated_at,
                 ChapterSummary.generated_at, ChapterSummary.is_stale)
        .outerjoin(Chapter, Chapter.chapter_id == ChapterSummary.chapter_id)
        .filter(ChapterSummary.story_id == story_id)
        .order_by(ChapterSummary.chapter_id)
        .all()
    )
    h = hashlib.sha256()
    for chapter_id, updated_at, generated_at, is_stale in rows:
        h.update(f"{chapter_id}|{updated_at.isoformat() if updated_at else ''}|"
                 f"{generated_at.isoformat() if generated_at else ''}|{bool(is_stale)}\n".encode())
    return h.hexdigest()


def _save_report(story_id: str, user_id: str, report: ManuscriptReport, fingerprint: str, db: Session) -> None:
    """One row per story (UNIQUE story_id): a regeneration replaces the
    previous report atomically, and two concurrent generations cannot create
    two rows (review M2)."""
    now = datetime.utcnow()
    values = {
        "story_id": story_id, "user_id": user_id,
        "content_json": report.model_dump_json(),
        "chapters_analyzed": report.chapters_analyzed,
        "source_fingerprint": fingerprint,
        "degraded": report.degraded,
        "created_at": now, "updated_at": now,
    }
    stmt = pg_insert(ManuscriptReportRecord.__table__).values(report_id=gen_uuid(), **values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["story_id"],
        set_={k: stmt.excluded[k] for k in ("user_id", "content_json", "chapters_analyzed",
                                            "source_fingerprint", "degraded", "updated_at")},
    )
    db.execute(stmt)
    db.commit()


@router.get("/{story_id}/manuscript-report", response_model=ManuscriptReport)
async def get_saved_manuscript_report(
    story_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The last generated report for this story (D2). 404 when none has been
    generated yet. is_stale is True when indexed chapters changed since."""
    _check_story_access(story_id, current_user.user_id, db)
    record = (
        db.query(ManuscriptReportRecord)
        .filter(ManuscriptReportRecord.story_id == story_id,
                ManuscriptReportRecord.user_id == current_user.user_id)
        .first()
    )
    if record is None:
        raise HTTPException(status_code=404, detail="No saved report for this story yet.")
    try:
        report = ManuscriptReport.model_validate_json(record.content_json)
    except Exception as exc:
        logger.warning("[manuscript] saved report unreadable (%s) — asking the author to regenerate",
                       type(exc).__name__)
        raise HTTPException(status_code=404, detail="No saved report for this story yet.")
    report.generated_at = report.generated_at or record.updated_at
    report.is_stale = record.source_fingerprint != _source_fingerprint(story_id, db)
    return report


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
        # Never echo the exception text to the author (it can carry internal
        # detail); the type is enough for the log.
        logger.warning("[manuscript] analysis failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="The manuscript report could not be generated right now. Please try again.",
        )

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

    # Stage 5 (5.14-R / 5.14-N) — deterministic sections, no LLM call.
    names_by_id = {
        cid: name for cid, name in
        db.query(Character.character_id, Character.name).filter(Character.story_id == story_id).all()
    }
    rel_raw, rel_dropped = build_relationship_arcs(
        [{"chapter": s.chapter_number, "relationship_changes": s.relationship_changes} for s in summaries],
        names_by_id,
    )
    if rel_dropped:
        logger.info("[manuscript] relationship changes not attributable to two known characters: %d",
                    rel_dropped)
    relationship_arcs = [RelationshipArcEntry(**a) for a in rel_raw]
    narrative_signals = [
        NarrativeSignalEntry(**sig) for sig in build_narrative_signals(
            [{"chapter": s.chapter_number, "characters_present": s.characters_present or [],
              "chapter_purpose": s.chapter_purpose} for s in summaries],
            signal_inputs.load_threads(db, story_id),
            signal_inputs.load_orphaned_hints(db, story_id),
        )
    ]

    report = ManuscriptReport(
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
        relationship_arcs          = relationship_arcs,
        narrative_signals          = narrative_signals,
        generated_at               = datetime.utcnow(),
        is_stale                   = False,
        degraded                   = bool(result.get("degraded", False)),
    )

    try:
        _save_report(story_id, current_user.user_id, report,
                     _source_fingerprint(story_id, db), db)
    except Exception as exc:
        # The author still gets the report they waited for; it just is not
        # saved. Logged by type only (no manuscript content).
        db.rollback()
        logger.error("[manuscript] report could not be saved (%s)", type(exc).__name__)
    return report
