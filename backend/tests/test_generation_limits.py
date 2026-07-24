"""
Generation-budget and response-contract regression guards (no DB, no LLM, no GPU).

Covers the two defects found during manual testing of task 3.1.  Both were
invisible to the existing suite because both endpoints returned HTTP 200.

  Failure 1 — Long continuation.  generate_continuations() used a fixed
    max_tokens=1600 regardless of the requested length.  Three 350-word
    suggestions need ~1420 tokens of prose plus ~175 for the direction and
    rationale strings and the JSON scaffolding — i.e. ~1600 against a 1600 cap.
    Measured on the real model with the real prompt: 1 run in 4 hit
    finish_reason="length", the truncated JSON array failed to parse,
    _extract_json returned [], and the router padded that to three
    "Could not generate this suggestion — please retry" cards.  Short (100 w,
    ~494 tokens) and medium (200 w, ~848 tokens) never came close, which is why
    only Long failed.

  Failure 2 — Outline.  The backend returned OutlineResponse.outline; the
    frontend read res.data.beats and its TypeScript interface declared `beats`.
    `undefined ?? []` rendered an empty list, so a fully correct 4-beat response
    from Qwen was discarded silently — no error, no toast, no console warning.

The contract tests below are the ones that would have caught Failure 2 before
it reached a manual test: nothing previously compared the two schemas.

    python3 backend/tests/test_generation_limits.py
    pytest  backend/tests/test_generation_limits.py -q
"""
import asyncio
import inspect
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from exceptions import AIResponseTruncatedError
from services import ai_service
import schemas


# Mirrors frontend lib/api.ts CONT_LENGTH_MAP — short / medium / long.
CONT_LENGTHS = {"short": 100, "medium": 200, "long": 350}

# Worst prompt measured end to end against the restored manuscript: real
# retrieval (4 chapter summaries + 4 character profiles) plus the 300-word tail
# the editor sends.  Used to prove the budget stays inside the context window.
MEASURED_PROMPT_TOKENS = 2341
CONTEXT_WINDOW = 8192


def _run(continuation_length: int, *, responses=None, raw='[]', finish_reason="stop"):
    """Run generate_continuations with vLLM stubbed.

    `responses` is a list of (raw, finish_reason) consumed one per attempt, so a
    test can make attempt 1 fail and attempt 2 succeed. Returns
    (max_tokens, result, call_count) — call_count is what pins "at most two
    generation attempts".
    """
    queue = list(responses) if responses is not None else [(raw, finish_reason)]
    seen = {}
    calls = {"n": 0}

    async def fake_complete_ex(system, user, **kwargs):
        seen.update(kwargs)
        calls["n"] += 1
        # Repeat the final scripted response if more attempts occur than
        # scripted — so a runaway loop shows up as a call count, not IndexError.
        return queue[min(calls["n"] - 1, len(queue) - 1)]

    original = ai_service._complete_ex
    ai_service._complete_ex = fake_complete_ex
    try:
        result = asyncio.run(
            ai_service.generate_continuations(
                tail_text="The water had reached the second shelf.",
                story_context="[Ch4] Devika confronts Sant.",
                character_context="## Character: Devika Rao",
                genre_context="GENRE",
                continuation_length=continuation_length,
            )
        )
    finally:
        ai_service._complete_ex = original
    return seen["max_tokens"], result, calls["n"]


def _captured_max_tokens(continuation_length: int, *, raw='[]', finish_reason="stop"):
    """Back-compat shim for the budget tests: returns (max_tokens, result)."""
    mt, result, _ = _run(continuation_length, raw=raw, finish_reason=finish_reason)
    return mt, result


THREE_VALID = json.dumps([
    {"direction": f"D{i}", "text": f"prose {i}", "rationale": f"R{i}"}
    for i in range(3)
])


# ── 1. Dynamic max_tokens scaling ─────────────────────────────────────────────

def test_max_tokens_scales_with_continuation_length():
    short, _ = _captured_max_tokens(CONT_LENGTHS["short"], raw=THREE_VALID)
    medium, _ = _captured_max_tokens(CONT_LENGTHS["medium"], raw=THREE_VALID)
    long_, _ = _captured_max_tokens(CONT_LENGTHS["long"], raw=THREE_VALID)

    assert long_ > medium >= short, (short, medium, long_)


def test_long_budget_clears_the_measured_truncation_point():
    """Long must exceed the 1600 that was actually hit, with real headroom.

    The observed worst case consumed the entire 1600-token cap; anything at or
    barely above that reintroduces the intermittent failure.
    """
    long_, _ = _captured_max_tokens(CONT_LENGTHS["long"], raw=THREE_VALID)

    assert long_ >= 2300, f"long budget {long_} leaves too little headroom over the measured 1600"


# ── 2. Short / medium stability — the no-regression guarantee ─────────────────

def test_short_and_medium_budgets_are_unchanged_at_1600():
    """These two lengths worked before and must behave byte-identically."""
    for name in ("short", "medium"):
        budget, _ = _captured_max_tokens(CONT_LENGTHS[name], raw=THREE_VALID)
        assert budget == 1600, f"{name} budget changed to {budget}; short/medium must stay at 1600"


# ── 3. Context-window budget ──────────────────────────────────────────────────

def test_prompt_plus_output_stays_inside_the_context_window():
    """max-model-len is 8192 on this hardware (1× A40, TP=1)."""
    for name, words in CONT_LENGTHS.items():
        budget, _ = _captured_max_tokens(words, raw=THREE_VALID)
        total = MEASURED_PROMPT_TOKENS + budget
        assert total < CONTEXT_WINDOW, (
            f"{name}: prompt {MEASURED_PROMPT_TOKENS} + output {budget} = {total} >= {CONTEXT_WINDOW}"
        )


# ── 4. Truncation is surfaced, never silently padded ──────────────────────────

TRUNCATED = (
    '[\n  {\n    "direction": "Conflict Escalation",\n'
    '    "text": "Devika, Mara, and Pell left the Bureau\'s headquarters, their steps quick and'
)


def test_truncated_json_does_not_parse():
    """Pins the parser behaviour the failure depends on."""
    assert ai_service._extract_json(TRUNCATED, fallback=[]) == []


def test_truncation_raises_instead_of_returning_fallback_cards():
    """finish_reason='length' with nothing parseable must raise, not return []."""
    try:
        _captured_max_tokens(CONT_LENGTHS["long"], raw=TRUNCATED, finish_reason="length")
    except AIResponseTruncatedError as exc:
        assert "cut off" in str(exc).lower() or "shorter" in str(exc).lower()
        return
    raise AssertionError("truncated generation returned successfully instead of raising")


def test_partial_success_at_the_cap_is_still_returned():
    """Hitting the cap but still yielding usable suggestions is not an error."""
    _, result = _captured_max_tokens(
        CONT_LENGTHS["long"], raw=THREE_VALID, finish_reason="length",
    )
    assert len(result) == 3


def test_malformed_but_complete_output_does_not_raise_truncation():
    """finish_reason='stop' with bad JSON is a different failure — must not claim truncation."""
    _, result = _captured_max_tokens(
        CONT_LENGTHS["long"], raw="I'm sorry, I cannot do that.", finish_reason="stop",
    )
    assert result == []


def test_complete_delegates_to_complete_ex():
    """_complete() must keep its str return type for every existing call site."""
    assert inspect.signature(ai_service._complete).return_annotation is str
    ret = inspect.signature(ai_service._complete_ex).return_annotation
    assert "tuple" in str(ret).lower(), ret


# ── 4b. Structural completion, then exactly one retry ─────────────────────────
#
# The real failure signature, captured live: 4636 chars, finish_reason="stop",
# ~1000 tokens below the cap, three complete objects, no closing bracket.

UNTERMINATED = json.dumps([
    {"direction": f"D{i}", "text": f"prose {i}", "rationale": f"R{i}"}
    for i in range(3)
])[:-1].rstrip()          # drop the final ']' — exactly the observed defect


def test_unterminated_array_is_structurally_completed_without_retry():
    """The 0 ms path: recover in place, spend no second generation."""
    _, result, calls = _run(CONT_LENGTHS["long"], raw=UNTERMINATED, finish_reason="stop")

    assert len(result) == 3, result
    assert result[0]["text"] == "prose 0"
    assert calls == 1, f"structural completion should not trigger a retry (calls={calls})"


def test_structural_completion_preserves_content_exactly():
    """Only the terminator is added — no content is altered."""
    recovered = ai_service._close_unterminated_json_array(UNTERMINATED)

    assert recovered == json.loads(UNTERMINATED + "]")


def test_structural_completion_refuses_anything_but_the_observed_pattern():
    """Narrow by construction — not a general repair engine."""
    close = ai_service._close_unterminated_json_array

    assert close('[{"a": 1}]') is None                  # already valid — nothing to do
    assert close('{"a": 1}') is None                    # object, not an array
    assert close('[{"a": 1}, {"b":') is None            # cut mid-object — not guessed at
    assert close('[{"a": 1},') is None                  # trailing comma — not our case
    assert close('I am sorry, I cannot do that.') is None
    assert close('') is None


def test_retry_fires_when_structural_completion_cannot_help():
    """Unrecoverable + finish_reason='stop' → exactly one fresh sample."""
    _, result, calls = _run(
        CONT_LENGTHS["long"],
        responses=[("I'm sorry, I cannot do that.", "stop"), (THREE_VALID, "stop")],
    )

    assert len(result) == 3, result
    assert calls == 2, f"expected one retry, got {calls} attempts"


def test_no_retry_when_the_first_attempt_succeeds():
    """No wasted ~50s of GPU time on the happy path."""
    _, result, calls = _run(CONT_LENGTHS["long"], raw=THREE_VALID, finish_reason="stop")

    assert len(result) == 3
    assert calls == 1, f"retried despite a successful first attempt (calls={calls})"


def test_no_retry_on_truncation():
    """A budget failure would only truncate again — raise instead."""
    try:
        _run(CONT_LENGTHS["long"], raw=TRUNCATED, finish_reason="length")
    except AIResponseTruncatedError:
        pass
    else:
        raise AssertionError("truncation did not raise")

    # Re-run capturing the call count: the raise must happen after ONE attempt.
    calls = {"n": 0}

    async def counting(system, user, **kwargs):
        calls["n"] += 1
        return TRUNCATED, "length"

    original = ai_service._complete_ex
    ai_service._complete_ex = counting
    try:
        asyncio.run(ai_service.generate_continuations(
            tail_text="t", story_context="s", character_context="c",
            genre_context="g", continuation_length=CONT_LENGTHS["long"],
        ))
    except AIResponseTruncatedError:
        pass
    finally:
        ai_service._complete_ex = original

    assert calls["n"] == 1, f"truncation triggered {calls['n']} attempts; must not retry"


def test_never_exceeds_two_generation_attempts():
    """Both attempts unusable → give up. The hard ceiling."""
    _, result, calls = _run(
        CONT_LENGTHS["long"],
        responses=[("garbage one", "stop"), ("garbage two", "stop")],
    )

    assert result == []
    assert calls == 2, f"expected a hard ceiling of 2 attempts, got {calls}"


def test_retry_that_truncates_reports_truncation():
    """Attempt 1 unparseable, attempt 2 hits the cap → honest truncation error."""
    try:
        _run(CONT_LENGTHS["long"],
             responses=[("garbage", "stop"), (TRUNCATED, "length")])
    except AIResponseTruncatedError:
        return
    raise AssertionError("a truncated retry did not surface as truncation")


def test_short_and_medium_retry_behaviour_unchanged():
    """Short/medium must still succeed in a single attempt at 1600 tokens."""
    for name in ("short", "medium"):
        budget, result, calls = _run(CONT_LENGTHS[name], raw=THREE_VALID, finish_reason="stop")
        assert budget == 1600 and len(result) == 3 and calls == 1, (name, budget, calls)


# ── 5. Backend response contract ──────────────────────────────────────────────

def test_outline_response_field_is_outline_not_beats():
    """The exact mismatch that lost a correct beat sheet in the UI."""
    fields = set(schemas.OutlineResponse.model_fields)

    assert fields == {"chapter_id", "outline"}, fields
    assert "beats" not in fields, "backend renamed to `beats` — frontend reads `outline`"


def test_outline_response_serialises_with_the_outline_key():
    """Guards the wire format the frontend actually consumes."""
    payload = schemas.OutlineResponse(
        chapter_id="c1",
        outline=[schemas.OutlineBeat(
            scene_number=1, beat_description="b",
            characters_present=["Devika"], location="office", pacing_note="tense",
        )],
    ).model_dump()

    assert "outline" in payload and "beats" not in payload
    assert payload["outline"][0]["scene_number"] == 1


def test_continuation_response_field_is_suggestions():
    fields = set(schemas.ContinuationResponse.model_fields)
    assert fields == {"chapter_id", "suggestions"}, fields


# ── 6. Frontend consumes the same contract ────────────────────────────────────
#
# Source-level assertions rather than a JS test run: the mismatch lived in the
# TypeScript interface itself, so the compiler could not catch it. These read
# the real frontend files and fail if either side drifts again.

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def test_frontend_reads_outline_not_beats():
    src = (FRONTEND / "components/ai-tools/AIToolsSidebar.tsx").read_text(encoding="utf-8")

    assert "res.data.outline" in src, "frontend no longer reads res.data.outline"
    assert "res.data.beats" not in src, "frontend still reads the non-existent res.data.beats"


def test_frontend_outline_interface_matches_backend():
    src = (FRONTEND / "lib/types.ts").read_text(encoding="utf-8")
    block = re.search(r"export interface OutlineResponse \{(.*?)\}", src, re.S)

    assert block, "OutlineResponse interface not found in lib/types.ts"
    body = block.group(1)
    assert re.search(r"\boutline\s*:", body), "interface is missing the `outline` field"
    assert not re.search(r"\bbeats\s*:", body), "interface still declares `beats`"


def test_frontend_word_minimum_matches_backend():
    """Both sides require 10 words; a lower client bound just causes a 400."""
    ui = (FRONTEND / "components/ai-tools/AIToolsSidebar.tsx").read_text(encoding="utf-8")
    router = (Path(__file__).resolve().parents[1] / "routers/writing_tools.py").read_text(encoding="utf-8")

    assert "length < 10" in ui, "frontend chapter-goal minimum is not 10 words"
    assert "< 10" in router, "backend chapter-goal minimum is no longer 10 words"


# ── Plain-python runner (no pytest required) ──────────────────────────────────

if __name__ == "__main__":
    tests = [
        (name, obj)
        for name, obj in sorted(globals().items())
        if name.startswith("test_") and callable(obj)
    ]
    failures = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception as exc:  # noqa: BLE001 — this is the test harness
            failures.append((name, exc))
            print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")

    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
