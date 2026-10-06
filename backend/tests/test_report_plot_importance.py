"""
Stage 12.3 — found in the owner-authorised agent review (HR-09, 2026-10-06):
"Where the plot moves most" showed every chapter as 0 on a realistic 40-chapter
story. The display reused the retrieval boost, which is capped and saturates on
any chapter with 6+ events, so min == max and every normalised score was 0.
The report now ranks on the uncapped score, and omits the section when there is
genuinely no variation; retrieval keeps its bounded boost. No model, no DB.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import ai_service  # noqa: E402


class _Q:
    def __init__(self, rows): self.rows = rows
    def filter(self, *a, **k): return self
    def all(self): return self.rows


class _DB:
    def __init__(self, rows): self.rows = rows
    def query(self, *a, **k): return _Q(self.rows)


ROWS = [  # (chapter, key_events, arc_notes, relationship_changes)
    (1, ["e"] * 6, {"Wren": "x"}, []),
    (2, ["e"] * 8, {"Wren": "x"}, [{"characters": ["A", "B"], "change": "y"}]),
    (3, ["e"] * 12, {"Wren": "x"}, [{"characters": ["A", "B"], "change": "y"}]),
]


def test_capped_scores_saturate_which_is_why_display_must_not_use_them():
    capped = ai_service._plot_importance_by_chapter("s", {1, 2, 3}, _DB(ROWS))
    assert len(set(capped.values())) == 1                      # all at the retrieval cap
    assert max(capped.values()) <= ai_service._PLOT_IMPORTANCE_CAP


def test_uncapped_scores_rank_the_busier_chapter_higher():
    raw = ai_service._plot_importance_by_chapter("s", {1, 2, 3}, _DB(ROWS), cap=False)
    assert raw[3] > raw[2] > raw[1]


def test_the_report_shows_a_ranking_and_omits_it_when_there_is_no_variation(monkeypatch):
    import asyncio

    async def fake_strategy(chapters):
        return {"character_arcs": [], "pacing": {"slow_chapters": [], "intense_chapters": [], "assessment": ""},
                "unresolved_threads": [], "strengths": [], "improvements": [], "note": "", "mode_note": "",
                "chapters_analyzed": len(chapters), "word_count_total": 0}

    monkeypatch.setitem(ai_service._MANUSCRIPT_STRATEGIES, "summary_pass", fake_strategy)
    chapters = [{"chapter": n} for n in (1, 2, 3)]

    class _Thread(_Q):
        pass

    class DB(_DB):
        def query(self, *a, **k):
            first = str(a[0]) if a else ""
            return _Q([]) if "NarrativeThread" in first or "name" in first else _Q(self.rows)

    r = asyncio.run(ai_service.analyze_manuscript("s", chapters, db=DB(ROWS)))
    imp = r["chapter_plot_importance"]
    assert imp["3"] == 100.0 and imp["1"] == 0.0 and 0 < imp["2"] < 100

    flat = [(n, ["e"] * 6, {"W": "x"}, []) for n in (1, 2, 3)]
    r = asyncio.run(ai_service.analyze_manuscript("s", chapters, db=DB(flat)))
    assert r["chapter_plot_importance"] == {}
