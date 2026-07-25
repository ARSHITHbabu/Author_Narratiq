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
from . import lifecycle
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
            lifecycle.transition(node, lifecycle.BLOCKED, source="orchestrator",
                                 reason="upstream node did not produce", strict=False)
            continue

        deps = _pipe_dependencies(node, graph)
        node.params[_DEPS_KEY] = deps

        missing = ctx_mod.resolve_node_params(node, context, refs, memory, db)
        if missing:
            lifecycle.transition(node, lifecycle.NEEDS_INPUT, source="orchestrator",
                                 reason="required params missing", strict=False)
            node.user_message = f"I need: {', '.join(missing)}."
            all_missing.extend(missing)
            any_needs_input = True
            continue

        spec = get_action(node.capability, node.action)
        is_server = (node.execution_locus == "server"
                     and (node.capability, node.action) in SERVER_ADAPTERS)

        if is_server:
            # FEATURE call — adapter invokes the feature's services (model-owning).
            # This is the ONE path that may reach a terminal status in-process,
            # because the result is in hand when it does.
            lifecycle.transition(node, lifecycle.EXECUTING, source="orchestrator",
                                 reason="server adapter dispatched", strict=False)
            try:
                result = await run_server_adapter(node, bundle, db, user)
                answer = (result or {}).get("answer") if isinstance(result, dict) else None
                if not result or not str(answer or "").strip():
                    # An adapter that returns None or an empty payload has not
                    # done the thing. Reporting "Done." here is precisely the
                    # false success in Phase 2 Issue 5.
                    logger.warning("[voice.orchestrator] feature %s.%s returned no result",
                                   node.capability, node.action)
                    node.result = None
                    lifecycle.transition(node, lifecycle.FAILED, source="orchestrator",
                                         reason="adapter returned no result", strict=False)
                    node.user_message = ("I couldn't get an answer for that — "
                                         "please try again.")
                else:
                    node.result = result
                    lifecycle.transition(node, lifecycle.SUCCEEDED, source="orchestrator",
                                         reason="adapter returned a result", strict=False)
                    node.user_message = answer
                    if result.get("context_used"):
                        context_used = result["context_used"]
            except Exception as exc:                       # noqa: BLE001
                logger.warning("[voice.orchestrator] feature %s.%s failed: %s",
                               node.capability, node.action, exc)
                node.result = None
                lifecycle.transition(node, lifecycle.FAILED, source="orchestrator",
                                     reason="adapter raised", strict=False)
                node.user_message = "I couldn't complete that just now — please try again."
        else:
            # Proposed client action — the frontend executes it via api.ts. It is
            # NOT done yet, and must not be described as if it were: the terminal
            # status arrives later, from the executor's own report.
            node.execution_locus = "client"
            node.result = None
            lifecycle.transition(
                node,
                lifecycle.AWAITING_CONFIRMATION if node.requires_confirmation else lifecycle.READY,
                source="orchestrator", reason="handed to client executor", strict=False,
            )
            node.user_message = node.user_message or _describe_client_action(node)
            # Transforms ALWAYS act on the selection only — never RAG/story passages.
            if node.capability == "text_transform":
                context_used = "selected text"
        node.params.pop(_DEPS_KEY, None)

    exec_ms = int((time.monotonic() - t0) * 1000)
    return {"missing": all_missing, "any_needs_input": any_needs_input,
            "exec_ms": exec_ms, "context_used": context_used or bundle.used_label}


# _summarize_result() was removed here (task 3.7). It returned "Done." for any
# result and was called from nowhere — a dead function that could only ever have
# reported success. The guarantee it was supposed to provide now lives where the
# message is actually produced, above.


def _describe_client_action(node) -> str:
    verb = {
        "read": "Fetching", "analyze": "Analyzing", "generate": "Generating",
        "write": "Will update", "destructive": "Will change", "export": "Will export",
    }.get(node.action_type, "Will run")
    return f"{verb} via {node.capability}.{node.action}."
