"""
Real-Time Voice Agent router.

  WS   /api/voice/stream                      — streaming mic → partials → final plan
  POST /api/voice/transcribe                  — one-shot audio blob → transcript
  POST /api/voice/interpret                   — STT-free agent core (primary test surface)
  POST /api/voice/sessions/{id}/remember      — push a client-executed result into memory (B)
  POST /api/voice/commands/{id}/confirm       — record confirmation / applied conversion
  GET  /api/voice/sessions/{id}               — session history
  GET  /api/voice/analytics/{summary|intents|performance}  — dashboards (admin)

Execution model: the agent PLANS; the frontend EXECUTES via api.ts. These
endpoints never call other feature routers — they return a structured plan.
"""
import json
import logging
import os
import time
import uuid

from fastapi import (APIRouter, Depends, HTTPException, Request, WebSocket,
                     WebSocketDisconnect)
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from middleware.rate_limit import limiter, get_user_id
from models import User, VoiceSession, VoiceCommand, VoiceWorkflow, VoiceTask
from schemas import (VoiceInterpretRequest, VoiceAgentResponse, VoiceTranscribeResponse,
                     VoiceContext, VoiceWorkflowConfirmRequest, VoiceSessionHistory,
                     VoiceSessionOut, VoiceCommandOut, VoiceAnalyticsSummary,
                     VoiceNodeResultRequest, VoiceNodeResultResponse)
from routers.auth import get_current_user, decode_token
from services.voice import agent as voice_agent
from services.voice import analytics as voice_analytics
from services.voice import lifecycle

logger = logging.getLogger(__name__)

router = APIRouter(tags=["voice"])


def _require_enabled() -> None:
    if not settings.voice_agent_enabled:
        raise HTTPException(status_code=503, detail="Voice agent is disabled")


def _require_admin(user: User) -> None:
    admins = settings.voice_admin_emails or []
    if admins and user.email not in admins:
        raise HTTPException(status_code=403, detail="Admin access required")


# ══════════════════════════════════════════════════════════════════════════════
#  REST — agent core
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/interpret", response_model=VoiceAgentResponse)
@limiter.limit(settings.rate_limit_voice, key_func=get_user_id)
async def interpret(
    request: Request,
    body: VoiceInterpretRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """STT-free agent core: transcript + context → consolidated plan."""
    _require_enabled()
    if not (body.transcript or "").strip():
        raise HTTPException(status_code=422, detail="Empty transcript")
    return await voice_agent.interpret(
        db, current_user, body.transcript, body.context,
        session_id=body.session_id, skip_clean=body.skip_clean,
    )


@router.post("/transcribe", response_model=VoiceTranscribeResponse)
@limiter.limit(settings.rate_limit_voice, key_func=get_user_id)
async def transcribe(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """One-shot transcription of an uploaded audio blob (fallback / non-WS path)."""
    _require_enabled()
    from fastapi import UploadFile
    form = await request.form()
    file: UploadFile = form.get("file")
    if file is None:
        raise HTTPException(status_code=422, detail="No 'file' provided")

    content = await file.read()
    actual_mb = len(content) / (1024 * 1024)
    if actual_mb > settings.max_voice_audio_mb:
        from exceptions import UploadTooLargeError
        raise UploadTooLargeError(limit_mb=settings.max_voice_audio_mb, actual_mb=actual_mb)

    os.makedirs(settings.upload_dir_audio, exist_ok=True)
    ext = os.path.splitext(file.filename or "voice.webm")[1] or ".webm"
    path = os.path.join(settings.upload_dir_audio, f"voice-{uuid.uuid4()}{ext}")
    with open(path, "wb") as f:
        f.write(content)
    try:
        from services.audio_service import transcribe_audio, clean_transcript
        result = await transcribe_audio(path)
        raw = result.get("raw_transcript", "")
        cleaned = await clean_transcript(raw) if raw else ""
        return VoiceTranscribeResponse(
            transcript=raw, cleaned_transcript=cleaned or raw,
            confidence=result.get("confidence", 0.0),
            language=result.get("language_detected", ""),
            duration_seconds=result.get("duration_seconds", 0.0),
        )
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# ══════════════════════════════════════════════════════════════════════════════
#  Session memory + confirmation tracking
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/sessions/{session_id}/remember")
def remember(
    session_id: str,
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Push a client-executed result (e.g. continuation options) into session
    memory so follow-ups like 'use the second option' resolve (B)."""
    _require_enabled()
    sess = (db.query(VoiceSession)
            .filter(VoiceSession.session_id == session_id,
                    VoiceSession.user_id == current_user.user_id).first())
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    from services.voice.session_memory import VoiceSessionContextManager
    mem = VoiceSessionContextManager.load(session_id, db)
    kind = payload.get("result_kind")
    output = payload.get("output")
    mem.record_turn(command=mem.get("last_command", ""),
                    intent=mem.get("last_intent", ""),
                    capability=mem.get("last_capability", ""),
                    result_kind=kind, output=output)
    mem.save(db)
    db.commit()
    return {"ok": True}


@router.post("/commands/{command_id}/confirm")
def confirm_command(
    command_id: str,
    body: VoiceWorkflowConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Record that a proposed (mutating) action was confirmed and/or applied —
    drives the voice→applied conversion metric and per-node status."""
    _require_enabled()
    cmd = (db.query(VoiceCommand)
           .filter(VoiceCommand.command_id == command_id,
                   VoiceCommand.user_id == current_user.user_id).first())
    if not cmd:
        raise HTTPException(status_code=404, detail="Command not found")
    # `confirmed` means the author approved it — nothing more. Whether it then
    # WORKED arrives separately, via the result endpoint below. Conflating the
    # two is what let an approval be recorded as a completed data change
    # (task 3.7).
    cmd.confirmed = bool(body.confirmed)

    wf = db.query(VoiceWorkflow).filter(VoiceWorkflow.command_id == command_id).first()
    if wf:
        task = (db.query(VoiceTask)
                .filter(VoiceTask.workflow_id == wf.workflow_id,
                        VoiceTask.node_key == body.node_key).first())
        if task:
            task.confirmed = bool(body.confirmed)
            if not body.confirmed:
                lifecycle.transition(task, lifecycle.SKIPPED, source="confirm_endpoint",
                                     reason="author declined", strict=False)
            else:
                # Approved → it is being run, not done. `applied` is the
                # executor's claim that it ran; the outcome still comes from the
                # result report.
                lifecycle.transition(task, lifecycle.EXECUTING, source="confirm_endpoint",
                                     reason="author approved", strict=False)
        _resync_workflow(db, wf)
    db.commit()
    return {"ok": True, "confirmed": cmd.confirmed}


def _resync_workflow(db: Session, wf: VoiceWorkflow) -> str:
    """Recompute a workflow's status from its tasks. Derived, never assigned."""
    tasks = db.query(VoiceTask).filter(VoiceTask.workflow_id == wf.workflow_id).all()
    lifecycle.expire_stale_nodes(tasks, settings.voice_execution_timeout_seconds)
    derived = lifecycle.derive_command_status([t.status for t in tasks])
    wf.status = derived
    wf.updated_at = datetime.utcnow()
    return derived


@router.post("/commands/{command_id}/nodes/{node_key}/result",
             response_model=VoiceNodeResultResponse)
def report_node_result(
    command_id: str,
    node_key: str,
    body: VoiceNodeResultRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Record what actually happened when an action ran.

    The missing half of the loop: client-side actions execute in the browser, so
    the backend cannot know their outcome unless the browser says so. Without
    this, a command's status was whatever the backend assumed at planning time —
    which is how the agent came to confirm chapter creations that never
    happened (Phase 2 Issue 5).

    Idempotent per (command, node). A report for a node that has already reached
    a terminal status is recorded as `recorded=false` and changes nothing: a
    late or duplicated message must never resurrect a finished node, least of
    all turn a recorded failure into a success.
    """
    _require_enabled()

    # 1 + 2 — authenticated user owns this command.
    cmd = (db.query(VoiceCommand)
           .filter(VoiceCommand.command_id == command_id,
                   VoiceCommand.user_id == current_user.user_id).first())
    if not cmd:
        raise HTTPException(status_code=404, detail="Command not found")

    wf = db.query(VoiceWorkflow).filter(VoiceWorkflow.command_id == command_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="No workflow for this command")

    # 3 — the node belongs to this command's workflow.
    task = (db.query(VoiceTask)
            .filter(VoiceTask.workflow_id == wf.workflow_id,
                    VoiceTask.node_key == node_key).first())
    if not task:
        raise HTTPException(status_code=404, detail="Step not found for this command")

    # 4 — still active. Terminal nodes are closed; say so rather than pretend.
    if task.status in lifecycle.TERMINAL:
        logger.info("[voice] duplicate result for %s/%s ignored (already %s)",
                    command_id[:8], node_key, task.status)
        return VoiceNodeResultResponse(
            node_key=node_key, node_status=task.status,
            command_status=_resync_workflow(db, wf) or wf.status, recorded=False,
        )

    # A node still sitting in a pre-dispatch status is moved through EXECUTING,
    # so SUCCEEDED is never reached from anywhere else.
    if task.status not in (lifecycle.EXECUTING,):
        lifecycle.transition(task, lifecycle.EXECUTING, source="result_endpoint",
                             reason="executor reported", strict=False)

    lifecycle.transition(
        task, lifecycle.SUCCEEDED if body.ok else lifecycle.FAILED,
        source="result_endpoint",
        reason=body.error_code or ("executor reported success" if body.ok else "executor reported failure"),
        strict=False,
    )
    if body.message:
        task.result_summary = body.message[:1000]

    command_status = _resync_workflow(db, wf)
    cmd.status = command_status
    tasks = db.query(VoiceTask).filter(VoiceTask.workflow_id == wf.workflow_id).all()
    cmd.result_summary = lifecycle.summarize_outcome([t.status for t in tasks])[:1000]
    db.commit()

    return VoiceNodeResultResponse(
        node_key=node_key, node_status=task.status,
        command_status=command_status, recorded=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  History + analytics
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/sessions/{session_id}", response_model=VoiceSessionHistory)
def get_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_enabled()
    sess = (db.query(VoiceSession)
            .filter(VoiceSession.session_id == session_id,
                    VoiceSession.user_id == current_user.user_id).first())
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    cmds = (db.query(VoiceCommand)
            .filter(VoiceCommand.session_id == session_id)
            .order_by(VoiceCommand.created_at.asc()).all())
    return VoiceSessionHistory(
        session=VoiceSessionOut.model_validate(sess),
        commands=[VoiceCommandOut.model_validate(c) for c in cmds],
    )


@router.get("/analytics/summary", response_model=VoiceAnalyticsSummary)
def analytics_summary(
    days: int = 7,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_enabled()
    _require_admin(current_user)
    return voice_analytics.compute_summary(db, days=max(1, min(days, 90)))


@router.get("/analytics/intents")
def analytics_intents(
    days: int = 7,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_enabled()
    _require_admin(current_user)
    s = voice_analytics.compute_summary(db, days=max(1, min(days, 90)))
    return {"range_days": s["range_days"], "intent_distribution": s["intent_distribution"],
            "capability_usage": s["capability_usage"]}


@router.get("/analytics/performance")
def analytics_performance(
    days: int = 7,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_enabled()
    _require_admin(current_user)
    s = voice_analytics.compute_summary(db, days=max(1, min(days, 90)))
    return {"range_days": s["range_days"], "stt_p95_ms": s["stt_p95_ms"],
            "e2e_p95_ms": s["e2e_p95_ms"], "failure_rate": s["failure_rate"],
            "clarification_rate": s["clarification_rate"],
            "low_confidence_rate": s["low_confidence_rate"]}


# ══════════════════════════════════════════════════════════════════════════════
#  WebSocket — streaming mic
# ══════════════════════════════════════════════════════════════════════════════

@router.websocket("/stream")
async def voice_stream(websocket: WebSocket):
    """
    Protocol:
      client → {"type":"start","context":{...},"session_id":"?"} then binary audio frames,
               then {"type":"stop"} or {"type":"cancel"}
      server → {"type":"partial","transcript":...}
               {"type":"state","value":"transcribing|thinking"}
               {"type":"final","response":<VoiceAgentResponse>}
               {"type":"error","code":...,"message":...}
    """
    await websocket.accept()

    if not settings.voice_agent_enabled:
        await websocket.send_json({"type": "error", "code": "disabled",
                                   "message": "Voice agent is disabled"})
        await websocket.close()
        return

    # ── Authenticate via ?token= query param ─────────────────────────────────
    token = websocket.query_params.get("token", "")
    user = None
    db = None
    try:
        from database import SessionLocal
        db = SessionLocal()
        user_id = decode_token(token)              # raises 401 on bad token
        user = db.query(User).filter(User.user_id == user_id).first()
        if not user:
            raise ValueError("user not found")
    except Exception:
        await websocket.send_json({"type": "error", "code": "unauthorized",
                                   "message": "Invalid or missing token"})
        await websocket.close()
        if db:
            db.close()
        return

    from services.voice.stt_stream import STTSession
    stt: STTSession | None = None
    latest_context: dict = {}
    session_id: str | None = None

    try:
        while True:
            msg = await websocket.receive()
            if msg.get("type") == "websocket.disconnect":
                break

            if "bytes" in msg and msg["bytes"] is not None:
                if stt is None:
                    stt = STTSession(settings.upload_dir_audio)
                stt.add_chunk(msg["bytes"])
                partial = await stt.maybe_partial()
                if partial:
                    await websocket.send_json({"type": "partial", "transcript": partial})
                continue

            if "text" in msg and msg["text"]:
                try:
                    ctrl = json.loads(msg["text"])
                except json.JSONDecodeError:
                    continue
                mtype = ctrl.get("type")

                if mtype == "start":
                    latest_context = ctrl.get("context", {}) or {}
                    session_id = ctrl.get("session_id") or session_id
                    if stt:
                        stt.cleanup()
                    stt = STTSession(settings.upload_dir_audio)
                    await websocket.send_json({"type": "state", "value": "listening"})

                elif mtype == "cancel":
                    if stt:
                        stt.cleanup()
                        stt = None

                elif mtype == "stop":
                    if ctrl.get("context"):
                        latest_context = ctrl["context"]
                    await websocket.send_json({"type": "state", "value": "transcribing"})
                    t_stt = time.monotonic()
                    final = await stt.finalize() if stt else {"raw_transcript": ""}
                    stt_ms = int((time.monotonic() - t_stt) * 1000)
                    raw = (final.get("raw_transcript") or "").strip()

                    if not raw:
                        await websocket.send_json({"type": "error", "code": "no_speech",
                                                   "message": "I didn't catch that — please try again."})
                        if stt:
                            stt.cleanup()
                            stt = None
                        continue

                    await websocket.send_json({"type": "state", "value": "thinking"})
                    context = VoiceContext(**_coerce_context(latest_context))
                    resp = await voice_agent.interpret(
                        db, user, raw, context, session_id=session_id,
                    )
                    # carry STT latency into the persisted row best-effort
                    resp_dict = resp.model_dump()
                    resp_dict.setdefault("_stt_ms", stt_ms)
                    session_id = resp.session_id
                    await websocket.send_json({"type": "final", "response": resp.model_dump()})
                    if stt:
                        stt.cleanup()
                        stt = None

    except WebSocketDisconnect:
        pass
    except Exception as exc:                       # noqa: BLE001
        logger.warning("[voice.ws] error: %s", exc)
        try:
            await websocket.send_json({"type": "error", "code": "server_error",
                                       "message": "Voice processing failed."})
        except Exception:
            pass
    finally:
        if stt:
            stt.cleanup()
        if session_id and db:
            try:
                sess = db.query(VoiceSession).filter(VoiceSession.session_id == session_id).first()
                if sess and sess.status == "active":
                    from datetime import datetime
                    sess.status = "completed"
                    sess.ended_at = datetime.utcnow()
                    db.commit()
            except Exception:
                db.rollback()
        if db:
            db.close()


def _coerce_context(raw: dict) -> dict:
    """Keep only known VoiceContext fields (defensive against extra client keys)."""
    allowed = set(VoiceContext.model_fields.keys())
    return {k: v for k, v in (raw or {}).items() if k in allowed}
