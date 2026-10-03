"""
Stage 12 Tranche 3 (A19) — the A18 offline replay as a pass/fail regression test.

`replay_output_checks_t2b.py` measured the output checks once against stored
REAL model outputs and wrote a report; nothing failed if a later change to
`prompt_safety` started refusing clean prose or stopped catching an obeyed
answer. This test replays the same committed evidence on every run, no model:

  * clean prose (Q&A, plot suggestions, writing suggestions, continuation),
    before and after A18, plus any Tranche 3 re-run   -> 0 flagged
  * legitimate selection rewrites (Stage 11 guard-on, Tranche 2b, Tranche 3)
                                                      -> 0 flagged by either check
  * Plot Assistant answers that obeyed the planted instruction before the
    Stage 11 fence                                    -> every one flagged
  * the same feature after the fence                  -> 0 flagged

The thresholds are the A18 acceptance figures; they are not tuned here.

    DATABASE_URL=...narratiq_test pytest backend/tests/test_output_checks_replay.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))
sys.path.insert(0, str(_BACKEND / "tests"))
sys.path.insert(0, str(_BACKEND / "scripts" / "security"))
sys.path.insert(0, str(_BACKEND / "scripts" / "perf"))

import pytest  # noqa: E402

from services.prompt_safety import output_obeyed_material, rewrite_lost_source  # noqa: E402

_TESTING = _BACKEND.parent / "docs" / "testing"
_CLEAN = sorted([_TESTING / "stage-12" / "clean-prose-probe-before-a18.json",
                 _TESTING / "stage-12" / "clean-prose-probe-after-a18.json",
                 *(_TESTING / "stage-12" / "tranche3").glob("clean-prose-probe-*.json")])
_LEGIT = sorted([_TESTING / "stage-11" / "legit-rewrite-probe-guard-on.json",
                 _TESTING / "stage-12" / "legit-rewrite-probe-tranche2b.json",
                 *(_TESTING / "stage-12" / "tranche3").glob("legit-rewrite-probe-*.json")])


def _clean_items():
    from replay_output_checks_t2b import items
    out = []
    for path in _CLEAN:
        for row in json.loads(path.read_text())["rows"]:
            if row["status"] != 200:
                continue
            for label, text in items(row["feature"], row["body"]):
                if text:
                    out.append((f"{path.name}:{row['passage']}:{row['feature']}:{label}", row["source"], text))
    return out


def _legit_rows():
    from legit_rewrite_probe import PASSAGES
    out = []
    for path in _LEGIT:
        for row in json.loads(path.read_text())["rows"]:
            if row.get("status") == 200 and row.get("output"):
                out.append((f"{path.name}:{row['passage']}:{row['tool']}", PASSAGES[row["passage"]],
                            row["output"], row["tool"]))
    return out


def _plot_assistant_answers(filename: str) -> tuple[str, list[str]]:
    from prompt_injection_probe import CHAPTERS
    source = " ".join(c.replace("<p>", " ").replace("</p>", " ") for c in CHAPTERS)
    answers = []
    for s in json.loads((_TESTING / "stage-11" / filename).read_text())["features"]["plot-assistant"]["samples"]:
        try:
            answers.append(json.loads(s["output"]).get("answer") or "")
        except json.JSONDecodeError:        # stored samples are cut at 1500 characters
            txt = s["output"]
            i = txt.find('"answer":"')
            answers.append(json.loads('"' + txt[i + 10:].split('","suggestions"')[0] + '"') if i >= 0 else "")
    return source, answers


def test_corpora_are_present_and_non_trivial():
    clean, legit = _clean_items(), _legit_rows()
    # A18 measured 203 clean outputs and 84 rewrites per legit file; fewer means
    # the evidence files changed shape and the replay silently tests nothing.
    assert len(clean) >= 203, len(clean)
    assert len(legit) >= 2 * 84, len(legit)


def test_clean_prose_is_never_flagged():
    flagged = [(label, text[:200]) for label, src, text in _clean_items() if output_obeyed_material(src, text)]
    assert flagged == []


def test_legitimate_rewrites_trip_neither_check():
    obeyed = [label for label, src, out, _ in _legit_rows() if output_obeyed_material(src, out)]
    lost = [label for label, src, out, tool in _legit_rows()
            if rewrite_lost_source(src, out, same_language=tool != "translate")]
    assert obeyed == [] and lost == []


@pytest.mark.parametrize("filename,expect_all_flagged", [
    ("injection-probe-before-fix.json", True),
    ("injection-probe-after-fix.json", False),
])
def test_plot_assistant_obeyed_signature(filename, expect_all_flagged):
    source, answers = _plot_assistant_answers(filename)
    assert answers, filename
    flags = [output_obeyed_material(source, a) for a in answers]
    if expect_all_flagged:
        assert all(flags), flags
    else:
        assert not any(flags), flags
