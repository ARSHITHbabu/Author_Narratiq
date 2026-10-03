# Gate 6 / task 6.5 — deliberate prompt regression detected by the AI quality harness (Stage 12.1)

**Harness:** `backend/tests/test_ai_quality_invariants.py` (the `ai-harness` suite of `run_full_regression.sh`). It makes live model calls through the in-process app against the allow-listed `narratiq_test` database. The live backend never reloads code, so it was not affected.

**Degradation:** a realistic "tightening" of the no-change assessor's prompt (`services/ai_service.py`, `_assess_change_needed`). The added instruction: *"Passages almost never fully meet a target, so answer false unless it is impossible to improve it at all."* This is the kind of edit that silently stops the no-change layer protecting text that is already right.

| Step | Result |
|---|---|
| 0. Before: `ai_service.py` identical to HEAD (`git diff --quiet`) | confirmed |
| 1. Baseline harness run | **12 passed, 1 warning in 50.05s** |
| 2. With the deliberate regression | **1 failed, 11 passed, 1 warning in 52.65s**. Red: `test_already_suitable_passage_is_returned_unchanged[adventure-3]`: *"adventure-3 was designed as a true-positive no-change case … but the no-change layer did not fire"* |
| 3. Revert | `ai_service.py` restored from HEAD; `git diff --quiet` clean; the degraded wording appears 0 times |
| 4. After revert | **12 passed, 1 warning in 44.22s** |

**Conclusion:** the harness detects a deliberate prompt regression and goes green again once it is reverted. Task 6.5's verification is met.

**Limits (not hidden):**
- Only one of the already-suitable cases went red. The harness is an invariant check, not a statistical quality measure.
- It runs on demand: there is no schedule or CI (6.1 deferred). "Alert on regression beyond an agreed threshold" (6.5) stays open; the stored-baseline comparison it cites generates nothing.
