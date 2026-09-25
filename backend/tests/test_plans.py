"""
Stage 7 task 7.5 — services/plans.py (spec §21). Pure unit tests: no DB, no LLM.

    pytest backend/tests/test_plans.py -q
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from exceptions import ApiError  # noqa: E402
from services import plans  # noqa: E402


def test_default_limits_match_decision_d1():
    p = plans.resolve_plans("")
    assert (p["free"].max_pins, p["free"].pin_ttl_days, p["free"].max_pin_chars) == (20, 7, 8000)   # D1, D3
    assert (p["free"].max_context_pins, p["free"].max_idea_cards, p["free"].max_style_samples) == (2, 50, 1)
    assert p["free"].can_extend_ttl is False and p["free"].strict_consistency is False
    assert (p["basic"].max_pins, p["basic"].pin_ttl_days, p["basic"].max_idea_cards) == (60, 30, 200)
    assert (p["pro"].max_pins, p["pro"].pin_ttl_days, p["pro"].max_pin_chars) == (200, 90, 16000)
    assert p["pro"].max_idea_cards == -1 and p["pro"].strict_consistency is True        # D6: pro+
    assert (p["studio"].max_pins, p["studio"].pin_ttl_days, p["studio"].max_context_pins) == (500, 180, 8)


@pytest.mark.parametrize("plan", [None, "", "no_such_plan"])
def test_null_or_unknown_plan_resolves_to_free(plan):
    user = SimpleNamespace(plan=plan)
    assert plans.plan_name(user) == "free"
    assert plans.get_limits(user) == plans.resolve_plans("")["free"]


def test_override_changes_only_named_values():
    p = plans.resolve_plans('{"free": {"max_pins": 30}, "pro": {"can_extend_ttl": false}}')
    assert p["free"].max_pins == 30 and p["free"].pin_ttl_days == 7
    assert p["pro"].can_extend_ttl is False and p["pro"].max_pins == 200


def test_override_can_define_new_plan_on_top_of_free():
    p = plans.resolve_plans('{"team": {"max_pins": 999}}')
    assert p["team"].max_pins == 999 and p["team"].pin_ttl_days == p["free"].pin_ttl_days


@pytest.mark.parametrize("raw", [
    "{not json", '["free"]', '{"free": 3}', '{"free": {"max_pinz": 1}}',
    '{"free": {"max_pins": "20"}}', '{"free": {"can_extend_ttl": 1}}', '{"free": {"max_pins": -5}}',
    '{"free": {"max_pins": -1}}',
])
def test_malformed_override_fails_fast(raw):
    with pytest.raises(ValueError):
        plans.resolve_plans(raw)


def test_unlimited_idea_cards_is_allowed_only_for_idea_cards():
    assert plans.resolve_plans('{"free": {"max_idea_cards": -1}}')["free"].max_idea_cards == -1


def test_enforcement_errors_follow_error_contract():
    free = SimpleNamespace(plan="free")
    with pytest.raises(ApiError) as e:
        plans.enforce_pin_size(free, "x" * 8001)
    assert e.value.status_code == 413 and e.value.code == "pin_too_large"
    assert e.value.body()["limits"] == {"plan": "free", "max": 8000}
    with pytest.raises(ApiError) as e:
        plans.enforce_context_pins(free, 3)
    assert e.value.status_code == 422 and e.value.code == "too_many_context_pins"
    plans.enforce_context_pins(free, 2)   # at the limit is fine
    with pytest.raises(ApiError) as e:
        plans.enforce_idea_card_create(free, 50)
    assert e.value.status_code == 409
    plans.enforce_idea_card_create(SimpleNamespace(plan="pro"), 10_000)   # unlimited
    with pytest.raises(ApiError):
        plans.enforce_style_sample_create(free, 1)


def test_no_business_number_hardcoded_in_phase3_routers():
    """R8 — limits are configuration, not code: the Phase 3 routers never
    contain a plan value; they call services/plans."""
    root = Path(__file__).resolve().parents[1]
    import re
    src = (root / "routers" / "ai_workspace.py").read_text()
    for pattern in (r"max_pins\s*[=<>]+\s*\d", r"pin_ttl_days\s*=\s*\d", r"timedelta\(days=\d",
                    r"max_context_pins\s*[=<>]+\s*\d", r"max_idea_cards\s*[=<>]+\s*\d"):
        assert not re.search(pattern, src, re.M), pattern
