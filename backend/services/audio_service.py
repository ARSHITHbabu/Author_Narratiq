"""
Phase 2 — P2-11 Audio Notes Transcription Service
Uses faster-whisper (CTranslate2) with lazy loading.
Model: faster-whisper-large-v3-turbo (~1.5 GB; deepdml CTranslate2 mirror)
Transcription runs in asyncio.to_thread to avoid blocking the event loop.
"""
import asyncio
import logging
import os
import re

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


# Stage 12 Tranche 3 (A21): the clean-up may only remove fillers and repeats.
# Measured on the live model: it dropped a whole dictated opening sentence
# ("Audio note for chapter 3.", "Note to self for the next draft.") in 19 of 20
# runs, despite "do NOT remove facts" in the prompt, and that text is what the
# author appends to a note. Code enforces it instead: if the cleaned text has
# lost more than CLEANUP_MIN_KEPT of the transcript's non-filler words, the raw
# transcript (already punctuated by Whisper) is kept. The same check keeps a
# dictation longer than the 3000 characters sent to the model from losing its end.
_FILLERS = frozenset({"um", "uh", "er", "erm", "hmm", "like", "you", "know", "so", "basically", "actually"})
CLEANUP_MIN_KEPT = 0.9
_WORD = re.compile(r"[^\W_]+(?:'[^\W_]+)?")


def cleanup_kept_share(raw_text: str, cleaned: str) -> float:
    """Share of the raw transcript's distinct non-filler words still present."""
    raw = {w for w in _WORD.findall(raw_text.lower()) if w not in _FILLERS}
    if not raw:
        return 1.0
    return len(raw & set(_WORD.findall(cleaned.lower()))) / len(raw)


async def clean_transcript(raw_text: str) -> str:
    """
    Post-process the raw Whisper transcript with Qwen:
    - Remove filler words (um, uh, like, you know)
    - Fix run-on sentences and add punctuation
    - Normalise repeated words
    Returns the cleaned text, or raw_text on failure or when the clean-up
    dropped the author's words (cleanup_kept_share below CLEANUP_MIN_KEPT).
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
        cleaned = result.strip() if result else ""
        if not cleaned:
            return raw_text
        # Against the WHOLE transcript: only the first 3000 characters are sent,
        # so a longer dictation must keep its raw text rather than lose its end.
        kept = cleanup_kept_share(raw_text, cleaned)
        if kept < CLEANUP_MIN_KEPT:
            # Counts only: never log transcript text.
            logger.warning("[audio_service] clean-up dropped content (kept %.2f of words); keeping the raw transcript", kept)
            return raw_text
        return cleaned
    except Exception as exc:
        logger.warning("[audio_service] clean_transcript failed: %s", exc)
        return raw_text
