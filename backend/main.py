from contextlib import asynccontextmanager
import asyncio
import os
import httpx
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import engine, Base, run_db_migrations
import models  # noqa: F401

from routers import auth, projects, chapters, intake, plot_assistant, ai_transform, ocr, manuscript, export, characters, plot_holes, manuscript_report
from routers import search as search_router
from routers import story_intel
from routers import analysis, writing_tools, pacing, narrative_threads, story_bible, audio as audio_router

Base.metadata.create_all(bind=engine)
run_db_migrations(engine)   # add new columns to existing tables

# ── OCR image cleanup ─────────────────────────────────────────────────────────
# Confirmed uploads: text is safely in the DB; original image no longer needed.
# Unconfirmed uploads: author abandoned the session; remove after 3 days.
_OCR_CONFIRMED_TTL_HOURS   = 24
_OCR_UNCONFIRMED_TTL_HOURS = 72
_OCR_CLEANUP_INTERVAL_SECS = 3600   # sweep every hour


async def _cleanup_ocr_images() -> int:
    """
    Delete OCR image files whose retention window has expired and null their
    image_path in the DB.  The OcrUpload record itself is kept — it provides
    the idempotency guard (confirmed=True) and OCR text traceability.

    Returns the count of files removed this run.
    """
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
                print(f"[ocr_cleanup] could not delete {path!r}: {exc}")
            finally:
                upload.image_path = None

        if stale:
            db.commit()
            print(
                f"[ocr_cleanup] swept {len(stale)} record(s): "
                f"{removed} file(s) deleted "
                f"(confirmed>{_OCR_CONFIRMED_TTL_HOURS}h or "
                f"unconfirmed>{_OCR_UNCONFIRMED_TTL_HOURS}h)"
            )
    except Exception as exc:
        print(f"[ocr_cleanup] error during cleanup: {exc}")
        db.rollback()
    finally:
        db.close()

    return removed


async def _cleanup_audio_files() -> None:
    """
    Delete confirmed audio files older than 24 h and failed/unconfirmed ones older than 72 h.
    The AudioUpload DB record is retained for traceability.
    """
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
                print(f"[audio_cleanup] could not delete {path!r}: {exc}")
            finally:
                upload.audio_path = None
        if stale:
            db.commit()
            print(f"[audio_cleanup] swept {len(stale)} record(s): {removed} file(s) deleted")
    except Exception as exc:
        print(f"[audio_cleanup] error: {exc}")
        db.rollback()
    finally:
        db.close()


async def _run_periodic_cleanup() -> None:
    """Startup sweep then hourly OCR + audio file cleanup loop."""
    await _cleanup_ocr_images()
    await _cleanup_audio_files()
    while True:
        await asyncio.sleep(_OCR_CLEANUP_INTERVAL_SECS)
        try:
            await _cleanup_ocr_images()
            await _cleanup_audio_files()
        except Exception as exc:
            print(f"[cleanup] periodic sweep failed: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────────

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

    print("NarratIQ startup: loading BGE-M3 embeddings model...")
    from services.ai_service import get_bge
    get_bge()   # blocks until BGE-M3 is in memory — fast (~3 s on CPU)
    app.state.embeddings_ready = True
    print(f"BGE-M3 loaded on {settings.bge_device}.")

    # ── pgvector path self-check (fail fast) ──────────────────────────────────
    # Validates the embedding → pgvector bind/cast round-trip at boot so a broken
    # vector query surfaces here in the logs, not as a per-request 500. This is
    # the exact failure mode (`:q::vector` bind leak) that silently broke all
    # retrieval after the SQLite→PostgreSQL migration.
    print("NarratIQ startup: verifying pgvector query path...")
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
        print(f"pgvector query path OK (self-similarity={float(_score):.4f}).")
    except Exception as e:
        # Hard failure: retrieval (plot assistant, QA, character RAG) cannot work.
        raise RuntimeError(
            "pgvector query path self-check FAILED — vector retrieval is broken. "
            f"Cause: {type(e).__name__}: {e}. "
            "Check pgvector is installed and the embedding<=>vector cast syntax."
        ) from e

    print(f"NarratIQ startup: connecting to vLLM at {settings.vllm_base_url}...")
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.get(settings.vllm_health_url)
            r.raise_for_status()
            app.state.llm_ready = True
            print("vLLM health check passed.")
        except Exception as e:
            app.state.llm_ready = False
            print(
                f"WARNING: vLLM not reachable at {settings.vllm_health_url} ({e}). "
                "AI generation features will be unavailable until vLLM starts."
            )

    if app.state.llm_ready:
        print("NarratIQ startup: warming up vLLM (first-token pre-heat)...")
        try:
            from services.ai_service import warmup
            await warmup()
            print("vLLM warmup complete — first user request will be fast.")
        except Exception as e:
            print(f"WARNING: vLLM warmup failed ({e}).")

    asyncio.create_task(_run_periodic_cleanup())
    print(f"OCR+Audio cleanup scheduler started "
          f"(confirmed>{_OCR_CONFIRMED_TTL_HOURS}h, "
          f"unconfirmed>{_OCR_UNCONFIRMED_TTL_HOURS}h, "
          f"interval={_OCR_CLEANUP_INTERVAL_SECS//3600}h).")

    print("NarratIQ ready.")
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    # Allow any RunPod proxy domain so both
    # https://{pod-id}-3000.proxy.runpod.net (frontend on RunPod) and
    # http://localhost:3000 (local frontend dev) work without changing .env each time.
    allow_origin_regex=r"https://.*\.proxy\.runpod\.net",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("uploads/ocr",   exist_ok=True)
os.makedirs("uploads/audio", exist_ok=True)

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


@app.get("/api/health")
async def health():
    import os
    vllm_status = "ready" if getattr(app.state, "llm_ready",       False) else "unavailable"
    bge_status  = "ready" if getattr(app.state, "embeddings_ready", False) else "loading"

    # GPU info — populated by start.sh via env vars before FastAPI boots
    gpu_info: dict = {}
    try:
        import torch
        if torch.cuda.is_available():
            gpu_info = {
                "count":              torch.cuda.device_count(),
                "tensor_parallel":    settings.tensor_parallel_size,
                "vram_per_gpu_gb":    round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 1),
                "total_vram_gb":      round(
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
