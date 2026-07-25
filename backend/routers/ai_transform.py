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
)
from routers.auth import get_current_user, User
from services import ai_service
from services.genre_context import build_genre_context

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ai-transform"])


def _genre_ctx(story_id: Optional[str], db: Session) -> str:
    """Resolve the genre-profile context for a story (or "" when none/absent)."""
    if not story_id:
        return ""
    try:
        return build_genre_context(story_id, db)
    except Exception:  # never let context lookup break a transform
        return ""


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
    result = await ai_service.refine_text(data.text, data.mode or "standard", genre_context=_genre_ctx(data.story_id, db))
    return TransformResponse(original=data.text, transformed=result,
                             mode=data.mode or "standard", tokens_used=len(data.text.split()) * 2)


@router.post("/refine/stream")
@limiter.limit(settings.rate_limit_realtime_ai, key_func=get_user_id)
async def refine_stream(request: Request, data: TransformRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _sse_stream(ai_service.stream_refine(data.text, data.mode or "standard", genre_context=_genre_ctx(data.story_id, db)))


# ── Tone ──────────────────────────────────────────────────────────────────────

@router.post("/tone", response_model=TransformResponse)
@limiter.limit(settings.rate_limit_realtime_ai, key_func=get_user_id)
async def tone_transform(request: Request, data: ToneRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    result = await ai_service.transform_tone(data.text, data.tone, genre_context=_genre_ctx(data.story_id, db))
    return TransformResponse(original=data.text, transformed=result,
                             mode=f"tone:{data.tone}", tokens_used=len(data.text.split()) * 2)


@router.post("/tone/stream")
@limiter.limit(settings.rate_limit_realtime_ai, key_func=get_user_id)
async def tone_stream(request: Request, data: ToneRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _sse_stream(ai_service.stream_tone(data.text, data.tone, genre_context=_genre_ctx(data.story_id, db)))


# ── Emotion ───────────────────────────────────────────────────────────────────

@router.post("/emotion", response_model=TransformResponse)
@limiter.limit(settings.rate_limit_realtime_ai, key_func=get_user_id)
async def emotion_rewrite(request: Request, data: EmotionRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    result = await ai_service.rewrite_emotion(data.text, data.emotion, data.intensity or "medium", genre_context=_genre_ctx(data.story_id, db))
    return TransformResponse(original=data.text, transformed=result,
                             mode=f"emotion:{data.emotion}", tokens_used=len(data.text.split()) * 2)


@router.post("/emotion/stream")
@limiter.limit(settings.rate_limit_realtime_ai, key_func=get_user_id)
async def emotion_stream(request: Request, data: EmotionRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _sse_stream(ai_service.stream_emotion(data.text, data.emotion, data.intensity or "medium", genre_context=_genre_ctx(data.story_id, db)))


# ── Age adapt ─────────────────────────────────────────────────────────────────

@router.post("/age-adapt", response_model=TransformResponse)
@limiter.limit(settings.rate_limit_realtime_ai, key_func=get_user_id)
async def age_adapt(request: Request, data: AgeAdaptRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    result = await ai_service.adapt_for_age(data.text, data.target_age, genre_context=_genre_ctx(data.story_id, db))
    return TransformResponse(original=data.text, transformed=result,
                             mode=f"age:{data.target_age}", tokens_used=len(data.text.split()) * 2)


@router.post("/age-adapt/stream")
@limiter.limit(settings.rate_limit_realtime_ai, key_func=get_user_id)
async def age_adapt_stream(request: Request, data: AgeAdaptRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _sse_stream(ai_service.stream_age_adapt(data.text, data.target_age, genre_context=_genre_ctx(data.story_id, db)))


# ── Style ─────────────────────────────────────────────────────────────────────

@router.post("/style", response_model=TransformResponse)
@limiter.limit(settings.rate_limit_realtime_ai, key_func=get_user_id)
async def style_transform(request: Request, data: StyleRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    result = await ai_service.transform_style(data.text, data.style, genre_context=_genre_ctx(data.story_id, db))
    return TransformResponse(original=data.text, transformed=result,
                             mode=f"style:{data.style}", tokens_used=len(data.text.split()) * 2)


@router.post("/style/stream")
@limiter.limit(settings.rate_limit_realtime_ai, key_func=get_user_id)
async def style_stream(request: Request, data: StyleRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _sse_stream(ai_service.stream_style(data.text, data.style, genre_context=_genre_ctx(data.story_id, db)))


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
    result = await ai_service.rewrite_in_author_style(text, data.author, genre_context=_genre_ctx(data.story_id, db))
    return TransformResponse(original=data.text, transformed=result,
                             mode=f"author:{data.author}", tokens_used=len(text.split()) * 2)


@router.post("/author-style/stream")
@limiter.limit(settings.rate_limit_realtime_ai, key_func=get_user_id)
async def author_style_stream(request: Request, data: AuthorStyleRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    text = _validate_transform_text(data.text)
    return _sse_stream(ai_service.stream_author_style(text, data.author, genre_context=_genre_ctx(data.story_id, db)))


# ── Translate ─────────────────────────────────────────────────────────────────

@router.post("/translate", response_model=TransformResponse)
@limiter.limit(settings.rate_limit_realtime_ai, key_func=get_user_id)
async def translate(request: Request, data: TranslationRequest, current_user: User = Depends(get_current_user)):
    result = await ai_service.translate_text(data.text, data.target_language, data.source_language or "en")
    return TransformResponse(original=data.text, transformed=result,
                             mode=f"translate:{data.target_language}", tokens_used=len(data.text.split()) * 3)


@router.post("/translate/stream")
@limiter.limit(settings.rate_limit_realtime_ai, key_func=get_user_id)
async def translate_stream(request: Request, data: TranslationRequest, current_user: User = Depends(get_current_user)):
    return _sse_stream(ai_service.stream_translate(data.text, data.target_language, data.source_language or "en"))


# ── Suggestions ───────────────────────────────────────────────────────────────

@router.post("/suggestions", response_model=SuggestionsResponse)
@limiter.limit(settings.rate_limit_realtime_ai, key_func=get_user_id)
async def suggestions(request: Request, data: SuggestionRequest, current_user: User = Depends(get_current_user)):
    try:
        raw = await ai_service.generate_suggestions(data.text)
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
