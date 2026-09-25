# Stage 8 — Manual Verification Guide

| | |
|---|---|
| Stage | 8 — Editor UI and Author Workspace Redesign (the Studio) |
| Branch | `claude/stage-8-studio-workspaces`: cut from `main` at `06850cf`; its first commit (the pins-router fix) reached `main` in PR #3; `main` at `abbb4f1` (which adds Stage 2 and Stage 5 from PR #2) was merged back in on 2026-09-25. The Stage 8 work itself is not on `main` |
| Created | 2026-09-25 |
| Status | **PENDING MANUAL VERIFICATION** |
| Checklist | [`docs/NarratIQ_Master_Implementation_Checklist.md`](../../NarratIQ_Master_Implementation_Checklist.md), Stage 8 and its Completion Gate |
| Why this exists | The cloud has no pod, no vLLM, no real author and no screen reader. Stage 8 was verified there with a mocked-API Playwright suite (`frontend/tests/studio/`, 65 tests) plus unit tests. Everything that needs the real stack, real AI output or a person's judgement is listed here instead of being ticked. |

**Safety rules for every item:** take the backup in MV-8.0 first. Never stop or restart the pod (restarting the frontend or backend *process* is fine). Use the disposable fixture story (`backend/scripts/seed_fixture.py`) for anything that writes. Do not paste manuscript text into any external tool. Do not print `SECRET_KEY`.

**What changed that you will notice:** the editor is now a set of workspaces on a left rail (Write, Plan, Characters, World, Analyze, Assistant, Publish). Notes and the Idea Shelf moved to World; Narrative Threads is only in Analyze; Search & replace is back in Write (Ctrl/⌘F). Write has a Draft/Edit switch (Edit is the default) and a View menu (Reading, Focus, Zen, Typewriter, Fullscreen). The AI panel's tools are grouped into Rewrite / Generate / Versions and the panel can be expanded (Ctrl+\\). Layout sizes are remembered per user, per browser. On first load your old panel sizes carry over; your last workspace and modes start fresh once.

**Order:** MV-8.0 → MV-8.1 → MV-8.2 → MV-8.3 → MV-8.4 → MV-8.5 → MV-8.6 → MV-8.7 (author items last).

---

## STAGE VERIFICATION SUMMARY

| Item | Checklist | Classification |
|---|---|---|
| 8.1 Workspace navigation, one home per tool | 8.1 | VERIFIED IN CLOUD (mocked API) |
| 8.2 Resizable/expandable panels, per-user layout | 8.2 | VERIFIED IN CLOUD (mocked API) |
| 8.3 Writing-first hierarchy, Reading/Focus/Zen | 8.3 | IMPLEMENTED — MANUAL VERIFICATION REQUIRED (author review, MV-8.5) |
| 8.4 Progressive disclosure (controls 53→35 with the AI panel open) | 8.4 | IMPLEMENTED — MANUAL VERIFICATION REQUIRED (author review, MV-8.5) |
| 8.5 Draft/Edit separation | 8.5 | IMPLEMENTED — MANUAL VERIFICATION REQUIRED (author review, MV-8.5) |
| 8.6 Phase 3 surfaces in the sidecar | 8.6 | IMPLEMENTED — MANUAL VERIFICATION REQUIRED (live run, MV-8.2) |
| 8.7 Scalability (mock tool) + add-a-tool guide | 8.7 | VERIFIED IN CLOUD |
| 8.8 IA deduplication; Phase 2 Issue 10 closed | 8.8 | VERIFIED IN CLOUD |
| 8.9 Accessibility: axe, keyboard, contrast, focus | 8.9 | VERIFIED IN CLOUD (mocked API) |
| 8.9 Screen-reader pass | 8.9 | IMPLEMENTED — MANUAL VERIFICATION REQUIRED (MV-8.4) |
| 8.9 Automated a11y check in CI | 8.9 | BLOCKED — CI deferred by decision (task 6.1); runs locally as `npm run test:a11y` |
| 8.10 Viewport matrix 1920→768 | 8.10 | VERIFIED IN CLOUD |
| 8.11 Multi-hour author session | 8.11 | IMPLEMENTED — MANUAL VERIFICATION REQUIRED (MV-8.7) |
| Stage 7 carry-forward: selection-toolbar test 9 | 7.15 | Fixed; VERIFIED IN CLOUD; live re-run MV-8.3 |
| Pins router startup fix (`f387d1d`, now also on `main`) | — | VERIFIED IN CLOUD (`import main` loads 165 routes after the merge) |
| Stage 5 surfaces inside the Studio (merged from `main`): scan outcome, saved report, near-no-op result | — | VERIFIED IN CLOUD (`tests/studio/stage5.spec.ts`, mocked); live behaviour is the Stage 5 guide's MV-5.D1, MV-5.D2 and MV-5.D4, now done from Analyze and the Write AI panel |

No item is FAILED. Nothing in this stage touches the database schema; there is no migration.

---

## MV-8.0 — Back up, deploy the branch's frontend, restart processes

| Field | Value |
|---|---|
| Related task | All of Stage 8 |
| Requirement | The pod serves the Stage 8 frontend and backend without data loss |
| Why the cloud could not verify it | The cloud built the app against a mock API only |
| Required environment | RunPod pod terminal |
| Preconditions | No author work in progress; you have decided to test this branch on the pod (Stage 8 is not on `main`) |
| Procedure | 1. `bash scripts/backup_database.sh` (note the path)  2. `git fetch origin claude/stage-8-studio-workspaces && git checkout claude/stage-8-studio-workspaces`  3. `cd backend && python3 -c "import main; print(len(main.app.routes))"` (expect about 165 and no error)  4. Compare dependencies: `pip freeze > /tmp/freeze.txt` and check every package in `backend/requirements.txt` is present at a compatible version (Stage 8 adds no Python dependency; this confirms the pod still matches)  5. `cd ../frontend && npm install && npm run build` (NEXT_PUBLIC_API_URL comes from `.env.local`, which `start-narratiq.sh` writes)  6. Restart the backend and frontend processes (or re-run `bash start-narratiq.sh`)  7. `curl -s http://localhost:8000/api/health` |
| Expected result | Steps 3, 5 and 7 succeed; the build prints `/projects/[id]/write` around 128 kB / 290 kB; the app opens on the workspace rail |
| Failure indicators | Import error in step 3; a missing or mismatched package in step 4; build failure |
| Evidence to capture | Backup path; route count; any mismatched packages; the build's route table line for `/write` |
| Rollback | `git checkout claude/project-thread-yeshmd` (or `main`), `npm run build`, restart the frontend |
| Status | **PENDING MANUAL VERIFICATION** |

## MV-8.1 — Studio suite on the pod (optional sanity check)

| Field | Value |
|---|---|
| Requirement | The cloud results reproduce on the pod's machine |
| Procedure | `cd frontend && npm run test:studio` then `npx playwright test --project=unit` |
| Expected result | 65 studio tests (3 variant-only tests skipped), 99 unit tests, all passing |
| Evidence to capture | The two summary lines |
| Status | **PENDING MANUAL VERIFICATION** |

## MV-8.2 — Full live browser run against the real stack (review H1)

| Field | Value |
|---|---|
| Related task | 8.6 verification; H1 (seven live specs were updated for the new layout and have never run against it live) |
| Requirement | Every live browser spec passes against the Stage 8 UI with real AI |
| What must be tested | All 64 tests in 13 files of `--project=browser`. Updated in Stage 8: `notes-reliability`, `ocr-panel`, `phase3-pins-compare`, `story-bible-generation`, `selection-toolbar`, `sidecar-lock-and-strength`, `audio-transcription` |
| Why the cloud could not verify it | Needs the real backend, vLLM and a seeded story. The cloud only confirmed the specs compile and list (`--list`: 64 tests in 13 files) |
| Preconditions | MV-8.0; fixture story seeded; `E2E_BASE_URL`, `E2E_EMAIL`, `E2E_PASSWORD`, `E2E_STORY_ID` set |
| Procedure | `cd frontend && PW_CHROMIUM_PATH=<chromium> npx playwright test --project=browser --reporter=list 2>&1 | tee /tmp/stage8-browser.txt` |
| Expected result | All pass (tests that `skip` on a missing precondition are listed as skipped, not failed) |
| Failure indicators | A locator timeout in one of the seven updated specs usually means the spec and UI disagree; send the test name and the error |
| Evidence to capture | `/tmp/stage8-browser.txt` summary and any failures |
| Stage 5 note | The Stage 5 guide's MV-5.D1 (Narrative Threads scan), MV-5.D2 (saved Manuscript Report) and MV-5.D4 (near-no-op Style result) now start from Analyze → Narrative Threads, Analyze → Manuscript Report and Write → AI assistant → Rewrite tool. Run them in this layout |
| Checklist affected | 8.6 "Every Phase 3 capability is reachable and usable"; Stage 8 gate |
| Status | **PENDING MANUAL VERIFICATION** |

## MV-8.3 — Selection-toolbar test 9, repeated (Stage 7 carry-forward)

| Field | Value |
|---|---|
| Related task | 7.15 carry-forward; Stage 8 review M2 |
| Requirement | The Escape / re-select test no longer fails intermittently |
| Why the cloud could not verify it | The root cause was fixed and the equivalent studio test passes every run in the cloud (the old code failed 2 of 5); the live spec needs the pod |
| Procedure | `npx playwright test --project=browser tests/browser/selection-toolbar.spec.ts --repeat-each=10` |
| Expected result | 10 of 10 passes for every test in the file |
| Evidence to capture | The summary line |
| Checklist affected | 7.15's toolbar item (Stage 7 carried-forward list) |
| Status | **PENDING MANUAL VERIFICATION** |

## MV-8.4 — Screen-reader pass

| Field | Value |
|---|---|
| Related task | 8.9 "Audit screen-reader labelling on all panels" |
| Requirement | A screen-reader user can find and operate every workspace |
| Why the cloud could not verify it | axe checks names and roles; only a real screen reader shows what is announced |
| Required environment | NVDA + Firefox or Chrome (Windows), or VoiceOver + Safari (macOS) |
| Procedure | Keyboard only, screen reader on: 1. Tab once: "Skip to content" is announced; Enter  2. Move through the Workspaces navigation: each item announces its name and the current one says "current page"  3. Write: open a chapter from the binder; the editor is announced as editable text; the formatting toolbar is a toolbar; Draft/Edit announces as a radio group  4. Open the AI panel (button in the status bar): its heading is announced and focus moves into it; the tool groups announce as tabs; Close returns focus to the button  5. Plan and World: the section tabs announce as tabs with selected state  6. Analyze: open one tool; its heading is announced; Close returns focus to its card  7. Ctrl/⌘K: the palette announces as a dialog with a search field |
| Expected result | Every control has a meaningful name; no silent buttons; focus never lands on something invisible |
| Evidence to capture | Screen reader and browser used; a list of anything unlabelled or confusing (location + what was announced) |
| Checklist affected | 8.9 screen-reader box; Stage 8 gate "Accessibility baseline met" (with the CI item still deferred) |
| Status | **PENDING MANUAL VERIFICATION** |

## MV-8.5 — Author reviews (8.3, 8.4, 8.5)

| Field | Value |
|---|---|
| Related task | 8.3, 8.4, 8.5 author-review boxes; the design owner (Arshith Babu, confirmed) runs or approves these reviews |
| Requirement | The author judges the redesign on its own terms |
| Why the cloud could not verify it | These are judgements only the author can make |
| Procedure | Using the fixture story or a real manuscript: 1. **Focal point (8.3):** open Write with the AI panel closed. Is the manuscript clearly the main thing on screen? Try Reading, Focus and Zen (View menu; Escape leaves them)  2. **Discoverability (8.4):** without help, find: Story Bible, Notes, the Idea Shelf, Search & replace, Pacing, Continuity, Compare versions, and the voice agent (its buttons in the header and the AI panel were removed as duplicates; it lives in Assistant and in Ctrl/⌘K). Note any you could not find within 30 s, and try Ctrl/⌘K for them  3. **Drafting session (8.5):** 20+ minutes in Draft mode writing new text. Did anything distract?  4. **Editing session (8.5):** 20+ minutes in Edit mode revising with the AI panel and selection toolbar  5. **Design owner:** already confirmed (Arshith Babu, 2026-09-25); nothing to do |
| Expected result | A yes / no with a sentence for each of 1–4; any tool not found in step 2 is recorded |
| Evidence to capture | Answers to 1–4 |
| Checklist affected | 8.3, 8.4, 8.5 author-review boxes |
| Status | **PENDING MANUAL VERIFICATION** |

## MV-8.6 — Real-browser layout checks

| Field | Value |
|---|---|
| Related task | 8.2 (already verified in cloud; this confirms on the real app) |
| Procedure | 1. Drag the binder and AI panel edges, reload: sizes stay  2. Expand the AI panel (button or Ctrl+\\), reload: still expanded  3. Log out, log in as a second account in the same browser: default layout, not the first account's  4. Log back in as the first account: its layout is back |
| Expected result | As described |
| Evidence to capture | Pass / fail per step |
| Status | **PENDING MANUAL VERIFICATION** |

## MV-8.7 — Multi-hour author usability session (8.11)

| Field | Value |
|---|---|
| Related task | 8.11 (all boxes) |
| Requirement | Real authors complete a full session without layout friction |
| Why the cloud could not verify it | Needs people and hours |
| Participants | At least 2 authors who write long-form fiction; one should not have seen NarratIQ before |
| Setup | The pod on this branch (MV-8.0); each author uses their own account and a manuscript of at least 5 chapters (their own, or the fixture story). Nothing leaves the pod |
| Session script (about 3 hours, with breaks) | **0:00–0:10** Orientation: the rail, Ctrl/⌘K, Draft/Edit. No other tips. **0:10–1:10** Drafting: write a new scene or chapter in Draft mode. **1:10–1:20** Break. **1:20–2:10** Editing: revise an earlier chapter using the AI panel (rewrite, tone, continue), pin a version, compare two versions, lock a sentence. **2:10–2:40** Planning: use Plot Assistant, set a pacing goal, add two ideas to the Idea Shelf aimed at a chapter, check the Story Bible. **2:40–3:00** Analysis: run Continuity and Emotional Arc, then go back to Write and act on one finding |
| Friction log (fill in during the session) | Time · workspace · what the author was trying to do · what happened · severity (blocker / annoying / minor) · quote |
| Afterwards, ask | 1. Where did you lose time finding something? 2. Did the screen feel crowded at any point? When? 3. Did you get tired of anything by the end? 4. Does this feel like a writing studio or a tool dashboard? 5. What would you change first? |
| Expected result | No blocker in the log; answers to 4 lean "studio" |
| Evidence to capture | The friction log and answers per author |
| Checklist affected | 8.11 all boxes; Stage 8 gate "Multi-hour author usability session passed" and "All 18 Editor UI issues closed or accepted" |
| Status | **PENDING MANUAL VERIFICATION** |

---

**After verification:** send the evidence back in the project thread. Boxes are ticked only from that evidence; findings from MV-8.5 and MV-8.7 become fixes on this branch before the Stage 8 gate closes.
