"""
Search & Replace router — pure Python regex, no LLM, no Qwen.

Endpoints:
  POST /api/search/exact/{story_id}    — regex search across chapters
  POST /api/search/semantic/{story_id} — BGE-M3 semantic chunk search
  POST /api/search/replace/{story_id}  — find/replace with version snapshot + BGE-M3 re-index

Safety rules enforced here:
  - Exact search and replace use only Python regex (deterministic, no AI).
  - HTML tags are never touched during replace — only text nodes are modified.
  - A StoryVersion snapshot is created before every non-dry-run replace.
  - BGE-M3 chunk re-index is queued as a FastAPI BackgroundTask (non-blocking).
  - Semantic search uses BGE-M3 retrieval only — no replace option exposed.
"""

import re
from html import unescape
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
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

router = APIRouter(tags=["search"])

_CONTEXT_CHARS = 80   # characters of context shown around each match


# ── HTML helpers ──────────────────────────────────────────────────────────────

def _html_to_plain(html: str) -> str:
    """Strip HTML to searchable plain text."""
    text = re.sub(r"</p>|<br\s*/?>|</h[1-6]>", " ", html, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return unescape(re.sub(r"\s+", " ", text)).strip()


def _replace_in_html(
    html: str,
    pattern: re.Pattern,
    replacement: str,
    occurrence_index: int = -1,
) -> tuple[str, int]:
    """
    Replace occurrences of pattern inside HTML text nodes only.
    Tags are never modified.

    occurrence_index:
      -1  → replace all occurrences
       N  → replace only the Nth occurrence (0-based, counted across all text nodes)

    Returns (new_html, count_replaced).
    """
    parts = re.split(r"(<[^>]+>)", html)
    new_parts: list[str] = []

    if occurrence_index < 0:
        total = 0
        for part in parts:
            if part.startswith("<"):
                new_parts.append(part)
            else:
                new_part, n = pattern.subn(lambda _: replacement, part)
                total += n
                new_parts.append(new_part)
        return "".join(new_parts), total

    # Replace only the Nth occurrence across all text nodes
    global_count = 0
    replaced = 0
    for part in parts:
        if part.startswith("<"):
            new_parts.append(part)
            continue
        chars: list[str] = []
        last = 0
        for m in pattern.finditer(part):
            if global_count == occurrence_index:
                chars.append(part[last : m.start()])
                chars.append(replacement)
                last = m.end()
                replaced = 1
            global_count += 1
        chars.append(part[last:])
        new_parts.append("".join(chars))

    return "".join(new_parts), replaced


def _build_pattern(query: str, whole_word: bool, case_sensitive: bool) -> re.Pattern:
    flags = 0 if case_sensitive else re.IGNORECASE
    escaped = re.escape(query)
    pat = rf"\b{escaped}\b" if whole_word else escaped
    return re.compile(pat, flags)


def _search_plain(plain: str, pattern: re.Pattern) -> list[dict]:
    matches = []
    for m in pattern.finditer(plain):
        s, e = m.start(), m.end()
        before = plain[max(0, s - _CONTEXT_CHARS) : s].lstrip()
        after  = plain[e : min(len(plain), e + _CONTEXT_CHARS)].rstrip()
        matches.append({
            "context_before": before,
            "match_text":     m.group(),
            "context_after":  after,
        })
    return matches


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
        print(f"[search] Re-indexed {n} chunk(s) for ch{chapter_number} ({chapter_id[:8]}…)")
    except Exception as exc:
        print(f"[search] BGE-M3 re-index failed for {chapter_id[:8]}…: {exc}")
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

    pattern = _build_pattern(data.query, data.whole_word, data.case_sensitive)
    results: list[ChapterSearchResult] = []
    total = 0

    for ch in chapters:
        if not ch.content:
            continue
        plain   = _html_to_plain(ch.content)
        matches = _search_plain(plain, pattern)
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

    results: list[SemanticResult] = []
    seen_chapters: set[str] = set()
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
        seen_chapters.add(ch.chapter_id)

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

    pattern = _build_pattern(data.query, data.whole_word, data.case_sensitive)
    preview: list[ReplacePreviewItem] = []
    affected: list[Chapter] = []
    total_replaced = 0

    for ch in chapters:
        if not ch.content:
            continue
        plain   = _html_to_plain(ch.content)
        matches = list(pattern.finditer(plain))
        if not matches:
            continue

        # How many will be replaced?
        if data.occurrence_index is not None:
            replace_count = 1 if data.occurrence_index < len(matches) else 0
        else:
            replace_count = len(matches)

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
            # Create version snapshot before replacing
            db.add(
                StoryVersion(
                    chapter_id     = ch.chapter_id,
                    content        = ch.content,
                    version_number = _next_version_number(ch.chapter_id, db),
                    label          = f"Before replace: '{data.query}' → '{data.replacement}'",
                )
            )

            new_content, replaced = _replace_in_html(
                ch.content,
                pattern,
                data.replacement,
                occurrence_index=data.occurrence_index if data.occurrence_index is not None else -1,
            )
            ch.content    = new_content
            ch.word_count = len(_html_to_plain(new_content).split())
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
        print(f"[search] Replace done: {total_replaced} occurrence(s) in {len(affected)} chapter(s). BGE-M3 re-index queued.")
    else:
        total_replaced = sum(p.match_count for p in preview)

    return ReplaceResponse(
        dry_run          = data.dry_run,
        replaced_count   = total_replaced,
        chapters_affected= len(preview),
        preview          = preview,
    )
