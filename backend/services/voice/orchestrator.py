"""
Execution orchestrator (A).

Walks the validated DAG in topological order. For each node:
  1. pipe upstream results into this node's params (dependency edges)
  2. resolve params from context/refs/memory/DB (context.resolve_node_params)
  3. if a REQUIRED param is missing → mark needs_input (agent asks clarification)
  4. if the node is a SAFE server_sync capability with a feature adapter → run the
     adapter (which calls the FEATURE's services) and store the result
  5. otherwise emit it as a proposed CLIENT action (execution = client_call+args),
     awaiting_confirmation when it mutates content

CRITICAL: this layer contains NO model code. server_sync nodes are executed only
through the Feature Adapter Layer (services/voice/adapters.py), which calls the
feature's own service functions; the feature owns its model. Every other node is
executed client-side against the real router endpoints via api.ts.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from . import context as ctx_mod
from .adapters import SERVER_ADAPTERS, run_server_adapter

logger = logging.getLogger(__name__)

# Internal param key carrying upstream results into a node (stripped before send).
_DEPS_KEY = "_deps"


# ── Orchestration ─────────────────────────────────────────────────────────────

def _pipe_dependencies(node, graph) -> dict[str, Any]:
    """Collect upstream results and pipe obvious fields into this node's params."""
    deps: dict[str, Any] = {}
    for dep_key in node.depends_on:
        dep = graph.node(dep_key)
        if dep and dep.result is not None:
            deps[dep_key] = dep.result
            # auto-pipe generated text into a consumer's content/text slot
            if isinstance(dep.result, dict) and dep.result.get("text"):
                if not node.params.get("content") and "content" in _required(node):
                    node.params["content"] = dep.result["text"]
                if not node.params.get("text") and "text" in _required(node):
                    node.params["text"] = dep.result["text"]
    return deps


def _required(node) -> list[str]:
    from .capabilities import get_action
    spec = get_action(node.capability, node.action)
    return spec.required if spec else []


def _client_args(params: dict) -> dict:
    return {k: v for k, v in params.items() if not k.startswith("_")}


async def execute(graph, context, refs, memory, db, user=None) -> dict:
    """
    Execute the graph; mutate nodes in place. Returns a consolidated dict:
      {missing, any_needs_input, exec_ms, context_used}

    Single resolution pass per node AFTER dependency results are piped, so a
    later node can be satisfied by an upstream node's output. server_sync nodes
    run via the Feature Adapter Layer; all others become client plans.
    """
    from .capabilities import get_action

    t0 = time.monotonic()
    all_missing: list[str] = []
    any_needs_input = False
    bundle = ctx_mod.build_bundle(context, memory, db)
    context_used = ""

    for node in graph.topo_order():
        # If an upstream node could not run, skip dependents.
        upstream_blocked = any(
            (graph.node(d) and graph.node(d).status in ("needs_input", "failed", "skipped"))
            for d in node.depends_on
        )
        if upstream_blocked:
            node.status = "skipped"
            continue

        deps = _pipe_dependencies(node, graph)
        node.params[_DEPS_KEY] = deps

        missing = ctx_mod.resolve_node_params(node, context, refs, memory, db)
        if missing:
            node.status = "needs_input"
            node.user_message = f"I need: {', '.join(missing)}."
            all_missing.extend(missing)
            any_needs_input = True
            continue

        spec = get_action(node.capability, node.action)
        is_server = (node.execution_locus == "server"
                     and (node.capability, node.action) in SERVER_ADAPTERS)

        if is_server:
            # FEATURE call — adapter invokes the feature's services (model-owning).
            node.status = "running"
            try:
                result = await run_server_adapter(node, bundle, db, user)
                node.result = result or {}
                node.status = "done"
                node.user_message = (result or {}).get("answer", "Done.")
                if (result or {}).get("context_used"):
                    context_used = result["context_used"]
            except Exception as exc:                       # noqa: BLE001
                logger.warning("[voice.orchestrator] feature %s.%s failed: %s",
                               node.capability, node.action, exc)
                node.status = "failed"
                node.user_message = "I couldn't complete that just now — please try again."
        else:
            # Proposed client action — frontend executes via api.ts (real feature).
            node.execution_locus = "client"
            node.result = None
            node.status = "awaiting_confirmation" if node.requires_confirmation else "ready"
            node.user_message = node.user_message or _describe_client_action(node)
            # Transforms ALWAYS act on the selection only — never RAG/story passages.
            if node.capability == "text_transform":
                context_used = "selected text"
        node.params.pop(_DEPS_KEY, None)

    exec_ms = int((time.monotonic() - t0) * 1000)
    return {"missing": all_missing, "any_needs_input": any_needs_input,
            "exec_ms": exec_ms, "context_used": context_used or bundle.used_label}


def _summarize_result(node, result: dict) -> str:
    if node.capability == "text_transform":
        return "Rewrite ready for review."
    return "Done."


def _describe_client_action(node) -> str:
    verb = {
        "read": "Fetching", "analyze": "Analyzing", "generate": "Generating",
        "write": "Will update", "destructive": "Will change", "export": "Will export",
    }.get(node.action_type, "Will run")
    return f"{verb} via {node.capability}.{node.action}."
