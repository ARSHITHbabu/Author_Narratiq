"""
Phase 2 — P2-11 Audio Notes Transcription Service
Uses faster-whisper (CTranslate2) with lazy loading.
Model: faster-whisper-large-v3-turbo (~1.5 GB; deepdml CTranslate2 mirror)
Transcription runs in asyncio.to_thread to avoid blocking the event loop.
"""
import asyncio
import logging
import os

from config import settings

logger = logging.getLogger(__name__)

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
        logger.info(
            "[audio_service] faster-whisper loaded: %s (device=%s, compute=%s)",
            model_path, settings.whisper_device, settings.whisper_compute_type,
        )
    return _whisper_model


def _transcribe_sync(audio_path: str, language: str | None = None) -> dict:
    """
    Synchronous transcription. Called via asyncio.to_thread.
    Returns dict with keys: raw_transcript, language, avg_confidence, duration, word_count.

    `language` pins the decode language (e.g. "en" for live voice commands so a
    noisy utterance is never mis-detected). None = auto-detect (legacy upload path).
    Noise/silence segments are filtered via no_speech_prob + avg_logprob thresholds.
    """
    import math
    model = _get_whisper()

    segments, info = model.transcribe(
        audio_path,
        beam_size=5,
        language=language,                       # pinned for voice mode; None = auto
        task="transcribe",
        temperature=0.0,                         # deterministic, more stable
        vad_filter=True,                         # skip silence
        vad_parameters={"min_silence_duration_ms": 500},
        no_speech_threshold=settings.voice_no_speech_threshold,
        log_prob_threshold=settings.voice_logprob_threshold,
        condition_on_previous_text=False,        # stop runaway hallucinated text
        word_timestamps=False,
    )

    texts   = []
    scores  = []
    for seg in segments:
        # Drop segments the model flags as silence/very low confidence (noise).
        if getattr(seg, "no_speech_prob", 0.0) > settings.voice_no_speech_threshold:
            continue
        if seg.avg_logprob is not None and seg.avg_logprob < settings.voice_logprob_threshold:
            continue
        t = seg.text.strip()
        if not t:
            continue
        texts.append(t)
        if seg.avg_logprob is not None:
            scores.append(math.exp(max(seg.avg_logprob, -5)))

    raw_transcript = " ".join(texts)
    avg_confidence = sum(scores) / len(scores) if scores else 0.0
    duration       = info.duration if info else 0.0
    word_count     = len(raw_transcript.split()) if raw_transcript else 0

    return {
        "raw_transcript":    raw_transcript,
        "language_detected": (language or (info.language if info else "")),
        "duration_seconds":  round(duration, 1),
        "confidence":        round(min(avg_confidence, 1.0), 3),
        "word_count":        word_count,
    }


async def transcribe_audio(audio_path: str, language: str | None = None) -> dict:
    """
    Async wrapper — runs faster-whisper in a thread pool so the FastAPI event
    loop stays free during the CPU-bound transcription.
    `language` pins the decode language (voice mode); None auto-detects (upload).
    Returns the same dict as _transcribe_sync.
    """
    return await asyncio.to_thread(_transcribe_sync, audio_path, language)


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
    system = (
        "You are a transcript editor. Clean the following raw speech-to-text transcript.\n"
        "Rules:\n"
        "- Remove filler words: um, uh, like, you know, so, basically, actually (when used as filler)\n"
        "- Add proper punctuation and sentence breaks\n"
        "- Fix repeated words (e.g. 'the the' → 'the')\n"
        "- Do NOT change meaning, do NOT add or remove facts\n"
        "- Return ONLY the cleaned text with no commentary"
    )
    try:
        result = await _complete(system=system, user=raw_text[:3000], max_tokens=1024)
        return result.strip() if result else raw_text
    except Exception as exc:
        logger.warning("[audio_service] clean_transcript failed: %s", exc)
        return raw_text
