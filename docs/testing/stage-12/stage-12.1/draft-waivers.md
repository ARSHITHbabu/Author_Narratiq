# Stage 12.1 — DRAFT waiver register (none accepted)

> **Status: DRAFTS ONLY.** No waiver below is accepted, recorded or in force. Each takes effect only if the product
> owner explicitly approves it, with a dated decision. Until then, the gates that depend on these items stay open.
> Master Execution Plan §13: "No gate may be waived without a recorded product-owner decision."

---

## W-1 — Continuous integration (task 6.1; Gate 6 "CI blocks failing merges"; PG-01, PG-10; 6.4/6.5/6.7/7.4/8.9/9.5/11.8 CI halves)

| | |
|---|---|
| **Requirement** | Every change runs the test suites automatically, and a failing change cannot merge into `main` |
| **Why it remains open** | Deferred by the owner on 2026-09-22 (priority on product features). A working GitHub Actions setup was built and verified locally, then removed |
| **Evidence available** | `backend/tests/run_full_regression.sh` runs every suite on demand. Latest full results: backend 1,142/0, retrieval 147/147, frontend unit 108, studio 104 (+3 skipped), a11y 13, variants 32, live browser 69/0/0 (Tranche 3), docs-sync clean |
| **Risk created** | A regression can be merged without anyone running the suites. Protection depends on the operator's discipline |
| **Mitigation present** | One-command local regression runner; `make docs-check`; the dependency gate script; every stage so far ran the full suites before approval |
| **What would close it** | Re-adding the workflow (the removed design is recorded in the Stage 6 report) and making it a required check on `main` |

## W-2 — Container build (MV-10.3; PG-04, a dependency of Gate 8; Stage 10 "Containerisation complete")

| | |
|---|---|
| **Requirement** | A clean container build produces a working stack, with image digests pinned |
| **Why it remains open** | RunPod pods cannot run Docker. `backend/Dockerfile`, `frontend/Dockerfile` and `docker-compose.yml` exist but have never been built |
| **Evidence available** | Production deploys with `start-narratiq.sh`, verified from scratch on fresh pods: 14 min 35 s on 2026-10-03, again from the real checkout path, and in a full restore rehearsal. Every dependency and model is pinned (`requirements.txt`, `requirements.vllm.txt`, model revisions) |
| **Risk created** | Deployment reproducibility depends on the bootstrap script and RunPod's base image; there is no second deployment path |
| **Mitigation present** | Pinned requirements and model revisions; three successful from-scratch bring-ups; a documented rollback |
| **What would close it** | Running `scripts/verify_containers.sh` on any Docker host (MV-10.3) and recording the image digests |

## W-3 — Off-pod backup copy (S10-B; task 10.1; Stage 1/10 items; RPO for volume loss)

| | |
|---|---|
| **Requirement** | Backups stored off the pod, so loss of the RunPod network volume does not lose them |
| **Why it remains open** | No external storage provider is approved (S10-B). The hook `NARRATIQ_OFFPOD_COMMAND` is ready but unconfigured |
| **Evidence available** | Hourly on-pod sets with integrity manifests and restore verification; Gate 7 rehearsal (2026-10-03): full restore with all 57 tables matching, RTO about 21 minutes from a fresh pod |
| **Risk created** | **Loss of the network volume loses the database and every backup.** Author data would be unrecoverable. This is the highest-impact item in this register |
| **Mitigation present** | None against volume loss. Restart and container loss are covered by on-pod backups |
| **What would close it** | An approved destination plus `NARRATIQ_OFFPOD_COMMAND` (recommended: encrypt each set with a public key whose private key never touches the pod), and one verified off-pod restore |

## W-4 — Alerts delivered to a person (S10-D; task 10.2; Stage 10 "Monitoring and alerting live")

| | |
|---|---|
| **Requirement** | When the service degrades, a person is notified |
| **Why it remains open** | No external channel is approved (S10-D). Alerts are written to `/workspace/logs/alerts.jsonl`; the hook `NARRATIQ_ALERT_COMMAND` is ready |
| **Evidence available** | The watchdog raises and records alerts (Stage 10: PASS); `/api/ops/metrics` |
| **Risk created** | An outage, failed backup or stale backup goes unnoticed until someone looks |
| **Mitigation present** | Alert log, ops endpoints and health checks |
| **What would close it** | An approved channel connected through `NARRATIQ_ALERT_COMMAND`, plus one test alert that a person confirms |

## W-5 — `SECRET_KEY` copy in a team secret store (task 2.2; Stage 2 gate)

| | |
|---|---|
| **Requirement** | `SECRET_KEY` is stored outside the pod, so a re-clone or new pod does not sign every author out |
| **Why it remains open** | No team secret store is reachable from the agent environment. This pod generated a **new** key on 2026-10-03 (S12-D) |
| **Evidence available** | The key is stable across restarts (Stage 2); it is generated once and never overwritten (`start-narratiq.sh`) |
| **Risk created** | Losing `backend/.env` (it sits on the same volume as the backups) signs every author out once. **No author data is lost** |
| **Mitigation present** | Sessions are re-established by signing in again |
| **What would close it** | The owner copies the current key into a password manager or team store (procedure: `runpod-environment-variables.md` §3.3) |

---

## Related owner decisions that are not waivers (listed for completeness)

- **Gate 8 / 10.5 "Rollback rehearsal succeeds without data loss."** Rolling back past migration `0027` drops every character's presence label (On page / Mentioned only / In the past). It is documented in the migration and in `rollback.md` §3, and regenerable by running cast generation again. All author content survived the rehearsal. **Decision:** accept that this documented loss satisfies the criterion, or require a data-preserving downgrade.
- **Gate 3a / 4.9 "Fix relationship extraction errors" (not applicable).** No relationship-extraction pipeline exists. **Decision:** accept "not applicable", or define the work. This also holds CAST-H8.
