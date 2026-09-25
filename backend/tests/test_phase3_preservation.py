"""
Stage 7 task 7.3 — P3-02 / P3-05 acceptance gaps closed on the Stage 5 engine,
and product rule R6 ("locked content is never silently changed") verified by
TEST, as spec §46 item 2 requires. No DB, no live LLM (fake model).

    pytest backend/tests/test_phase3_preservation.py -q
"""
import asyncio
import random
import re
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from exceptions import ApiError  # noqa: E402
from services import ai_service  # noqa: E402
from services.transform_preservation import (  # noqa: E402
    DEFAULT_PRESERVE_RULES, build_extra_rules_clause, check_dialogue_changes, check_pov_shift,
    check_tense_shift, check_timeline_additions, is_probably_english, validate_locked_ranges,
    verify_preservation,
)

PAST = ("She walked into the hall. She was tired and she looked at the doors. He said nothing. "
        "They waited while she turned away and the lamps flickered.")


# ── Locked-range validation (spec E4, and corruption-safe offsets) ──────────

def test_valid_ranges_pass():
    validate_locked_ranges("One. Two. Three.", [{"start": 0, "end": 4}, {"start": 10, "end": 16}])
    validate_locked_ranges("anything", None)


@pytest.mark.parametrize("ranges", [
    [{"start": 0, "end": 99}],             # beyond text
    [{"start": 5, "end": 5}],              # empty
    [{"start": 6, "end": 2}],              # inverted
    [{"start": 0, "end": 6}, {"start": 4, "end": 9}],   # overlap
])
def test_invalid_ranges_rejected(ranges):
    with pytest.raises(ApiError) as e:
        validate_locked_ranges("One. Two. Three.", ranges)
    assert e.value.status_code == 422 and e.value.code == "invalid_locked_range"


def test_everything_locked_is_rejected():
    text = "One. Two."
    with pytest.raises(ApiError) as e:
        validate_locked_ranges(text, [{"start": 0, "end": 4}, {"start": 5, "end": 9}])
    assert e.value.code == "no_unlocked_segments"


# ── Conservative heuristic checks ──────────────────────────────────────────

def test_tense_flip_detected_and_no_false_positive_on_identical_text():
    present = ("I walk into the hall. I am tired and I look at the doors. He says nothing. "
               "We wait while I turn away.")
    assert check_tense_shift(PAST, present, 0.25) is True
    assert check_tense_shift(PAST, PAST, 0.25) is False


def test_tense_ignores_dialogue():
    text = 'She walked in. She was tired. "I am fine, I know what I want," she said. She turned and looked.'
    assert check_tense_shift(text, text.replace("fine", "okay"), 0.25) is False


def test_pov_shift_detected():
    first = "I walked into the hall. I was tired and I looked at my doors. We waited while I turned away."
    assert check_pov_shift(PAST, first, 0.30) is True
    assert check_pov_shift(PAST, PAST, 0.30) is False


def test_too_little_signal_never_warns():
    assert check_tense_shift("He ran.", "He runs.", 0.25) is False
    assert check_pov_shift("She sat.", "I sat.", 0.30) is False


def test_dialogue_and_timeline_checks():
    src = 'Kira said, "We leave at once." Elara nodded.'
    assert check_dialogue_changes(src, src, 0.6) == []
    assert check_dialogue_changes(src, 'Kira said, "Stay here forever and never go." Elara nodded.', 0.6)
    assert check_dialogue_changes(src, "Kira said nothing.", 0.6)
    assert check_timeline_additions(src, src + " Three days later, at dawn, they left.") == ["at dawn", "three days later"]
    assert check_timeline_additions(src, src) == []


def test_heuristics_skip_translation_and_non_english():
    rules = dict(DEFAULT_PRESERVE_RULES)
    present = "I walk in. I am tired and I look at my doors. We wait while I turn away and he says nothing."
    assert verify_preservation(PAST, present, rules, tool="translate") == []
    fr = "Elle marchait dans la salle. Elle était fatiguée et regardait les portes du château."
    assert not is_probably_english(fr)
    assert [w for w in verify_preservation(fr, present, rules, tool="tone") if w["kind"] in ("tense_shift", "pov_shift")] == []


def test_default_rules_warn_only_and_never_hard():
    present = "I walk in. I am tired and I look at my doors. We wait while I turn away and he says nothing."
    warnings = verify_preservation(PAST, present, dict(DEFAULT_PRESERVE_RULES), tool="tone")
    assert {w["kind"] for w in warnings} >= {"tense_shift", "pov_shift"}
    assert all(w["severity"] == "soft" for w in warnings)
    enforced = dict(DEFAULT_PRESERVE_RULES, tense=True)
    assert [w["severity"] for w in verify_preservation(PAST, present, enforced, tool="tone") if w["kind"] == "tense_shift"] == ["hard"]


def test_default_rules_add_nothing_to_prompt():
    """Byte-compatibility: with default rules the extra clause is empty."""
    assert build_extra_rules_clause(dict(DEFAULT_PRESERVE_RULES), PAST, None) == ""
    clause = build_extra_rules_clause(dict(DEFAULT_PRESERVE_RULES, tense=True, pov=True), PAST,
                                      SimpleNamespace(tense="past", pov_style="third person limited"))
    assert "past tense" in clause and "third person limited" in clause


# ── R6 — locked spans are byte-identical, by test (spec §46 item 2) ─────────

_SENT = re.compile(r"[^.!?]+[.!?]+\s*")


def _adversarial_model(seed):
    rnd = random.Random(seed)

    def responder(system, user, i):
        # Rewrites EVERYTHING, including the text inside [KEEP] — a maximally
        # disobedient model. Sometimes also mangles whitespace/punctuation.
        def mangle(m):
            return m.group(1) + " ".join(w.upper() for w in m.group(2).split()) + rnd.choice(["!", "", "  ?"]) + m.group(3)
        return re.sub(r"(\[(?:KEEP|REWRITE)\])(.*?)(\[/(?:KEEP|REWRITE)\])", mangle, user, flags=re.S)
    return responder


def test_r6_locked_segments_byte_identical_over_100_randomised_runs(monkeypatch):
    base = ("The corridor was long.  Elara walked, slowly, down it! "
            "\"Who's there?\" she asked.\nKira did not answer. The lamps hissed; the doors waited. "
            "Nobody came — not then, not ever.")
    spans = [(m.start(), m.end()) for m in _SENT.finditer(base)]
    monkeypatch.setattr(ai_service, "build_preservation_clause", lambda *a, **k: "")
    monkeypatch.setattr(ai_service, "check_character_name_preservation", lambda *a, **k: [])

    async def no_change_check(*a, **k):
        return True, ""
    monkeypatch.setattr(ai_service, "_assess_change_needed", no_change_check)

    for run in range(100):
        rnd = random.Random(run)
        k = rnd.randint(1, len(spans) - 1)
        locked = sorted(rnd.sample(spans, k))
        ranges = [{"start": s, "end": e} for s, e in locked]
        fake_calls = []

        async def fake_complete(system, user, temperature=0.0, max_tokens=512, response_format=None, _r=_adversarial_model(run)):
            fake_calls.append(1)
            return _r(system, user, len(fake_calls))
        monkeypatch.setattr(ai_service, "_complete", fake_complete)
        result = asyncio.run(ai_service.transform_tone(base, "dark", locked_ranges=ranges))
        out = result["transformed"]
        assert result["failed"] is False, run
        for s, e in locked:
            assert base[s:e] in out, f"run {run}: locked span changed: {base[s:e]!r}"
        # And the locked spans appear in the original order.
        pos = 0
        for s, e in locked:
            nxt = out.find(base[s:e], pos)
            assert nxt >= pos, f"run {run}: locked span out of order"
            pos = nxt + (e - s)


def test_r6_contract_failure_reports_failed_and_keeps_original(monkeypatch):
    """A model that never returns the marker structure → bounded ladder →
    failed=True with the ORIGINAL text; never a wrong rewrite."""
    monkeypatch.setattr(ai_service, "build_preservation_clause", lambda *a, **k: "")

    async def no_change_check(*a, **k):
        return True, ""

    async def broken(system, user, temperature=0.0, max_tokens=512, response_format=None):
        raise ai_service.AIServiceUnavailableError() if False else ValueError("boom")
    monkeypatch.setattr(ai_service, "_assess_change_needed", no_change_check)

    calls = []

    async def no_markers(system, user, temperature=0.0, max_tokens=512, response_format=None):
        calls.append(1)
        if "fragment" in system:
            raise RuntimeError("fallback down")
        return "plain text with no markers"
    monkeypatch.setattr(ai_service, "_complete", no_markers)
    monkeypatch.setattr(ai_service, "_per_segment_fallback", lambda *a, **k: asyncio.sleep(0, result=None))
    text = "First sentence. Second sentence."
    result = asyncio.run(ai_service.transform_tone(text, "dark", locked_ranges=[{"start": 0, "end": 15}]))
    assert result["failed"] is True and result["transformed"] == text
    assert len(calls) == 2   # first attempt + exactly one stricter retry


def test_legacy_path_without_controls_has_no_phase3_fields(monkeypatch):
    """Byte-compatibility: p3=None returns the Stage 5 shape with empty
    Phase 3 fields and the unchanged system prompt."""
    seen = []

    async def fake(system, user, temperature=0.0, max_tokens=512, response_format=None):
        seen.append(system)
        return "Rewritten text."

    async def no_change_check(*a, **k):
        return True, ""
    monkeypatch.setattr(ai_service, "_complete", fake)
    monkeypatch.setattr(ai_service, "_assess_change_needed", no_change_check)
    result = asyncio.run(ai_service.transform_tone("Some text here.", "dark"))
    assert result["warnings"] == [] and result["context_used"] == {} and result["name_autofix"] == []
    assert "ADDITIONAL CONSTRAINTS" not in seen[0] and "STORY CONTEXT" not in seen[0]


def test_equivalent_time_of_day_rewording_is_not_a_new_time_reference():
    """Regression — found by the Stage 7 golden-set measurement: tech-4's
    "By morning" rewritten as "By dawn" was flagged as an added time
    reference (6/54 false positives before the fix, 0/54 after)."""
    src = "By morning the anomaly had a name and a case number."
    assert check_timeline_additions(src, "By dawn, the anomaly bore a name and a case number.") == []
    assert check_timeline_additions("The morning was cold.", "At sunrise it was cold.") == []
    assert check_timeline_additions(src, "By midnight the anomaly had a name.") == ["by midnight"]
