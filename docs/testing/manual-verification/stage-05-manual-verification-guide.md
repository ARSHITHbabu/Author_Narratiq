# Stage 5 — Manual Verification Guide

| | |
|---|---|
| Stage | 5 — Phase 1 AI Generation Quality (2026-09-25 cloud pass: live-review defects D1–D4, 5.14's three partial items, 5.8's measurement harness) |
| Created | 2026-09-25 |
| Checklist | [`docs/NarratIQ_Master_Implementation_Checklist.md`](../../NarratIQ_Master_Implementation_Checklist.md), Stage 5 and its Completion Gate |
| Why this exists | The cloud workspace has no GPU, no vLLM, no BGE-M3 weights and no author. Everything that needs the live model, the pod's database, a browser against the real stack, or the author's judgement is listed here with exact steps instead of being ticked. |

Everything the cloud *could* verify is recorded in the checklist with the test that proves it:
`backend/tests/test_stage5_signals.py`, `test_stage5_prompts_and_guard.py`, `test_stage5_persistence.py`, the
migration round trip (`backend/tests/run_migration_roundtrip.sh`), `tsc --noEmit` and `npm run test`.

**Safety rules for every item:** take the backup in MV-5.0 first; never stop or restart the pod (restarting the
backend *process* is fine); use the disposable fixture story (`backend/scripts/seed_fixture.py`) for anything that
writes; do not paste manuscript text into any external tool; do not print `SECRET_KEY`.

**Order:** MV-5.0 → MV-5.KD → MV-5.D1…D4 → MV-5.14-A/B/C → MV-5.8-A → MV-5.G → the author items (MV-5.14-D, MV-5.BR, MV-5.3B, MV-5.AR).

---

## A. Deployment

### MV-5.0 — Back up, apply migration 0023, restart the backend

| Field | Value |
|---|---|
| Related task | Stage 5 D1/D2 (migration `0023_thread_scans_and_manuscript_reports`) |
| Requirement | The two new tables exist on the pod's database, created by Alembic, with no data loss |
| What must be tested | A pre-migration backup, then `alembic upgrade head` to `0023`, then a healthy backend |
| Why the cloud could not verify it | The cloud has its own disposable database. The migration was round-tripped there (upgrade → downgrade → re-upgrade, and after `create_all()`), not on the pod |
| Required environment | The RunPod pod terminal |
| Preconditions | No author work in progress; the branch is checked out on the pod |
| Test data | None |
| Procedure | 1. `bash scripts/backup_database.sh` (note the dump path it prints)  2. `cd backend && python3 -m alembic current` (expect `0022`)  3. `python3 -m alembic upgrade head`  4. `python3 -m alembic current` (expect `0023 (head)`)  5. Restart only the backend process (or re-run `bash start-narratiq.sh`, which runs `create_all()` then `alembic upgrade head`)  6. `curl -s http://localhost:8000/api/health` |
| Expected result | Step 4 prints `0023 (head)`; health is OK; `psql … -c "\d narrative_thread_scans"` and `"\d manuscript_reports"` show `uq_…_story_id` constraints |
| Failure indicators | Any Alembic error; a missing backup file; health not OK |
| Evidence to capture | The backup path and size; the `alembic current` output before and after |
| Checklist affected | Prerequisite for every item below |
| Status | **PENDING MANUAL VERIFICATION** |

---

## B. Live-review defects (the 2026-09-22 author findings)

### MV-5.KD — The known-defect suite on the pod

| Field | Value |
|---|---|
| Related task | Stage 5 gate, D1–D4 "confirmed live" boxes |
| Requirement | The four defects the author found are gone against the real model |
| What must be tested | `backend/tests/test_known_stage5_defects.py`, which now asserts the fixed behaviour (it polls scan-status; it re-fetches the saved report with GET) |
| Why the cloud could not verify it | Every test there drives real vLLM + BGE-M3 through a real uvicorn |
| Required environment | The pod with vLLM up, and the `narratiq_test` database |
| Preconditions | MV-5.0 done |
| Test data | Created and removed by the test fixture (a disposable 3-chapter story) |
| Procedure | `cd backend && DATABASE_URL=postgresql+psycopg2://narratiq:narratiq@localhost:5432/narratiq_test python3 -m pytest tests/test_known_stage5_defects.py -m known_stage5_defect -q` |
| Expected result | 4 passed |
| Failure indicators | Any failure. Record which one; D4's test is a live AI-quality judgement and can fail even though the code path is correct (see MV-5.D4) |
| Evidence to capture | The pytest summary line and any failure message |
| Checklist affected | The four "confirmed live on the pod" boxes (D1–D4) |
| Status | **PENDING MANUAL VERIFICATION** |

### MV-5.D1 — Narrative Threads scan shows its result in the browser

| Field | Value |
|---|---|
| Related task | D1 |
| Requirement | A scan ends in a visible, honest outcome, including after navigating away and back |
| What must be tested | Scan → status polling → thread list; resume after navigation; a second click does not start a second scan |
| Why the cloud could not verify it | Needs the live model and a browser |
| Required environment | Pod, browser |
| Preconditions | MV-5.0; a story with at least 3 indexed chapters (the fixture story is fine) |
| Test data | The fixture story |
| Procedure | 1. Open the story → Narrative Threads → Scan Threads. Note the clock time  2. While it says "Scanning your chapters…", click Scan again (it should stay one scan)  3. Navigate to another panel and back: the scanning notice must still be there  4. Wait for the outcome. Note the clock time  5. `curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/stories/<id>/narrative-threads/scan-status` |
| Expected result | Threads appear (or "found no narrative threads", or a plain failure message) without a page reload; step 5 shows `completed` with `threads_written` ≥ 1 for the fixture; only one scan row per story |
| Expected scan time (review L4) | One model call per 3 chapters (up to 1,050 output tokens each) plus a clustering step. Estimate: 20–40 s per 3 chapters on the A40, so about 1 minute for the 3-chapter fixture and 5–7 minutes for 30 chapters. **Record the real time**; the panel gives up waiting after 10 minutes (the scan keeps running) |
| Failure indicators | The scanning notice never resolves; a failure with no explanation; two scans running at once |
| Evidence to capture | Screenshot of the result; the scan-status JSON; the measured duration and chapter count; `grep narrative_threads /tmp/narratiq-logs/backend.log | tail` (ids and counts only) |
| Checklist affected | "D1 — confirmed live on the pod" |
| Status | **PENDING MANUAL VERIFICATION** |

### MV-5.D2 — Manuscript Report is still there after navigating away

| Field | Value |
|---|---|
| Related task | D2 |
| Requirement | The last report is saved, reloads with its time, and says when chapters changed since |
| What must be tested | Generate → navigate away → back; edit a chapter → stale notice; Regenerate |
| Why the cloud could not verify it | Needs the live model and a browser (the API round trip is cloud-tested) |
| Required environment | Pod, browser |
| Preconditions | MV-5.0; a story with at least 2 indexed chapters |
| Test data | The fixture story |
| Procedure | 1. Manuscript Report → Generate Report  2. Go to another page, come back: the same report shows, with "Generated <time>"  3. Edit and save one chapter, reopen the panel: the amber "Your chapters have changed…" notice shows  4. Regenerate: the notice disappears and the time updates  5. Log in as a second user and request `GET /api/stories/<first user's id>/manuscript-report`: 404 |
| Expected result | As described; the Relationships and "Things to check" sections appear when the data supports them |
| Failure indicators | The report disappears; no stale notice after an edit; any 500 |
| Evidence to capture | Screenshots of steps 2 and 3; the step 5 status code |
| Checklist affected | "D2 — confirmed live on the pod" |
| Status | **PENDING MANUAL VERIFICATION** |

### MV-5.D3 — Plot Hole Detection returns a result

| Field | Value |
|---|---|
| Related task | D3 (see also 3.4) |
| Requirement | The model's answer is readable with guided JSON |
| What must be tested | Plot holes on the fixture and on a longer story; whether vLLM accepts `response_format` |
| Why the cloud could not verify it | Guided decoding is a vLLM 0.9.2 feature; the cloud has no vLLM |
| Required environment | Pod, browser or curl |
| Preconditions | MV-5.0 |
| Test data | The fixture story; any story of 10+ indexed chapters if available |
| Procedure | 1. Run Plot Hole Detection in the UI twice  2. `grep -E "plot_holes|guided JSON" /tmp/narratiq-logs/backend.log | tail -20` |
| Expected result | A result (findings or "no plot holes found") both times; logs show `parse_metric feature=plot_holes outcome=clean` or `salvaged`, and no "guided JSON unsupported (400)" line |
| Acceptable alternative | A "guided JSON unsupported (400) — retrying plain" line means this vLLM build rejected guided decoding and the plain path ran: record it; the defect may then persist and needs a follow-up |
| Failure indicators | "could not be completed"; `outcome=failed` |
| Evidence to capture | The two outcomes and the log lines (they contain no manuscript text) |
| Checklist affected | "D3 — confirmed live on the pod" |
| Status | **PENDING MANUAL VERIFICATION** |

### MV-5.D4 — Style "Thriller" produces a real rewrite, or says honestly that it could not

| Field | Value |
|---|---|
| Related task | D4 (5.10) |
| Requirement | Thriller at moderate/strong changes the text noticeably; if it cannot, the author is told, not shown the unchanged text as a rewrite |
| What must be tested | Style prompt v3 with the near-no-op guard, in the sidebar and the selection toolbar |
| Why the cloud could not verify it | Output quality needs the live model |
| Required environment | Pod, browser |
| Preconditions | MV-5.0; `PROMPT_VERSION` not set in the RunPod UI (the default is now `v3`) |
| Test data | Fixture chapter 1, first two paragraphs |
| Procedure | 1. Select the paragraphs → Style → Thriller → Strong. Repeat at Moderate  2. Repeat from the AI Tools sidebar  3. `grep -E "prompt_version\] transform=style|near_noop" /tmp/narratiq-logs/backend.log | tail` |
| Expected result | A clearly tighter, tenser rewrite with the same events and names; the log shows `version=v3`. If a `[near_noop] … reported as no change` line appears, the UI must show "The AI could not find a meaningful change to make…" and offer no Insert button |
| Failure indicators | Near-identical text presented as a normal result; `version=v2` in the log (a stale `PROMPT_VERSION`) |
| Evidence to capture | Before/after text of one run (fixture text only); the log lines |
| Checklist affected | "D4 — confirmed live on the pod"; informs 5.10's author review |
| Status | **PENDING MANUAL VERIFICATION** |

---

## C. AI quality measurements (pod, no author judgement needed)

### MV-5.14-A — Timeline reasoning, live

| Field | Value |
|---|---|
| Related task | 5.14 "Strengthen timeline reasoning (Critical 4)" |
| Requirement | The continuity check reports a planted date reversal and does not report a legitimate flashback |
| What must be tested | The model's verification of the deterministic timeline candidates (prompt v3) |
| Why the cloud could not verify it | The deterministic part is cloud-tested (planted reversal 100% recall, flashback control 0 candidates); whether the model confirms it needs vLLM |
| Required environment | Pod |
| Preconditions | MV-5.0 |
| Test data | Two disposable stories created in the fixture account: (a) chapters anchored "May 2, 2010", "May 9, 2010", "April 20, 2010" with no flashback wording; (b) the same, but chapter 3 opens "In a flashback to April 20, 2010…" and chapter 4 returns to "May 10, 2010". Index them (Sync Summaries) |
| Procedure | Run Continuity Check on each story 3 times |
| Expected result | (a) a `timeline` finding citing chapters 2 and 3 in at least 2 of 3 runs; (b) no timeline finding about chapter 3 in any run |
| Failure indicators | (a) never reported; (b) the flashback reported as an error |
| Evidence to capture | The findings JSON of each run |
| Checklist affected | 5.14 timeline item (the author ticks it, together with MV-5.14-D) |
| Status | **PENDING MANUAL VERIFICATION** |

### MV-5.14-B — Narrative reasoning, live

| Field | Value |
|---|---|
| Related task | 5.14 "Strengthen narrative reasoning (Critical 5)" |
| Requirement | "Things to check" lists real structural issues, and the continuity check confirms only real ones |
| What must be tested | Narrative signals on a story with a character who vanishes and a dead-end thread |
| Why the cloud could not verify it | Needs indexed summaries from the live model and a completed thread scan |
| Required environment | Pod, browser |
| Preconditions | MV-5.0, MV-5.D1 |
| Test data | A disposable story of 8+ chapters where a named character appears in chapters 1–2 and never again |
| Procedure | 1. Index, run the thread scan  2. Generate the Manuscript Report  3. Run Continuity Check |
| Expected result | "Things to check" lists the character disappearance citing chapters 1–2; any continuity finding about it cites real chapters |
| Failure indicators | A signal with no chapters; a continuity finding citing a non-existent chapter |
| Evidence to capture | Screenshot of the section; the continuity JSON |
| Checklist affected | 5.14 narrative item |
| Status | **PENDING MANUAL VERIFICATION** |

### MV-5.14-C — Relationships section, live

| Field | Value |
|---|---|
| Related task | 5.14 "Add relationship arc analysis (Medium 11)" |
| Requirement | The Relationships section shows each pair's changes in chapter order with chapter chips |
| What must be tested | The deterministic aggregation on real indexed data |
| Why the cloud could not verify it | `relationship_changes` is written by the live summariser |
| Required environment | Pod, browser |
| Preconditions | MV-5.0; chapters indexed under the Stage 4 summary prompt (migration 0017 fields present) |
| Test data | The fixture story |
| Procedure | Generate the Manuscript Report; expand each Relationships card |
| Expected result | Pairs named by current character names, changes in chapter order; no raw ids |
| Failure indicators | Raw UUIDs shown; changes out of order |
| Evidence to capture | Screenshot |
| Checklist affected | 5.14 relationship item |
| Status | **PENDING MANUAL VERIFICATION** |

### MV-5.8-A — Emotion measurement

| Field | Value |
|---|---|
| Related task | 5.8 verification boxes 1 and 2 |
| Requirement | Emotion scenarios measured; distinct emotions produce measurably distinct outputs |
| What must be tested | `backend/tests/measure_emotion_set.py` against the live model |
| Why the cloud could not verify it | Needs vLLM and BGE-M3 |
| Required environment | Pod |
| Preconditions | MV-5.0 |
| Test data | The golden-set passages (fixture text, not author manuscripts) |
| Procedure | `cd backend && python3 tests/measure_emotion_set.py --label after_v3` |
| Expected result | A report at `tests/fixtures/emotion_measurement_after_v3.json`. Record `mean_cross_emotion_similarity` (lower = more distinct; outputs of different emotions that are nearly identical would read above ~0.85), `mean_shared_phrase_rate` and `unchanged_outputs` (expect 0) |
| Failure indicators | `unchanged_outputs` > 0; cross-emotion similarity near 1.0 |
| Evidence to capture | The summary block the script prints; commit the JSON report |
| Checklist affected | 5.8's two verification boxes (tick only with the numbers recorded) |
| Status | **PENDING MANUAL VERIFICATION** |

### MV-5.G — Golden set under v3, with the Thriller scenarios

| Field | Value |
|---|---|
| Related task | 5.16 re-measurement; D4 |
| Requirement | v3 does not regress the other transforms (they use their v2 prompts) and changes Thriller output |
| What must be tested | The standard golden set plus the opt-in D4 Thriller scenarios |
| Why the cloud could not verify it | Needs vLLM and BGE-M3 |
| Required environment | Pod |
| Preconditions | MV-5.0 |
| Test data | Golden-set passages |
| Procedure | `cd backend && python3 tests/measure_transform_golden_set.py --label after_v3 --d4-thriller` |
| Expected result | Non-style scenarios within noise of `after_v2`; Thriller scenarios with `byte_identical_rate` 0 and visibly lower text similarity at strong than at moderate |
| Failure indicators | A non-style scenario moving well outside its earlier stdev; Thriller byte-identical |
| Evidence to capture | The report JSON; a short before/after table |
| Checklist affected | Evidence for 5.16's re-measurement note and D4 |
| Status | **PENDING MANUAL VERIFICATION** |

---

## D. Author decisions and reviews (only Arshith can close these)

### MV-5.14-D — Accept (or not) 5.14's three items

| Field | Value |
|---|---|
| Related task | 5.14 items Critical 4, Critical 5, Medium 11; gate line "All 15 Story Audit issues closed or accepted" |
| Requirement | The author decides whether the new dedicated mechanisms close the three items |
| What must be tested | The author's judgement, informed by MV-5.14-A/B/C |
| Why the cloud could not verify it | An author decision (plan review M4) |
| Required environment | None beyond the evidence above |
| Preconditions | MV-5.14-A, B, C done |
| Test data | — |
| Procedure | For each of the three items, record one of: **accept** (tick it with the evidence), **accept with a follow-up** (tick and name the follow-up), or **reject** (keep it open, say what is missing) |
| Expected result | Three recorded decisions with the date |
| Failure indicators | — |
| Evidence to capture | The decision text in the checklist next to each item |
| Checklist affected | 5.14's three items; the gate line |
| Status | **PENDING AUTHOR DECISION** |

### MV-5.BR — Blind author review, and Gate 3b

| Field | Value |
|---|---|
| Related task | Stage 5 gate lines "Blind author review passed" and Gate 3b |
| Requirement | The author judges transform, suggestion and Story Audit output quality without knowing which prompt version made it |
| What must be tested | Tone, emotion, audience, style (incl. Thriller), translation, suggestions, continuity and the manuscript report |
| Why the cloud could not verify it | Subjective by design |
| Required environment | Pod, browser |
| Preconditions | MV-5.G done (it produces the outputs to compare) |
| Test data | Golden-set outputs from `after_v2` and `after_v3`, shuffled by someone else or by a script, labels hidden |
| Procedure | For each pair, pick the better one or "no difference"; then reveal the labels |
| Expected result | v3 preferred or equal on style; no transform clearly worse |
| Failure indicators | v3 clearly worse on any transform |
| Evidence to capture | The tally |
| Checklist affected | The two gate lines |
| Status | **PENDING AUTHOR REVIEW** |

### MV-5.AR — The per-task author reviews still open

| Field | Value |
|---|---|
| Related task | 5.7, 5.10, 5.11, 5.13, 5.15, 5.16 author-review boxes |
| Requirement | Each open "author review" box is judged by the author |
| What must be tested | As written in each task's own box |
| Why the cloud could not verify it | Subjective by design |
| Required environment | Pod, browser |
| Preconditions | MV-5.0 |
| Test data | The fixture story |
| Procedure | Work through each task's open author-review box in the checklist; 5.10 should include the Thriller result from MV-5.D4 |
| Expected result | Each box ticked with a dated note, or left open with the reason |
| Failure indicators | — |
| Evidence to capture | The notes |
| Checklist affected | Those boxes |
| Status | **PENDING AUTHOR REVIEW** |

---

## E. Browser checks with no AI dependency

Covered inside MV-5.D1 (scan notices, resume after navigation) and MV-5.D2 (saved report, stale notice). One
extra check: build the frontend with `NEXT_PUBLIC_P3_ENABLED=false` and confirm the Narrative Threads and
Manuscript Report panels still work (they are not Phase 3 features and must not depend on that flag).

---

## STAGE VERIFICATION SUMMARY

| | Count | Items |
|---|---:|---|
| **Cloud verified** | 9 | Migration 0023 (round trip incl. after `create_all()`, `alembic check` adds no drift); D1 scan lifecycle, concurrency, outcomes, ownership, orphan sweep; D2 upsert, GET, stale, cross-user 404, cascade on project delete; D3 guided JSON on/off, 400 fallback, content-free logs, budget; D4 style v3, guard, strong skip, UI message; 5.14 timeline/narrative/relationship modules and continuity wiring; prompt v3 resolution for every transform; 5.8 harness logic; `tsc` and 90/90 frontend unit tests |
| **Manual verification pending** | 12 | MV-5.0, MV-5.KD, MV-5.D1, MV-5.D2, MV-5.D3, MV-5.D4, MV-5.14-A, MV-5.14-B, MV-5.14-C, MV-5.8-A, MV-5.G, browser flag check (E) |
| **Author decision / review pending** | 3 | MV-5.14-D, MV-5.BR, MV-5.AR |
| **Blocked** | 0 | — |
| **Failed** | 0 | — |

**Stage gate: OPEN — MANUAL VERIFICATION PENDING.** Open gate lines: "All 15 Story Audit issues closed or
accepted" (MV-5.14-A–D), "Blind author review passed" and Gate 3b (MV-5.BR), and the four "D1–D4 confirmed live"
boxes (MV-5.KD, MV-5.D1–D4).
