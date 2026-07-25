"""
Voice Analytics & Observability (D).

Raw capture (per turn) → voice_commands (+ voice_tasks per node). A periodic
rollup aggregates raw rows into voice_usage_daily (per user + global). Dashboard
queries power GET /api/voice/analytics/*.

Metrics covered: usage (sessions, commands, active users), intent/capability
distribution, quality (low-confidence, clarification, failed resolution/exec,
abandoned workflows), performance (stt/e2e p95), business (voice→applied).

Alert thresholds (documented for monitoring): failure_rate>0.05,
clarification_rate>0.25, stt_p95_ms>4000, e2e_p95_ms>6000.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from . import lifecycle

logger = logging.getLogger(__name__)


def record_turn(db, *, session, command_id, graph, timings, status, confidence,
                intent, capability, action_type, requires_confirmation,
                resolved_references, parameters, transcript, cleaned, user_id,
                story_id, result_summary) -> None:
    """Persist a VoiceCommand row plus the VoiceWorkflow/VoiceTask graph. Caller commits."""
    from models import VoiceCommand, VoiceWorkflow, VoiceTask

    vcmd = VoiceCommand(
        command_id=command_id,
        session_id=session.session_id,
        user_id=user_id,
        story_id=story_id,
        raw_transcript=transcript or "",
        cleaned_transcript=cleaned or "",
        resolved_references=resolved_references or {},
        detected_intent=intent or "",
        capability=capability or "",
        target_router=_router_for(capability),
        action_type=action_type or "",
        confidence=float(confidence or 0.0),
        requires_confirmation=bool(requires_confirmation),
        parameters=_safe_params(parameters),
        status=status,
        result_summary=(result_summary or "")[:2000],
        stt_ms=int(timings.get("stt_ms", 0)),
        llm_ms=int(timings.get("llm_ms", 0)),
        route_ms=int(timings.get("route_ms", 0)),
        exec_ms=int(timings.get("exec_ms", 0)),
        latency_ms=int(timings.get("latency_ms", 0)),
        created_at=datetime.utcnow(),
    )
    db.add(vcmd)

    if graph and graph.nodes:
        import uuid as _uuid
        workflow_id = str(_uuid.uuid4())   # assign explicitly: default fires only on flush
        wf = VoiceWorkflow(
            workflow_id=workflow_id,
            command_id=command_id,
            session_id=session.session_id,
            node_count=len(graph.nodes),
            # NOT "completed": at this point client-locus nodes have only been
            # dispatched. The workflow reaches a terminal status when its nodes
            # report their outcomes (task 3.7).
            status=lifecycle.derive_command_status([n.status for n in graph.nodes]),
            graph_json={"is_multi_step": graph.is_multi_step,
                        "nodes": [n.node_key for n in graph.nodes]},
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(wf)
        db.flush()   # ensure the workflow row exists before its tasks (FK order)
        for n in graph.nodes:
            db.add(VoiceTask(
                workflow_id=workflow_id,
                node_key=n.node_key,
                capability=n.capability,
                action=n.action,
                action_type=n.action_type,
                depends_on=list(n.depends_on),
                params=_safe_params(n.params),
                execution_locus=n.execution_locus,
                requires_confirmation=bool(n.requires_confirmation),
                status=n.status,
                result_summary=(n.user_message or "")[:1000],
                created_at=datetime.utcnow(),
            ))


def _router_for(capability: str) -> str:
    from .capabilities import CAPABILITY_REGISTRY
    cap = CAPABILITY_REGISTRY.get(capability or "")
    return cap.router if cap else ""


def _safe_params(params: dict | None) -> dict:
    """Drop bulky/internal fields before persisting (text bodies, _deps)."""
    if not isinstance(params, dict):
        return {}
    out = {}
    for k, v in params.items():
        if k.startswith("_"):
            continue
        if isinstance(v, str) and len(v) > 400:
            out[k] = v[:400] + "…"
        else:
            out[k] = v
    return out


# ── Daily rollup ──────────────────────────────────────────────────────────────

def _p95(values: list[int]) -> int:
    if not values:
        return 0
    s = sorted(values)
    idx = min(len(s) - 1, int(round(0.95 * (len(s) - 1))))
    return int(s[idx])


def rollup_daily(day: str | None = None) -> dict:
    """Aggregate one UTC day of raw rows into voice_usage_daily (global row,
    user_id=None). Idempotent upsert. Returns the computed global metrics."""
    from database import SessionLocal
    from models import VoiceCommand, VoiceSession, VoiceUsageDaily
    from sqlalchemy import func

    day = day or datetime.utcnow().strftime("%Y-%m-%d")
    start = datetime.strptime(day, "%Y-%m-%d")
    end = start + timedelta(days=1)

    db = SessionLocal()
    try:
        cmds = (db.query(VoiceCommand)
                .filter(VoiceCommand.created_at >= start, VoiceCommand.created_at < end)
                .all())
        sessions = (db.query(VoiceSession)
                    .filter(VoiceSession.started_at >= start, VoiceSession.started_at < end)
                    .all())

        intents: dict[str, int] = {}
        caps: dict[str, int] = {}
        low = clar = failed = 0
        e2e = [c.latency_ms or 0 for c in cmds]
        stt = [c.stt_ms or 0 for c in cmds]
        for c in cmds:
            if c.detected_intent:
                intents[c.detected_intent] = intents.get(c.detected_intent, 0) + 1
            if c.capability:
                caps[c.capability] = caps.get(c.capability, 0) + 1
            if (c.confidence or 0) < 0.5:
                low += 1
            if c.status == "needs_clarification":
                clar += 1
            if c.status == "failed":
                failed += 1

        durations = [
            (s.ended_at - s.started_at).total_seconds()
            for s in sessions if s.ended_at and s.started_at
        ]
        metrics = dict(
            sessions=len(sessions),
            commands=len(cmds),
            avg_session_seconds=round(sum(durations) / len(durations), 1) if durations else 0.0,
            intent_distribution=intents,
            capability_usage=caps,
            low_confidence=low,
            clarifications=clar,
            failed_resolutions=clar,
            failed_executions=failed,
            abandoned_workflows=sum(1 for s in sessions if s.status in ("failed", "cancelled")),
            stt_p95_ms=_p95(stt),
            e2e_p95_ms=_p95(e2e),
            voice_to_applied=sum(1 for c in cmds if c.confirmed),
        )

        row = (db.query(VoiceUsageDaily)
               .filter(VoiceUsageDaily.day == day, VoiceUsageDaily.user_id.is_(None))
               .first())
        if not row:
            row = VoiceUsageDaily(day=day, user_id=None, created_at=datetime.utcnow())
            db.add(row)
        for k, v in metrics.items():
            setattr(row, k, v)
        row.updated_at = datetime.utcnow()
        db.commit()
        logger.info("[voice.analytics] rollup %s: %d commands, %d sessions", day, len(cmds), len(sessions))
        return metrics
    except Exception as exc:                       # noqa: BLE001
        logger.error("[voice.analytics] rollup failed: %s", exc)
        db.rollback()
        return {}
    finally:
        db.close()


def compute_summary(db, days: int = 7) -> dict:
    """Live summary over the last `days` from raw voice_commands."""
    from models import VoiceCommand, VoiceSession

    since = datetime.utcnow() - timedelta(days=days)
    cmds = db.query(VoiceCommand).filter(VoiceCommand.created_at >= since).all()
    sessions = db.query(VoiceSession).filter(VoiceSession.started_at >= since).all()

    total = len(cmds)
    intents: dict[str, int] = {}
    caps: dict[str, int] = {}
    low = clar = failed = applied = 0
    for c in cmds:
        if c.detected_intent:
            intents[c.detected_intent] = intents.get(c.detected_intent, 0) + 1
        if c.capability:
            caps[c.capability] = caps.get(c.capability, 0) + 1
        if (c.confidence or 0) < 0.5:
            low += 1
        if c.status == "needs_clarification":
            clar += 1
        if c.status == "failed":
            failed += 1
        if c.confirmed:
            applied += 1

    n_sessions = len(sessions)
    return dict(
        range_days=days,
        total_sessions=n_sessions,
        total_commands=total,
        active_users=len({c.user_id for c in cmds}),
        avg_commands_per_session=round(total / n_sessions, 2) if n_sessions else 0.0,
        clarification_rate=round(clar / total, 3) if total else 0.0,
        failure_rate=round(failed / total, 3) if total else 0.0,
        low_confidence_rate=round(low / total, 3) if total else 0.0,
        voice_to_applied=applied,
        intent_distribution=dict(sorted(intents.items(), key=lambda x: -x[1])[:25]),
        capability_usage=dict(sorted(caps.items(), key=lambda x: -x[1])[:25]),
        stt_p95_ms=_p95([c.stt_ms or 0 for c in cmds]),
        e2e_p95_ms=_p95([c.latency_ms or 0 for c in cmds]),
    )
