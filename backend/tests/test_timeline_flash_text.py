"""
Stage 12 Tranche 3 (A20, MV-5.14-A) — a flashback marked in the chapter's own
text is not a date reversal.

Live, the summariser kept chapter 3's date ("April 20, 2010") but dropped
"In a flashback to", so the planted-flashback story got a timeline finding in
3 of 3 runs (docs/testing/stage-12/tranche3/mv-5.14-a*.json). No model here.

    DATABASE_URL=...narratiq_test pytest backend/tests/test_timeline_flash_text.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.timeline_signals import build_timeline_signals, flash_cue_chapters  # noqa: E402

PLAIN = "<p>On April 20, 2010, Clara signed the lease with the landlord.</p>"
FLASH = "<p>In a flashback to April 20, 2010, Clara signed the lease with the landlord.</p>"
SUMMARIES = [{"chapter_number": n, "timeline_markers": [d], "key_events": []}
             for n, d in ((1, "May 2, 2010"), (2, "May 9, 2010"), (3, "April 20, 2010"), (4, "May 10, 2010"))]


def _reversals(flash):
    return [s for s in build_timeline_signals(SUMMARIES, flash) if s["kind"] == "date_reversal"]


def test_flashback_sentence_with_a_date_marks_the_chapter():
    assert flash_cue_chapters([(1, "<p>On May 2, 2010, Clara opened.</p>"), (3, FLASH)]) == {3}


def test_plain_dated_chapter_is_not_a_flashback():
    assert flash_cue_chapters([(3, PLAIN)]) == set()


def test_cue_in_another_sentence_does_not_hide_a_reversal():
    text = "<p>She remembered her mother's bakery.</p><p>On April 20, 2010, Clara signed the lease.</p>"
    assert flash_cue_chapters([(3, text)]) == set()


def test_year_anchor_and_markup_inside_the_sentence():
    text = "<p><em>Years earlier</em>, in <strong>1998</strong>, the lighthouse was sold.</p>"
    assert flash_cue_chapters([(5, text)]) == {5}


def test_flash_forward_counts():
    assert flash_cue_chapters([(2, "<p>Years later, on June 1, 2031, Ada returned.</p>")]) == {2}


def test_missing_or_empty_content_is_ignored():
    assert flash_cue_chapters([(1, None), (2, ""), (None, FLASH)]) == set()


def test_mv514a_story_b_flashback_is_suppressed_and_story_a_still_reported():
    flash = flash_cue_chapters([(1, "<p>May 2, 2010</p>"), (2, "<p>May 9, 2010</p>"), (3, FLASH),
                                (4, "<p>On May 10, 2010, they reopened.</p>")])
    assert flash == {3}
    assert not any(3 in s["chapters"] for s in _reversals(flash))
    plain = flash_cue_chapters([(3, PLAIN)])
    assert any(s["chapters"] == [2, 3] for s in _reversals(plain))
