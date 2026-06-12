"""
Safety & Confirmation gate.

Per-node confirmation policy enforced server-side (the frontend re-checks before
executing). A node requires confirmation when:
  - its action_type mutates stored content (write|destructive|export), OR
  - the overall intent confidence is below settings.voice_confidence_threshold, OR
  - it is a terminal mutating node in a multi-step graph (present-then-apply).

Mutating nodes are NEVER auto-executed by the orchestrator — they are only ever
returned as proposed client actions.
"""
from __future__ import annotations

from .capabilities import _MUTATING


def is_safe_to_autorun(node) -> bool:
    """True for read/analyze/generate nodes that do not mutate stored content."""
    return node.action_type not in _MUTATING


def apply(graph, confidence: float) -> bool:
    """
    Set requires_confirmation on each node and return whether the consolidated
    response requires confirmation at all.
    """
    from config import settings
    low_confidence = confidence < settings.voice_confidence_threshold
    any_confirm = False

    for node in graph.nodes:
        needs = node.requires_confirmation
        if node.action_type in _MUTATING:
            needs = True
        if low_confidence and node.action_type in _MUTATING:
            needs = True
        # In a multi-step graph, every mutating step is present-then-apply.
        if graph.is_multi_step and node.action_type in _MUTATING:
            needs = True
        node.requires_confirmation = needs
        any_confirm = any_confirm or needs

    return any_confirm
