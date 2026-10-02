"""
Search & Replace router — pure Python regex, no LLM, no Qwen.

Endpoints:
  POST /api/search/exact/{story_id}    — regex search across chapters
  POST /api/search/semantic/{story_id} — BGE-M3 semantic chunk search
  POST /api/search/replace/{story_id}  — find/replace with version snapshot + BGE-M3 re-index

Safety rules enforced here:
  - Exact search and replace use only deterministic regex matching (no AI).
  - Count, preview, Replace One and Replace All share ONE text model
    (services/search_match.py, mirrored by frontend/lib/searchMatch.ts), so the
    number shown, the number previewed and the number replaced always agree
    (Stage 12 remediation A9).
  - HTML tags are never touched during replace; the replacement is escaped as
    author text; entities outside the match are never altered. Every write is
    checked to keep the chapter's tag sequence identical, or nothing is saved.
  - A StoryVersion snapshot is created before every non-dry-run replace.
  - BGE-M3 chunk re-index is queued as a FastAPI BackgroundTask (non-blocking).
  - Semantic search uses BGE-M3 retrieval only — no replace option exposed.
"""

import re
from html import unescape

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from services import search_match
from models import Chapter, Story, StoryVersion
from routers.auth import User, get_current_user
from schemas import (
    ChapterSearchResult,
    ExactSearchRequest,
    ExactSearchResponse,
    ReplacePreviewItem,
    ReplaceRequest,
    ReplaceResponse,
    SearchMatchContext,
    SemanticResult,
    SemanticSearchRequest,
    SemanticSearchResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["search"])

_CONTEXT_CHARS = 80   # characters of context shown around each match
_TAG_SEQ = re.compile(r"<!--.*?-->|<[^>]*>", re.S)


# ── HTML helpers ──────────────────────────────────────────────────────────────

def _html_to_plain(html: str) -> str:
    """Strip HTML to searchable plain text."""
    text = re.sub(r"</p>|<br\s*/?>|</h[1-6]>", " ", html, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return unescape(re.sub(r"\s+", " ", text)).strip()


def _next_version_number(chapter_id: str, db: Session) -> int:
    max_ver = (
        db.query(func.max(StoryVersion.version_number))
        .filter(StoryVersion.chapter_id == chapter_id)
        .scalar()
    )
    return (max_ver or 0) + 1


# ── BGE-M3 background re-index ────────────────────────────────────────────────

async def _reindex_chapter_chunks(
    chapter_id: str,
    story_id: str,
    chapter_number: int,
    content_html: str,
) -> None:
    """
    Chunks-only BGE-M3 re-index after a replace operation.
    Skips Qwen summary regeneration (10× faster; summary stays accurate
    unless a chapter's plot changed, which a text replace doesn't do).
    """
    from database import SessionLocal
    from services.ai_service import _html_to_plain as ai_plain, embed_and_store_chunks

    db = SessionLocal()
    try:
        plain = ai_plain(content_html)
        n = await embed_and_store_chunks(chapter_id, story_id, chapter_number, plain, db)
        logger.info(f"[search] Re-indexed {n} chunk(s) for ch{chapter_number} ({chapter_id[:8]}…)")
    except Exception as exc:
        logger.warning(f"[search] BGE-M3 re-index failed for {chapter_id[:8]}…: {exc}")
    finally:
        db.close()


# ── Story access guard ────────────────────────────────────────────────────────

def _check_story(story_id: str, user_id: str, db: Session) -> Story:
    story = (
        db.query(Story)
        .filter(Story.story_id == story_id, Story.user_id == user_id)
        .first()
    )
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return story


# ── Exact Search ──────────────────────────────────────────────────────────────

@router.post("/exact/{story_id}", response_model=ExactSearchResponse)
def exact_search(
    story_id: str,
    data: ExactSearchRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_story(story_id, current_user.user_id, db)

    if not data.query or not data.query.strip():
        return ExactSearchResponse(query=data.query, total_matches=0, chapters_hit=0, results=[])

    q = db.query(Chapter).filter(Chapter.story_id == story_id)
    if data.chapter_ids:
        q = q.filter(Chapter.chapter_id.in_(data.chapter_ids))
    chapters = q.order_by(Chapter.chapter_number).all()

    results: list[ChapterSearchResult] = []
    total = 0

    for ch in chapters:
        if not ch.content:
            continue
        matches = [
            {"context_before": m.context_before, "match_text": m.text, "context_after": m.context_after}
            for m in search_match.find_matches(ch.content, data.query, data.whole_word, data.case_sensitive)
        ]
        if not matches:
            continue
        total += len(matches)
        results.append(
            ChapterSearchResult(
                chapter_id    = ch.chapter_id,
                chapter_number= ch.chapter_number,
                chapter_title = ch.title or f"Chapter {ch.chapter_number}",
                match_count   = len(matches),
                matches       = [SearchMatchContext(**m) for m in matches],
            )
        )

    return ExactSearchResponse(
        query         = data.query,
        total_matches = total,
        chapters_hit  = len(results),
        results       = results,
    )


# ── Semantic Search ───────────────────────────────────────────────────────────

@router.post("/semantic/{story_id}", response_model=SemanticSearchResponse)
async def semantic_search(
    story_id: str,
    data: SemanticSearchRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_story(story_id, current_user.user_id, db)

    if not data.query or not data.query.strip():
        return SemanticSearchResponse(query=data.query, results=[])

    from services.ai_service import retrieve_chunks_from_store

    chunks = await retrieve_chunks_from_store(data.query, story_id, db, top_k=data.top_k)
    if not chunks:
        return SemanticSearchResponse(query=data.query, results=[])

    chapter_map = {
        ch.chapter_number: ch
        for ch in db.query(Chapter).filter(Chapter.story_id == story_id).all()
    }

    # De-duplication across near-identical overlapping chunks (task 4.13) now
    # happens inside retrieve_chunks_from_store itself, so every result here
    # is already content-distinct — nothing further to filter.
    results: list[SemanticResult] = []
    for c in chunks:
        ch = chapter_map.get(c["chapter"])
        if not ch:
            continue
        results.append(
            SemanticResult(
                chapter_id    = ch.chapter_id,
                chapter_number= ch.chapter_number,
                chapter_title = ch.title or f"Chapter {ch.chapter_number}",
                chunk_text    = c["text"],
                score         = c["score"],
            )
        )

    return SemanticSearchResponse(query=data.query, results=results)


# ── Replace ───────────────────────────────────────────────────────────────────

@router.post("/replace/{story_id}", response_model=ReplaceResponse)
async def replace_in_story(
    story_id: str,
    data: ReplaceRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_story(story_id, current_user.user_id, db)

    if not data.query or not data.query.strip():
        raise HTTPException(status_code=400, detail="Search query cannot be empty")

    q = db.query(Chapter).filter(Chapter.story_id == story_id)
    if data.chapter_ids:
        q = q.filter(Chapter.chapter_id.in_(data.chapter_ids))
    chapters = q.order_by(Chapter.chapter_number).all()

    preview: list[ReplacePreviewItem] = []
    affected: list[Chapter] = []
    total_replaced = 0

    for ch in chapters:
        if not ch.content:
            continue
        found = search_match.find_matches(ch.content, data.query, data.whole_word, data.case_sensitive)
        if not found:
            continue

        # How many will be replaced? The same enumeration the editor highlights.
        if data.occurrence_index is not None:
            replace_count = 1 if 0 <= data.occurrence_index < len(found) else 0
        else:
            replace_count = len(found)

        if replace_count == 0:
            continue

        preview.append(
            ReplacePreviewItem(
                chapter_id    = ch.chapter_id,
                chapter_number= ch.chapter_number,
                chapter_title = ch.title or f"Chapter {ch.chapter_number}",
                match_count   = replace_count,
            )
        )

        if not data.dry_run:
            new_content, replaced = search_match.replace(
                ch.content, data.query, data.replacement,
                whole_word=data.whole_word, case_sensitive=data.case_sensitive,
                occurrence_index=data.occurrence_index,
            )
            # Integrity guard: replace only ever edits text between tags. If the
            # tag sequence changed, or fewer occurrences were rewritten than
            # previewed, something is wrong — save nothing anywhere.
            if _TAG_SEQ.findall(new_content) != _TAG_SEQ.findall(ch.content) or replaced != replace_count:
                db.rollback()
                logger.error("[search] replace integrity check failed: chapter=%s expected=%d got=%d",
                             ch.chapter_id[:8], replace_count, replaced)
                raise HTTPException(
                    status_code=500,
                    detail="The replacement could not be applied safely, so nothing was changed. "
                           "Your text is exactly as it was.",
                )
            # Version snapshot before the change (kept from the original design).
            db.add(
                StoryVersion(
                    chapter_id     = ch.chapter_id,
                    content        = ch.content,
                    version_number = _next_version_number(ch.chapter_id, db),
                    label          = f"Before replace: '{data.query}' → '{data.replacement}'",
                )
            )
            ch.content    = new_content
            ch.word_count = search_match.plain_word_count(new_content)
            total_replaced += replaced
            affected.append(ch)

    if not data.dry_run and affected:
        db.commit()
        for ch in affected:
            background_tasks.add_task(
                _reindex_chapter_chunks,
                ch.chapter_id,
                story_id,
                ch.chapter_number,
                ch.content,
            )
        logger.debug(f"[search] Replace done: {total_replaced} occurrence(s) in {len(affected)} chapter(s). BGE-M3 re-index queued.")
    else:
        total_replaced = sum(p.match_count for p in preview)

    return ReplaceResponse(
        dry_run          = data.dry_run,
        replaced_count   = total_replaced,
        chapters_affected= len(preview),
        preview          = preview,
    )
