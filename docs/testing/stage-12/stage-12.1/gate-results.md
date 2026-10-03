# Stage 12.1 — Release gate verification results (2026-10-03)

Pod `x0smrkvs4n6wpk` (1× A40). Code: HEAD `f7a7a2e` plus the uncommitted Tranche 3 and Stage 12.1 changes (`repository-state.md`). Exit criteria: Master Execution Plan §13.

**No gate is recorded as passed here.** These are the technical results. Ticking the 12.1 boxes, and any waiver, waits for the product owner's review. Statuses: TECHNICALLY PASSED; TECHNICALLY PASSED — OWNER DECISION REQUIRED; PARTIALLY VERIFIED; BLOCKED — EXTERNAL INFRASTRUCTURE; FAILED — TECHNICAL DEFECT.

| Gate | Status |
|---|---|
| 1 — Environment stable | **TECHNICALLY PASSED** |
| 2 — Core workflows functional | **TECHNICALLY PASSED** (one human reading noted, part of Gate 3b / UAT) |
| 3a — Retrieval correct | **TECHNICALLY PASSED — OWNER DECISION REQUIRED** (4.9 "not applicable") |
| 3b — AI quality acceptable | **TECHNICALLY PASSED — OWNER DECISION REQUIRED** (blind review and the other human reviews; package ready) |
| 4 — No critical defects | **PARTIALLY VERIFIED**: 7 open technical items (none small-fixable), 73 needing judgement |
| 5 — Security checks passed | **TECHNICALLY PASSED — OWNER DECISION REQUIRED** (residual risk, dependency acceptance, 11.7) |
| 6 — End-to-end tests passed | **TECHNICALLY PASSED** for the automated suite; CI is **BLOCKED — EXTERNAL INFRASTRUCTURE** (W-1); real-author UAT is a human item |
| 7 — Backup and recovery verified | **TECHNICALLY PASSED** |
| 8 — Deployment and rollback tested | **TECHNICALLY PASSED — OWNER DECISION REQUIRED** (PG-04 / MV-10.3: W-2 or a Docker host; presence-label loss on rollback) |

## Gate 1 — Environment stable

**Requirement:** ports reachable externally; `/api/health` healthy; AI generation through the proxy; env vars clean; `verify_runpod_setup.sh` passes truthfully.

**Already current (A24, 2026-10-03):**
- the setup check passed 39/0;
- health ready;
- generation through the public proxy returned 200;
- vLLM listens on 127.0.0.1 only;
- a fresh-pod bring-up, and a start from the real checkout path.

**Stage 12.1 — the failure path, proved non-destructively (env-only inputs; the running stack untouched):**

| Broken configuration | Result |
|---|---|
| Wrong vLLM port (`VLLM_PORT=9999`) | exit 1: `[FAIL] vLLM (port 9999) — NOT RUNNING` |
| Missing model directory (`LLM_MODEL_PATH=/nonexistent/Qwen`) | exit 1: `[FAIL] LLM … directory NOT FOUND` |
| An isolated backend (:8100) started with a **wrong `VLLM_BASE_URL`** | exit 1: `[FAIL] Backend is up but reports vLLM NOT ready — every AI endpoint will return 503` (the :8100 proxy and port-list checks also fail, correctly: that port is not exposed). The temporary backend was then stopped |
| Control, configuration restored | exit 0, **39 passed / 0 failed** |

Logs: `gate1-*.log`. This also satisfies Stage 2.6's "fails correctly on a deliberately broken config".

**External, not part of §13 Gate 1:** the `SECRET_KEY` team-store copy (W-5).

## Gate 2 — Core workflows functional

**Already current (A24):** plot holes, outline, continuation and continuity were all usable on data restored from a backup. Story Bible `completed`, with 0 failed sections. Notes and analytics usable. Voice-agent action and OCR panel specs pass live.

**Stage 12.1 — the OCR journey, end to end in the browser:** new live spec `tests/browser/ocr-to-editor.spec.ts`.
1. Upload a printed-text image (`fixtures/ocr/printed-note.png`).
2. Real GOT-OCR2.0 extraction; the text is shown for review.
3. Choose "Current Chapter Draft" and confirm.
4. The chapter stores the original sentence plus the extracted text, the Write editor shows both, and they are still there after a reload.

Result: **2/2 passed** (first run: the workflow passed; the test's own content check used the list endpoint, which omits chapter text, and was corrected). This closes task 3.10's long-open manual journey technically; handwriting quality remains unmeasured.

**Live browser suite after the Stage 12.1 changes:** 69 passed / 0 failed across the 14 existing specs, plus the OCR spec 2/2.

**Human (Gate 3b / UAT):** the Story Bible "never asserts unsupported facts" reading (package item 5).

## Gate 3a — Retrieval correct

**Requirement:** known-answer queries return correct-chapter evidence; search exact and correct; character sync consistent; retrieval regression suite green.

**Evidence (current, not re-run unnecessarily):**
- retrieval suite **147/147** (final Tranche 3 isolated run; re-run again in this stage's regression, see the completion report);
- search integrity (A9) **plus the Stage 12.1 race fix** (SEARCH-1/2/3);
- D-1 scope (A1, null-chapter guard, voice correction);
- character sync (4.7);
- Plot Assistant retrieval (A13; the long-manuscript measurement is still an open follow-up).

**Owner decision:** 4.9 "Fix relationship extraction errors". The checklist records it as not applicable: no relationship-extraction pipeline exists. Accept or define the work (this also holds CAST-H8 and the Stage 4 Cast gate line).

## Gate 3b — AI quality acceptable

**Technical evidence:**
- measured improvements (5.16; Tranche 2 A14, A15 Style, A17);
- no-change invariants green, and **the harness now proven to catch a deliberate regression** (Gate 6);
- continuity citation validation, MV-5.14-A/B/C.

**Human review package, ready to use:** `gate3b-review/`.
- `blind-review.md`: 12 blind A/B pairs, v2 vs v4, with a separate key.
- `a15-light-labelling.md`: 90 Light outputs.
- `children-meaning-review.md`: 80 children's rewrites.
- the MV-5.14-D decision sheet with evidence.
- the MV-5.AR list, the Story Bible reading, and the translation review.

All built from saved outputs, deterministic, and no judgement made.

## Gate 4 — No critical defects

The full 114-issue reconciliation is in `gate4-release-blocking-matrix.md`: **33 fixed and verified, 7 open technical, 73 human judgement, 1 accepted.**

**Fixed during Stage 12.1:**
- SEARCH-1/2/3 (Critical): stale search answers replaced current results. Reproduced by a test that fails on the old code.
- AUDIT-H8/H9/H10: report sections were computed but never shown.

**Attempted and rejected:** CAST-H6 role definitions (worse: 22/25).

**Open technical items (no small fix available):**
- AWT-D, AWT-G, AWT-I (Critical);
- AWT-1.2, 1.6, 3.7 and CAST-H6 (High).

**Gate 4 technical closure (2026-10-03, after the owner's Section 1 decision):**
- **Current categorisation:** `gate4-section3-review.md`. It records 33 fixed, 2 accepted, 66 human review, **0 technical**, 4 known-limitation candidates and 9 external.
- **PA-C6 / PA-H12:** measured on a 40-chapter manuscript (`pa-long-manuscript-measurement.md`). Ordering criterion B is not met, and the cause is embedding similarity, not code. They are now owner-decision candidates.
- **Defects fixed during that work:**
  - chapter-summary truncation at 8,000 characters (PA-H10's technical cause);
  - BGE-M3 CPU thread oversubscription (indexing 44 min → 220 s).
- **Regression after these fixes:**
  - backend: 1170 passed, 1 xfailed;
  - retrieval: 147 passed.
- **Plot Assistant (PA-C1):**
  - added a studio test of the scope toggle and a live task 4.1 check, which passed 3/3;
  - fixed a defect: creative-intent answers reported no evidence while using three chapter summaries (`summary_chapters`);
  - fixed the toggle's accessibility: its state was shown by colour only.
- **Regression after those fixes:**
  - studio: 108 passed (3 variant-only skips);
  - backend: 1175 passed, **1 failed** (`adventure-3` no-change, then 9/10 on re-run with the code path unchanged; AWT-G variability, recorded in `awt-g-consistency.md`);
  - retrieval: 147 passed.
- The Gate 6 note "`ai_service.py` byte-identical to HEAD" describes the state at the time of that proof. `ai_service.py` now also carries the approved Story Bible fix and these two fixes.

## Gate 5 — Security checks passed

See `gate5-security.md`. Every §13 criterion has current technical evidence.
- Fresh audits: requirements 5 High (unchanged; unreachable).
- Installed runtime: 4 Critical / 59 High (the vLLM stack, already accepted 2026-10-02; pod image packages, external). lxml XXE was **proven unreachable** through `.docx` import; urllib3 and soupsieve are unreachable.
- npm production tree: 1 High (postcss, build-time). npm overall: 8 High (new `braces` advisory in build tooling, unreachable).

**Owner decisions:** the P1 residual risk, acceptance of the dependency classification, 11.7, and the pod template.

## Gate 6 — End-to-end tests passed

**Requirement:** the automated suite green on a clean pod; CI blocks failing merges; a UAT subset executed by real authors.
- **Automated:** green (Tranche 3 final runs and this stage's regression).
- **Deliberate regression proof:** red, then revert, then green (`gate6-regression-detection.md`), with `ai_service.py` byte-identical to HEAD afterwards.
- **CI:** W-1 draft (external).
- **UAT:** real authors (human).

## Gate 7 — Backup and recovery verified

A24 evidence is current: real backup → verify PASS → full documented restore into a clean database → manifest MATCH (57 tables) → restart. RPO/RTO are now documented with measured values (`backup-and-restore.md` §6: about 21 minutes from a fresh pod).

**Not repeated** (the existing evidence is current and sufficient). Off-pod copy: W-3 (external; not a §13 Gate 7 criterion).

## Gate 8 — Deployment and rollback tested

**Requirement:** a clean-pod deploy from scratch; rollback rehearsed for code, schema and models; the port contract documented in the deploy runbook.

**Evidence (P0 / A22, current):**
- three from-scratch or restart bring-ups (14 min 35 s; 337 s; 306 s from the real path);
- code, schema and frontend rollback to `0032a81`, isolated, 369 s;
- model rollback, 26 s;
- the prompt-version rollback;
- port contract: `runpod-deployment.md` (ports 3000 and 8000 exposed at pod creation, 9001 internal).

**Owner decisions:**
- PG-04 / MV-10.3: waiver W-2, or a Docker host.
- 10.5 "without data loss": whether the documented presence-label loss on rollback past `0027` is acceptable.
