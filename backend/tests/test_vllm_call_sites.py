"""
Stage 12 Tranche 3 (A19) — every model call goes through the fenced path.

The prompt-injection fence (services/prompt_safety.harden) is applied in
exactly two places, `_complete_ex` and `_stream_generate` in
services/ai_service.py. That only protects every AI feature while nothing else
talks to the model server. This test walks the backend source and fails if a
new direct model call appears anywhere else (the health probe, which sends no
author material, is the one allowed exception).

    DATABASE_URL=...narratiq_test pytest backend/tests/test_vllm_call_sites.py -q
"""
from __future__ import annotations

import ast
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_SKIP_DIRS = {"tests", "scripts", "migrations", "__pycache__", "uploads", "venv", ".venv"}
_ALLOWED = {("services/ai_service.py", "_complete_ex"), ("services/ai_service.py", "_stream_generate")}
# Calls that reach the model server: the OpenAI client's completion/chat
# endpoints, and any helper that returns that client.
_MODEL_ATTRS = {"completions"}
_CLIENT_FACTORIES = {"get_vllm_client", "AsyncOpenAI", "OpenAI"}


def _sources():
    for path in sorted(_BACKEND.rglob("*.py")):
        rel = path.relative_to(_BACKEND)
        if rel.parts[0] in _SKIP_DIRS:
            continue
        yield rel.as_posix(), ast.parse(path.read_text(), filename=str(path))


def _enclosing_functions(tree):
    """Map each node to the name of the innermost function that contains it."""
    owner = {}

    def visit(node, fn):
        for child in ast.iter_child_nodes(node):
            name = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else fn
            owner[child] = name
            visit(child, name)
    visit(tree, None)
    return owner


def _model_uses():
    found = []
    for rel, tree in _sources():
        owner = _enclosing_functions(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in _MODEL_ATTRS:
                found.append((rel, owner.get(node), "." + node.attr, node.lineno))
            elif isinstance(node, ast.Call):
                fn = node.func
                name = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else None
                if name in _CLIENT_FACTORIES:
                    found.append((rel, owner.get(node), name + "()", node.lineno))
    return found


def test_only_the_fenced_functions_call_the_model():
    uses = _model_uses()
    # get_vllm_client() is defined in ai_service and builds the client there.
    outside = [u for u in uses
               if (u[0], u[1]) not in _ALLOWED
               and not (u[0] == "services/ai_service.py" and u[1] == "get_vllm_client")]
    assert outside == [], f"model called outside the fenced path: {outside}"


def test_no_raw_http_call_to_a_completion_endpoint():
    # A plain httpx POST to the model server would bypass the client and the
    # fence alike. The health probe only lists models, never completes.
    raw = [(rel, node.lineno) for rel, tree in _sources() for node in ast.walk(tree)
           if isinstance(node, ast.Constant) and isinstance(node.value, str)
           and ("chat/completions" in node.value or "v1/completions" in node.value)]
    assert raw == [], raw


def test_both_fenced_functions_still_call_the_model():
    # Guards the guard: if the fenced functions are renamed, the allow-list
    # above would silently allow nothing and the first test would still pass.
    callers = {(u[0], u[1]) for u in _model_uses() if u[2] == ".completions"}
    assert callers == _ALLOWED, callers


def test_both_fenced_functions_apply_the_fence():
    tree = ast.parse((_BACKEND / "services" / "ai_service.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in {n for _, n in _ALLOWED}:
            calls = {c.func.attr if isinstance(c.func, ast.Attribute) else getattr(c.func, "id", None)
                     for c in ast.walk(node) if isinstance(c, ast.Call)}
            assert "harden" in calls, f"{node.name} no longer calls prompt_safety.harden"
