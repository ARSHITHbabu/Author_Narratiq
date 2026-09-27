# Stage 9 — Full Regression Results (task 9.1)

| | |
|---|---|
| **Checklist task** | 9.1 — Full regression run |
| **Run date** | 2026-09-27 |
| **Pod** | `6uavswo19trx9n` — 1× NVIDIA A40 (48 GB), fresh pod; brought up with `start-narratiq.sh` through the path symlink `/workspace/narratiq-ai → /workspace/Author_Narratiq` (script portability is a Stage 10/11 item) |
| **Code** | `main` at `6debfe2` plus the uncommitted Stage 9 changes listed in the Stage 9 report |
| **Runtime** | vLLM 0.9.2 serving Qwen2.5-7B-Instruct (TP=1, max_model_len 8192); BGE-M3 in-process **on CPU** (`bge_device` default); PostgreSQL 16 + pgvector; Alembic head `0023` |
| **Runner** | `backend/tests/run_full_regression.sh` (new) — one summary line per suite |
| **Test data** | Allow-listed `narratiq_test` only (conftest guard). The live `narratiq` database is empty on this pod and no test wrote to it |

## Results

| Suite | Command | Result | Notes |
|---|---|---|---|
| Backend (full, excl. known-defect marker) | `run_full_regression.sh backend` | **738 passed, 0 failed** (1 xfailed = the chapter-reorder API gap from 6.3; 4 deselected = known-defect marker) — final run after every Stage 9 change | First run: 728 passed, 2 failed — both in the new `test_security_stage9.py` rate-limit tests, caused by two existing tests that switch the global limiter off and never restore it (`test_retrieval_signatures.py`, `test_story_bible_outcomes.py`). Fixed in the new tests with a fixture that forces the limiter on for their own duration |
| Known Stage 5 defects (live model, own uvicorn on :8099) | `run_full_regression.sh known-defects` | **4 passed** | First attempt: 4 errors — the test server needs > 90 s to start while other suites load the CPU (BGE-M3 on CPU). Passed on an idle pod. This is MV-5.KD's evidence |
| Stage 4 retrieval suite | `run_full_regression.sh retrieval` | **96 passed** | |
| Migration round-trip | `run_full_regression.sh migration` | **PASS** | head → 0018 (7/7 author tables byte-identical, idea card survives as a note card) → head → head again (no-op) |
| Frontend unit | `npm test` | **99 passed** | |
| Frontend studio (mocked API) | `npm run test:studio` | **65 passed** | |
| Accessibility (axe) | `npm run test:a11y` | **13 passed** | |
| Build variants (mock-tool, p3-off) | `npm run test:studio:variants` | **20 passed** | |
| Live browser (`--project=browser`, 64 tests) | see below | **62 passed, 1 failed, 1 skipped** | Failed: `manuscript-upload.spec.ts` — the **known product gap** from task 6.4 (no upload control in the UI); the test is written to fail until the feature exists. Skipped: `audio-transcription.spec.ts` — needs a real speech recording (manual, as in 6.4) |
| Selection-toolbar test 9 (Escape order), repeated | `-g "9: Escape" --repeat-each=10` | **10/10 passed** | Stage 7 carry-forward (7.15) and MV-8.3 |
| AI quality invariants | `pytest test_ai_quality_invariants.py` | **12 passed** | Live model |
| New Stage 9 suites | isolation, security, targeted issues | **all passed** (see Stage 9 report) | `test_cross_user_isolation.py` 11, `test_security_stage9.py` 30, `test_stage9_targeted_issues.py` 8 |

### How the live browser suite was run

Against an isolated stack bound to the test database, never the live one:

* backend `uvicorn main:app --port 8100` with `DATABASE_URL=…/narratiq_test`, `CORS_ORIGINS` for :3200, and
  every `RATE_LIMIT_*` raised to `1000/minute` **for this test stack only** (every spec signs in through the
  API, and the 5/minute login limit otherwise returns 429 after five specs). Rate limiting itself is verified
  separately in `test_security_stage9.py`;
* frontend `next build` with `NEXT_DIST_DIR=.next-e2e NEXT_PUBLIC_API_URL=http://localhost:8100`, served on :3200;
* `E2E_API_URL=http://localhost:8100` and `E2E_BASE_URL=http://localhost:3200` (the specs default to the live
  :8000/:3000);
* one worker, and **one fixture story per spec**, created by the new `backend/scripts/seed_browser_fixtures.py`.

**Test-infrastructure defects found and fixed while getting to a clean run** (none were product defects):

1. `seed_fixture.py` used `e2e-fixture@narratiq.test`; the installed `email-validator` (≥ 2.1) rejects the
   reserved `.test` domain, so login answered 422. Now `@narratiq-internal-test.com` (also in `voice_e2e_smoke.py`).
2. The live specs each expect their own seeded text ("The lighthouse…", the two "sensor" sentences, a chapter
   titled "Fixture", a note "Tide chart margins", two similar hints, an empty story) but all read one
   `E2E_STORY_ID`. Earlier stages seeded these by hand; `seed_browser_fixtures.py` now creates them.
3. `story-bible-generation` and `character-hint-sync` need the story **indexed** first (the backend correctly
   answers 422 "No indexed chapters found", and mention indexing is queued only for indexed chapters).
   Documented in the seeding script.
4. With Playwright's default worker count (half of 96 cores) the specs overlap on shared fixture data; the run
   uses `--workers=1`.

Operator error recorded for honesty: the first two live runs omitted `E2E_API_URL`, so their sign-in requests
went to the live :8000 backend and failed (401/429). The live database is empty and nothing was written.

## AI quality harness — compared with the last recorded baselines

| Measurement | Baseline | Stage 9 (prompt v3 for style, v2 elsewhere) | Reading |
|---|---|---|---|
| Transform golden set (12 standard scenarios) | `transform_golden_after_v2.json` | `transform_golden_stage9_20260927.json` | Every scenario within noise (largest Δ text similarity +0.029, inside its recorded stdev); the same 5 scenarios byte-identical (the no-change layer declining text already in the target register) |
| Golden set + D4 Thriller (MV-5.G) | — | `transform_golden_stage9_20260927_d4.json` | Thriller is **never byte-identical** (0/8) — the D4 near-no-op is gone. **Strong vs moderate is not reliably stronger**: lower similarity at strong for 2 of 4 passages, equal for 1 (tech-2, 0.923 — a light rewrite), higher for 1. Recorded as an AI-quality finding for author review, not a pass |
| Voice convergence (5.12-H) | after_v2: text Δ +0.0041, content Δ −0.0117 | text Δ +0.0099, content Δ −0.0076 | No convergence; unchanged |
| Emotion set (MV-5.8-A — first live measurement) | none | 48 scenarios; unchanged outputs **0**; mean cross-emotion similarity **0.4985** (max 0.6365); shared-phrase rate 0.109 | Distinct emotions produce distinct outputs (the guide's warning line is ~0.85). Evidence for 5.8's two verification boxes |
| Suggestions quality (5.13) | after: recall 1.00, 10 categories, soft praise present | recall **1.00**, **10** categories, soft praise **none**, all prioritised | Unchanged or better |
| Preservation checks (5.9) | committed report | `preservation_checks_measurement_stage9_20260927.json` | Recall 1.00 on every broken-rewrite class (tense, POV, dialogue, timeline) |
| Continuity depth (5.14) | committed report | `continuity_depth_report_stage9_20260927.json` | Same verdicts as the committed report; only the model's wording differs |
| Phase 3 live E2E | 18/18 recorded | not re-run (covered by `phase3-pins-compare.spec.ts` 4/4 live and the Phase 3 backend tests) | |

The committed measurement files were not overwritten: two scripts write to fixed names, so their Stage 9
output was saved under `*_stage9_20260927.json` and the committed files were restored from `HEAD`.
