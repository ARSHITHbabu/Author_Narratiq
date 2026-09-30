"""
Operations endpoints (Stage 10, task 10.2).

  GET  /api/ops/status   — the configuration detail /api/health used to expose
                           publicly (vLLM URL, model, context window, GPU).
  GET  /api/ops/metrics  — the numbers the pod watchdog alerts on.
  GET  /api/ops/errors   — recent scrubbed error records.
  GET  /api/stats        — account/story/chapter counts (moved behind the ops
                           token; it was unauthenticated).
  POST /api/client-errors — frontend error reports (public, rate-limited,
                           size-capped, scrubbed; no authority).

Every /api/ops/* route and /api/stats require `X-Ops-Token` equal to the
OPS_TOKEN setting. With OPS_TOKEN unset they answer 404 — nothing operational
is exposed by default. Nothing here returns author content.
"""
from __future__ import annotations

import hmac
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func

from config import settings
from middleware.rate_limit import get_remote_address, limiter
from services import error_tracking
from services.error_tracking import counters
from services.health_probe import vllm_ready

router = APIRouter(tags=["ops"])
public_router = APIRouter(tags=["ops"])

_STARTED = time.time()


def require_ops_token(request: Request) -> None:
    expected = settings.ops_token or ""
    if not expected:
        raise HTTPException(status_code=404, detail="Not Found")
    sent = request.headers.get("x-ops-token", "")
    if not sent or not hmac.compare_digest(sent, expected):
        raise HTTPException(status_code=403, detail="Forbidden")


@router.get("/status", dependencies=[Depends(require_ops_token)])
async def ops_status(request: Request):
    gpu: dict = {}
    try:
        import torch
        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            gpu = {"count": torch.cuda.device_count(), "tensor_parallel": settings.tensor_parallel_size,
                   "vram_per_gpu_gb": round(props.total_memory / 1024**3, 1)}
    except Exception:                                   # noqa: BLE001
        pass
    return {
        "vllm": "ready" if await vllm_ready() else "unavailable",
        "bge_m3": "ready" if getattr(request.app.state, "embeddings_ready", False) else "loading",
        "gpu": gpu,
        "config": {"vllm_url": settings.vllm_base_url, "vllm_model": settings.vllm_model_name,
                   "max_model_len": settings.max_model_len,
                   "gpu_memory_util": settings.gpu_memory_utilization},
        "uptime_seconds": int(time.time() - _STARTED),
    }


def _job_counts(db, since: datetime) -> dict:
    from models import AudioUpload, ManuscriptJob, NarrativeThreadScan, StoryBible, StoryIntelJob
    specs = [
        ("manuscript_jobs",        ManuscriptJob,       ("error",),             ("processing",)),
        ("story_intel_jobs",       StoryIntelJob,       ("error",),             ("pending", "running")),
        ("story_bibles",           StoryBible,          ("failed", "partial"),  ("running",)),
        ("narrative_thread_scans", NarrativeThreadScan, ("failed",),            ("pending", "running")),
        ("audio_uploads",          AudioUpload,         ("failed",),            ("processing",)),
    ]
    out = {}
    for name, model, failed, active in specs:
        out[name] = {
            "failed_last_60m": db.query(func.count()).select_from(model)
                                 .filter(model.status.in_(failed), model.updated_at >= since).scalar() or 0,
            "in_progress": db.query(func.count()).select_from(model)
                             .filter(model.status.in_(active)).scalar() or 0,
        }
    return out


def _backup_status() -> dict:
    """Read-only view of the on-pod backup state written by the backup scripts."""
    backup_dir = Path(os.environ.get("NARRATIQ_BACKUP_DIR", "/workspace/backups"))
    out: dict = {"dir_exists": backup_dir.is_dir(), "latest_dump_age_hours": None, "last_verify": None,
                 "last_offpod": None}
    try:
        dumps = sorted(backup_dir.glob("narratiq-2*.dump"), key=lambda p: p.stat().st_mtime)
        if dumps:
            out["latest_dump_age_hours"] = round((time.time() - dumps[-1].stat().st_mtime) / 3600, 2)
        for key, name in (("last_verify", "LAST-VERIFY.json"), ("last_offpod", "LAST-OFFPOD.json")):
            f = backup_dir / name
            if f.is_file():
                out[key] = json.loads(f.read_text())
    except Exception:                                   # noqa: BLE001 — status is best effort
        pass
    return out


@router.get("/metrics", dependencies=[Depends(require_ops_token)])
async def ops_metrics(request: Request):
    from database import SessionLocal
    from models import ErrorEvent
    from services.ai_service import parser_metrics

    since = datetime.utcnow() - timedelta(minutes=60)
    db = SessionLocal()
    try:
        jobs = _job_counts(db, since)
        errors_60m = db.query(func.coalesce(func.sum(ErrorEvent.occurrences), 0)).filter(
            ErrorEvent.last_seen >= since).scalar() or 0
    finally:
        db.close()
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "uptime_seconds": int(time.time() - _STARTED),
        "vllm": "ready" if await vllm_ready() else "unavailable",
        "http": {"last_5m": counters.window(5), "last_15m": counters.window(15),
                 "last_60m": counters.window(60)},
        # Cumulative since process start; the watchdog alerts on deltas.
        "ai_parse": parser_metrics(),
        "background_jobs": jobs,
        "orphan_recovery": getattr(request.app.state, "orphan_recovery", None),
        "error_events_last_60m": int(errors_60m),
        "backups": _backup_status(),
    }


@router.get("/errors", dependencies=[Depends(require_ops_token)])
def ops_errors(limit: int = 50):
    from database import SessionLocal
    from models import ErrorEvent
    db = SessionLocal()
    try:
        rows = (db.query(ErrorEvent).order_by(ErrorEvent.last_seen.desc())
                  .limit(max(1, min(limit, 200))).all())
        return [{"source": r.source, "kind": r.kind, "route": r.route, "method": r.method,
                 "status_code": r.status_code, "message": r.message, "stack": r.stack,
                 "occurrences": r.occurrences, "first_seen": r.first_seen.isoformat() + "Z",
                 "last_seen": r.last_seen.isoformat() + "Z", "request_id": r.request_id} for r in rows]
    finally:
        db.close()


@public_router.get("/api/stats", dependencies=[Depends(require_ops_token)])
def stats():
    from database import SessionLocal
    from models import Chapter, Story, User
    db = SessionLocal()
    try:
        return {"users": db.query(User).count(), "stories": db.query(Story).count(),
                "chapters": db.query(Chapter).count()}
    finally:
        db.close()


class ClientErrorIn(BaseModel):
    kind:    str = Field(default="Error", max_length=120)
    message: str = Field(default="", max_length=2000)
    stack:   str = Field(default="", max_length=8000)
    route:   str = Field(default="", max_length=300)   # the page's route pattern, e.g. /projects/[id]/write


def _frontend_stack(stack: str) -> str:
    """Keep only 'at fn (file:line:col)' frame lines; drop anything else."""
    frames = []
    for line in (stack or "").splitlines():
        line = line.strip()
        if line.startswith("at ") or "@" in line and ".js" in line:
            frames.append(error_tracking.scrub(line)[:200])
    return "\n".join(frames[:error_tracking.STACK_MAX_FRAMES])


@public_router.post("/api/client-errors", status_code=202)
@limiter.limit(settings.rate_limit_client_errors, key_func=get_remote_address)
def client_error(request: Request, body: ClientErrorIn):
    counters.incr("client_errors")
    route = body.route if body.route.startswith("/") else ""
    # Concrete ids in a page path are replaced so records group by page type.
    route = error_tracking.scrub(route).replace(" ", "")[:300]
    error_tracking.record_event(source="frontend", kind=body.kind, route=route or None,
                                request_id=getattr(request.state, "request_id", None),
                                message=body.message, stack=_frontend_stack(body.stack))
    return {"accepted": True}
