"""
Stage 12 Tranche 2a — A13 Plot Assistant retrieval (PA-C6, PA-H12, PA-C9, PA-H11).

Deterministic (no model, no embeddings) — the ranking rules are pure functions
over stub rows; the router tests stub every model call:
  * importance only breaks NEAR-ties: a cosine gap >= epsilon is never
    overturned; equal-cosine candidates order by chapter event count;
  * the per-chapter quota spreads evidence only when another chapter offers a
    near-equal passage, and never starves a single-chapter answer;
  * character mentions are sampled across the whole book, not chapters 1–5;
  * the question → character detector handles titles, aliases, possessives,
    multi-part names and Unicode without substring errors;
  * the Q&A prompt is measured with the real tokenizer and always fits;
  * a planted future-chapter secret never reaches a chapter-scoped Q&A or
    creative prompt, while full scope still sees it.

    DATABASE_URL=...narratiq_test pytest backend/tests/test_plot_assistant_retrieval_t2a.py -q
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402

from services import ai_service as ai  # noqa: E402


def row(ch, score, i=0, text=None):
    return NS(chapter_number=ch, score=score, chunk_index=i, chunk_id=f"{ch}-{i}",
              text=text or f"passage {ch}-{i} unique words {ch*100+i}", word_count=50)


# ── PA-C6 / PA-H12: near-tie importance ──────────────────────────────────────

def test_near_tie_is_broken_toward_the_eventful_chapter():
    rows = [row(1, 0.700), row(2, 0.695)]
    out = ai._rerank_near_ties(rows, {1: 0.0, 2: 3.0})
    assert [r.chapter_number for r in out] == [2, 1]


def test_a_clear_semantic_gap_is_never_overturned():
    rows = [row(1, 0.720), row(2, 0.700)]              # gap 0.02 == epsilon
    out = ai._rerank_near_ties(rows, {1: 0.0, 2: 99.0})
    assert [r.chapter_number for r in out] == [1, 2]
    rows = [row(1, 0.80), row(2, 0.50)]
    assert [r.chapter_number for r in ai._rerank_near_ties(rows, {1: 0.0, 2: 99.0})] == [1, 2]


def test_equal_cosine_orders_strictly_by_event_count_and_is_stable():
    import math
    raw = {5: math.log1p(5), 8: math.log1p(8), 12: math.log1p(12)}
    rows = [row(5, 0.6), row(12, 0.6), row(8, 0.6)]
    out = [r.chapter_number for r in ai._rerank_near_ties(rows, raw)]
    assert out == [12, 8, 5]
    assert out == [r.chapter_number for r in ai._rerank_near_ties(list(reversed(rows)), raw)]


def test_old_cap_saturation_no_longer_ties_busy_chapters():
    # Under the old boost, 6, 9 and 14 events all hit the 0.08 cap and tied.
    import math
    raw = {c: math.log1p(c) for c in (6, 9, 14)}
    pct = ai._importance_percentiles(raw)
    assert pct[6] < pct[9] < pct[14]


def test_unsummarised_chapters_get_no_boost_and_single_chapter_is_neutral():
    assert ai._importance_percentiles({}) == {}
    assert ai._importance_percentiles({3: 2.0}) == {3: 0.0}


# ── PA-H11: chapter quota and mention sampling ───────────────────────────────

def test_quota_spreads_when_other_chapters_are_near_equal():
    ranked = [row(1, 0.80, 0), row(1, 0.79, 1), row(1, 0.78, 2), row(1, 0.77, 3),
              row(7, 0.76, 0), row(9, 0.75, 0)]
    out = ai._select_with_chapter_quota(ranked, 6)          # quota = 2
    chapters = [r.chapter_number for r in out]
    assert chapters.count(1) <= 4 and 7 in chapters and 9 in chapters
    assert chapters[:2] == [1, 1]


def test_quota_never_starves_a_single_chapter_answer():
    ranked = [row(1, 0.9 - i * 0.01, i) for i in range(6)] + [row(4, 0.30)]
    out = ai._select_with_chapter_quota(ranked, 6)
    assert [r.chapter_number for r in out] == [1] * 6        # chapter 4 is far worse


def test_mentions_are_sampled_across_the_whole_book():
    mentions = [NS(chapter_number=c, mention_id=f"{c}-{j}") for c in range(1, 41) for j in range(3)]
    picked = ai._sample_mentions_evenly(mentions)
    chs = [m.chapter_number for m in picked]
    assert len(picked) == 10 and chs[0] == 1 and chs[-1] == 40
    assert max(chs) > 30 and chs == sorted(chs)


def test_short_books_still_get_two_mentions_per_chapter():
    mentions = [NS(chapter_number=c, mention_id=f"{c}-{j}") for c in (1, 2, 3) for j in range(4)]
    picked = ai._sample_mentions_evenly(mentions)
    assert [m.chapter_number for m in picked] == [1, 1, 2, 2, 3, 3]


# ── PA-C9: question → characters ─────────────────────────────────────────────

class Ch:
    def __init__(self, name, aliases=()):
        self.name, self.aliases = name, list(aliases)


CAST = [Ch("Mara Halloran"), Ch("Ash"), Ch("Will Turner"), Ch("Vell", ["the Magistrate"]), Ch("Éléonore Vasse")]


@pytest.mark.parametrize("q,expected", [
    ("What does Captain Mara want?", ["Mara Halloran"]),          # title + first name
    ("Where is Halloran's ship?", ["Mara Halloran"]),             # possessive, surname
    ("Tell me about mara halloran", ["Mara Halloran"]),           # full name, lower case
    ("Is the Magistrate’s story true?", ["Vell"]),                # alias, curly possessive
    ("Who is éléonore?", ["Éléonore Vasse"]),                     # Unicode
    ("What did Ash say?", ["Ash"]),
    ("What does Will want?", ["Will Turner"]),                    # everyday word, capitalised
])
def test_detector_finds_named_characters(q, expected):
    from services.character_names import detect_named_characters
    assert [c.name for c in detect_named_characters(q, CAST)] == expected


@pytest.mark.parametrize("q", [
    "Who scattered the ashes?",             # Ash ≠ ashes; "the" never identifies anyone
    "What will happen next?",               # everyday word, not capitalised
    "What happened at the harbour?",
    "",
])
def test_detector_avoids_substring_and_function_word_errors(q):
    from services.character_names import detect_named_characters
    assert detect_named_characters(q, CAST) == []


# ── Real-tokenizer budget ────────────────────────────────────────────────────

def test_qa_prompt_always_fits_the_model_window(monkeypatch):
    from config import settings
    sent = {}

    async def fake_complete(system, user, **kw):
        sent["system"], sent["user"], sent["task"] = system, user, kw.get("task")
        return "ok"

    monkeypatch.setattr(ai, "_complete", fake_complete)
    big = "word " * 900
    chunks = [{"chapter": i, "chunk_index": 0, "text": big, "word_count": 900, "score": 0.5} for i in range(12)]
    intel = {"story_premise": "p " * 400, "memory_hits": [{"content": "m " * 300}] * 6}
    asyncio.run(ai.answer_story_question("What happens?", chunks, character_context=["c " * 800],
                                         note_context=["n " * 200], current_chapter="x" * 600,
                                         intel_context=intel))
    used = ai._qa_prompt_tokens(sent["system"], sent["user"], "What happens?")
    assert used <= settings.max_model_len - ai._QA_COMPLETION_TOKENS - ai._QA_SAFETY_MARGIN
    assert "Passage 1 " in sent["user"]                     # the best passage always survives


def test_intel_block_is_capped():
    intel = {"memory_hits": [{"content": "fact " * 200} for _ in range(6)]}
    block = ai._trim_to_tokens(ai.format_intel_context(intel), ai._INTEL_CONTEXT_TOKEN_CAP)
    assert ai.count_tokens(block) <= ai._INTEL_CONTEXT_TOKEN_CAP


# ── D-1: a planted future-chapter secret, end to end through the router ──────

SECRET = "PLANTED-SECRET the magistrate faked his death"


@pytest.mark.parametrize("intent", ["qa", "creative", "mixed"])
@pytest.mark.parametrize("scope,cap,leaks", [("chapter", 2, False), ("chapter", 3, False), ("full", None, True)])
def test_planted_future_secret_never_reaches_a_chapter_scoped_prompt(intent, scope, cap, leaks, monkeypatch):
    from _phase3_helpers import two_authors
    from middleware.rate_limit import limiter
    from models import Chapter, StoryDNA, StoryMemoryEntry
    from routers import plot_assistant as pa
    from services import story_intel_service as sis

    monkeypatch.setattr(limiter, "enabled", False)
    vec = [1.0] + [0.0] * 1023

    async def fake_embed(_t):
        return vec

    monkeypatch.setattr(sis, "embed_text", fake_embed)
    monkeypatch.setattr(sis, "embed_text_sync", lambda _t: vec)
    prompts: list[str] = []

    async def capture(system, user, **kw):
        prompts.append(system + "\n" + user)
        if "suggest" in system.lower() or "idea" in system.lower():
            return '[{"id": 1, "text": "An idea.", "rationale": "Because."}]'
        return "An answer."

    async def fake_intent(_q):
        return intent

    async def no_chunks(*_a, **_k):
        return []

    monkeypatch.setattr(ai, "_complete", capture)
    monkeypatch.setattr(pa, "detect_query_intent", fake_intent)
    for name in ("retrieve_relevant_chunks", "retrieve_chunks_from_store", "retrieve_character_context",
                 "retrieve_note_context"):
        monkeypatch.setattr(pa, name, no_chunks)

    async def fake_struct(system, user, **kw):
        prompts.append(system + "\n" + user)
        return [{"id": 1, "text": "An idea.", "rationale": "Because."}], {}

    monkeypatch.setattr(ai, "complete_structured", fake_struct)

    with two_authors() as (db, a, _b, client):
        try:
            # Chapter 4 reveals the secret; analysis ran over chapters 1-4.
            db.add(Chapter(story_id=a.sid, chapter_number=4, title="Four", content="<p>He lives.</p>"))
            db.add(StoryDNA(story_id=a.sid, premise=SECRET))
            db.commit()
            db.refresh(a.story)
            asyncio.run(sis.run_p25_memory_consolidation(db, a.story))
            db.commit()
            body = {"story_id": a.sid, "question": "What is Vell hiding?", "scope": scope}
            if cap is not None:
                body["current_chapter_number"] = cap
            r = client.post("/api/plot-assistant/", headers=a.headers, json=body)
            assert r.status_code == 200, r.text[:300]
            assert prompts, "no model call captured"
            assert any(SECRET in p for p in prompts) is leaks
        finally:
            db.rollback()
            db.query(StoryMemoryEntry).filter(StoryMemoryEntry.story_id == a.sid).delete()
            db.query(StoryDNA).filter(StoryDNA.story_id == a.sid).delete()
            db.commit()
