"""
Streaming STT (CPU worker pool).

Browser MediaRecorder streams Opus/WebM chunks over the WebSocket. Because
faster-whisper is window-based (not token-streaming), we transcribe the
*accumulated* audio buffer:

  - partial passes: a small/fast model (settings.stt_partial_model, e.g. "base",
    int8) with beam_size=1 and VAD off → live partial transcript every ~1-2s.
  - final pass: the authoritative large-v3-turbo model via
    services.audio_service.transcribe_audio() (reuses the existing loader and the
    upload path unchanged).

All transcription is bounded by stt_semaphore (settings.stt_concurrency) so it
never contends with vLLM/BGE-M3 on the GPU and degrades predictably under load.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid

logger = logging.getLogger(__name__)

_stt_semaphore: asyncio.Semaphore | None = None
_partial_model = None
_partial_lock = asyncio.Lock()


def stt_semaphore() -> asyncio.Semaphore:
    global _stt_semaphore
    if _stt_semaphore is None:
        from config import settings
        _stt_semaphore = asyncio.Semaphore(settings.stt_concurrency)
        logger.info("[voice.stt] worker pool initialised: max_concurrent=%d", settings.stt_concurrency)
    return _stt_semaphore


def _load_partial_model():
    from faster_whisper import WhisperModel
    from config import settings
    return WhisperModel(
        settings.stt_partial_model,
        device=settings.whisper_device,
        compute_type=settings.stt_partial_compute,
        num_workers=1,
    )


async def get_partial_model():
    global _partial_model
    if _partial_model is None:
        async with _partial_lock:
            if _partial_model is None:
                _partial_model = await asyncio.to_thread(_load_partial_model)
                logger.info("[voice.stt] partial model loaded: %s", _partial_model)
    return _partial_model


def _voice_language() -> str | None:
    from config import settings
    return None if settings.voice_stt_auto_language else settings.voice_stt_language


def _transcribe_partial_sync(model, path: str) -> str:
    """Fast partial pass — English-pinned, VAD on, noise/low-confidence filtered.
    Returns '' for noise so junk partials are never displayed or routed."""
    from config import settings
    segments, _info = model.transcribe(
        path,
        beam_size=1,
        language=_voice_language(),
        task="transcribe",
        temperature=0.0,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 400},
        no_speech_threshold=settings.voice_no_speech_threshold,
        log_prob_threshold=settings.voice_logprob_threshold,
        condition_on_previous_text=False,
    )
    kept = []
    for s in segments:
        if getattr(s, "no_speech_prob", 0.0) > settings.voice_no_speech_threshold:
            continue
        if s.avg_logprob is not None and s.avg_logprob < settings.voice_logprob_threshold:
            continue
        t = s.text.strip()
        if t:
            kept.append(t)
    text = " ".join(kept).strip()
    # Ignore tiny noise fragments — partials this short are not useful and often junk.
    if len(text) < settings.voice_min_partial_chars:
        return ""
    return text


class STTSession:
    """Accumulates streamed audio for one utterance and produces partial + final
    transcripts. One instance per active WebSocket recording."""

    def __init__(self, work_dir: str):
        self.work_dir = work_dir
        os.makedirs(work_dir, exist_ok=True)
        self.audio_id = str(uuid.uuid4())
        self.path = os.path.join(work_dir, f"voice-{self.audio_id}.webm")
        self._fh = open(self.path, "wb")
        self._bytes = 0
        self._last_partial_at = 0.0
        self._closed = False

    def add_chunk(self, data: bytes) -> None:
        if self._closed or not data:
            return
        self._fh.write(data)
        self._fh.flush()
        self._bytes += len(data)

    @property
    def has_audio(self) -> bool:
        return self._bytes > 0

    async def maybe_partial(self, min_interval: float = 1.2) -> str | None:
        """Run a partial transcription if enough time has elapsed. Returns text or
        None. Partial transcripts are DISPLAY-ONLY and are never routed to the
        agent — only the stabilized final transcript triggers routing."""
        now = time.monotonic()
        if self._closed or self._bytes == 0 or (now - self._last_partial_at) < min_interval:
            return None
        self._last_partial_at = now
        try:
            t0 = time.monotonic()
            async with stt_semaphore():
                model = await get_partial_model()
                text = await asyncio.to_thread(_transcribe_partial_sync, model, self.path)
            logger.info("[voice.stt] partial %dms -> %r", int((time.monotonic() - t0) * 1000), text[:60])
            return text or None
        except Exception as exc:                       # noqa: BLE001
            logger.debug("[voice.stt] partial failed: %s", exc)
            return None

    async def finalize(self) -> dict:
        """Authoritative final transcription (large-v3-turbo), English-pinned."""
        self.close()
        if self._bytes == 0:
            return {"raw_transcript": "", "confidence": 0.0, "language_detected": "",
                    "duration_seconds": 0.0, "word_count": 0}
        from services.audio_service import transcribe_audio
        t0 = time.monotonic()
        async with stt_semaphore():
            result = await transcribe_audio(self.path, language=_voice_language())
        logger.info("[voice.stt] final %dms conf=%.2f -> %r",
                    int((time.monotonic() - t0) * 1000), result.get("confidence", 0.0),
                    (result.get("raw_transcript") or "")[:80])
        return result

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            try:
                self._fh.close()
            except Exception:
                pass

    def cleanup(self) -> None:
        self.close()
        try:
            if os.path.exists(self.path):
                os.remove(self.path)
        except OSError:
            pass
