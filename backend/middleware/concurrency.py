"""
Background AI concurrency limiting for NarratIQ AI.

Two asyncio.Semaphore instances control how many background AI tasks run
simultaneously, preventing unbounded task flooding that would saturate vLLM
and deny service to foreground (realtime) requests.

  bg_ai_semaphore    — governs all background Qwen calls
                       (story bible, narrative threads, chapter summary, manuscript ingest,
                        story intel P01-P29, audio transcript cleanup)
  embedding_semaphore — governs background BGE-M3 embedding tasks
                       (note embeds, character profile embeds, note-card embeds)

Semaphore values come from settings (BG_AI_CONCURRENCY, EMBEDDING_CONCURRENCY env vars).
They are initialised lazily on first access so config is fully loaded first.

Foreground (realtime) requests do NOT acquire these semaphores — they go directly
to vLLM and compete only at the queue level. The semaphores protect foreground
requests by preventing background tasks from flooding the queue.

Future Celery migration:
  Replace `async with bg_ai_semaphore():` in each background function with a
  @celery_app.task(priority=LOW) decorator. No API or DB schema changes needed.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)

_bg_ai_semaphore: asyncio.Semaphore | None = None
_embedding_semaphore: asyncio.Semaphore | None = None


def bg_ai_semaphore() -> asyncio.Semaphore:
    """Return the singleton background-AI semaphore (lazy init)."""
    global _bg_ai_semaphore
    if _bg_ai_semaphore is None:
        from config import settings
        _bg_ai_semaphore = asyncio.Semaphore(settings.bg_ai_concurrency)
        logger.info(
            "[concurrency] background AI semaphore initialised: max_concurrent=%d",
            settings.bg_ai_concurrency,
        )
    return _bg_ai_semaphore


def embedding_semaphore() -> asyncio.Semaphore:
    """Return the singleton embedding semaphore (lazy init)."""
    global _embedding_semaphore
    if _embedding_semaphore is None:
        from config import settings
        _embedding_semaphore = asyncio.Semaphore(settings.embedding_concurrency)
        logger.info(
            "[concurrency] embedding semaphore initialised: max_concurrent=%d",
            settings.embedding_concurrency,
        )
    return _embedding_semaphore
