"""
Database inputs for the deterministic Stage 5 signal modules (task 5.14).

Keeps services/timeline_signals.py and services/narrative_signals.py pure
(no DB, easy to test) and gives the two consumers — the continuity check
(routers/analysis.py) and the manuscript report (routers/manuscript_report.py)
— one place that decides which Story Intelligence rows are trusted.

Decision H2 (Stage 5 plan review): the ChapterSummary-based modules are the
source. Story Intelligence is consumed only where it adds something the
summaries cannot provide, and only from NON-stale rows:
  - P26 StoryTimelineEvent.is_flashback / is_flashforward → flashback
    suppression for timeline candidates;
  - the P11 foreshadowing registry's orphaned_hints → extra
    setup-without-payoff candidates.
RelationshipIntelligence (P24) is deliberately not consumed: the report's
relationship arcs come from ChapterSummary.relationship_changes only, so
there is one author-facing relationship view, not two that can disagree.
"""
from typing import Optional

from sqlalchemy.orm import Session

from models import NarrativeThread, StoryForeshadowingRegistry, StoryTimelineEvent


def load_threads(db: Session, story_id: str) -> list[dict]:
    rows = db.query(NarrativeThread).filter(NarrativeThread.story_id == story_id).all()
    return [{"name": t.name, "status": t.status, "introduced_chapter": t.introduced_chapter,
             "last_seen_chapter": t.last_seen_chapter} for t in rows]


def load_orphaned_hints(db: Session, story_id: str) -> Optional[list]:
    """None when the registry is absent or stale (stale rows are not trusted)."""
    reg = db.query(StoryForeshadowingRegistry).filter(
        StoryForeshadowingRegistry.story_id == story_id).first()
    if reg is None or reg.is_stale:
        return None
    return reg.orphaned_hints if isinstance(reg.orphaned_hints, list) else None


def load_flash_chapters(db: Session, story_id: str) -> set[int]:
    rows = (
        db.query(StoryTimelineEvent.chapter_number)
        .filter(StoryTimelineEvent.story_id == story_id,
                StoryTimelineEvent.is_stale.isnot(True),
                (StoryTimelineEvent.is_flashback.is_(True)) | (StoryTimelineEvent.is_flashforward.is_(True)))
        .all()
    )
    return {r[0] for r in rows if isinstance(r[0], int)}


def signals_touching(signals: list[dict], chapters: set[int]) -> list[dict]:
    """Signals that cite at least one of `chapters` — for a chunked
    continuity check, each chunk verifies the candidates about its chapters."""
    return [s for s in signals if chapters.intersection(s.get("chapters") or [])]
