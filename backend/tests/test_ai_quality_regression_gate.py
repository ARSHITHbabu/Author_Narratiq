"""
Stage 12.3 — task 6.5: the regression gate's decision rule, without a model.
The live proof (baseline / unchanged re-run / injected regression) is recorded in
docs/testing/stage-12/stage-12.3/ai-quality-regression-gate.md.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402

import ai_quality_regression_gate as gate  # noqa: E402


def test_fisher_matches_hand_computed_values():
    # 0/10 vs 10/10: only one table is as extreme -> 1 / C(20,10)
    assert gate.fisher_one_sided_lower(0, 10, 10, 10) == pytest.approx(1 / 184756)
    # identical rates are never significant
    assert gate.fisher_one_sided_lower(9, 10, 9, 10) > 0.5
    assert gate.fisher_one_sided_lower(10, 10, 10, 10) == pytest.approx(1.0)


def test_alarm_boundary_detects_a_collapse_not_a_wobble():
    alpha = gate.FAMILY_ALPHA / 11
    assert gate.minimum_alarm_count(20, 20, 20, alpha) == 11    # 20/20 baseline: alarm at <= 11/20
    assert gate.minimum_alarm_count(18, 20, 20, alpha) == 7     # 18/20 baseline: alarm at <= 7/20
    assert gate.minimum_alarm_count(14, 20, 20, alpha) == 3
    # the documented 1-in-10 adventure-3 variability never alarms
    assert gate.fisher_one_sided_lower(16, 20, 18, 20) > alpha


def test_evaluate_alarms_only_on_a_significant_drop():
    base = {"a": {"passes": 10, "trials": 10}, "b": {"passes": 9, "trials": 10}}
    assert gate.evaluate(base, {"a": {"passes": 9, "trials": 10}, "b": {"passes": 8, "trials": 10}})["alarm"] is False
    v = gate.evaluate(base, {"a": {"passes": 10, "trials": 10}, "b": {"passes": 0, "trials": 10}})
    assert v["alarm"] is True and [r["invariant"] for r in v["rows"] if r["ALARM"]] == ["b"]
    # better than baseline never alarms
    assert gate.evaluate({"a": {"passes": 2, "trials": 10}}, {"a": {"passes": 10, "trials": 10}})["alarm"] is False


def test_injected_regression_touches_only_the_no_change_assessor(monkeypatch):
    from services import ai_service
    seen = []

    async def fake(system, user, *a, label=None, **k):
        seen.append((label, system))
        return None, {}

    monkeypatch.setattr(ai_service, "complete_structured", fake)
    gate._inject("degraded-no-change")
    asyncio.run(ai_service.complete_structured("SYS", "u", coerce=None, label="no_change_assessment"))
    asyncio.run(ai_service.complete_structured("SYS", "u", coerce=None, label="strict_consistency"))
    assert seen[0] == ("no_change_assessment", "SYS" + gate.DEGRADED_NO_CHANGE)
    assert seen[1] == ("strict_consistency", "SYS")


def test_cli_refuses_a_baseline_recorded_with_a_regression(capsys):
    assert gate.main_cli(["--record-baseline", "x.json", "--inject-regression", "degraded-no-change"]) == 2
    assert gate.main_cli([]) == 2


def test_an_http_error_invalidates_the_run_instead_of_counting_as_a_failure(monkeypatch):
    """A 429/500 is an infrastructure fault; counted as a failed invariant it would
    fake a regression (found 2026-10-06: the per-user AI rate limit turned most of
    a first baseline attempt into 0/20)."""
    import fastapi.testclient

    class NoLifespanClient:
        """Never enter the real app lifespan here: its shutdown closes the shared
        vLLM client and every later live test in the same process would fail
        (found 2026-10-06 in the full backend run)."""
        def __init__(self, *_a, **_k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(fastapi.testclient, "TestClient", NoLifespanClient)
    monkeypatch.setattr(gate, "_run_once", lambda *a, **k: (429, False, ""))
    with pytest.raises(RuntimeError, match="HTTP 429"):
        gate.run(1, ["light"], None)


def test_inverted_question_injection_rewrites_only_the_assessor_question(monkeypatch):
    from services import ai_service
    seen = []

    async def fake(system, user, *a, label=None, **k):
        seen.append(system)
        return None, {}

    monkeypatch.setattr(ai_service, "complete_structured", fake)
    gate._inject("inverted-no-change-question")
    sys_prompt = "You are assessing a passage for a tone transform. Question: is this passage ALREADY dark? Return ONLY JSON"
    asyncio.run(ai_service.complete_structured(sys_prompt, "u", coerce=None, label="no_change_assessment"))
    assert "could this passage be improved further for dark?" in seen[0]
    assert "ALREADY" not in seen[0]


def test_renamed_key_injection_changes_only_the_requested_field(monkeypatch):
    from services import ai_service
    seen = []

    async def fake(system, user, *a, label=None, **k):
        seen.append(system)
        return None, {}

    monkeypatch.setattr(ai_service, "complete_structured", fake)
    gate._inject("renamed-assessor-key")
    asyncio.run(ai_service.complete_structured(
        'Question: is this passage ALREADY dark? Return ONLY JSON: {"already_suitable": true/false, "reason": "x"}.',
        "u", coerce=None, label="no_change_assessment"))
    assert '"needs_rewrite": true/false' in seen[0] and '"already_suitable"' not in seen[0]
