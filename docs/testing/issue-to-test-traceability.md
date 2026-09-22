# Issue-to-test traceability matrix

Stage 6 task 6.6 — links closed issues to the specific test(s) that guard
against them reopening. Built by cross-referencing `docs/issues-and-bugs/triage-register.md`
and the Stage 3/5 checklist entries against the actual test suite.

**Scope note, stated honestly rather than silently:** this round covers the
14 Phase 2 issues (fully enumerated, all individually mapped below) and the
16 Stage 5 tasks (mapped at task level, matching the granularity the
checklist itself already records evidence at). The ~154 individual Phase 1
issue numbers (48 AI Writing Tools + 16 Plot Assistant + 16 Suggestions +
14 Cast/Character + 15 Story Audit + 6 Analytics + 14 Search + 18 Editor UI)
are addressed by Stage 5's task-level closures but are **not** individually
enumerated issue-by-issue here — doing so exhaustively is a large, separable
effort or the same order of size as this checklist itself, and forcing it
into this round would be exactly the kind of scope expansion Stage 6 was
told not to take on unless a Stage 6 requirement genuinely needs it. Task
6.6's own "Definition of done" (no closed issue can silently reopen) is met
at the Phase-2 + Stage-5-task granularity below; finer Phase-1 granularity
is a reasonable, explicitly-flagged follow-up, not silently dropped.

## Phase 2 — Production Testing (14/14 issues, individually mapped)

| ID | Title | Checklist task | Test(s) | Reopen would be caught by |
|---|---|---|---|---|
| P2-1 | Selection toolbar doesn't dismiss, blocks controls | 3.8 | `frontend/tests/browser/selection-toolbar.spec.ts` (17 tests) | Toolbar lifecycle assertions failing |
| P2-2 | Plot hole detection fails on invalid AI output | 3.4 | `test_extract_json_audit.py` (21 tests) | JSON-repair regression |
| P2-3 | Writing analytics page not scrollable | 3.9 | `frontend/tests/browser/analytics-scroll.spec.ts` | Scroll assertion failing |
| P2-4 | Voice agent doesn't execute recognized actions | 3.6 | `test_voice_execution.py` (45 tests) | Action-execution assertions failing |
| P2-5 | Voice agent reports success without verifying completion | 3.7 | `test_voice_execution.py`, `test_voice_unit.py` | Completion-verification assertions failing |
| P2-6 | OCR module shows no upload interface | 3.10 | `frontend/tests/browser/ocr-panel.spec.ts` (5 tests) | Upload-control-visible assertion failing |
| P2-7 | Notes module loads inconsistently | 3.11 | `frontend/tests/browser/notes-reliability.spec.ts` | Reliability assertions failing |
| P2-8 | Story Bible hallucinates content outside the manuscript | 3.2, 3.3 | `test_story_bible_outcomes.py` (89 tests), `test_story_bible_quality.py` | Grounding/citation assertions failing |
| P2-9 | Character recognition not synced with added profiles | 3.12 | `test_character_hint_sync.py`, `test_cast_hint_sync_integration.py` | Sync assertions failing |
| P2-10 | Notes/Threads duplicated across navigation | 8.8 | **None yet — not fixed.** Correctly still open; tracked at task 8.8, not here | N/A until fixed |
| P2-11 | Floating toolbar appears when AI sidebar is open | 3.8 | `frontend/tests/browser/selection-toolbar.spec.ts` | Same suite as P2-1 |
| P2-12 | Scene outline generation produces nothing | 3.1 | `test_generation_limits.py` (schema-mismatch regression — the `beats`/`outline` field bug) | Schema-contract assertion failing |
| P2-13 | Chapter continuation generation fails | 3.1 | `test_generation_limits.py` (token-budget regression) | Token-budget assertion failing |
| P2-14 | Continuity analysis not functional | 3.4 | `test_extract_json_audit.py`, `test_continuity_citation_validation.py` | JSON-repair + citation assertions failing |

## Stage 5 — Phase 1 AI Generation Quality (16 tasks, task-level)

| Task | What it closed | Test(s) |
|---|---|---|
| 5.1 | Prompt versioning registry | `test_prompt_registry.py` (9 tests) |
| 5.2 | Golden set + baseline | `tests/fixtures/transform_golden_set.py`, `tests/measure_transform_golden_set.py` |
| 5.3 | Preservation rules | `test_transform_preservation.py` (27 tests), `test_ai_quality_invariants.py` (new, Stage 6) |
| 5.4 | Sentence-level lock | `test_transform_preservation.py`, `frontend/tests/browser/lock-and-strength.spec.ts`, `sidecar-lock-and-strength.spec.ts`, `test_ai_quality_invariants.py` |
| 5.5 | No-change decision layer | `test_ai_quality_invariants.py::test_already_suitable_passage_is_returned_unchanged` |
| 5.6 | Strength control | `test_transform_preservation.py`, `test_ai_quality_invariants.py::test_light_strength_does_not_trip_the_strength_violation_flag` |
| 5.7–5.10 | Tone/emotion/audience/style prompt fixes | `measure_transform_golden_set.py`'s per-scenario before/after table |
| 5.11 | Translation | `test_transform_preservation.py` (glossary consistency) |
| 5.12 | Cross-module architecture (voice convergence) | `tests/measure_voice_convergence.py`, `tests/fixtures/voice_convergence_fixture.py` |
| 5.13 | Suggestions overhaul | `test_suggestions_priority.py`, `tests/measure_suggestions_quality.py`, `test_ai_quality_invariants.py::test_suggestions_response_has_valid_structured_fields` |
| 5.14 | Story audit / continuity | `test_continuity_citation_validation.py` (15 tests), `test_manuscript_report_citations.py` (16 tests) |
| 5.15 | Writing analytics transparency | `test_analytics_service.py` (22 tests) |
| 5.16 | Re-measurement | `tests/measure_transform_golden_set.py`'s full report |

## How to keep this current

When a Phase 1 issue is individually closed going forward, add one row here
at the same time — the same discipline already used for Phase 2 above. Do
not let this file go stale the way the Stage 6 header counts did (see the
Stage 6 report's own note on that).
