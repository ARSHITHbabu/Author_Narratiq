"""
Phase 2 Analysis Router
Handles: P2-01 Emotional Arc Map, P2-05 Continuity Validator,
         P2-08 Style Drift Detector, P2-10 Duplicate Scene Detector
All endpoints are story-scoped and enforce ownership via _get_owned_story().
"""
import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from middleware.rate_limit import limiter, get_user_id
from models import Story, Chapter, ChapterSummary, ChapterChunk, StoryNote, NoteCard, CharacterProfile, Character
from schemas import (
    EmotionalArcEntry, EmotionalArcResponse,
    ContinuityIssue, ContinuityCheckResponse,
    StyleDriftResponse,
    DuplicatePair, DuplicateScenesResponse,
)
from routers.auth import get_current_user, User
from services.ai_service import (
    get_arc_assessment,
    check_continuity,
    describe_style_drift,
    get_bge,
    vector_distance,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analysis"])


def _get_owned_story(story_id: str, user_id: str, db: Session) -> Story:
    story = db.query(Story).filter(
        Story.story_id == story_id,
        Story.user_id  == user_id,
    ).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return story


# ── P2-01: Emotional Arc Map ──────────────────────────────────────────────────

@router.get("/{story_id}/emotional-arc", response_model=EmotionalArcResponse)
@limiter.limit(settings.rate_limit_heavy_ai, key_func=get_user_id)
async def get_emotional_arc(
    request: Request,
    story_id: str,
    include_assessment: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return the chapter-by-chapter emotional tone as an ordered arc.
    Optionally include a Qwen-generated arc assessment paragraph.

    Reads from chapter_summaries.emotional_tone — no new AI calls unless
    include_assessment=true and there are at least 3 chapters.
    """
    _get_owned_story(story_id, current_user.user_id, db)

    rows = (
        db.query(ChapterSummary, Chapter.title)
        .join(Chapter, ChapterSummary.chapter_id == Chapter.chapter_id)
        .filter(ChapterSummary.story_id == story_id)
        .order_by(ChapterSummary.chapter_number)
        .all()
    )

    if not rows:
        return EmotionalArcResponse(
            story_id=story_id,
            chapter_count=0,
            arc=[],
            assessment=None,
        )

    arc = [
        EmotionalArcEntry(
            chapter_number=summary.chapter_number,
            chapter_title=title or f"Chapter {summary.chapter_number}",
            emotional_tone=summary.emotional_tone,
        )
        for summary, title in rows
    ]

    assessment = None
    if include_assessment and len(arc) >= 3:
        arc_dicts = [
            {
                "chapter_number": e.chapter_number,
                "chapter_title":  e.chapter_title,
                "emotional_tone": e.emotional_tone,
            }
            for e in arc
        ]
        assessment = await get_arc_assessment(arc_dicts)

    return EmotionalArcResponse(
        story_id=story_id,
        chapter_count=len(arc),
        arc=arc,
        assessment=assessment,
    )


# ── P2-05: Continuity & World Consistency Validator ──────────────────────────

@router.post("/{story_id}/continuity-check", response_model=ContinuityCheckResponse)
@limiter.limit(settings.rate_limit_heavy_ai, key_func=get_user_id)
async def run_continuity_check(
    request: Request,
    story_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Scan all manuscript data (character profiles, chapter summaries, notes,
    note cards) and identify continuity contradictions.

    For manuscripts > 10 chapters: processes in chunks of 10, merges results,
    deduplicates by description to avoid repeated findings.
    """
    _get_owned_story(story_id, current_user.user_id, db)

    # Gather character profiles
    char_rows = (
        db.query(Character, CharacterProfile)
        .outerjoin(CharacterProfile, Character.character_id == CharacterProfile.character_id)
        .filter(Character.story_id == story_id)
        .all()
    )
    char_profiles = [
        {
            "name":       c.name,
            "appearance": p.appearance if p else "",
            "status":     c.status,
            "goals":      p.goals if p else "",
        }
        for c, p in char_rows
    ]

    # Gather chapter summaries
    summaries = (
        db.query(ChapterSummary)
        .filter(ChapterSummary.story_id == story_id)
        .order_by(ChapterSummary.chapter_number)
        .all()
    )
    if not summaries:
        raise HTTPException(
            status_code=422,
            detail="No indexed chapters found. Index at least one chapter first.",
        )

    summary_dicts = [
        {
            "chapter_number":    s.chapter_number,
            "locations":         s.locations,
            "characters_present": s.characters_present,
            "key_events":        s.key_events,
        }
        for s in summaries
    ]

    # Gather notes (first 200 chars each to stay within context)
    notes = [
        n.content[:200]
        for n in db.query(StoryNote).filter(StoryNote.story_id == story_id).all()
    ]
    cards = [
        c.content[:200]
        for c in db.query(NoteCard).filter(NoteCard.story_id == story_id).all()
    ]

    # Chunked processing for large manuscripts
    chunk_size = 10
    all_issues: list[dict] = []

    degraded = False
    degraded_reason: str | None = None

    if len(summary_dicts) <= chunk_size:
        all_issues, meta = await check_continuity(char_profiles, summary_dicts, notes, cards)
        degraded, degraded_reason = meta.degraded, meta.reason
    else:
        tasks = []
        for i in range(0, len(summary_dicts), chunk_size):
            chunk = summary_dicts[i:i + chunk_size]
            tasks.append(check_continuity(char_profiles, chunk, notes, cards))
        results = await asyncio.gather(*tasks)
        seen_descs: set[str] = set()
        degraded_chunks = 0
        for chunk_issues, meta in results:
            if meta.degraded:
                degraded_chunks += 1
            for issue in chunk_issues:
                key = issue.get("description", "")[:80]
                if key not in seen_descs:
                    seen_descs.add(key)
                    all_issues.append(issue)
        # A failed chunk is a hole in the analysis. Saying "no issues found"
        # while three of four chunks were read is the defect this closes.
        if degraded_chunks:
            degraded = True
            degraded_reason = (
                f"{degraded_chunks} of {len(results)} sections of the manuscript "
                "could not be fully checked. Please run the check again."
            )

    issues = [
        ContinuityIssue(
            type=i.get("type", "continuity_break"),
            description=i.get("description", ""),
            chapter_refs=i.get("chapter_refs", []),
            severity=i.get("severity", "medium"),
            resolution_hint=i.get("resolution_hint", ""),
        )
        for i in all_issues
    ]

    return ContinuityCheckResponse(
        story_id=story_id,
        issues_found=len(issues),
        issues=issues,
        chapters_scanned=len(summaries),
        note=(
            "These are potential inconsistencies for author review — "
            "verify each before revising."
        ),
        degraded=degraded,
        degraded_reason=degraded_reason,
    )


# ── P2-08: Writing Style Drift Detector ──────────────────────────────────────

@router.post("/{story_id}/style-drift", response_model=StyleDriftResponse)
@limiter.limit(settings.rate_limit_heavy_ai, key_func=get_user_id)
async def detect_style_drift(
    request: Request,
    story_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Compute BGE-M3 centroid distance between early and late chapter chunks.
    For manuscripts >= 6 chapters: early = first 3 (or first 25% if > 20),
    late = last 3 (or last 25% if > 20).
    drift_score in [0,1]: 0 = identical style, 1 = maximally different.
    """
    import numpy as np

    _get_owned_story(story_id, current_user.user_id, db)

    # Get chapter count
    chapter_numbers = sorted(set(
        r[0] for r in
        db.query(ChapterChunk.chapter_number)
        .filter(ChapterChunk.story_id == story_id)
        .distinct()
        .all()
    ))

    if len(chapter_numbers) < 6:
        return StyleDriftResponse(
            story_id=story_id,
            status="insufficient_data",
            description="Not enough chapters for style drift analysis.",
            min_chapters_required=6,
            actual_chapters=len(chapter_numbers),
        )

    if len(chapter_numbers) > 20:
        cutoff = max(3, len(chapter_numbers) // 4)
        early_nums = chapter_numbers[:cutoff]
        late_nums  = chapter_numbers[-cutoff:]
    else:
        early_nums = chapter_numbers[:3]
        late_nums  = chapter_numbers[-3:]

    def _fetch_embeddings(chap_nums: list[int]) -> list:
        rows = (
            db.query(ChapterChunk)
            .filter(
                ChapterChunk.story_id == story_id,
                ChapterChunk.chapter_number.in_(chap_nums),
                ChapterChunk.embedding.isnot(None),
            )
            .all()
        )
        return rows

    early_chunks = _fetch_embeddings(early_nums)
    late_chunks  = _fetch_embeddings(late_nums)

    if not early_chunks or not late_chunks:
        return StyleDriftResponse(
            story_id=story_id,
            status="insufficient_data",
            description="Chapter chunks have not been indexed yet. Save chapters to trigger indexing.",
            min_chapters_required=6,
            actual_chapters=len(chapter_numbers),
        )

    # Compute centroids using numpy (not pgvector — centroid arithmetic, not similarity search)
    def _to_array(chunks):
        vecs = []
        for c in chunks:
            if c.embedding is not None:
                arr = list(c.embedding) if not isinstance(c.embedding, list) else c.embedding
                vecs.append(arr)
        return np.array(vecs, dtype=np.float32) if vecs else None

    early_mat = _to_array(early_chunks)
    late_mat  = _to_array(late_chunks)

    if early_mat is None or late_mat is None:
        return StyleDriftResponse(
            story_id=story_id,
            status="insufficient_data",
            description="Embeddings not yet populated for chunk data.",
            min_chapters_required=6,
            actual_chapters=len(chapter_numbers),
        )

    early_centroid = early_mat.mean(axis=0)
    late_centroid  = late_mat.mean(axis=0)

    # Cosine similarity between centroids
    norm_e = np.linalg.norm(early_centroid)
    norm_l = np.linalg.norm(late_centroid)
    if norm_e < 1e-9 or norm_l < 1e-9:
        cosine_sim = 1.0
    else:
        cosine_sim = float(np.dot(early_centroid, late_centroid) / (norm_e * norm_l))
        cosine_sim = max(-1.0, min(1.0, cosine_sim))

    drift_score = round(1.0 - cosine_sim, 4)

    # Find representative passages (chunk closest to its centroid)
    def _closest_chunk(chunks_list, centroid):
        best, best_sim = None, -2.0
        for c in chunks_list:
            if c.embedding is None:
                continue
            v = np.array(list(c.embedding) if not isinstance(c.embedding, list) else c.embedding, dtype=np.float32)
            n = np.linalg.norm(v)
            if n < 1e-9:
                continue
            sim = float(np.dot(v, centroid) / (n * np.linalg.norm(centroid)))
            if sim > best_sim:
                best_sim, best = sim, c
        return best

    sample_early_chunk = _closest_chunk(early_chunks, early_centroid)
    sample_late_chunk  = _closest_chunk(late_chunks, late_centroid)
    sample_early = sample_early_chunk.text[:600] if sample_early_chunk else ""
    sample_late  = sample_late_chunk.text[:600]  if sample_late_chunk  else ""

    DRIFT_THRESHOLD = 0.15
    if drift_score <= DRIFT_THRESHOLD:
        description = "Writing style is consistent throughout the manuscript."
        status = "ok"
    else:
        description = await describe_style_drift(sample_early, sample_late)
        status = "drifted"

    return StyleDriftResponse(
        story_id=story_id,
        status=status,
        drift_score=drift_score,
        early_chapters=early_nums,
        late_chapters=late_nums,
        description=description,
        sample_early=sample_early if drift_score > DRIFT_THRESHOLD else None,
        sample_late=sample_late  if drift_score > DRIFT_THRESHOLD else None,
    )


# ── P2-10: Duplicate Scene Detector ──────────────────────────────────────────

@router.post("/{story_id}/duplicate-scenes", response_model=DuplicateScenesResponse)
@limiter.limit(settings.rate_limit_heavy_ai, key_func=get_user_id)
async def detect_duplicate_scenes(
    request: Request,
    story_id: str,
    threshold: float = Query(default=0.92, ge=0.5, le=1.0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Find chapter pairs with high semantic similarity using pgvector nearest-
    neighbour search on ChapterSummary embeddings (one vector per chapter).

    Uses pgvector ORDER BY <=> LIMIT per chapter instead of O(n²) pairwise
    comparison. Caps at 50 pairs. Returns sorted by similarity descending.
    """
    _get_owned_story(story_id, current_user.user_id, db)

    summaries = (
        db.query(ChapterSummary, Chapter.title, Chapter.content)
        .join(Chapter, ChapterSummary.chapter_id == Chapter.chapter_id)
        .filter(
            ChapterSummary.story_id == story_id,
            ChapterSummary.embedding.isnot(None),
        )
        .order_by(ChapterSummary.chapter_number)
        .all()
    )

    if len(summaries) < 2:
        return DuplicateScenesResponse(
            story_id=story_id,
            threshold=threshold,
            pairs_found=0,
            pairs=[],
        )

    # Build lookup: chapter_number → (summary, title, content)
    by_num = {
        s.chapter_number: (s, t, c)
        for s, t, c in summaries
    }

    seen_pairs: set[tuple[int, int]] = set()
    pairs: list[DuplicatePair] = []

    # For each chapter, find nearest neighbours via pgvector
    for summary, title, content in summaries:
        if summary.embedding is None:
            continue
        vec_str = "[" + ",".join(str(float(v)) for v in summary.embedding) + "]"

        # Query all other chapters by cosine distance
        sql = text(
            "SELECT cs.chapter_number, "
            "       1 - (cs.embedding <=> CAST(:vec AS vector)) AS similarity "
            "FROM chapter_summaries cs "
            "WHERE cs.story_id = :sid "
            "  AND cs.chapter_number != :self_num "
            "  AND cs.embedding IS NOT NULL "
            "ORDER BY cs.embedding <=> CAST(:vec AS vector) "
            "LIMIT 5"
        )
        rows = db.execute(sql, {
            "vec":      vec_str,
            "sid":      story_id,
            "self_num": summary.chapter_number,
        }).fetchall()

        for row in rows:
            other_num = row[0]
            sim = float(row[1])
            if sim < threshold:
                continue
            pair_key = (min(summary.chapter_number, other_num),
                        max(summary.chapter_number, other_num))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)
            if len(pairs) >= 50:
                break

            a_num, b_num = pair_key
            a_sum, a_title, a_content = by_num.get(a_num, (None, "", ""))
            b_sum, b_title, b_content = by_num.get(b_num, (None, "", ""))

            pairs.append(DuplicatePair(
                chapter_a=a_num,
                chapter_b=b_num,
                a_title=a_title or f"Chapter {a_num}",
                b_title=b_title or f"Chapter {b_num}",
                similarity_score=round(sim, 4),
                a_snippet=(a_content or "")[:200],
                b_snippet=(b_content or "")[:200],
            ))

        if len(pairs) >= 50:
            break

    # Sort by similarity descending
    pairs.sort(key=lambda p: p.similarity_score, reverse=True)

    return DuplicateScenesResponse(
        story_id=story_id,
        threshold=threshold,
        pairs_found=len(pairs),
        pairs=pairs,
    )
