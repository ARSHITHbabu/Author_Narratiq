"""
What a whole-manuscript artefact was built from, as one comparable hash.

Used by the saved Manuscript Report (Stage 5, D2) and the Story Bible (Stage 11,
Phase 2 §19 P2-06 "stale detection"). Both are generated from the story's
indexed chapters, so both record this fingerprint when they are generated and
compare it with the current one when read: if they differ, a chapter was
edited, re-indexed, added or removed since, and the artefact is stale.
"""
from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session

from models import Chapter, ChapterSummary


def chapter_source_fingerprint(story_id: str, db: Session) -> str:
    """Hash of every indexed chapter's id, the chapter's own updated_at, its
    summary's generated_at and stale flag. Any edit, re-index, addition or
    removal changes it. Metadata only: no manuscript text is read."""
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
