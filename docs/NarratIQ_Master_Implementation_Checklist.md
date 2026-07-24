# NarratIQ Master Implementation Checklist

| | |
|---|---|
| **Document** | NarratIQ Master Implementation Checklist |
| **Version** | 1.0 |
| **Created** | 2026-07-24 |
| **Repository state** | branch `main`, commit `c226fd4` |
| **Derived from** | [`docs/NarratIQ_Master_Execution_Plan_and_Document_Implementation_Order.md`](./NarratIQ_Master_Execution_Plan_and_Document_Implementation_Order.md) |
| **Status** | Active — day-to-day execution document |

## Purpose

The single execution checklist for all remaining NarratIQ AI work. The analysis behind this ordering lives in the Master Execution Plan; this document contains only tasks, order, dependencies, verification and completion state.

## How to use this checklist

- Work top to bottom. Stages are ordered by engineering dependency, not by phase number.
- Do not start a stage until its **Entry condition** is met.
- Do not close a stage until its **Stage Completion Gate** is fully ticked.
- Tasks marked **Can run in parallel: Yes** may be picked up by another engineer simultaneously.
- Tasks with a **Blocked by** decision ID cannot start until that decision is recorded in Stage 0.
- Tick the box only when the **Definition of done** is satisfied — not when the code is written.
- Update the progress table whenever a stage closes.

### Three ordering changes from the Master Execution Plan

Repository verification during checklist construction changed three things. Each is noted inline where it applies.

1. **Phase 2 Issues 12 and 13 are a 4-line signature bug, not an AI-output problem.** `writing_tools.py:94, 106, 180, 191` pass `query=` to `retrieve_relevant_chunks()` (first parameter `question`) and `retrieve_character_context()` (parameters `story_id, question, db`). Both raise `TypeError` at runtime. Verified in code; independently identified as **PRE-1** in the Phase 3 specification §7.4. This moves outline and continuation from Large to Small effort and to the front of Stage 3.
2. **Only Issues 2 and 14 belong to the degraded-output class.** The `query=` bug is isolated to `writing_tools.py`; `plot_holes.py` and `analysis.py` use no retrieval helpers. The README's "four features share one root cause" is therefore two causes, not one.
3. **Stage 1 opens with a database backup**, before the pod stop/start. The Master Execution Plan scheduled backup automation under production readiness; a stop/start cycle on an unbacked-up database holding every manuscript is not an acceptable risk to carry.

---

## Overall Progress Summary

**Formula:** `completion % = (ticked actionable checkboxes ÷ total actionable checkboxes) × 100`, counting every `- [ ]` in Stages 0–12 including subtasks, verification steps and stage gates.

| Stage | Total Tasks | Completed | Remaining | Blocked | Status |
|---|---:|---:|---:|---:|---|
| 0 — Decisions and Triage | 10 | 0 | 10 | 0 | Not Started |
| 1 — Backup and RunPod Infrastructure | 9 | 0 | 9 | 0 | In Progress |
| 2 — Environment and Service Verification | 6 | 0 | 6 | 1 | Not Started |
| 3 — Phase 2 Production Defect Resolution | 13 | 0 | 13 | 0 | Not Started |
| 4 — Phase 1 Retrieval and Data Correctness | 15 | 0 | 15 | 6 | Not Started |
| 5 — Phase 1 AI Generation Quality | 16 | 0 | 16 | 2 | Not Started |
| 6 — Test Automation and CI | 7 | 0 | 7 | 0 | Not Started |
| 7 — Phase 3 Implementation | 15 | 0 | 15 | 12 | Not Started |
| 8 — Editor UI and Workspace Redesign | 11 | 0 | 11 | 1 | Not Started |
| 9 — Full Regression Testing and UAT | 7 | 0 | 7 | 1 | Not Started |
| 10 — Production Readiness | 9 | 0 | 9 | 1 | Not Started |
| 11 — Documentation Reconciliation | 9 | 0 | 9 | 1 | Not Started |
| 12 — Release Validation | 3 | 0 | 3 | 1 | Not Started |
| **Total** | **130** | **0** | **130** | **26** | **In Progress** |

> The stage table counts **main tasks**. Stage 1 shows 0 completed because task 1.1 is still open — one of its seven subtasks is done. The counts below track actionable checkboxes and are the authoritative progress measure.

**Total actionable checkboxes:** 1125
**Currently completed:** 6
**Remaining:** 1119
**Overall project completion:** 0.5% (6 ÷ 1125)

> This checklist contains **only remaining work**. Already-delivered systems (PostgreSQL 16 + pgvector, the 15-migration chain, 24 routers, the production-hardening pass) are verified complete and are deliberately absent — they are recorded in the Master Execution Plan §6.1. A 0% reading measures remaining work, not the product.

---

## Next Task to Execute

> ### ☞ Stage 1, Task 1.1 — Take a verified database backup and confirm network-volume persistence
>
> **Next actionable subtask:** *Copy the dump off-pod (not to `/workspace` alone).*
> The `pg_dump` subtask is complete (2026-07-24). A verified, readable archive now exists at `/workspace/backups/` — but it is still **on the pod**, so it does not yet protect against the stop/start. Inspection during that subtask confirmed the PostgreSQL data directory sits on the **ephemeral** container overlay, not the network volume; the database will very likely not survive the stop, making the off-pod copy and the restore test the two items that actually reduce risk.
>
> **Why this is next.** Every downstream task requires a reachable application, and reachability requires exposing pod ports 3000 and 8000 — which on RunPod requires a **stop → edit → start** cycle. That cycle is the single highest-consequence action in the whole plan: no backup existed anywhere in the repository (production gap PG-02), and `/workspace` persistence across a pod stop has never been verified in writing. Taking the backup first converts an irreversible risk into a reversible one.
>
> Stage 0 decisions are formally first in the document order, but only **D-2** touches Stage 1–2 work, and it does not block the backup. Run Stage 0 in parallel — the decision session should be scheduled the same day.
>
> **Prerequisites:** SSH/terminal access to the running pod. None other.
>
> **Source:** Production gap PG-02 (Master Execution Plan §12); `docs/incidents/runpod-port-3000-404-incident-report.md`; `docs/operations/runpod-deployment.md`
>
> **Completion condition:** A `pg_dump` of the live database is stored **off-pod**, its integrity verified by a test restore into a scratch database, and the network volume mount point is documented and confirmed to survive a stop/start.
>
> **Do not stop the pod until this task is ticked.**

---

# Stage 0 — Required Product and Engineering Decisions

**Entry condition:** Master Execution Plan reviewed.
**Why first:** Six decisions block 25 downstream tasks. Recording them costs one meeting; guessing them costs rework.
**Runs in parallel with:** Stages 1 and 2 (no decision blocks the infrastructure work except D-2, which blocks only task 2.4).

---

- [ ] **0.1 — D-1: Plot Assistant retrieval scope**
  - **Source:** Master Execution Plan §5.1; `docs/issues-and-bugs/open/phase-1-ai-writing-tools-qa-issues.docx` (Plot Assistant Critical 1, 2, 5, 9; High 11)
  - **Area:** Product / AI
  - **Priority:** Critical
  - **Depends on:** None
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Context:** `plot_assistant.py:90` and `:138` pass `max_chapter_number=current_chapter_number`. This is deliberate spoiler prevention, and it is the mechanism behind ~9 QA issues. Options: (a) always story-wide; (b) keep the guard, add an explicit scope toggle; (c) mode-dependent. Engineering recommendation: **(b)** — the real defect is that the limiting is silent.
  - **Implementation checklist:**
    - [ ] Record the approved decision (a / b / c)
    - [ ] Record the decision owner
    - [ ] Record the approval date
    - [ ] Update dependent tasks 4.1, 4.2, 4.3, 4.4, 4.15
  - **Verification:**
    - [ ] Decision written into the repository, not only into chat or a meeting note
  - **Definition of done:** Approved retrieval-scope behaviour is documented and Stage 4 tasks are unblocked.

- [ ] **0.2 — D-2: Retire or repair `start.sh`**
  - **Source:** Master Execution Plan §5.4; `docs/operations/runpod-environment-variables.md` §10
  - **Area:** Infrastructure
  - **Priority:** Medium
  - **Depends on:** None
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Context:** `start.sh:25` and `scripts/verify_runpod_setup.sh:14` use port 8001; `config.py:59` and `start-narratiq.sh:17` use 9001. The verification script reports a false failure against a healthy stack.
  - **Implementation checklist:**
    - [ ] Record the approved decision (retire / repair)
    - [ ] Record the decision owner
    - [ ] Record the approval date
    - [ ] Update dependent task 2.4
  - **Verification:**
    - [ ] Decision recorded in the repository
  - **Definition of done:** Task 2.4 has an unambiguous instruction.

- [ ] **0.3 — D-3: Single-worker or multi-worker deployment target**
  - **Source:** Master Execution Plan §5.8, PG-05; `backend/middleware/rate_limit.py:67`
  - **Area:** Infrastructure / Security
  - **Priority:** High
  - **Depends on:** None
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Context:** slowapi storage is in-memory and per-process. Correct only at `--workers 1`. Any multi-worker target makes Redis-backed storage mandatory.
  - **Implementation checklist:**
    - [ ] Record the approved decision and target worker count
    - [ ] Record the decision owner
    - [ ] Record the approval date
    - [ ] Update dependent task 10.4
  - **Verification:**
    - [ ] Decision recorded; task 10.4 sized accordingly
  - **Definition of done:** Rate-limit storage requirement is settled before launch sizing.

- [ ] **0.4 — D-4: Phase 3 stakeholder decisions (spec §45, D1–D12)**
  - **Source:** `docs/phases/phase-3-planned/phase-3-author-centric-ai-workflow.md` §45
  - **Area:** Product / AI / Infrastructure
  - **Priority:** High
  - **Depends on:** None
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] D1 — plan limit values
    - [ ] D2 — plan assignment mechanism
    - [ ] D3 — free-tier pin retention (3 / 7 / 14 days)
    - [ ] D4 — `pin_store_embedding` default (on / off)
    - [ ] D5 — default style match level (off / light / strong)
    - [ ] D6 — Tier-2 strict consistency gating (all / pro+ / off)
    - [ ] D7 — fold PRE-2 into Phase 3A (yes / separate)
    - [ ] D8 — PRE-1 as Phase 3 M0 or immediate hotfix *(this checklist assumes **immediate hotfix**, task 3.1 — confirm)*
    - [ ] D9 — exclude `ai_generation_pins` from logical backups
    - [ ] D10 — Idea Shelf navigation placement
    - [ ] D11 — account-level style profiles (Phase 3 / later)
    - [ ] D12 — auto-retry on near-duplicate (on / off)
    - [ ] Record owner and approval date for all twelve
    - [ ] Update dependent tasks 7.1 through 7.15
  - **Verification:**
    - [ ] All twelve recorded with a rationale
  - **Definition of done:** Stage 7 can start without open product questions.

- [ ] **0.5 — D-5: Preservation-layer sequencing**
  - **Source:** Master Execution Plan §7.3, §5.9
  - **Area:** Product / AI / Planning
  - **Priority:** Critical
  - **Depends on:** None
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Context:** Phase 3's P3-02 and P3-05 are, by design, the fix for the 48-issue author-voice cluster. Implementing them generically in Stage 5 and again in Phase 3 builds the same capability twice. This checklist assumes they are **pulled forward into Stage 5** (tasks 5.3, 5.4) — confirm or reverse.
  - **Implementation checklist:**
    - [ ] Record the approved decision (pull forward / keep in Phase 3)
    - [ ] Record the decision owner
    - [ ] Record the approval date
    - [ ] If reversed, move tasks 5.3 and 5.4 into Stage 7 and update task 7.3
  - **Verification:**
    - [ ] Decision recorded; Stage 5 and Stage 7 task lists reconciled
  - **Definition of done:** No capability is scheduled to be built twice.

- [ ] **0.6 — D-6: Release-blocking issue scope**
  - **Source:** Master Execution Plan §5.9, Gate 4
  - **Area:** Product
  - **Priority:** Critical
  - **Depends on:** Task 0.9
  - **Blocked by:** None
  - **Can run in parallel:** No — needs the triage output
  - **Implementation checklist:**
    - [ ] Define the release-blocking severity bar
    - [ ] Apply it to all triaged issues
    - [ ] Record the decision owner
    - [ ] Record the approval date
    - [ ] Update Stage 12 gate criteria
  - **Verification:**
    - [ ] Every issue carries a release-blocking / post-launch / won't-fix label
  - **Definition of done:** "Are we ready to ship?" is an answerable question.

- [ ] **0.7 — D-7: Missing recovery report**
  - **Source:** Master Execution Plan §4.4; `README.md`; `docs/archive/documentation-recovery-changelog.md:282`
  - **Area:** Documentation
  - **Priority:** Low
  - **Depends on:** None
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Search for `NarratIQ_Project_Recovery_Report.docx` outside the repository
    - [ ] Record the approved decision (commit it / formally retire the reference)
    - [ ] Record the decision owner and approval date
    - [ ] Update dependent task 11.9
  - **Verification:**
    - [ ] Decision recorded
  - **Definition of done:** The reference is either resolvable or formally retired.

- [ ] **0.8 — D-8: Acceptable chapter ceiling at launch**
  - **Source:** Master Execution Plan §5.5; `backend/services/ai_service.py:1533`, `:1773`
  - **Area:** Product / AI
  - **Priority:** Medium
  - **Depends on:** None
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Context:** Plot-hole detection and manuscript reports cap at 60 chapters. The `batched` / `hierarchical` strategies are **not written** — lines 1607–1610 and 1884–1885 are commented registry entries pointing at non-existent functions. This is implementation work, not enablement.
  - **Implementation checklist:**
    - [ ] Record the approved decision (accept 60 at launch / implement batched strategy)
    - [ ] Record the decision owner and approval date
    - [ ] If implementing, add scoped tasks to Stage 5 and size them as new development
  - **Verification:**
    - [ ] Decision recorded; the 60-chapter limit is documented in user-facing terms if accepted
  - **Definition of done:** The supported manuscript length is a stated product commitment.

- [ ] **0.9 — Triage the full open-issue backlog**
  - **Source:** `docs/issues-and-bugs/open/phase-1-ai-writing-tools-qa-issues.docx` (154 issues); `docs/issues-and-bugs/open/phase-2-production-testing-issues.docx` (14 issues)
  - **Area:** Product / Testing
  - **Priority:** Critical
  - **Depends on:** None
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Import all 154 Phase 1 issues into the tracker with sub-report and severity preserved
    - [ ] Import all 14 Phase 2 issues with severity preserved
    - [ ] Merge the two Search sub-reports (9 + 12 issues, substantially duplicated) preserving both references
    - [ ] Label each issue release-blocking / post-launch / won't-fix
    - [ ] Link each issue to its checklist task ID in this document
    - [ ] Assign an owner to every release-blocking issue
  - **Verification:**
    - [ ] Issue count in the tracker reconciles to 168 minus recorded merges
    - [ ] Every issue maps to exactly one checklist task
  - **Definition of done:** No issue exists only inside a `.docx`; the backlog is schedulable.

- [ ] **0.10 — Assign stage owners**
  - **Source:** Master Execution Plan §10
  - **Area:** Planning
  - **Priority:** High
  - **Depends on:** None
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Assign an owner to each of Stages 1–12
    - [ ] Assign a single owner per functional region of `ai_service.py` (retrieval / prompts / strategies) — this file is touched by Stages 3, 4, 5 and 7
    - [ ] Agree the parallel-track allocation from Master Execution Plan §10.1
  - **Verification:**
    - [ ] Every stage has a named owner
  - **Definition of done:** No stage is unowned and `ai_service.py` has no concurrent-edit conflict risk.

### Stage 0 Completion Gate

- [ ] All eight decisions (D-1 … D-8) recorded with owner and date
- [ ] All twelve Phase 3 sub-decisions (D1–D12) recorded
- [ ] Full backlog triaged and labelled
- [ ] Every stage has a named owner
- [ ] Decision register (below) fully populated
- [ ] Stage 4, 5 and 7 blocked-task lists updated to reflect the decisions

---

# Stage 1 — Backup and RunPod Infrastructure Stabilisation

**Entry condition:** Terminal access to the running pod.
**Why here:** The application is healthy and completely unreachable — ports 3000 and 8000 are not exposed. Nothing downstream is verifiable until this is fixed, and the fix requires a pod stop/start.
**Source:** `docs/incidents/runpod-port-3000-404-incident-report.md`; `docs/operations/runpod-deployment.md`; PG-02

---

- [ ] **1.1 — Take a verified database backup and confirm volume persistence** ☞ *NEXT TASK*
  - **Source:** PG-02; incident report
  - **Area:** Infrastructure / Database
  - **Priority:** Critical
  - **Depends on:** None
  - **Blocked by:** None
  - **Can run in parallel:** No — blocks 1.3
  - **Implementation checklist:**
    - [x] `pg_dump` the live `narratiq` database — *2026-07-24*
    - [ ] Copy the dump **off-pod** (not to `/workspace` alone) — ⏸ **DEFERRED by user decision, 2026-07-24.** Requires a manual receive step on the user's machine and a destination choice. The user will complete it **before any operation that could endanger the backup**. See the blocking note under task 1.3.
    - [x] Record the dump size, timestamp and checksum — *2026-07-24, recorded in `/workspace/backups/BACKUP-RECORD.txt`*
    - [x] Test-restore the dump into a scratch database and confirm row counts on `stories`, `chapters`, `characters` — *2026-07-24*
    - [x] Identify and document the network volume mount point — *2026-07-24, [`docs/operations/storage-and-persistence.md`](./operations/storage-and-persistence.md)*
    - [x] Document which paths survive a pod stop and which do not — *2026-07-24, [`docs/operations/storage-and-persistence.md`](./operations/storage-and-persistence.md) §8. All entries **Predicted (unobserved)** until task 1.5 confirms or corrects them.*
    - [ ] Back up `backend/.env` and `frontend/.env.local` separately (they hold `SECRET_KEY`)
  - **Verification:**
    - [x] Test restore completes without error and row counts match the source — *2026-07-24*
    - [ ] Backup file is retrievable from outside the pod — ⏸ blocked by the deferred off-pod copy
  - **Definition of done:** The database can be fully restored from an off-pod artifact, proven by an actual restore, not by the dump existing.
  - **Progress notes:**
    - *2026-07-24 — `pg_dump` subtask complete.* `scripts/backup_database.sh` added; archive at `/workspace/backups/narratiq-20260724T103824Z.dump` (474,438 bytes, SHA-256 `f1b07d30…c233ac5`), verified readable by `pg_restore --list` with 52 `TABLE DATA` entries reconciling to the 52 public tables, plus `alembic_version` and `EXTENSION vector`. Companion `narratiq-globals-*.sql` carries role definitions with `--no-role-passwords`. Source row counts unchanged (`stories`=1, `chapters`=4, `characters`=8, `users`=1, `chapter_chunks`=21); no downtime. **The backup is still on-pod** — the two verification items below remain open.
    - *Finding — PostgreSQL data directory is on ephemeral storage.* `postgres -D /var/lib/postgresql/16/main` is on the container overlay, not the `/workspace` network volume. The restore path in task 1.5 should be treated as the **expected** outcome of the stop/start, not a contingency.
    - *Finding — `chmod` is not enforced on `/workspace`.* The RunPod FUSE mount (`mfs#eu-se-1.runpod.net:9421`) forces group/other bits to mirror owner bits, so `700`/`600` return success but read back as `777`/`666`. Systemic to the volume — `backend/.env` is already mode `666`. The backup script attempts the `chmod` and warns when it does not take. Confidentiality therefore depends on off-pod storage; encryption-at-rest is a candidate for Stage 10.
    - *2026-07-24 — backup metadata recorded.* `/workspace/backups/BACKUP-RECORD.txt` holds filename, UTC timestamp, byte size and SHA-256 for both dumps and both globals files, plus the source database state they capture. Values independently re-derived from the filesystem and cross-checked against the `.sha256` sidecars; backup artifacts unmodified.
    - *2026-07-24 — test restore passed; the backup is proven restorable.* `narratiq-20260724T103824Z.dump` restored into scratch database `narratiq_restore_test` with `pg_restore --exit-on-error`: exit 0, zero errors or warnings. All comparisons against the live database were exact — `stories`=1, `chapters`=4, `characters`=8, `users`=1, `chapter_chunks`=21, `alembic_version`=0015, 52 tables, 124 indexes including 6 HNSW. Byte-level md5 over chapter/story/character content matched (`a9cd379f…`), as did md5 over all `vector(1024)` embeddings (`1414ed11…`); a pgvector `<=>` cosine query ran correctly on the restored data. Live database unmodified, services healthy throughout, scratch database dropped. **Caveat:** restored with `--no-owner`, so the `ALTER … OWNER TO narratiq` path is untested — a real recovery should create the role from `narratiq-globals-*.sql` first and restore without that flag. Only the first of the two archives was restore-tested. `sudo` is absent on this pod; `su postgres -c` was used instead, and no PostgreSQL configuration was changed.
    - *2026-07-24 — network volume identified and documented.* New reference: `docs/operations/storage-and-persistence.md`. `/workspace` is a MooseFS FUSE mount, `mfs#eu-se-1.runpod.net:9421[/podvolumes/d12dtfg81gbe/2e5wiiphzhzf14]`, region `eu-se-1`, options `rw,nosuid,nodev,relatime,user_id=0,group_id=0,allow_other`. Exactly two data-bearing filesystems exist: `/workspace` (network volume) and `/` (overlay, 100 G). Repository, models, backups and uploads are on the volume; **PostgreSQL data directory, logs and `/root` are on the container layer**. Persistence across a pod stop is labelled **Expected, not Verified** — no stop has been observed. Per-path survival analysis is subtask 6; task 1.5 supplies the observation that upgrades the label.
    - *2026-07-24 — pod-stop survival documented as prediction.* `storage-and-persistence.md` §8 covers 14 paths. Filesystem assignments are measured; the survival column is **Predicted (unobserved)** on every row — no pod stop has been performed. Predicted to survive: repository, models, backups, uploads, `node_modules`, `.next`, `backend/.env`. Predicted lost: **the PostgreSQL data directory**, all Python packages (`/usr/local/lib/python3.11/dist-packages` — system Python, no virtualenv), PostgreSQL and Node apt binaries, the `ovis.py` patch, `/tmp/narratiq-logs`, `/root`. Verified directly: every `start-narratiq.sh` re-install guard is a presence check (`:21,:53,:63,:97,:124,:205`) so all re-trigger on a rebuilt container — **but `:472,:479` create schema only and `grep pg_restore` returns nothing in either startup script, so the stack comes back reporting healthy with zero manuscripts and the data restore is a manual step nothing automates.**
    - *2026-07-24 — off-pod copy deferred by user decision.* The transfer needs a manual receive step on the user's machine and a destination choice, so it is being scheduled separately. No transfer was attempted. On-pod backups are intact and untouched. **Task 1.3 (stop the pod) must not proceed until this is done** — see the hard stop recorded there. Remaining subtasks of 1.1 that do not depend on the off-pod copy continue in document order.
    - *Finding — weak database credential.* The `narratiq` role's password is identical to its username and database name. PostgreSQL binds to `127.0.0.1` only, which bounds exposure. Pre-existing; not changed. Triage alongside Stage 10.

- [ ] **1.2 — Record the pre-restart baseline**
  - **Source:** incident report §2
  - **Area:** Infrastructure
  - **Priority:** High
  - **Depends on:** 1.1
  - **Blocked by:** None
  - **Can run in parallel:** No
  - **Implementation checklist:**
    - [ ] Capture `ps aux`, `ss -tulpn`, `nvidia-smi`
    - [ ] Capture `curl localhost:8000/api/health` output
    - [ ] Capture current `frontend/.env.local` contents
    - [ ] Capture the current pod ID and region
    - [ ] Save `/tmp/narratiq-logs/*.log`off-pod
  - **Verification:**
    - [ ] Baseline artifacts stored off-pod
  - **Definition of done:** Post-restart state can be diffed against a known-good baseline.

- [ ] **1.3 — Stop the pod safely**
  - **Source:** incident report §4
  - **Area:** Infrastructure
  - **Priority:** Critical
  - **Depends on:** 1.1, 1.2
  - **Blocked by:** None
  - **Can run in parallel:** No
  - **Implementation checklist:**
    - [ ] Confirm task 1.1 is ticked
    - [ ] Stop PostgreSQL cleanly before the pod stop
    - [ ] Stop the pod via the RunPod console
  - > ### ⛔ HARD STOP — do not start this task yet
    > The off-pod copy (task 1.1, subtask 2) is **deferred** as of 2026-07-24. The only backup is on the pod, and inspection confirmed PostgreSQL's data directory sits on the **ephemeral container overlay** (`/var/lib/postgresql/16/main`), not the network volume. Stopping the pod now would very likely destroy the live database while its only backup shares the same failure domain.
    >
    > **Precondition for starting 1.3:** subtask 2 of task 1.1 is ticked and a checksum has been verified on the destination machine.
  - **Verification:**
    - [ ] Pod shows stopped state; no write was in flight at shutdown
  - **Definition of done:** Pod stopped with a verified backup in hand.

- [ ] **1.4 — Expose HTTP ports 3000 and 8000**
  - **Source:** incident report §1, §4 — the root cause
  - **Area:** Infrastructure
  - **Priority:** Critical
  - **Depends on:** 1.3
  - **Blocked by:** None
  - **Can run in parallel:** No
  - **Context:** The pod exposes only TCP 22, HTTP 8888, HTTP 19123. Both 3000 (frontend) and 8000 (API) are unexposed — exposing only 3000 yields a UI that loads and then fails every API call.
  - **Implementation checklist:**
    - [ ] Add HTTP port **3000** to the pod configuration
    - [ ] Add HTTP port **8000** to the pod configuration
    - [ ] Confirm both appear in the saved configuration before starting
  - **Verification:**
    - [ ] RunPod GraphQL API `pod.runtime.ports` lists both privatePorts
  - **Definition of done:** Both ports are present in the pod's authoritative port list.

- [ ] **1.5 — Restart the pod and bring up the stack**
  - **Source:** `docs/operations/how-to-run.md`; `start-narratiq.sh`
  - **Area:** Infrastructure
  - **Priority:** Critical
  - **Depends on:** 1.4
  - **Blocked by:** None
  - **Can run in parallel:** No
  - **Implementation checklist:**
    - [ ] Start the pod
    - [ ] Confirm `/workspace/narratiq-ai` and `/workspace/models` survived the stop
    - [ ] Confirm the database survived; if not, restore from task 1.1
    - [ ] Run `bash start-narratiq.sh`
    - [ ] Watch `/tmp/narratiq-logs/vllm.log`, `backend.log`, `frontend.log` to completion
  - **Verification:**
    - [ ] All three services report started
    - [ ] `curl localhost:8000/api/health` reports vLLM available, not `"unavailable"`
  - **Definition of done:** Full stack running on the restarted pod with data intact.
  - > ### ☞ Run the persistence confirmation **before** anything else writes
    > [`docs/operations/storage-and-persistence.md`](./operations/storage-and-persistence.md) **§8.5** contains a ready-to-run command block for this exact moment — the first start after a stop. It checks whether the volume returned with its contents, whether the database survived or came back as a fresh empty cluster, and whether the container layer reset as predicted.
    >
    > §8 currently records **predictions**, every row labelled *Predicted (unobserved)*. This start is the only opportunity to convert them into observations. After running the block, update §8.2's Evidence column to **Verified 〈date〉** for each confirmed row, and **correct** any row the results contradict rather than leaving the prediction standing.
    >
    > **Expect the database to be gone.** §8.3 and §8.4: `start-narratiq.sh:472,479` create the schema only, and no `pg_restore` exists in any startup script — so a healthy-looking stack with zero manuscripts is the predicted outcome, not a surprise. The restore from task 1.1 is a manual step.

- [ ] **1.6 — Verify actual GPU configuration and model context length**
  - **Source:** incident report §11 — contradicts `CLAUDE.md`
  - **Area:** Infrastructure / AI
  - **Priority:** High
  - **Depends on:** 1.5
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Context:** The incident found **1× NVIDIA A40** with effective `max-model-len` **8192**, while `CLAUDE.md` documents 2× RTX PRO 4500 Blackwell (sm_120) with `--tensor-parallel-size 2` and 16384. The Blackwell NCCL flags and sm_120 requirements may not apply.
  - **Implementation checklist:**
    - [ ] Record `nvidia-smi` output — GPU model and count
    - [ ] Record `RUNPOD_GPU_COUNT`
    - [ ] Record the actual `tensor_parallel` value from `/api/health`
    - [ ] Record the effective `max-model-len` from the vLLM startup log
    - [ ] Determine whether `NCCL_P2P_DISABLE` / `NCCL_SHM_DISABLE` are required on this hardware
    - [ ] Feed all findings into task 11.4
  - **Verification:**
    - [ ] Recorded values match what vLLM actually started with
  - **Definition of done:** The real hardware and context window are known and documented facts.

- [ ] **1.7 — Rebuild the frontend with the correct public API URL**
  - **Source:** `CLAUDE.md`; `docs/operations/how-to-run.md`
  - **Area:** Frontend / Infrastructure
  - **Priority:** Critical
  - **Depends on:** 1.5
  - **Blocked by:** None
  - **Can run in parallel:** No
  - **Context:** `NEXT_PUBLIC_API_URL` is inlined at **build** time. A pod ID change without a rebuild produces a UI that loads and calls the wrong host.
  - **Implementation checklist:**
    - [ ] Confirm the pod ID after restart
    - [ ] Write `frontend/.env.local` with `NEXT_PUBLIC_API_URL=https://{POD_ID}-8000.proxy.runpod.net`
    - [ ] Run `npm run build` in `frontend/`
    - [ ] Restart the frontend service
  - **Verification:**
    - [ ] Browser network tab shows API calls going to the `-8000` proxy host
    - [ ] No call targets `localhost` from the browser
  - **Definition of done:** The built frontend targets the correct external API host.

- [ ] **1.8 — Verify external reachability end to end**
  - **Source:** incident report §1
  - **Area:** Infrastructure / Testing
  - **Priority:** Critical
  - **Depends on:** 1.7
  - **Blocked by:** None
  - **Can run in parallel:** No
  - **Implementation checklist:**
    - [ ] `https://{POD_ID}-3000.proxy.runpod.net` returns HTTP 200 from an external browser
    - [ ] `https://{POD_ID}-8000.proxy.runpod.net/api/health` returns healthy
    - [ ] Log in through the external URL
    - [ ] Open a project and load a chapter
    - [ ] Run one real AI generation through the proxy
  - **Verification:**
    - [ ] A 404 with `server: cloudflare` and an empty body no longer occurs
    - [ ] Full round trip works from outside the pod
  - **Definition of done:** An external user can log in, open a manuscript and get an AI response.

- [ ] **1.9 — Add the port contract to deployment documentation**
  - **Source:** incident report §12 recommendation
  - **Area:** Documentation
  - **Priority:** High
  - **Depends on:** 1.8
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Add "expose HTTP 3000 and 8000" as a **pod-creation prerequisite** in `docs/operations/runpod-deployment.md`
    - [ ] Document that ports are fixed at pod creation and need a stop/edit/start to change
    - [ ] Document the diagnostic signature: empty-body 404 + `server: cloudflare` = unexposed port, never an application fault
    - [ ] Mark the incident resolved with the fix date
  - **Verification:**
    - [ ] A new operator following the deployment doc exposes both ports at creation
  - **Definition of done:** This incident cannot recur through the documented procedure.
  - **Also found in this document — recorded 2026-07-24 during task 1.1, not yet fixed:**
    - `runpod-deployment.md:55` instructs `ln -s /runpod-volume/models /workspace/models`. **`/runpod-volume` does not exist on this pod** — `/workspace` *is* the network volume mount, and `/workspace/models` is a real directory, not a symlink. Following the document as written produces a broken symlink and a stack that cannot find its model weights.
    - `runpod-deployment.md:48` states a ~17 GB model footprint; measured size is **22 G**.
    - Evidence and the correct layout: [`docs/operations/storage-and-persistence.md`](./operations/storage-and-persistence.md) §6.

### Stage 1 Completion Gate

- [ ] Verified off-pod backup exists and a test restore succeeded
- [ ] Ports 3000 and 8000 exposed and confirmed via the RunPod API
- [ ] All three services healthy after restart
- [ ] Frontend rebuilt against the correct API URL
- [ ] External end-to-end round trip succeeds
- [ ] Actual GPU and context length recorded
- [ ] Deployment documentation updated with the port contract
- [ ] **Gate 1 — Environment stable** passed

---

# Stage 2 — Environment and Service Verification

**Entry condition:** Stage 1 gate passed.
**Why here:** A stale `VLLM_BASE_URL` in the RunPod UI silently overrides `backend/.env`, producing a healthy backend where every AI call returns 503. Debugging Stages 3–5 against that state wastes enormous effort on phantom AI failures.
**Source:** `docs/operations/runpod-environment-variables.md`

---

- [ ] **2.1 — Audit and clean RunPod UI environment variables**
  - **Source:** `docs/operations/runpod-environment-variables.md` §4, §10
  - **Area:** Infrastructure
  - **Priority:** Critical
  - **Depends on:** Stage 1
  - **Blocked by:** None
  - **Can run in parallel:** No
  - **Implementation checklist:**
    - [ ] List every variable currently set in the RunPod UI
    - [ ] Compare against the source document's obsolete-variable table
    - [ ] Delete every obsolete key, especially any stale `VLLM_BASE_URL` pointing at 8001
    - [ ] Confirm no key violates `extra="forbid"` in `backend/config.py`
    - [ ] Document the final approved variable set
  - **Verification:**
    - [ ] Backend starts cleanly with no pydantic-settings error
    - [ ] `/api/health` reports vLLM available
  - **Definition of done:** Only variables that are actually read remain set.

- [ ] **2.2 — Verify `SECRET_KEY` presence and stability**
  - **Source:** `CLAUDE.md` Config Gotchas; `.env.example`
  - **Area:** Security / Infrastructure
  - **Priority:** High
  - **Depends on:** 2.1
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Confirm `SECRET_KEY` is set and ≥32 characters
    - [ ] Confirm it is set in the RunPod UI, not only auto-generated into `backend/.env`, so a re-clone does not invalidate sessions
    - [ ] Record it in the team secret store
  - **Verification:**
    - [ ] Restart the backend; existing JWTs still validate
  - **Definition of done:** Logins survive a backend restart and a repository re-clone.

- [ ] **2.3 — Verify all three services and the vLLM port**
  - **Source:** `docs/operations/how-to-run.md`
  - **Area:** Infrastructure / Testing
  - **Priority:** High
  - **Depends on:** 2.1
  - **Blocked by:** None
  - **Can run in parallel:** No
  - **Implementation checklist:**
    - [ ] vLLM listening on 9001 and serving `Qwen/Qwen2.5-7B-Instruct`
    - [ ] Backend on 8000; `/api/health` fully healthy
    - [ ] Frontend on 3000
    - [ ] BGE-M3 loaded — confirm from the startup log
    - [ ] pgvector self-check passed at startup
    - [ ] Orphan-job recovery ran at startup
  - **Verification:**
    - [ ] One embedding operation and one generation operation both succeed
  - **Definition of done:** No service is in degraded mode.

- [ ] **2.4 — Resolve the 8001/9001 port contradiction**
  - **Source:** Master Execution Plan §5.4; `start.sh:25`; `scripts/verify_runpod_setup.sh:14`
  - **Area:** Infrastructure
  - **Priority:** Medium
  - **Depends on:** 2.3
  - **Blocked by:** **D-2**
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Apply the D-2 decision — retire `start.sh` or correct it to 9001
    - [ ] Correct `scripts/verify_runpod_setup.sh:14` to 9001
    - [ ] Remove or update any remaining 8001 reference in scripts
  - **Verification:**
    - [ ] `bash scripts/verify_runpod_setup.sh` exits 0 against the working stack
    - [ ] No script reports a false failure
  - **Definition of done:** The verification script tells the truth, so operators can trust it.

- [ ] **2.5 — Close the UNVERIFIED items in the environment document**
  - **Source:** `docs/operations/runpod-environment-variables.md` §11
  - **Area:** Documentation / Infrastructure
  - **Priority:** Medium
  - **Depends on:** 2.3
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Walk §11 item by item against the now-live pod
    - [ ] Mark each Confirmed or still Unverified with evidence
    - [ ] Feed remaining unknowns into task 11.5
  - **Verification:**
    - [ ] Every §11 item has a recorded outcome
  - **Definition of done:** The environment document contains no untested assumption.

- [ ] **2.6 — Establish a repeatable clean-start verification script**
  - **Source:** Master Execution Plan Gate 1; PG-04 precursor
  - **Area:** Infrastructure / Testing
  - **Priority:** Medium
  - **Depends on:** 2.3, 2.4
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Extend `verify_runpod_setup.sh` to check external proxy reachability on 3000 and 8000
    - [ ] Add a vLLM generation smoke check
    - [ ] Add a pgvector query smoke check
    - [ ] Add a check that ports 3000/8000 appear in the RunPod port list
  - **Verification:**
    - [ ] Script passes on the current pod and fails correctly on a deliberately broken config
  - **Definition of done:** Environment health is one command, not a manual ritual.

### Stage 2 Completion Gate

- [ ] Obsolete environment variables removed
- [ ] `SECRET_KEY` stable and stored
- [ ] All three services verified healthy, vLLM on 9001
- [ ] Port contradiction resolved; verification script passes honestly
- [ ] Environment document UNVERIFIED items closed
- [ ] Clean-start verification is a single repeatable command
- [ ] No AI endpoint returns 503 for environment reasons

---

# Stage 3 — Phase 2 Production Defect Resolution

**Entry condition:** Stage 2 gate passed.
**Why here:** Contains the only Critical-rated defect in the repository plus four features that fail outright. Highest ratio of user-visible improvement to effort in the whole plan.
**Source:** `docs/issues-and-bugs/open/phase-2-production-testing-issues.docx` (all 14 issues); `docs/phases/phase-3-planned/phase-3-author-centric-ai-workflow.md` §7.4 (PRE-1, PRE-2)
**Parallelism:** Tasks 3.1–3.13 are largely independent. Suggested split — backend A: 3.1–3.5; backend B: 3.6, 3.7, 3.12; frontend: 3.8–3.11.

---

- [ ] **3.1 — PRE-1: fix the retrieval call signatures in `writing_tools.py`**
  - **Source:** Phase 3 spec §7.4 (PRE-1); Phase 2 issues **12** (outline) and **13** (continuation)
  - **Area:** Backend
  - **Priority:** Critical
  - **Depends on:** Stage 2
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Context — verified in code:** `writing_tools.py:94, 106, 180, 191` pass `query=`. `retrieve_relevant_chunks()` takes `question` first (`ai_service.py:3305`); `retrieve_character_context()` takes `(story_id, question, db, …)` (`ai_service.py:1113`). Both raise `TypeError: unexpected keyword argument 'query'` at runtime. This is the whole reason outline and continuation fail — **not** an AI-output problem. Additionally `retrieve_character_context` returns `list[str]` but is passed to `generate_continuations(character_context=…)` as if it were a string.
  - **Implementation checklist:**
    - [ ] Fix `writing_tools.py:94` — `query=` → `question=`
    - [ ] Fix `writing_tools.py:106` — correct keyword and argument order
    - [ ] Fix `writing_tools.py:180` — `query=` → `question=`
    - [ ] Fix `writing_tools.py:191` — correct keyword and argument order
    - [ ] Join the character context: `"\n\n".join(...)` before passing to `generate_continuations` and `generate_chapter_outline`
    - [ ] Grep the whole backend for any other `retrieve_*(query=` call site
  - **Verification:**
    - [ ] Add `backend/tests/test_retrieval_signatures.py` asserting the call signatures (named in Phase 3 spec §3579 as the PRE-1 regression guard)
    - [ ] Manually run chapter continuation — 3 options returned
    - [ ] Manually run scene outline — beat sheet returned
    - [ ] Confirm character context reaches the prompt as text, not as a list repr
  - **Definition of done:** Phase 2 Issues 12 and 13 are closed, with a regression test that makes this class of error impossible to reintroduce silently.

- [ ] **3.2 — Story Bible status integrity**
  - **Source:** Phase 2 Issue 8 (partial); `README.md` known issue 2; `backend/routers/story_bible.py:136–147`
  - **Area:** Backend / Database
  - **Priority:** Critical
  - **Depends on:** Stage 2
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Context — verified in code:** On `AIServiceUnavailableError` the section body becomes `"[AI temporarily unavailable — please regenerate]"`; on any other exception, `f"[Error generating {section}: {exc}]"`. Control then falls through to `:145–147` which sets `status = "completed"` and commits.
  - **Implementation checklist:**
    - [ ] Enumerate every section-generation failure path in `_generate_bible_background`
    - [ ] Track per-section success/failure during generation
    - [ ] Set status to `partial` when some sections failed, `failed` when all failed, `completed` only when all succeeded
    - [ ] Add a `failed_sections` field so the UI can offer targeted regeneration
    - [ ] Never persist a placeholder string as if it were content
    - [ ] Surface partial state in `StoryBiblePanel.tsx` with a per-section retry
  - **Verification:**
    - [ ] Unit test: force one section to raise; assert status is `partial`, never `completed`
    - [ ] Unit test: force all sections to raise; assert status is `failed`
    - [ ] Database-state check: no `story_bibles` row with `status='completed'` contains a `[` placeholder marker
    - [ ] Re-run the reported QA scenario
  - **Definition of done:** A bible marked `completed` contains only genuinely generated content.

- [ ] **3.3 — Story Bible grounding and provenance**
  - **Source:** Phase 2 Issue **8** (Critical); Master Execution Plan §5.2
  - **Area:** AI / Backend
  - **Priority:** Critical
  - **Depends on:** 3.2
  - **Blocked by:** None
  - **Can run in parallel:** No — same module as 3.2
  - **Context — verified in code:** The prompt at `ai_service.py:3646–3650` already says *"ground everything in what is actually in the text. Do not invent details not supported by the provided context."* The defect is **context starvation**: `_build_full_context()` assembles from chapter summaries truncated to **300 characters each**. The model is asked for a comprehensive timeline while shown a compressed digest, so it interpolates. Prompt-only fixes will not resolve this.
  - **Implementation checklist:**
    - [ ] Raise the per-summary character budget in `_build_full_context()` and measure the resulting token count
    - [ ] Add chapter provenance to every context entry so the model can cite it
    - [ ] Require each bible entry to carry a source chapter reference
    - [ ] Add an explicit "not established in the manuscript" output convention instead of gap-filling
    - [ ] Add a post-generation check flagging timeline events with no chapter reference
    - [ ] Handle context-window limits — chunk or summarise rather than truncate silently
  - **Verification:**
    - [ ] AI-output validation: generate a bible on a fixture manuscript with known content; assert zero events absent from the source
    - [ ] Assert every bible entry carries provenance
    - [ ] Author review confirms no unsupported detail
  - **Definition of done:** The Story Bible states only what the manuscript supports, and marks uncertainty explicitly.

- [ ] **3.4 — Degraded-output contract for AI features**
  - **Source:** Phase 2 Issues **2** (plot holes) and **14** (continuity); Master Execution Plan §5.3
  - **Area:** AI / Backend
  - **Priority:** High
  - **Depends on:** Stage 2
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Context — verified in code:** `_extract_json()` (`ai_service.py:272–310`) is already robust — clean parse → fence strip → all balanced spans → trailing-comma repair. The failure is at the caller: `ai_service.py:1589–1594` raises `ValueError` when the schema does not match. Confirmed that `plot_holes.py` and `analysis.py` do **not** use retrieval helpers, so these two issues are genuinely the schema class, unlike Issues 12/13.
  - **Implementation checklist:**
    - [ ] Define the degraded-output contract: coerce → one bounded reprompt → partial result with `degraded: true`
    - [ ] Replace the `raise ValueError` at `ai_service.py:1591–1594` with the contract
    - [ ] Apply the contract to continuity analysis
    - [ ] Return partial findings rather than nothing when only some entries parse
    - [ ] Surface `degraded: true` in the UI as an honest partial-result banner
    - [ ] Ensure a genuine failure returns an actionable message, never a raw stack trace
  - **Verification:**
    - [ ] Unit test with deliberately malformed model output — asserts partial result, not exception
    - [ ] Manually run plot hole detection — usable results returned
    - [ ] Manually run continuity analysis — usable results returned
  - **Definition of done:** Phase 2 Issues 2 and 14 are closed; no AI feature returns nothing when it could return something.

- [ ] **3.5 — Audit every `_extract_json` caller for the hard-fail pattern**
  - **Source:** Master Execution Plan §5.3 recommendation
  - **Area:** AI / Backend
  - **Priority:** High
  - **Depends on:** 3.4
  - **Blocked by:** None
  - **Can run in parallel:** No
  - **Context:** The four reported features are a sample, not the population. Establish the true scope before declaring the class fixed.
  - **Implementation checklist:**
    - [ ] Grep every `_extract_json` call site in `ai_service.py` and the routers
    - [ ] Classify each as hard-fail / silent-fallback / handled
    - [ ] Apply the 3.4 contract to every hard-fail site
    - [ ] Flag every silent-fallback site — a silent empty result is its own defect class
    - [ ] Record the audit result in the tracker
  - **Verification:**
    - [ ] Every call site has a recorded classification and a handled outcome
  - **Definition of done:** No AI feature can fail opaquely on model output shape.

- [ ] **3.6 — Voice agent action execution**
  - **Source:** Phase 2 Issue **4** (High)
  - **Area:** Backend / AI
  - **Priority:** High
  - **Depends on:** Stage 2
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Trace transcription → intent → planner → orchestrator → adapter for a failing utterance
    - [ ] Identify where intent resolution or routing drops the request
    - [ ] Fix intent classification for the reported utterance classes
    - [ ] Ensure every resolved intent maps to a real capability in `capabilities.py` / `catalog.py`
    - [ ] Return an explicit "I could not map that request" instead of silently doing nothing
  - **Verification:**
    - [ ] Integration test per supported voice intent asserting the correct adapter is invoked
    - [ ] Manual: "create a chapter called Storm" actually creates the chapter
    - [ ] Database-state check confirming the mutation occurred
  - **Definition of done:** A recognised utterance either executes the correct action or explains why it cannot.

- [ ] **3.7 — Voice agent success reporting must reflect reality**
  - **Source:** Phase 2 Issue **5** (High)
  - **Area:** Backend
  - **Priority:** High
  - **Depends on:** 3.6
  - **Blocked by:** None
  - **Can run in parallel:** No — same subsystem
  - **Context:** A false success is worse than an honest failure — the author believes their data changed when it did not.
  - **Implementation checklist:**
    - [ ] Derive the success message from the adapter's actual return value, never from plan completion
    - [ ] Treat a `None` or error adapter result as failure
    - [ ] Ensure `_summarize_result` cannot report success on an empty result
    - [ ] Return a specific failure reason to the user
    - [ ] Audit `awaiting_confirmation` transitions for the same assumption
  - **Verification:**
    - [ ] Integration test: force an adapter failure, assert the user-facing message reports failure
    - [ ] Database-state check: no success message without a corresponding data change
  - **Definition of done:** The voice agent never claims an action succeeded unless it did.

- [ ] **3.8 — PRE-2: selection toolbar lifecycle and sidebar deference**
  - **Source:** Phase 2 Issues **1** and **11**; Phase 3 spec §7.4 (PRE-2)
  - **Area:** Frontend
  - **Priority:** High
  - **Depends on:** Stage 2
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Context:** Fix both issues together — same component, contradictory required behaviours. Phase 3A rewrites this component substantially (pin, regenerate, lock, compare), so fixing the lifecycle now avoids fixing it twice. Phase 3 decision **D7** recommends folding these together.
  - **Implementation checklist:**
    - [ ] `SelectionToolbar.tsx` — dismiss immediately on deselection
    - [ ] Suppress the toolbar entirely while the AI Assistant sidebar is open
    - [ ] Ensure the toolbar never overlays essential editor controls
    - [ ] Evaluate making it draggable (reported as desirable, not required)
    - [ ] Verify a single consistent interaction flow for selection-based AI actions
  - **Verification:**
    - [ ] Playwright test: select → toolbar appears; deselect → toolbar disappears
    - [ ] Playwright test: sidebar open → toolbar suppressed
    - [ ] Manual check against the reported QA scenario
  - **Definition of done:** Exactly one interface handles a text selection at any moment.

- [ ] **3.9 — Writing analytics page scrolling**
  - **Source:** Phase 2 Issue **3** (Medium)
  - **Area:** Frontend
  - **Priority:** Medium
  - **Depends on:** Stage 2
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Identify the container preventing vertical overflow on the analytics view
    - [ ] Apply correct overflow handling so all sections are reachable
    - [ ] Verify at narrow and short viewport sizes
    - [ ] Confirm future analytics sections remain reachable as content grows
  - **Verification:**
    - [ ] Playwright test asserting the last analytics section is scrollable into view
    - [ ] Manual check at 1366×768 and smaller
  - **Definition of done:** All analytics content is accessible at any viewport size.

- [ ] **3.10 — OCR upload interface renders**
  - **Source:** Phase 2 Issue **6** (High)
  - **Area:** Frontend
  - **Priority:** High
  - **Depends on:** Stage 2
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Context:** `frontend/components/ocr/OCRPanel.tsx` exists — diagnose why it renders empty rather than assuming the feature is unbuilt.
  - **Implementation checklist:**
    - [ ] Reproduce the empty panel and capture the browser console error
    - [ ] Check whether the dynamic import or a data fetch fails
    - [ ] Fix the render path so the file upload control appears
    - [ ] Verify supported formats are accepted
    - [ ] Verify extracted text can be reviewed and injected into all four destinations
  - **Verification:**
    - [ ] Playwright test: OCR panel renders an upload control
    - [ ] Manual end-to-end: upload an image → text extracted → injected into the editor
  - **Definition of done:** The full OCR workflow is reachable from the UI.

- [ ] **3.11 — Notes module load reliability**
  - **Source:** Phase 2 Issue **7** (Medium–High)
  - **Area:** Frontend / Backend
  - **Priority:** High
  - **Depends on:** Stage 2
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Context:** Intermittent — notes fail to load, then appear on a later visit. Diagnose as a race or cache-invalidation defect; a retry wrapper would mask it.
  - **Implementation checklist:**
    - [ ] Reproduce and capture whether the API call fails or returns empty
    - [ ] Check for a race between panel mount and story context readiness
    - [ ] Check client-side cache invalidation on navigation
    - [ ] Fix the underlying cause, not the symptom
    - [ ] Add an explicit loading state distinct from an empty state
  - **Verification:**
    - [ ] Playwright test navigating away and back repeatedly, asserting notes load every time
    - [ ] Confirm the API returns consistent results under repeated calls
  - **Definition of done:** Notes load on first attempt every time.

- [ ] **3.12 — Character recognition synchronisation**
  - **Source:** Phase 2 Issue **9**; Phase 1 Cast Generation Critical 1, 2 and High 5
  - **Area:** Backend / Frontend / Database
  - **Priority:** High
  - **Depends on:** Stage 2
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Note:** Deliberately started here rather than Stage 4 because it is a data-integrity defect the author sees immediately. The deeper alias and dedup work continues in tasks 4.6–4.9.
  - **Implementation checklist:**
    - [ ] Remove a name from the unresolved queue when it is added, matched or merged
    - [ ] Refresh the unrecognised-names queue after cast generation
    - [ ] Ensure the mention-to-character link is written at match time
    - [ ] Ensure the frontend re-fetches after a character mutation
  - **Verification:**
    - [ ] Integration test: add a character, assert it leaves the unresolved list
    - [ ] Database-state check: no name simultaneously in `characters` and unresolved
    - [ ] Manual check against the reported QA scenario
  - **Definition of done:** A character never appears as both recognised and unrecognised.

- [ ] **3.13 — Notes and Narrative Threads navigation duplication**
  - **Source:** Phase 2 Issue **10** (Medium); Phase 1 Editor UI Medium 16
  - **Area:** Frontend
  - **Priority:** Low
  - **Depends on:** None
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - > **Deferred from Phase 2 defect resolution to Stage 8 to avoid duplicate implementation.** The information architecture is being rebuilt in the workspace redesign; fixing navigation placement twice is waste. Phase 3 decision **D10** (Idea Shelf placement) also lands in the same surface. Tracked here so the issue is not lost — implemented as task **8.8**.
  - **Implementation checklist:**
    - [ ] Confirm the issue is carried into task 8.8 with both source references
  - **Verification:**
    - [ ] Task 8.8 explicitly closes Phase 2 Issue 10
  - **Definition of done:** Deferral is recorded and traceable; no work performed in this stage.

### Stage 3 Completion Gate

- [ ] All 14 Phase 2 issues closed or explicitly deferred with a recorded destination
- [ ] Chapter continuation, scene outline, plot hole detection and continuity analysis all return usable results
- [ ] Story Bible never reports `completed` on partial content
- [ ] Story Bible contains no unsupported detail, verified against a fixture
- [ ] Voice agent never reports false success
- [ ] Regression tests added for tasks 3.1–3.7
- [ ] `_extract_json` caller audit complete
- [ ] **Gate 2 — Core workflows functional** passed

---

# Stage 4 — Phase 1 Retrieval and Data Correctness

**Entry condition:** Stage 3 gate passed; **D-1 recorded**.
**Why here:** Retrieval is the foundation every AI feature stands on. Tuning prompts while retrieval returns the wrong chapters produces confident, well-written, wrong answers.
**Source:** `docs/issues-and-bugs/open/phase-1-ai-writing-tools-qa-issues.docx` — Plot Assistant (16), Cast Generation & Character Management (14), Search Module ×2 (9 + 12). **51 issues.**
**Parallelism:** Search (4.10–4.14) and Character (4.6–4.9) are **not** blocked by D-1 and should start immediately. Plot Assistant tasks are strictly sequential — one owner on the `ai_service.py` retrieval region.

---

- [ ] **4.1 — Implement the approved Plot Assistant retrieval scope**
  - **Source:** Plot Assistant Critical **1**, **2**, **5**, **9**; High **11**
  - **Area:** AI / Backend
  - **Priority:** Critical
  - **Depends on:** Stage 3
  - **Blocked by:** **D-1**
  - **Can run in parallel:** No
  - **Implementation checklist:**
    - [ ] Apply the D-1 decision at `plot_assistant.py:90` and `:138`
    - [ ] If option (b): add a scope parameter to the request schema and a UI toggle
    - [ ] Ensure `retrieve_relevant_chunks` and `retrieve_chunks_from_store` honour the chosen scope
    - [ ] Ensure `retrieve_character_context` uses the same scope rule
    - [ ] Make the active scope visible in the UI — silent limiting is the root defect
  - **Verification:**
    - [ ] Integration test on a multi-chapter fixture: a question about a late chapter returns late-chapter evidence under story-wide scope
    - [ ] Integration test: capped scope excludes later chapters as designed
    - [ ] Manual: ask a whole-story question from Chapter 1 and confirm correct behaviour
  - **Definition of done:** Retrieval scope matches the approved product decision and is visible to the author.

- [ ] **4.2 — Tune retrieval breadth and context budget**
  - **Source:** Plot Assistant Critical **3**; High **11**
  - **Area:** AI / Backend
  - **Priority:** High
  - **Depends on:** 4.1
  - **Blocked by:** **D-1**
  - **Can run in parallel:** No
  - **Context:** `top_k=4` for suggestions, `top_k=5` with character context, `top_k=8` otherwise — thin for story-wide questions.
  - **Implementation checklist:**
    - [ ] Measure recall at current `top_k` values on a fixture with known answers
    - [ ] Raise `top_k` and re-measure against the context-window limit
    - [ ] Rebalance the 800-token character budget against the chunk budget
    - [ ] Confirm the total prompt stays within the verified `max-model-len` from task 1.6
    - [ ] Ensure character retrieval returns evidence for characters that appear late in the manuscript
  - **Verification:**
    - [ ] Recall measured before and after; improvement demonstrated
    - [ ] No prompt exceeds the context window under worst-case assembly
  - **Definition of done:** Retrieval returns enough evidence to answer story-wide questions without overflowing context.

- [ ] **4.3 — Context prioritisation and ranking**
  - **Source:** Plot Assistant Critical **6**, **7**; High **12**
  - **Area:** AI / Backend
  - **Priority:** High
  - **Depends on:** 4.2
  - **Blocked by:** **D-1**
  - **Can run in parallel:** No
  - **Implementation checklist:**
    - [ ] Review the hybrid ranking — cosine similarity plus name-mention boost (`ai_service.py:1187`)
    - [ ] Ensure plot-critical passages outrank incidental mentions
    - [ ] Fix cases where information present in the manuscript is reported as missing
    - [ ] Add plot-importance weighting to ranking
  - **Verification:**
    - [ ] Fixture test: known plot-critical passages appear in the top results
    - [ ] Fixture test: no "not in the story" answer for a fact that is in the story
  - **Definition of done:** The highest-ranked evidence is the most relevant evidence.

- [ ] **4.4 — Distinguish retrieval failure from knowledge failure**
  - **Source:** Plot Assistant Critical **7**, **8**
  - **Area:** AI / Backend
  - **Priority:** High
  - **Depends on:** 4.3
  - **Blocked by:** **D-1**
  - **Can run in parallel:** No
  - **Context:** The system must tell the author *"I did not find this"* versus *"this is not established in your story"*. Conflating the two destroys trust in every negative answer.
  - **Implementation checklist:**
    - [ ] Return retrieval metadata — chunk count, chapter coverage — alongside the answer
    - [ ] Instruct the model to distinguish the two cases explicitly in its answer
    - [ ] Surface the distinction in the UI
    - [ ] Report when scope limiting (D-1) caused an empty result
  - **Verification:**
    - [ ] Fixture test: a fact outside the retrieved scope yields "not found in the searched range", never "not in your story"
  - **Definition of done:** Negative answers are honest about their cause.

- [ ] **4.5 — Chapter summary depth and coverage**
  - **Source:** Plot Assistant High **10**, **13**, **14**; Medium **15**, **16**
  - **Area:** AI / Backend
  - **Priority:** Medium
  - **Depends on:** 4.3
  - **Blocked by:** **D-1**
  - **Can run in parallel:** Yes
  - **Context:** Also improves Story Bible grounding (task 3.3), which consumes the same summaries.
  - **Implementation checklist:**
    - [ ] Ensure major story revelations are captured in `ChapterSummary`
    - [ ] Capture character arc progression per chapter
    - [ ] Capture emotional arc signal in summaries
    - [ ] Capture relationship state changes
    - [ ] Strengthen the story-reasoning layer over summaries
    - [ ] Re-index existing chapters via `POST /api/stories/{id}/chapters/sync-summaries`
  - **Verification:**
    - [ ] Fixture test: known revelations appear in the generated summaries
    - [ ] Re-indexing completes without error on an existing story
  - **Definition of done:** Summaries carry enough signal for story-wide reasoning.

- [ ] **4.6 — Character alias resolution**
  - **Source:** Plot Assistant Critical **4**; Cast Generation Critical **3**
  - **Area:** Backend / AI
  - **Priority:** High
  - **Depends on:** Stage 3
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Support nicknames, titles, surnames and epithets mapping to one character
    - [ ] Store aliases against the character record
    - [ ] Apply alias matching in retrieval name-mention boosting
    - [ ] Apply alias matching in mention detection
  - **Verification:**
    - [ ] Fixture test: a query using an alias retrieves the correct character's context
    - [ ] Database-state check: aliases persist against the right character
  - **Definition of done:** One character with several names is treated as one character everywhere.

- [ ] **4.7 — Cast generation synchronisation**
  - **Source:** Cast Generation Critical **1**, **2**; High **5**
  - **Area:** Backend / Frontend
  - **Priority:** High
  - **Depends on:** 3.12
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Make cast generation and unrecognised-name detection read one consistent state
    - [ ] Refresh the unrecognised queue transactionally after cast generation
    - [ ] Prevent stale queue entries surviving a page refresh
  - **Verification:**
    - [ ] Integration test: generate cast, assert the unresolved queue reflects the result immediately
  - **Definition of done:** Cast generation leaves the character state internally consistent.

- [ ] **4.8 — Character deduplication and consolidation**
  - **Source:** Cast Generation Critical **4**; Medium **13**, **14**
  - **Area:** Backend / Database
  - **Priority:** High
  - **Depends on:** 4.6
  - **Blocked by:** None
  - **Can run in parallel:** No — depends on aliases
  - **Implementation checklist:**
    - [ ] Detect duplicate character records created across chapters
    - [ ] Provide a merge operation preserving both records' data
    - [ ] Consolidate fragmented character memory story-wide
    - [ ] Ensure merges re-embed the surviving profile
  - **Verification:**
    - [ ] Integration test: create a duplicate, merge, assert one record with combined data
    - [ ] Database-state check: no orphaned relationships after a merge
  - **Definition of done:** Each character exists exactly once with complete story-wide memory.

- [ ] **4.9 — Character classification and relationship accuracy**
  - **Source:** Cast Generation High **6**, **7**, **8**, **9**, **10**; Medium **11**, **12**
  - **Area:** AI / Backend
  - **Priority:** Medium
  - **Depends on:** 4.8
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Improve role classification accuracy
    - [ ] Improve importance ranking so minor characters are not promoted
    - [ ] Fix relationship extraction errors
    - [ ] Make character description generation consistent across runs
    - [ ] Fix mention classification errors
    - [ ] Fix mention-to-character linking failures
  - **Verification:**
    - [ ] Fixture test with known cast: roles, importance and relationships match ground truth within an agreed tolerance
  - **Definition of done:** Character metadata is accurate enough for authors to rely on without correcting it.

- [ ] **4.10 — Search query truncation and full-term matching**
  - **Source:** Search Module report 1 Critical **1**, **2**, **3**; Search Module report 2 Critical **1**, **2** *(merged — the two sub-reports duplicate these)*
  - **Area:** Backend
  - **Priority:** Critical
  - **Depends on:** Stage 3
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Find where the query string is truncated before matching
    - [ ] Fix character-level matching so full terms are matched as terms
    - [ ] Make query processing consistent between semantic and exact modes
    - [ ] Handle multi-word queries correctly
  - **Verification:**
    - [ ] Unit test: a multi-word query matches the full phrase, not its first character
    - [ ] Fixture test: known term occurrences are all found
  - **Definition of done:** A search for a term finds that term, complete and correct.

- [ ] **4.11 — Search match counting and highlighting**
  - **Source:** Search report 1 Critical **4**, High **5**; Search report 2 High **4**, **5** *(merged)*
  - **Area:** Backend / Frontend
  - **Priority:** High
  - **Depends on:** 4.10
  - **Blocked by:** None
  - **Can run in parallel:** No
  - **Implementation checklist:**
    - [ ] Fix the match count to reflect actual occurrences
    - [ ] Fix highlighting to mark the correct spans
    - [ ] Ensure counts and highlights agree with each other
  - **Verification:**
    - [ ] Unit test asserting exact match counts on a fixture with a known occurrence count
    - [ ] Playwright test asserting the highlighted span matches the query
  - **Definition of done:** Reported counts and visible highlights are both correct and consistent.

- [ ] **4.12 — Exact search mode correctness**
  - **Source:** Search report 1 High **6**; Search report 2 Critical **3**, High **6** *(merged)*
  - **Area:** Backend
  - **Priority:** High
  - **Depends on:** 4.10
  - **Blocked by:** None
  - **Can run in parallel:** No
  - **Implementation checklist:**
    - [ ] Make exact mode respect the full query string
    - [ ] Remove semantic behaviour leaking into exact mode
    - [ ] Verify search-and-replace operates on exact matches only
  - **Verification:**
    - [ ] Unit test: exact mode returns only literal matches
    - [ ] Manual: search "Devika", replace one occurrence, confirm only that occurrence changed
  - **Definition of done:** Exact mode is literal and predictable.

- [ ] **4.13 — Semantic search deduplication and diversity**
  - **Source:** Search report 2 High **7**, **8**; Medium **9**, **10**
  - **Area:** Backend
  - **Priority:** Medium
  - **Depends on:** 4.10
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Context:** Chapter chunks use 350-word overlap, so overlapping chunks legitimately contain the same text — dedup must operate on content, not chunk ID.
  - **Implementation checklist:**
    - [ ] Deduplicate results that overlap due to chunk overlap
    - [ ] Fix duplicate semantic results
    - [ ] Improve result diversity so one passage does not fill the result set
  - **Verification:**
    - [ ] Fixture test: no two results contain substantially the same text
  - **Definition of done:** Each result adds new information.

- [ ] **4.14 — Search relevance, ranking and stability**
  - **Source:** Search report 1 High **7**, Medium **8**, **9**; Search report 2 Medium **11**, **12**
  - **Area:** Backend
  - **Priority:** Medium
  - **Depends on:** 4.13
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Fix relevance degradation on longer queries
    - [ ] Make behaviour consistent between the two search engines
    - [ ] Review regex and tokenisation handling for special characters
    - [ ] Stabilise query processing so repeated identical queries return identical results
    - [ ] Optimise result ranking
  - **Verification:**
    - [ ] Fixture test: identical queries return identical ordered results across runs
    - [ ] Special-character queries do not error
  - **Definition of done:** Search is deterministic, consistent and relevant.

- [ ] **4.15 — Retrieval regression suite**
  - **Source:** Master Execution Plan §11.5; Gate 3a
  - **Area:** Testing
  - **Priority:** High
  - **Depends on:** 4.1–4.14
  - **Blocked by:** **D-1**
  - **Can run in parallel:** No
  - **Implementation checklist:**
    - [ ] Build a fixed multi-chapter fixture manuscript with documented ground truth
    - [ ] Write known-answer retrieval assertions per chapter
    - [ ] Write character-retrieval assertions including aliases
    - [ ] Write search assertions with exact expected counts
    - [ ] Wire the suite into CI (task 6.1)
  - **Verification:**
    - [ ] Suite passes; reintroducing a Stage 4 defect turns it red
  - **Definition of done:** Retrieval correctness is permanently guarded by tests.

### Stage 4 Completion Gate

- [ ] All 16 Plot Assistant issues closed or accepted
- [ ] All 14 Cast Generation & Character Management issues closed or accepted
- [ ] All 21 Search issues (both sub-reports, merged) closed or accepted
- [ ] Retrieval scope matches the D-1 decision and is visible in the UI
- [ ] Retrieval regression suite green in CI
- [ ] No character appears as both recognised and unrecognised
- [ ] **Gate 3a — Retrieval correct** passed

---

# Stage 5 — Phase 1 AI Generation Quality

**Entry condition:** Stage 4 gate passed; **D-5 recorded**.
**Why here:** This is the product's core value and its largest defect cluster. It follows retrieval because continuity and suggestion quality depend on retrieved context; it precedes Phase 3 because Phase 3 builds on the generation loop.
**Source:** `docs/issues-and-bugs/open/phase-1-ai-writing-tools-qa-issues.docx` — AI Writing Tools (38 + 10 cross-module), AI Suggestions (16), Story Audit (15), Writing Analytics (6). **85 issues.**

> **Tasks 5.3 and 5.4 implement Phase 3 capabilities P3-05 and P3-02 early**, per Master Execution Plan §7.3 and decision **D-5**. They are the designed fix for the 48-issue author-voice cluster. Do not implement them again in Stage 7 — task 7.3 verifies them instead.

---

- [ ] **5.1 — Prompt versioning registry**
  - **Source:** Production gap **PG-08**
  - **Area:** AI / Backend
  - **Priority:** High
  - **Depends on:** Stage 4
  - **Blocked by:** None
  - **Can run in parallel:** No — **must land before any other Stage 5 task**
  - **Context:** Stage 5 changes prompts at scale. Without versioning, quality regressions become untraceable and unrevertible.
  - **Implementation checklist:**
    - [ ] Extract inline prompts from `ai_service.py` into a versioned registry
    - [ ] Assign a version identifier to each prompt
    - [ ] Log the prompt version with every generation
    - [ ] Make the active version configurable for A/B comparison
    - [ ] Record the current prompts as the baseline version
  - **Verification:**
    - [ ] A generation log entry identifies exactly which prompt version produced it
    - [ ] Reverting to the baseline version is a config change, not a code change
  - **Definition of done:** Every generation is traceable to a specific prompt version.

- [ ] **5.2 — AI quality golden set and baseline measurement**
  - **Source:** Master Execution Plan §11.4; Gate 3b
  - **Area:** AI / Testing
  - **Priority:** Critical
  - **Depends on:** 5.1
  - **Blocked by:** None
  - **Can run in parallel:** No
  - **Context:** Gate 3b requires *measured* improvement. Without a baseline captured before changes, "better" is unprovable.
  - **Implementation checklist:**
    - [ ] Assemble N author passages spanning genres and styles
    - [ ] Define M transform scenarios (tone, emotion, audience, style, translation)
    - [ ] Define the voice-preservation scoring method
    - [ ] Define the unnecessary-change rate metric — edit distance on passages needing no change
    - [ ] Define the genre-drift metric
    - [ ] Define the continuity false-positive rate metric
    - [ ] Run and record the **baseline** against the current prompt version
  - **Verification:**
    - [ ] Baseline numbers recorded and reproducible
  - **Definition of done:** A measurable quality baseline exists before any prompt changes.

- [ ] **5.3 — Preservation rules (implements P3-05 early)**
  - **Source:** AI Writing Tools Critical **A**, **B**, **D**, **I**, **J**; Issues 1.1, 1.4, 4.7, 4.10; `docs/phases/phase-3-planned/phase-3-author-centric-ai-workflow.md` §P3-05, §25.3
  - **Area:** AI / Backend / Database / Frontend
  - **Priority:** Critical
  - **Depends on:** 5.2
  - **Blocked by:** **D-5**
  - **Can run in parallel:** No
  - **Implementation checklist:**
    - [ ] Design confirmation against Phase 3 spec §P3-05
    - [ ] Create the preservation-rules table and migration
    - [ ] Implement rule entry — "do not change character names", "do not change tone", author-defined rules
    - [ ] Inject enumerated constraints plus real character names into the prompt per §12.3 budgeting
    - [ ] Implement the deterministic post-generation checks in §25.3
    - [ ] Implement the one repair retry on violation
    - [ ] Surface preservation warnings in the UI
    - [ ] Establish the preservation hierarchy: author voice → narrative style → genre identity → character voice → emotional subtext → literary quality → story intent
  - **Verification:**
    - [ ] Unit tests for each deterministic check
    - [ ] Golden-set measurement: voice-preservation score improves over the 5.2 baseline
    - [ ] Rule violations are detected, not merely requested
  - **Definition of done:** Author-defined constraints are enforced by a post-check, not just asked for in a prompt.

- [ ] **5.4 — Sentence-level lock and partial regeneration (implements P3-02 early)**
  - **Source:** AI Writing Tools Issues **1.2**, **1.6**, **3.4**, **4.2**; Phase 3 spec §P3-02, §9.2, §24.1
  - **Area:** AI / Backend / Frontend
  - **Priority:** Critical
  - **Depends on:** 5.3
  - **Blocked by:** **D-5**
  - **Can run in parallel:** No
  - **Implementation checklist:**
    - [ ] Design confirmation against Phase 3 spec §P3-02
    - [ ] Implement segment model — one sentence per lockable segment
    - [ ] Implement `[KEEP]` / `[REWRITE]` segment marking per §1516
    - [ ] Ensure `[KEEP]` segments are never emitted by the model
    - [ ] Validate index-set equality and per-segment non-emptiness on return
    - [ ] Implement the retry ladder: one stricter retry → per-segment fallback → 502
    - [ ] Add lock controls to `SelectionToolbar.tsx` (coordinate with task 3.8)
  - **Verification:**
    - [ ] **Assert byte-identity of locked segments across regeneration** (§24.1) — locked text must be guaranteed, not requested
    - [ ] Golden-set measurement: unnecessary-change rate falls versus baseline
  - **Definition of done:** An author can lock a sentence and regenerate around it with a byte-level guarantee.

- [ ] **5.5 — "No change required" decision layer**
  - **Source:** AI Writing Tools Critical **C**; Issues **1.7**, **3.4**, **3.6**, **3.7**, **4.8**
  - **Area:** AI / Backend
  - **Priority:** Critical
  - **Depends on:** 5.3
  - **Blocked by:** None
  - **Can run in parallel:** No
  - **Context:** The system currently always rewrites. It must be able to conclude that text already satisfies the request.
  - **Implementation checklist:**
    - [ ] Add a pre-transform assessment step per transform type
    - [ ] Implement audience-suitability detection (3.6)
    - [ ] Implement style detection so an already-matching style is not restyled (4.8)
    - [ ] Implement a minimal-change mode (1.7, 3.7)
    - [ ] Return the original text unchanged when no change is warranted, with an explanation
  - **Verification:**
    - [ ] Golden-set: passages needing no change return byte-identical text
    - [ ] Unnecessary-change rate approaches zero on the no-change subset
  - **Definition of done:** Requesting a transform on already-suitable text returns it unchanged.

- [ ] **5.6 — Transformation strength control**
  - **Source:** AI Writing Tools Issue **4.3**; Critical **I** (editing vs rewriting mismatch)
  - **Area:** AI / Backend / Frontend
  - **Priority:** High
  - **Depends on:** 5.5
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Add a strength parameter to transform endpoints
    - [ ] Make "adjust" and "rewrite" distinct operations at the prompt level
    - [ ] Expose the control in the transform UI
    - [ ] Default to the lower-intervention setting
  - **Verification:**
    - [ ] Golden-set: low strength produces measurably smaller edit distance than high strength
  - **Definition of done:** The author controls how much the AI is allowed to change.

- [ ] **5.7 — Tone transformation issues**
  - **Source:** AI Writing Tools Category 1 — Issues **1.1**–**1.6** *(1.7 covered by 5.5)*
  - **Area:** AI
  - **Priority:** High
  - **Depends on:** 5.3, 5.5
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] 1.1 Author voice preservation on tone change
    - [ ] 1.2 Stop excessive content rewriting
    - [ ] 1.3 Prevent genre drift during tone changes
    - [ ] 1.4 Stop narrative style replacement
    - [ ] 1.5 Stop unnecessary metaphor and imagery injection
    - [ ] 1.6 Make tonal adjustments targeted, not broad
  - **Verification:**
    - [ ] Golden-set tone scenarios re-measured against baseline
    - [ ] Author review on tone transforms
  - **Definition of done:** Tone changes adjust tone and nothing else.

- [ ] **5.8 — Emotion transformation issues**
  - **Source:** AI Writing Tools Category 2 — Issues **2.1**–**2.7**
  - **Area:** AI
  - **Priority:** High
  - **Depends on:** 5.3, 5.5
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] 2.1 Stop emotional over-explanation
    - [ ] 2.2 Preserve emotional subtext
    - [ ] 2.3 Preserve emotional nuance
    - [ ] 2.4 Make intensity levels match output strength
    - [ ] 2.5 Differentiate emotion categories meaningfully
    - [ ] 2.6 Remove generic emotional templates
    - [ ] 2.7 Preserve authorial emotional restraint
  - **Verification:**
    - [ ] Golden-set emotion scenarios re-measured
    - [ ] Distinct emotions produce measurably distinct outputs
  - **Definition of done:** Emotional transforms preserve subtlety and differentiate correctly.

- [ ] **5.9 — Audience adaptation issues**
  - **Source:** AI Writing Tools Category 3 — Issues **3.1**–**3.5** *(3.6, 3.7 covered by 5.5)*
  - **Area:** AI
  - **Priority:** High
  - **Depends on:** 5.3, 5.5
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] 3.1 Preserve genre atmosphere during adaptation
    - [ ] 3.2 Preserve emotional depth
    - [ ] 3.3 Prevent character perspective and age drift
    - [ ] 3.4 Stop rewriting already-suitable content
    - [ ] 3.5 Prevent literary quality regression
  - **Verification:**
    - [ ] Golden-set audience scenarios re-measured
  - **Definition of done:** Audience adaptation changes reading level without degrading the writing.

- [ ] **5.10 — Style transformation issues**
  - **Source:** AI Writing Tools Category 4 — Issues **4.1**, **4.2**, **4.4**, **4.5**, **4.6**, **4.7**, **4.9**, **4.10** *(4.3 covered by 5.6, 4.8 by 5.5)*
  - **Area:** AI
  - **Priority:** High
  - **Depends on:** 5.3, 5.5, 5.6
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] 4.1 Apply style by editing, not rewriting
    - [ ] 4.2 Stop unnecessary word and phrase replacement
    - [ ] 4.4 Stop genre trope exaggeration
    - [ ] 4.5 Remove style stereotype dependency
    - [ ] 4.6 Stop introducing new content
    - [ ] 4.7 Stop modifying character voice
    - [ ] 4.9 Prevent literary style degradation
    - [ ] 4.10 Prevent author identity erosion
  - **Verification:**
    - [ ] Golden-set style scenarios re-measured
    - [ ] Author identity preserved under blind review
  - **Definition of done:** Style transforms apply a style without overwriting the author.

- [ ] **5.11 — Translation issues**
  - **Source:** AI Writing Tools Category 5 — Issues **5.1**–**5.7**
  - **Area:** AI
  - **Priority:** Medium
  - **Depends on:** 5.3
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] 5.1 Translate rather than interpret
    - [ ] 5.2 Preserve literary voice across languages
    - [ ] 5.3 Preserve imagery
    - [ ] 5.4 Improve natural language quality consistency
    - [ ] 5.5 Prevent contextual meaning drift
    - [ ] 5.6 Preserve emotional nuance
    - [ ] 5.7 Ensure cross-language consistency for repeated terms and names
  - **Verification:**
    - [ ] Golden-set translation scenarios reviewed by a fluent speaker
    - [ ] Character names and key terms translate consistently across passages
  - **Definition of done:** Translation preserves meaning, voice and imagery.

- [ ] **5.12 — Cross-module transform architecture**
  - **Source:** AI Writing Tools Critical **E**, **F**, **G**, **H** *(A, B, D, I, J covered by 5.3–5.6)*
  - **Area:** AI / Backend
  - **Priority:** Critical
  - **Depends on:** 5.3, 5.4, 5.5, 5.6
  - **Blocked by:** None
  - **Can run in parallel:** No
  - **Implementation checklist:**
    - [ ] **E** Prevent content injection across all transform types
    - [ ] **F** Preserve literary subtlety across all transform types
    - [ ] **G** Make transformation results consistent across repeated runs
    - [ ] **H** Prevent AI voice convergence — different authors must not converge on one voice
    - [ ] Apply the preservation hierarchy uniformly across every transform
  - **Verification:**
    - [ ] Golden-set: two distinct author voices remain distinguishable after the same transform
    - [ ] Repeated identical transforms produce stable results
  - **Definition of done:** Every transform obeys the same preservation architecture.

- [ ] **5.13 — AI suggestions and writing tips overhaul**
  - **Source:** AI Suggestions sub-report — all **16** issues (Critical 1, 2; High 3–11; Medium 12–16)
  - **Area:** AI
  - **Priority:** High
  - **Depends on:** 5.1, 5.2
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Context:** The report's finding is blunt — suggestions are praise, not suggestions, with positive bias and no weakness detection.
  - **Implementation checklist:**
    - [ ] Redesign prompts toward developmental-editing critique
    - [ ] Add weakness detection (High 3)
    - [ ] Remove positive bias (High 4)
    - [ ] Make feedback actionable and specific (Critical 1, 2)
    - [ ] Eliminate generic and repetitive feedback (High 5, 6, 7)
    - [ ] Remove over-reliance on fixed categories (High 8)
    - [ ] Add story-specific analysis using retrieved context (High 9; Medium 15)
    - [ ] Add narrative risk detection (High 10)
    - [ ] Add developmental editing depth (High 11; Medium 12, 14)
    - [ ] Add recommendation prioritisation (Medium 13)
    - [ ] Separate observations from recommendations (Medium 16)
    - [ ] Consider an explicitly adversarial critique pass
  - **Verification:**
    - [ ] Golden-set: suggestion actionability rate measured and improved
    - [ ] Author review confirms suggestions identify real weaknesses
  - **Definition of done:** Suggestions read as a developmental editor's notes, not as praise.

- [ ] **5.14 — Story audit: continuity false positives and reasoning depth**
  - **Source:** Story Audit sub-report — all **15** issues (Critical 1–5; High 6–10; Medium 11–15)
  - **Area:** AI
  - **Priority:** Critical
  - **Depends on:** Stage 4, 5.1, 5.2
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Context:** False continuity breaks are worse than none — they train authors to ignore the feature.
  - **Implementation checklist:**
    - [ ] **Require evidence citation for every reported contradiction; suppress uncited findings** (Critical 1, 2; High 6)
    - [ ] Move beyond surface-level contradiction detection (Critical 3)
    - [ ] Strengthen timeline reasoning (Critical 4)
    - [ ] Strengthen narrative reasoning (Critical 5)
    - [ ] Deepen character arc analysis (High 7)
    - [ ] Complete unresolved-thread detection (High 8)
    - [ ] Add story stakes analysis (High 9)
    - [ ] Add plot importance prioritisation (High 10)
    - [ ] Add relationship arc analysis (Medium 11)
    - [ ] Add theme analysis (Medium 12)
    - [ ] Replace generic improvement recommendations (Medium 13)
    - [ ] Add developmental editing insight (Medium 14, 15)
  - **Verification:**
    - [ ] Golden-set: continuity false-positive rate measured and reduced versus baseline
    - [ ] Every reported finding carries a manuscript citation
  - **Definition of done:** Continuity reports nothing it cannot evidence.

- [ ] **5.15 — Writing analytics transparency**
  - **Source:** Writing Analytics sub-report — all **6** issues (Medium 1–6)
  - **Area:** AI / Frontend
  - **Priority:** Medium
  - **Depends on:** 3.9
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Explain how each metric is calculated (Medium 1)
    - [ ] Explain the readability score and its scale (Medium 2)
    - [ ] Give the dialogue ratio genre context (Medium 3)
    - [ ] Add genre-aware analytics benchmarks (Medium 4)
    - [ ] Make metrics actionable (Medium 5)
    - [ ] Integrate story intelligence into analytics (Medium 6)
  - **Verification:**
    - [ ] Every displayed metric has an explanation reachable in the UI
    - [ ] Author review confirms the numbers are interpretable
  - **Definition of done:** No analytics number is presented without meaning.

- [ ] **5.16 — Re-measure quality against baseline**
  - **Source:** Gate 3b
  - **Area:** AI / Testing
  - **Priority:** Critical
  - **Depends on:** 5.3–5.15
  - **Blocked by:** None
  - **Can run in parallel:** No
  - **Implementation checklist:**
    - [ ] Re-run the full golden set against the new prompt versions
    - [ ] Compare every metric to the 5.2 baseline
    - [ ] Record which metrics improved, held and regressed
    - [ ] Investigate and address any regression
    - [ ] Conduct blind author review on transform output
  - **Verification:**
    - [ ] Voice preservation improved; unnecessary-change rate reduced; continuity false-positive rate reduced
    - [ ] Blind author review passes
  - **Definition of done:** Quality improvement is demonstrated by measurement, not asserted.

### Stage 5 Completion Gate

- [ ] All 48 AI Writing Tools issues (38 + 10 cross-module) closed or accepted
- [ ] All 16 AI Suggestions issues closed or accepted
- [ ] All 15 Story Audit issues closed or accepted
- [ ] All 6 Writing Analytics issues closed or accepted
- [ ] Prompt versioning live; every generation traceable to a version
- [ ] Measured improvement over the 5.2 baseline recorded
- [ ] P3-05 and P3-02 delivered and verified against Phase 3 acceptance criteria
- [ ] Blind author review passed
- [ ] **Gate 3b — AI quality acceptable** passed

---

# Stage 6 — Test Automation and CI

**Entry condition:** Stage 5 gate passed.
**Why here:** Encodes fixed behaviour, not broken behaviour. Must exist before Phase 3 adds eleven capabilities. CI scaffolding (task 6.1) is the exception — start it during Stage 1.
**Source:** `docs/testing/author-feature-test-checklist.docx`; production gaps PG-01, PG-10
**Current state:** 5 backend test files, 2 frontend spec files, no CI.

---

- [ ] **6.1 — CI pipeline**
  - **Source:** Production gap **PG-01**
  - **Area:** Infrastructure / Testing
  - **Priority:** Critical
  - **Depends on:** None — **start during Stage 1**
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Create `.github/workflows/` with a CI workflow
    - [ ] Run backend lint and the existing 5 test files
    - [ ] Run frontend lint, typecheck and the existing 2 spec files
    - [ ] Run `alembic upgrade head` then `downgrade` against a throwaway PostgreSQL service
    - [ ] Fail the build on any test failure
    - [ ] Make the workflow a required check on `main`
  - **Verification:**
    - [ ] A deliberately broken commit fails CI and cannot merge
  - **Definition of done:** No change reaches `main` without passing tests.

- [ ] **6.2 — Seeded fixture manuscript and deterministic test user**
  - **Source:** Master Execution Plan §11.2; `docs/testing/author-feature-test-checklist.docx`
  - **Area:** Testing
  - **Priority:** Critical
  - **Depends on:** 6.1
  - **Blocked by:** None
  - **Can run in parallel:** No — blocks 6.3–6.5
  - **Context:** The checklist references specific characters (Devika, Mara, Sant, Vance) — the fixture must contain them.
  - **Implementation checklist:**
    - [ ] Author a multi-chapter fixture manuscript with documented ground truth
    - [ ] Include the named cast, aliases, a timeline and a mystery thread
    - [ ] Create a deterministic seeded test user with a known JWT
    - [ ] Add a reset-to-fixture command
    - [ ] Document the ground truth alongside the fixture
  - **Verification:**
    - [ ] Reset restores identical state every time
  - **Definition of done:** Every test runs against a known, reproducible manuscript.

- [ ] **6.3 — Automate the author feature test checklist**
  - **Source:** `docs/testing/author-feature-test-checklist.docx` — every row
  - **Area:** Testing
  - **Priority:** Critical
  - **Depends on:** 6.2
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Writing and editor rows — editor, project/story, chapter management, search/replace, DOCX/PDF export
    - [ ] AI text transform rows — refine, tone, emotion, audience, style, author-style, translation, suggestions, continuation, outline
    - [ ] Story intelligence rows — genre detection, emotional arc, continuity, style drift, duplicate scene, narrative threads, plot holes, plot assistant, editorial report, copyright risk
    - [ ] Characters and world rows — character bible, profiles, relationship graph, arc timeline, voice consistency, story bible
    - [ ] Input and ingestion rows — manuscript upload, OCR, audio transcription, notes/cards
    - [ ] Productivity and platform rows — voice agent, pacing goals, analytics, activity timeline, JWT auth
    - [ ] **Assert database state, not only HTTP 200** — several defects returned success while failing to persist
    - [ ] Mark rows that must remain manual and document why
  - **Verification:**
    - [ ] Every checklist row maps to a test or a documented manual exception
  - **Definition of done:** The manual checklist is an automated suite.

- [ ] **6.4 — Playwright end-to-end suite**
  - **Source:** Master Execution Plan §11.3
  - **Area:** Testing / Frontend
  - **Priority:** High
  - **Depends on:** 6.2
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Login → project → chapter → autosave → reload persistence
    - [ ] Select text → transform → apply
    - [ ] Upload manuscript → chapters populate
    - [ ] OCR upload → text injected
    - [ ] Audio upload → transcript returned
    - [ ] Generate story bible → five sections render with provenance
    - [ ] Voice agent → action actually executes
    - [ ] Selection toolbar lifecycle (guards task 3.8)
    - [ ] Analytics scrolling (guards task 3.9)
  - **Verification:**
    - [ ] Suite runs in CI against a live stack
  - **Definition of done:** Critical author journeys are guarded end to end.

- [ ] **6.5 — AI quality evaluation harness in CI**
  - **Source:** Master Execution Plan §11.4; task 5.2
  - **Area:** AI / Testing
  - **Priority:** High
  - **Depends on:** 5.2, 6.2
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Package the golden set as a runnable suite
    - [ ] Automate voice-preservation scoring
    - [ ] Automate the unnecessary-change rate
    - [ ] Automate continuity false-positive measurement
    - [ ] Automate Story Bible provenance validation
    - [ ] Alert on regression beyond an agreed threshold
    - [ ] Run on a schedule rather than per-commit if GPU cost requires it
  - **Verification:**
    - [ ] A deliberate prompt regression is detected by the harness
  - **Definition of done:** AI quality regressions are caught automatically.

- [ ] **6.6 — Regression tests for every closed issue**
  - **Source:** Master Execution Plan §11.5
  - **Area:** Testing
  - **Priority:** High
  - **Depends on:** 6.3
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Convert every closed Phase 2 issue into a permanent test
    - [ ] Convert every closed Phase 1 issue into a permanent test or a golden-set case
    - [ ] Make both QA reports re-runnable as suites so closure is demonstrable
    - [ ] Link each test to its issue ID
  - **Verification:**
    - [ ] Reintroducing any closed defect turns the suite red
  - **Definition of done:** No closed issue can silently reopen.

- [ ] **6.7 — Dependency vulnerability scanning**
  - **Source:** Production gap **PG-10**
  - **Area:** Security / Infrastructure
  - **Priority:** Medium
  - **Depends on:** 6.1
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Add `pip-audit` for `backend/requirements.txt`, `requirements.setup.txt`, `requirements.vllm.txt`
    - [ ] Add `npm audit` for the frontend
    - [ ] Enable Dependabot or an equivalent
    - [ ] Define the severity threshold that fails the build
    - [ ] Triage the current findings
  - **Verification:**
    - [ ] Scan runs in CI; a seeded vulnerable dependency fails the build
  - **Definition of done:** Dependency risk is continuously monitored.

### Stage 6 Completion Gate

- [ ] CI green and enforced as a required check on `main`
- [ ] Fixture manuscript and deterministic test user in place
- [ ] Every author-checklist row automated or documented as manual
- [ ] Playwright suite covering all critical journeys
- [ ] AI quality harness running and alerting
- [ ] Every closed issue guarded by a regression test
- [ ] Dependency scanning active
- [ ] **Gate 6 — End-to-end tests passed** (initial pass; re-confirmed in Stage 9)

---

# Stage 7 — Phase 3 Implementation

**Entry condition:** Stage 6 gate passed; **D-4 recorded** (all twelve sub-decisions).
**Why here:** Phase 3 optimises the loop *around* generation. A lossless loop around an untrustworthy generator preserves untrustworthy output efficiently. With Stages 3–5 complete it delivers its intended value.
**Source:** `docs/phases/phase-3-planned/phase-3-author-centric-ai-workflow.md` (authoritative Markdown)
**Note:** P3-02 and P3-05 were delivered in Stage 5. Task 7.3 verifies them rather than rebuilding them.

---

- [ ] **7.1 — Close Phase 3 stakeholder decisions and re-baseline**
  - **Source:** Phase 3 spec §45, §7.4
  - **Area:** Product / Planning
  - **Priority:** Critical
  - **Depends on:** Stage 6
  - **Blocked by:** **D-4**
  - **Can run in parallel:** No
  - **Implementation checklist:**
    - [ ] Confirm all twelve §45 decisions are recorded (task 0.4)
    - [ ] Re-read §7.4 and confirm each listed blocker is cleared
    - [ ] Re-baseline scope given P3-02 and P3-05 already delivered
    - [ ] Confirm the milestone sequence: Milestone 0 → 3A generation control → remaining
  - **Verification:**
    - [ ] No open product question remains in the Phase 3 scope
  - **Definition of done:** Phase 3 implementation can start without ambiguity.

- [ ] **7.2 — Verify PRE-1 and PRE-2 are delivered**
  - **Source:** Phase 3 spec §7.4, §46 items 3 and 4
  - **Area:** Backend / Frontend
  - **Priority:** Critical
  - **Depends on:** 7.1
  - **Blocked by:** None
  - **Can run in parallel:** No
  - **Implementation checklist:**
    - [ ] Confirm PRE-1 fixed in task 3.1 with `test_retrieval_signatures.py` present
    - [ ] Confirm P2-02 continuation and P2-04 outline demonstrably work
    - [ ] Confirm PRE-2 fixed in task 3.8 — toolbar dismisses on deselect and defers to the sidecar
  - **Verification:**
    - [ ] Phase 3 spec §46 items 3 and 4 satisfied
  - **Definition of done:** Phase 3's prerequisite defects are provably closed.

- [ ] **7.3 — Verify P3-02 and P3-05 meet Phase 3 acceptance criteria**
  - **Source:** Phase 3 spec §40, §P3-02, §P3-05; Master Execution Plan §7.3
  - **Area:** AI / Backend
  - **Priority:** Critical
  - **Depends on:** 7.2
  - **Blocked by:** **D-4**, **D-5**
  - **Can run in parallel:** No
  - > **Do not reimplement.** These were delivered in Stage 5 tasks 5.4 and 5.3.
  - **Implementation checklist:**
    - [ ] Verify P3-02 against its §40 acceptance criteria
    - [ ] Verify P3-05 against its §40 acceptance criteria
    - [ ] Confirm the segment model is compatible with P3-01 pin storage
    - [ ] Confirm the preservation-rules table matches the §13 schema so P3-10 can extend it
    - [ ] Close any acceptance gap found
  - **Verification:**
    - [ ] Both capabilities pass Phase 3 acceptance, not merely the Phase 1 QA fix
  - **Definition of done:** P3-02 and P3-05 are Phase-3-complete, with no duplicate implementation.

- [ ] **7.4 — Phase 3 migrations 0016–0019**
  - **Source:** Phase 3 spec §13, §46 item 5
  - **Area:** Database
  - **Priority:** Critical
  - **Depends on:** 7.3
  - **Blocked by:** **D-4**
  - **Can run in parallel:** No
  - **Implementation checklist:**
    - [ ] Reconcile the preservation-rules migration created in Stage 5 with the planned numbering
    - [ ] Create the `ai_generation_pins` migration
    - [ ] Create the `note_cards` extension migration (§13.3) for P3-09 / P3-10
    - [ ] Add the nullable vector column for P3-11
    - [ ] Use `alembic revision --autogenerate`; never raw `ALTER TABLE`
    - [ ] Ensure every migration is idempotent and reversible
  - **Verification:**
    - [ ] `alembic upgrade head` then `downgrade` runs cleanly on PostgreSQL 16 + pgvector
    - [ ] Migration test runs in CI
    - [ ] Rollback verified against a populated database
  - **Definition of done:** Schema changes apply and roll back cleanly.

- [ ] **7.5 — P3-01 Temporary generation pins**
  - **Source:** Phase 3 spec §P3-01 (§327), §15, §16, §21.1
  - **Area:** Backend / Database / Frontend
  - **Priority:** High
  - **Depends on:** 7.4
  - **Blocked by:** **D-4** (D3, D4, D9)
  - **Can run in parallel:** No — P3-03, P3-04, P3-06, P3-11 all reuse it
  - **Implementation checklist:**
    - [ ] Design confirmation against §P3-01
    - [ ] `ai_generation_pins` table and migration
    - [ ] Backend pin create / list / delete
    - [ ] Retention and expiry per D3
    - [ ] `pin_store_embedding` default per D4
    - [ ] Ownership and permission rules — a pin belongs to one user and one story
    - [ ] Plan-limit enforcement per §21.1
    - [ ] Exclude from logical backups per D9
    - [ ] Pin action in `SelectionToolbar.tsx`
    - [ ] Pin list UI
  - **Verification:**
    - [ ] Unit and integration tests for pin lifecycle and expiry
    - [ ] Cross-user isolation test — user A cannot read user B's pins
    - [ ] Migration and rollback verified
    - [ ] Storage growth measured against the §32 cost model
  - **Definition of done:** An author can keep a good attempt and it survives until expiry.

- [ ] **7.6 — P3-03 Use pinned versions as generation context**
  - **Source:** Phase 3 spec §P3-03 (§477), §1517
  - **Area:** AI / Backend / Frontend
  - **Priority:** High
  - **Depends on:** 7.5
  - **Blocked by:** **D-4**
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Design confirmation against §P3-03
    - [ ] Feed up to N pins into the prompt, budget-shared
    - [ ] Summarise oversized pins rather than truncating
    - [ ] Apply §12.3 prompt budgeting
    - [ ] Run preservation checks on the output
    - [ ] UI to select which pins are context
  - **Verification:**
    - [ ] Integration test asserting pin content reaches the prompt
    - [ ] Prompt stays within the context window at maximum pin count
  - **Definition of done:** An author can say "use the villain from attempt 4".

- [ ] **7.7 — P3-04 Side-by-side comparison and merge**
  - **Source:** Phase 3 spec §P3-04 (§545), §1518, §1519
  - **Area:** Frontend / AI
  - **Priority:** High
  - **Depends on:** 7.5
  - **Blocked by:** **D-4**
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Design confirmation against §P3-04
    - [ ] Client-side diff — no new storage
    - [ ] Comparison summary via `_extract_json` with `{}` fallback, best-effort
    - [ ] Block-level merge selection
    - [ ] Merge smoothing with word-count delta ≤ 12% and block similarity ≥ 0.9
    - [ ] One retry, then return the unsmoothed merge
    - [ ] Comparison and merge UI
  - **Verification:**
    - [ ] Unit tests for the smoothing constraints
    - [ ] Playwright test for the compare-and-merge flow
  - **Definition of done:** An author can see how two candidates differ and combine them.

- [ ] **7.8 — P3-06 Generate from a specific previous version**
  - **Source:** Phase 3 spec §P3-06 (§685), §1521
  - **Area:** AI / Backend / Frontend
  - **Priority:** Medium
  - **Depends on:** 7.5
  - **Blocked by:** **D-4**
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Design confirmation against §P3-06
    - [ ] Lineage columns on `ai_generation_pins` — parent, root, depth
    - [ ] Pass the base pin as SOURCE DRAFT plus the original excerpt for position
    - [ ] Record derivation intent (variation, improve, …)
    - [ ] Apply the P3-11 anti-echo score
    - [ ] Lineage view in the UI
  - **Verification:**
    - [ ] Integration test asserting lineage is recorded correctly
    - [ ] Derived output differs measurably from its parent
  - **Definition of done:** An author can branch from any earlier attempt.

- [ ] **7.9 — P3-07 Session-level idea-repetition avoidance**
  - **Source:** Phase 3 spec §P3-07 (§747), §1522, §29.5
  - **Area:** AI / Backend
  - **Priority:** Medium
  - **Depends on:** 7.5
  - **Blocked by:** **D-4** (D12)
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Design confirmation against §P3-07
    - [ ] Session-scoped avoid-set — **never persisted** (§29.5)
    - [ ] Cap at 8 gists × 140 characters
    - [ ] Similarity check against the avoid-set via P3-11
    - [ ] Auto-retry default per D12
  - **Verification:**
    - [ ] Unit test asserting the avoid-set is not written to the database
    - [ ] Repeated generations produce varied ideas within a session
  - **Definition of done:** The model stops repeating itself within a session, and nothing is permanently blacklisted.

- [ ] **7.10 — P3-08 Character and story-fact consistency guard**
  - **Source:** Phase 3 spec §P3-08 (§815), §1523
  - **Area:** AI / Backend
  - **Priority:** High
  - **Depends on:** 7.3, Stage 4
  - **Blocked by:** **D-4** (D6)
  - **Can run in parallel:** Yes
  - **Context:** Composes both retrieval helpers fixed in task 3.1 — verify PRE-1 first.
  - **Implementation checklist:**
    - [ ] Design confirmation against §P3-08
    - [ ] Assemble characters, facts, world rules, timeline and nearby summaries into context
    - [ ] Implement Tier 0 and Tier 1 free checks
    - [ ] Implement the Tier 2 opt-in JSON check, gated per D6
    - [ ] One repair retry on a hard-rule violation
    - [ ] Reuse Phase 1/2 data — no new storage
  - **Verification:**
    - [ ] Integration test: a generation contradicting an established fact is flagged
    - [ ] Tier 2 cost measured against the D6 gating decision
  - **Definition of done:** Generations that contradict the established story are caught.

- [ ] **7.11 — P3-09 Idea Shelf**
  - **Source:** Phase 3 spec §P3-09 (§907), §13.3, §27.2
  - **Area:** Backend / Database / Frontend
  - **Priority:** Medium
  - **Depends on:** 7.4
  - **Blocked by:** **D-4** (D10)
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Design confirmation against §P3-09
    - [ ] Extend `note_cards` with an `idea` card type — no new table (§27.2)
    - [ ] Ideas survive pin expiry
    - [ ] Navigation placement per D10 — coordinate with task 8.8
    - [ ] Idea Shelf UI
    - [ ] Ownership rules consistent with note cards
  - **Verification:**
    - [ ] Integration test: an idea survives its source pin's expiry
    - [ ] Migration and rollback verified
  - **Definition of done:** A good idea outlives the generation that produced it.

- [ ] **7.12 — P3-10 Author writing-style preservation**
  - **Source:** Phase 3 spec §P3-10 (§974), §28.1, §1524
  - **Area:** AI / Backend
  - **Priority:** Medium
  - **Depends on:** 7.3, 7.4
  - **Blocked by:** **D-4** (D5, D11)
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Design confirmation against §P3-10
    - [ ] Extend the P3-05 preservation table
    - [ ] Reuse `story_dna` rather than building a style analyser (§28.1)
    - [ ] Assemble fingerprint, exemplars and surrounding paragraphs into context
    - [ ] Default style match level per D5
    - [ ] Account-level style profiles deferred per D11 (§28.6)
    - [ ] Note: no machine verification at this scale (§1524) — rely on golden-set author review
  - **Verification:**
    - [ ] Golden-set author review confirms style match
    - [ ] Token cost measured against the D5 decision
  - **Definition of done:** Generated text sounds like the author.

- [ ] **7.13 — P3-11 Duplicate and near-duplicate detection**
  - **Source:** Phase 3 spec §P3-11 (§1048)
  - **Area:** AI / Backend / Database
  - **Priority:** Medium
  - **Depends on:** 7.5
  - **Blocked by:** **D-4** (D4, D12)
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Design confirmation against §P3-11
    - [ ] Nullable vector column on `ai_generation_pins`
    - [ ] Similarity scoring against existing pins
    - [ ] Anti-echo score used by P3-06 and P3-07
    - [ ] Surface near-duplicate warnings in the UI
    - [ ] Auto-retry behaviour per D12
  - **Verification:**
    - [ ] Unit test: a near-identical generation is detected
    - [ ] Behaviour verified with `pin_store_embedding` both on and off
  - **Definition of done:** The author is told when a new attempt repeats an old one.

- [ ] **7.14 — Verify Phase 3 product rules R1–R10**
  - **Source:** Phase 3 spec §46 item 2
  - **Area:** AI / Backend / Testing
  - **Priority:** High
  - **Depends on:** 7.5–7.13
  - **Blocked by:** None
  - **Can run in parallel:** No
  - **Implementation checklist:**
    - [ ] Verify each of R1–R10
    - [ ] **R1 and R6 must be verified by test, not by inspection** (spec requirement)
  - **Verification:**
    - [ ] Automated tests exist for R1 and R6
    - [ ] Every other rule has a recorded verification method
  - **Definition of done:** All ten product rules are verified as the spec requires.

- [ ] **7.15 — Phase 3 definition of done (§46, §47)**
  - **Source:** Phase 3 spec §46, §47
  - **Area:** Planning / Testing
  - **Priority:** High
  - **Depends on:** 7.14
  - **Blocked by:** None
  - **Can run in parallel:** No
  - **Implementation checklist:**
    - [ ] All eleven capabilities meet their §40 acceptance criteria
    - [ ] Migrations 0016–0019 apply and roll back cleanly
    - [ ] Walk the full §47 checklist
    - [ ] Track realised cost against the §32 model
    - [ ] Extend the Stage 6 suite with Phase 3 coverage
  - **Verification:**
    - [ ] Every §46 and §47 item ticked
  - **Definition of done:** Phase 3 is complete by its own published standard.

### Stage 7 Completion Gate

- [ ] All twelve Phase 3 stakeholder decisions applied
- [ ] PRE-1 and PRE-2 verified closed
- [ ] P3-01 … P3-11 all delivered (P3-02, P3-05 verified from Stage 5)
- [ ] Migrations 0016–0019 apply and roll back cleanly on PostgreSQL 16 + pgvector
- [ ] Locked segments proven byte-identical across regeneration
- [ ] Product rules R1–R10 verified, R1 and R6 by test
- [ ] Phase 3 §46 and §47 fully satisfied
- [ ] Storage and cost within the §32 model

---

# Stage 8 — Editor UI and Author Workspace Redesign

**Entry condition:** Stage 7 gate passed.
**Why here:** The QA report's own conclusion is that this is a redesign, not a patch. Phase 3 adds pin, compare and lock surfaces to the editor — redesigning first guarantees a second redesign. Genuinely broken UI was already fixed in Stage 3, so authors are not waiting on usability blockers.
**Source:** `docs/issues-and-bugs/open/phase-1-ai-writing-tools-qa-issues.docx` — Editor UI sub-report (**18** issues); Phase 2 Issue 10 (deferred from task 3.13); production gap PG-09
**Prerequisite:** A named design owner. This is a UX programme, not a ticket queue.

---

- [ ] **8.1 — Workspace-based navigation**
  - **Source:** Editor UI Critical **3**, **4**, **7**
  - **Area:** Frontend
  - **Priority:** High
  - **Depends on:** Stage 7
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Replace the overloaded right-panel tab strip with workspace navigation
    - [ ] Stop treating major tools as small tabs
    - [ ] Define workspaces: writing, planning, analysis, AI assistance
    - [ ] Map all Phase 1, 2 and 3 tools to a workspace
  - **Verification:**
    - [ ] Every tool has exactly one home; Playwright navigation tests pass
  - **Definition of done:** Navigation reflects author workflow, not the feature list.

- [ ] **8.2 — Resizable and expandable panels**
  - **Source:** Editor UI Critical **8**
  - **Area:** Frontend
  - **Priority:** High
  - **Depends on:** 8.1
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Make the side panel resizable by drag
    - [ ] Allow panels to expand to full width for detailed work
    - [ ] Persist panel sizes per user
  - **Verification:**
    - [ ] Playwright test: resize persists across reload
  - **Definition of done:** The author controls the workspace layout.

- [ ] **8.3 — Writing-first visual hierarchy**
  - **Source:** Editor UI Critical **1**, **2**; High **9**, **14**
  - **Area:** Frontend
  - **Priority:** High
  - **Depends on:** 8.1
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Give the manuscript visual primacy
    - [ ] Stop AI tools competing visually with the text
    - [ ] Reduce congestion for long-session use
    - [ ] Provide a focused reading and writing mode
  - **Verification:**
    - [ ] Author review confirms the manuscript is the focal point
  - **Definition of done:** The interface reads as a writing tool first.

- [ ] **8.4 — Progressive disclosure**
  - **Source:** Editor UI Critical **6**; High **10**, **13**
  - **Area:** Frontend
  - **Priority:** Medium
  - **Depends on:** 8.1
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Show tools progressively instead of all at once
    - [ ] Establish a clear tool hierarchy
    - [ ] Reduce navigation density
    - [ ] Keep discoverability without visual clutter
  - **Verification:**
    - [ ] Measured reduction in simultaneously visible controls
    - [ ] Author review confirms features remain discoverable
  - **Definition of done:** Cognitive load is reduced without hiding capability.

- [ ] **8.5 — Drafting and editing mode separation**
  - **Source:** Editor UI High **11**, **12**
  - **Area:** Frontend
  - **Priority:** Medium
  - **Depends on:** 8.3
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Define distinct drafting and editing modes
    - [ ] Surface only mode-relevant tools
    - [ ] Respect the long-form writing workflow
  - **Verification:**
    - [ ] Author review across a full drafting session and a full editing session
  - **Definition of done:** Drafting and editing feel like different activities.

- [ ] **8.6 — Dedicated space for advanced AI and Phase 3 surfaces**
  - **Source:** Editor UI High **15**
  - **Area:** Frontend
  - **Priority:** High
  - **Depends on:** 8.1, Stage 7
  - **Blocked by:** None
  - **Can run in parallel:** No
  - **Implementation checklist:**
    - [ ] Give advanced AI features room to work
    - [ ] Home the Phase 3 pin, compare, lock and preservation surfaces
    - [ ] Integrate the rewritten `SelectionToolbar` from tasks 3.8 and 5.4
  - **Verification:**
    - [ ] Every Phase 3 capability is reachable and usable
  - **Definition of done:** Advanced AI is not squeezed into a narrow panel.

- [ ] **8.7 — Scalability for future features**
  - **Source:** Editor UI Critical **5**; Medium **18**
  - **Area:** Frontend
  - **Priority:** Medium
  - **Depends on:** 8.1
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Verify the layout system absorbs new tools without redesign
    - [ ] Document how to add a tool to the workspace
    - [ ] Confirm friction does not grow with feature count
  - **Verification:**
    - [ ] Add a mock tool and confirm no layout regression
  - **Definition of done:** The next feature does not require another redesign.

- [ ] **8.8 — Information architecture and navigation deduplication**
  - **Source:** Editor UI Medium **16**, **17**; **Phase 2 Issue 10** *(deferred from task 3.13)*; Phase 3 decision **D10**
  - **Area:** Frontend
  - **Priority:** Medium
  - **Depends on:** 8.1
  - **Blocked by:** **D-4** (D10)
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Remove the Notes and Narrative Threads navigation duplication
    - [ ] Place the Idea Shelf per D10
    - [ ] Rework the IA so it reads as an author studio, not a tool dashboard
    - [ ] Give every feature one clearly defined location
  - **Verification:**
    - [ ] No feature appears in more than one navigation section without a documented reason
    - [ ] **Phase 2 Issue 10 explicitly closed here**
  - **Definition of done:** Every feature has one obvious home.

- [ ] **8.9 — Accessibility baseline**
  - **Source:** Production gap **PG-09**
  - **Area:** Frontend
  - **Priority:** Medium
  - **Depends on:** 8.1–8.8
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Adopt WCAG 2.1 AA as the standard
    - [ ] Audit keyboard navigation across the editor
    - [ ] Audit screen-reader labelling on all panels
    - [ ] Audit colour contrast
    - [ ] Add focus management for dynamically loaded panels
    - [ ] Add an automated accessibility check to CI
  - **Verification:**
    - [ ] Automated audit passes at the agreed threshold
    - [ ] Keyboard-only navigation completes a full writing session
  - **Definition of done:** The product is usable without a mouse and with a screen reader.

- [ ] **8.10 — Responsive behaviour**
  - **Source:** Master Execution Plan §12 (accessibility and responsive audit)
  - **Area:** Frontend
  - **Priority:** Low
  - **Depends on:** 8.2
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Verify the workspace at common laptop resolutions
    - [ ] Verify panels degrade gracefully at narrow widths
    - [ ] Confirm no horizontal page scroll
  - **Verification:**
    - [ ] Playwright viewport matrix passes
  - **Definition of done:** The workspace is usable on a standard laptop screen.

- [ ] **8.11 — Multi-hour author usability session**
  - **Source:** Editor UI Overall Assessment and Final Recommendation
  - **Area:** Testing / Product
  - **Priority:** High
  - **Depends on:** 8.1–8.10
  - **Blocked by:** None
  - **Can run in parallel:** No
  - **Context:** The report's explicit concern is long-session comfort, which a short demo cannot assess.
  - **Implementation checklist:**
    - [ ] Recruit real authors
    - [ ] Run multi-hour drafting sessions
    - [ ] Record friction points, fatigue and navigation confusion
    - [ ] Confirm against the report's stated goal — a professional author studio
    - [ ] Address findings before closing the stage
  - **Verification:**
    - [ ] Authors complete a full session without layout friction
  - **Definition of done:** The redesign is validated by the people it was designed for.

### Stage 8 Completion Gate

- [ ] All 18 Editor UI issues closed or accepted
- [ ] Phase 2 Issue 10 closed
- [ ] Every Phase 1, 2 and 3 tool has one clear home
- [ ] Panels resizable; layout persists
- [ ] Accessibility baseline met
- [ ] Multi-hour author usability session passed
- [ ] No feature duplicated across navigation sections

---

# Stage 9 — Full Regression Testing and UAT

**Entry condition:** Stage 8 gate passed.
**Source:** Master Execution Plan §11; both QA reports; `docs/testing/author-feature-test-checklist.docx`

---

- [ ] **9.1 — Full regression run**
  - **Source:** Master Execution Plan §11.5
  - **Area:** Testing
  - **Priority:** Critical
  - **Depends on:** Stage 8
  - **Blocked by:** None
  - **Can run in parallel:** No
  - **Implementation checklist:**
    - [ ] Run the complete backend integration suite
    - [ ] Run the complete Playwright suite
    - [ ] Run the AI quality harness
    - [ ] Run migration up/down verification
    - [ ] Investigate and fix every failure
  - **Verification:**
    - [ ] Entire suite green on a clean pod
  - **Definition of done:** Nothing regressed across nine stages of change.

- [ ] **9.2 — Re-run both QA reports as suites**
  - **Source:** `docs/issues-and-bugs/open/` — both documents
  - **Area:** Testing
  - **Priority:** Critical
  - **Depends on:** 9.1
  - **Blocked by:** None
  - **Can run in parallel:** No
  - **Implementation checklist:**
    - [ ] Re-run all 14 Phase 2 scenarios
    - [ ] Re-run all 154 Phase 1 scenarios or their automated equivalents
    - [ ] Record pass/fail per issue
    - [ ] Reconcile against the Stage 0 triage labels
  - **Verification:**
    - [ ] Every release-blocking issue passes
    - [ ] Every deferred issue is explicitly accepted
  - **Definition of done:** Issue closure is demonstrated, not asserted.

- [ ] **9.3 — Performance testing**
  - **Source:** Master Execution Plan §11.6; production gap PG-12
  - **Area:** Testing / Infrastructure
  - **Priority:** High
  - **Depends on:** 9.1
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Measure p50/p95 latency per AI endpoint
    - [ ] Test concurrent users against `BG_AI_CONCURRENCY=3` and `EMBEDDING_CONCURRENCY=2`
    - [ ] Measure pgvector HNSW latency at realistic corpus size
    - [ ] Measure behaviour at the 60-chapter plot-hole cap
    - [ ] Measure vLLM queue depth under load
    - [ ] Record baselines for ongoing comparison
  - **Verification:**
    - [ ] Latency targets defined and met
  - **Definition of done:** Performance characteristics are known, not guessed.

- [ ] **9.4 — Security testing**
  - **Source:** Master Execution Plan §11.7
  - **Area:** Security / Testing
  - **Priority:** Critical
  - **Depends on:** 9.1
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Auth bypass attempts
    - [ ] JWT expiry and revocation behaviour
    - [ ] Upload guard bypass — Content-Length spoofing
    - [ ] Rate-limit effectiveness at the D-3 target worker count
    - [ ] Prompt injection via manuscript content into AI features
    - [ ] `_AUTHOR_STYLES` safety registry under adversarial input — Hemingway, Woolf, Christie, unknown strings
    - [ ] Dependency vulnerability review
  - **Verification:**
    - [ ] No finding above the agreed severity threshold remains open
  - **Definition of done:** Known attack surfaces are tested and closed.

- [ ] **9.5 — Cross-user data isolation testing**
  - **Source:** Production gap **PG-14**
  - **Area:** Security / Testing
  - **Priority:** Critical
  - **Depends on:** 9.1
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Context:** Highest-value security test. Multi-tenant manuscript data with no verified isolation test is a serious pre-launch gap. Write this early even though it is verified here.
  - **Implementation checklist:**
    - [ ] Create two test users with separate stories
    - [ ] Attempt cross-user access on every story-scoped endpoint
    - [ ] Attempt cross-user access on chapters, characters, notes, bibles, pins, audio and OCR
    - [ ] Verify the permission seam in `StoryContextEngine.tsx` — documented as always granting access today
    - [ ] Add the isolation suite to CI
  - **Verification:**
    - [ ] Every cross-user attempt returns 403 or 404, never data
  - **Definition of done:** No user can reach another user's manuscript by any route.

- [ ] **9.6 — User acceptance testing with real authors**
  - **Source:** Master Execution Plan §11.8; `docs/testing/author-feature-test-checklist.docx`
  - **Area:** Product / Testing
  - **Priority:** Critical
  - **Depends on:** 9.2
  - **Blocked by:** **D-6**
  - **Can run in parallel:** No
  - **Context:** Most of the 154 Phase 1 issues were found by an author, not a test suite. Only an author can confirm closure.
  - **Implementation checklist:**
    - [ ] Recruit authors with real manuscripts
    - [ ] Run the manual UAT subset from task 6.3
    - [ ] Assess: does the transform preserve my voice?
    - [ ] Assess: does the Plot Assistant know my whole story?
    - [ ] Assess: is the Story Bible accurate?
    - [ ] Assess: is the workspace comfortable for a full writing day?
    - [ ] Record and triage all findings
  - **Verification:**
    - [ ] Authors confirm the previously reported problems are resolved
  - **Definition of done:** Real authors accept the product.

- [ ] **9.7 — Close out the issue documents**
  - **Source:** `docs/issues-and-bugs/README.md` workflow
  - **Area:** Documentation
  - **Priority:** Medium
  - **Depends on:** 9.2, 9.6
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] `git mv` closed issue documents to `docs/issues-and-bugs/resolved/`
    - [ ] Record the fixing commit for each
    - [ ] Create a new open document for any remaining accepted issues
    - [ ] Update `docs/issues-and-bugs/README.md`
    - [ ] Update `docs/README.md` open-issues section
  - **Verification:**
    - [ ] No resolved issue remains in `open/`
  - **Definition of done:** The issue folder reflects reality.

### Stage 9 Completion Gate

- [ ] Full regression suite green
- [ ] Both QA reports re-run with recorded per-issue outcomes
- [ ] Zero open Critical issues
- [ ] All High issues fixed or explicitly accepted per D-6
- [ ] Performance baselines recorded and met
- [ ] Security suite passed including cross-user isolation
- [ ] UAT completed and accepted by real authors
- [ ] Issue documents moved to `resolved/`
- [ ] **Gate 4 — No critical defects** passed
- [ ] **Gate 5 — Security checks passed** passed
- [ ] **Gate 6 — End-to-end tests passed** confirmed

---

# Stage 10 — Production Readiness

**Entry condition:** Stage 9 gate passed. Tasks 10.1–10.3 and 10.9 may start much earlier — they are fully parallel with every other stage.
**Source:** Master Execution Plan §12 — production gaps PG-02 … PG-07, PG-11 … PG-15

---

- [ ] **10.1 — Automated backup and rehearsed restore**
  - **Source:** Production gap **PG-02**
  - **Area:** Infrastructure / Database
  - **Priority:** Critical
  - **Depends on:** 1.1 (manual backup taken there)
  - **Blocked by:** None
  - **Can run in parallel:** Yes — **start immediately**
  - **Implementation checklist:**
    - [ ] Schedule automated `pg_dump` to off-pod storage
    - [ ] Exclude `ai_generation_pins` per Phase 3 decision D9
    - [ ] Define retention and rotation
    - [ ] Verify backup integrity automatically
    - [ ] Document the restore procedure step by step
    - [ ] **Rehearse a full restore into a clean database**
    - [ ] Define and document RPO and RTO
    - [ ] Include uploaded audio and OCR files in the backup scope
  - **Verification:**
    - [ ] A restore rehearsal from an automated backup succeeds end to end
    - [ ] Restored data passes row-count and spot-check validation
  - **Definition of done:** Manuscript loss is recoverable, proven by rehearsal.

- [ ] **10.2 — Monitoring and alerting**
  - **Source:** Production gap **PG-03**
  - **Area:** Infrastructure
  - **Priority:** High
  - **Depends on:** Stage 2
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Context:** Degraded mode — AI returning 503 while health looks fine — is currently invisible until an author complains.
  - **Implementation checklist:**
    - [ ] Add error tracking (Sentry or equivalent) to backend and frontend
    - [ ] Add uptime monitoring on `/api/health`
    - [ ] Alert specifically on `"vllm": "unavailable"`
    - [ ] Alert on rising AI failure and degraded-output rates
    - [ ] Alert on background job failures and orphan recovery activity
    - [ ] Set `LOG_FORMAT=json` for aggregation
    - [ ] Define the on-call notification path
  - **Verification:**
    - [ ] Deliberately stopping vLLM triggers an alert
  - **Definition of done:** Production problems are detected by monitoring, not by users.

- [ ] **10.3 — Containerisation**
  - **Source:** Production gap **PG-04**
  - **Area:** Infrastructure
  - **Priority:** Medium
  - **Depends on:** Stage 2
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Create a Dockerfile for the backend
    - [ ] Create a Dockerfile for the frontend
    - [ ] Create a compose file for local development with PostgreSQL + pgvector
    - [ ] Pin all base image and dependency versions
    - [ ] Document the relationship to `start-narratiq.sh`
  - **Verification:**
    - [ ] A clean container build produces a working stack
  - **Definition of done:** Deployment does not depend solely on a bash script and a RunPod base image.

- [ ] **10.4 — Shared rate-limit storage**
  - **Source:** Production gap **PG-05**; `backend/middleware/rate_limit.py:67`
  - **Area:** Security / Backend
  - **Priority:** High
  - **Depends on:** Stage 2
  - **Blocked by:** **D-3**
  - **Can run in parallel:** Yes
  - **Context:** slowapi is constructed with no `storage_uri`. `SLOWAPI_STORAGE_URI` is read by nothing. In-memory storage is per-process, so limits multiply by worker count.
  - **Implementation checklist:**
    - [ ] Apply the D-3 decision
    - [ ] If multi-worker: provision Redis and pass `storage_uri=` to the `Limiter`
    - [ ] Remove or implement the misleading `SLOWAPI_STORAGE_URI` reference
    - [ ] If staying single-worker: document the constraint prominently and add a startup guard that warns when `--workers > 1`
  - **Verification:**
    - [ ] Rate limits verified effective at the target worker count
  - **Definition of done:** Rate limiting works as documented at the deployed worker count.

- [ ] **10.5 — Rollback procedure**
  - **Source:** Production gap **PG-06**
  - **Area:** Infrastructure / Database
  - **Priority:** High
  - **Depends on:** 10.1, 10.3
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Document code rollback
    - [ ] Document and **test** Alembic downgrade paths against a populated database
    - [ ] Document model-version rollback
    - [ ] Document frontend rollback including the build-time API URL
    - [ ] Rehearse a full rollback
  - **Verification:**
    - [ ] Rollback rehearsal succeeds without data loss
  - **Definition of done:** A bad release can be reversed within the documented RTO.

- [ ] **10.6 — Data retention and deletion policy**
  - **Source:** Production gap **PG-07**
  - **Area:** Product / Backend / Security
  - **Priority:** Medium
  - **Depends on:** Stage 9
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Define account deletion behaviour
    - [ ] Define manuscript deletion behaviour including embeddings and chunks
    - [ ] Define retention for audio uploads and OCR images beyond the existing 24h/72h TTL
    - [ ] Define pin retention per Phase 3 decision D3
    - [ ] Implement an account and data deletion endpoint
    - [ ] Publish the policy
  - **Verification:**
    - [ ] Account deletion removes all associated rows including vector columns
    - [ ] Database-state check confirms no orphaned data
  - **Definition of done:** Authors can delete their data and it is genuinely deleted.

- [ ] **10.7 — JWT HttpOnly cookie migration**
  - **Source:** Production gap **PG-15**; `CLAUDE.md` "Phase B (future)"
  - **Area:** Security / Backend / Frontend
  - **Priority:** Medium
  - **Depends on:** Stage 9
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Context:** JWT currently in `localStorage['narratiq_token']` — XSS-exfiltratable.
  - **Implementation checklist:**
    - [ ] Migrate token storage to HttpOnly cookies
    - [ ] Update the frontend auth flow and the 401 interceptor in `frontend/lib/api.ts`
    - [ ] Add CSRF protection appropriate to cookie auth
    - [ ] Verify the WebSocket voice agent still authenticates
    - [ ] Verify session persistence across reload
  - **Verification:**
    - [ ] Token is not reachable from JavaScript
    - [ ] Full auth flow passes end to end
  - **Definition of done:** Session tokens are not exposed to client-side script.

- [ ] **10.8 — Load and capacity planning**
  - **Source:** Production gap **PG-12**
  - **Area:** Infrastructure / Product
  - **Priority:** Medium
  - **Depends on:** 9.3
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Determine max concurrent authors on one GPU pod using the 9.3 baselines
    - [ ] Model GPU capacity against Phase 3 Tier-2 consistency cost (D6)
    - [ ] Define the scaling trigger
    - [ ] Document the onboarding limit
  - **Verification:**
    - [ ] Capacity figure validated by a load test
  - **Definition of done:** The supported concurrent user count is a known number.

- [ ] **10.9 — Incident response process**
  - **Source:** Production gap **PG-13**
  - **Area:** Operations
  - **Priority:** Low
  - **Depends on:** 10.2
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Context:** The RunPod incident report demonstrates the capability already exists — formalise it.
  - **Implementation checklist:**
    - [ ] Define severity levels
    - [ ] Define the on-call and escalation path
    - [ ] Adopt the existing incident report as the postmortem template
    - [ ] Define where incident reports are filed — `docs/incidents/`
    - [ ] Document the port-exposure diagnostic as a known-issue runbook entry
  - **Verification:**
    - [ ] A tabletop exercise runs cleanly through the process
  - **Definition of done:** The next incident follows a process, not improvisation.

### Stage 10 Completion Gate

- [ ] Automated backup running; **restore rehearsed successfully**
- [ ] Monitoring and alerting live; degraded mode raises an alert
- [ ] Containerisation complete
- [ ] Rate limiting correct at the target worker count
- [ ] Rollback rehearsed for code, schema and models
- [ ] Data retention and deletion policy implemented and published
- [ ] JWT migrated to HttpOnly cookies
- [ ] Capacity limit known and documented
- [ ] Incident response process documented
- [ ] **Gate 7 — Backup and recovery verified** passed
- [ ] **Gate 8 — Deployment and rollback tested** passed

---

# Stage 11 — Documentation Reconciliation

**Entry condition:** Stage 10 gate passed. Deliberately late — reconciling earlier would document a system about to change.
**Source:** Master Execution Plan §5.4–§5.7, §4.3, §4.4; production gap PG-11

---

- [ ] **11.1 — Fix `CLAUDE.md` internal contradictions**
  - **Source:** Master Execution Plan §5.6 (conflict C-6)
  - **Area:** Documentation
  - **Priority:** High
  - **Depends on:** Stage 10
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Remove `continuation.py`, `outline.py` and `voice.py` from the Phase 2 feature table — they do not exist; the functionality is in `writing_tools.py` and `characters.py`
    - [ ] Reconcile migration numbering — on-disk `0008`, `0009`, `0010` are correct
    - [ ] Add the Phase 3 migrations `0016`–`0019`
    - [ ] Update the architecture section for all Stage 3–8 changes
  - **Verification:**
    - [ ] Every file, router and migration named in `CLAUDE.md` exists
  - **Definition of done:** The architecture source of truth no longer contradicts itself.

- [ ] **11.2 — Correct `README.md`**
  - **Source:** Master Execution Plan §5.5 (conflict C-5)
  - **Area:** Documentation
  - **Priority:** Medium
  - **Depends on:** Stage 10
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Correct the claim that batched and hierarchical plot-hole strategies are "written but not enabled" — they are **not written**; lines 1607–1610 are commented registry entries pointing at non-existent functions
    - [ ] Refresh the Known Issues section against the post-Stage-9 state
    - [ ] Update the feature status lists
    - [ ] Update the documentation table with any new paths
  - **Verification:**
    - [ ] Every README claim traces to verified code or a closed issue
  - **Definition of done:** The landing page is accurate.

- [ ] **11.3 — Resolve the Phase 3 naming collision**
  - **Source:** Master Execution Plan §5.7 (conflict C-7)
  - **Area:** Documentation
  - **Priority:** Medium
  - **Depends on:** Stage 10
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Rename the `CLAUDE.md` section to "Production Hardening (completed)"
    - [ ] Refer to the feature phase consistently as "Phase 3 — Author-Centric AI Workflow"
    - [ ] Update `docs/README.md` and `docs/phases/README.md` warnings accordingly
  - **Verification:**
    - [ ] No document uses "Phase 3" ambiguously
  - **Definition of done:** The two workstreams are unambiguously distinguishable.

- [ ] **11.4 — Reconcile hardware documentation**
  - **Source:** `docs/incidents/runpod-port-3000-404-incident-report.md` §11; task 1.6
  - **Area:** Documentation
  - **Priority:** Medium
  - **Depends on:** 1.6
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Update the `CLAUDE.md` Blackwell GPU section with the verified hardware from task 1.6
    - [ ] Correct the documented `max-model-len` if 8192 is confirmed
    - [ ] Clarify which NCCL flags and sm_120 requirements apply to which hardware
    - [ ] Update `docs/operations/runpod-deployment.md` GPU requirements
  - **Verification:**
    - [ ] Documented hardware matches what vLLM actually starts with
  - **Definition of done:** GPU documentation matches reality.

- [ ] **11.5 — Refresh the product and technical specification to v5**
  - **Source:** Master Execution Plan §4.3; `docs/specifications/narratiq-ai-product-and-technical-documentation.docx`
  - **Area:** Documentation
  - **Priority:** Medium
  - **Depends on:** 11.1
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Context:** Currently v4.1, titled "Phase 1 Complete — Phase 2 Planned". Phase 2, the hardening pass and Phase 3 have all landed since.
  - **Implementation checklist:**
    - [ ] Update the implementation status tables
    - [ ] Add Phase 2 delivered features
    - [ ] Add the production hardening pass
    - [ ] Add Phase 3 capabilities
    - [ ] Update the architecture section
    - [ ] Retitle to v5 with an accurate phase status
  - **Verification:**
    - [ ] The specification matches the shipped system
  - **Definition of done:** The product spec is current.

- [ ] **11.6 — Formal Phase 2 acceptance**
  - **Source:** `docs/phases/phase-2-completed/phase-2-intelligence-expansion-roadmap.docx` §20.4, §16, §19
  - **Area:** Documentation / Product
  - **Priority:** Medium
  - **Depends on:** Stage 9
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Context:** Phase 2 was declared complete by construction, never by acceptance. §20.4 includes items that were never done — for example updating the implementation report to reflect Phase 2 additions.
  - **Implementation checklist:**
    - [ ] Walk §20.4 line by line, marking each verified or not
    - [ ] Confirm every §16 Production Rule still holds, especially self-hosted-only and BGE-M3 singleton reuse
    - [ ] Verify each of P2-01 … P2-11 against its §19 task specification
    - [ ] Update or supersede the Phase 1 Production Implementation Report to cover Phase 2
    - [ ] Confirm §20.5 out-of-scope items remain out of scope
    - [ ] Record a named verifier and date per item
  - **Verification:**
    - [ ] Every §20.4 item has a verifier and a date
  - **Definition of done:** Phase 2 is formally accepted rather than assumed.

- [ ] **11.7 — Release the author-style and copyright-risk features**
  - **Source:** `docs/specifications/author-style-and-copyright-risk-features.md`; `CHANGELOG.md` "Unreleased"
  - **Area:** AI / Documentation / Security
  - **Priority:** Medium
  - **Depends on:** 9.4
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Context:** The `_AUTHOR_STYLES` registry is the stated safety authority restricting output to public-domain authors. Verify before release, not after.
  - **Implementation checklist:**
    - [ ] Confirm the adversarial tests from task 9.4 pass
    - [ ] Verify the living-author redirect cannot be bypassed
    - [ ] Verify "inspired-by, never copy" prompt enforcement under adversarial prompting
    - [ ] Verify the copyright-risk score and disclaimer render correctly
    - [ ] Flag the disclaimer wording for legal review
    - [ ] Move from "Unreleased" to a versioned CHANGELOG entry
  - **Verification:**
    - [ ] No adversarial prompt elicits in-copyright author imitation
  - **Definition of done:** Both features are verified safe and formally released.

- [ ] **11.8 — Automate generated-document synchronisation**
  - **Source:** Production gap **PG-11**
  - **Area:** Documentation / Infrastructure
  - **Priority:** Low
  - **Depends on:** 6.1
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Context:** Two `.md`/`.docx` pairs currently at 1.000 and 0.999 similarity will drift the moment the Markdown is edited.
  - **Implementation checklist:**
    - [ ] Add a `make docs` target regenerating Word copies via pandoc
    - [ ] Regenerate both current pairs
    - [ ] Add a CI check that fails when a pair is out of sync
    - [ ] Document the workflow in `docs/README.md` conventions
  - **Verification:**
    - [ ] Editing a Markdown source without regenerating fails CI
  - **Definition of done:** Word copies cannot silently diverge from their sources.

- [ ] **11.9 — Resolve the missing recovery report**
  - **Source:** Master Execution Plan §4.4; **D-7**
  - **Area:** Documentation
  - **Priority:** Low
  - **Depends on:** Stage 10
  - **Blocked by:** **D-7**
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Apply the D-7 decision
    - [ ] If located: commit it to the correct documentation folder
    - [ ] If retired: remove the reference from `README.md` and annotate the archive mapping table
    - [ ] Update `docs/archive/README.md`
  - **Verification:**
    - [ ] No document references an unresolvable file
  - **Definition of done:** Every documentation reference resolves.

### Stage 11 Completion Gate

- [ ] `CLAUDE.md` self-consistent; every named file exists
- [ ] `README.md` accurate, including the plot-hole strategy correction
- [ ] Phase 3 naming collision resolved
- [ ] Hardware documentation matches verified reality
- [ ] Product specification refreshed to v5
- [ ] Phase 2 formally accepted with named verifiers
- [ ] Author-style and copyright-risk features released
- [ ] Generated document sync automated
- [ ] All documentation references resolve
- [ ] A new engineer can follow the documentation without hitting a non-existent file

---

# Stage 12 — Release Validation

**Entry condition:** Stage 11 gate passed.
**Source:** Master Execution Plan §13 — Gates 1–9

---

- [ ] **12.1 — Verify all production readiness gates**
  - **Source:** Master Execution Plan §13
  - **Area:** Product / Testing / Infrastructure
  - **Priority:** Critical
  - **Depends on:** Stages 1–11
  - **Blocked by:** None
  - **Can run in parallel:** No
  - **Implementation checklist:**
    - [ ] Gate 1 — Environment stable
    - [ ] Gate 2 — Core workflows functional
    - [ ] Gate 3a — Retrieval correct
    - [ ] Gate 3b — AI quality acceptable
    - [ ] Gate 4 — No critical defects
    - [ ] Gate 5 — Security checks passed
    - [ ] Gate 6 — End-to-end tests passed
    - [ ] Gate 7 — Backup and recovery verified
    - [ ] Gate 8 — Deployment and rollback tested
    - [ ] Record any waiver with an explicit product-owner decision
  - **Verification:**
    - [ ] Every gate is passed or has a recorded waiver
  - **Definition of done:** No gate is silently skipped.

- [ ] **12.2 — Publish release notes and operational documentation**
  - **Source:** Master Execution Plan §13 Gate 9
  - **Area:** Documentation
  - **Priority:** High
  - **Depends on:** 12.1
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [ ] Write release notes covering all delivered work
    - [ ] Update `CHANGELOG.md` with the release version
    - [ ] Confirm the deployment runbook includes the port contract
    - [ ] Confirm the backup, restore and rollback runbooks are current
    - [ ] Publish known limitations, including the chapter ceiling per D-8
  - **Verification:**
    - [ ] An operator can deploy, back up, restore and roll back from the documentation alone
  - **Definition of done:** Operational documentation is complete and current.

- [ ] **12.3 — Release approval**
  - **Source:** Master Execution Plan §13 Gate 9
  - **Area:** Product
  - **Priority:** Critical
  - **Depends on:** 12.1, 12.2
  - **Blocked by:** **D-6**
  - **Can run in parallel:** No
  - **Implementation checklist:**
    - [ ] Present gate results to the product owner
    - [ ] Confirm the D-6 release-blocking scope is satisfied
    - [ ] Record accepted known issues
    - [ ] Obtain and record written sign-off
    - [ ] Confirm the rollback plan is ready before deploying
  - **Verification:**
    - [ ] Written sign-off recorded in the repository
  - **Definition of done:** **Gate 9 — Release approval completed.**

### Stage 12 Completion Gate

- [ ] All nine production readiness gates passed or waived with recorded decisions
- [ ] Release notes published
- [ ] Operational documentation complete
- [ ] Product owner sign-off recorded
- [ ] Rollback plan ready
- [ ] **Release approved**

---

# Final Project Completion Checklist

- [ ] All 168 open issues closed, deferred with a recorded decision, or accepted per D-6
- [ ] All eleven Phase 3 capabilities delivered and verified against §46 and §47
- [ ] All fifteen production gaps (PG-01 … PG-15) addressed
- [ ] All eight master decisions (D-1 … D-8) recorded and applied
- [ ] All twelve Phase 3 sub-decisions (D1 … D12) recorded and applied
- [ ] All eight documentation conflicts (C-1 … C-8) resolved or formally accepted
- [ ] CI enforced; full test suite green
- [ ] AI quality improvement demonstrated by measurement against the Stage 5 baseline
- [ ] Backup and restore rehearsed; rollback rehearsed
- [ ] Security suite passed including cross-user data isolation
- [ ] UAT accepted by real authors
- [ ] Documentation self-consistent with no unresolvable reference
- [ ] All nine production readiness gates passed
- [ ] Release approved and shipped

---

# Decision Register

| ID | Decision | Owner | Status | Date | Blocks |
|---|---|---|---|---|---|
| D-1 | Plot Assistant retrieval scope | Product owner | ☐ Open | — | 4.1, 4.2, 4.3, 4.4, 4.5, 4.15 |
| D-2 | Retire or repair `start.sh` | Tech lead | ☐ Open | — | 2.4 |
| D-3 | Single- or multi-worker deployment target | Tech lead / Infra | ☐ Open | — | 10.4 |
| D-4 | Phase 3 stakeholder decisions (D1–D12) | Product + Eng | ☐ Open | — | 7.1–7.15, 8.8 |
| D-5 | Preservation-layer sequencing | Product + Eng | ☐ Open | — | 5.3, 5.4, 7.3 |
| D-6 | Release-blocking issue scope | Product owner | ☐ Open | — | 9.6, 12.3 |
| D-7 | Missing recovery report | Doc owner | ☐ Open | — | 11.9 |
| D-8 | Acceptable chapter ceiling at launch | Product owner | ☐ Open | — | Plot-hole strategy sizing |
| D1–D12 | Phase 3 spec §45 sub-decisions | Product + Eng | ☐ Open | — | Stage 7 (see task 0.4) |

---

# Blocked-Task Register

26 tasks are currently blocked. All clear once Stage 0 completes, except 1.4 which is an infrastructure action.

| Task | Blocked by | Clears when |
|---|---|---|
| 2.4 | D-2 | D-2 recorded |
| 4.1, 4.2, 4.3, 4.4, 4.5, 4.15 | D-1 | D-1 recorded |
| 5.3, 5.4 | D-5 | D-5 recorded |
| 7.1, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 7.10, 7.11, 7.12, 7.13 | D-4 | All twelve §45 decisions recorded |
| 8.8 | D-4 (D10) | D10 recorded |
| 9.6 | D-6 | D-6 recorded |
| 10.4 | D-3 | D-3 recorded |
| 11.9 | D-7 | D-7 recorded |
| 12.3 | D-6 | D-6 recorded |

**Additionally blocked by infrastructure:** every task in Stages 2–12 is transitively blocked until task 1.4 (port exposure) completes.

---

# Source-Document Coverage Matrix

| Source Document | Checklist Stage | Tasks Created | Fully Covered |
|---|---|---:|---|
| `docs/NarratIQ_Master_Execution_Plan_and_Document_Implementation_Order.md` | 0–12 (all) | 130 | Yes — this checklist is its execution form |
| `docs/issues-and-bugs/open/phase-1-ai-writing-tools-qa-issues.docx` | 4, 5, 8 | 42 | Yes — all 154 issues mapped |
| ├ AI Writing Tools (48) | 5 | 5.3–5.12 | Yes |
| ├ AI Plot Assistant (16) | 4 | 4.1–4.5 | Yes |
| ├ AI Suggestions (16) | 5 | 5.13 | Yes |
| ├ Cast Generation & Character Management (14) | 3, 4 | 3.12, 4.6–4.9 | Yes |
| ├ Story Audit (15) | 5 | 5.14 | Yes |
| ├ Writing Analytics (6) | 3, 5 | 3.9, 5.15 | Yes |
| ├ Search Module ×2 (9 + 12, merged) | 4 | 4.10–4.14 | Yes |
| └ Editor UI / Author Workspace (18) | 8 | 8.1–8.11 | Yes |
| `docs/issues-and-bugs/open/phase-2-production-testing-issues.docx` | 3, 8 | 13 | Yes — all 14 issues mapped (Issue 10 deferred to 8.8) |
| `docs/phases/phase-3-planned/phase-3-author-centric-ai-workflow.md` | 3, 5, 7 | 17 | Yes — P3-01…P3-11, PRE-1, PRE-2, §45, §46, §47 |
| `docs/phases/phase-3-planned/phase-3-author-centric-ai-workflow.docx` | — | 0 | Reference only — generated duplicate (0.999 similarity), no separate tasks required |
| `docs/incidents/runpod-port-3000-404-incident-report.md` | 1 | 9 | Yes |
| `docs/incidents/runpod-port-3000-404-incident-report.docx` | — | 0 | Reference only — generated duplicate (1.000 similarity), no separate tasks required |
| `docs/operations/runpod-environment-variables.md` | 2 | 5 | Yes |
| `docs/operations/runpod-deployment.md` | 1, 2, 11 | 3 | Yes |
| `docs/operations/how-to-run.md` | 1, 2 | 2 | Yes |
| `docs/testing/author-feature-test-checklist.docx` | 6, 9 | 4 | Yes — every row automated in 6.3 |
| `docs/phases/phase-2-completed/phase-2-intelligence-expansion-roadmap.docx` | 11 | 1 | Yes — §20.4 acceptance in 11.6 |
| `docs/phases/phase-1-completed/phase-1-production-implementation-report.docx` | 11 | 1 | Yes — superseded/updated in 11.6 |
| `docs/phases/phase-1-completed/phase-1-status-update.docx` | 11 | 1 | Yes — baseline for 11.6 verification |
| `docs/specifications/author-style-and-copyright-risk-features.md` | 9, 11 | 2 | Yes — 9.4 adversarial tests, 11.7 release |
| `docs/specifications/narratiq-ai-product-and-technical-documentation.docx` | 11 | 1 | Yes — v5 refresh in 11.5 |
| `README.md` | 11 | 1 | Yes |
| `CLAUDE.md` | 11 | 3 | Yes — 11.1, 11.3, 11.4 |
| `CHANGELOG.md` | 11, 12 | 2 | Yes |
| `.env.example` | 2 | 1 | Yes |
| `docs/archive/narratiq-ai-technical-analysis-report-v2.docx` | — | 0 | Reference only — superseded, no implementation tasks required |
| `docs/archive/documentation-recovery-changelog.md` | — | 0 | Reference only — historical record of a completed task |
| `docs/README.md`, `docs/phases/README.md`, `docs/issues-and-bugs/README.md`, `docs/operations/README.md`, `docs/archive/README.md` | 9, 11 | 2 | Yes — updated in 9.7 and 11.x |

**26 source documents inventoried. 21 generated implementation tasks. 5 are reference-only (2 generated duplicates, 2 archived, and the navigational index set which is updated rather than implemented).**

---

# Excluded Items

Every issue, capability, production gap and decision from every source document has a checklist location. Nothing was excluded on grounds of being minor.

Four items are deliberately **deferred** rather than excluded, each with a recorded destination:

| Item | Source | Deferred to | Reason |
|---|---|---|---|
| Phase 2 Issue 10 — Notes/Threads navigation duplication | Phase 2 issues | Task **8.8** | The information architecture is being rebuilt in Stage 8; fixing placement twice is waste. Recorded in task 3.13. |
| Batched / hierarchical plot-hole strategies | `README.md`; `ai_service.py:1607–1610` | Sized under **D-8** | Not written — commented registry entries pointing at non-existent functions. Genuine development work whose scope depends on the accepted chapter ceiling. |
| Account-level style profiles | Phase 3 spec §28.6 | Post-Phase-3 per **D11** | The specification itself defers this. |
| `NarratIQ_Project_Recovery_Report.docx` content | `README.md`; archive changelog | Task **11.9** under **D-7** | Not in the repository; cannot be actioned until located or formally retired. |

---

*This checklist was produced by inspection only. No application code, database schema, migration, infrastructure component or existing document was modified.*
