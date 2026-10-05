"""
Stage 12.2 — datamarking for story Q&A (prompt_safety Layer 1b).

Chapter-scoped story Q&A (the Plot Assistant's default request, every voice
story question) followed an instruction planted in the open chapter: voice
12/12, Plot Assistant 9/12. The fix marks the fenced Q&A material in the PROMPT
COPY (every 4th gap; the open chapter's excerpt at every gap). These tests check
exactly what would be sent to vLLM — no model. Live measurements:
docs/testing/stage-12/stage-12.2/injection-coverage.md.

    DATABASE_URL=...narratiq_test pytest backend/tests/test_qa_datamark.py -q
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402

from config import settings  # noqa: E402
from services import ai_service  # noqa: E402
from services.prompt_safety import (  # noqa: E402
    DATAMARK, _DATAMARK_RULE, _SYSTEM_RULE, datamark, dense_span, harden, strip_datamarks,
)
from test_prompt_safety import PASSAGE, _Capture  # noqa: E402

QUESTION = "What happens in the lighthouse?"
CHUNKS = [{"chapter": 1, "score": 0.9, "word_count": 60, "text": PASSAGE}]
CHAPTER_HTML = f"<p>{PASSAGE}</p>"
SENTINELS = ("\x1e", "\x1f")


def _gaps(line: str) -> int:
    return len(re.findall(r"[ \t]+|" + DATAMARK, line))


# ── datamark() / dense_span() ─────────────────────────────────────────────────

def test_every_fourth_gap_is_marked_per_line_and_newlines_survive():
    out = datamark("one two three four five six seven eight nine\nten eleven twelve thirteen fourteen")
    first, second = out.split("\n")
    assert first == f"one two three four{DATAMARK}five six seven eight{DATAMARK}nine"
    assert second == f"ten eleven twelve thirteen{DATAMARK}fourteen"      # counting restarts per line


def test_an_authors_own_marker_character_cannot_pose_as_a_mark():
    assert datamark(f"a{DATAMARK}b") == "a^b"


def test_dense_span_is_marked_at_every_gap_and_its_delimiters_never_survive():
    out = datamark("a b c d e f\n" + dense_span("one two three four five") + "\nx y z")
    assert f"one{DATAMARK}two{DATAMARK}three{DATAMARK}four{DATAMARK}five" in out
    assert not any(s in out for s in SENTINELS)
    assert dense_span("") == "" and not any(s in dense_span("a\x1eb\x1fc")[1:-1] for s in SENTINELS)


def test_strip_datamarks_returns_normal_text():
    assert strip_datamarks(f"Devika{DATAMARK}climbs  the stairs.") == "Devika climbs the stairs."
    assert strip_datamarks("plain answer") == "plain answer"


def test_harden_without_mark_is_unchanged():
    system, user = harden("SYS", "a b c d e f g h", task="TASK")
    assert DATAMARK not in user and system.endswith(_SYSTEM_RULE.format(nid=re.search(r"AUTHOR_MATERIAL (\w{8})", user).group(1)))


# ── answer_story_question: what reaches vLLM ──────────────────────────────────

async def _qa_messages(monkeypatch, *, guard=True, mark=True, current_chapter=CHAPTER_HTML):
    cap = _Capture()
    monkeypatch.setattr(ai_service, "get_vllm_client", cap)
    monkeypatch.setattr(settings, "prompt_injection_guard", guard)
    monkeypatch.setattr(settings, "prompt_injection_datamark_qa", mark)
    await ai_service.answer_story_question(QUESTION, CHUNKS, current_chapter=current_chapter, scope_limited=True)
    return cap.messages[0]["content"], cap.messages[1]["content"]


@pytest.mark.asyncio
async def test_qa_material_is_marked_and_the_question_is_not(monkeypatch):
    system, user = await _qa_messages(monkeypatch)
    nid = re.search(r"<<<AUTHOR_MATERIAL (\w{8})>>>", user).group(1)
    material, after = user.split(f"<<<END_AUTHOR_MATERIAL {nid}>>>")
    assert system.endswith(_DATAMARK_RULE.format(nid=nid))
    assert DATAMARK in material and DATAMARK not in after
    assert QUESTION in after                                   # the question stays last and unmarked
    assert not any(s in user for s in SENTINELS)


@pytest.mark.asyncio
async def test_the_open_chapter_excerpt_is_marked_at_every_gap(monkeypatch):
    _system, user = await _qa_messages(monkeypatch)
    excerpt = user.split("Current chapter (last 600")[1].split("\n", 1)[1].split("\n<<<END_AUTHOR_MATERIAL")[0]
    assert " " not in excerpt and excerpt.count(DATAMARK) == _gaps(CHAPTER_HTML)


@pytest.mark.asyncio
async def test_switch_off_restores_the_stage11_qa_prompt(monkeypatch):
    system, user = await _qa_messages(monkeypatch, mark=False)
    nid = re.search(r"<<<AUTHOR_MATERIAL (\w{8})>>>", user).group(1)
    assert DATAMARK not in user and system.endswith(_SYSTEM_RULE.format(nid=nid))
    assert f"Current chapter (last 600 chars):\n{CHAPTER_HTML}" in user
    assert not any(s in user for s in SENTINELS)


@pytest.mark.asyncio
async def test_guard_off_sends_no_marks_and_no_delimiters(monkeypatch):
    _system, user = await _qa_messages(monkeypatch, guard=False)
    assert user.startswith(f"Question: {QUESTION}\n\n")
    assert DATAMARK not in user and not any(s in user for s in SENTINELS)


@pytest.mark.asyncio
async def test_other_model_calls_are_never_marked(monkeypatch):
    cap = _Capture()
    monkeypatch.setattr(ai_service, "get_vllm_client", cap)
    monkeypatch.setattr(settings, "prompt_injection_guard", True)
    monkeypatch.setattr(settings, "prompt_injection_datamark_qa", True)
    await ai_service._complete("SYSTEM TASK", PASSAGE)            # e.g. a rewrite
    assert PASSAGE in cap.messages[1]["content"] and DATAMARK not in cap.messages[1]["content"]


@pytest.mark.asyncio
async def test_a_marker_echoed_by_the_model_never_reaches_the_author(monkeypatch):
    class _Echo(_Capture):
        def __call__(self):
            client = super().__call__()
            create = client.chat.completions.create

            async def echo(**kw):
                resp = await create(**kw)
                resp.choices[0].message.content = f"Devika{DATAMARK}finds the lamp room empty."
                return resp
            client.chat.completions.create = echo
            return client
    monkeypatch.setattr(ai_service, "get_vllm_client", _Echo())
    monkeypatch.setattr(settings, "prompt_injection_guard", True)
    monkeypatch.setattr(settings, "prompt_injection_datamark_qa", True)
    answer = await ai_service.answer_story_question(QUESTION, CHUNKS)
    assert answer == "Devika finds the lamp room empty."


def test_the_window_fit_measures_the_marked_prompt(monkeypatch):
    long_user = ("Devika climbed the lighthouse stairs while the storm battered the glass. " * 200)
    monkeypatch.setattr(settings, "prompt_injection_guard", True)
    monkeypatch.setattr(settings, "prompt_injection_datamark_qa", False)
    plain = ai_service._qa_prompt_tokens("SYS", long_user, QUESTION)
    monkeypatch.setattr(settings, "prompt_injection_datamark_qa", True)
    marked = ai_service._qa_prompt_tokens("SYS", long_user, QUESTION)
    assert marked > plain * 1.1     # the budget sees the real (marked) size, so it can never overflow
