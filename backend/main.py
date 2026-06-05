from contextlib import asynccontextmanager
import os
import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import engine, Base, run_db_migrations
import models  # noqa: F401

from routers import auth, projects, chapters, intake, plot_assistant, ai_transform, ocr, manuscript, export, characters
from routers import search as search_router

Base.metadata.create_all(bind=engine)
run_db_migrations(engine)   # add new columns to existing tables


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

os.makedirs("uploads/ocr", exist_ok=True)

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
