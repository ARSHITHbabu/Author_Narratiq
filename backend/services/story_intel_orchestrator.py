"""
Story Intelligence Orchestrator — dependency-aware pass runner.

Pass dependency graph (each pass requires prior passes to be complete):
  P01 → (none)
  P02 → (none)
  P03 → P01
  P04 → P02
  P05 → P02
  P06 → P02
  P07 → P02
  P08–P12 → (none, per-chapter)
  P13 → P08
  P14 → P09
  P15 → P05, P10
  P16 → P06, P12
  P17 → P07, P11, P12
  P18 → P01–P07
  P19 → P08–P17
  P20 → P03, P01
  P21 → P07, P19
  P22 → P18, P19
  P23 → P08–P12 (uses character mentions from chapter processing)
  P24 → P23
  P25 → P22, P23, P24
  P26 → P08–P12 (uses chapter content)
  P27 → P26
  P28 → P23, P24, P25, P26
  P29 → P25, P28

Entry point: run_full_analysis(story_id, db, passes=None, force_refresh=False, job_id=None)
"""
import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from sqlalchemy.orm import Session

from models import (
    Chapter, Character, CharacterRelationship, Story, StoryIntelJob, gen_uuid,
)
from services.story_intel_service import (
    _analyze_chapter_batch,
    build_integration_context,
    run_p01_genre_hierarchy,
    run_p02_story_dna,
    run_p03_audience_profile,
    run_p04_themes,
    run_p05_conflicts,
    run_p06_world_profile,
    run_p07_narrative_structure,
    run_p13_emotional_arc,
    run_p14_pacing,
    run_p15_conflict_evolution,
    run_p16_world_synth,
    run_p17_structure_synth,
    run_p18_strength_indicators,
    run_p19_risk_register,
    run_p20_market_analysis,
    run_p21_series_potential,
    run_p22_overall_synthesis,
    run_p23_character_intel,
    run_p24_relationship_intel,
    run_p25_memory_consolidation,
    run_p26_timeline,
    run_p27_timeline_contradictions,
    run_p28_graph_population,
)

logger = logging.getLogger(__name__)

ALL_PASSES = [
    "P01", "P02", "P03", "P04", "P05", "P06", "P07",
    "P08", "P09", "P10", "P11", "P12",
    "P13", "P14", "P15", "P16", "P17",
    "P18", "P19", "P20", "P21", "P22",
    "P23", "P24", "P25", "P26", "P27", "P28", "P29",
]


def _update_job(db: Session, job_id: Optional[str], **kwargs) -> None:
    if not job_id:
        return
    job = db.query(StoryIntelJob).filter_by(job_id=job_id).first()
    if job:
        for k, v in kwargs.items():
            setattr(job, k, v)
        job.updated_at = datetime.utcnow()
        db.commit()


async def run_full_analysis(
    story_id: str,
    db: Session,
    passes: Optional[List[str]] = None,
    force_refresh: bool = False,
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute all requested intelligence passes in dependency order.
    Updates job progress via StoryIntelJob if job_id is provided.
    Returns a summary dict of results.
    """
    if passes is None:
        passes = ALL_PASSES
    passes_set: Set[str] = set(passes)

    story = db.query(Story).filter_by(story_id=story_id).first()
    if not story:
        raise ValueError(f"Story {story_id} not found")

    completed: List[str] = []
    failed: List[str] = []
    results: Dict[str, Any] = {}

    total = len(passes_set)

    def _pct(done: int) -> int:
        return int(done / total * 100) if total else 100

    def _progress(pass_code: str) -> None:
        _update_job(db, job_id,
                    current_pass=pass_code,
                    passes_completed=completed,
                    passes_failed=failed,
                    percent=_pct(len(completed) + len(failed)),
                    status="running")

    async def _run(pass_code: str, coro) -> Any:
        _progress(pass_code)
        try:
            result = await coro
            completed.append(pass_code)
            results[pass_code] = result
            db.commit()
            logger.info(f"[intel] {pass_code} ✓ story={story_id}")
            return result
        except Exception as e:
            failed.append(pass_code)
            db.rollback()
            logger.error(f"[intel] {pass_code} ✗ story={story_id}: {e}")
            return None

    _update_job(db, job_id, status="running", current_pass="P01",
                passes_requested=list(passes_set), percent=0)

    # ── Foundation passes (independent) ──────────────────────────────────────
    if "P01" in passes_set:
        await _run("P01", run_p01_genre_hierarchy(db, story))
    if "P02" in passes_set:
        await _run("P02", run_p02_story_dna(db, story))

    # ── Derived from foundation ───────────────────────────────────────────────
    if "P03" in passes_set:
        await _run("P03", run_p03_audience_profile(db, story))
    if "P04" in passes_set:
        await _run("P04", run_p04_themes(db, story))
    if "P05" in passes_set:
        await _run("P05", run_p05_conflicts(db, story))
    if "P06" in passes_set:
        await _run("P06", run_p06_world_profile(db, story))
    if "P07" in passes_set:
        await _run("P07", run_p07_narrative_structure(db, story))

    # ── Per-chapter passes (P08–P12 batched) ─────────────────────────────────
    chapter_data: List[Dict[str, Any]] = []
    chapters = sorted(story.chapters, key=lambda c: c.chapter_number)

    per_chapter_passes = {"P08", "P09", "P10", "P11", "P12"}
    if per_chapter_passes & passes_set and chapters:
        _update_job(db, job_id, current_pass="P08-P12", percent=_pct(len(completed)))
        for chapter in chapters:
            try:
                data = await _analyze_chapter_batch(chapter)
                chapter_data.append(data)
                logger.info(f"[intel] P08-P12 ch{chapter.chapter_number} ✓")
            except Exception as e:
                logger.warning(f"[intel] P08-P12 ch{chapter.chapter_number} ✗: {e}")
                chapter_data.append({"chapter_number": chapter.chapter_number})
        for code in ["P08", "P09", "P10", "P11", "P12"]:
            if code in passes_set:
                completed.append(code)
        db.commit()

    # ── Synthesis passes ──────────────────────────────────────────────────────
    if "P13" in passes_set and chapter_data:
        await _run("P13", run_p13_emotional_arc(db, story, chapter_data))
    if "P14" in passes_set and chapter_data:
        await _run("P14", run_p14_pacing(db, story, chapter_data))
    if "P15" in passes_set and chapter_data:
        await _run("P15", run_p15_conflict_evolution(db, story, chapter_data))
    if "P16" in passes_set and chapter_data:
        await _run("P16", run_p16_world_synth(db, story, chapter_data))
    if "P17" in passes_set and chapter_data:
        await _run("P17", run_p17_structure_synth(db, story, chapter_data))

    # ── Strength and risk ─────────────────────────────────────────────────────
    if "P18" in passes_set:
        await _run("P18", run_p18_strength_indicators(db, story))
    if "P19" in passes_set:
        await _run("P19", run_p19_risk_register(db, story, chapter_data))

    # ── Market and series ─────────────────────────────────────────────────────
    if "P20" in passes_set:
        await _run("P20", run_p20_market_analysis(db, story))
    if "P21" in passes_set:
        await _run("P21", run_p21_series_potential(db, story))

    # ── Overall synthesis ─────────────────────────────────────────────────────
    if "P22" in passes_set:
        await _run("P22", run_p22_overall_synthesis(db, story))

    # ── V2: Character intelligence ────────────────────────────────────────────
    if "P23" in passes_set and story.characters:
        _update_job(db, job_id, current_pass="P23", percent=_pct(len(completed)))
        for char in story.characters:
            try:
                result = await run_p23_character_intel(db, story, char)
                logger.info(f"[intel] P23 char={char.name} ✓")
                db.commit()
            except Exception as e:
                logger.warning(f"[intel] P23 char={char.name} ✗: {e}")
                db.rollback()
        completed.append("P23")

    # ── V2: Relationship intelligence ─────────────────────────────────────────
    if "P24" in passes_set and story.character_relationships:
        _update_job(db, job_id, current_pass="P24", percent=_pct(len(completed)))
        for rel in story.character_relationships:
            try:
                await run_p24_relationship_intel(db, story, rel)
                logger.info(f"[intel] P24 rel={rel.relationship_id} ✓")
                db.commit()
            except Exception as e:
                logger.warning(f"[intel] P24 rel={rel.relationship_id} ✗: {e}")
                db.rollback()
        completed.append("P24")

    # ── V2: Memory consolidation ──────────────────────────────────────────────
    if "P25" in passes_set:
        try:
            _update_job(db, job_id, current_pass="P25", percent=_pct(len(completed)))
            count = await run_p25_memory_consolidation(db, story)
            db.commit()
            completed.append("P25")
            results["P25"] = {"memory_entries_written": count}
            logger.info(f"[intel] P25 ✓ {count} memory entries")
        except Exception as e:
            db.rollback()
            failed.append("P25")
            logger.error(f"[intel] P25 ✗: {e}")

    # ── V2: Timeline ──────────────────────────────────────────────────────────
    if "P26" in passes_set:
        await _run("P26", run_p26_timeline(db, story))
    if "P27" in passes_set:
        await _run("P27", run_p27_timeline_contradictions(db, story))

    # ── V2: Graph population ──────────────────────────────────────────────────
    if "P28" in passes_set:
        try:
            _update_job(db, job_id, current_pass="P28", percent=_pct(len(completed)))
            nc, ec = await run_p28_graph_population(db, story)
            db.commit()
            completed.append("P28")
            results["P28"] = {"node_count": nc, "edge_count": ec}
            logger.info(f"[intel] P28 ✓ nodes={nc} edges={ec}")
        except Exception as e:
            db.rollback()
            failed.append("P28")
            logger.error(f"[intel] P28 ✗: {e}")

    # ── V2: Integration context ───────────────────────────────────────────────
    if "P29" in passes_set:
        try:
            _update_job(db, job_id, current_pass="P29", percent=_pct(len(completed)))
            ctx = await build_integration_context(db, story_id)
            completed.append("P29")
            results["P29"] = ctx
            logger.info(f"[intel] P29 ✓")
        except Exception as e:
            failed.append("P29")
            logger.error(f"[intel] P29 ✗: {e}")

    # ── Finalise ──────────────────────────────────────────────────────────────
    final_status = "complete" if not failed else "complete_with_errors"
    _update_job(db, job_id,
                status=final_status,
                passes_completed=completed,
                passes_failed=failed,
                current_pass="",
                percent=100)

    return {
        "status": final_status,
        "passes_completed": completed,
        "passes_failed": failed,
        "story_id": story_id,
    }


async def run_analysis_background(
    story_id: str,
    user_id: str,
    triggered_by: str = "manual",
    passes: Optional[List[str]] = None,
    force_refresh: bool = False,
) -> str:
    """
    Create a job record and launch the analysis as a background asyncio task.
    Returns the job_id immediately.
    """
    from database import SessionLocal

    db = SessionLocal()
    try:
        job = StoryIntelJob(
            job_id=gen_uuid(),
            story_id=story_id,
            user_id=user_id,
            status="pending",
            triggered_by=triggered_by,
            passes_requested=passes or ALL_PASSES,
        )
        db.add(job)
        db.commit()
        job_id = job.job_id
    finally:
        db.close()

    async def _worker():
        from middleware.concurrency import bg_ai_semaphore
        from exceptions import AIServiceUnavailableError
        worker_db = SessionLocal()
        try:
            async with bg_ai_semaphore():
                await run_full_analysis(
                    story_id=story_id,
                    db=worker_db,
                    passes=passes,
                    force_refresh=force_refresh,
                    job_id=job_id,
                )
        except AIServiceUnavailableError as exc:
            logger.warning("[intel_worker] AI unavailable for story=%s: %s", story_id[:8], exc)
            _update_job(worker_db, job_id, status="error", error_message="AI temporarily unavailable — please retry")
            worker_db.commit()
        except Exception as e:
            logger.error("[intel_worker] unhandled error story=%s: %s", story_id[:8], e)
            _update_job(worker_db, job_id, status="error", error_message=str(e))
            worker_db.commit()
        finally:
            worker_db.close()

    asyncio.create_task(_worker())
    return job_id
