# Author feature test checklist — automation matrix

Source: `docs/testing/author-feature-test-checklist.docx` (40 rows across 6 tables).
Built for Stage 6 task 6.3. Per explicit instruction, rows are NOT forced into
backend pytest merely to reach 40/40 — each is classified into the lowest
appropriate testing layer, and every row is traceably accounted for (a
passing/failing automated test, or a named manual exception).

**Layers used:** `backend` (pytest, `backend/tests/`), `frontend-unit`
(Playwright `--project=unit`), `browser` (Playwright `--project=browser`,
needs a live stack), `live-ai` (quality judgment, task 6.5's harness —
never per-commit), `manual` (documented reason it stays manual).

## Table 0 — Writing and editor

| # | Feature | Layer | Where | Status |
|---|---|---|---|---|
| 1 | Rich text editor + autosave + refresh persistence | `browser` | new spec, 6.4 (`autosave-persistence.spec.ts`) | Planned — see 6.4 section of the Stage 6 report |
| 2 | Project/story management (create/rename/delete) | `backend` | `test_e2e_checklist_gaps.py::test_project_create_rename_delete_persists_correctly` | **New, passing** — asserts DB state after rename/delete, not just HTTP 200 |
| 3 | Chapter management (create, reorder) | `backend` | `test_e2e_checklist_gaps.py::test_chapter_creation_persists_and_increments_number` (create) + `::test_chapter_reorder_before_earlier_chapter` (reorder) | Create: **new, passing**. Reorder: **new, `xfail(strict=True)` — genuine gap found**: no API can reorder a chapter at all (`ChapterUpdate` has no `chapter_number` field; no dedicated reorder route exists anywhere) |
| 4 | Search & replace | `backend` | `test_search_module.py` (existing, whole-word/case-sensitive matching, occurrence-indexed replace) | Existing coverage, unit-level. No integration-level "hit the real endpoint" test added — the underlying matching logic is already well covered |
| 5 | Export DOCX/PDF | `backend` | `test_e2e_checklist_gaps.py::test_export_docx_produces_a_valid_openable_document` + `::test_export_pdf_produces_nonempty_pdf_bytes` | **New, passing** — actually opens the DOCX with `python-docx` and checks content, checks the PDF magic byte header, not just a 200 |

## Table 1 — AI text transforms

| # | Feature | Layer | Where | Status |
|---|---|---|---|---|
| 1 | Refine | `live-ai` | 6.5 golden set (`transform_golden_set.py`) | Covered by Stage 5's existing golden set + 6.5's packaging |
| 2 | Change tone | `live-ai` + `backend` | 6.5 golden set; deterministic preservation checks in `test_transform_preservation.py` | Existing coverage |
| 3 | Rewrite emotion | `live-ai` | Not in the golden-set harness by design (5.8's own note: emotion is excluded from the no-change/strength architecture) | Existing limitation, not a Stage 6 gap — see 5.8 |
| 4 | Audience adaptation | `live-ai` + `backend` | 6.5 golden set; `test_transform_preservation.py` | Existing coverage |
| 5 | Style rewrite | `live-ai` + `backend` | 6.5 golden set; **also** `test_known_stage5_defects.py::test_style_transform_produces_a_meaningfully_different_thriller_rewrite` | Existing coverage + a dedicated regression guard for the author's 2026-09-22 Thriller finding |
| 6 | Author-inspired style | `live-ai` | Not separately golden-set-measured | Existing limitation, out of Stage 6 scope |
| 7 | Translation | `backend` (glossary consistency) + `live-ai` (fluent-speaker quality) | `test_transform_preservation.py` (glossary); native-speaker review still pending per Stage 5's own note | Existing coverage; the fluent-speaker judgment was never automatable |
| 8 | AI writing suggestions | `backend` + `live-ai` | `test_suggestions_priority.py`; `measure_suggestions_quality.py` | Existing coverage |
| 9 | Chapter continuation | `backend` | `test_generation_limits.py` (token-budget/schema contract regression) | Existing coverage |
| 10 | Chapter outline | `backend` | `test_generation_limits.py` (schema-mismatch regression — the `beats` vs `outline` field bug) | Existing coverage |

## Table 2 — Story intelligence

| # | Feature | Layer | Where | Status |
|---|---|---|---|---|
| 1 | Genre detection | `backend` | `test_genre_detection.py` | Existing coverage |
| 2 | Emotional arc | `backend` | Covered indirectly via Stage 4 story-intelligence tests | Existing coverage |
| 3 | Continuity check | `backend` | `test_continuity_citation_validation.py`, `measure_continuity_depth.py` | Existing coverage |
| 4 | Style drift | `backend` | `test_e2e_checklist_gaps_2.py::test_style_drift_handles_a_short_manuscript_without_crashing` | **Filled (2026-09-22 closure).** Asserts honest degradation (not a crash) below the endpoint's own documented 6-chapter minimum for a real drift computation |
| 5 | Duplicate scene | `backend` | `test_semantic_dedup.py` | Existing coverage |
| 6 | Narrative threads | `backend` | `test_known_stage5_defects.py::test_narrative_threads_scan_detects_the_manuscripts_mystery_thread` | **New — `known_stage5_defect`, currently failing on purpose.** Scan completes but detects 0 threads on a manuscript with a clear one |
| 7 | Plot hole detection | `backend` | `test_known_stage5_defects.py::test_plot_hole_detection_returns_a_parseable_result` | **New — `known_stage5_defect`, currently failing on purpose.** Model output fails to parse as JSON on both the initial call and the retry |
| 8 | Plot assistant | `backend` | `test_e2e_checklist_gaps_2.py::test_plot_assistant_answers_a_question_about_the_manuscript` | **Filled (2026-09-22 closure).** Real vLLM call, asserts a real answer/suggestions payload |
| 9 | Editorial report (manuscript report) | `backend` | `test_manuscript_report_citations.py` (citation validity); `test_known_stage5_defects.py::test_manuscript_report_persists_across_a_refetch` | Citation logic: existing coverage. Persistence: **new — `known_stage5_defect`, currently failing on purpose.** No `db.add`/`db.commit` anywhere in `routers/manuscript_report.py` |
| 10 | Copyright risk | `backend` | `test_author_style_and_copyright.py` | Existing coverage — **includes the 3 pre-existing, already-documented failures** (overall-risk derivation bug in `analyze_copyright_risk`), unrelated to Stage 6, unchanged by it |

## Table 3 — Characters and world

| # | Feature | Layer | Where | Status |
|---|---|---|---|---|
| 1 | Character bible (cast generation) | `backend` | `test_cast_classification_accuracy.py`, `test_cast_hint_sync_integration.py` | Existing coverage |
| 2 | Character profiles | `backend` | `test_character_hint_sync.py`, `test_character_merge.py` | Existing coverage |
| 3 | Relationship graph | `backend` | `test_character_merge.py` (relationship reassignment on merge) | Existing coverage |
| 4 | Character arc timeline | `backend` | `test_chapter_arc_fields.py` | Existing coverage |
| 5 | Voice consistency | `backend` | `test_e2e_checklist_gaps_2.py::test_voice_consistency_check_handles_sparse_dialogue_without_crashing` (note: distinct from the Voice Agent, per CLAUDE.md's explicit warning not to confuse the two) | **Filled (2026-09-22 closure).** Asserts honest degradation below the endpoint's own documented 3-dialogue-passage minimum |
| 6 | Story Bible generator | `backend` | `test_story_bible_outcomes.py` (89 tests), `test_story_bible_quality.py` | Existing, extensive coverage |

## Table 4 — Input and ingestion

| # | Feature | Layer | Where | Status |
|---|---|---|---|---|
| 1 | Manuscript upload | `backend` + `browser` | Backend: `test_e2e_checklist_gaps.py::test_manuscript_docx_upload_creates_chapters_from_content` (passing). Browser: `frontend/tests/browser/manuscript-upload.spec.ts` | **Split result, corrected 2026-09-22 closure.** Backend endpoint fully works. **Real frontend gap found executing the browser spec live:** `manuscriptApi.upload` (lib/api.ts) is never called from any component — confirmed via exhaustive `grep -rln "manuscriptApi\."` across `app/` and `components/` (zero results) and by opening every workspace tab live. An author cannot upload a manuscript through the UI at all today. The browser spec now documents this as a reproducible, plainly-failing check |
| 2 | OCR | `browser` | `frontend/tests/browser/ocr-panel.spec.ts` | Existing coverage |
| 3 | Audio transcription | `manual` | `frontend/tests/browser/audio-transcription.spec.ts` (full justification + manual procedure in its own docstring) | **MANUAL, justified (2026-09-22 closure).** No TTS tool available in this environment to generate a real speech fixture (checked: espeak/espeak-ng/festival, gtts/pyttsx3, ffmpeg — all absent); a silent/tone fixture would only prove upload plumbing, not real transcription, risking a false pass |
| 4 | Notes/cards | `backend` | `test_e2e_checklist_gaps_2.py::test_note_create_and_list_persists` + `::test_note_card_create_and_list_persists` (routes are under `/api/ocr/`, not `/api/stories/` — found while writing this test) | **Filled (2026-09-22 closure)** |

## Table 5 — Productivity and platform

| # | Feature | Layer | Where | Status |
|---|---|---|---|---|
| 1 | Voice agent | `browser` | new spec, 6.4 (`voice-agent-action.spec.ts`) | Planned — see 6.4 section of the Stage 6 report |
| 2 | Pacing goals | `backend` | `test_e2e_checklist_gaps_2.py::test_pacing_goal_set_and_persists` | **Filled (2026-09-22 closure)** |
| 3 | Writing analytics | `backend` | `test_analytics_service.py` (22 tests) | Existing, extensive coverage |
| 4 | Activity timeline | `backend` | `test_e2e_checklist_gaps.py::test_activity_event_record_and_list_round_trip` | **New, passing at the API level.** Separately and importantly: the live database was found to have **zero** `activity_events` rows despite real author usage during the 2026-09-22 session, even though a frontend caller (`StoryContextEngine.tsx`) exists. This test proves the record/list endpoints themselves work; it does not explain why the real trigger path produced nothing. Per explicit instruction, this is recorded as a documented open observability gap, not expanded into an audit-logging investigation |
| 5 | JWT auth (register/logout/login/persistence) | `backend` | `test_e2e_checklist_gaps.py::test_register_then_login_again_sees_the_same_projects` | **New, passing** — a real register → create project → re-login → list projects round trip |

---

## Summary

**As of the 2026-09-22 closure pass** (all 5 new Playwright browser specs executed live against a real stack; all 6 previously-documented backend gaps filled or explicitly justified as manual):

- **40/40 rows accounted for.**
- **21** already had existing coverage (referenced, not duplicated).
- **16** now have new, passing automated tests (project CRUD, chapter creation, DOCX/PDF export, manuscript-upload backend, activity round-trip, JWT round-trip, style-transform regression guard, style drift, plot assistant, voice consistency, notes, note cards, pacing goals, autosave persistence [browser], story bible generation [browser], voice agent action [browser]).
- **3** are `known_stage5_defect` — genuinely broken, deliberately failing, excluded from required CI, runnable on demand (narrative threads, plot holes, manuscript report persistence) — confirmed live: 2 reproduce deterministically (narrative threads, manuscript report persistence), 1 (plot holes) is real but sampling-dependent and did not reproduce in this run.
- **2** are newly-found `xfail`/plainly-failing gaps, confirmed live, not worked around: chapter reorder (no API exists at all) and manuscript upload (no frontend UI exists at all, despite a working backend).
- **1** is genuinely MANUAL with a documented justification and step-by-step procedure: audio transcription (no TTS tool available in this environment to generate a real speech fixture).
- **1** (OCR) already has full, existing browser coverage.

**6.4's 5 new Playwright browser specs — final live results:** autosave persistence **PASS**, story bible generation **PASS**, voice agent action **PASS**, manuscript upload **FAIL** (real product gap, not a selector bug), audio transcription **MANUAL** (justified above). 3 real selector/timing bugs were found and fixed in the FIRST three specs while executing them live (documented in each file's own comments) — none were product bugs.
