"""
Stage 12.3 — task 7.10: a Tier-2 consistency warning describes the
contradiction (what the passage does) instead of restating the rule.

Live 2026-09-25 (tests/manual_phase3_live_e2e.py, D6 Tier-2 scenario): the
story's world rule is "The harbour lamps are lit only by the keeper."; the
rewrite adds "Elara lit the harbour lamps herself."; the 7B model's warning was
the rule itself. These tests pin the post-processing that turns such an echo
into a describing warning from a verified quote, and drops an echo that points
at nothing in the passage. No model is called here; the live re-measurement is
backend/scripts/quality/tier2_warning_text_probe.py.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import consistency  # noqa: E402
from services.consistency import _coerce_issues, restates_rule, verified_quote  # noqa: E402

RULE = "The harbour lamps are lit only by the keeper."
BLOCK = ("STORY CONTEXT — facts already established.\n"
         "CHARACTERS IN THIS PASSAGE\nElara — a fisher's daughter, careful and quiet\n"
         f"WORLD RULES\n{RULE}")
PASSAGE = ("Kira waited by the window. The harbour lights went out one by one and she did not move. "
           "Elara lit the harbour lamps herself.")


def _one(issue):
    out, dropped = _coerce_issues({"issues": [issue]}, PASSAGE, BLOCK)
    return out, dropped


def test_the_recorded_live_echo_becomes_a_describing_warning():
    out, dropped = _one({"kind": "world_rule", "rule": RULE, "quote": "Elara lit the harbour lamps herself.",
                         "message": "The harbour lamps are lit only by the keeper."})
    assert dropped == 0 and len(out) == 1
    w = out[0]
    assert w["message"] != RULE
    assert "Elara lit the harbour lamps herself" in w["message"]        # what the passage did
    assert "established world rule" in w["message"] and RULE in w["message"]   # what it breaks
    assert w["evidence"] == "Elara lit the harbour lamps herself."
    assert w["severity"] == "soft" and w["kind"] == "consistency"


def test_a_describing_message_is_kept_as_written_with_its_evidence():
    msg = "Elara lights the lamps herself, although only the keeper may light them."
    out, _ = _one({"kind": "world_rule", "rule": RULE, "quote": "Elara lit the harbour lamps herself",
                   "message": msg})
    assert out[0]["message"] == msg
    assert out[0]["evidence"] == "Elara lit the harbour lamps herself"


def test_an_echo_with_nothing_in_the_passage_to_point_at_is_dropped():
    for echo in (RULE, "Only the keeper may light the harbour lamps."):
        out, dropped = _one({"kind": "world_rule", "rule": RULE, "quote": "", "message": echo})
        assert out == [] and dropped == 1, echo


def test_an_invented_quote_is_not_presented_as_evidence():
    out, _ = _one({"kind": "world_rule", "rule": RULE, "quote": "Elara smashed every lamp in the harbour",
                   "message": "Elara lights the harbour lamps herself instead of the keeper."})
    assert len(out) == 1 and "evidence" not in out[0]
    assert out[0]["message"].startswith("Elara lights")


def test_quote_verification_ignores_case_punctuation_and_curly_quotes():
    assert verified_quote("“elara LIT the harbour lamps herself”", PASSAGE) == "elara LIT the harbour lamps herself"
    assert verified_quote("lamps herself Elara", PASSAGE) is None          # not contiguous
    assert verified_quote("", PASSAGE) is None


def test_restatement_detection():
    assert restates_rule(RULE, RULE, BLOCK, PASSAGE)
    assert restates_rule("Only the keeper may light the harbour lamps.", RULE, BLOCK, PASSAGE)
    assert not restates_rule("Elara lit the harbour lamps herself, which only the keeper may do.",
                             RULE, BLOCK, PASSAGE)
    # a trait contradiction names the passage's action
    assert not restates_rule("Kira does not move while the lights go out, though she is recorded as restless.",
                             "Kira is restless and never sits still.", "", PASSAGE)


def test_strict_check_returns_describing_warnings_and_never_edits_the_passage(monkeypatch):
    from services import ai_service
    seen = {}

    async def fake_structured(system, user, *, coerce, **_k):
        seen["system"], seen["user"] = system, user
        return coerce({"issues": [{"kind": "world_rule", "rule": RULE,
                                   "quote": "Elara lit the harbour lamps herself.",
                                   "message": RULE}]})[0], {}

    monkeypatch.setattr(ai_service, "complete_structured", fake_structured)
    warnings, ran = asyncio.run(consistency.strict_consistency_check(BLOCK, PASSAGE))
    assert ran is True and len(warnings) == 1
    assert "Elara lit the harbour lamps herself" in warnings[0]["message"]
    assert '"quote"' in seen["system"] and "Do not just repeat the rule" in seen["system"]
    assert PASSAGE in seen["user"]
    assert set(warnings[0]) <= {"kind", "severity", "message", "entity", "evidence", "rule"}   # no edit field


def test_old_shape_without_rule_or_quote_still_works_when_descriptive():
    out, _ = _coerce_issues({"issues": [{"kind": "trait",
                                         "message": "Kira sits motionless at the window though she is restless."}]},
                            PASSAGE, "CHARACTERS\nKira — restless, never sits still")
    assert len(out) == 1 and out[0]["entity"] == {"type": "trait"}
