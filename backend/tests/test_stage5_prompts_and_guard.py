"""
Stage 5 — prompt v3 (review H1), the continuity prompt in the registry
(5.14), the style near-no-op guard (D4, review M1), guided JSON in
complete_structured (D3), the plot-hole / thread-extraction budgets, and the
emotion measurement harness logic (5.8). No database, no model: every model
call is a deterministic fake.

    pytest backend/tests/test_stage5_prompts_and_guard.py -q
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402

from config import Settings, settings  # noqa: E402
from services import ai_service  # noqa: E402
from services.prompt_registry import PROMPT_REGISTRY, resolve_prompt_version  # noqa: E402

PASSAGE = ("Elara walked down the long corridor. She was tired, and she looked at every door. "
           "Kira waited by the window and said nothing. They had come too far to turn back.")
REWRITE = ("Elara stalked the corridor. Every door a threat. Kira at the window, silent, watching. "
           "No way back now. Not after this.")


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ── H1: v3 carries every v2 transform ────────────────────────────────────────

def test_v3_defines_every_v2_transform_type():
    assert set(PROMPT_REGISTRY["v2"]) <= set(PROMPT_REGISTRY["v3"])


@pytest.mark.parametrize("transform", sorted(PROMPT_REGISTRY["v2"]))
def test_every_v2_key_resolves_under_v3_without_fallback(transform, caplog):
    builder, resolved = resolve_prompt_version(transform, "v3", "v2")
    assert resolved == "v3"
    assert "unresolvable" not in caplog.text
    if transform not in ("style", "continuity"):
        assert builder is PROMPT_REGISTRY["v2"][transform], f"{transform} must reuse its v2 builder"


def test_config_defaults_are_v3_with_v2_fallback():
    fields = Settings.model_fields
    assert fields["prompt_version"].default == "v3"
    assert fields["prompt_version_fallback"].default == "v2"


def test_unknown_version_falls_back_to_v2_not_v1():
    builder, resolved = resolve_prompt_version("tone", "v999", settings.prompt_version_fallback)
    assert resolved == "v2" and builder is PROMPT_REGISTRY["v2"]["tone"]


# ── D4: style v3 ─────────────────────────────────────────────────────────────

def test_style_v3_names_thriller_craft_levers_and_drops_the_v2_brakes():
    s = PROMPT_REGISTRY["v3"]["style"]("Thriller", "")
    assert "punchy" in s and "tension" in s and "noticeable" in s
    assert "Avoid leaning on surface-level genre tropes" not in s
    assert "Return ONLY the rewritten passage" in s


def test_style_v3_keeps_preservation_and_strength_clauses_and_genre():
    s = PROMPT_REGISTRY["v3"]["style"]("noir", "GENRE: crime", preservation_clause="PRESERVE-X",
                                       strength_clause="STRENGTH-Y")
    assert s.startswith("GENRE: crime") and "PRESERVE-X" in s and "STRENGTH-Y" in s


def test_style_v3_unknown_target_is_the_v2_prompt():
    assert PROMPT_REGISTRY["v3"]["style"]("Hemingway", "") == PROMPT_REGISTRY["v2"]["style"]("Hemingway", "")


# ── 5.14: continuity prompt in the registry ──────────────────────────────────

def test_continuity_is_not_in_v1_and_v2_is_the_pre_registry_prompt():
    assert "continuity" not in PROMPT_REGISTRY["v1"]
    system, instructions = PROMPT_REGISTRY["v2"]["continuity"]()
    assert system.startswith("You are a continuity editor reviewing a manuscript")
    assert instructions.endswith("Return ONLY the JSON array.")


def test_continuity_v3_without_signals_equals_v2_and_with_signals_asks_to_verify():
    assert PROMPT_REGISTRY["v3"]["continuity"](signals_block="") == PROMPT_REGISTRY["v2"]["continuity"]()
    system, instructions = PROMPT_REGISTRY["v3"]["continuity"](signals_block="SIGNALS-BLOCK")
    assert instructions.startswith("SIGNALS-BLOCK") and "hints, not findings" in system


def test_check_continuity_sends_the_signals_block(monkeypatch):
    seen = {}

    async def fake_structured(system, user, **kw):
        seen["system"], seen["user"] = system, user
        return [], ai_service.DegradedMeta(False, None, 1, 0)

    monkeypatch.setattr(ai_service, "complete_structured", fake_structured)
    monkeypatch.setattr(settings, "prompt_version", "v3")
    run(ai_service.check_continuity([], [{"chapter_number": 1}], [], [], signals_block="Timeline signals: X"))
    assert "Timeline signals: X" in seen["user"]
    monkeypatch.setattr(settings, "prompt_version", "v2")          # rollback by config
    run(ai_service.check_continuity([], [{"chapter_number": 1}], [], [], signals_block="Timeline signals: X"))
    assert "Timeline signals: X" not in seen["user"]


# ── D4 / M1: the style near-no-op guard ──────────────────────────────────────

class Fake:
    def __init__(self, *outputs):
        self.outputs, self.calls = list(outputs), []

    async def __call__(self, system, user, temperature=0.0, max_tokens=512, **_kw):
        self.calls.append(system)
        return self.outputs[min(len(self.calls) - 1, len(self.outputs) - 1)]


def _patch(monkeypatch, fake, needs_change=True):
    monkeypatch.setattr(ai_service, "_complete", fake)
    checks = []

    async def assess(text, target, transform_type):
        checks.append(target)
        return needs_change, "Already suitable."
    monkeypatch.setattr(ai_service, "_assess_change_needed", assess)
    return checks


def test_is_near_noop_scales_with_the_unlocked_share():
    assert ai_service._is_near_noop(PASSAGE, PASSAGE, None)
    assert not ai_service._is_near_noop(PASSAGE, REWRITE, None)
    # A small edit confined to the only unlocked sentence is a real change there.
    locked = [{"start": 0, "end": PASSAGE.index("They had")}]
    last = PASSAGE[:PASSAGE.index("They had")] + "No way back now."
    assert not ai_service._is_near_noop(PASSAGE, last, locked)
    assert not ai_service._is_near_noop(PASSAGE, PASSAGE, [{"start": 0, "end": len(PASSAGE)}])  # all locked


def test_guard_retries_once_then_reports_no_change_honestly(monkeypatch):
    fake = Fake(PASSAGE, PASSAGE)
    _patch(monkeypatch, fake)
    r = run(ai_service.transform_style(PASSAGE, "Thriller", strength="strong"))
    assert len(fake.calls) == 2, "exactly one retry"
    assert "nearly identical" in fake.calls[1]
    assert r["no_change"] is True and r["transformed"] == PASSAGE
    assert r["reason"] == ai_service._NEAR_NOOP_REASON and r["failed"] is False


def test_guard_returns_the_retry_when_it_changes_the_text(monkeypatch):
    fake = Fake(PASSAGE, REWRITE)
    _patch(monkeypatch, fake)
    r = run(ai_service.transform_style(PASSAGE, "Thriller", strength="moderate"))
    assert len(fake.calls) == 2 and r["no_change"] is False and r["transformed"] == REWRITE


def test_guard_does_not_fire_on_a_real_rewrite_or_at_light(monkeypatch):
    fake = Fake(REWRITE)
    _patch(monkeypatch, fake)
    assert run(ai_service.transform_style(PASSAGE, "Thriller", strength="strong"))["transformed"] == REWRITE
    assert len(fake.calls) == 1
    fake2 = Fake(PASSAGE)
    _patch(monkeypatch, fake2)
    r = run(ai_service.transform_style(PASSAGE, "Thriller", strength="light"))
    assert len(fake2.calls) == 1 and r["no_change"] is False


def test_guard_is_style_only(monkeypatch):
    fake = Fake(PASSAGE)
    _patch(monkeypatch, fake)
    r = run(ai_service.transform_tone(PASSAGE, "dark", strength="strong"))
    assert len(fake.calls) == 1 and r["no_change"] is False
    assert ai_service._NEAR_NOOP_GUARD_TRANSFORMS == frozenset({"style"})


def test_guard_keeps_locked_spans_byte_identical_on_the_retry(monkeypatch):
    cut = PASSAGE.index("Kira")
    locked = [{"start": 0, "end": cut}]
    first = f"[KEEP]{PASSAGE[:cut]}[/KEEP][REWRITE]{PASSAGE[cut:]}[/REWRITE]"
    second = f"[KEEP]{PASSAGE[:cut]}[/KEEP][REWRITE]Kira, at the glass. Silent. No way back.[/REWRITE]"
    fake = Fake(first, second)
    _patch(monkeypatch, fake)
    r = run(ai_service.transform_style(PASSAGE, "Thriller", strength="strong", locked_ranges=locked))
    assert len(fake.calls) == 2
    assert r["transformed"].startswith(PASSAGE[:cut]) and r["transformed"].endswith("No way back.")


def test_strong_style_skips_the_already_suitable_shortcut(monkeypatch):
    fake = Fake(REWRITE)
    checks = _patch(monkeypatch, fake, needs_change=False)
    r = run(ai_service.transform_style(PASSAGE, "Thriller", strength="strong"))
    assert checks == [] and r["transformed"] == REWRITE
    r2 = run(ai_service.transform_style(PASSAGE, "Thriller", strength="moderate"))
    assert checks == ["already written in the style of Thriller"] and r2["no_change"] is True


# ── D3: guided JSON in complete_structured ───────────────────────────────────

def _coerce(parsed):
    return (parsed, 0) if isinstance(parsed, dict) else (None, 0)


def test_guided_json_sends_response_format_and_is_off_by_default(monkeypatch):
    calls = []

    async def ex(system, user, temperature=0.0, max_tokens=512, response_format=None):
        calls.append(response_format)
        return '{"ok": 1}', "stop"
    monkeypatch.setattr(ai_service, "_complete_ex", ex)
    run(ai_service.complete_structured("s", "u", coerce=_coerce, guided_json=True, label="t"))
    run(ai_service.complete_structured("s", "u", coerce=_coerce, label="t"))
    assert calls == [{"type": "json_object"}, None]


def test_guided_json_falls_back_to_plain_on_400(monkeypatch):
    import httpx
    from openai import BadRequestError
    calls = []

    async def ex(system, user, temperature=0.0, max_tokens=512, response_format=None):
        calls.append(response_format)
        if response_format is not None:
            req = httpx.Request("POST", "http://x")
            raise BadRequestError("unsupported", response=httpx.Response(400, request=req), body=None)
        return '{"ok": 1}', "stop"
    monkeypatch.setattr(ai_service, "_complete_ex", ex)
    value, meta = run(ai_service.complete_structured("s", "u", coerce=_coerce, guided_json=True, label="t"))
    assert value == {"ok": 1} and meta.degraded is False
    assert calls == [{"type": "json_object"}, None]


def test_guided_json_does_not_swallow_ai_unavailable(monkeypatch):
    from exceptions import AIServiceUnavailableError

    async def ex(*a, **kw):
        raise AIServiceUnavailableError()
    monkeypatch.setattr(ai_service, "_complete_ex", ex)
    with pytest.raises(AIServiceUnavailableError):
        run(ai_service.complete_structured("s", "u", coerce=_coerce, guided_json=True, label="t"))


def test_parse_failure_log_never_contains_the_output(monkeypatch, caplog):
    secret = "Mara hides the forged contract in the chapel"

    async def ex(*a, **kw):
        return f"Sure! {secret}", "stop"
    monkeypatch.setattr(ai_service, "_complete_ex", ex)
    value, meta = run(ai_service.complete_structured("s", "u", coerce=_coerce, guided_json=True, label="t"))
    assert value is None and meta.degraded
    assert secret not in caplog.text


def test_plot_hole_budget_scales_and_is_bounded():
    assert ai_service._plot_hole_max_tokens(1) == 1400
    assert ai_service._plot_hole_max_tokens(15) == 1800
    assert ai_service._plot_hole_max_tokens(200) == 2400


# ── D1: thread extraction accepts both root shapes ───────────────────────────

def test_thread_coerce_accepts_object_root_and_bare_array():
    ev = {"thread_name": "The forged contract", "chapter_number": 2, "action": "introduced", "description": "d"}
    obj, _ = ai_service.coerce_thread_events({"threads": [ev]}, {2})
    arr, _ = ai_service.coerce_thread_events([ev], {2})
    assert obj == arr and len(obj) == 1


def test_thread_coerce_drops_entries_citing_unknown_chapters():
    ev = {"thread_name": "The forged contract", "chapter_number": 9, "action": "introduced"}
    value, discarded = ai_service.coerce_thread_events({"threads": [ev]}, {1, 2})
    assert not value and discarded == 1


def test_thread_extraction_counts_unreadable_batches(monkeypatch):
    async def ex(*a, **kw):
        return "not json at all", "stop"
    monkeypatch.setattr(ai_service, "_complete_ex", ex)
    stats = {}
    summaries = [{"chapter_number": n, "title": f"C{n}", "key_events": [], "characters_present": [],
                  "raw_summary": ""} for n in range(1, 5)]
    out = run(ai_service.extract_narrative_threads_from_summaries(summaries, stats=stats))
    assert out == []
    assert stats["batches"] == 2 and stats["batches_failed"] == 2


# ── 5.8: emotion harness logic ───────────────────────────────────────────────

def test_emotion_harness_metrics_and_report_shape():
    from measure_emotion_set import EMOTIONS, INTENSITIES, distinctness, run as harness_run, shared_phrase_rate

    async def distinct(text, emotion, intensity):
        return {"transformed": f"{emotion} {intensity} " + " ".join(reversed(text.split()))[:40] + f" {emotion}-only words"}

    async def collapsed(text, emotion, intensity):
        return "her heart raced and tears welled up in her eyes"

    passages = [{"id": "p1", "text": PASSAGE}]
    r_distinct = run(harness_run(distinct, passages, n_trials=1))
    r_collapsed = run(harness_run(collapsed, passages, n_trials=1))
    assert r_distinct["summary"]["scenarios"] == len(EMOTIONS) * len(INTENSITIES)
    assert r_collapsed["summary"]["mean_cross_emotion_similarity"] == 1.0
    assert r_distinct["summary"]["mean_cross_emotion_similarity"] < r_collapsed["summary"]["mean_cross_emotion_similarity"]
    assert r_collapsed["summary"]["mean_shared_phrase_rate"] == 1.0
    assert distinctness({"a": ["x y z"], "b": ["x y z"]}) == 1.0
    assert shared_phrase_rate("", {"a": ["one two three"], "b": ["four five six"]}) == 0.0


def test_style_v3_has_levers_for_every_style_the_picker_offers():
    import re
    from services.prompt_registry import _STYLE_LEVERS_V3
    src = (Path(__file__).resolve().parents[2] / "frontend/lib/transforms.ts").read_text(encoding="utf-8")
    block = src[src.index("export const STYLES"):src.index("\n]", src.index("export const STYLES"))]
    ids = {m.lower() for m in re.findall(r"id: '([^']+)'", block)}
    assert ids and ids <= set(_STYLE_LEVERS_V3), ids - set(_STYLE_LEVERS_V3)


def test_plot_hole_coerce_accepts_object_root_and_bare_array():
    """Review L2: the 400 fallback runs unguided, so both shapes must parse."""
    finding = {"description": "The key is lost in ch 2 but used in ch 3", "severity": "high", "chapters": [2, 3]}
    obj, _ = ai_service.coerce_plot_hole_result({"issues": [finding]})
    arr, _ = ai_service.coerce_plot_hole_result([finding])
    assert obj is not None and arr is not None
    assert obj["issues"][0]["description"] == arr["issues"][0]["description"] == finding["description"]
