"""
Voice Agent facade — the single entry point that orchestrates every layer and
returns the consolidated VoiceAgentResponse. STT-free and fully unit-testable
(this is what POST /api/voice/interpret calls).

Pipeline: session → memory → normalize → reference → plan → safety →
orchestrate → consolidate → persist/analytics → save memory.
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime

from . import (analytics, catalog, clarify, normalize, orchestrator, planner,
               reference, safety, vocabulary)
from . import lifecycle
from .capabilities import CAPABILITY_REGISTRY, get_action
from .context import summarize_context
from .session_memory import VoiceSessionContextManager

logger = logging.getLogger(__name__)


def _get_or_create_session(db, user_id: str, story_id, session_id):
    from models import VoiceSession
    if session_id:
        row = (db.query(VoiceSession)
               .filter(VoiceSession.session_id == session_id,
                       VoiceSession.user_id == user_id).first())
        if row:
            if story_id and not row.story_id:
                row.story_id = story_id
            return row
    row = VoiceSession(user_id=user_id, story_id=story_id, status="active",
                       context_state={}, started_at=datetime.utcnow())
    db.add(row)
    db.flush()   # assign session_id without committing
    return row


def _node_out(node) -> dict:
    from schemas import WorkflowNodeOut, VoiceExecution
    execution = None
    if node.execution_locus == "client":
        execution = VoiceExecution(
            client_call=node.client_call,
            args={k: v for k, v in node.params.items() if not k.startswith("_")},
        )
    return WorkflowNodeOut(
        node_key=node.node_key,
        capability=node.capability,
        action=node.action,
        action_type=node.action_type,
        depends_on=node.depends_on,
        execution_locus=node.execution_locus,
        requires_confirmation=node.requires_confirmation,
        status=node.status,
        execution=execution,
        result=node.result,
        user_message=node.user_message,
    )


async def interpret(db, user, transcript: str, context, session_id: str | None = None,
                    skip_clean: bool = False):
    """Run one voice turn. Returns a schemas.VoiceAgentResponse."""
    from schemas import (VoiceAgentResponse, WorkflowOut, VoiceClarification)

    t_start = time.monotonic()
    timings = {"stt_ms": 0, "llm_ms": 0, "route_ms": 0, "exec_ms": 0}
    story_id = getattr(context, "story_id", None)

    session = _get_or_create_session(db, user.user_id, story_id, session_id)
    memory = VoiceSessionContextManager.load(session.session_id, db)
    command_id = str(uuid.uuid4())

    cleaned = (transcript or "").strip()
    command = normalize.normalize_command(cleaned)

    # Stitch a pending clarification answer onto the original command.
    pending = memory.pop_pending_clarification()
    if pending and pending.get("transcript"):
        command = f"{pending['transcript']} {command}".strip()

    # ── Story-aware transcript correction (B) ─────────────────────────────────
    from config import settings as _cfg
    corrections: list = []
    resolved_entities: list = []
    if _cfg.voice_vocab_enabled and story_id:
        vocab = vocabulary.build_story_vocabulary(story_id, db)
        command, corrections = vocabulary.correct_transcript(
            command, vocab, min_score=_cfg.voice_vocab_fuzzy_min)
        resolved_entities = [{"name": c["to"], "kind": c["kind"]} for c in corrections]

    # ── Reference resolution (B) + entity pre-resolution from corrections ─────
    refs = reference.resolve(command, memory, context)
    for c in corrections:
        if c["kind"] == "character" and c.get("ref_id") and not refs.character_id:
            refs.character_id = c["ref_id"]; refs.character_name = c["to"]
        elif c["kind"] == "chapter" and c.get("ref_id") and not refs.chapter_id:
            refs.chapter_id = c["ref_id"]

    # ── Plan (A) ──────────────────────────────────────────────────────────────
    context_brief = summarize_context(context, memory)
    has_selection = bool(getattr(context, "has_selection", False)
                         and getattr(context, "selected_text", None))
    t_llm = time.monotonic()
    graph = await planner.plan(command, context_brief, has_selection=has_selection)
    timings["llm_ms"] = int((time.monotonic() - t_llm) * 1000)

    # No capability matched → clarification with closest options.
    if not graph.nodes:
        closest = [c for c, _ in catalog.shortlist(command, k=4)]
        resp = _finalize(
            db, session, memory, command_id, transcript, cleaned, refs, graph,
            context=context, corrected_transcript=command, resolved_entities=resolved_entities,
            status="needs_clarification", confidence=graph.confidence,
            primary=None, timings=timings, t_start=t_start, user_id=user.user_id,
            story_id=story_id,
            user_message="I'm not sure which feature you meant.",
            clarification=VoiceClarification(
                question="Which would you like?",
                missing=[],
                options=[{"capability": c, "description": CAPABILITY_REGISTRY[c].description}
                         for c in closest if c in CAPABILITY_REGISTRY],
            ),
        )
        return resp

    # ── Safety (per-node confirmation) ────────────────────────────────────────
    requires_confirmation = safety.apply(graph, graph.confidence)

    # ── Orchestrate (server pre-run + client plan) ────────────────────────────
    t_route = time.monotonic()
    exec_info = await orchestrator.execute(graph, context, refs, memory, db, user=user)
    timings["exec_ms"] = exec_info["exec_ms"]
    context_used = exec_info.get("context_used", "")
    timings["route_ms"] = int((time.monotonic() - t_route) * 1000) - exec_info["exec_ms"]
    if timings["route_ms"] < 0:
        timings["route_ms"] = 0

    primary = graph.nodes[0]

    # ── Status determination ──────────────────────────────────────────────────
    from config import settings
    clarification = None
    if exec_info["any_needs_input"]:
        status = "needs_clarification"
        missing = sorted(set(exec_info["missing"]))
        question, options = clarify.build_clarification(
            missing, story_id, db, capability=primary.capability)
        clarification = VoiceClarification(question=question, missing=missing, options=options)
        memory.set_pending_clarification({"transcript": command, "missing": missing})
    elif graph.confidence < settings.voice_low_confidence_floor and not graph.is_multi_step:
        status = "needs_clarification"
        closest = [c for c, _ in catalog.shortlist(command, k=4)]
        clarification = VoiceClarification(
            question="Did you mean one of these?",
            options=[{"capability": c, "description": CAPABILITY_REGISTRY[c].description}
                     for c in closest if c in CAPABILITY_REGISTRY],
        )
    elif requires_confirmation:
        status = "needs_confirmation"
    else:
        # Derived from what the nodes actually did — never from "the plan was
        # built". Client-locus nodes are READY here: dispatched, outcome
        # unknown, so the command reports EXECUTING until their results are
        # reported back. This assignment is the whole of Phase 2 Issue 5: it
        # used to read `status = "success"` while nothing had run.
        status = lifecycle.derive_command_status(n.status for n in graph.nodes)

    return _finalize(
        db, session, memory, command_id, transcript, cleaned, refs, graph,
        context=context, corrected_transcript=command, resolved_entities=resolved_entities,
        status=status, confidence=graph.confidence, primary=primary,
        timings=timings, t_start=t_start, user_id=user.user_id, story_id=story_id,
        user_message=_consolidate_message(graph, status),
        clarification=clarification, requires_confirmation=requires_confirmation,
        context_used=context_used,
    )


def _consolidate_message(graph, status: str) -> str:
    """Author-facing summary. Says what has happened so far — nothing about a
    client action is claimed until its executor reports back."""
    # Skip nodes whose answer is rendered by the AnswerCard (server_sync Q&A) so
    # the natural-language answer isn't duplicated in the header line.
    parts = [
        n.user_message for n in graph.topo_order()
        if n.user_message and not (isinstance(n.result, dict) and n.result.get("answer"))
    ]
    base = " ".join(parts)
    if status == "needs_confirmation":
        return (base + " Confirm to apply.").strip()
    return base


def _finalize(db, session, memory, command_id, transcript, cleaned, refs, graph,
              *, context, status, confidence, primary, timings, t_start, user_id,
              story_id, user_message, clarification=None, requires_confirmation=False,
              corrected_transcript="", resolved_entities=None, context_used=""):
    from schemas import VoiceAgentResponse, WorkflowOut

    timings["latency_ms"] = int((time.monotonic() - t_start) * 1000)

    capability = primary.capability if primary else ""
    action = primary.action if primary else ""
    action_type = primary.action_type if primary else ""
    target_router = CAPABILITY_REGISTRY[capability].router if capability in CAPABILITY_REGISTRY else ""
    intent_key = f"{capability}.{action}" if capability else ""

    # consolidated server results
    result: dict = {}
    for n in (graph.nodes if graph else []):
        if n.result is not None:
            result[n.node_key] = n.result

    workflow_out = None
    if graph and graph.nodes:
        workflow_out = WorkflowOut(
            workflow_id=str(uuid.uuid4()),
            node_count=len(graph.nodes),
            status=("awaiting_confirmation" if requires_confirmation
                    else "needs_input" if status == "needs_clarification"
                    else "completed"),
            nodes=[_node_out(n) for n in graph.topo_order()],
        )

    # ── update session memory (B) ─────────────────────────────────────────────
    if primary:
        server_output = primary.result
        result_kind = None
        if capability == "continuation":
            result_kind = "continuation"
        elif action_type == "analyze":
            result_kind = "analysis"
        elif capability == "story_bible":
            result_kind = "bible"
        memory.record_turn(command=cleaned, intent=intent_key, capability=capability,
                           result_kind=result_kind, output=server_output)
    if context is not None:
        memory.remember_context(context)

    # ── persist analytics + audit (D) ─────────────────────────────────────────
    try:
        analytics.record_turn(
            db, session=session, command_id=command_id, graph=graph, timings=timings,
            status=status, confidence=confidence, intent=intent_key, capability=capability,
            action_type=action_type, requires_confirmation=requires_confirmation,
            resolved_references=refs.references if refs else {},
            parameters=(primary.params if primary else {}),
            transcript=transcript, cleaned=cleaned, user_id=user_id, story_id=story_id,
            result_summary=user_message,
        )
        memory.save(db)
        db.commit()
    except Exception as exc:                       # noqa: BLE001
        logger.error("[voice.agent] persistence failed: %s", exc)
        db.rollback()

    return VoiceAgentResponse(
        session_id=session.session_id,
        command_id=command_id,
        transcript=transcript or "",
        cleaned_transcript=cleaned,
        corrected_transcript=corrected_transcript or cleaned,
        resolved_entities=resolved_entities or [],
        context_used=context_used,
        resolved_references=refs.references if refs else {},
        detected_intent=intent_key,
        capability=capability,
        target_router=target_router,
        action_type=action_type,
        is_multi_step=bool(graph and graph.is_multi_step),
        confidence=float(confidence or 0.0),
        requires_confirmation=requires_confirmation,
        status=status,
        workflow=workflow_out,
        result=result,
        user_message=user_message,
        clarification=clarification,
    )
