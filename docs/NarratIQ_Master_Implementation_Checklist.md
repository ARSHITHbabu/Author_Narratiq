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
| 3 — Phase 2 Production Defect Resolution | 13 | 13 | 0 | 0 | **Complete** |
| 4 — Phase 1 Retrieval and Data Correctness | 16 | 0 | 16 | 6 | Not Started |
| 5 — Phase 1 AI Generation Quality | 16 | 0 | 16 | 2 | Not Started |
| 6 — Test Automation and CI | 7 | 0 | 7 | 0 | Not Started |
| 7 — Phase 3 Implementation | 15 | 0 | 15 | 12 | Not Started |
| 8 — Editor UI and Workspace Redesign | 11 | 0 | 11 | 1 | Not Started |
| 9 — Full Regression Testing and UAT | 7 | 0 | 7 | 1 | Not Started |
| 10 — Production Readiness | 9 | 0 | 9 | 1 | Not Started |
| 11 — Documentation Reconciliation | 9 | 0 | 9 | 1 | Not Started |
| 12 — Release Validation | 3 | 0 | 3 | 1 | Not Started |
| **Total** | **131** | **13** | **118** | **26** | **In Progress** |

> The stage table counts **main tasks**. Stage 1 shows 0 completed because task 1.1 is still open — six of its seven subtasks are done; the seventh, the off-pod copy, is deferred. The counts below track actionable checkboxes and are the authoritative progress measure.

> *2026-07-26 — Stage 3 closed.* All 13 main tasks are ticked and the Stage 3 gate is closed. **Two checkboxes inside Stage 3 remain open by design, not by omission**: task 3.10's manual OCR end-to-end (its image→text half is blocked by a separate defect tracked outside Stage 3) and task 3.13's *"task 8.8 closes Phase 2 Issue 10"* (an assertion about future Stage 8 work). Both are annotated in place. The total rose from 1125 to 1134 with the addition of task **4.16**.

**Total actionable checkboxes:** 1134
**Currently completed:** 144
**Remaining:** 990
**Overall project completion:** 12.7% (144 ÷ 1134)

> *Counting-basis note (2026-07-25):* the recorded total of 1125 is a **whole-file** checkbox count. The formula above says Stages 0–12, which counts **1111** — the 14-box difference is the Final Project Completion Checklist and the register sections. The existing basis is retained so the figures stay comparable across updates; the formula wording and the basis should be reconciled in Stage 11.

> This checklist contains **only remaining work**. Already-delivered systems (PostgreSQL 16 + pgvector, the 15-migration chain, 24 routers, the production-hardening pass) are verified complete and are deliberately absent — they are recorded in the Master Execution Plan §6.1. A 0% reading measures remaining work, not the product.

---

## Next Task to Execute

> ### ✅ Stage 3 is COMPLETE — 2026-07-26
>
> All **13 main tasks** are done and the **Stage 3 Completion Gate is closed**, including *Gate 2 — Core workflows functional*. The ten verification items that had stood open across 3.2, 3.3, 3.4, 3.6 and 3.7 were executed in one consolidated run on a **verification copy** of the restored manuscript; the restored manuscript itself was never written to and still matches its 2026-07-24 baseline exactly.
>
> The run found and fixed **two real defects no earlier testing had caught** — the voice recording endpoints returning HTTP 500 on every call, and provenance coverage measuring 0.37 rather than 1.00. Both were corrected under approved plans and re-verified; provenance now measures **117/117 = 1.00**, grounding **11/11 events supported, 0 unsupported**, and the author has confirmed no unsupported detail.
>
> ### ☞ Next stage — Stage 4, Phase 1 Retrieval and Data Correctness
>
> **Entry condition:** Stage 3 gate passed ✅ — and **decision D-1 recorded**, which is *not* yet done. Six Stage 4 tasks (4.1–4.5, 4.15) are blocked on it, so D-1 is the practical next action, not a task.
>
> **Carried out of Stage 3, tracked but not scheduled:**
> 1. **OCR inference failure** (`DynamicCache` / GOT-OCR2.0) — high priority, documented at [`docs/issues-and-bugs/ocr-extraction-got-ocr2-dynamiccache-failure.md`](./issues-and-bugs/ocr-extraction-got-ocr2-dynamiccache-failure.md), deliberately outside the Stage 3 numbering.
> 2. **Five pre-existing character-hint overlaps** in the restored manuscript — awaiting the backfill decision recorded under task 3.12.
> 3. **Story Bible interpretation quality** — new task **4.16**, created from the author's review.
> 4. **Stage 1's off-pod backup copy** and **Stage 2's environment hygiene** remain deferred, as they have been since 2026-07-24.
>
> ### ⚑ Superseded — the 3.9 pointer (kept for traceability)
>
> **Task 3.8 is COMPLETE (2026-07-26), verification included** — the third main task in Stage 3 to close fully, after 3.1 and 3.5. Phase 2 Issues **1** and **11** are closed and Phase 3 completion criterion 4 (PRE-2) is satisfied. 17 browser tests executed, 61 unit tests, and the author confirmed the QA scenario by hand.
>
> **The environment is no longer a blocker.** The 2026-07-24 dump is restored (1 story / 4 chapters / 8 characters / 21 embedded chunks, schema at `0016`), Chromium and its system libraries are installed, and all three services are healthy. **The ten open verification items across 3.2, 3.3, 3.4, 3.6 and 3.7 are now runnable** — they need execution time, not environment work. Worth scheduling as a single verification pass rather than one task at a time.
>
> **3.9 is a small, self-contained frontend defect** (Phase 2 Issue 3, Medium): the analytics page is unreachable below the fold. Root cause identified in code — see the task.
>
> ### ⚑ Superseded — the 3.8 pointer (kept for traceability)
>
> **Tasks 3.6 and 3.7 — completion approved by the user 2026-07-26.** All ten implementation subtasks and both closeable verification items are ticked. **Both main-task boxes stay open** on three verification items that need a manuscript in the database — the same class of blocker as 3.2, 3.3 and 3.4. Test evidence re-run on 2026-07-26 against the restored runtime: **221/221 backend tests pass** — voice 44, `_extract_json` audit 21, degraded output 25, story bible 89, generation limits 24, retrieval signatures 18.
>
> **3.8 is the first frontend task in Stage 3** (Phase 2 Issues **1** and **11**, Phase 3 spec §7.4 PRE-2, decision **D7**). It is also the first task since 3.1 whose verification is *not* gated on AI output — it needs a browser and a chapter to type in, not a working model.
>
> **Five main tasks now sit open on environment-dependent verification only:** 3.2 (2 items), 3.3 (3), 3.4 (2), 3.6 (2), 3.7 (1) — **ten items in total**. All ten need the same one thing: **a manuscript in the live database**. See the environment note below.
>
> ### ⚑ 2026-07-26 — The stack is running again; the database is empty
>
> Verified live at 10:32 UTC, read-only:
> 1. **All three services are up and healthy.** `/api/health` reports `backend: ready`, `vllm: ready`, `bge_m3: ready`; frontend returns HTTP 200 on port 3000. Backend Python dependencies, Node and npm are all reinstalled.
> 2. **The GPU has changed.** The pod now has **1 × NVIDIA A40 (44.4 GB usable, `tensor_parallel: 1`)**, not the 2 × RTX PRO 4500 Blackwell recorded in `CLAUDE.md`. `max_model_len` is **8192**, so the Story Bible context budgets measured under task 3.3 apply at their 8192 figures, not the doubled 16384 ones. The Blackwell-specific notes in `CLAUDE.md` (sm_120, NCCL flags, `--tensor-parallel-size 2`) no longer describe this pod — **documentation drift, to be reconciled in Stage 11**, not a defect.
> 3. **The live database is at migration `0016` and holds no data** — `users`, `stories`, `chapters`, `chapter_chunks`, `chapter_summaries`, `characters`, `story_bibles` and `voice_commands` are all **0 rows**.
> 4. **The 2026-07-24 backups are intact.** All three SHA-256 checksums in `/workspace/backups` re-verified **OK** on 2026-07-26. They hold 1 story / 4 chapters / 8 characters / 21 chunks. Still **on-pod only** — task 1.1's off-pod copy remains deferred and remains the one unmitigated risk.
>
> **Consequence:** the ten open verification items are now blocked on **data alone**, not on the stack. Restoring `narratiq-20260724T104320Z.dump` into the live database would unblock all of them, but it is a data operation on a live database and **has not been performed — it needs explicit user approval**.
>
> ### ⚠ Superseded next-task note — the Task 3.6 pointer (kept for traceability)
>
> **Task 3.5 is COMPLETE (2026-07-25), verification included** — the second main task in Stage 3 to close fully, after 3.1. The `_extract_json` audit found **five remaining hard-fail sites, none among the four reported issues**; all are converted, seven silent-fallback sites are flagged with destinations, and the register is enforced by a test. It also closed a **live privacy gap** — ten log statements were writing manuscript-derived model output — and two latent 500s.
>
> **Tasks 3.2, 3.3 and 3.4 remain open on verification only** — five items, all needing a restored manuscript and a running stack. That is now the largest blocker in Stage 3.
>
> **3.6 is the voice agent's action execution** (Phase 2 Issue 4), paired with **3.7** (false success reporting), which depends on it. Note 3.5 already flagged `voice/intent.py` as a silent-fallback site whose destination is **this task** — a failed intent parse currently yields `{}`, which is one plausible path to "transcribed correctly, did nothing".
>
> ### ⚠ Superseded next-task note (kept for traceability)
>
> **Tasks 3.2 and 3.3 are implementation-complete (2026-07-25).** Both remain open **only** on verification items requiring live AI on a real manuscript — five in total across the two tasks. Delivered: the failure-path audit ([`docs/issues-and-bugs/story-bible-failure-path-audit.md`](./issues-and-bugs/story-bible-failure-path-audit.md), the canonical reference), per-section outcomes, `completed`/`partial`/`failed` derived from them, **SB-F23 and SB-F16 closed**, `failed_sections` persisted (schema at `0016`), no placeholders stored as content, per-section retry in the UI, and a token-budgeted, provenance-tagged, visibly-degrading context.
>
> ⚠ **The five open verification items are the single largest blocker in Stage 3** and they all need the same thing: a restored manuscript and a running stack. Nothing else in the stage depends on them, so implementation continues — but Stage 3's gate cannot close until the environment returns.
>
> **3.4 closes Phase 2 Issues 2 (plot holes) and 14 (continuity).** Per the audit, these are genuinely the *schema* class, not the retrieval class that 3.1 fixed — `plot_holes.py` and `analysis.py` use no retrieval helpers. `_extract_json()` is already robust; the failure is the caller raising `ValueError` on a schema mismatch.
>
> ### ⚑ 2026-07-25 — Workflow change, by user direction
>
> Review and approval now happen **one complete main task at a time**, not one subtask at a time — to cut review overhead and RunPod cost while holding engineering quality constant. Per main task: **one** planning report organised by subtask → approval → implement all approved subtasks without stopping between them → **one** consolidated implementation report → approval → a single checklist update. **Exception:** if implementing one subtask reveals that a later subtask needs a **material architectural change** beyond the approved plan, stop before that subtask, explain what changed and why, and seek approval for that portion only. Minor adjustments, bug fixes and refactoring inside the approved architecture do not require stopping.
>
> ### ⚠ The product is mid-change — finish 3.2 before starting anything else — *satisfied 2026-07-25: all six 3.2 implementation subtasks including the frontend `partial`/`failed` handling and per-section retry are complete. Kept for traceability.*
>
> The backend can now return `partial`; the frontend still renders it through the **completed** branch and shows **no notification** for it. **User direction: do not move to an unrelated main task until this is closed.** Remaining order: `failed_sections` → stop persisting placeholders → frontend `partial`/`failed` handling → per-section retry. This is an accepted intermediate state, **not a releasable one**.
>
> **Constraints carried into the remaining subtasks:**
> 1. `failed_sections` **does** need a migration (unlike `status`); follow the reversible, idempotent pattern of `0015`.
> 2. **SB-F15** — the database-state verification checkbox is unsafe as worded. A bare `[` scan false-positives on genuine prose. Assert on `status` + `failed_sections`, or match the exact placeholder strings.
> 3. Live end-to-end verification of 3.2 needs a restored fixture manuscript and a running stack — see the environment issues below.
> 4. Four stale comments describing the status value set should be corrected alongside the `failed_sections` schema work.
>
> ### ⚑ 2026-07-25 — Environment issues: the pod no longer has a working stack or any data — *partly superseded 2026-07-26: the stack is back, the empty database is not. See the 2026-07-26 note above.*
>
> Discovered during the 3.2 audit, **tracked separately, not blocking documentation work**:
> 1. **The live database is empty.** PostgreSQL 16.14 is running with the `0015` schema, but `stories`, `chapters`, `chapter_summaries`, `chapter_chunks`, `characters` and `users` are all **0 rows**. The 1 story / 4 chapters / 8 characters / 21 chunks restored on 2026-07-24 are gone from the live database; they survive only in `/workspace/backups`, whose checksums were re-verified intact on 2026-07-25.
> 2. **Backend, frontend and vLLM are not running** — `/api/health` unreachable.
> 3. **Schema drift:** live `story_bibles.status` is nullable with no server default, i.e. provisioned by `Base.metadata.create_all()` rather than migration `0015`.
>
> **Consequence:** every remaining 3.2 verification step — the two unit tests, the database-state check and the re-run of the QA scenario — needs a restored fixture manuscript and a running stack. Code-writing subtasks can proceed; their verification cannot close until this is resolved. **No restore or service start has been performed** — awaiting user direction.
>
> **Task 3.1 (PRE-1) closed 2026-07-24.** Chapter continuation and outline generation both work; Phase 2 Issues 12 and 13 are resolved. Four defects were fixed under it, three of which were not in the original task description — see its progress notes.
>
> Stage 1 remains open on the deferred off-pod backup copy, and Stage 2 on deferred environment hygiene. Neither gates Stage 3 feature work.
>
> ### ⚑ 2026-07-24 — Recovery complete. The application is running again.
>
> The container was destroyed and rebuilt at 15:17 UTC, taking PostgreSQL with it. The stack has been fully recovered: ports 3000 and 8000 exposed, runtime reinstalled, **database restored from the 10:38 backup with all 1 story / 4 chapters / 8 characters / 21 embedded chunks intact**, backend and frontend reachable on both proxy hosts. Details under tasks 1.4–1.8. **Feature development can resume.**
>
> **Deferred by user direction, recorded not abandoned:** the off-pod backup transfer (task 1.1), the Git history rewrite and contributor cleanup, task 1.2's rewrite, task 1.9 and all documentation reconciliation, and the `storage-and-persistence.md` §8 evidence pass. None is complete; none blocks feature work.
>
> ### ☞ Stage 1, Task 1.1 — Take a verified database backup and confirm network-volume persistence
>
> **Next actionable subtask:** *Copy the dump off-pod (not to `/workspace` alone)* — ⏸ **deferred by user decision, 2026-07-24.** It is the only subtask of 1.1 still open, and until it is done task 1.1 cannot be ticked and task 1.3 must not start.
>
> Six of the seven subtasks are complete (2026-07-24): the `pg_dump`, its metadata record, a proven test restore, the volume mount-point identification, the pod-stop survival analysis, and the encrypted environment-file backup. Every artifact is still **on the pod**, so none of it yet protects against the stop/start. Inspection confirmed the PostgreSQL data directory sits on the **ephemeral** container overlay, not the network volume; the database will very likely not survive the stop, which is what makes the off-pod copy the one remaining item that actually reduces risk.
>
> **While the off-pod copy is deferred,** work continues in document order on items that do not depend on it — the established policy for this task. Nothing downstream of the pod stop may proceed.
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
    - [x] Back up `backend/.env` and `frontend/.env.local` separately (they hold `SECRET_KEY`) — *2026-07-24, encrypted archive `/workspace/backups/env-backup-20260724T114018Z.tar.gz.gpg`, decrypt verified by the user*
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
    - *2026-07-24 — environment files backed up and the archive proven decryptable.* `backend/.env` and `frontend/.env.local` are captured in a single GPG symmetric archive, `/workspace/backups/env-backup-20260724T114018Z.tar.gz.gpg` (514 bytes, SHA-256 `3e4964ca…52a5c83`, AES256.CFB cipher 9, S2K mode 3 iterated+salted, MDC present). Integrity confirmed against its `.sha256` sidecar; captured contents confirmed byte-identical to the live files (`backend/.env` 343 bytes `e1432583…f958c98`, `frontend/.env.local` 65 bytes `7beaf628…44a56b28`), so the archive is current. Scope covers `SECRET_KEY`, `DATABASE_URL`, `VLLM_BASE_URL`, `VLLM_MODEL_NAME`, `CORS_ORIGINS`, `NEXT_PUBLIC_API_URL` — verified by reading key names only; no secret value was read, printed or logged. **Recoverability proven by the user on 2026-07-24** via a decrypt-and-extract round trip into a scratch directory, both extracted hashes matching, plaintext destroyed afterwards. Metadata recorded in `/workspace/backups/BACKUP-RECORD.txt`. The passphrase is held only by the user, off-pod and outside any password manager on this machine.
    - *Discovery during this subtask — the archive was created ahead of its report.* The artifact was written 2026-07-24 11:40–11:46 UTC, after the previous checklist edit (11:32) and before commit `6c50522` (11:49), and was neither reported nor validated at the time. All evidence above was independently re-derived from the filesystem in a later session before this box was ticked; nothing was inherited on trust.
    - *Limitation — this artifact is on-pod.* It sits in `/workspace/backups` alongside the database dumps and shares their failure domain. `/workspace` is the network volume and is *predicted* to survive a pod stop, but that prediction is still unobserved. **Ticking this subtask does not relax the hard stop on task 1.3.**
    - *Limitation — passphrase loss is unrecoverable and has a user-visible cost.* There is no escrow and no second copy. If the passphrase is lost, `start-narratiq.sh` regenerates `SECRET_KEY` and every active author session is invalidated — recoverable, but a forced logout for every author.
    - *Deferred improvement — no reproducible script.* The database backup has `scripts/backup_database.sh`; this environment-file backup was performed ad hoc and exists nowhere in the repository. Recorded here as a candidate improvement, **not** a condition of this subtask, by user decision on 2026-07-24. Natural home: an extension to `scripts/backup_database.sh`, or Stage 10.
    - *Finding — weak database credential.* The `narratiq` role's password is identical to its username and database name. PostgreSQL binds to `127.0.0.1` only, which bounds exposure. Pre-existing; not changed. Triage alongside Stage 10.

- [ ] **1.2 — Record the pre-restart baseline** ⏸ **DEFERRED — original intent no longer achievable**
  - > *2026-07-24.* The container was recreated at 15:17 UTC outside this workflow, before any baseline was captured. There is no pre-restart state left to record, so this task cannot be completed as written. **Not started, not complete — deferred for rewrite or retirement** once feature work allows. It does not block application recovery and did not block it. Task 1.3's dependency on it is void for the same reason.
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
  - > ### ⓘ Superseded by events — 2026-07-24, not performed
    > **This task was never executed and is no longer required.** Two things happened outside the workflow: (a) the container was recreated at 15:17 UTC with no controlled stop, destroying the database — the exact loss this task's hard stop existed to prevent; (b) the port change in task 1.4 was subsequently applied by RunPod **without recreating the container** (`PID 1` start time unchanged at 15:17 across the whole port edit), so no second stop was needed. No further pod stop is pending. Recovery was completed on the running container instead. Leave unticked — the work described here did not occur.
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
    - [x] Add HTTP port **3000** to the pod configuration — *2026-07-24, by the user via the RunPod console*
    - [x] Add HTTP port **8000** to the pod configuration — *2026-07-24, by the user via the RunPod console*
    - [x] Confirm both appear in the saved configuration before starting — *2026-07-24, confirmed functionally*
  - **Verification:**
    - [x] ~~RunPod GraphQL API `pod.runtime.ports` lists both privatePorts~~ — *2026-07-24. **The GraphQL check was not run** (no API key on the pod). Substituted with stronger end-to-end evidence: both `https://cvbzi22qmdehpk-3000.proxy.runpod.net/` and `…-8000.proxy.runpod.net/api/health` return **HTTP 200** with correct bodies. Before the change both returned the documented unexposed-port signature (empty-body 404, `server: cloudflare`); immediately after, with the app still down, both returned **502** — proving the proxy route existed and was forwarding. A live 200 supersedes a config listing.*
  - **Definition of done:** Both ports are present in the pod's authoritative port list.

- [ ] **1.5 — Restart the pod and bring up the stack**
  - **Source:** `docs/operations/how-to-run.md`; `start-narratiq.sh`
  - **Area:** Infrastructure
  - **Priority:** Critical
  - **Depends on:** 1.4
  - **Blocked by:** None
  - **Can run in parallel:** No
  - **Implementation checklist:**
    - [ ] Start the pod — *not performed by this workflow; the container came up on its own at 15:17 UTC on 2026-07-24. Left unticked deliberately.*
    - [x] Confirm `/workspace/narratiq-ai` and `/workspace/models` survived — *2026-07-24, both intact; all 4 model directories present, `node_modules` and `.next` too*
    - [x] Confirm the database survived; if not, restore from task 1.1 — *2026-07-24. **It did not survive.** Restored from `/workspace/backups/narratiq-20260724T103824Z.dump`.*
    - [x] Run `bash start-narratiq.sh` — *2026-07-24, completed; reinstalled Node 20, PostgreSQL 16 + pgvector, the pip stack and vLLM onto the wiped container layer*
    - [x] Watch `/tmp/narratiq-logs/vllm.log`, `backend.log`, `frontend.log` to completion — *2026-07-24*
  - **Verification:**
    - [x] All three services report started — *2026-07-24; vLLM pid 11423, backend pid 14686 (restarted after the restore), frontend pid 14487, PostgreSQL 16 pid 12522*
    - [x] `curl localhost:8000/api/health` reports vLLM available, not `"unavailable"` — *2026-07-24, `"vllm":"ready"`, `"bge_m3":"ready"`, `"backend":"ready"`*
  - **Definition of done:** Full stack running on the restarted pod with data intact.
  - **Progress notes:**
    - *2026-07-24 — persistence predictions confirmed by observation.* The container reset at 15:17 UTC settled `storage-and-persistence.md` §8 empirically. **Survived** (`/workspace` network volume): repository, all 4 models, `node_modules`, `.next`, `backend/.env` with its `SECRET_KEY`, and every backup artifact — all three checksums re-verified `OK` after the reset. **Lost** (container overlay): the entire PostgreSQL installation — *binaries as well as the data directory* — plus Node, the full pip stack, and `/tmp/narratiq-logs`. The §8 prediction was correct on every point. Full §8.2 Evidence-column rewrite is deferred; this note is the record.
    - *2026-07-24 — database restored and verified.* `narratiq-20260724T103824Z.dump` restored with `pg_restore --exit-on-error`: **exit 0, zero errors or warnings.** Guarded by a zero-application-rows precheck run twice, immediately before the `DROP DATABASE` (start-narratiq.sh had created an empty 52-table schema that would otherwise collide). Roles first re-applied from `narratiq-globals-20260724T103824Z.sql`; both roles already existed so the `CREATE ROLE` statements errored harmlessly while the `ALTER ROLE` attribute statements applied. **Restored with ownership, not `--no-owner`** — all 52 tables report `tableowner=narratiq`, closing the caveat recorded under task 1.1. Verified after restore: `stories`=1, `chapters`=4, `characters`=8, `users`=1, `chapter_chunks`=21 — every count an exact match to the pre-loss source; 52 tables, 124 indexes, 6 HNSW, `alembic_version`=0015, pgvector 0.8.5; all 21 chunks carry 1024-dim embeddings and a `<=>` cosine query returns correctly ordered neighbours (self 0.000000, next 0.102494). **The 2026-07-24 backup performed its purpose in a real recovery, not a drill.**
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
    - [x] Record `nvidia-smi` output — GPU model and count — *2026-07-24, **1× NVIDIA A40, 46068 MiB***
    - [x] Record `RUNPOD_GPU_COUNT` — *2026-07-24, **1***
    - [x] Record the actual `tensor_parallel` value from `/api/health` — *2026-07-24, **1***
    - [x] Record the effective `max-model-len` from the vLLM startup log — *2026-07-24, **8192**, confirmed independently at `/v1/models`*
    - [ ] Determine whether `NCCL_P2P_DISABLE` / `NCCL_SHM_DISABLE` are required on this hardware — deferred; inert at `TP=1` (no cross-GPU communication), so it does not affect current runtime
    - [ ] Feed all findings into task 11.4 — deferred with the documentation work
  - **Verification:**
    - [ ] Recorded values match what vLLM actually started with
  - **Definition of done:** The real hardware and context window are known and documented facts.
  - > ### ⚠ Constraint that affects feature work — recorded 2026-07-24
    > **The usable context window is 8192 tokens, not the 16384 stated in `CLAUDE.md`.** `start-narratiq.sh:303-311` sizes vLLM from the detected GPU count; at 1 GPU it selects `TP=1, max-model-len=8192, gpu-memory-utilization=0.88`, so **no configuration change is needed — the script adapts itself.** But every prompt-assembly and context-budget task in Stages 4, 5 and 7 must be designed against **8192**. Correcting `CLAUDE.md` is deferred with the rest of the documentation work; this note is the operative record until then.

- [ ] **1.7 — Rebuild the frontend with the correct public API URL**
  - **Source:** `CLAUDE.md`; `docs/operations/how-to-run.md`
  - **Area:** Frontend / Infrastructure
  - **Priority:** Critical
  - **Depends on:** 1.5
  - **Blocked by:** None
  - **Can run in parallel:** No
  - **Context:** `NEXT_PUBLIC_API_URL` is inlined at **build** time. A pod ID change without a rebuild produces a UI that loads and calls the wrong host.
  - **Implementation checklist:**
    - [x] Confirm the pod ID after restart — *2026-07-24. **The pod ID changed** from `2e5wiiphzhzf14` to `cvbzi22qmdehpk`; the stale value in `frontend/.env.local` would have produced a UI that loads and then calls a dead host.*
    - [x] Write `frontend/.env.local` with `NEXT_PUBLIC_API_URL=https://{POD_ID}-8000.proxy.runpod.net` — *2026-07-24, written automatically by `start-narratiq.sh:577-580` from `RUNPOD_POD_ID`; no manual edit was needed*
    - [x] Run `npm run build` in `frontend/` — *2026-07-24, clean rebuild after stale-artifact removal, `BUILD_ID=VMkSDhuLq-skpLjWE9QZs`*
    - [x] Restart the frontend service — *2026-07-24, pid 14487, `next-server v14.2.3`, exactly 1 process*
  - **Verification:**
    - [ ] Browser network tab shows API calls going to the `-8000` proxy host — needs a real browser; **build-level equivalent passed**: the new host is inlined in `.next/static/chunks/6264-*.js`
    - [x] No call targets `localhost` from the browser — *2026-07-24, verified against the compiled bundle: **0 occurrences** of `localhost:8000` and **0 occurrences** of the old pod ID across `.next/static/chunks/*.js`; the only inlined API host is `cvbzi22qmdehpk-8000`*
  - **Definition of done:** The built frontend targets the correct external API host.

- [ ] **1.8 — Verify external reachability end to end**
  - **Source:** incident report §1
  - **Area:** Infrastructure / Testing
  - **Priority:** Critical
  - **Depends on:** 1.7
  - **Blocked by:** None
  - **Can run in parallel:** No
  - **Implementation checklist:**
    - [x] `https://{POD_ID}-3000.proxy.runpod.net` returns HTTP 200 — *2026-07-24, serves `<title>NarratIQ AI — AI-Powered Long-Form Storytelling</title>`. Requested from the pod; a true external-browser check is still the user's step below.*
    - [x] `https://{POD_ID}-8000.proxy.runpod.net/api/health` returns healthy — *2026-07-24, HTTP 200, `"vllm":"ready"`*
    - [ ] Log in through the external URL — **needs the author's own credentials; user step**
    - [ ] Open a project and load a chapter — **user step**
    - [ ] Run one real AI generation through the proxy — **user step.** Inference itself is proven: a direct vLLM call returned the exact requested output (4 completion tokens, model `Qwen/Qwen2.5-7B-Instruct`). What remains untested is the authenticated path through the proxy.
  - **Verification:**
    - [x] A 404 with `server: cloudflare` and an empty body no longer occurs — *2026-07-24, both hosts return 200*
    - [ ] Full round trip works from outside the pod — awaiting the user's browser login
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

- [x] **3.1 — PRE-1: fix the retrieval call signatures in `writing_tools.py`** — *completed 2026-07-24*
  - **Source:** Phase 3 spec §7.4 (PRE-1); Phase 2 issues **12** (outline) and **13** (continuation)
  - **Area:** Backend
  - **Priority:** Critical
  - **Depends on:** Stage 2 — *satisfied in substance on 2026-07-24: the recovery proved all three services healthy on the correct vLLM port (task 2.3's Definition of done). The remaining Stage 2 items are environment and documentation hygiene, deferred by user direction, and none gates this work.*
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Context — verified in code:** `writing_tools.py:94, 106, 180, 191` pass `query=`. `retrieve_relevant_chunks()` takes `question` first (`ai_service.py:3305`); `retrieve_character_context()` takes `(story_id, question, db, …)` (`ai_service.py:1113`). Both raise `TypeError: unexpected keyword argument 'query'` at runtime. This is the whole reason outline and continuation fail — **not** an AI-output problem. Additionally `retrieve_character_context` returns `list[str]` but is passed to `generate_continuations(character_context=…)` as if it were a string.
  - **Implementation checklist:**
    - [x] Fix `writing_tools.py:94` — `query=` → `question=` — *2026-07-24, now line 97*
    - [x] Fix `writing_tools.py:106` — correct keyword and argument order — *2026-07-24, now lines 112-113, keyword form*
    - [x] Fix `writing_tools.py:180` — `query=` → `question=` — *2026-07-24, now line 188*
    - [x] Fix `writing_tools.py:191` — correct keyword and argument order — *2026-07-24, now lines 199-200*
    - [x] Join the character context: `"\n\n".join(...)` before passing to `generate_continuations` and `generate_chapter_outline` — *2026-07-24, both call sites*
    - [x] Grep the whole backend for any other `retrieve_*(query=` call site — *2026-07-24, zero hits; `plot_assistant.py` and `voice/adapters.py` were already correct*
  - **Verification:**
    - [x] Add `backend/tests/test_retrieval_signatures.py` asserting the call signatures (named in Phase 3 spec §3579 as the PRE-1 regression guard) — *2026-07-24, 18 tests, all passing*
    - [x] Manually run chapter continuation — 3 options returned — *2026-07-24, user-tested. Short and Medium passed on the first attempt; Long failed and required two further fixes (see notes), then passed.*
    - [x] Manually run scene outline — beat sheet returned — *2026-07-24, user-tested; failed initially on a response-contract mismatch, fixed, then passed*
    - [x] Confirm character context reaches the prompt as text, not as a list repr — *2026-07-24, verified against the live prompt: 5128 chars of plain text, zero list-repr artefacts*
  - **Definition of done:** Phase 2 Issues 12 and 13 are closed, with a regression test that makes this class of error impossible to reintroduce silently.
  - **Progress notes:**
    - *2026-07-24 — PRE-1 fixed, plus a third defect the checklist did not record.* The four `query=` call sites and the `list[str]`→`str` mismatch were fixed as approved. **A third defect was found while reading the code:** `writing_tools.py` read the retrieved dicts with the keys `chapter_number` and `text`, which `retrieve_relevant_chunks()` does not produce — it returns `chapter` and `raw_summary`. `.get()` defaults swallowed both misses, so the assembled story context was `"[Ch] \n\n[Ch] …"` — no manuscript content and no exception. Fixing only the signatures would have shipped confident, fluent, entirely **ungrounded** prose, which is worse than an honest `TypeError`. Mandatory fields now use direct indexing so a future interface change raises `KeyError` instead of silently degrading. Evidence: live capture against the restored manuscript showed 2169 chars of real chapter summaries and 5128 chars of character context reaching the prompt.
    - *2026-07-24 — manual testing found two further defects; both fixed under this task.* **(a) Long continuation** returned three "Could not generate this suggestion" cards. Root cause: `max_tokens=1600` was fixed regardless of requested length, while 3 × 350 words needs ≈1600 — measured truncation on 1 run in 4, `finish_reason="length"`. Now sized dynamically, `max(1600, int(3 × continuation_length × 1.9) + 400)` → 2395 at Long; **Short and Medium remain exactly 1600, byte-identical to previous behaviour**. **(b) Outline** rendered nothing at all. Root cause: the backend returns `OutlineResponse.outline` while the frontend read `res.data.beats` and its TypeScript interface declared `beats` — so a correct 4-beat response was discarded by `undefined ?? []`, silently, with no error. Backend was never at fault. Frontend interface, read site and the client-side word minimum (3 → 10, matching the backend) all corrected.
    - *2026-07-24 — truncation no longer reports success.* New `AIResponseTruncatedError` → **HTTP 422** with an actionable message, raised only when the budget was exhausted **and** nothing parseable survived. New `_complete_ex()` exposes vLLM's `finish_reason`; `_complete()` delegates to it, so all existing call sites are unaffected. The handler emits `detail` alongside `message` because the frontend reads `e.response.data.detail`.
    - *2026-07-24 — residual reliability defect found and closed.* After the budget fix, Long still failed ~11% of the time with `finish_reason="stop"` — Qwen intermittently ends a **complete** suggestion array without its closing `]`, ~1000 tokens below the cap. Fixed with a narrowly gated structural completion (payload must start `[`, not end `]`, end `}`, and parse after appending exactly one `]`; the only mutation is the terminator) followed by **exactly one** retry when that cannot help. No retry on `finish_reason="length"`. Two attempts is a structural maximum, not a policy. **Live verification: 15 of 15 Long continuations succeeded, 0 failures, 2 retries** (was ~89%).
    - *Known limitation — retry latency.* The two retried runs took **87.4 s and 92.4 s**. If the RunPod proxy enforces Cloudflare's default 100 s origin timeout, a slightly slower retry would surface to the author as a network error. The configured value could not be confirmed from inside the pod. Unmitigated; candidate remedies (shorter retry, streaming, background job) are new scope.
    - *Known limitation — structural completion is unexercised in production conditions.* `structural_recoveries=0` across the 15-run live sample; both failures in that sample had a shape the narrow gate correctly refused, and the retry recovered them. The path is proven by unit tests and against the originally captured payload, but **the retry is the load-bearing fix**.
    - *Test coverage added:* `tests/test_retrieval_signatures.py` (18) and `tests/test_generation_limits.py` (24) — **42 tests**, no DB, no LLM, no GPU. Both run under `pytest` and via a plain `python3` harness, so no new dependency was introduced. `pytest` is still not installed on this pod.

- [x] **3.2 — Story Bible status integrity** — *completed 2026-07-26*
  - **Source:** Phase 2 Issue 8 (partial); `README.md` known issue 2; `backend/routers/story_bible.py:136–147`
  - **Area:** Backend / Database
  - **Priority:** Critical
  - **Depends on:** Stage 2
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Context — verified in code:** On `AIServiceUnavailableError` the section body becomes `"[AI temporarily unavailable — please regenerate]"`; on any other exception, `f"[Error generating {section}: {exc}]"`. Control then falls through to `:145–147` which sets `status = "completed"` and commits.
  - **Implementation checklist:**
    - [x] Enumerate every section-generation failure path in `_generate_bible_background` — *2026-07-25; 32 paths (SB-F01…SB-F32) recorded in [`docs/issues-and-bugs/story-bible-failure-path-audit.md`](./issues-and-bugs/story-bible-failure-path-audit.md). The function is actually `_generate_bible_pipeline` — see note below.*
    - [x] Track per-section success/failure during generation — *2026-07-25; `SectionOutcome` + `classify_section_result()` in `backend/routers/story_bible.py`, 19 new tests. Tracking only — status, persistence, placeholders and the external API are unchanged.*
    - [x] Set status to `partial` when some sections failed, `failed` when all failed, `completed` only when all succeeded — *2026-07-25; `derive_status()` in `backend/routers/story_bible.py`, plus the SB-F23 rollback fix. 29 tests.*
      - **Mandatory acceptance criterion — SB-F23 (user direction, 2026-07-25): ✅ CLOSED.** `db.rollback()` is now the first statement of the outer handler (`story_bible.py:287`), making `failed` reachable on the commit path for the first time. All seven required points are covered by dedicated tests: forced commit failure; rollback **before** any recovery query (asserted on recorded call order); successful re-query; status set to `failed`; recovery commit succeeds; row never left `running`; the original failure does not escape the handler. **Mutation-verified** — removing the rollback line fails 3 of the 4 commit-failure tests. See audit §5 L6.
    - [x] Add a `failed_sections` field so the UI can offer targeted regeneration — *2026-07-25; migration `0016`, `JSON` column, shape `[{"section","failure","reason"}]`. Cleared on every terminal write.*
    - [x] Never persist a placeholder string as if it were content — *2026-07-25; **SB-F16 closed** — a failed section is now absent from `content_json`, described only by `status` + `failed_sections`.*
    - [x] Surface partial state in `StoryBiblePanel.tsx` with a per-section retry — *2026-07-25; new endpoint `POST /stories/{id}/story-bible/sections/{section}` plus panel, hook, types and API client. **All 6 implementation subtasks now complete; the task stays open on two verification items.***
  - **Verification:**
    - [x] Unit test: force one section to raise; assert status is `partial`, never `completed` — *2026-07-25, `test_status_is_partial_when_some_sections_fail`; reinforced by `test_every_failure_class_prevents_completed`, which proves no failure class (unavailable, error, empty, truncated) can yield `completed`*
    - [x] Unit test: force all sections to raise; assert status is `failed` — *2026-07-25, `test_status_is_failed_when_every_section_fails`*
    - [x] Database-state check: no `story_bibles` row with `status='completed'` contains a `[` placeholder marker — *2026-07-26 verification run; **run against real data at last** — `verify_story_bible_integrity.py` PASS with 1 `completed` row on the verification copy, no longer vacuous. Re-run and re-passed after every regeneration in the run.*
    - [x] Re-run the reported QA scenario — *2026-07-26 verification run; **executed end to end**: generated a bible → killed vLLM 42 s in → status **`partial`** with one section stored and four recorded `unavailable` with author-safe reasons, **no placeholder text persisted**, content and failed sets disjoint → retried each failed section → status walked `partial → partial → partial → **completed**` as `failed_sections` emptied. Exported DOCX (41,989 bytes) contains no bracketed error text and carries 62 `[Ch N]` tags. An earlier 25-second interruption also exercised the all-fail branch: status `failed`, nothing stored.*
  - **Definition of done:** A bible marked `completed` contains only genuinely generated content.
  - **Canonical reference:** [`docs/issues-and-bugs/story-bible-failure-path-audit.md`](./issues-and-bugs/story-bible-failure-path-audit.md) — audited at commit `cb0144a`, 2026-07-25. **Every remaining subtask of 3.2 must be implemented against this document rather than re-deriving the failure paths.** Its §8 states the required per-section tracking shape, the status decision table, the schema impact and the cross-task dependencies.
  - **Progress notes:**
    - *2026-07-25 — failure-path enumeration complete (subtask 1 of 6).* Documentation only; no code, schema, API, frontend or database change. 32 paths enumerated across eight architectural layers (context construction, AI invocation, AI output validation, section assembly, persistence, transaction commit, background execution lifecycle, recovery/startup). **14 produce a false `completed`**, 4 are already correct, 3 leave a row stuck in `running`, 11 are recorded context or deferred scope. Verification: 30 `file:line` citations range-checked and 22 content-checked against the working tree; four load-bearing claims confirmed by execution rather than reading.
    - *Checklist naming — do not lose.* This task names `_generate_bible_background`; the function is **`_generate_bible_pipeline`** (`backend/routers/story_bible.py:117`). The cited lines `:136–147` remain correct. Renamed in code at some earlier point; the task title above is left as-is so the source reference stays greppable.
    - **⚠ SB-F23 — mandatory for the status subtask.** When `db.commit()` at `story_bible.py:151` fails, the outer handler at `:153` re-queries on a session that has not been rolled back, raises `PendingRollbackError`, and the `failed` status is **never written** — the row stays `running` permanently (cleared only by the startup sweep) and every retry is refused by the duplicate guard at `:194`. Confirmed by execution. **`failed` is unreachable on the commit path until `db.rollback()` is moved to the top of that handler**, so the status contract is incomplete without it. Must be resolved when the status logic is implemented, not deferred.
    - **⚠ SB-F13 — truncation is persisted as genuine content.** `generate_story_bible_section` calls `_complete()`, which discards `finish_reason`; at `max_tokens=1500` a mid-sentence fragment is stored under `completed`. The detection machinery (`_complete_ex()`, `AIResponseTruncatedError`) already exists from task 3.1 and is simply unused here. Adopting it is a precondition of the per-section tracking subtask.
    - **⚠ SB-F15 — the verification checkbox below is unsafe as worded.** A bare `[` scan false-positives on genuine prose (`[Chapter 3]`, `[Act I]`, Markdown links). Match the exact placeholder strings, or assert on `status` + `failed_sections` once placeholders are no longer persisted.
    - *Production baseline, 2026-07-25 (live, read-only):* **0 `story_bibles` rows, 0 placeholder-bearing `completed` bibles, 0% affected**; corroborated by decoding both 2026-07-24 backups. **No backfill migration or data clean-up is required by this task.** Also verified live: `status` is `character varying` with **no `CHECK` constraint**, so `partial` needs no migration — but `failed_sections` does.
    - *2026-07-25 — per-section outcome tracking complete (subtask 2 of 6).* Every section is now classified as generated or failed across four classes — `unavailable`, `error`, `empty` (SB-F12), `truncated` (SB-F13) — derived from the **response**, not only from raised exceptions, because the last two raise nothing. Outcomes live in memory and are logged as counts and section keys only; **nothing consumes them yet**. Tests: **19 new** (`backend/tests/test_story_bible_outcomes.py`), 3.1 regressions still **24/24** and **18/18**. Four of the new tests are *inertness guards* pinning that status, `content_json`, placeholders and version are byte-for-byte unchanged — **the status subtask must flip `test_status_still_completed_when_every_section_fails` and `test_status_still_completed_when_some_sections_fail`**; they are written to fail loudly rather than be quietly satisfied.
    - *⚠ Internal service contract changed — external API did not.* `generate_story_bible_section()` (`backend/services/ai_service.py:3727`) now returns **`tuple[str, Optional[str]]` — `(text, finish_reason)`** instead of `str`, delegating to `_complete_ex()` because `_complete()` discards `finish_reason` (the reason SB-F13 was undetectable). This is a **breaking in-process signature change**, made in place rather than behind an `_ex` wrapper on user direction, valid only while the Story Bible pipeline is the sole caller. A future caller assigning the result to one variable will silently receive a tuple. `test_section_generator_has_exactly_one_caller` is the tripwire. **The HTTP contract is untouched** — routes, methods, schemas, status codes and auth are identical, so no client, including the voice agent, sees a difference.
    - *Hidden-caller verification (user-directed, 2026-07-25).* Eight vectors checked before widening the signature: static references repo-wide (3 only — definition, import, single call site); **voice-agent extension point** — the `story_bible` capability is **not** in `SERVER_ADAPTERS` (`services/voice/adapters.py:110–113`) and executes client-side against the HTTP endpoint; dynamic dispatch (`getattr`/`importlib`/`__import__`/`globals()`/`eval`/`exec`) — none reaches `ai_service`; developer scripts and smoke tests; packaging entry points — none exist; Alembic migrations; frontend; and duplicate module copies — none, the `.ipynb_checkpoints` directories hold only Markdown. **No hidden callers.** ⚠ `/workspace/narratiq-ai-backup-before-claude-removal` is a **separate git repository** outside this working tree; it retains the old `-> str` signature and would need this change reapplied if ever restored or merged.
    - *2026-07-25 — terminal status now derived from outcomes (subtask 3 of 6).* `derive_status()`: 5/5 genuine → `completed`, 1–4 → `partial`, 0 or a pipeline-level abort → `failed`; no outcomes at all → `failed`. The unconditional `bible.status = "completed"` is gone. **Definition recorded precisely: placeholder text may still be persisted for failed sections for now, but a bible containing one can never be `completed` — it is `partial` or `failed`.** Tests: **29** in `backend/tests/test_story_bible_outcomes.py` (was 19), 3.1 regressions still 24/24 and 18/18, `npx tsc --noEmit` clean. This is the **first unit in 3.2 to change author-visible behaviour**.
    - *Two fixture defects found and fixed while testing.* The fake session was poisoned from construction, so three commit-failure tests were exercising a *query* failure rather than a *commit* failure; and `rollback()` did not discard uncommitted in-memory state as a real session does, letting `test_commit_failure_never_leaves_the_row_running` pass **even with the fix removed**. Both corrected — recorded because a test that passes for the wrong reason is worse than no test.
    - *⚠ Versioning consequence of `partial` — accepted, documented, not separately implemented.* `story_bible.py:350` bumps the version only when the previous status was `completed`. A bible that would previously have read `completed` (with placeholders) and bumped to v2 on regeneration now reads `partial` and is **overwritten in place**. Semantically correct — an incomplete generation should be completed, not preserved as a canonical version — and consistent with existing `failed`-retry behaviour. No code was changed for this; it follows from the status fix. Extends audit **SB-F21**.
    - *⚠ Temporary frontend gap — NOT a releasable end state, closes in subtask 6.* The database and HTTP API now expose `partial`; the UI does not yet understand it. Consequences: `StoryBiblePanel.tsx:32` falls through to the **completed** branch, and `StoryBibleWatcher` (`useStoryBible.ts:44–50`) fires **neither toast** on `running → partial` — the false *"Story Bible is ready."* is gone, but a partial result now produces **no notification at all**. `lib/types.ts:542` still declares the three-value union; the build does not break (the value arrives through an `as` cast — `tsc --noEmit` exit 0), but the type is now inaccurate. **User direction: do not move to an unrelated main task while the backend can return `partial` and the frontend still renders it as completed.** Continue directly through `failed_sections` → placeholder removal → frontend `partial`/`failed` handling → retry behaviour.
    - *Consumer compatibility verified (user-directed, 2026-07-25).* `status` is an open string everywhere — no `Literal`, no `Enum`, no `CheckConstraint`, plain `VARCHAR`. Three backend readers reviewed: `orphan_recovery.py:81` (`== "running"`, so `partial` is correctly never swept — it is terminal), the duplicate guard at `story_bible.py:330` (`partial`/`failed` correctly allow regeneration), and `story_bible.py:350` (the versioning consequence above). No other backend client, automation, background job, CLI tool, mobile client, script, packaging entry point or test assumes a closed three-value set; the voice agent does not read bible status at all.
    - *Deferred by agreement:* four stale comments still describe the value set as `running | completed | failed` — `schemas.py:1389`, `models.py:1073`, `database.py:81`, migration `0015`'s docstring. Documentation only, no runtime effect; to be corrected alongside the `failed_sections` schema work.
    - *2026-07-25 — `failed_sections` persisted (subtask 4 of 6).* Migration **`0016_story_bible_failed_sections`** adds a nullable `JSON` column; chain is now `… → 0015 → 0016 (head)`. Shape `[{"section","failure","reason"}]` — **author-facing fields only**; exception text, traces, timestamps and model diagnostics stay in the logs, verified by test. `StoryBibleOut` exposes it with a validator coercing `NULL → []`, so a client never receives `null`. **Both provisioning paths verified against the live database**: Alembic upgrade → downgrade → re-upgrade, upgrade idempotency, the `create_all` shim in `database.py`, and the real startup order (shim first, then `alembic upgrade head`) — the last matters because the live table was provisioned by `create_all`, not by `0015`. Tests: **38** (was 29); 3.1 regressions still 24/24 and 18/18. **The live database schema is now at `0016`.**
    - *Stale-failure clearing — the key correctness requirement of this subtask.* `failed_sections` is **assigned, never appended**, on the success path, and cleared on the pipeline-failure path (which carries no per-section detail). A two-run test proves a repaired bible stops reporting sections that are now fine.
    - *Expected in-progress behaviour, accepted by the user.* `failed_sections` describes the **last completed run**; it is not cleared when a new generation starts, so during a regeneration the row still shows the previous run's failures. The UI renders the running state throughout, so this is never author-visible. Acceptable intermediate condition; no change required.
    - *Historical migration note — decision recorded.* Three of the four stale `running | completed | failed` comments were corrected in place (`models.py`, `schemas.py`, `database.py`). The fourth lives in migration **`0015`'s docstring**, which documents what that migration did in June; rewriting it would falsify the record, so a **dated forward-pointer** was appended instead, noting `partial` was added later and that the unconstrained `VARCHAR` needed no schema change. Approved by the user.
    - *2026-07-25 — placeholders no longer persisted (subtask 5 of 6). **SB-F16, the root cause of this whole defect class, is closed.*** Neither `"[AI temporarily unavailable — please regenerate]"` nor `f"[Error generating {section}: {exc}]"` is written anywhere; content is stored only when the section outcome is `ok`. Raw exception text now exists **only in logs** — asserted both ways (absent from `content_json`, present in the log record, so failures stay diagnosable). Invariant tested: `content_json` and `failed_sections` are disjoint and together cover all five sections. Tests: **45** (was 38); 3.1 regressions 24/24 and 18/18; `npx tsc --noEmit` exit 0. The two `content_json` consumers were re-swept first — the panel's `?? ''` and the export's `if not text: continue` both handle an absent key, so no frontend change was needed.
    - *Truncation — **Option A**, user decision 2026-07-25, with rationale recorded.* A truncated section's prose is **dropped**, not stored; only the failure record `{"section", "failure": "truncated", "reason"}` is kept. Reasoning: the Story Bible database should hold only successfully generated, usable sections; a stored fragment would be rendered and exported as if finished; and deliberate preservation of unfinished or alternative generations belongs to the planned **pinning feature**, captured at generation time. Consequence: a truncated fragment is **not recoverable from the bible afterwards**.
    - *Side effect — the `[`-marker verification is now satisfiable by construction.* No placeholder is written to any row at any status, so **SB-F15**'s false-positive risk is gone. The remaining database-state checkbox should still assert on exact placeholder strings or on `status` + `failed_sections`, never on a bare `[`.
    - *Known limitation — historical rows.* Nothing rewrites existing bibles, so a row created before this change would keep its placeholder text under a `completed` status. Moot today (0 rows); re-check if a database holding older bibles is ever restored.
    - *2026-07-25 — partial state surfaced with per-section retry (subtask 6 of 6). **All implementation work for 3.2 is complete.*** New endpoint **`POST /stories/{id}/story-bible/sections/{section}`** — authenticated, ownership-checked, rate-limited on `rate_limit_background_ai`, 400 on an unknown section, 404 with no bible, `already_generating` while a run is in flight. Repairing a section merges it into `content_json`, updates `failed_sections`, and **recomputes the status across the whole bible** (`outcomes_from_persisted_state` → `derive_status`), so fixing the last failure yields `completed`. Frontend: partial banner, failed tabs marked, each failed section shows its author-safe reason plus a targeted regenerate button, and the `running → partial` transition now raises an honest warning toast instead of nothing. Tests: **68** (was 45), including 7 real `TestClient` endpoint tests; 3.1 regressions 24/24 and 18/18; `npx tsc --noEmit` exit 0.
    - *Three engineering decisions taken without escalation, per the new workflow.* **(a)** Background task + the existing `running` status rather than a synchronous request — one section can take up to 120 s against a ~100 s proxy timeout (a recorded 3.1 risk), and this reuses the established polling architecture with no schema change. **(b)** A failed repair **does not fail the whole bible**: the recovery handler restores the status the persisted content supports, so a broken repair attempt cannot destroy four good sections. **(c)** No version bump on repair — completing an existing bible is not minting a new canonical one.
    - *Known limitation — reload during a targeted retry.* The row is `running` for the whole bible, so a reload mid-repair shows the generic full-generation spinner; local UI state covers the normal case. Distinguishing them persistently would need a schema field and was not judged worth one.
    - *Verification 1 — database-state check: **checker proven, live assertion vacuous**.* `backend/scripts/verify_story_bible_integrity.py` (read-only) asserts: no placeholder in any row at any status — matching the **exact** strings, never a bare `[` (SB-F15); no `completed` bible naming failed sections; no `partial`/`failed` bible without explanation; no section both stored and failed; only recognised status values. **Live run passes but with 0 rows, so it proves nothing** — the script says so in its own output. The logic was therefore extracted into a pure `check_rows()` and unit-tested against known-bad rows (**7 tests**): it catches every violation class and does **not** false-positive on genuine prose containing `[Chapter 3]`, `[Act I]` or Markdown links. **Checkbox deliberately left open until run against real data (user direction).**
    - *Verification 2 — QA scenario: **environment-blocked**.* Steps for when the environment returns: generate a bible → stop vLLM mid-run → confirm `partial` with the failed sections named → retry one section → confirm it fills in and the status becomes `completed` → confirm the exported DOCX contains no bracketed error text.
    - *⚠ Task 3.2 stays open on those two verification items* — all six implementation subtasks are done; only real-environment validation remains.
    - *⚠ Verification of the remaining subtasks is environment-blocked.* The live database holds the `0015` schema but **no data** (0 stories, 0 chapters, 0 users), and the backend, frontend and vLLM are not running. Every later 3.2 verification step needs a fixture manuscript and a running stack. Tracked as an environment issue, not a defect in this task — see the Next Task section.

- [x] **3.3 — Story Bible grounding and provenance** — *completed 2026-07-26*
  - **Source:** Phase 2 Issue **8** (Critical); Master Execution Plan §5.2
  - **Area:** AI / Backend
  - **Priority:** Critical
  - **Depends on:** 3.2
  - **Blocked by:** None
  - **Can run in parallel:** No — same module as 3.2
  - **Context — verified in code:** The prompt at `ai_service.py:3646–3650` already says *"ground everything in what is actually in the text. Do not invent details not supported by the provided context."* The defect is **context starvation**: `_build_full_context()` assembles from chapter summaries truncated to **300 characters each**. The model is asked for a comprehensive timeline while shown a compressed digest, so it interpolates. Prompt-only fixes will not resolve this.
  - **Implementation checklist:**
    - [x] Raise the per-summary character budget in `_build_full_context()` and measure the resulting token count — *2026-07-25; budget derived from `max_model_len` and measured with the real Qwen tokenizer. 4 chapters: 375→**2,039** tokens; 40 chapters: 3,349→**4,839**; 200 chapters: **18,991 (2.3× over the 8,192 window!) → 5,299**, i.e. the old code was already guaranteed to 400.*
    - [x] Add chapter provenance to every context entry so the model can cite it — *2026-07-25; `[Ch 7]`, `[Character: …]`, `[Note: …]`, `[Card: …]`.*
    - [x] Require each bible entry to carry a source chapter reference — *2026-07-25; four system-prompt rules plus per-section citation targets.*
    - [x] Add an explicit "not established in the manuscript" output convention instead of gap-filling — *2026-07-25; `BIBLE_NOT_ESTABLISHED`, fixed and greppable.*
    - [x] Add a post-generation check flagging timeline events with no chapter reference — *2026-07-25; `audit_section_provenance()`, **logged only** by user decision — no column, no migration, no UI.*
    - [x] Handle context-window limits — chunk or summarise rather than truncate silently — *2026-07-25; max–min fair allocation, even sampling across the manuscript, the ending always kept, and a `WHAT YOU ARE NOT SEEING` block naming what was omitted.*
  - **Verification:**
    - [x] AI-output validation: generate a bible on a fixture manuscript with known content; assert zero events absent from the source — *2026-07-26 verification run; **11/11 timeline events** had every proper noun present in the chapter they cite; **0 events unsupported** anywhere in the manuscript. Measured twice — before and after the provenance prompt work — with the same result (12/12 then 11/11).*
    - [x] Assert every bible entry carries provenance — *2026-07-26 verification run; **117/117 entries cited, ratio 1.00 in all five sections**. First live measurement **failed at 0.37** (characters 0.00, locations 0.33, world_rules 0.75) and was corrected under approved corrective plan B — see the note below. The criterion was **not** relaxed.*
    - [x] Author review confirms no unsupported detail — *2026-07-26; **author-confirmed**: the generated bible is grounded in the source, with no unsupported facts, fabricated events or invented characters. The author noted minor **interpretation and summarisation quality** observations — explicitly **not** hallucinations and out of Stage 3 scope; carried to new task **4.16**.*
  - **Definition of done:** The Story Bible states only what the manuscript supports, and marks uncertainty explicitly.
  - **Progress notes:**
    - *2026-07-25 — all six implementation subtasks complete; **all three verification items intentionally left open**, each requiring live AI validation on a real manuscript with a running backend, frontend and vLLM.* No database, API or frontend change; no new dependency. Tests: **89** in `backend/tests/test_story_bible_outcomes.py` (was 68); 3.1 regressions 24/24 and 18/18; integrity checker PASS; `npx tsc --noEmit` exit 0.
    - *Token measurement — the defect quantified.* `count_tokens()` uses the **real Qwen tokenizer** from `settings.qwen_path` (already on disk — no new dependency), lazily cached, with a deliberately **pessimistic** fallback because under-estimating costs a failed generation while over-estimating costs only unused context. Budget = `max_model_len − 1500 (completion) − 900 (prompt overhead)`. Measured at `max_model_len=8192` (budget 5,792): 4 chapters **375 → 2,039** tokens; 40 chapters **3,349 → 4,839**; 200 chapters **18,991 → 5,299**. The 200-chapter figure matters most: **the old assembly produced 2.3× the context window**, so a large manuscript was already a guaranteed vLLM 400 — audit **SB-F08**, live before this task.
    - *Engineering decisions taken without escalation.* **(a) Max–min fair allocation** (`fair_share`) so one enormous chapter cannot starve thirty others — the failure mode that hit the timeline hardest. **(b) Even sampling across the whole manuscript** rather than a prefix when not every chapter fits: a bible built from act one is a different kind of wrong. **(c) The final chapter is always kept** — stride sampling otherwise never includes it, and a bible that stops before the climax describes a different book. **(d)** Character/note/card per-field caps raised (150→400, 300→600 chars) inside the same measured budget, and those entries tagged too — they were previously unlabelled as well.
    - *⚠ A defect introduced and caught during implementation, recorded rather than hidden.* The first allocator produced, at 200 chapters, a context of **61 tokens — no manuscript at all**: per-entry overhead exceeded the character budget, every summary fell below the floor, and all were dropped. That would have been **worse than the original defect** — a bible generated from nothing but the omission notice. Caught by the measurement step this subtask required, not by a test that had been written in advance. Fixed with capacity-based sampling and pinned by `test_a_huge_manuscript_never_yields_an_empty_context` at 200 and 1000 chapters.
    - *Audit payoff — SB-F15 prevented a collision.* Provenance tags put bracketed text back into bible content. Under the checklist's original bare-`[` detector this would have fought the 3.2 work head-on; because SB-F15 forced exact-string matching, the integrity checker remains correct with no rework.
    - *Known limitations.* No live generation, so **whether Qwen actually complies with the citation rules is unverified**. Very large manuscripts still lose chapters (200 → 50 kept) — visible, never silent, but true summarise-of-summaries is a larger design and out of scope. The prompt grew, and more rules can dilute instruction-following. `max_model_len` defaults to 8192; the 2-GPU pod sets 16384, which nearly doubles every figure above.

- [x] **3.4 — Degraded-output contract for AI features** — *completed 2026-07-26*
  - **Source:** Phase 2 Issues **2** (plot holes) and **14** (continuity); Master Execution Plan §5.3
  - **Area:** AI / Backend
  - **Priority:** High
  - **Depends on:** Stage 2
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Context — verified in code:** `_extract_json()` (`ai_service.py:272–310`) is already robust — clean parse → fence strip → all balanced spans → trailing-comma repair. The failure is at the caller: `ai_service.py:1589–1594` raises `ValueError` when the schema does not match. Confirmed that `plot_holes.py` and `analysis.py` do **not** use retrieval helpers, so these two issues are genuinely the schema class, unlike Issues 12/13.
  - **Implementation checklist:**
    - [x] Define the degraded-output contract: coerce → one bounded reprompt → partial result with `degraded: true` — *2026-07-25; `complete_structured()` + `DegradedMeta` in `ai_service.py`, reusable by every structured call site.*
    - [x] Replace the `raise ValueError` at `ai_service.py:1591–1594` with the contract — *2026-07-25; done at the **real** site, `_strategy_single_pass` — the cited line was wrong, see notes.*
    - [x] Apply the contract to continuity analysis — *2026-07-25; `check_continuity` now returns `(issues, meta)`; the silent `[]` fallback is gone, and per-chunk degradation is aggregated.*
    - [x] Return partial findings rather than nothing when only some entries parse — *2026-07-25; entry-level salvage with a discard count; truncated arrays salvaged too.*
    - [x] Surface `degraded: true` in the UI as an honest partial-result banner — *2026-07-25; banners in both panels, and the green clean-result states now render only when `degraded` is false.*
    - [x] Ensure a genuine failure returns an actionable message, never a raw stack trace — *2026-07-25; `detail=str(exc)` removed from `plot_holes.py`; exception detail to logs only.*
  - **Verification:**
    - [x] Unit test with deliberately malformed model output — asserts partial result, not exception — *2026-07-25; `backend/tests/test_degraded_output.py`, **25 tests**.*
    - [x] Manually run plot hole detection — usable results returned — *2026-07-26 verification run; **3 substantive findings** across 4 chapters (character inconsistency, timeline inconsistency, continuity break — each naming its chapters), `degraded: false`. Phase 2 Issue 2 closed.*
    - [x] Manually run continuity analysis — usable results returned — *2026-07-26 verification run; **2 issues** returned (character appearance, timeline), `degraded: false` — so the honest-degradation banner correctly stayed off. Phase 2 Issue 14 closed.*
  - **Definition of done:** Phase 2 Issues 2 and 14 are closed; no AI feature returns nothing when it could return something.
  - **Progress notes:**
    - *2026-07-25 — all six implementation subtasks complete; the unit-test verification is closed, **both manual verification items intentionally left open** pending a real manuscript and a running vLLM.* `complete_structured()` + `DegradedMeta` in `ai_service.py` implement the contract once and are reused by both features — deliberately, so **task 3.5's audit has a single thing to point every remaining hard-fail at**. Tests: **25** in `backend/tests/test_degraded_output.py`; Story Bible 89/89, 3.1 regressions 24/24 and 18/18, integrity checker PASS, `npx tsc --noEmit` exit 0. No database change; API changes are **additive only** (`degraded`, `degraded_reason` on `PlotHoleResponse` and `ContinuityCheckResponse`).
    - *⚠ Checklist discrepancy 1 — the cited line is wrong (recorded, not silently corrected, per user direction).* This task says *"Replace the `raise ValueError` at `ai_service.py:1591–1594`"*. At commit `cb0144a` — the revision this checklist was written against — lines 1585–1596 are a **comment block** in the plot-hole strategy registry, verified with `git show`. The real sites were **1654** (`_strategy_single_pass`, plot holes — the actual target, fixed here) and **1570** (`generate_plot_suggestions`, the **Plot Assistant** — a different feature, left for 3.5). **Proposed wording:** *"Replace the `raise ValueError` in `_strategy_single_pass` (`ai_service.py:1654` at `cb0144a`)"*.
    - *⚠ Checklist discrepancy 2 — the two issues are different defect classes.* The Context above frames both as the schema/hard-fail class. In fact **Issue 2 (plot holes) hard-failed** — `raise ValueError` → HTTP 503, discarding findings that had parsed — while **Issue 14 (continuity) silently returned `[]`** via `_extract_json(raw, fallback=[])`, so the panel displayed *"No continuity issues detected. Great consistency!"* when the model's output was unreadable. The silent-fallback case is the more damaging of the two and is precisely the class **task 3.5** exists to enumerate. **Proposed wording:** *"Issue 2 is the hard-fail class; Issue 14 is the silent-fallback class."*
    - *⚠ Checklist discrepancy 3 — an unmentioned third factor.* Continuity runs **chunked and in parallel** for >10 chapters (`analysis.py:186–212`). A chunk that failed returned `[]` and was indistinguishable from a clean chunk, so a 40-chapter manuscript could silently analyse three of its four chunks. Per-chunk degradation is now aggregated and reported as *"N of M sections could not be fully checked"*.
    - *Engineering decisions taken without escalation.* **(a)** One shared helper rather than per-feature handling. **(b)** Exactly one reprompt — asserted on call count, because a model that cannot produce the shape twice will not produce it on the fifth try and the author is waiting. **(c)** Partial beats exception; raising is reserved for nothing-usable-at-all. **(d)** **Truncated findings are salvaged**, deliberately unlike 3.1's continuation handling: a truncated *list of findings* is useful, a truncated *sentence* is not. **(e)** Coercion accepts the documented shape, a bare array, or a single-array wrapper, but **refuses to guess between two arrays** — picking one would be inventing structure. **(f)** Only *presentation* fields are defaulted (id, severity, suggestion); a finding with **no description is dropped, never invented**.
    - *The UI change that matters most is a negative condition.* The green "No issues detected" / "Great consistency!" states now render **only when `degraded` is false**. A degraded empty result reads "No issues could be read from this scan" — the difference between "your manuscript is clean" and "we could not check it".
    - *Known limitations.* No live run: whether Qwen's real malformed output matches the shapes coercion accepts is unverified — the coercers were written against shapes models plausibly emit, not against captured failures. The reprompt roughly doubles latency on the failure path. `generate_plot_suggestions` still carries the identical anti-pattern, left for 3.5 as agreed. Banner fatigue is unmeasured until logs exist.

- [x] **3.5 — Audit every `_extract_json` caller for the hard-fail pattern** — *completed 2026-07-25*
  - **Source:** Master Execution Plan §5.3 recommendation
  - **Area:** AI / Backend
  - **Priority:** High
  - **Depends on:** 3.4
  - **Blocked by:** None
  - **Can run in parallel:** No
  - **Context:** The four reported features are a sample, not the population. Establish the true scope before declaring the class fixed.
  - **Implementation checklist:**
    - [x] Grep every `_extract_json` call site in `ai_service.py` and the routers — *2026-07-25; **17 sites**, 14 of them feature code — see the register below*
    - [x] Classify each as hard-fail / silent-fallback / handled — *2026-07-25; **5 hard-fail, 7 silent-fallback, 2 handled, 3 infrastructure***
    - [x] Apply the 3.4 contract to every hard-fail site — *2026-07-25; all 5 converted with per-site coercers. **None of the 5 was among the four reported issues** — the sample really was a sample*
    - [x] Flag every silent-fallback site — a silent empty result is its own defect class — *2026-07-25; 7 flagged with symptom and destination task; **behaviour deliberately unchanged** — each belongs to the task that owns its feature*
    - [x] Record the audit result in the tracker — *2026-07-25; register below, and enforced in `backend/tests/test_extract_json_audit.py` so it cannot go stale*
  - **Verification:**
    - [x] Every call site has a recorded classification and a handled outcome — *2026-07-25; the register is executable — a new unregistered caller fails the suite*
  - **Definition of done:** No AI feature can fail opaquely on model output shape. — **MET 2026-07-25.**
  - **Progress notes:**
    - *2026-07-25 — task complete, including its verification. **The first Stage 3 task since 3.1 to close fully*** — nothing in it was environment-blocked. Tests: **21** in `backend/tests/test_extract_json_audit.py`; suite totals 21 + 25 + 89 + 24 + 18; `npx tsc --noEmit` exit 0. No database, API or frontend change.
    - **The audit register — 17 call sites, 14 in feature code.** The Context above was right: the four reported features were a sample. **Five hard-fail sites remained and none of them was among the four reported issues.**

      | Class | Sites | Outcome |
      |---|---|---|
      | **Hard-fail → converted** | `generate_suggestions`, `generate_plot_suggestions`, `analyze_copyright_risk`, `_strategy_manuscript_summary_pass`, `generate_chapter_summary` | All 5 now use `complete_structured()` with per-site coercers |
      | **Silent-fallback → flagged** | `extract_cast` (→Stage 4), `enrich_character_from_story` (→Stage 4), `build_character_arc_timeline` (→Stage 4), `_parse_suggestions` (→Stage 5), `generate_chapter_outline` (→Stage 5), `extract_narrative_threads_from_summaries` (→Stage 7), `voice/intent.py` (→task 3.6) | Recorded with symptom + destination; **behaviour unchanged by design** |
      | **Handled** | `generate_ocr_suggestions` (logs, then a deterministic difflib fallback), `voice/planner.py` | The model to copy — degrades deliberately and says so |
      | **Infrastructure** | `complete_structured` ×2, `_complete_json` | The approved path |

    - *The register is **executable**.* `test_no_new_direct_extract_json_callers` resolves every `_extract_json` call to its enclosing function and fails on anything not in the register, so a new feature must use `complete_structured()` or justify a row in review (user requirement 3).
    - *⚠ **Privacy finding — manuscript-derived text was being written to logs.*** All five hard-fail sites logged `raw[:300]`, i.e. model output derived from the author's manuscript — and so did **`_extract_json` itself**, which fires **system-wide on every parse failure**, plus `detect_genre`, `extract_cast`, `enrich_character_from_story` and `build_character_arc_timeline`. **Ten log statements scrubbed** to metadata only (`chars=%d`, `finish_reason=%s`); character *names* were replaced with truncated IDs, an unpublished character's name being the author's material too. A test now fails on any `logger` line containing `raw[:N]`/`text[:N]` (user requirement 2). This was a live confidentiality gap against the project's own rule that manuscripts are confidential unpublished works.
    - *Parser metrics added (user requirement 1).* `parser_metrics()` counts per feature: `clean`, `salvaged`, `truncated`, `reprompted`, `failed`, `calls`, `entries_discarded`, each emitting `parse_metric feature=… outcome=… attempts=… discarded=…`. Counters only, no content. In-process and reset on restart — sufficient for log-based observability; a future diagnostics view can read it unchanged.
    - *`generate_chapter_summary` given extra scrutiny (user requirement 4).* Justified: it runs at **index time**, so a schema hiccup made a chapter invisible to every retrieval, grounding and continuity feature until re-indexed. 8 dedicated tests. Notably, `"Devika, Arun"` is now normalised to a list — models return that routinely and dropping it silently lost a chapter's cast. The hard failure is **retained** on purpose: a chapter with no usable summary must not be indexed as if it had one.
    - *⚠ Two latent production bugs found and closed (pre-existing, not regressions).* **(a)** `plot_assistant.py:204` indexes `s["id"]`, `s["text"]`, `s["rationale"]` directly — a model omitting `rationale` was a `KeyError` → 500. **(b)** `ai_transform.py` does `Suggestion(**s)` where `category` and `reason` are required — omitting either was a `ValidationError` → 500. Both closed by guaranteeing presentation fields in the shared coercer. Its `detail=str(exc)` was also replaced with fixed author-facing text, matching 3.4's fix to `plot_holes.py`.
    - *Known limitations.* No live run — coercers are written against shapes models plausibly emit, not captured failures. The seven silent-fallback sites still lie quietly by design (`extract_cast` returning nothing still reads as "your manuscript has no characters" until Stage 4). The register is keyed by function name, so a rename needs a register update — the test will say so.

- [x] **3.6 — Voice agent action execution** — *completed 2026-07-26; implementation 2026-07-25, verification 2026-07-26.*
  - **Source:** Phase 2 Issue **4** (High)
  - **Area:** Backend / AI
  - **Priority:** High
  - **Depends on:** Stage 2
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [x] Trace transcription → intent → planner → orchestrator → adapter for a failing utterance — *2026-07-25; full static trace, plus per-stage decision logging so the intermittent fault is diagnosable live. **No failing utterance is recorded in the QA report**, so the trace is of the pipeline, not of a captured failure*
    - [x] Identify where intent resolution or routing drops the request — *2026-07-25; six drop points enumerated and each given its own distinguishable status. **Three hypotheses were raised and falsified** — routing is sound; see notes*
    - [x] Fix intent classification for the reported utterance classes — *2026-07-25; `voice/intent.py` adopts the 3.4 structured contract — an unreadable classification no longer becomes a silent guess at confidence 0.4*
    - [x] Ensure every resolved intent maps to a real capability in `capabilities.py` / `catalog.py` — *2026-07-25; already true, now **enforced**: 58/58 client executors, 3/3 server adapters, and `disambiguate_action` cannot emit a non-existent action*
    - [x] Return an explicit "I could not map that request" instead of silently doing nothing — *2026-07-25; `none` carries a stated reason, and the executor's `ok:false` now **reaches the backend** — which it never did before*
  - **Verification:**
    - [x] Integration test per supported voice intent asserting the correct adapter is invoked — *2026-07-25; registry↔executor and registry↔adapter coverage enforced by test*
    - [x] Manual: "create a chapter called Storm" actually creates the chapter — *2026-07-26 verification run; **failed on first run and passed after a fix** — see the corrective note. Final: intent `chapter_mgmt.create` with `title` extracted → confirm HTTP 200 (task `executing`, command still `needs_confirmation` — approval is not success) → executor creates the chapter → result reported → node and command `succeeded`, chapter present.*
    - [x] Database-state check confirming the mutation occurred — *2026-07-26 verification run; the chapter row exists **and** the command row records the execution that produced it. On the first run the chapter existed while the command still read `awaiting_confirmation` — data changed with no record of it — which is why this item initially failed.*
  - **Definition of done:** A recognised utterance either executes the correct action or explains why it cannot.

- [x] **3.7 — Voice agent success reporting must reflect reality** — *completed 2026-07-26; implementation 2026-07-25, verification 2026-07-26.*
  - **Source:** Phase 2 Issue **5** (High)
  - **Area:** Backend
  - **Priority:** High
  - **Depends on:** 3.6
  - **Blocked by:** None
  - **Can run in parallel:** No — same subsystem
  - **Context:** A false success is worse than an honest failure — the author believes their data changed when it did not.
  - **Implementation checklist:**
    - [x] Derive the success message from the adapter's actual return value, never from plan completion — *2026-07-25; **R1 closed** — `agent.py` no longer writes `status = "success"` at plan time*
    - [x] Treat a `None` or error adapter result as failure — *2026-07-25; **R3 closed** — `.get("answer", "Done.")` is gone; an empty adapter result is `failed` with a reason*
    - [x] Ensure `_summarize_result` cannot report success on an empty result — *2026-07-25; **it was dead code** returning "Done." for any result and called from nowhere — deleted; the guarantee now lives where the message is produced. See the discrepancy note*
    - [x] Return a specific failure reason to the user — *2026-07-25; the reason travels executor → result report → `result_summary` → author; author-safe text only, internals to logs*
    - [x] Audit `awaiting_confirmation` transitions for the same assumption — *2026-07-25; **R4 closed** — approval → `executing`, decline → `skipped`; one applied node no longer completes a whole workflow*
  - **Verification:**
    - [x] Integration test: force an adapter failure, assert the user-facing message reports failure — *2026-07-25; covered in `backend/tests/test_voice_execution.py`*
    - [x] Database-state check: no success message without a corresponding data change — *2026-07-26 verification run; **verified live in both directions**: a reported failure yields node `failed`, command `failed`, and **no chapter created**; a reported success yields `succeeded` **and** a real chapter row. Initially **failed** — both recording endpoints returned HTTP 500 — see the corrective note.*
  - **Definition of done:** The voice agent never claims an action succeeded unless it did.
  - **Progress notes (Tasks 3.6 + 3.7 — implemented together, 2026-07-25):**
    - *Implemented as one pass by user approval*, because both act on the same pipeline and splitting them would mean touching the same files twice. **All ten implementation subtasks are complete; two verification items closed, three left open and marked blocked.** Tests: **44** in `backend/tests/test_voice_execution.py`; totals 44 + 21 + 25 + 89 + 24 + 18; `npx tsc --noEmit` exit 0; `main.py` imports clean. **No migration, no new dependency.** New file: `backend/services/voice/lifecycle.py`.
    - **Lifecycle architecture (user requirement 1).** All status changes now go through one state machine, `services/voice/lifecycle.py`, instead of being assigned in five places with no rules. Vocabulary: `planned → ready | awaiting_confirmation | needs_input | blocked → executing → succeeded | failed | skipped`. **`SUCCEEDED` is reachable from `EXECUTING` and nowhere else** — proven by a test that iterates every other status. Terminal statuses are terminal, so a **retry is a new command**: `failed → executing` is rejected, which stops a late or duplicated report resurrecting a node and turning a recorded failure into a success. Invalid transitions raise and **do not mutate state** (user requirement 5). A test asserts `orchestrator.execute` contains zero direct `node.status =` assignments.
    - **The five confirmed root causes of the false success, all closed.** **R1** `agent.py:167` set `status = "success"` when the *plan was built* — client nodes were `ready`, results `None`, nothing had run. **R2** non-confirmation nodes **never reported back**: `voiceApi.confirm` was only called on the confirmation path, so read/analyze/generate outcomes never reached the backend — **the channel did not exist**. **R3** `.get("answer", "Done.")` reported an empty or `None` adapter result as success. **R4** `confirm_command` conflated *approval* with *success*, and one applied node set the whole workflow `completed`. **R5** `VoiceCommand.status` **defaulted to `"success"`** — optimistic from row creation. Now: status is derived, approval and outcome are separate facts, and the default is `planned`.
    - **Result-reporting protocol (user requirement 5 of the plan).** New additive endpoint `POST /api/voice/commands/{command_id}/nodes/{node_key}/result` `{ok, message, error_code}`, used by **both** paths — `runPlan` reports every executed step, and the confirmation path reports approval and outcome separately. Server-locus nodes resolve in-process from the adapter's return value. Validation (user requirement 2): authenticated user owns the command, the workflow belongs to the command, the node belongs to the workflow, and the node is **still active** — a terminal node returns `recorded: false` and changes nothing. Command and workflow status are **derived** from their tasks, never assigned.
    - **Timeout behaviour (user requirement 3).** `voice_execution_timeout_seconds` (default 180). A node handed to the browser and never reported on becomes `failed` with an actionable author-safe reason — the author closed the tab, the network dropped, the browser crashed; all are silence, and **silence is not consent to claim success**. Startup orphan recovery sweeps survivors (`VoiceTask` `executing → failed`). **`awaiting_confirmation` is deliberately exempt**: an author who has not answered has not timed out, they are thinking.
    - **Privacy-safe logging (user requirement 4).** Every transition logs `prev`, `new`, `source`, `reason`, `at`, so a disputed outcome is reconstructable from the log alone. Stage decision logs record capability, action, confidence and candidate count — **never the author's spoken words**, which are about their unpublished manuscript. A test extracts every `logger.*` call in `intent.classify` and fails if it references the command, prompt, brief or transcript. Continues the rule established by task 3.5.
    - *⚠ **Checklist discrepancy — `_summarize_result` was dead code.*** The 3.7 subtask *"Ensure `_summarize_result` cannot report success on an empty result"* targets `orchestrator.py:134`, a function that returned `"Done."` for any result and was **called from nowhere** (grep: definition only). Fixing it would have changed nothing. The live equivalent was `node.user_message = (result or {}).get("answer", "Done.")` (R3). The dead function was deleted and the guarantee placed where the message is actually produced. **Proposed wording:** *"Ensure the node's user_message cannot report success on an empty adapter result (`orchestrator.py`); `_summarize_result` is dead code — delete it."* Recorded, not silently applied, per user direction.
    - *⚠ **Three hypotheses raised and falsified before planning** — recorded so they are not re-investigated.* (a) *Client actions have no frontend executor* — **false**, 58/58 covered. (b) *The intent layer emits actions absent from the registry* — **false**, zero invalid pairs across the registry. (c) *`needs_confirmation` is a method used as a truthy property* — **false**, all three call sites call it correctly. Routing is sound, which is consistent with the QA report's wording (*"does not **consistently** interpret"*) and is why the fix is honesty about outcomes rather than a routing repair.
    - *⚠ **Issue 4's root cause is diagnosable, not diagnosed.*** No failing utterance was recorded in the QA report, and the pipeline cannot be exercised without the stack. Stage logging now makes one session's log sufficient to identify the drop point. **This is not a claim that Issue 4 is fixed** — it is a claim that a request can no longer stop silently, and that the agent can no longer say it worked when it did not.
    - *Side effect worth noting:* the 3.5 audit register caught `voice/intent.py` leaving the `_extract_json` census when 3.6 converted it — the guard test working exactly as intended. Register updated.
    - *2026-07-26 — **completion approved by the user**; test evidence re-run against the rebuilt runtime.* The 2026-07-25 figures were recorded on the previous container. Re-run today with the backend dependencies reinstalled: `test_voice_execution.py` **44/44**, and the full Stage 3 regression set **221/221** — audit 21, degraded output 25, story bible 89, generation limits 24, retrieval signatures 18. **No code changed on 2026-07-26**; this is re-verification of committed work (`ba822c3`), not a new implementation. **Three verification items stay open and unticked** — 3.6's manual "create a chapter called Storm" and its database-state check, and 3.7's live database-state check. All three need a manuscript in the live database; the stack itself is no longer the blocker.


- [x] **3.8 — PRE-2: selection toolbar lifecycle and sidebar deference** — *completed 2026-07-26*
  - **Source:** Phase 2 Issues **1** and **11**; Phase 3 spec §7.4 (PRE-2)
  - **Area:** Frontend
  - **Priority:** High
  - **Depends on:** Stage 2
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Context:** Fix both issues together — same component, contradictory required behaviours. Phase 3A rewrites this component substantially (pin, regenerate, lock, compare), so fixing the lifecycle now avoids fixing it twice. Phase 3 decision **D7** recommends folding these together.
  - **Implementation checklist:**
    - [x] `SelectionToolbar.tsx` — dismiss immediately on deselection — *2026-07-26; whitespace-only drags ignored, Escape dismisses from every state, a new selection resets menu/dismissal/preview*
    - [x] Suppress the toolbar entirely while the AI Assistant sidebar is open — *2026-07-26; suppressed while the sidecar is **visible** (so Focus/Zen hand it back), and the sidebar's scope indicator made live so deference does not hand the selection to a stale surface*
    - [x] Ensure the toolbar never overlays essential editor controls — *2026-07-26; moved from `top-2` (over the formatting bar, save status and **Save**) to a measured, clamped bottom rest, and out of the scroll container so it cannot drift*
    - [x] Evaluate making it draggable (reported as desirable, not required) — *2026-07-26; **implemented, session-only** — pointer drag, clamped live, double-click to reset. Persistence was **removed on user direction**: a component Phase 3A will redesign does not need a localStorage schema, migration and rollback story to be draggable*
    - [x] Verify a single consistent interaction flow for selection-based AI actions — *2026-07-26; one rule in `lib/selectionOwnership.ts`, asked by every surface. Audit: no third selection surface exists on the editor (the voice panel is on `/assistant`, the Command Palette has no selection action, there is no TipTap BubbleMenu), and the sidebar exposes a **superset** of the toolbar's transform groups, so deference costs the author nothing*
  - **Verification:**
    - [x] Playwright test: select → toolbar appears; deselect → toolbar disappears — *2026-07-26; **executed** against the running stack, Chromium 1223*
    - [x] Playwright test: sidebar open → toolbar suppressed — *2026-07-26; **executed**, both directions plus the sidebar-already-open case*
    - [x] Manual check against the reported QA scenario — *2026-07-26; **user-confirmed** ("everything is working correctly")*
  - **Definition of done:** Exactly one interface handles a text selection at any moment. — **MET 2026-07-26.**
  - **Progress notes:**
    - *2026-07-26 — task complete including verification. **The third Stage 3 task to close fully**, after 3.1 and 3.5.* New: `lib/selectionOwnership.ts` (the ownership rule, selection-safe contract, preview identity) and `lib/toolbarPosition.ts` (clamping, default rest, menu direction) — split so neither is a miscellaneous utility. Modified: `SelectionToolbar.tsx` (rewritten), `write/page.tsx`, `AISidecar.tsx`, `AIToolsSidebar.tsx`, `EditorWithMethods.tsx`, `StoryContextEngine.tsx`, `playwright.config.ts`. No backend, database, API or prompt change.
    - *Tests: **61 unit** (33 new across `selection-ownership.spec.ts` and `toolbar-position.spec.ts`, 19 pre-existing, 9 preview-validity), **17 browser** (`tests/browser/`, all executed), `npx tsc --noEmit` exit 0, production build exit 0.* The Playwright config now has two projects — `unit` (no browser, the default) and `browser` (opt-in, needs binaries + a fixture story) — so a browser check can never be reported as passing without having run.
    - **Manuscript safety strengthened beyond the task description.** A preview is bound to `(chapter, range, exact source text)`. Apply re-checks all three at the moment of writing via a new `getTextInRange()` on the editor bridge and refuses if the author edited the passage meanwhile; a superseded generation can no longer produce a preview; and a generation that lands after a chapter switch is discarded with an author-facing explanation. **Two latent defects were closed here that neither QA issue mentions:** the selection carried no chapter identity (a preview could be applied to a different chapter's offsets), and `EditorWithMethods` stamped every selection with the *first* chapter's id because its listener closed over a stale prop.
    - *Selection-safe contract.* Clicking a surface that consumes the selection (the sidebar, the toolbar, the sidebar toggle) no longer reads as abandoning the selection. Declared by a `data-selection-safe` attribute, so a future surface opts in without the workspace knowing about it.
    - *Observations recorded, not fixed (out of scope):* the Zen-mode button is labelled "Exit Zen (Esc)" but no Escape handler is wired for it, and the sidecar toggle is labelled ⌘\ while `StudioShell`'s keymap only binds ⌘K, ⌘. and ⌘1–7.
    - *Environment note.* The 2026-07-24 dump was restored on 2026-07-26 (a pre-restore dump of the empty database was taken first, checksums re-verified) and Chromium plus its system libraries were installed. A **separate synthetic fixture account** carries the browser tests, so no restored manuscript content appears in any test, screenshot, log or report.

- [x] **3.9 — Writing analytics page scrolling** — *completed 2026-07-26*
  - **Source:** Phase 2 Issue **3** (Medium)
  - **Area:** Frontend
  - **Priority:** Medium
  - **Depends on:** Stage 2
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Implementation checklist:**
    - [x] Identify the container preventing vertical overflow on the analytics view — *2026-07-26; `StudioShell.tsx:161` renders every workspace inside `<main … overflow-hidden>` within an `h-screen … overflow-hidden` shell (`:64`), while `analytics/page.tsx` was written standalone — `min-h-screen`, a **`fixed`** nav and `pt-24`. `min-h-screen` creates no scroll container, so everything past the first viewport was clipped*
    - [x] Apply correct overflow handling so all sections are reachable — *2026-07-26; conformed to the Studio contract used by `analyze/page.tsx`: `h-full flex flex-col` → in-flow header (`flex-shrink-0`) → **one** scroll region (`flex-1 min-h-0 overflow-y-auto`). No page-specific workaround, no nested scrollers*
    - [x] Verify at narrow and short viewport sizes — *2026-07-26; 1366×768, 1180×720, 1024×640 and 1024×560, all asserted geometrically*
    - [x] Confirm future analytics sections remain reachable as content grows — *2026-07-26; the test targets **the last section**, not a fixed height, so added sections stay covered without layout changes*
  - **Verification:**
    - [x] Playwright test asserting the last analytics section is scrollable into view — *2026-07-26; **executed** — `tests/browser/analytics-scroll.spec.ts`, 9/9 pass*
    - [x] Manual check at 1366×768 and smaller — *2026-07-26; verified at four viewports with bounding-box and `toBeInViewport` assertions plus attached screenshots; **user-approved 2026-07-26***
  - **Definition of done:** All analytics content is accessible at any viewport size. — **MET 2026-07-26.**
  - **Progress notes:**
    - *2026-07-26 — task complete including verification.* One production file changed (`analytics/page.tsx`); one test file added. No backend, database, API, dependency or component-API change. Tests: **9** new browser, full browser project **26/26**, unit **61/61**, `tsc` exit 0, production build exit 0, backend regression **221/221**, services healthy.
    - *Also asserted, beyond the task description:* exactly **one** vertical scroll container on the page (detected by computed style, so a nested scrollbar fails the test), the window itself never scrolls, the header never overlaps the scroll region at any scroll position, wheel scrolling works, and back/forward navigation leaves the page scrollable.
    - *Observations recorded, not fixed (out of scope).* **(a)** Native window scroll-restoration does not apply to this page — the studio owns the viewport and workspaces scroll an inner container; this is the established contract for every workspace, not new here. **(b)** Entering Focus or Zen re-lays out the panel group and the editor reloads content, dropping a live text selection; pre-existing, ownership rule unaffected, natural fit for Stage 8. **(c)** The analytics route is reachable from exactly one button (`analyze/page.tsx:63`) and is not in the workspace registry — an information-architecture question for task 8.8.

- [x] **3.10 — OCR upload interface renders** — *completed 2026-07-26*
  - **Source:** Phase 2 Issue **6** (High)
  - **Area:** Frontend
  - **Priority:** High
  - **Depends on:** Stage 2
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Context:** `frontend/components/ocr/OCRPanel.tsx` exists — diagnose why it renders empty rather than assuming the feature is unbuilt.
  - **Implementation checklist:**
    - [x] Reproduce the empty panel and capture the browser console error — *2026-07-26; reproduced on two stories side by side. With chapters: 1 file input, full UI. **Without chapters: 0 file inputs, empty area, and a clean console** — no error to capture, which is itself the evidence*
    - [x] Check whether the dynamic import or a data fetch fails — *2026-07-26; **neither**. No page error, no failed request, and the same `next/dynamic` chunk renders the panel fine when a chapter exists. The cause is a render guard, not a load failure*
    - [x] Fix the render path so the file upload control appears — *2026-07-26; `world/page.tsx:38` gated the whole panel on `activeChapterId`, which is null **while chapters load** and **for any story with no chapters** (`StoryContextEngine.tsx:144-146`). Gate removed; `chapterId` is now nullable and only the one destination that needs it is disabled*
    - [x] Verify supported formats are accepted — *2026-07-26; the `accept` attribute matches the backend exactly. **Mismatch found and reported, deliberately not changed:** the runtime guard (`OCRPanel.tsx:62`) accepts any `image/*`, so GIF/BMP/TIFF/SVG pass the client and are refused by the server with a 400 — matters mainly for drag-and-drop. Awaiting a decision on which side to align*
    - [x] Verify extracted text can be reviewed and injected into all four destinations — *2026-07-26; all four confirmed **at database level**, not by response code: `story_notes` (1 row), `note_card` (1 row), `character_profile` (character + profile row), `chapter_draft` (content 356→396 chars, marker present). `chapter_draft` without a chapter id correctly refused with 400*
  - **Verification:**
    - [x] Playwright test: OCR panel renders an upload control — *2026-07-26; **executed** — `tests/browser/ocr-panel.spec.ts`, 5/5, including the no-chapter story that used to render nothing*
    - [ ] Manual end-to-end: upload an image → text extracted → injected into the editor — *⛔ **the image→text half cannot run**: extraction fails inside GOT-OCR2.0 (`'DynamicCache' object has no attribute 'seen_tokens'`), a **separate backend defect** recorded in [`docs/issues-and-bugs/ocr-extraction-got-ocr2-dynamiccache-failure.md`](./issues-and-bugs/ocr-extraction-got-ocr2-dynamiccache-failure.md). The **injection half is verified** for all four destinations. Deliberately left open and carried to that issue*
  - **Definition of done:** The full OCR workflow is reachable from the UI. — **MET 2026-07-26** (reachability; extraction quality is the separate issue above).
  - **Progress notes:**
    - *2026-07-26 — task complete on user approval, with one verification item explicitly carried to the OCR inference issue.* Two production files changed (`world/page.tsx`, `OCRPanel.tsx`), one test file added, one issue document written. No backend, database, API, dependency or model change. Tests: **5** new browser, full browser project **31/31 twice**, unit **61/61**, `tsc` exit 0, build exit 0, backend regression **221/221**, services healthy.
    - *`chapterId` audit (user requirement).* It occurs in exactly three places in the OCR workflow — prop type, destructure, and the confirm call. All three are null-safe; `isConfirmDisabled` gains the chapter check; the backend independently returns 400 for `chapter_draft` without a chapter, so client and server agree. Behaviour on stories that already have chapters is byte-identical, browser-tested.
    - *Loading and empty states are distinct, and the feature is never hidden.* "Loading this story's chapters…" versus "This story has no chapters yet… notes, note cards and character profiles work now", with the disabled destination carrying its own matching reason.
    - *⚠ **A separate High-severity defect was found because this fix made the feature reachable.*** OCR extraction fails at inference on every image. It is documented with logs, likely cause (vendored GOT-OCR2.0 code versus the installed `transformers`) and three candidate remedies, and **needs its own task** — suggested Stage 3 alongside the other Phase 2 defects.
    - *Reachability note:* a story can be left with **zero chapters** through the API (verified), which is what made this bug reachable in normal use.

- [x] **3.11 — Notes module load reliability** — *completed 2026-07-26*
  - **Source:** Phase 2 Issue **7** (Medium–High)
  - **Area:** Frontend / Backend
  - **Priority:** High
  - **Depends on:** Stage 2
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Context:** Intermittent — notes fail to load, then appear on a later visit. Diagnose as a race or cache-invalidation defect; a retry wrapper would mask it.
  - **Implementation checklist:**
    - [x] Reproduce and capture whether the API call fails or returns empty — *2026-07-26; **the spontaneous fault did not recur** in 16 steady visits (both workspaces) or 6 rapid tab-flip cycles — all 200s. **The failure mode reproduced deterministically:** forcing only the note-cards request to fail made the panel render "No story notes yet" while three notes existed*
    - [x] Check for a race between panel mount and story context readiness — *2026-07-26; the panel takes `storyId` from the route and does not wait on the chapters query, so there is no mount-order race. It **is** conditionally rendered in `world/page.tsx:38` and `plan/page.tsx:43`, so every tab switch remounts and re-fetches*
    - [x] Check client-side cache invalidation on navigation — *2026-07-26; there is no cache — notes are component state, unlike stories/chapters which React Query owns. Nothing stale to invalidate; the defect was elsewhere*
    - [x] Fix the underlying cause, not the symptom — *2026-07-26; **two structural defects**, neither intermittent. (1) `Promise.all` made the two reads all-or-nothing, so a cards failure discarded the notes. (2) A failure rendered as **emptiness** — the toast vanished, the false "you have no notes" stayed. Now: independent per-section loads, abort + sequence guards so a stale answer can never overwrite a newer one, cancellation distinguished from failure, and **no automatic retry** — retry is user-triggered and scoped to the failed section*
    - [x] Add an explicit loading state distinct from an empty state — *2026-07-26; four distinct states: loading, loaded-and-empty, partially failed (working section still renders; failed section shows why plus Retry; the other tab carries a marker), fully failed. Toasts name which endpoint failed and fire once per transition*
  - **Verification:**
    - [x] Playwright test navigating away and back repeatedly, asserting notes load every time — *2026-07-26; **executed** — `tests/browser/notes-reliability.spec.ts`, 13/13, including 10 cycles in **each** workspace*
    - [x] Confirm the API returns consistent results under repeated calls — *2026-07-26; 8 repeated reads of `/notes`, identical id sets every time*
  - **Definition of done:** Notes load on first attempt every time. — **MET 2026-07-26** for every failure mode that can be induced; see the limitation below.
  - **Progress notes:**
    - *2026-07-26 — task complete including verification.* Two production files changed (`NotesPanel.tsx`; `lib/api.ts` gains an optional `AbortSignal` on two reads), one test file added. No backend, database, migration or dependency change; mutation and `reloadKey` behaviour preserved and browser-tested.
    - *Tests: **13** new browser, full browser project **44/44 twice**, unit **61/61**, `tsc` exit 0, build exit 0, backend regression **221/221**, services healthy.* Coverage: repeated navigation in both workspaces, API stability, cards-fail-notes-survive, notes-fail-cards-survive, both-fail, loaded-and-empty, cancellation, stale-response rejection, manual Retry recovery, and a request count proving there is no hidden retry.
    - *⚠ **Known limitation — the original spontaneous trigger was never observed.*** What is fixed is that any such failure can no longer masquerade as "you have no notes", can no longer take the other section down with it, and now names the endpoint that failed — the diagnostic that did not previously exist. If Issue 7 recurs, it will be legible.
    - *Recorded, not done (out of scope):* notes still have no shared cache, so each mount re-fetches. Moving them under the Story Context Engine would remove the remount-refetch entirely — a Stage 8 candidate.

- [x] **3.12 — Character recognition synchronisation** — *completed 2026-07-26*
  - **Source:** Phase 2 Issue **9**; Phase 1 Cast Generation Critical 1, 2 and High 5
  - **Area:** Backend / Frontend / Database
  - **Priority:** High
  - **Depends on:** Stage 2
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Note:** Deliberately started here rather than Stage 4 because it is a data-integrity defect the author sees immediately. The deeper alias and dedup work continues in tasks 4.6–4.9.
  - **Implementation checklist:**
    - [x] Remove a name from the unresolved queue when it is added, matched or merged — *2026-07-26; one helper, `services/character_names.py::resolve_hints_for_names`, called from **four** paths: manual create, confirm-cast, promote, and rename/alias update. Hint creation now shares the same normalisation, so the two sides cannot drift*
    - [x] Refresh the unrecognised-names queue after cast generation — *2026-07-26; reconciled **inside the confirm-cast transaction**, so the response is already settled when it returns; the frontend's 3-second delayed reload is gone*
    - [x] Ensure the mention-to-character link is written at match time — *2026-07-26; `_queue_mention_index()` runs on create, promote and confirm-cast (one helper replacing three inline copies). **Verified by real rows**: `Ledger` 1, `Keeper` 1, `Lighthouse` 1 mention, with no manual `sync-mentions`*
    - [x] Ensure the frontend re-fetches after a character mutation — *2026-07-26; deterministic refetch after create, update, promote and cast confirmation, with **sequenced loads** so a slower earlier response cannot restore a stale cast list or hint count*
  - **Verification:**
    - [x] Integration test: add a character, assert it leaves the unresolved list — *2026-07-26; **17 unit tests** plus **9 end-to-end API checks**, each asserted against the database: exact, case-insensitive and whitespace-normalised creation, alias addition, rename-into-hint, promotion clearing every duplicate, cast confirmation, and the **negative case** — `"Marek"` does not dismiss `"Marekk"` (similarity 0.909, above the creation threshold)*
    - [x] Database-state check: no name simultaneously in `characters` and unresolved — *2026-07-26; holds for **every reconciliation path** on fixture data. ⚠ **The restored manuscript still holds 5 pre-existing overlaps** — `Devika Rao`, `Teodor Vance`, `Caleb Ferro`, `Aurelio Sant`, `Halloran` — created before this fix and **deliberately not modified** (read-only audit only, by user direction). A one-off backfill is the open policy question below*
    - [x] Manual check against the reported QA scenario — *2026-07-26; **3 browser tests executed**: registering a character removes its chip and drops the banner count with **no page navigation** (asserted), the similar-but-distinct name survives, and background indexing is shown as in progress*
  - **Definition of done:** A character never appears as both recognised and unrecognised. — **MET 2026-07-26** for everything created from this point; pre-existing rows await the backfill decision.
  - **Progress notes:**
    - *2026-07-26 — task complete including verification.* New: `backend/services/character_names.py` (normalisation + both matching rules + reconciliation) and `backend/tests/test_character_hint_sync.py`. Modified: `routers/characters.py`, `services/ai_service.py`, `schemas.py` (additive only), `CharacterList.tsx`, `lib/types.ts`. **No migration** — this reconciles existing rows, it does not change the schema.
    - **The defect, quantified in real data.** Hint *creation* already filtered against registered names; nothing reconciled the queue afterwards. The restored manuscript shows the consequence: **10 live hints against 8 characters, 5 of them exact duplicates of registered names — a 50% overlap rate.**
    - **Matching semantics — deliberately asymmetric, and this is the design decision.** Normalisation is shared (trim → collapse internal whitespace → casefold). **Creation** suppresses a new hint on an exact match *or* `SequenceMatcher` ratio **≥ 0.85**. **Reconciliation** dismisses an existing hint on an **exact normalised match only**, against name *and* aliases. Rationale: a surviving hint is visible and one click from dismissal; a wrongly-dismissed hint is invisible. The audit found **0 fuzzy-only near matches**, so the conservative rule costs nothing on real data.
    - *Transaction contract.* `resolve_hints_for_names` **never commits** — pinned by a test that fails if it does. Every caller commits once, so a response can never report a registered character while the unrecognised list still names it.
    - *Mention indexing — measured before deciding.* Chunk scan **8–14 ms/chapter**; the BGE-M3 embedding is the real cost at **0.8–1.4 s per character per run** (≈25–45 s at the restored manuscript's 8 characters × 4 chapters). It therefore stays **background**, and the API reports `mention_indexing_chapters` as work **still running**, which the UI states plainly ("The cast is saved. Mention counts … will fill in shortly"). No fixed delay is used anywhere.
    - *⚠ A defect introduced and caught during implementation.* `create_character` was a sync `def`, so queueing background work raised `RuntimeError: no running event loop` → HTTP 500. The endpoint is now `async`, and the helper degrades (logs, returns 0) instead of failing a mutation if ever called without a loop.
    - *Tests: **17** new unit, **9** end-to-end API, **3** mention-link confirmations, **3** new browser; full browser project **47/47**, unit **61/61**, backend regression **221/221**, `tsc` and production build clean.*
    - **⚠ Open policy question — pre-existing overlaps.** The fix is forward-looking. The 5 overlapping hints already in the restored manuscript need a deliberate one-off reconciliation pass; **recommended as a script the author runs, not a startup sweep**. Also open: whether dismissing a name should suppress it permanently, since re-detection in a later chapter can recreate the hint.

- [x] **3.13 — Notes and Narrative Threads navigation duplication** — *deferral confirmed 2026-07-26; implemented as task 8.8*
  - **Source:** Phase 2 Issue **10** (Medium); Phase 1 Editor UI Medium 16
  - **Area:** Frontend
  - **Priority:** Low
  - **Depends on:** None
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - > **Deferred from Phase 2 defect resolution to Stage 8 to avoid duplicate implementation.** The information architecture is being rebuilt in the workspace redesign; fixing navigation placement twice is waste. Phase 3 decision **D10** (Idea Shelf placement) also lands in the same surface. Tracked here so the issue is not lost — implemented as task **8.8**.
  - **Implementation checklist:**
    - [x] Confirm the issue is carried into task 8.8 with both source references — *2026-07-26; **traceability re-verified end to end**, see the audit below. No product code, tests, builds or service work performed — the definition of done forbids them.*
  - **Verification:**
    - [ ] Task 8.8 explicitly closes Phase 2 Issue 10 — *⏳ **intentionally open and future-dependent — not blocked, not forgotten.** This asserts an event in Stage 8; it can only be ticked when task 8.8 is actually implemented. Ticking it now would claim a future outcome. Task 8.8's own verification list carries the matching item, and its gate (Stage 8, line ~2354) repeats it.*
  - **Definition of done:** Deferral is recorded and traceable; no work performed in this stage. — **MET 2026-07-26.**
  - **Progress notes:**
    - *2026-07-26 — traceability audit, documentation only.* **Task 8.8 carries all six required references:** Phase 2 Issue **10**; Editor UI Medium **16** and **17**; the back-reference *"(deferred from task 3.13)"*; Phase 3 decision **D10**; the implementation item *"Remove the Notes and Narrative Threads navigation duplication"*; and the verification item *"**Phase 2 Issue 10 explicitly closed here**"*. The Stage 8 gate repeats "Phase 2 Issue 10 closed" independently.
    - *Registers consistent.* **Decision Register:** `D-4 — Phase 3 stakeholder decisions (D1–D12) … Blocks 7.1–7.15, 8.8`. **Blocked-Task Register:** `8.8 | D-4 (D10) | D10 recorded`. **Coverage Matrix:** the Phase 2 issues document is marked *"all 14 issues mapped (Issue 10 deferred to 8.8)"*, and the Excluded/Deferred table names the issue, its destination task **8.8**, and the reason, with a pointer back to 3.13. Three independent records agree; none contradicts another.
    - **The duplication as it actually stands, 2026-07-26** (read-only code survey, no changes):
      - **Notes** appears in **two** workspaces — `world` (Story Bible · Notes · Scan) at `world/page.tsx:17,38` and `plan` (Outline · Beats · Threads · Notes) at `plan/page.tsx:20,43`. Same `NotesPanel` component, two homes.
      - **Narrative Threads** appears in **two** surfaces — the `plan` workspace's Threads tab (`plan/page.tsx:19,42`) and the `analyze` workspace via the panel registry (`registries/panels.tsx:53`, `workspace: 'analyze', surface: 'page'`).
      - A **third, latent** location exists: `components/plot-holes/AuditPanel.tsx:68` embeds `NarrativeThreadsPanel` as a tab, but `AuditPanel` is referenced by no route and no registry entry — legacy surface, recorded so Stage 8 does not rediscover it.
    - *Why the placement decision waits for Stage 8.* The information architecture is being rebuilt in the workspace redesign (task **8.8**), and decision **D10** (Idea Shelf placement) lands on the same surface. Choosing homes now would mean choosing twice, and the second choice would overwrite the first. **This is a placement decision, not a defect in either component** — both render correctly wherever they appear.
    - *Adjacent observations already logged, offered as Stage 8 context only* (deliberately **not** expanded into an IA specification here): the analytics route is reachable from a single button and is absent from the workspace registry (task 3.9 notes), and the World workspace's tab strip mixes Story Bible, Notes and OCR (task 3.10 notes).

### Stage 3 Completion Gate — **CLOSED 2026-07-26**

- [x] All 14 Phase 2 issues closed or explicitly deferred with a recorded destination — *Issues 1, 11 → 3.8 · 2, 14 → 3.4 · 3 → 3.9 · 4 → 3.6 · 5 → 3.7 · 6 → 3.10 · 7 → 3.11 · 8 → 3.2 and 3.3 · 9 → 3.12 · 12, 13 → 3.1 · **10 deferred to task 8.8** with destination recorded in three registers (task 3.13). ⚠ Issue 6's **interface** is closed; OCR **inference** fails on a separate, newly found defect tracked outside Stage 3 — see the note below.*
- [x] Chapter continuation, scene outline, plot hole detection and continuity analysis all return usable results — *continuation and outline user-tested 2026-07-24 (task 3.1); plot holes (3 findings) and continuity (2 issues) verified live 2026-07-26, both `degraded: false`*
- [x] Story Bible never reports `completed` on partial content — *proven live: a mid-run interruption produced `partial`, and a later one `failed`; `completed` appeared only when all five sections were genuinely generated*
- [x] Story Bible contains no unsupported detail, verified against a fixture — *11/11 timeline events supported by their cited chapter, 0 unsupported; **author review confirmed** 2026-07-26*
- [x] Voice agent never reports false success — *verified live in both directions after the HTTP 500 defect was fixed; a reported failure is recorded as failure with no data change*
- [x] Regression tests added for tasks 3.1–3.7 — *`test_retrieval_signatures` 18 · `test_generation_limits` 24 · `test_story_bible_outcomes` 89 · `test_degraded_output` 25 · `test_extract_json_audit` 21 · `test_voice_execution` 45 · `test_voice_recording_routes` 7 — plus `test_character_hint_sync` 17 for 3.12. **246 backend tests, all passing***
- [x] `_extract_json` caller audit complete — *task 3.5, 17 call sites registered and enforced by an executable register*
- [x] **Gate 2 — Core workflows functional** passed — *2026-07-26; every criterion above met against a real manuscript on a running stack. Recorded here; the matching box under task 12.1 stays open until Release Validation re-checks it at release time.*

> ### ⚑ Stage 3 closing note — 2026-07-26
>
> **All 13 main tasks are complete** and the gate is closed. The ten verification items that stood open across 3.2, 3.3, 3.4, 3.6 and 3.7 were executed in one consolidated run against a **verification copy** of the restored manuscript (4 chapters / 21 chunks / 8 characters / 67 mentions, embeddings preserved). The restored manuscript itself was **never written to** — its counts were re-audited afterwards and match the 2026-07-24 baseline exactly.
>
> **The run found two genuine defects that all prior testing had missed**, both fixed under approved corrective plans and re-verified:
> 1. **Voice recording endpoints returned HTTP 500 on every call** — `routers/voice_agent.py` used `datetime.utcnow()` with no module-level import, so `/confirm` and `/nodes/{key}/result` raised `NameError`. 44 passing voice tests never caught it because none drove the routes through the application; the client also swallowed the errors silently. Both fixed, and 7 live-route regression tests plus an anti-silence test now guard it.
> 2. **Provenance coverage was 0.37, not 1.00** — characters 0.00, locations 0.33, world_rules 0.75. The prompt only demanded per-line citation where it was explicit (timeline, themes). Corrected across three measured iterations to **117/117 = 1.00**, with the acceptance criterion left unchanged.
>
> **Carried out of Stage 3, deliberately:** the OCR `DynamicCache` inference failure (tracked as a separate high-priority defect, `docs/issues-and-bugs/ocr-extraction-got-ocr2-dynamiccache-failure.md`); the 5 pre-existing character-hint overlaps in the restored manuscript awaiting a backfill decision (task 3.12); and Story Bible interpretation/summarisation quality, raised by the author's review and recorded as new task **4.16**.

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

- [ ] **4.16 — Story Bible interpretation and summarisation quality**
  - **Source:** Author review of the Stage 3 verification run, 2026-07-26 (verification item under task 3.3)
  - **Area:** AI / Prompt engineering
  - **Priority:** Medium
  - **Depends on:** 3.3 (complete)
  - **Blocked by:** None
  - **Can run in parallel:** Yes
  - **Context:** Stage 3 established that the Story Bible is **factually grounded** — 117/117 entries cited, 11/11 timeline events supported by their cited chapter, and the author confirmed no unsupported facts, fabricated events or invented characters. The author separately observed **minor interpretation and summarisation quality issues**: how some information is read, condensed or presented. These are explicitly **not hallucinations** and were deliberately excluded from Stage 3, whose objective was correctness, not polish.
  - **Constraint that defines this task:** improvements must be **generalisable across all manuscripts**. No hard-coded rules, no manuscript-specific heuristics, no tuning against the one sample story — a fix that improves this manuscript by encoding facts about it is a regression in disguise.
  - **Implementation checklist:**
    - [ ] Collect the author's specific observations and classify each as interpretation, summarisation, emphasis or presentation
    - [ ] Reproduce each class on at least two structurally different manuscripts, so the problem is shown to be general rather than local
    - [ ] Define a quality measure that is separate from the grounding measure — provenance is already at 1.00 and must not be traded away
    - [ ] Improve section instructions for the weakest class first, re-measuring after each iteration
    - [ ] Re-run the Stage 3 grounding and provenance checks after every change, as non-negotiable guard rails
  - **Verification:**
    - [ ] Provenance stays at 1.00 and grounding stays at zero unsupported events across every test manuscript
    - [ ] The author confirms the observed quality issues are reduced, on a manuscript other than the original sample
    - [ ] No manuscript-specific string, name or rule appears anywhere in the change
  - **Definition of done:** Story Bible output reads well and interprets faithfully on any manuscript, with factual grounding unchanged.
  - **Progress notes:**
    - *2026-07-26 — task created from the author's Stage 3 review, by user direction, with no implementation and no plan produced. Stage 3 was closed on correctness; this carries the quality work forward.*

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
