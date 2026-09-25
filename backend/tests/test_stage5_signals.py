"""
Stage 5 task 5.14 — deterministic signal modules (no DB, no model):
timeline candidates, narrative-structure signals, relationship arcs.

    pytest backend/tests/test_stage5_signals.py -q
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.narrative_signals import (  # noqa: E402
    MAX_SIGNALS, build_narrative_signals, dead_end_threshold, format_signals_for_prompt,
)
from services.relationship_arcs import build_relationship_arcs  # noqa: E402
from services.timeline_signals import (  # noqa: E402
    MAX_TIMELINE_SIGNALS, build_timeline_signals, format_timeline_signals_for_prompt, parse_anchors,
)


def _ch(n, markers=(), events=()):
    return {"chapter_number": n, "timeline_markers": list(markers), "key_events": list(events)}


def _kinds(sigs):
    return [s["kind"] for s in sigs]


# ── Timeline: parser ─────────────────────────────────────────────────────────

def test_parser_reads_every_date_form():
    a = parse_anchors(_ch(1, ["March 3, 1998", "4 June 1999", "2001-02-10", "in 1985"]))
    dates = sorted(d[0].isoformat() for d in a["dates"])
    assert dates == ["1985-01-01", "1998-03-03", "1999-06-04", "2001-02-10"]
    precisions = {d[2]: d[1] for d in a["dates"]}
    assert precisions["1985"] == "year" and precisions["March 3, 1998"] == "day"


def test_parser_reads_ages_seasons_and_flash_cues():
    a = parse_anchors(_ch(1, ["summer 1998"], ["Mara was 16 when she left", "the 40-year-old Tobias waits"]))
    assert a["ages"]["Mara"][0] == 16 and a["ages"]["Tobias"][0] == 40
    assert ("summer", 1998) in a["seasons"]
    assert a["flash"] is False
    assert parse_anchors(_ch(2, ["Years earlier, in 1990"]))["flash"] is True
    assert parse_anchors(_ch(3, [], ["She remembered the flood"]))["flash"] is True


def test_parser_ignores_invalid_dates_and_implausible_ages():
    a = parse_anchors(_ch(1, ["February 30, 1998"], ["Room was 404 feet away"]))
    assert all(d[1] == "year" for d in a["dates"])       # the bad day is not a full date
    assert a["ages"] == {}


# ── Timeline: each conflict type ─────────────────────────────────────────────

def test_date_reversal_is_detected_and_cites_both_chapters():
    sigs = build_timeline_signals([_ch(1, ["March 3, 1998"]), _ch(2, ["June 1, 1997"])])
    assert _kinds(sigs) == ["date_reversal"]
    assert sigs[0]["chapters"] == [1, 2] and sigs[0]["confidence"] == 0.8


def test_year_only_reversal_is_lower_confidence():
    sigs = build_timeline_signals([_ch(1, ["1998"]), _ch(2, ["1995"])])
    assert _kinds(sigs) == ["date_reversal"] and sigs[0]["confidence"] == 0.6


def test_age_decrease_is_detected():
    sigs = build_timeline_signals([_ch(1, [], ["Mara was 16"]), _ch(4, [], ["Mara is 14"])])
    assert _kinds(sigs) == ["age_decrease"] and sigs[0]["chapters"] == [1, 4]


def test_weekday_mismatch_is_detected():
    # 3 March 1998 was a Tuesday.
    sigs = build_timeline_signals([_ch(1, ["Monday, March 3, 1998"])])
    assert _kinds(sigs) == ["weekday_mismatch"] and "Tuesday" in sigs[0]["detail"]
    assert build_timeline_signals([_ch(1, ["Tuesday, March 3, 1998"])]) == []


def test_season_reversal_within_one_year_and_winter_never_compared():
    sigs = build_timeline_signals([_ch(1, ["autumn 2003"]), _ch(2, ["spring 2003"])])
    assert _kinds(sigs) == ["season_reversal"]
    assert build_timeline_signals([_ch(1, ["winter 2003"]), _ch(2, ["spring 2003"])]) == []
    assert build_timeline_signals([_ch(1, ["autumn 2003"]), _ch(2, ["spring 2004"])]) == []


def test_forward_moving_timeline_has_no_candidates():
    rows = [_ch(1, ["March 3, 1998"], ["Mara was 16"]), _ch(2, ["spring 1999"], ["Mara is 17"]),
            _ch(3, ["2001-02-10"])]
    assert build_timeline_signals(rows) == []


# ── Timeline: flashback suppression ──────────────────────────────────────────

def test_flashback_cue_suppresses_the_reversal():
    rows = [_ch(1, ["March 3, 1998"]), _ch(2, ["Years earlier, June 1990"]), _ch(3, ["April 1998"])]
    assert build_timeline_signals(rows) == []


def test_story_intelligence_flash_chapters_suppress_the_reversal():
    rows = [_ch(1, ["1998"]), _ch(2, ["1990"])]
    assert _kinds(build_timeline_signals(rows)) == ["date_reversal"]
    assert build_timeline_signals(rows, flash_chapters={2}) == []


def test_flashback_chapter_does_not_become_the_new_baseline():
    # Ch2 is a flashback to 1990; ch3 (1997) must be compared with ch1 (1998), not ch2.
    rows = [_ch(1, ["1998"]), _ch(2, ["Long ago, 1990"]), _ch(3, ["1997"])]
    sigs = build_timeline_signals(rows)
    assert _kinds(sigs) == ["date_reversal"] and sigs[0]["chapters"] == [1, 3]


def test_planted_fixture_full_recall_and_zero_false_on_the_control():
    """DoD 5.14-T: 100% recall on the planted reversal, 0 candidates on the
    legitimate-flashback control."""
    planted = [_ch(1, ["May 2, 2010"]), _ch(2, ["May 9, 2010"]), _ch(3, ["April 20, 2010"])]
    control = [_ch(1, ["May 2, 2010"]), _ch(2, ["May 9, 2010"]),
               _ch(3, ["In a flashback: April 20, 2010"]), _ch(4, ["May 10, 2010"])]
    assert [s["chapters"] for s in build_timeline_signals(planted)] == [[2, 3]]
    assert build_timeline_signals(control) == []


# ── Timeline: ordering, cap, prompt, privacy ─────────────────────────────────

def test_ordering_is_stable_and_highest_confidence_first():
    rows = [_ch(1, ["1998"]), _ch(2, ["1995"]), _ch(3, ["Monday, March 3, 1999"])]
    sigs = build_timeline_signals(rows)
    assert _kinds(sigs)[0] == "weekday_mismatch"
    assert sigs == build_timeline_signals(list(reversed(rows)))    # input order does not matter


def test_budget_cap():
    rows = [_ch(n, [str(2100 - n)]) for n in range(1, 30)]          # every chapter goes backwards
    assert len(build_timeline_signals(rows)) == MAX_TIMELINE_SIGNALS


def test_prompt_block_asks_for_verification_and_is_empty_without_signals():
    assert format_timeline_signals_for_prompt([]) == ""
    block = format_timeline_signals_for_prompt(build_timeline_signals([_ch(1, ["1998"]), _ch(2, ["1995"])]))
    assert "VERIFY" in block and "flashback" in block and "chapters 1 and 2" in block


def test_no_manuscript_text_is_logged(caplog):
    secret = "the-hidden-ledger-under-the-floorboards"
    with caplog.at_level(logging.DEBUG):
        build_timeline_signals([_ch(1, ["1998", secret]), _ch(2, ["1995", secret])])
        build_narrative_signals([{"chapter": 1, "characters_present": [secret], "chapter_purpose": secret}])
        build_relationship_arcs([{"chapter": 1, "relationship_changes": [{"characters": ["a", "b"], "change": secret}]}],
                                {"a": "A", "b": "B"})
    assert secret not in caplog.text


# ── Narrative signals ────────────────────────────────────────────────────────

def _s(n, chars=(), purpose="Advances the plot"):
    return {"chapter": n, "characters_present": list(chars), "chapter_purpose": purpose}


def test_dead_end_thread_becomes_a_setup_signal():
    threads = [{"name": "The forged contract", "status": "dead_end", "introduced_chapter": 2, "last_seen_chapter": 4},
               {"name": "The open thread", "status": "open", "introduced_chapter": 1, "last_seen_chapter": 9}]
    sigs = build_narrative_signals([_s(n) for n in range(1, 11)], threads)
    assert [(s["kind"], s["subject"], s["chapters"]) for s in sigs] == [
        ("setup_without_payoff", "The forged contract", [2, 4])]
    assert sigs[0]["source"] == "narrative_threads"


def test_foreshadowing_hints_only_when_they_cite_a_real_chapter():
    hints = [{"hint": "A locked drawer", "chapter": 3}, {"hint": "No chapter"}, {"hint": "Bad chapter", "chapter": 99},
             "not-a-dict"]
    sigs = build_narrative_signals([_s(n) for n in range(1, 6)], [], hints)
    assert [(s["subject"], s["chapters"], s["source"]) for s in sigs] == [
        ("A locked drawer", [3], "foreshadowing_registry")]


def test_stale_registry_passed_as_none_adds_nothing():
    assert build_narrative_signals([_s(n) for n in range(1, 6)], [], None) == []


def test_character_disappearance_uses_the_dead_end_threshold():
    assert dead_end_threshold(10) == 3 and dead_end_threshold(40) == 6
    summaries = [_s(1, ["Tobias"]), _s(2, ["Tobias"])] + [_s(n) for n in range(3, 11)]
    sigs = build_narrative_signals(summaries)
    assert [(s["kind"], s["subject"], s["chapters"]) for s in sigs] == [
        ("character_disappearance", "Tobias", [1, 2])]
    # Appearing once is not a disappearance; a character still around near the end is not either.
    once = [_s(1, ["Ghost"])] + [_s(n) for n in range(2, 11)]
    late = [_s(1, ["Mara"]), _s(8, ["Mara"])] + [_s(n) for n in (2, 3, 4, 5, 6, 7, 9, 10)]
    assert build_narrative_signals(once) == [] and build_narrative_signals(late) == []


def test_purpose_gap_needs_two_consecutive_empty_chapters():
    summaries = [_s(1), _s(2, purpose=""), _s(3, purpose="n/a"), _s(4), _s(5, purpose="")]
    sigs = build_narrative_signals(summaries)
    assert [(s["kind"], s["chapters"]) for s in sigs] == [("purpose_gap", [2, 3])]


def test_empty_manuscript_and_cap():
    assert build_narrative_signals([]) == []
    threads = [{"name": f"Thread number {i}", "status": "dead_end", "introduced_chapter": 1, "last_seen_chapter": 2}
               for i in range(30)]
    assert len(build_narrative_signals([_s(n) for n in range(1, 11)], threads)) == MAX_SIGNALS


def test_narrative_prompt_block():
    assert format_signals_for_prompt([]) == ""
    block = format_signals_for_prompt(build_narrative_signals([_s(1, ["T"]), _s(2, ["T"])] + [_s(n) for n in range(3, 11)]))
    assert "VERIFY" in block and "[character_disappearance] T" in block


# ── Relationship arcs ────────────────────────────────────────────────────────

NAMES = {"a": "Mira", "b": "Vell", "c": "Oren"}


def _r(n, *changes):
    return {"chapter": n, "relationship_changes": [{"characters": list(p), "change": c} for p, c in changes]}


def test_arcs_aggregate_by_unordered_pair_in_chapter_order():
    arcs, dropped = build_relationship_arcs(
        [_r(3, (("b", "a"), "reconcile")), _r(1, (("a", "b"), "quarrel")), _r(2, (("a", "c"), "meet"))], NAMES)
    assert dropped == 0
    assert arcs[0]["characters"] == ["Mira", "Vell"]
    assert [c["chapter"] for c in arcs[0]["changes"]] == [1, 3]
    assert (arcs[0]["first_chapter"], arcs[0]["last_chapter"], arcs[0]["chapter_count"]) == (1, 3, 2)
    assert arcs[1]["characters"] == ["Mira", "Oren"]


def test_arcs_use_current_names_and_drop_unknown_ids():
    deleted = "0b8f6c1e-1111-4222-8333-944455556666"      # id-shaped, no longer a character
    arcs, dropped = build_relationship_arcs(
        [_r(1, (("a", deleted), "x"), (("a", "a"), "self"), (("a", "b"), "")), _r(2, (("a", "b"), "ally"))],
        {"a": "Mira Renamed", "b": "Vell"})
    assert [a["characters"] for a in arcs] == [["Mira Renamed", "Vell"]]
    assert dropped == 3


def test_arcs_keep_plain_names_the_summary_used():
    arcs, _ = build_relationship_arcs([_r(1, (("a", "Captain Hale"), "rivals"))], NAMES)
    assert arcs[0]["characters"] == ["Captain Hale", "Mira"]


def test_arcs_empty_input():
    assert build_relationship_arcs([], NAMES) == ([], 0)
    assert build_relationship_arcs([{"chapter": 1, "relationship_changes": None}], NAMES) == ([], 0)
