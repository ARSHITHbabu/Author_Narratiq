from contextlib import asynccontextmanager
import asyncio
import os
import httpx
from datetime import datetime, timedelta
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from logger import setup_logging
from config import settings

# Configure logging before anything else logs
setup_logging(level=settings.log_level, fmt=settings.log_format)

import logging
logger = logging.getLogger(__name__)

from database import engine, Base, run_db_migrations
import models  # noqa: F401

from exceptions import AIServiceUnavailableError, UploadTooLargeError
from middleware.rate_limit import limiter

from routers import auth, projects, chapters, intake, plot_assistant, ai_transform, ocr, manuscript, export, characters, plot_holes, manuscript_report
from routers import search as search_router
from routers import story_intel
from routers import analysis, writing_tools, pacing, narrative_threads, story_bible, audio as audio_router
from routers import voice_agent

Base.metadata.create_all(bind=engine)
run_db_migrations(engine)   # add new columns to existing tables

# ── OCR image cleanup ─────────────────────────────────────────────────────────
_OCR_CONFIRMED_TTL_HOURS   = 24
_OCR_UNCONFIRMED_TTL_HOURS = 72
_OCR_CLEANUP_INTERVAL_SECS = 3600   # sweep every hour


async def _cleanup_ocr_images() -> int:
    from database import SessionLocal
    from models import OcrUpload
    from sqlalchemy import and_, or_

    now = datetime.utcnow()
    confirmed_cutoff   = now - timedelta(hours=_OCR_CONFIRMED_TTL_HOURS)
    unconfirmed_cutoff = now - timedelta(hours=_OCR_UNCONFIRMED_TTL_HOURS)

    db = SessionLocal()
    removed = 0
    try:
        stale = (
            db.query(OcrUpload)
            .filter(
                OcrUpload.image_path.isnot(None),
                or_(
                    and_(OcrUpload.confirmed == True,  OcrUpload.created_at < confirmed_cutoff),   # noqa: E712
                    and_(OcrUpload.confirmed == False, OcrUpload.created_at < unconfirmed_cutoff),  # noqa: E712
                ),
            )
            .all()
        )

        for upload in stale:
            path = upload.image_path
            try:
                if path and os.path.exists(path):
                    os.remove(path)
                    removed += 1
            except OSError as exc:
                logger.warning("[ocr_cleanup] could not delete %r: %s", path, exc)
            finally:
                upload.image_path = None

        if stale:
            db.commit()
            logger.info(
                "[ocr_cleanup] swept %d record(s): %d file(s) deleted "
                "(confirmed>%dh or unconfirmed>%dh)",
                len(stale), removed,
                _OCR_CONFIRMED_TTL_HOURS, _OCR_UNCONFIRMED_TTL_HOURS,
            )
    except Exception as exc:
        logger.error("[ocr_cleanup] error during cleanup: %s", exc)
        db.rollback()
    finally:
        db.close()

    return removed


async def _cleanup_audio_files() -> None:
    from database import SessionLocal
    from models import AudioUpload
    from sqlalchemy import and_, or_

    now = datetime.utcnow()
    confirmed_cutoff   = now - timedelta(hours=_OCR_CONFIRMED_TTL_HOURS)
    unconfirmed_cutoff = now - timedelta(hours=_OCR_UNCONFIRMED_TTL_HOURS)

    db = SessionLocal()
    try:
        stale = (
            db.query(AudioUpload)
            .filter(
                AudioUpload.audio_path.isnot(None),
                or_(
                    and_(AudioUpload.confirmed == True,  AudioUpload.created_at < confirmed_cutoff),   # noqa: E712
                    and_(AudioUpload.confirmed == False, AudioUpload.created_at < unconfirmed_cutoff),  # noqa: E712
                ),
            )
            .all()
        )
        removed = 0
        for upload in stale:
            path = upload.audio_path
            try:
                if path and os.path.exists(path):
                    os.remove(path)
                    removed += 1
            except OSError as exc:
                logger.warning("[audio_cleanup] could not delete %r: %s", path, exc)
            finally:
                upload.audio_path = None
        if stale:
            db.commit()
            logger.info("[audio_cleanup] swept %d record(s): %d file(s) deleted", len(stale), removed)
    except Exception as exc:
        logger.error("[audio_cleanup] error: %s", exc)
        db.rollback()
    finally:
        db.close()


async def _rollup_voice_analytics() -> None:
    """Roll today's raw voice events into voice_usage_daily (D)."""
    if not settings.voice_agent_enabled:
        return
    try:
        from services.voice.analytics import rollup_daily
        await asyncio.to_thread(rollup_daily)
    except Exception as exc:                       # noqa: BLE001
        logger.error("[cleanup] voice analytics rollup failed: %s", exc)


async def _run_periodic_cleanup() -> None:
    """Startup sweep then hourly OCR + audio file cleanup + voice analytics rollup."""
    await _cleanup_ocr_images()
    await _cleanup_audio_files()
    await _rollup_voice_analytics()
    while True:
        await asyncio.sleep(_OCR_CLEANUP_INTERVAL_SECS)
        try:
            await _cleanup_ocr_images()
            await _cleanup_audio_files()
            await _rollup_voice_analytics()
        except Exception as exc:
            logger.error("[cleanup] periodic sweep failed: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────────

    # ── Orphan job recovery (before accepting any requests) ───────────────────
    from startup.orphan_recovery import recover_orphaned_jobs
    await recover_orphaned_jobs()

    # ── Create upload directories from config ─────────────────────────────────
    os.makedirs(settings.upload_dir_audio, exist_ok=True)
    os.makedirs(settings.upload_dir_ocr,   exist_ok=True)
    logger.info("[startup] upload dirs: audio=%r ocr=%r", settings.upload_dir_audio, settings.upload_dir_ocr)

    # Validate model paths before attempting to load anything
    missing = settings.validate_model_paths()
    if missing:
        paths_str = "\n".join(missing)
        raise RuntimeError(
            "Required model directories not found. "
            "Run scripts/download_models.sh first.\n"
            f"Missing:\n{paths_str}\n"
            f"Expected under: {settings.model_base_dir}"
        )

    logger.info("[startup] loading BGE-M3 embeddings model...")
    from services.ai_service import get_bge
    get_bge()
    app.state.embeddings_ready = True
    logger.info("[startup] BGE-M3 loaded on %s", settings.bge_device)

    # ── Voice agent: build the capability shortlist index (BGE-M3) ────────────
    if settings.voice_agent_enabled:
        try:
            from services.voice.catalog import build_catalog_embeddings
            n = build_catalog_embeddings()
            logger.info("[startup] voice capability index built: %d capabilities", n)
        except Exception as e:                       # noqa: BLE001
            logger.warning("[startup] voice capability index build failed: %s", e)

    # ── pgvector path self-check ──────────────────────────────────────────────
    logger.info("[startup] verifying pgvector query path...")
    try:
        from sqlalchemy import text as _sql_text
        from database import SessionLocal
        from services.ai_service import embed_text_sync, vector_similarity
        _probe = embed_text_sync("startup vector self-check")
        _db = SessionLocal()
        try:
            _score = _db.execute(
                _sql_text(f"SELECT {vector_similarity('CAST(:q AS vector)')} AS s"),
                {"q": "[" + ",".join(str(float(v)) for v in _probe) + "]"},
            ).scalar()
        finally:
            _db.close()
        if _score is None or abs(float(_score) - 1.0) > 1e-3:
            raise RuntimeError(f"unexpected self-similarity score: {_score}")
        logger.info("[startup] pgvector query path OK (self-similarity=%.4f)", float(_score))
    except Exception as e:
        raise RuntimeError(
            "pgvector query path self-check FAILED — vector retrieval is broken. "
            f"Cause: {type(e).__name__}: {e}. "
            "Check pgvector is installed and the embedding<=>vector cast syntax."
        ) from e

    logger.info("[startup] connecting to vLLM at %s...", settings.vllm_base_url)
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.get(settings.vllm_health_url)
            r.raise_for_status()
            app.state.llm_ready = True
            logger.info("[startup] vLLM health check passed")
        except Exception as e:
            app.state.llm_ready = False
            logger.warning(
                "[startup] vLLM not reachable at %s (%s). "
                "AI generation features will be unavailable until vLLM starts.",
                settings.vllm_health_url, e,
            )

    if app.state.llm_ready:
        logger.info("[startup] warming up vLLM (first-token pre-heat)...")
        try:
            from services.ai_service import warmup
            await warmup()
            logger.info("[startup] vLLM warmup complete — first user request will be fast")
        except Exception as e:
            logger.warning("[startup] vLLM warmup failed: %s", e)

    asyncio.create_task(_run_periodic_cleanup())
    logger.info(
        "[startup] cleanup scheduler started (confirmed>%dh, unconfirmed>%dh, interval=%dh)",
        _OCR_CONFIRMED_TTL_HOURS, _OCR_UNCONFIRMED_TTL_HOURS, _OCR_CLEANUP_INTERVAL_SECS // 3600,
    )

    logger.info("[startup] NarratIQ ready (log_level=%s, log_format=%s)", settings.log_level, settings.log_format)
    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    from services.ai_service import _vllm_client
    if _vllm_client:
        await _vllm_client.close()


app = FastAPI(
    title="NarratIQ AI API",
    description="AI-Powered Long-Form Storytelling Platform",
    version="3.0.0",
    lifespan=lifespan,
)

# ── Rate limiter ──────────────────────────────────────────────────────────────
app.state.limiter = limiter


# ── Global exception handlers ─────────────────────────────────────────────────

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    retry_after = 60
    return JSONResponse(
        status_code=429,
        content={
            "error":       "rate_limit_exceeded",
            "message":     "Too many requests. Please wait before trying again.",
            "retry_after": retry_after,
        },
        headers={"Retry-After": str(retry_after)},
    )


@app.exception_handler(AIServiceUnavailableError)
async def ai_unavailable_handler(request: Request, exc: AIServiceUnavailableError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "error":       "ai_unavailable",
            "message":     exc.message,
            "retry_after": exc.retry_after,
        },
        headers={"Retry-After": str(exc.retry_after)},
    )


@app.exception_handler(UploadTooLargeError)
async def upload_too_large_handler(request: Request, exc: UploadTooLargeError) -> JSONResponse:
    return JSONResponse(
        status_code=413,
        content={
            "error":   "upload_too_large",
            "message": exc.message,
        },
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"https://.*\.proxy\.runpod\.net",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,           prefix="/api/auth")
app.include_router(projects.router,       prefix="/api/projects")
app.include_router(chapters.router,       prefix="/api/stories")
app.include_router(characters.router,     prefix="/api/stories")
app.include_router(intake.router,         prefix="/api/intake")
app.include_router(plot_assistant.router, prefix="/api/plot-assistant")
app.include_router(ai_transform.router,   prefix="/api/ai")
app.include_router(ocr.router,            prefix="/api/ocr")
app.include_router(manuscript.router,     prefix="/api/manuscript")
app.include_router(export.router,         prefix="/api/export")
app.include_router(search_router.router,  prefix="/api/search")
app.include_router(plot_holes.router,        prefix="/api/stories")
app.include_router(manuscript_report.router, prefix="/api/stories")
app.include_router(story_intel.router,       prefix="/api/stories")
# ── Phase 2 routers ───────────────────────────────────────────────────────────
app.include_router(analysis.router,          prefix="/api/stories")
app.include_router(writing_tools.router,     prefix="/api/stories")
app.include_router(pacing.router,            prefix="/api/stories")
app.include_router(narrative_threads.router, prefix="/api/stories")
app.include_router(story_bible.router,       prefix="/api/stories")
app.include_router(audio_router.router,      prefix="/api/stories")
# ── Real-Time Voice Agent ───────────────────────────────────────────────────────
app.include_router(voice_agent.router,       prefix="/api/voice")


@app.get("/api/health")
async def health():
    import os
    vllm_status = "ready" if getattr(app.state, "llm_ready",       False) else "unavailable"
    bge_status  = "ready" if getattr(app.state, "embeddings_ready", False) else "loading"

    gpu_info: dict = {}
    try:
        import torch
        if torch.cuda.is_available():
            gpu_info = {
                "count":           torch.cuda.device_count(),
                "tensor_parallel": settings.tensor_parallel_size,
                "vram_per_gpu_gb": round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 1),
                "total_vram_gb":   round(
                    torch.cuda.get_device_properties(0).total_memory / 1024**3
                    * torch.cuda.device_count(), 1
                ),
            }
    except Exception:
        pass

    return {
        "status":   "ok",
        "version":  "3.0.0",
        "platform": "NarratIQ AI",
        "backend":  "ready",
        "vllm":     vllm_status,
        "bge_m3":   bge_status,
        "got_ocr":  "lazy",
        "gpu":      gpu_info,
        "config": {
            "vllm_url":        settings.vllm_base_url,
            "vllm_model":      settings.vllm_model_name,
            "max_model_len":   settings.max_model_len,
            "gpu_memory_util": settings.gpu_memory_utilization,
        },
    }


@app.get("/api/stats")
def stats():
    from database import SessionLocal
    from models import User, Story, Chapter
    db = SessionLocal()
    try:
        return {
            "users":    db.query(User).count(),
            "stories":  db.query(Story).count(),
            "chapters": db.query(Chapter).count(),
        }
    finally:
        db.close()
