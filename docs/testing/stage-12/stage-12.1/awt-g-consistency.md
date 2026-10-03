# AWT-G — run-to-run consistency, 10-trial measurement (Stage 12.1)

**Method:** the existing golden-set tool `backend/tests/measure_transform_golden_set.py`, unchanged, with its trial count set to **10** at runtime (the tool's constant is 3). It covers 12 scenarios × 10 trials = **120 transforms**, prompt v4 (the current default), pod `x0smrkvs4n6wpk`, run sequentially.

**Raw output:** `backend/tests/fixtures/transform_golden_stage12_1_v4_n10.json` (every trial's output and metrics).

**Acceptance criterion** (task 5.12 "G: consistent across runs"): 5.12-G was ticked because the mean across-trial stdev **fell below the pre-Stage-5 baseline** (text 0.0643 → 0.0197, content 0.0163 → 0.0051).

| Run | Trials | Mean stdev text | Mean stdev content | Max stdev text |
|---|---:|---:|---:|---:|
| baseline_v1 (pre-Stage-5) | 3 | 0.0643 | 0.0163 | 0.324 |
| after_v2 (Stage 5) | 3 | 0.0197 | 0.0051 | 0.071 |
| Stage 9, 2026-09-27 (v3) | 3 | 0.0213 | 0.0048 | 0.103 |
| Tranche 2b (v4) | 3 | 0.0743 | 0.0223 | 0.362 |
| **Stage 12.1 (v4)** | **10** | **0.0866** | **0.0271** | **0.351** |

**Criterion not met:** both means are above the v1 baseline.

## Where the variability comes from

| Scenario | Unchanged in 10 runs | Stdev text | Sequence (U = returned unchanged, r = rewritten) |
|---|---:|---:|---|
| gothic-1 tone → suspenseful | 1 | 0.351 | rUrrrrrrrr |
| tech-1 style → cinematic | 3 | 0.141 | UUrrUrrrrr |
| tech-4 style → cinematic | 4 | 0.267 | UrUrUrrUrr |
| the other 9 scenarios | 0 or 10 (never mixed) | mean **0.031** | — |

The **3 scenarios that flip between "unchanged" and "rewritten"** average 0.253. The other 9 average 0.031, which is within the v1 baseline. So the rewrites themselves are about as stable as in Stage 5. The spread comes from the yes/no "does this passage need changing?" decision.

## Root cause

That decision is made by the no-change assessor (`_assess_change_needed`, temperature 0). It was called **alone, 20 times in sequence, with identical input**:

| Scenario | "Needs change" in 20 identical calls |
|---|---|
| gothic-1 tone | 19/20 |
| tech-1 style | 15/20 |
| tech-4 style | 3/20 |

Greedy decoding on vLLM 0.9.2 (prefix caching and chunked prefill on) is **not bit-deterministic**. On a borderline yes/no judgement, that is enough to flip the answer. The code path is deterministic and receives identical input every time, so this is **model-serving variability on borderline passages, not a deterministic defect in NarratIQ**.

The shift since Stage 9 (gothic-1 unchanged 3/3 then, mostly rewritten now) matches Tranche 2 A14's rewording of this exact assessor question, an intentional, measured change.

## What was not done, and why

- **No change was made.**
- Caching each verdict per passage would make repeated requests agree, and would improve this metric, without making the judgement better. That is the result-improving change the owner ruled out.
- Disabling vLLM prefix caching is an infrastructure and performance change, outside this item.

## Author impact

- A borderline passage may be returned "unchanged, with a reason" on one request and rewritten on the next.
- Both outcomes are presented honestly; nothing is overwritten without the author choosing **Replace**.
- No data risk.

## Options for the owner (Section 3, G2)

1. Accept as documented model variability (known limitation).
2. Require work, choosing from:
   - (a) a stable verdict per passage (cache);
   - (b) a margin-based assessor that answers "needs change" unless clearly suitable (needs measurement against the A14/A18 baselines);
   - (c) a serving configuration test (prefix caching off), measured for latency.

## Owner direction (2026-10-03, recorded; not a checklist update)

The product owner accepted this measurement as evidence and directed that AWT-G be recorded as follows:

- the 5.12-G acceptance criterion is **NOT met**;
- the measurement covered **120 transforms**;
- the variability is concentrated in **borderline unchanged-vs-rewrite decisions**;
- it is classified as **model variability, not a deterministic NarratIQ code defect**;
- the author stays in control, because no rewrite is applied unless **Replace** is chosen;
- **no artificial caching or other metric-improving workaround** is to be added.

AWT-G must not be presented as passing its original consistency criterion.

## Addendum (2026-10-03, Gate 4 technical closure regression)

- **What happened:** the full backend regression after the Stage 12.1 Plot Assistant fix had one failure: `test_ai_quality_invariants.py::test_already_suitable_passage_is_returned_unchanged[adventure-3]`. The no-change check did not fire on a passage designed as already suitable.
- **Re-run on identical code:** 9 passed, 1 failed out of 10.
- **The code path was not changed:** `git diff` shows that `ai_service.py`'s Stage 12.1 hunks are only the BGE thread sizing, chapter-summary windowing and the Story Bible example filter.
- **Same variability as recorded above:** this is the temperature-0 no-change assessment flipping on identical input, now also observed on `adventure-3` at about 1 in 10.
- **Not changed:** no test, threshold or prompt was modified. AWT-G stays **criterion not met**, pending the owner's decision.
- **The previous full run passed** (1,170 / 0 earlier the same day).
