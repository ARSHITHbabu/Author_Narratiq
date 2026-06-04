import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from schemas import (
    TransformRequest, ToneRequest, EmotionRequest, AgeAdaptRequest,
    StyleRequest, TranslationRequest, TransformResponse, SuggestionRequest, SuggestionsResponse
)
from routers.auth import get_current_user, User
from services import ai_service

router = APIRouter(tags=["ai-transform"])

# ── SSE helper ────────────────────────────────────────────────────────────────

def _sse_stream(async_gen):
    """
    Wraps an async generator of token strings into an SSE StreamingResponse.
    Frontend listens with EventSource or fetch + ReadableStream.

    Event format:
        data: {"token": "...", "done": false}
        data: {"done": true}
    """
    async def _generate():
        async for token in async_gen:
            yield f"data: {json.dumps({'token': token, 'done': False})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",   # disable nginx buffering on RunPod
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


# ── Refine ────────────────────────────────────────────────────────────────────

@router.post("/refine", response_model=TransformResponse)
async def refine(data: TransformRequest, current_user: User = Depends(get_current_user)):
    result = await ai_service.refine_text(data.text, data.mode or "standard")
    return TransformResponse(original=data.text, transformed=result,
                             mode=data.mode or "standard", tokens_used=len(data.text.split()) * 2)


@router.post("/refine/stream")
async def refine_stream(data: TransformRequest, current_user: User = Depends(get_current_user)):
    return _sse_stream(ai_service.stream_refine(data.text, data.mode or "standard"))


# ── Tone ──────────────────────────────────────────────────────────────────────

@router.post("/tone", response_model=TransformResponse)
async def tone_transform(data: ToneRequest, current_user: User = Depends(get_current_user)):
    result = await ai_service.transform_tone(data.text, data.tone)
    return TransformResponse(original=data.text, transformed=result,
                             mode=f"tone:{data.tone}", tokens_used=len(data.text.split()) * 2)


@router.post("/tone/stream")
async def tone_stream(data: ToneRequest, current_user: User = Depends(get_current_user)):
    return _sse_stream(ai_service.stream_tone(data.text, data.tone))


# ── Emotion ───────────────────────────────────────────────────────────────────

@router.post("/emotion", response_model=TransformResponse)
async def emotion_rewrite(data: EmotionRequest, current_user: User = Depends(get_current_user)):
    result = await ai_service.rewrite_emotion(data.text, data.emotion, data.intensity or "medium")
    return TransformResponse(original=data.text, transformed=result,
                             mode=f"emotion:{data.emotion}", tokens_used=len(data.text.split()) * 2)


@router.post("/emotion/stream")
async def emotion_stream(data: EmotionRequest, current_user: User = Depends(get_current_user)):
    return _sse_stream(ai_service.stream_emotion(data.text, data.emotion, data.intensity or "medium"))


# ── Age adapt ─────────────────────────────────────────────────────────────────

@router.post("/age-adapt", response_model=TransformResponse)
async def age_adapt(data: AgeAdaptRequest, current_user: User = Depends(get_current_user)):
    result = await ai_service.adapt_for_age(data.text, data.target_age)
    return TransformResponse(original=data.text, transformed=result,
                             mode=f"age:{data.target_age}", tokens_used=len(data.text.split()) * 2)


@router.post("/age-adapt/stream")
async def age_adapt_stream(data: AgeAdaptRequest, current_user: User = Depends(get_current_user)):
    return _sse_stream(ai_service.stream_age_adapt(data.text, data.target_age))


# ── Style ─────────────────────────────────────────────────────────────────────

@router.post("/style", response_model=TransformResponse)
async def style_transform(data: StyleRequest, current_user: User = Depends(get_current_user)):
    result = await ai_service.transform_style(data.text, data.style)
    return TransformResponse(original=data.text, transformed=result,
                             mode=f"style:{data.style}", tokens_used=len(data.text.split()) * 2)


@router.post("/style/stream")
async def style_stream(data: StyleRequest, current_user: User = Depends(get_current_user)):
    return _sse_stream(ai_service.stream_style(data.text, data.style))


# ── Translate ─────────────────────────────────────────────────────────────────

@router.post("/translate", response_model=TransformResponse)
async def translate(data: TranslationRequest, current_user: User = Depends(get_current_user)):
    result = await ai_service.translate_text(data.text, data.target_language, data.source_language or "en")
    return TransformResponse(original=data.text, transformed=result,
                             mode=f"translate:{data.target_language}", tokens_used=len(data.text.split()) * 3)


@router.post("/translate/stream")
async def translate_stream(data: TranslationRequest, current_user: User = Depends(get_current_user)):
    return _sse_stream(ai_service.stream_translate(data.text, data.target_language, data.source_language or "en"))


# ── Suggestions (structured JSON — no streaming) ──────────────────────────────

@router.post("/suggestions", response_model=SuggestionsResponse)
async def suggestions(data: SuggestionRequest, current_user: User = Depends(get_current_user)):
    try:
        raw = await ai_service.generate_suggestions(data.text)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    from schemas import Suggestion
    result = [Suggestion(**s) for s in raw]
    return SuggestionsResponse(suggestions=result, tokens_used=len(data.text.split()) * 2)
