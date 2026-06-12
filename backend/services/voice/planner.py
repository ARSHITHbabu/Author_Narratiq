"""
Multi-Step Task Planner + Execution Graph (A).

Decomposes one voice command into a dependency-ordered DAG of TaskNodes. A
single-step command yields a 1-node graph so the downstream path is uniform.

Qwen produces the decomposition (over the BGE-M3-shortlisted candidates); the
result is strictly validated against CAPABILITY_REGISTRY, repaired where
possible, checked for cycles, and capped at settings.voice_max_graph_nodes. On
any validation failure it falls back to the single-step classifier.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from . import catalog, intent as intent_mod
from .capabilities import (CAPABILITY_REGISTRY, get_action, disambiguate_action,
                           extract_inline_params, _MUTATING)
from .fastroute import fast_route, transform_action
from .guards import is_compound, is_question, has_actionable_verb
from .topic import classify_topic, is_action_command

logger = logging.getLogger(__name__)


@dataclass
class TaskNode:
    node_key: str
    capability: str
    action: str
    action_type: str
    params: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    execution_locus: str = "client"
    requires_confirmation: bool = False
    status: str = "pending"
    result: dict | None = None
    user_message: str = ""
    client_call: str | None = None


@dataclass
class ExecutionGraph:
    nodes: list[TaskNode] = field(default_factory=list)
    is_multi_step: bool = False
    confidence: float = 0.0
    reasoning: str = ""

    def node(self, key: str) -> TaskNode | None:
        return next((n for n in self.nodes if n.node_key == key), None)

    def topo_order(self) -> list[TaskNode]:
        """Kahn's algorithm. Assumes a validated DAG (validate() ran)."""
        indeg = {n.node_key: 0 for n in self.nodes}
        for n in self.nodes:
            for d in n.depends_on:
                if d in indeg:
                    indeg[n.node_key] += 1
        ready = [k for k, v in indeg.items() if v == 0]
        order: list[str] = []
        while ready:
            k = ready.pop(0)
            order.append(k)
            for n in self.nodes:
                if k in n.depends_on:
                    indeg[n.node_key] -= 1
                    if indeg[n.node_key] == 0:
                        ready.append(n.node_key)
        by_key = {n.node_key: n for n in self.nodes}
        return [by_key[k] for k in order if k in by_key]


_SYSTEM = (
    "You are the task planner for a novel-writing voice assistant. Authors may "
    "issue compound, chained commands. Break the command into an ordered list of "
    "concrete steps. Each step uses ONE capability+action from the candidate list "
    "and may depend on earlier steps by their key.\n"
    "Respond with ONLY JSON:\n"
    '{"is_multi_step": bool, "steps": [ {"key":"n1","capability":"...",'
    '"action":"...","params":{...},"depends_on":[],"reason":"short"} ] }\n'
    "Rules:\n"
    "- capability+action MUST be from the candidates.\n"
    "- Keep it minimal: most commands are ONE step.\n"
    "- Only chain steps when the author clearly asked for multiple actions "
    "(e.g. 'analyze X then rewrite Y', 'generate a bible and then a beat sheet').\n"
    "- depends_on lists earlier step keys whose output this step needs.\n"
    "- Extract stated parameters (title, tone, emotion, query, replacement, etc.)."
)


def _build_node(step: dict, valid_keys: set[str], command: str) -> TaskNode | None:
    cap = (step.get("capability") or "").strip()
    if cap not in CAPABILITY_REGISTRY:
        return None
    action = (step.get("action") or "").strip()
    # Deterministic verb-cue correction (e.g. "delete" must not become "create").
    action = disambiguate_action(cap, command, action)
    spec = get_action(cap, action)
    if spec is None:
        return None
    key = (step.get("key") or "").strip() or f"n{len(valid_keys) + 1}"
    deps = [d for d in (step.get("depends_on") or []) if isinstance(d, str)]
    params = step.get("params") if isinstance(step.get("params"), dict) else {}
    params = dict(params)
    for k, v in extract_inline_params(cap, action, command).items():
        params.setdefault(k, v)
    return TaskNode(
        node_key=key,
        capability=cap,
        action=action,
        action_type=spec.action_type,
        params=params,
        depends_on=deps,
        execution_locus=spec.execution_locus,
        requires_confirmation=spec.needs_confirmation(),
        client_call=spec.client_call,
    )


def _has_cycle(nodes: list[TaskNode]) -> bool:
    keys = {n.node_key for n in nodes}
    indeg = {n.node_key: 0 for n in nodes}
    for n in nodes:
        for d in n.depends_on:
            if d in keys:
                indeg[n.node_key] += 1
    ready = [k for k, v in indeg.items() if v == 0]
    seen = 0
    while ready:
        k = ready.pop()
        seen += 1
        for n in nodes:
            if k in n.depends_on:
                indeg[n.node_key] -= 1
                if indeg[n.node_key] == 0:
                    ready.append(n.node_key)
    return seen != len(nodes)


def _single_node_graph(capability: str, action: str, params: dict, *, confidence: float,
                       reasoning: str) -> ExecutionGraph:
    spec = get_action(capability, action)
    node = TaskNode(
        node_key="n1", capability=capability, action=action,
        action_type=spec.action_type, params=dict(params),
        execution_locus=spec.execution_locus,
        requires_confirmation=spec.needs_confirmation(),
        client_call=spec.client_call,
    )
    return ExecutionGraph(nodes=[node], is_multi_step=False, confidence=confidence,
                          reasoning=reasoning)


async def plan(command: str, context_brief: str = "", has_selection: bool = False) -> ExecutionGraph:
    from config import settings
    from services.ai_service import _complete, _extract_json

    # ── Selected-text transform: route to the ai_transform FEATURE directly ───
    # This MUST come before topic/RAG/LLM routing so a transform request can never
    # fall through to story-QA/plot/character RAG. The selected_text is the only
    # source; if it's missing the context resolver clarifies ("select text first").
    if not is_compound(command):
        ta = transform_action(command, has_selection)
        if ta and get_action("text_transform", ta):
            return _single_node_graph("text_transform", ta, {}, confidence=0.95,
                                      reasoning="transform_selection")

    # ── Deterministic fast-path for high-precision single-intent commands ─────
    fr = fast_route(command)
    if fr:
        cap, action, params = fr
        if get_action(cap, action):
            return _single_node_graph(cap, action, params, confidence=0.95,
                                      reasoning="fast_route")

    # ── Question guard: a pure question (no actionable verb) becomes a single
    # safe Q&A read that returns a natural answer — never a workflow, never a
    # write. (Questions WITH an action verb, e.g. "find where X appears", fall
    # through to normal feature routing, which also returns a useful answer.)
    #
    # Topic routing: a question/topic goes to its REAL feature (character RAG,
    # relationship graph, continuity, pacing, …) — plot_assistant is reachable
    # ONLY for brainstorming. A generic factual question with no specific topic
    # falls to story_qa (RAG Q&A), NOT plot_assistant.
    if not is_compound(command) and not is_action_command(command):
        topic = classify_topic(command)
        if topic:
            cap, action = topic
            params = {"question": command} if action in ("ask", "brainstorm") else {}
            return _single_node_graph(cap, action, params, confidence=0.9, reasoning="topic")
        if is_question(command) and not has_actionable_verb(command):
            return _single_node_graph("story_qa", "ask", {"question": command},
                                      confidence=0.85, reasoning="story_qa_default")

    k = settings.voice_intent_shortlist_k
    cand_names = [c for c, _ in catalog.shortlist(command, k=k)]
    brief = catalog.candidate_brief(cand_names)

    user = (
        f"Command: {command!r}\n\n"
        f"Candidate capabilities:\n{brief}\n\n"
        f"{('Context: ' + context_brief) if context_brief else ''}\n\n"
        "Return the JSON plan."
    )
    try:
        raw = await _complete(system=_SYSTEM, user=user, temperature=0.0, max_tokens=600)
        data = _extract_json(raw, fallback={})
    except Exception as exc:                       # noqa: BLE001 — fall back below
        logger.warning("[voice.planner] planning call failed: %s", exc)
        data = {}

    steps = data.get("steps") if isinstance(data, dict) else None
    nodes: list[TaskNode] = []
    if isinstance(steps, list):
        seen_keys: set[str] = set()
        for step in steps[: settings.voice_max_graph_nodes]:
            node = _build_node(step, seen_keys, command)
            if node and node.node_key not in seen_keys:
                nodes.append(node)
                seen_keys.add(node.node_key)
        # prune dangling deps
        for n in nodes:
            n.depends_on = [d for d in n.depends_on if d in seen_keys and d != n.node_key]

    # ── Fallbacks ─────────────────────────────────────────────────────────────
    if not nodes or _has_cycle(nodes):
        if nodes and _has_cycle(nodes):
            logger.warning("[voice.planner] cycle detected — falling back to single step")
        det = await intent_mod.classify(command, context_brief)
        if det.capability == "none" or not det.action:
            return ExecutionGraph(nodes=[], is_multi_step=False, confidence=det.confidence,
                                  reasoning="no_match")
        action = disambiguate_action(det.capability, command, det.action)
        spec = get_action(det.capability, action)
        params = dict(det.params)
        for k, v in extract_inline_params(det.capability, action, command).items():
            params.setdefault(k, v)
        nodes = [TaskNode(
            node_key="n1", capability=det.capability, action=action,
            action_type=spec.action_type, params=params,
            execution_locus=spec.execution_locus,
            requires_confirmation=spec.needs_confirmation(),
            client_call=spec.client_call,
        )]
        return ExecutionGraph(nodes=nodes, is_multi_step=False,
                              confidence=det.confidence, reasoning=det.reasoning)

    # ── Guardrail: collapse to a single step unless the author clearly asked
    # for a compound (multi-step) action — prevents unrelated extra nodes.
    if len(nodes) > 1 and not is_compound(command):
        root = next((n for n in nodes if not n.depends_on), nodes[0])
        root.depends_on = []
        nodes = [root]

    # ── Guardrail: a question must never resolve to a write/destructive/export.
    # Reroute to the RAG Q&A feature (story_qa), not plot_assistant.
    if nodes and is_question(command) and nodes[0].action_type in _MUTATING:
        return _single_node_graph("story_qa", "ask", {"question": command},
                                  confidence=0.8, reasoning="question_safety")

    is_multi = len(nodes) > 1
    return ExecutionGraph(nodes=nodes, is_multi_step=is_multi,
                          confidence=float(data.get("confidence", 0.7) if isinstance(data, dict) else 0.7),
                          reasoning="planned")
