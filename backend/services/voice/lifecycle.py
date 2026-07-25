"""
Voice workflow lifecycle — the single place a status is allowed to change.

Tasks 3.6 / 3.7. The voice agent used to report success when the *plan* was
built: client-side nodes were still unexecuted, their results still None, and
nothing ever reported back for non-mutating actions. The author was told their
chapter had been created before anything had tried to create it.

Fixing that is not a matter of moving one assignment. Status was written in five
places with no rules about which change was legal, so "succeeded" could be
reached from anywhere. This module makes the lifecycle explicit:

  * one vocabulary, shared by backend and frontend;
  * one function that performs a change, rejecting illegal ones;
  * SUCCEEDED reachable ONLY from EXECUTING, and only via an actual result;
  * every change logged with previous → new, source and reason.

The invariant worth stating plainly: nothing in this system may record success
on the author's behalf. Success is something that is *reported*, never assumed.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

# ── The vocabulary ────────────────────────────────────────────────────────────

PLANNED               = "planned"                # in the graph, not yet resolved
NEEDS_INPUT           = "needs_input"            # a required parameter is missing
AWAITING_CONFIRMATION = "awaiting_confirmation"  # mutating action held for the author
READY                 = "ready"                  # approved to run, NOT yet run
EXECUTING             = "executing"              # handed over; outcome unknown
SUCCEEDED             = "succeeded"              # confirmed by an actual result
FAILED                = "failed"                 # reported failure
SKIPPED               = "skipped"                # deliberately not run (rejected)
BLOCKED               = "blocked"                # an upstream node did not produce

ALL_STATUSES = frozenset({
    PLANNED, NEEDS_INPUT, AWAITING_CONFIRMATION, READY, EXECUTING,
    SUCCEEDED, FAILED, SKIPPED, BLOCKED,
})

#: Nothing leaves a terminal status. A retry is a NEW command with a new plan —
#: which is what actually happens when the author speaks again. Allowing
#: failed → executing would let a late or duplicate report resurrect a node and
#: quietly turn a recorded failure into a success.
TERMINAL = frozenset({SUCCEEDED, FAILED, SKIPPED, BLOCKED})

_ALLOWED: dict[str, frozenset[str]] = {
    PLANNED:               frozenset({READY, AWAITING_CONFIRMATION, NEEDS_INPUT,
                                      BLOCKED, EXECUTING, FAILED, SKIPPED}),
    NEEDS_INPUT:           frozenset({READY, AWAITING_CONFIRMATION, SKIPPED, BLOCKED}),
    AWAITING_CONFIRMATION: frozenset({EXECUTING, SKIPPED, FAILED, BLOCKED}),
    READY:                 frozenset({EXECUTING, SKIPPED, FAILED, BLOCKED}),
    # The load-bearing row: success is reachable from EXECUTING and nowhere else.
    EXECUTING:             frozenset({SUCCEEDED, FAILED, SKIPPED}),
    SUCCEEDED:             frozenset(),
    FAILED:                frozenset(),
    SKIPPED:               frozenset(),
    BLOCKED:               frozenset(),
}


class InvalidTransition(ValueError):
    """Raised when code tries to make an illegal status change."""

    def __init__(self, current: str, new: str, source: str):
        super().__init__(
            f"illegal voice lifecycle transition {current!r} → {new!r} (source={source})"
        )
        self.current, self.new, self.source = current, new, source


def can_transition(current: Optional[str], new: str) -> bool:
    if new not in ALL_STATUSES:
        return False
    if current is None or current not in ALL_STATUSES:
        return True          # unknown/legacy value — treat as unset
    if current == new:
        return True          # idempotent re-assert
    return new in _ALLOWED[current]


def transition(
    entity,
    new_status: str,
    *,
    source: str,
    reason: str = "",
    field: str = "status",
    strict: bool = True,
) -> bool:
    """
    Move ``entity.<field>`` to ``new_status``, enforcing the lifecycle.

    Returns True when the status changed. Raises InvalidTransition on an illegal
    change when ``strict`` — the default, because an illegal change is a bug in
    the caller, and the failure mode it guards against (a stale report flipping a
    failure to a success) is exactly the defect this work exists to remove.

    Every change is logged with previous → new, source and reason, so a
    disputed outcome can be reconstructed from the log alone.
    """
    current = getattr(entity, field, None)

    if not can_transition(current, new_status):
        if strict:
            raise InvalidTransition(current, new_status, source)
        logger.warning(
            "[voice.lifecycle] rejected transition prev=%s new=%s source=%s reason=%s",
            current, new_status, source, reason or "-",
        )
        return False

    if current == new_status:
        return False

    setattr(entity, field, new_status)
    if hasattr(entity, "updated_at"):
        entity.updated_at = datetime.utcnow()

    logger.info(
        "[voice.lifecycle] transition prev=%s new=%s source=%s reason=%s at=%s",
        current, new_status, source, reason or "-", datetime.utcnow().isoformat(timespec="seconds"),
    )
    return True


# ── Derived command status ────────────────────────────────────────────────────

def derive_command_status(node_statuses: Iterable[str]) -> str:
    """
    A command's status, derived from its nodes — never assigned optimistically.

    The rule this replaces was `status = "success"` written the moment the plan
    was built, while every client node still sat unexecuted.
    """
    statuses = list(node_statuses)
    if not statuses:
        return FAILED
    if any(s == EXECUTING for s in statuses):
        return EXECUTING
    if any(s in (READY, PLANNED) for s in statuses):
        return EXECUTING          # dispatched, outcome not yet reported
    if any(s == AWAITING_CONFIRMATION for s in statuses):
        return AWAITING_CONFIRMATION
    if any(s == NEEDS_INPUT for s in statuses):
        return NEEDS_INPUT
    actionable = [s for s in statuses if s not in (SKIPPED, BLOCKED)]
    if not actionable:
        return SKIPPED
    if all(s == SUCCEEDED for s in actionable):
        return SUCCEEDED
    if any(s == SUCCEEDED for s in actionable):
        return FAILED             # partial — see summarize_outcome for the wording
    return FAILED


def summarize_outcome(node_statuses: Iterable[str]) -> str:
    """Author-facing one-liner. Says what happened, never more."""
    statuses = list(node_statuses)
    done   = sum(1 for s in statuses if s == SUCCEEDED)
    failed = sum(1 for s in statuses if s == FAILED)
    total  = sum(1 for s in statuses if s not in (SKIPPED, BLOCKED))

    if total == 0:
        return "Nothing was run."
    if done == total:
        return "Done." if total == 1 else f"Done — all {total} steps completed."
    if done == 0:
        return "That didn't work." if failed else "That hasn't run yet."
    return f"Partly done — {done} of {total} steps completed."


# ── Timeout policy ────────────────────────────────────────────────────────────
#
# A node handed to the client and never reported on must not sit in EXECUTING
# for ever. The author closed the tab, the browser crashed, the network dropped
# — all are silence, and silence is not consent to claim success. After the
# timeout the node becomes FAILED with a reason the author can act on.

DEFAULT_EXECUTION_TIMEOUT_SECONDS = 180

TIMEOUT_REASON = (
    "This didn't finish — the app stopped responding before it completed. "
    "Please check whether it applied, and try again if not."
)


def is_stale(started_at: Optional[datetime], timeout_seconds: int, *,
             now: Optional[datetime] = None) -> bool:
    if started_at is None:
        return False
    now = now or datetime.utcnow()
    return now - started_at > timedelta(seconds=timeout_seconds)


def expire_stale_nodes(nodes, timeout_seconds: int = DEFAULT_EXECUTION_TIMEOUT_SECONDS,
                       *, now: Optional[datetime] = None, source: str = "timeout_sweep") -> int:
    """
    Fail every node stuck in EXECUTING past the timeout. Returns how many.

    Deliberately does NOT touch AWAITING_CONFIRMATION: an author who has not yet
    answered has not timed out, they are thinking.
    """
    expired = 0
    for node in nodes:
        if getattr(node, "status", None) != EXECUTING:
            continue
        started = getattr(node, "updated_at", None) or getattr(node, "created_at", None)
        if not is_stale(started, timeout_seconds, now=now):
            continue
        if transition(node, FAILED, source=source, reason="execution timed out", strict=False):
            if hasattr(node, "result_summary"):
                node.result_summary = TIMEOUT_REASON
            expired += 1
    return expired
