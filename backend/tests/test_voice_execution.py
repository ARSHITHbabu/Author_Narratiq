"""
Voice agent execution and success reporting (no DB, no LLM, no GPU).

Tasks 3.6 (action execution) and 3.7 (success reporting must reflect reality).
Both operate on one pipeline, so they are tested together; each test names the
task it belongs to.

The defect at the centre of 3.7: the agent set `status = "success"` when the
PLAN was built. Client-side nodes were still unexecuted, their results None, and
for non-mutating actions nothing ever reported back — so the author was told
their chapter had been created before anything had tried to create it.

Run from backend/:

    cd backend && python3 tests/test_voice_execution.py
    cd backend && pytest tests/test_voice_execution.py -q
"""
import inspect
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.voice import lifecycle
from services.voice.lifecycle import InvalidTransition

BACKEND = Path(__file__).resolve().parents[1]
FRONTEND = BACKEND.parent / "frontend"


class _Node:
    """Stand-in for a VoiceTask / planner node."""
    def __init__(self, status=lifecycle.PLANNED, updated_at=None):
        self.status = status
        self.updated_at = updated_at
        self.result_summary = ""


# ══════════════════════════════════════════════════════════════════════════════
#  TASK 3.7 — the lifecycle state machine
# ══════════════════════════════════════════════════════════════════════════════

def test_succeeded_is_reachable_only_from_executing():
    """The load-bearing rule. Success must be something that gets reported,
    never something the system assumes on the author's behalf."""
    for status in lifecycle.ALL_STATUSES - {lifecycle.EXECUTING, lifecycle.SUCCEEDED}:
        assert not lifecycle.can_transition(status, lifecycle.SUCCEEDED), \
            f"{status} → succeeded must be illegal"
    assert lifecycle.can_transition(lifecycle.EXECUTING, lifecycle.SUCCEEDED)


def test_invalid_transitions_are_rejected():
    for current, new in (
        (lifecycle.FAILED, lifecycle.EXECUTING),      # a retry is a NEW command
        (lifecycle.SUCCEEDED, lifecycle.PLANNED),
        (lifecycle.SUCCEEDED, lifecycle.FAILED),
        (lifecycle.SKIPPED, lifecycle.SUCCEEDED),
        (lifecycle.READY, lifecycle.SUCCEEDED),       # never without executing
    ):
        node = _Node(current)
        try:
            lifecycle.transition(node, new, source="test")
            raise AssertionError(f"{current} → {new} should have been rejected")
        except InvalidTransition:
            pass
        assert node.status == current, "a rejected transition must not mutate state"


def test_terminal_statuses_are_terminal():
    for status in lifecycle.TERMINAL:
        assert lifecycle._ALLOWED[status] == frozenset(), f"{status} must be terminal"


def test_valid_transitions_are_allowed():
    for current, new in (
        (lifecycle.PLANNED, lifecycle.READY),
        (lifecycle.PLANNED, lifecycle.AWAITING_CONFIRMATION),
        (lifecycle.READY, lifecycle.EXECUTING),
        (lifecycle.AWAITING_CONFIRMATION, lifecycle.EXECUTING),
        (lifecycle.AWAITING_CONFIRMATION, lifecycle.SKIPPED),
        (lifecycle.EXECUTING, lifecycle.SUCCEEDED),
        (lifecycle.EXECUTING, lifecycle.FAILED),
    ):
        node = _Node(current)
        assert lifecycle.transition(node, new, source="test") is True
        assert node.status == new


def test_non_strict_mode_reports_rejection_without_raising():
    node = _Node(lifecycle.SUCCEEDED)
    assert lifecycle.transition(node, lifecycle.PLANNED, source="test", strict=False) is False
    assert node.status == lifecycle.SUCCEEDED


def test_transition_is_idempotent():
    node = _Node(lifecycle.EXECUTING)
    assert lifecycle.transition(node, lifecycle.EXECUTING, source="test") is False
    assert node.status == lifecycle.EXECUTING


def test_transition_records_the_full_audit_line():
    """prev, new, source, reason and timestamp — a disputed outcome has to be
    reconstructable from the log alone."""
    src = inspect.getsource(lifecycle.transition)
    for field in ("prev=%s", "new=%s", "source=%s", "reason=%s", "at=%s"):
        assert field in src, f"transition log is missing {field}"


def test_unknown_or_legacy_status_is_treated_as_unset():
    node = _Node("success")           # the old vocabulary
    assert lifecycle.transition(node, lifecycle.EXECUTING, source="test") is True


# ══════════════════════════════════════════════════════════════════════════════
#  TASK 3.7 — derived command status
# ══════════════════════════════════════════════════════════════════════════════

def test_a_plan_that_has_only_been_dispatched_is_not_success():
    """The exact defect: READY means handed over, not done."""
    assert lifecycle.derive_command_status([lifecycle.READY]) == lifecycle.EXECUTING
    assert lifecycle.derive_command_status([lifecycle.PLANNED]) == lifecycle.EXECUTING


def test_command_succeeds_only_when_every_node_succeeded():
    assert lifecycle.derive_command_status([lifecycle.SUCCEEDED]) == lifecycle.SUCCEEDED
    assert lifecycle.derive_command_status(
        [lifecycle.SUCCEEDED, lifecycle.SUCCEEDED]) == lifecycle.SUCCEEDED
    assert lifecycle.derive_command_status(
        [lifecycle.SUCCEEDED, lifecycle.FAILED]) == lifecycle.FAILED


def test_one_unreported_node_holds_the_whole_command_open():
    assert lifecycle.derive_command_status(
        [lifecycle.SUCCEEDED, lifecycle.EXECUTING]) == lifecycle.EXECUTING


def test_skipped_and_blocked_nodes_do_not_count_against_success():
    assert lifecycle.derive_command_status(
        [lifecycle.SUCCEEDED, lifecycle.SKIPPED, lifecycle.BLOCKED]) == lifecycle.SUCCEEDED


def test_empty_plan_is_not_success():
    assert lifecycle.derive_command_status([]) == lifecycle.FAILED


def test_partial_plan_is_summarised_honestly():
    assert "1 of 2" in lifecycle.summarize_outcome([lifecycle.SUCCEEDED, lifecycle.FAILED])
    assert lifecycle.summarize_outcome([lifecycle.SUCCEEDED]) == "Done."
    assert "didn't work" in lifecycle.summarize_outcome([lifecycle.FAILED])
    assert "hasn't run" in lifecycle.summarize_outcome([lifecycle.EXECUTING])


def test_author_facing_summaries_carry_no_internals():
    for statuses in ([lifecycle.SUCCEEDED], [lifecycle.FAILED],
                     [lifecycle.SUCCEEDED, lifecycle.FAILED], [lifecycle.EXECUTING]):
        message = lifecycle.summarize_outcome(statuses)
        for banned in ("node", "status", "executing", "None", "Exception", "capability"):
            assert banned not in message, f"{message!r} leaks {banned!r}"


# ══════════════════════════════════════════════════════════════════════════════
#  TASK 3.7 — timeout policy
# ══════════════════════════════════════════════════════════════════════════════

def test_a_node_never_stays_executing_for_ever():
    old = datetime.utcnow() - timedelta(seconds=3600)
    node = _Node(lifecycle.EXECUTING, updated_at=old)
    assert lifecycle.expire_stale_nodes([node], timeout_seconds=180) == 1
    assert node.status == lifecycle.FAILED
    assert node.result_summary == lifecycle.TIMEOUT_REASON


def test_timeout_does_not_touch_a_fresh_node():
    node = _Node(lifecycle.EXECUTING, updated_at=datetime.utcnow())
    assert lifecycle.expire_stale_nodes([node], timeout_seconds=180) == 0
    assert node.status == lifecycle.EXECUTING


def test_timeout_does_not_rush_a_thinking_author():
    """awaiting_confirmation is not a timeout — the author has not answered yet."""
    old = datetime.utcnow() - timedelta(seconds=3600)
    node = _Node(lifecycle.AWAITING_CONFIRMATION, updated_at=old)
    assert lifecycle.expire_stale_nodes([node], timeout_seconds=180) == 0
    assert node.status == lifecycle.AWAITING_CONFIRMATION


def test_timeout_reason_is_author_safe_and_actionable():
    assert "try again" in lifecycle.TIMEOUT_REASON.lower()
    for banned in ("timeout", "executing", "node", "None"):
        assert banned not in lifecycle.TIMEOUT_REASON


def test_timeout_is_configurable():
    from config import settings
    assert settings.voice_execution_timeout_seconds > 0


def test_a_server_restart_fails_unreported_steps():
    src = (BACKEND / "startup/orphan_recovery.py").read_text(encoding="utf-8")
    assert "VoiceTask" in src and "lifecycle.EXECUTING" in src
    assert "lifecycle.FAILED" in src, "a restart must not leave steps claiming to run"


# ══════════════════════════════════════════════════════════════════════════════
#  TASK 3.7 — the call sites
# ══════════════════════════════════════════════════════════════════════════════

def _code_lines(src: str) -> str:
    """Source with comment lines stripped — so a test cannot be fooled by a
    comment that quotes the very code it is checking for."""
    return "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))


def test_agent_no_longer_assigns_success_at_plan_time():
    from services.voice import agent
    code = _code_lines(inspect.getsource(agent))
    assert 'status = "success"' not in code, "the false-success assignment is back"
    assert "derive_command_status" in code


def test_orchestrator_treats_an_empty_adapter_result_as_failure():
    """An adapter returning None or {} has not done the thing; "Done." was a lie."""
    from services.voice import orchestrator
    src = inspect.getsource(orchestrator.execute)
    assert '.get("answer", "Done.")' not in src
    assert "adapter returned no result" in src


def test_dead_summarize_result_is_gone():
    from services.voice import orchestrator
    assert not hasattr(orchestrator, "_summarize_result"), \
        "_summarize_result returned 'Done.' for any result and was called from nowhere"


def test_orchestrator_routes_every_status_change_through_the_helper():
    from services.voice import orchestrator
    src = inspect.getsource(orchestrator.execute)
    direct = re.findall(r"node\.status\s*=\s*[\"']", src)
    assert not direct, f"status assigned directly, bypassing the state machine: {direct}"


def test_confirmation_no_longer_means_completion():
    src = (BACKEND / "routers/voice_agent.py").read_text(encoding="utf-8")
    assert 'task.status = "done" if body.applied' not in src
    assert "cmd.confirmed = bool(body.confirmed)" in src, \
        "approval must be recorded as approval, not as an applied change"


def test_one_applied_node_does_not_complete_a_whole_workflow():
    src = (BACKEND / "routers/voice_agent.py").read_text(encoding="utf-8")
    assert 'wf.status = "completed"' not in src
    assert "_resync_workflow" in src


def test_command_status_default_is_not_optimistic():
    from models import VoiceCommand
    assert VoiceCommand.__table__.c.status.default.arg == lifecycle.PLANNED


# ══════════════════════════════════════════════════════════════════════════════
#  TASK 3.7 — the result-report endpoint
# ══════════════════════════════════════════════════════════════════════════════

def _endpoint_source():
    src = (BACKEND / "routers/voice_agent.py").read_text(encoding="utf-8")
    start = src.index("def report_node_result")
    return src[start:src.index("\n@router.", start)] if "\n@router." in src[start:] else src[start:]


def test_result_endpoint_validates_ownership_and_liveness():
    src = _endpoint_source()
    assert "VoiceCommand.user_id == current_user.user_id" in src, "user must own the command"
    assert "VoiceWorkflow.command_id == command_id" in src, "workflow must belong to the command"
    assert "VoiceTask.node_key == node_key" in src, "node must belong to the workflow"
    assert "lifecycle.TERMINAL" in src, "a finished node must not accept a new result"


def test_result_endpoint_is_idempotent_for_terminal_nodes():
    src = _endpoint_source()
    assert "recorded=False" in src, "a duplicate report must be a no-op, not a state change"


def test_result_endpoint_passes_through_executing():
    """SUCCEEDED is unreachable except from EXECUTING, so the endpoint must move
    the node there first rather than jumping straight to a terminal status."""
    src = _endpoint_source()
    assert "lifecycle.EXECUTING" in src
    assert "lifecycle.SUCCEEDED if body.ok else lifecycle.FAILED" in src


def test_result_endpoint_is_registered():
    from routers import voice_agent
    paths = {r.path for r in voice_agent.router.routes}
    assert "/commands/{command_id}/nodes/{node_key}/result" in paths


def test_result_request_separates_outcome_from_approval():
    import schemas
    assert "ok" in schemas.VoiceNodeResultRequest.model_fields
    assert "confirmed" not in schemas.VoiceNodeResultRequest.model_fields, \
        "outcome and approval must not travel in the same field"


# ══════════════════════════════════════════════════════════════════════════════
#  TASK 3.7 — the frontend half of the loop
# ══════════════════════════════════════════════════════════════════════════════

def test_frontend_reports_results_for_non_confirmation_actions():
    """The channel that did not exist: read/analyze/generate steps ran in the
    browser and told the backend nothing.

    Reporting now goes through the `reportOutcome` helper (corrective plan A,
    2026-07-26), so this asserts that runPlan reports — not which literal call
    it uses."""
    src = (FRONTEND / "components/voice/useVoiceAgent.ts").read_text(encoding="utf-8")
    run_plan = src[src.index("const runPlan"):src.index("const confirm")]
    assert "reportOutcome(" in run_plan, "runPlan must report every executed step"
    helper = src[src.index("const reportOutcome"):src.index("const reportApproval")]
    assert "voiceApi.reportResult" in helper, "reportOutcome must call the result endpoint"


def test_frontend_reports_results_for_confirmed_actions_too():
    src = (FRONTEND / "components/voice/useVoiceAgent.ts").read_text(encoding="utf-8")
    confirm = src[src.index("const confirm"):src.index("const handleFinal")]
    assert "reportOutcome(" in confirm, "the confirmation path must report its outcome"
    assert "reportApproval(resp.command_id, node.node_key, true)" in confirm, \
        "approval must no longer carry the outcome"
    approval = src[src.index("const reportApproval"):src.index("const runPlan")]
    assert "voiceApi.confirm" in approval


def test_a_failure_to_record_an_outcome_is_never_silent():
    """A swallowed error is how a total failure of the recording channel went
    unnoticed until live verification (2026-07-26). Neither helper may hide one."""
    src = (FRONTEND / "components/voice/useVoiceAgent.ts").read_text(encoding="utf-8")
    helpers = src[src.index("const reportOutcome"):src.index("const runPlan")]
    assert "catch { /* noop */ }" not in helpers, "a recording failure is being swallowed"
    assert "console.error" in helpers, "a recording failure must be logged"
    assert "toast" in helpers, "a recording failure must be surfaced to the author"


def test_api_client_exposes_report_result():
    src = (FRONTEND / "lib/api.ts").read_text(encoding="utf-8")
    assert "reportResult:" in src
    assert "/nodes/${nodeKey}/result" in src


# ══════════════════════════════════════════════════════════════════════════════
#  TASK 3.6 — routing, drop points and intent
# ══════════════════════════════════════════════════════════════════════════════

def test_every_client_action_has_a_frontend_executor():
    """A declared capability with no executor is a request that vanishes."""
    from services.voice.capabilities import CAPABILITY_REGISTRY
    src = (FRONTEND / "lib/voiceActions.ts").read_text(encoding="utf-8")
    cases = set(re.findall(r"case '([\w.]+)'", src))

    missing = []
    for name, cap in CAPABILITY_REGISTRY.items():
        for action, spec in cap.actions.items():
            if getattr(spec, "execution_locus", "client") == "client":
                if f"{name}.{action}" not in cases:
                    missing.append(f"{name}.{action}")
    assert not missing, f"client actions with no executor: {missing}"


def test_every_server_action_has_an_adapter():
    from services.voice.capabilities import CAPABILITY_REGISTRY
    from services.voice.adapters import SERVER_ADAPTERS
    missing = []
    for name, cap in CAPABILITY_REGISTRY.items():
        for action, spec in cap.actions.items():
            if getattr(spec, "execution_locus", "client") == "server":
                if (name, action) not in SERVER_ADAPTERS:
                    missing.append(f"{name}.{action}")
    assert not missing, f"server actions with no adapter: {missing}"


def test_disambiguation_never_invents_an_action():
    """An action absent from the registry produces a client_call nothing can
    execute — the request is accepted and then silently dropped."""
    from services.voice.capabilities import CAPABILITY_REGISTRY, get_action, disambiguate_action
    invalid = []
    commands = ["create a chapter called Storm", "delete it", "rename this",
                "open chapter three", "show me the list", "undo that", "export it"]
    for name in CAPABILITY_REGISTRY:
        for command in commands:
            for hint in ("create", "delete", "update", "list", "open", ""):
                action = disambiguate_action(name, command, hint)
                if get_action(name, action) is None:
                    invalid.append(f"{name}.{action}")
    assert not invalid, f"intent layer can emit non-existent actions: {sorted(set(invalid))[:5]}"


def test_the_reported_utterance_still_routes_and_extracts_its_title():
    """Phase 2 Issue 4's example. Routing and extraction are sound — the failure
    was never here, which is why the fix is honesty about outcomes."""
    from services.voice.capabilities import get_action, extract_inline_params
    spec = get_action("chapter_mgmt", "create")
    assert spec is not None and spec.execution_locus == "client"
    assert spec.needs_confirmation() is True, "a write must be confirmed, not silently applied"
    assert extract_inline_params("chapter_mgmt", "create",
                                 "create a chapter called Storm") == {"title": "Storm"}


def test_unreadable_classification_fails_honestly_instead_of_guessing():
    """It used to become {} → a guess at confidence 0.4 → below the 0.55
    threshold → a clarification prompt. The author saw "I didn't understand",
    which is indistinguishable from the agent mishearing them."""
    from services.voice import intent
    assert intent.coerce_intent(None)[0] is None
    assert intent.coerce_intent({})[0] is None
    assert intent.coerce_intent({"capability": ""})[0] is None
    assert intent.coerce_intent({"capability": "chapter_mgmt"})[0] is not None

    src = inspect.getsource(intent.classify)
    assert "complete_structured" in src, "intent must use the structured contract"
    assert "fallback={}" not in src, "the silent-fallback is the defect"


def test_intent_logs_its_decision_without_the_authors_words():
    """The command text belongs in the prompt — the model needs it. It must not
    appear in a LOG line: the author's spoken words are about their manuscript."""
    from services.voice import intent
    src = inspect.getsource(intent.classify)
    assert "stage=classify" in src
    assert "capability=%s" in src and "confidence=%.2f" in src

    log_calls = re.findall(r"logger\.\w+\((?:[^()]|\([^()]*\))*\)", src, re.S)
    assert log_calls, "classify records no decision at all"
    for call in log_calls:
        for leak in ("command", "user", "brief", "transcript"):
            assert leak not in call, f"log call leaks {leak!r}: {call.strip()[:90]}"


def test_drop_points_are_distinguishable():
    """Each way a request can stop must produce its own status, so the log says
    which one happened rather than 'nothing occurred'."""
    for status in (lifecycle.NEEDS_INPUT, lifecycle.BLOCKED, lifecycle.SKIPPED,
                   lifecycle.FAILED, lifecycle.AWAITING_CONFIRMATION):
        assert status in lifecycle.ALL_STATUSES
    assert len({lifecycle.NEEDS_INPUT, lifecycle.BLOCKED, lifecycle.SKIPPED,
                lifecycle.FAILED, lifecycle.AWAITING_CONFIRMATION}) == 5


def test_unmapped_client_call_is_reported_not_swallowed():
    src = (FRONTEND / "lib/voiceActions.ts").read_text(encoding="utf-8")
    assert "ok: false" in src and "No executor for" in src, \
        "an unmapped action must return a failure, never silence"


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
