# Task 6.5 — variance-aware AI quality regression gate (Stage 12.3, 2026-10-06)

**Tool:** `backend/tests/ai_quality_regression_gate.py` (decision rule unit-tested without a model in
`backend/tests/test_ai_quality_regression_gate.py`, 8 tests). Pod `12j8ehik2alm0j` (1× A40), vLLM 0.9.2,
Qwen2.5-7B-Instruct, prompt `v4`, allow-listed `narratiq_test`. Tree: `2b63b51` plus the uncommitted Stage 12.3
changes (`tree_dirty: true` in every file — this is task 6.5 evidence, not the W-1 release-commit record).

## Why a new gate

The invariant harness (`test_ai_quality_invariants.py`) asserts each invariant once. On a non-deterministic
model a single red run cannot separate a regression from variability: `adventure-3` fails about 1 run in 10 on
unchanged code (`stage-12.1/awt-g-consistency.md` addendum). That is why the 2026-10-03 proof
(`stage-12.1/gate6-regression-detection.md`) was left unticked.

## Design

| | |
|---|---|
| Metric | Pass count k of N for each of the harness's own 11 invariants: locked segment byte-identical (3 passages), `no_change` on already-suitable passages (4), registered names preserved (2), Light strength not flagged (1), suggestions structurally valid (1). Real API, real model |
| Threshold | ALARM when an invariant's observed rate is **below** its recorded baseline with one-sided Fisher exact p < 0.01 / 11 (Bonferroni; family-wise α = 0.01). Equal or better never alarms |
| Sample size | N = 20 per invariant (220 calls per run). Alarm boundaries: 20/20 baseline → ≤ 11/20; 18/20 → ≤ 7/20; 14/20 → ≤ 3/20. N = 10 was rejected (a 7/10 baseline could never alarm) |
| Variance | The baseline is a recorded k/N of the same invariant on unchanged code; the exact test models the sampling noise of both runs. The documented ~1-in-10 wobble cannot alarm |
| Integrity | An HTTP error aborts the run as invalid — it is never counted as a quality failure (found on the first attempt: the per-user AI rate limit turned most calls into 429s; the gate now disables the limiter in-process, as the tests do; production limits untouched) |
| Deliberate regression | Injected **in-process** by wrapping `complete_structured` for the `no_change_assessment` call — no source file is edited |

## Results

| Run | File | Result | Verdict |
|---|---|---|---|
| Baseline (unchanged code) | `baseline.json` | 10 invariants 20/20; `no_change:adventure-3` **17/20** (the documented variability) | recorded |
| Unchanged re-run (false-alarm check) | `rerun-unchanged.json` | 10 × 20/20; adventure-3 19/20 | **no alarm** (correct) |
| Injection 1 — the Stage 12.1 "tightening" sentence | `injected-degraded-no-change.json` | all 11 at 20/20 (adventure-3 20/20) | **no alarm** — and correctly so: on the current code this prompt edit does **not** change behaviour |
| Injection 2 — question reworded to its opposite (3-trial probe, check mode, not saved) | — | no-change 3/3 everywhere; a trace showed the model still answering the `already_suitable` field correctly | no behaviour change |
| Injection 3 — the prompt asks for a renamed JSON field the parser does not read (prompt/code drift) | `injected-renamed-assessor-key.json` | the four `no_change` invariants **0/20**; the other seven unchanged at 20/20 | **ALARM** on exactly the four affected invariants (exit 1) |

**What this establishes**

* The harness, run as this gate, **detects a deliberate prompt regression** that changes behaviour, separates it
  from run-to-run variability (no alarm on the unchanged re-run, despite adventure-3 moving 17 → 19 → 20), and
  points at the invariants affected.
* The 2026-10-03 single-run "proof" did not show detection: the same degradation, measured 20 times, changes
  nothing on the current code, so its one red run was most probably the known variability. The checklist's
  decision to leave that proof unticked was right.

**Open for the owner:** the box asks for an *agreed* threshold. The rule above (family-wise α 0.01, N = 20, baseline
recorded on the current code rather than the Stage 5 v2 baseline, whose prompts are no longer the default) is
proposed for approval in the Owner Decision Package (OD-10). Scheduling stays N/A while CI is waived (W-1).

## Reproduce

```bash
cd backend
export DATABASE_URL=postgresql+psycopg2://narratiq:narratiq@localhost:5432/narratiq_test
python3 tests/ai_quality_regression_gate.py --record-baseline B.json                       # ~9 min
python3 tests/ai_quality_regression_gate.py --baseline B.json --out R.json                  # exit 0 = no alarm
python3 tests/ai_quality_regression_gate.py --baseline B.json \
    --inject-regression renamed-assessor-key --out R2.json                                  # exit 1 = alarm
```
