"""
Phase 3 plan catalogue and limit resolution (spec §21).

The single authority for every Phase 3 quantity limit (product rule R8 — limits
are configuration, not code). Routers never hold a business number; they call
the enforce_* helpers here, which raise ApiError with the §17.4 error
contract so every surface reports limits the same way.

Values are decision D1 (recorded 2026-09-21, accepted as proposed). Any subset
of any plan can be overridden with settings.plan_limits_json — parsed and
validated when this module is imported, so a malformed override stops the
backend at startup instead of running with silently-wrong limits.

Plan assignment is manual/admin for now (decision D2): users.plan is NULL for
every existing account and NULL resolves to "free".
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields, replace

from exceptions import ApiError

from config import settings


@dataclass(frozen=True)
class PlanLimits:
    max_pins: int
    pin_ttl_days: int
    max_pin_chars: int
    max_context_pins: int
    max_idea_cards: int          # -1 = unlimited
    max_style_samples: int
    can_extend_ttl: bool
    strict_consistency: bool     # Tier-2 consistency check (extra LLM call) — D6


DEFAULT_PLAN = "free"

_DEFAULT_PLANS: dict[str, PlanLimits] = {
    "free":   PlanLimits(20,   7,  8_000, 2,  50,  1, False, False),
    "basic":  PlanLimits(60,  30,  8_000, 3, 200,  3, True,  False),
    "pro":    PlanLimits(200, 90, 16_000, 5,  -1,  8, True,  True),
    "studio": PlanLimits(500, 180, 32_000, 8, -1, 15, True,  True),
}

_FIELD_TYPES = {f.name: f.type for f in fields(PlanLimits)}


def _parse_overrides(raw: str) -> dict[str, dict]:
    if not raw or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"PLAN_LIMITS_JSON is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("PLAN_LIMITS_JSON must be a JSON object of {plan: {limit: value}}")
    for plan, overrides in data.items():
        if not isinstance(overrides, dict):
            raise ValueError(f"PLAN_LIMITS_JSON[{plan!r}] must be an object")
        for key, value in overrides.items():
            if key not in _FIELD_TYPES:
                raise ValueError(f"PLAN_LIMITS_JSON[{plan!r}] has unknown limit {key!r}")
            expected = _FIELD_TYPES[key]
            if expected in ("bool", bool):
                if not isinstance(value, bool):
                    raise ValueError(f"PLAN_LIMITS_JSON[{plan!r}][{key!r}] must be true/false")
            elif isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"PLAN_LIMITS_JSON[{plan!r}][{key!r}] must be an integer")
            elif value < -1 or (value == -1 and key != "max_idea_cards"):
                raise ValueError(f"PLAN_LIMITS_JSON[{plan!r}][{key!r}] is out of range")
    return data


def resolve_plans(raw_override: str | None = None) -> dict[str, PlanLimits]:
    """Defaults merged with the override. A new plan name in the override is
    built on top of the free plan, so it can never be missing a limit."""
    overrides = _parse_overrides(settings.plan_limits_json if raw_override is None else raw_override)
    plans = dict(_DEFAULT_PLANS)
    for plan, values in overrides.items():
        base = plans.get(plan, _DEFAULT_PLANS[DEFAULT_PLAN])
        plans[plan] = replace(base, **values)
    return plans


# Import-time validation (spec §37.2: "Malformed plan_limits_json fails at import").
_PLANS: dict[str, PlanLimits] = resolve_plans()


def plan_name(user) -> str:
    name = getattr(user, "plan", None) or DEFAULT_PLAN
    return name if name in _PLANS else DEFAULT_PLAN


def get_limits(user) -> PlanLimits:
    """NULL or unknown plan → free. Never raises."""
    return _PLANS[plan_name(user)]


def limits_payload(user, used: int | None = None, max_key: str = "max_pins") -> dict:
    limits = get_limits(user)
    payload = {"plan": plan_name(user), "max": getattr(limits, max_key)}
    if used is not None:
        payload["used"] = used
    return payload


def limits_dict(user) -> dict:
    return asdict(get_limits(user))


# ── Enforcement helpers (spec §21.3) ──────────────────────────────────────────

def enforce_pin_size(user, content: str) -> None:
    limits = get_limits(user)
    if len(content) > limits.max_pin_chars:
        raise ApiError(
            413,
            (f"This result is too long to pin on the {plan_name(user)} plan "
                       f"({len(content):,} of {limits.max_pin_chars:,} characters). "
                       "You can send it to the Idea Shelf instead."),
            code="pin_too_large",
            limits=limits_payload(user, max_key="max_pin_chars"),
        )


def enforce_context_pins(user, count: int) -> None:
    limits = get_limits(user)
    if count > limits.max_context_pins:
        raise ApiError(
            422,
            (f"The {plan_name(user)} plan can use up to {limits.max_context_pins} "
                       f"pinned versions as context ({count} selected)."),
            code="too_many_context_pins",
            limits=limits_payload(user, used=count, max_key="max_context_pins"),
        )


def enforce_idea_card_create(user, current_count: int) -> None:
    limits = get_limits(user)
    if limits.max_idea_cards != -1 and current_count >= limits.max_idea_cards:
        raise ApiError(
            409,
            (f"The Idea Shelf is full for the {plan_name(user)} plan "
                       f"({current_count} of {limits.max_idea_cards}). Archive or delete an idea to add another."),
            code="idea_limit_reached",
            limits=limits_payload(user, used=current_count, max_key="max_idea_cards"),
        )


def enforce_style_sample_create(user, current_count: int) -> None:
    limits = get_limits(user)
    if current_count >= limits.max_style_samples:
        raise ApiError(
            409,
            (f"The {plan_name(user)} plan keeps up to {limits.max_style_samples} "
                       "style sample(s) per story. Remove one to add another."),
            code="style_sample_limit_reached",
            limits=limits_payload(user, used=current_count, max_key="max_style_samples"),
        )
