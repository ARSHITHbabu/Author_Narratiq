"""
Phase 2 — P2-11 Audio Notes Transcription Service
Uses faster-whisper (CTranslate2) with lazy loading.
Model: Systran/faster-whisper-large-v3-turbo (~1.5 GB)
Transcription runs in asyncio.to_thread to avoid blocking the event loop.
"""
import asyncio
import os

from config import settings

_whisper_model = None


def _get_whisper():
    """Lazy-load the faster-whisper model on first call. Thread-safe via GIL."""
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel

        model_path = settings.resolved_whisper_path
        if not os.path.exists(model_path):
            # Fall back to HuggingFace auto-download if local path missing
            model_path = settings.whisper_model_id

        _whisper_model = WhisperModel(
            model_path,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
            num_workers=1,
        )
        print(f"[audio_service] faster-whisper loaded: {model_path} "
              f"(device={settings.whisper_device}, compute={settings.whisper_compute_type})")
    return _whisper_model


def _transcribe_sync(audio_path: str) -> dict:
    """
    Synchronous transcription. Called via asyncio.to_thread.
    Returns dict with keys: raw_transcript, language, avg_confidence, duration, word_count.
    """
    model = _get_whisper()

    segments, info = model.transcribe(
        audio_path,
        beam_size=5,
        vad_filter=True,          # skip silence
        vad_parameters={"min_silence_duration_ms": 500},
        word_timestamps=False,
    )

    texts   = []
    scores  = []
    for seg in segments:
        texts.append(seg.text.strip())
        if seg.avg_logprob is not None:
            # Convert log-prob to approximate confidence [0,1]
            import math
            conf = math.exp(max(seg.avg_logprob, -5))
            scores.append(conf)

    raw_transcript = " ".join(t for t in texts if t)
    avg_confidence = sum(scores) / len(scores) if scores else 0.0
    duration       = info.duration if info else 0.0
    word_count     = len(raw_transcript.split()) if raw_transcript else 0

    return {
        "raw_transcript":    raw_transcript,
        "language_detected": info.language if info else "",
        "duration_seconds":  round(duration, 1),
        "confidence":        round(min(avg_confidence, 1.0), 3),
        "word_count":        word_count,
    }


async def transcribe_audio(audio_path: str) -> dict:
    """
    Async wrapper — runs faster-whisper in a thread pool so the FastAPI event
    loop stays free during the CPU-bound transcription.
    Returns the same dict as _transcribe_sync.
    """
    return await asyncio.to_thread(_transcribe_sync, audio_path)


async def clean_transcript(raw_text: str) -> str:
    """
    Post-process the raw Whisper transcript with Qwen:
    - Remove filler words (um, uh, like, you know)
    - Fix run-on sentences and add punctuation
    - Normalise repeated words
    Returns the cleaned text, or raw_text on failure.
    """
    if not raw_text or len(raw_text.split()) < 5:
        return raw_text

    from services.ai_service import _complete
    prompt = (
        "You are a transcript editor. Clean the following raw speech-to-text transcript.\n"
        "Rules:\n"
        "- Remove filler words: um, uh, like, you know, so, basically, actually (when used as filler)\n"
        "- Add proper punctuation and sentence breaks\n"
        "- Fix repeated words (e.g. 'the the' → 'the')\n"
        "- Do NOT change meaning, do NOT add or remove facts\n"
        "- Return ONLY the cleaned text with no commentary\n\n"
        f"Raw transcript:\n{raw_text[:3000]}"
    )
    try:
        result = await _complete(prompt, max_tokens=1024)
        return result.strip() if result else raw_text
    except Exception:
        return raw_text
