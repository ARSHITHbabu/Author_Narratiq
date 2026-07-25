"""
Degraded-output contract for structured AI features (no DB, no LLM, no GPU).

Task 3.4. Two features failed in opposite ways when the model returned a shape
they did not expect, and both lied to the author:

  Plot holes  (Phase 2 Issue 2)  — raise ValueError, discarding findings that
                                   DID parse, and return HTTP 503.
  Continuity  (Phase 2 Issue 14) — return [] via _extract_json's fallback, so
                                   the author was told the manuscript was
                                   consistent when the response was unreadable.

The contract replaces both: coerce → salvage → one bounded reprompt → partial
result carrying `degraded: true`. Raising is reserved for the case where there
is genuinely nothing to show.

Run from backend/ — config.py resolves .env relative to the working directory:

    cd backend && python3 tests/test_degraded_output.py
    cd backend && pytest tests/test_degraded_output.py -q
"""
import asyncio
import inspect
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import ai_service
from services.ai_service import (
    DegradedMeta,
    coerce_continuity_issues,
    coerce_plot_hole_result,
    complete_structured,
)

BACKEND = Path(__file__).resolve().parents[1]


def _run(responses):
    """Run complete_structured with vLLM stubbed.

    `responses` is a list of (raw_text, finish_reason) consumed one per attempt,
    so a test can make attempt 1 fail and attempt 2 succeed. Returns
    (value, meta, call_count).
    """
    calls = {"n": 0}

    async def fake_complete_ex(system, user, **kwargs):
        raw, finish = responses[min(calls["n"], len(responses) - 1)]
        calls["n"] += 1
        return raw, finish

    original = ai_service._complete_ex
    ai_service._complete_ex = fake_complete_ex
    try:
        value, meta = asyncio.run(complete_structured(
            "system", "user", coerce=coerce_plot_hole_result, label="test",
        ))
    finally:
        ai_service._complete_ex = original
    return value, meta, calls["n"]


ISSUE = {"issue_id": 1, "type": "timeline_inconsistency", "severity": "high",
         "chapters": [3, 7], "description": "The ledger is destroyed in Ch3 but read in Ch7.",
         "suggestion": "Move the destruction later."}


# ── 1. The contract ───────────────────────────────────────────────────────────

def test_clean_response_is_not_degraded_and_uses_one_call():
    value, meta, calls = _run([(json.dumps({"issues": [ISSUE], "note": "ok"}), "stop")])
    assert len(value["issues"]) == 1
    assert meta.degraded is False and meta.reason is None
    assert calls == 1, "a clean parse must not trigger a retry"


def test_unreadable_response_triggers_exactly_one_retry():
    value, meta, calls = _run([
        ("I'm afraid I can't do that.", "stop"),
        (json.dumps({"issues": [ISSUE]}), "stop"),
    ])
    assert value is not None and len(value["issues"]) == 1
    assert meta.degraded is True, "a result that needed a retry is not pristine"
    assert meta.attempts == 2
    assert calls == 2


def test_two_attempts_is_a_structural_maximum():
    """A model that cannot produce the shape twice will not produce it on the
    fifth try, and the author is waiting."""
    value, meta, calls = _run([("not json at all", "stop")])
    assert value is None
    assert meta.degraded is True and meta.attempts == 2
    assert calls == 2, f"expected exactly 2 attempts, got {calls}"


def test_total_failure_returns_none_not_an_exception():
    """The caller decides whether nothing-at-all is an error; the contract does
    not raise on the author's behalf."""
    value, meta, _ = _run([("", "stop")])
    assert value is None
    assert "could not be read" in meta.reason


def test_partial_parse_returns_findings_and_marks_degraded():
    payload = {"issues": [ISSUE, "not an object", {"no": "description"}]}
    value, meta, calls = _run([(json.dumps(payload), "stop")])
    assert len(value["issues"]) == 1, "the one valid finding must survive"
    assert meta.degraded is True
    assert meta.discarded == 2
    assert calls == 1, "salvage must not trigger a retry — we already have results"


def test_truncated_response_salvages_rather_than_failing():
    """A truncated LIST of findings is useful; this is deliberately unlike the
    continuation path, where a truncated sentence is not."""
    value, meta, _ = _run([(json.dumps({"issues": [ISSUE]}), "length")])
    assert len(value["issues"]) == 1
    assert meta.degraded is True
    assert "cut off" in meta.reason


def test_degraded_reasons_are_author_facing():
    for meta in (
        DegradedMeta(True, ai_service._degraded_reason(2, False)),
        DegradedMeta(True, ai_service._degraded_reason(0, True)),
        DegradedMeta(True, ai_service._degraded_reason(0, False, retried=True)),
    ):
        for banned in ("JSON", "parse", "coerce", "finish_reason", "None", "Exception"):
            assert banned not in meta.reason, f"{meta.reason!r} leaks {banned!r}"


# ── 2. Coercion — plot holes ──────────────────────────────────────────────────

def test_coerce_accepts_the_documented_shape():
    value, discarded = coerce_plot_hole_result({"issues": [ISSUE], "note": "n"})
    assert len(value["issues"]) == 1 and discarded == 0
    assert value["note"] == "n"


def test_coerce_accepts_a_bare_array():
    value, _ = coerce_plot_hole_result([ISSUE])
    assert len(value["issues"]) == 1


def test_coerce_accepts_a_single_array_wrapper():
    value, _ = coerce_plot_hole_result({"plot_holes": [ISSUE]})
    assert len(value["issues"]) == 1


def test_coerce_refuses_to_guess_between_several_arrays():
    """Picking one of two arrays would be inventing structure."""
    value, _ = coerce_plot_hole_result({"issues_a": [ISSUE], "issues_b": [ISSUE]})
    assert value is None


def test_coerce_rejects_shapes_with_no_array():
    assert coerce_plot_hole_result({"note": "nothing"})[0] is None
    assert coerce_plot_hole_result("a sentence")[0] is None
    assert coerce_plot_hole_result(None)[0] is None


def test_coercion_defaults_presentation_fields_only():
    """severity/id/suggestion are defaulted; description carries meaning and a
    finding without one is dropped rather than invented."""
    value, discarded = coerce_plot_hole_result({"issues": [
        {"description": "Something contradicts."},          # bare but meaningful
        {"severity": "high", "chapters": [1]},              # no description
    ]})
    assert discarded == 1
    kept = value["issues"][0]
    assert kept["severity"] == "medium" and kept["issue_id"] == 1
    assert kept["type"] and kept["suggestion"] == ""


def test_coercion_normalises_chapter_references():
    value, _ = coerce_plot_hole_result({"issues": [
        {"description": "d", "chapters": "3, 7"},
        {"description": "d", "chapters": 4},
        {"description": "d", "chapters": ["Ch 5", 6]},
    ]})
    assert [i["chapters"] for i in value["issues"]] == [[3, 7], [4], [5, 6]]


def test_coercion_clamps_unknown_severity():
    value, _ = coerce_plot_hole_result({"issues": [{"description": "d", "severity": "CATASTROPHIC"}]})
    assert value["issues"][0]["severity"] == "medium"


# ── 3. Coercion — continuity ──────────────────────────────────────────────────

CONT = {"type": "character_location", "description": "She is in two places in Ch4.",
        "chapter_refs": [4], "severity": "high", "resolution_hint": "Pick one."}


def test_continuity_coercion_salvages_valid_entries():
    value, discarded = coerce_continuity_issues([CONT, {"description": ""}, 42])
    assert len(value) == 1 and discarded == 2


def test_continuity_coercion_distinguishes_empty_from_unreadable():
    """The heart of Issue 14: an empty array is a real answer; a string is not."""
    empty, _ = coerce_continuity_issues([])
    assert empty == [], "an empty array means 'no issues found'"
    unreadable, _ = coerce_continuity_issues("no contradictions found")
    assert unreadable is None, "prose must not be read as 'manuscript is clean'"


# ── 4. The call sites ─────────────────────────────────────────────────────────

def test_plot_hole_strategy_uses_the_contract():
    src = inspect.getsource(ai_service._strategy_single_pass)
    assert "complete_structured(" in src
    assert "coerce_plot_hole_result" in src
    assert "_extract_json(raw, None)" not in src, "the old hard-fail parse is gone"
    assert "degraded" in src


def test_continuity_uses_the_contract_and_returns_meta():
    src = inspect.getsource(ai_service.check_continuity)
    assert "complete_structured(" in src
    assert "fallback=[]" not in src, "the silent-empty fallback is the defect"
    assert "return issues, meta" in src


def test_continuity_signature_forces_callers_to_handle_degradation():
    assert "tuple[list[dict], DegradedMeta]" in inspect.getsource(ai_service.check_continuity)


def test_every_continuity_caller_unpacks_the_meta():
    """A caller that ignores the meta silently reintroduces the false all-clear."""
    src = (BACKEND / "routers/analysis.py").read_text(encoding="utf-8")
    for line in src.splitlines():
        if "check_continuity(" in line and "await" in line:
            assert "meta" in line, f"caller drops the degradation meta: {line.strip()}"


def test_chunked_continuity_reports_failed_chunks():
    src = (BACKEND / "routers/analysis.py").read_text(encoding="utf-8")
    assert "degraded_chunks" in src
    assert "could not be fully checked" in src


def test_responses_expose_the_degraded_fields():
    import schemas
    for model in (schemas.PlotHoleResponse, schemas.ContinuityCheckResponse):
        assert "degraded" in model.model_fields
        assert "degraded_reason" in model.model_fields
        assert model.model_fields["degraded"].default is False, "must default to honest-but-not-alarming"


def test_plot_hole_router_does_not_leak_exception_text():
    src = (BACKEND / "routers/plot_holes.py").read_text(encoding="utf-8")
    assert "detail=str(exc)" not in src, "raw exception text must not reach the author"
    assert "could not be completed" in src


def test_frontend_panels_render_the_degraded_state():
    frontend = BACKEND.parent / "frontend"
    plot = (frontend / "components/plot-holes/PlotHolesPanel.tsx").read_text(encoding="utf-8")
    cont = (frontend / "components/analysis/ContinuityPanel.tsx").read_text(encoding="utf-8")

    assert "result.degraded" in plot
    assert "issues_found === 0 && !result.degraded" in plot, \
        "a clean result must only be claimed when the scan was complete"
    assert "degraded" in cont
    assert "issues.length === 0 && degraded" in cont, \
        "an incomplete check must not read as 'great consistency'"


# ── Plain-python runner (no pytest required) ──────────────────────────────────

if __name__ == "__main__":
    tests = [
        (name, obj)
        for name, obj in sorted(globals().items())
        if name.startswith("test_") and callable(obj)
    ]
    failures = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception as exc:  # noqa: BLE001 — this is the test harness
            failures.append((name, exc))
            print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")

    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
