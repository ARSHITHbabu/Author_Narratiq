import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from middleware.rate_limit import limiter, get_user_id
from schemas import (
    TransformRequest, ToneRequest, EmotionRequest, AgeAdaptRequest,
    StyleRequest, TranslationRequest, TransformResponse, SuggestionRequest, SuggestionsResponse,
    AuthorStyleRequest, AuthorStyleOption, AuthorStyleCatalog,
    AiLimitsOut, CompareSummaryRequest, CompareSummaryOut, MergeRequest, MergeOut,
)
from routers.auth import get_current_user, User
from services import ai_service
from services.genre_context import build_genre_context
from services.ownership import owned_story_or_none, owned_chapter_or_none, owned_story
from exceptions import ApiError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ai-transform"])


def _genre_ctx(story_id: Optional[str], db: Session) -> str:
    """Resolve the genre-profile context for a story (or "" when none/absent).
    Callers pass only a story_id that _owned_story_id() has already verified."""
    if not story_id:
        return ""
    try:
        return build_genre_context(story_id, db)
    except Exception:  # never let context lookup break a transform
        return ""


def _owned_story_id(story_id: Optional[str], user: User, db: Session) -> Optional[str]:
    """Stage 7 (C7-6): every /api/ai endpoint that accepts a story_id reads
    story data with it (genre profile, character names, manuscript passages).
    Before this, any signed-in user could pass another author's story_id and
    have that author's data injected into their own prompt. A foreign and a
    non-existent story_id now both return the same 404."""
    story = owned_story_or_none(story_id, user.user_id, db)
    return story.story_id if story is not None else None


async def _phase3(data, *, tool: str, user: User, db: Session, text: str):
    """Build the Phase 3 context when the client sent `controls`; None keeps
    the exact Stage 5 behaviour. Returns (p3_context_or_None, text_to_use)."""
    controls = getattr(data, "controls", None)
    if controls is None:
        return None, text
    if not data.story_id:
        raise ApiError(422, "Story-aware options need an open story.", code="story_required")
    story = owned_story(data.story_id, user.user_id, db)
    chapter = owned_chapter_or_none(getattr(data, "chapter_id", None), story.story_id, user.user_id, db)
    if controls.base_pin_id and getattr(data, "locked_ranges", None):
        raise ApiError(422, "Sentence locks apply to your selected text, not to a saved version. "
                            "Clear the locks to generate from a saved version.", code="locks_with_base_version")
    from services.generation_context import build_generation_context
    p3 = await build_generation_context(story=story, chapter=chapter, source_text=text, tool=tool,
                                        controls=controls, user=user, db=db)
    return p3, (p3.source_draft if p3.source_draft is not None else text)


def _response(data_text: str, mode: str, tokens: int, result: dict) -> TransformResponse:
    return TransformResponse(
        original=data_text, transformed=result["transformed"], mode=mode, tokens_used=tokens,
        no_change=result.get("no_change", False), reason=result.get("reason"),
        strength_violation=result.get("strength_violation", False),
        preservation_violations=result.get("preservation_violations", []),
        failed=result.get("failed", False), warnings=result.get("warnings", []),
        context_used=result.get("context_used", {}), name_autofix=result.get("name_autofix", []),
    )


def _validate_locks(data, text: str) -> None:
    from services.transform_preservation import validate_locked_ranges
    validate_locked_ranges(text, _locked_range_dicts(data))


def _sse_stream(async_gen):
    """Wrap an async generator of tokens into an SSE StreamingResponse."""
    async def _generate():
        async for token in async_gen:
            yield f"data: {json.dumps({'token': token, 'done': False})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


# ── Refine ────────────────────────────────────────────────────────────────────

@router.post("/refine", response_model=TransformResponse)
@limiter.limit(settings.rate_limit_realtime_ai, key_func=get_user_id)
async def refine(request: Request, data: TransformRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    story_id = _owned_story_id(data.story_id, current_user, db)
    result = await ai_service.refine_text(data.text, data.mode or "standard", genre_context=_genre_ctx(story_id, db))
    return TransformResponse(original=data.text, transformed=result,
                             mode=data.mode or "standard", tokens_used=len(data.text.split()) * 2)


@router.post("/refine/stream")
@limiter.limit(settings.rate_limit_realtime_ai, key_func=get_user_id)
async def refine_stream(request: Request, data: TransformRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    story_id = _owned_story_id(data.story_id, current_user, db)
    return _sse_stream(ai_service.stream_refine(data.text, data.mode or "standard", genre_context=_genre_ctx(story_id, db)))


# ── Tone ──────────────────────────────────────────────────────────────────────

def _locked_range_dicts(data) -> Optional[list]:
    ranges = getattr(data, "locked_ranges", None)
    return [{"start": r.start, "end": r.end} for r in ranges] if ranges else None


@router.post("/tone", response_model=TransformResponse)
@limiter.limit(settings.rate_limit_realtime_ai, key_func=get_user_id)
async def tone_transform(request: Request, data: ToneRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    story_id = _owned_story_id(data.story_id, current_user, db)
    p3, text = await _phase3(data, tool="tone", user=current_user, db=db, text=data.text)
    _validate_locks(data, text)
    result = await ai_service.transform_tone(
        text, data.tone, genre_context=_genre_ctx(story_id, db),
        story_id=story_id, db=db,
        strength=data.strength or "light", locked_ranges=_locked_range_dicts(data), p3=p3,
    )
    return _response(data.text, f"tone:{data.tone}", len(text.split()) * 2, result)


@router.post("/tone/stream")
@limiter.limit(settings.rate_limit_realtime_ai, key_func=get_user_id)
async def tone_stream(request: Request, data: ToneRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    story_id = _owned_story_id(data.story_id, current_user, db)
    return _sse_stream(ai_service.stream_tone(data.text, data.tone, genre_context=_genre_ctx(story_id, db)))


# ── Emotion ───────────────────────────────────────────────────────────────────

@router.post("/emotion", response_model=TransformResponse)
@limiter.limit(settings.rate_limit_realtime_ai, key_func=get_user_id)
async def emotion_rewrite(request: Request, data: EmotionRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    story_id = _owned_story_id(data.story_id, current_user, db)
    p3, text = await _phase3(data, tool="emotion", user=current_user, db=db, text=data.text)
    result = await ai_service.rewrite_emotion(
        text, data.emotion, data.intensity or "medium", genre_context=_genre_ctx(story_id, db),
        story_id=story_id, db=db, p3=p3,
    )
    return _response(data.text, f"emotion:{data.emotion}", len(text.split()) * 2, result)


@router.post("/emotion/stream")
@limiter.limit(settings.rate_limit_realtime_ai, key_func=get_user_id)
async def emotion_stream(request: Request, data: EmotionRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    story_id = _owned_story_id(data.story_id, current_user, db)
    return _sse_stream(ai_service.stream_emotion(data.text, data.emotion, data.intensity or "medium", genre_context=_genre_ctx(story_id, db)))


# ── Age adapt ─────────────────────────────────────────────────────────────────

@router.post("/age-adapt", response_model=TransformResponse)
@limiter.limit(settings.rate_limit_realtime_ai, key_func=get_user_id)
async def age_adapt(request: Request, data: AgeAdaptRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    story_id = _owned_story_id(data.story_id, current_user, db)
    p3, text = await _phase3(data, tool="age_adapt", user=current_user, db=db, text=data.text)
    _validate_locks(data, text)
    result = await ai_service.adapt_for_age(
        text, data.target_age, genre_context=_genre_ctx(story_id, db),
        story_id=story_id, db=db,
        strength=data.strength or "light", locked_ranges=_locked_range_dicts(data), p3=p3,
    )
    return _response(data.text, f"age:{data.target_age}", len(text.split()) * 2, result)


@router.post("/age-adapt/stream")
@limiter.limit(settings.rate_limit_realtime_ai, key_func=get_user_id)
async def age_adapt_stream(request: Request, data: AgeAdaptRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    story_id = _owned_story_id(data.story_id, current_user, db)
    return _sse_stream(ai_service.stream_age_adapt(data.text, data.target_age, genre_context=_genre_ctx(story_id, db)))


# ── Style ─────────────────────────────────────────────────────────────────────

@router.post("/style", response_model=TransformResponse)
@limiter.limit(settings.rate_limit_realtime_ai, key_func=get_user_id)
async def style_transform(request: Request, data: StyleRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    story_id = _owned_story_id(data.story_id, current_user, db)
    p3, text = await _phase3(data, tool="style", user=current_user, db=db, text=data.text)
    _validate_locks(data, text)
    result = await ai_service.transform_style(
        text, data.style, genre_context=_genre_ctx(story_id, db),
        story_id=story_id, db=db,
        strength=data.strength or "light", locked_ranges=_locked_range_dicts(data), p3=p3,
    )
    return _response(data.text, f"style:{data.style}", len(text.split()) * 2, result)


@router.post("/style/stream")
@limiter.limit(settings.rate_limit_realtime_ai, key_func=get_user_id)
async def style_stream(request: Request, data: StyleRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    story_id = _owned_story_id(data.story_id, current_user, db)
    return _sse_stream(ai_service.stream_style(data.text, data.style, genre_context=_genre_ctx(story_id, db)))


# ── Author-Inspired Style ───────────────────────────────────────────────────────

def _validate_transform_text(text: str) -> str:
    """Shared guard for selection transforms — non-empty, length-capped."""
    cleaned = (text or "").strip()
    if not cleaned:
        raise HTTPException(status_code=422, detail="No text provided to transform.")
    if len(cleaned) > 8000:
        raise HTTPException(status_code=422, detail="Selection too long (max 8000 characters). Select a smaller passage.")
    return cleaned


@router.get("/author-styles", response_model=AuthorStyleCatalog)
async def author_styles(current_user: User = Depends(get_current_user)):
    """Server-authoritative catalog of selectable author/style influences."""
    options = [AuthorStyleOption(**o) for o in ai_service.author_style_catalog()]
    return AuthorStyleCatalog(
        options=options,
        note=(
            "Named authors are public-domain only. Living or in-copyright author "
            "requests are mapped to safe generic styles. Output is inspired-by, "
            "never a copy."
        ),
    )


@router.post("/author-style", response_model=TransformResponse)
@limiter.limit(settings.rate_limit_realtime_ai, key_func=get_user_id)
async def author_style_transform(request: Request, data: AuthorStyleRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    text = _validate_transform_text(data.text)
    story_id = _owned_story_id(data.story_id, current_user, db)
    result = await ai_service.rewrite_in_author_style(text, data.author, genre_context=_genre_ctx(story_id, db))
    return TransformResponse(original=data.text, transformed=result,
                             mode=f"author:{data.author}", tokens_used=len(text.split()) * 2)


@router.post("/author-style/stream")
@limiter.limit(settings.rate_limit_realtime_ai, key_func=get_user_id)
async def author_style_stream(request: Request, data: AuthorStyleRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    text = _validate_transform_text(data.text)
    story_id = _owned_story_id(data.story_id, current_user, db)
    return _sse_stream(ai_service.stream_author_style(text, data.author, genre_context=_genre_ctx(story_id, db)))


# ── Translate ─────────────────────────────────────────────────────────────────

@router.post("/translate", response_model=TransformResponse)
@limiter.limit(settings.rate_limit_realtime_ai, key_func=get_user_id)
async def translate(request: Request, data: TranslationRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    story_id = _owned_story_id(data.story_id, current_user, db)
    result = await ai_service.translate_text(
        data.text, data.target_language, data.source_language or "en",
        story_id=story_id, db=db,
    )
    return TransformResponse(original=data.text, transformed=result["transformed"],
                             mode=f"translate:{data.target_language}", tokens_used=len(data.text.split()) * 3,
                             preservation_violations=result["preservation_violations"])


@router.post("/translate/stream")
@limiter.limit(settings.rate_limit_realtime_ai, key_func=get_user_id)
async def translate_stream(request: Request, data: TranslationRequest, current_user: User = Depends(get_current_user)):
    return _sse_stream(ai_service.stream_translate(data.text, data.target_language, data.source_language or "en"))


# ── Suggestions ───────────────────────────────────────────────────────────────

@router.post("/suggestions", response_model=SuggestionsResponse)
@limiter.limit(settings.rate_limit_realtime_ai, key_func=get_user_id)
async def suggestions(request: Request, data: SuggestionRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Task 5.13 — story_id/chapter_id were already required fields on this
    # request but were never used: generate_suggestions(data.text) alone
    # meant story-specific analysis (checklist High 9) had no context to
    # work with even though the caller always supplies the IDs to build it.
    # Reuses Stage 4's existing retrieval, not new infrastructure.
    # Stage 7 (C7-6): this retrieves manuscript passages by story_id — it
    # must never run against a story the caller does not own.
    owned_story(data.story_id, current_user.user_id, db)
    story_context = ""
    try:
        from services.ai_service import retrieve_chunks_from_store
        chunks = await retrieve_chunks_from_store(data.text, data.story_id, db, top_k=3)
        if chunks:
            story_context = "\n".join(c["text"] for c in chunks)
    except Exception as exc:  # never let context retrieval break suggestions
        logger.warning("[ai_transform] suggestions: story-context retrieval failed (%s) — continuing without it", exc)

    genre = ""
    try:
        from models import GenreProfile
        profile = db.query(GenreProfile).filter(GenreProfile.story_id == data.story_id).first()
        if profile and profile.genre:
            genre = profile.genre
    except Exception:
        pass

    try:
        raw = await ai_service.generate_suggestions(data.text, story_context=story_context, genre=genre)
    except ValueError as exc:
        # Fixed author-facing text; the detail goes to the log. Same rule as
        # plot_holes.py — str(exc) is safe only until one internal error reaches
        # this handler.
        logger.warning("[ai_transform] suggestions failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Writing suggestions could not be generated. Please try again.",
        )
    from schemas import Suggestion
    result = [Suggestion(**s) for s in raw]
    return SuggestionsResponse(suggestions=result, tokens_used=len(data.text.split()) * 2)


# ── Phase 3: limits, compare, merge (spec §17.2) ─────────────────────────────

@router.get("/limits", response_model=AiLimitsOut)
async def ai_limits(story_id: Optional[str] = None, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Resolved plan limits and current usage. The frontend only DISPLAYS
    these; every limit is enforced server-side regardless (spec §21.3)."""
    from datetime import datetime as _dt
    from models import AiGenerationPin, NoteCard
    from schemas import IDEA_CARD_TYPES
    from services import plans
    usage = {
        "pins": db.query(AiGenerationPin).filter(AiGenerationPin.user_id == current_user.user_id,
                                                 AiGenerationPin.expires_at > _dt.utcnow()).count(),
        "idea_cards": db.query(NoteCard).filter(NoteCard.user_id == current_user.user_id,
                                                NoteCard.card_type.in_(IDEA_CARD_TYPES - {"style_sample"})).count(),
    }
    sid = _owned_story_id(story_id, current_user, db)
    if sid:
        usage["style_samples"] = db.query(NoteCard).filter(NoteCard.story_id == sid, NoteCard.user_id == current_user.user_id,
                                                           NoteCard.card_type == "style_sample").count()
    return AiLimitsOut(plan=plans.plan_name(current_user), limits=plans.limits_dict(current_user), usage=usage,
                       session_history_max=settings.session_history_max, avoid_max_items=settings.avoid_max_items)


@router.post("/compare-summary", response_model=CompareSummaryOut)
@limiter.limit(settings.rate_limit_realtime_ai, key_func=get_user_id)
async def compare_summary(request: Request, data: CompareSummaryRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _owned_story_id(data.story_id, current_user, db)
    from services.version_tools import compare_summary as _summary
    return CompareSummaryOut(**await _summary(data.text_a, data.text_b))


@router.post("/merge-versions", response_model=MergeOut)
@limiter.limit(settings.rate_limit_realtime_ai, key_func=get_user_id)
async def merge_versions(request: Request, data: MergeRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _owned_story_id(data.story_id, current_user, db)
    total = sum(len(b.text) for b in data.blocks)
    if total > 16000:
        raise ApiError(422, "This merge is too long to smooth. Merge a shorter passage.", code="merge_too_long")
    from services.version_tools import smooth_merge
    return MergeOut(**await smooth_merge([b.text for b in data.blocks]))
