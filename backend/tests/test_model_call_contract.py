"""
Calling contract for services.ai_service, checked statically for the whole
backend.

Two production defects were exactly this kind of error:
  * Stage 3 (task 3.1): writing_tools passed `query=` to retrieval helpers whose
    parameter is `question`, so continuation and outline raised TypeError.
  * Stage 11: every Story Intelligence pass called `_complete(prompt, ...)`
    without the required `user` argument. All 20 raised TypeError, which the
    orchestrator swallowed, so the feature never worked and nothing showed it.

Neither was caught because no test executed those lines with the real
signature. This test parses every backend module and binds EVERY call to a
function from services.ai_service (imported by name, or via `ai_service.`)
against that function's real signature, so a missing argument or a wrong
keyword fails the suite without running the model.

    pytest backend/tests/test_model_call_contract.py -q
"""
from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from services import ai_service  # noqa: E402

SIGNATURES = {
    name: inspect.signature(obj)
    for name, obj in vars(ai_service).items()
    if inspect.isfunction(obj) and obj.__module__ == ai_service.__name__
}


def _imported_names(tree: ast.Module) -> dict[str, str]:
    """local name -> ai_service function name, for `from services.ai_service import x [as y]`."""
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in ("services.ai_service", "ai_service"):
            for a in node.names:
                if a.name in SIGNATURES:
                    out[a.asname or a.name] = a.name
    return out


def _calls(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    local = _imported_names(tree)
    if path.name == "ai_service.py" and path.parent.name == "services":
        local.update({n: n for n in SIGNATURES})
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if isinstance(f, ast.Name) and f.id in local:
            yield node, local[f.id]
        elif (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name)
              and f.value.id == "ai_service" and f.attr in SIGNATURES):
            yield node, f.attr


def _module_files():
    for p in BACKEND.rglob("*.py"):
        if "tests" in p.parts or "migrations" in p.parts:
            continue
        yield p


def test_every_ai_service_call_binds_to_the_real_signature():
    problems, checked = [], 0
    for path in _module_files():
        for call, name in _calls(path):
            if any(isinstance(a, ast.Starred) for a in call.args) or any(k.arg is None for k in call.keywords):
                continue  # *args / **kwargs: cannot be checked statically
            sig = SIGNATURES[name]
            try:
                sig.bind(*[None] * len(call.args), **{k.arg: None for k in call.keywords})
                checked += 1
            except TypeError as exc:
                problems.append(f"{path.relative_to(BACKEND)}:{call.lineno} {name}(): {exc}")
    assert not problems, "calls that do not match services.ai_service signatures:\n" + "\n".join(problems)
    assert checked > 100        # the scan really found the call sites


def test_the_check_would_have_caught_the_story_intel_bug():
    """The exact Stage 11 defect: one positional argument to _complete."""
    sig = SIGNATURES["_complete"]
    try:
        sig.bind(None, max_tokens=None, temperature=None)
    except TypeError:
        return
    raise AssertionError("_complete(prompt, ...) should not bind: `user` is required")
