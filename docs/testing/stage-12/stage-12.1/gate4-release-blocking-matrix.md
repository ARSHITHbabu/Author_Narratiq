# Gate 4 — the 114 release-blocking issues, reconciled against the current implementation (Stage 12.1)

| | |
|---|---|
| **Date** | 2026-10-03, pod `x0smrkvs4n6wpk` |
| **Code** | HEAD `f7a7a2e` plus the uncommitted Tranche 3 and Stage 12.1 changes (`repository-state.md`) |
| **Basis** | D-6: Critical and High = release-blocking (114 issues, `docs/issues-and-bugs/triage-register.md`). Severities unchanged. |
| **Supersedes** | the 2026-09-27 classification in `docs/testing/stage-09-qa-rerun-results.md` (kept as recorded) |
| **Method** | Four independent batches checked every issue against current code, current tests (deterministic suites re-run on `narratiq_test`) and recorded live evidence. Then the Stage 12.1 fixes below. Per-issue tables follow. |

## Changes made during Stage 12.1 (applied on top of the batch tables below)

| Issue(s) | Batch finding | Stage 12.1 action | Final state |
|---|---|---|---|
| **SEARCH-1, -2, -3** (Critical) | OPEN_TECHNICAL: out-of-order search responses replaced the current query's results and editor highlights | **Fixed.** `SearchPanel.tsx` numbers each request; only the newest may change the panel, and mode/scope changes invalidate requests in flight. A reproducing studio test (a delayed answer for "D" after "Devika") **fails on the old code and passes on the fix**. Live browser suite: see the completion report | **FIXED_VERIFIED** |
| **AUDIT-H8, -H9, -H10** (High) | OPEN_TECHNICAL: open tracker threads, stakes and plot importance were returned by the backend but never shown | **Fixed.** The Manuscript Report now shows Stakes (with escalation by chapter), "Where the plot moves most", Themes (AUDIT-M12) and "Still open in Narrative Threads". A studio test with an accessibility check covers them | technical cause **fixed**; the content's usefulness is still **HUMAN_JUDGEMENT** (Story Audit author review) |
| **CAST-H6** (High) | OPEN_TECHNICAL: Corvin (a reluctant ally) labelled antagonist in 11/25 live runs; the test tolerates 1 wrong role in 4 | **Fix attempted and rejected.** General role definitions in the cast prompt made it worse: **22/25** antagonist, and presence 19/25 against 21/25 before (`cast-role-definitions-experiment-REJECTED.json`). Reverted; `prompt_registry.py` is identical to HEAD. Invalid role values are already mapped to `supporting` before the author sees them | **OPEN_TECHNICAL** (model role variability) → owner decision |
| AWT-D, AWT-I (Critical); AWT-1.2, 1.6, 3.7 (High) | OPEN_TECHNICAL: at Light strength, Tone and age adaptation barely differ from Strong (median words kept, tone 0.57 vs 0.58, age 0.52 vs 0.48) | **Not fixable here:** A15 measured that Light wording has no effect for these transforms. Enforcement needs the human Light thresholds (A15 open item; labelling sheet in `gate3b-review/`) | **OPEN_TECHNICAL**, blocked on a human input |
| AWT-G (Critical) | OPEN_TECHNICAL (medium confidence): run-to-run variability at or above the pre-fix baseline (golden-set spread 0.074 vs 0.020 for v2), e.g. gothic-1 tone unchanged 3/3 at Stage 9 but rewritten 3/3 now | **Measured, 10 trials** (`awt-g-consistency.md`): mean stdev 0.0866, **criterion not met**. Cause: the temperature-0 no-change assessor is non-deterministic on borderline passages (19/20, 15/20, 3/20 on identical input); the rewrites themselves are stable (0.031). Model-serving variability, not a code defect; no change made | **OPEN** (model variability) → owner decision |
| **PA-C6** (Critical), **PA-H12** (High) | HUMAN_JUDGEMENT: ranking verified at rule level only; the A13 long-manuscript measurement (L3411) open | **Measured** (`pa-long-manuscript-measurement.md`): 40 chapters, 32,228 words, 14 planted scenarios, production path. PA-C6: the critical passage is delivered 12/12 (11/12 after a re-index) but ranked above every decoy only 7/12 (6/12). PA-H12: 1/2 pass. Root cause: BGE-M3 cosine favours decoys that share the question's words; the ranking code reproduces cosine order. A summary-blend design was measured offline and not implemented (partial, non-monotonic gains) | **Known-limitation candidate** → owner decision (accept, or a retrieval-design change) |
| PA-H10 (High), and every chapter-summary consumer | (found during the measurement) | **Defect fixed.** `generate_chapter_summary` read only the first 8,000 characters of a chapter. It now reads the whole chapter in context-sized windows and merges them. Live: a late revelation in a 4,034-word chapter reached the summary 0/3 → 3/3. Tests: `test_chapter_summary_windows.py` (5). On the long fixture, revelations in summaries are 4/7: the misses are model selection, not truncation | technical cause **fixed**; summary usefulness still **HUMAN_JUDGEMENT** (G7) |
| (indexing / retrieval latency; not one of the 114) | (found during the measurement) | **Defect fixed.** BGE-M3 on CPU used 48 torch threads per encode on a 7.65-CPU container quota, with 2 workers. Indexing 40 chapters took 2,653 s; it now takes **220 s**. Median Q&A retrieval latency 448 → 210 ms. Tests: `test_bge_cpu_threads.py` (9). Takes effect at the next backend start | **FIXED_VERIFIED** |
| PA-C1 (Critical) | HUMAN_JUDGEMENT; "not tested: the 4.1 manual check (L1384) and the toggle/badge, which has no frontend test" | **Both gaps closed; one defect fixed.** (1) Studio test `plot-assistant-scope.spec.ts`: default "This chapter", switch to "Full manuscript", the scope sent, the badge, axe. The toggle now exposes its state (`aria-pressed`, labelled group); before, it was colour only. (2) Live 4.1 check through the real UI and backend (`tests/browser/plot-assistant-scope.spec.ts`, `pa-scope-live-runs.log`): a whole-story question from Chapter 1. Chapter scope used only Chapter 1 in 3/3 runs; full scope reached Chapters 2–3 in 3/3. (3) **Defect found by the first live run and fixed:** creative-intent answers reported "0 passages, no chapters" while grounded on three chapter summaries. `retrieval.summary_chapters` now reports them, and the panel shows them (`test_plot_assistant_retrieval_meta.py`, red without the fix) | technical part **verified**; "answers are sound" is still the G7 judgement |

The current six-category view of all 114 (after the owner's decisions) is `gate4-section3-review.md`. The final-state summary below is the reconciliation as first recorded.

## Summary (all 114)

| Final state | Critical | High (incl. SEARCH-4 "High/Critical" and the 7 AWT-5.x translation items, release-blocking at Medium task priority) | Total |
|---|---:|---:|---:|
| FIXED_VERIFIED | 17 | 16 | **33** |
| OPEN_TECHNICAL | 3 | 4 | **7** |
| HUMAN_JUDGEMENT | 19 | 54 | **73** |
| ACCEPTED_LIMITATION (CAST-H10: presence variability, owner-accepted 2026-10-03) | 0 | 1 | **1** |
| EXTERNAL_DEFERRED / NOT_APPLICABLE | 0 | 0 | 0 |
| **Total** | **39** | **75** | **114** |

By category:

| Category | Release-blocking | Fixed | Open | Human | Accepted |
|---|---:|---:|---:|---:|---:|
| AI Writing Tools | 48 | 7 | 6 | 35 | 0 |
| Plot Assistant | 14 | 6 | 0 | 8 | 0 |
| Search | 9 | 9 | 0 | 0 | 0 |
| Cast | 7 | 4 | 1 | 1 | 1 |
| Story Audit | 10 | 0 | 0 | 10 | 0 |
| Suggestions | 11 | 1 | 0 | 10 | 0 |
| Editor UI | 15 | 6 | 0 | 9 | 0 |
| **Total** | **114** | **33** | **7** | **73** | **1** |

Compared with 2026-09-27: 27 PASS → **33 fixed and verified**. Every remaining item now has an owner and a named next step. "Live-pod manual" and "no evidence found" no longer occur.

## Gate 4 consequence

Gate 4 ("zero open Critical; every High fixed or explicitly accepted by the product owner") is **not passed**. 22 Critical items are still open: 3 open technical and 19 that need human judgement. 58 High items are neither fixed nor accepted (4 open technical, 54 human judgement). The exact decision list is in the Stage 12.1 completion report and `gate-results.md`.

---

## Batch table: pa-search

*(Classifications as found by the batch, before the Stage 12.1 fixes above.)*


Analysis date 2026-10-03. Read-only. Repository: `/workspace/Author_Narratiq`.

**Scope.** Release-blocking (D-6: Critical and High) rows of `docs/testing/stage-09-qa-rerun-results.md`, lines 152–165 and 219–227. **Plot Assistant: 14** (PA-C1…C9, PA-H10…H14). **Search: 9** (SEARCH-1…9). These match `docs/issues-and-bugs/triage-register.md` L31/L36 (14 / 9). PA-M15, PA-M16 and SEARCH-10…14 are Post-launch and out of scope.

**Severity.** No severity was changed. SEARCH-4 keeps its register label "High/Critical"; the Tranche 2 A9 record calls it High, but the owner decision was never recorded.

## Tests re-run for this reconciliation (isolated `narratiq_test`, 2026-10-03)

| File | Result |
|---|---|
| `backend/tests/test_search_module.py` | 65 passed |
| `backend/tests/test_search_replace_routes.py` | 6 passed |
| `backend/tests/test_semantic_dedup.py` | 5 passed |
| `backend/tests/test_semantic_search_stability.py` | 2 passed (real BGE-M3 + pgvector) |
| `backend/tests/test_plot_assistant_retrieval_t2a.py` | 31 passed |
| `backend/tests/test_plot_assistant_intel_scope.py` | 12 passed |
| `backend/tests/test_retrieval_scope.py` | 3 passed (real BGE-M3 + pgvector) |
| `backend/tests/test_plot_importance_ranking.py` | 5 passed |
| `backend/tests/test_alias_resolution.py` | 8 passed |
| `backend/tests/test_story_intel_provenance.py` | 6 passed |
| `backend/tests/test_stage9_targeted_issues.py` (`SKIP_LLM_TESTS=1`) | 2 passed, 6 skipped (the live PA-H10 ×3 and PA-C7 ×3) |

**Not re-run here:**
- Tests that call the live model: the PA-C7 and PA-H10 cases, and `test_retrieval_vs_knowledge_failure.py`. The brief did not allow live-model runs.
- Frontend Playwright specs.

For those I rely on recorded runs:
- 2026-09-27: the PA-C7 and PA-H10 live tests 3/3 each (`stage-09-qa-rerun-results.md` L77, L80).
- 2026-10-03 final isolated runs (checklist L112, L2796): backend 1,142 passed / 0 failed / 1 known xfail, with no skips recorded, so the live-LLM tests ran; retrieval 147/147; studio 104 (+3 skipped); live browser 69/0/0.
- No per-test log of the 2026-10-03 run is stored in the repository.

**Renamed tests.** Several test names cited in the Sept-27 matrix no longer exist; Tranche 2 A9 rewrote `test_search_module.py`. Examples: `test_match_count_reflects_actual_occurrences_not_estimate`, `test_highlight_spans_agree_with_reported_matches`, `test_replace_only_touches_the_named_occurrence`, `test_relevance_does_not_silently_drop_a_long_multiword_query`, `test_identical_query_returns_identical_results_across_repeated_runs`. The current equivalents are cited below.

## Per-issue matrix

| ID | Severity | Sept-27 status | CURRENT state | Evidence (test or doc, with path) | Justification |
|---|---|---|---|---|---|
| PA-C1 | Critical | Live-pod manual | **HUMAN_JUDGEMENT** | `backend/tests/test_plot_assistant_intel_scope.py::test_router_passes_the_scope_cap_to_story_intelligence` (scope_used echoed), `::test_chapter_scope_without_a_chapter_is_refused_before_any_retrieval` (D-1 null-chapter guard), `::test_full_scope_without_a_chapter_still_works`; `test_plot_assistant_retrieval_t2a.py::test_planted_future_secret_never_reaches_a_chapter_scoped_prompt[full]`; `test_retrieval_scope.py::test_full_scope_includes_later_chapter_chunks`; UI toggle and badge in `frontend/components/plot-assistant/PlotAssistantPanel.tsx:46,133-160,199-214` | Under D-1 option (b), Chapter-1-only answers from Chapter 1 are by design. The backend full-scope path is tested through the router. **Not tested:** the 4.1 manual check "whole-story question from Ch 1" (checklist L1384), which is still unticked, and the toggle/badge, which has no frontend test. Needs UAT Q2(4) (`docs/testing/stage-09-uat-guide.md:55-61`). |
| PA-C2 | Critical | PASS — automated | **FIXED_VERIFIED** | `backend/tests/test_retrieval_scope.py::test_full_scope_includes_later_chapter_chunks`; `test_plot_assistant_retrieval_t2a.py::test_quota_spreads_when_other_chapters_are_near_equal`, `::test_quota_never_starves_a_single_chapter_answer`; live recall 1.0 at caps 3/6/full in `backend/tests/fixtures/plot_retrieval_t2a.json` | Full-scope retrieval reaches later chapters, with real BGE-M3 and pgvector (re-run green). **Caveat:** the fixture is small, so its recall is saturated; the long-manuscript follow-up (checklist L3411) is open. |
| PA-C3 | Critical | PASS — automated | **FIXED_VERIFIED** | `backend/tests/test_retrieval_scope.py::test_character_context_story_evidence_respects_chapter_cap` (full scope surfaces the chapter-3 evidence); `test_plot_assistant_retrieval_t2a.py::test_mentions_are_sampled_across_the_whole_book`, `::test_short_books_still_get_two_mentions_per_chapter` | Later-chapter character evidence is retrieved. A13 removed the "mentions from chapters 1–5 only" sampling. Re-run green. |
| PA-C4 | Critical | PASS — alias retrieval automated; answer quality → UAT | **FIXED_VERIFIED** (retrieval) | `backend/tests/test_stage9_targeted_issues.py::test_PA_C4_CAST_C3_alias_in_question_retrieves_that_character`; `test_plot_assistant_retrieval_t2a.py::test_detector_finds_named_characters` (title, alias, possessive, part of a name), `::test_detector_avoids_substring_and_function_word_errors`; `test_alias_resolution.py` (8) | An alias-only question puts that character first; the QA path's name detector now resolves aliases (`routers/plot_assistant.py:150-151`). Re-run green. Aliases must already be stored; cast extraction unions them (`services/ai_service.py:1772-1796`). Answer prose is still UAT Q2. |
| PA-C5 | Critical | PASS — automated | **FIXED_VERIFIED** | `backend/tests/test_retrieval_scope.py::test_full_scope_includes_later_chapter_chunks`, `::test_capped_scope_excludes_later_chapter_chunks`; `test_plot_assistant_retrieval_t2a.py::test_a_clear_semantic_gap_is_never_overturned`; `backend/tests/fixtures/plot_retrieval_t2a.json` (expected chapter hit in every case) | Later-chapter questions retrieve the later chapter at full scope. Importance can no longer pull an earlier chapter above a clearly better match. Same small-fixture caveat as PA-C2. |
| PA-C6 | Critical | Live-pod manual | **HUMAN_JUDGEMENT** | `backend/tests/test_plot_assistant_retrieval_t2a.py::test_near_tie_is_broken_toward_the_eventful_chapter`, `::test_a_clear_semantic_gap_is_never_overturned`, `::test_equal_cosine_orders_strictly_by_event_count_and_is_stable`, `::test_old_cap_saturation_no_longer_ties_busy_chapters`; `test_plot_importance_ranking.py` (5) | The ranking rules are verified deterministically: cosine first, importance only breaks near-ties. Nothing shows that a keyword-heavy incidental passage loses to the plot-critical one on a real manuscript. The A13 long-manuscript measurement (checklist L3411) is an open box. Owner/UAT decision needed. |
| PA-C7 | Critical | PASS — automated (3/3 live) | **FIXED_VERIFIED** | `backend/tests/test_stage9_targeted_issues.py::test_PA_C7_fact_in_the_story_is_not_reported_missing` (end-to-end `POST /api/plot-assistant/`, live Qwen, ×3). Recorded 3/3 in `docs/testing/stage-09-qa-rerun-results.md:80`; inside the 1,142/0 backend run (checklist L2796, 2026-10-03) | An answer-level test of the reported behaviour, through the real router. **Caveats:** only one fact and one fixture; full scope only. Live re-run not performed here. |
| PA-C8 | Critical | PASS — automated | **FIXED_VERIFIED** | `backend/tests/test_retrieval_vs_knowledge_failure.py::test_scope_limited_negative_answer_avoids_confident_story_claim` (live Qwen); `routers/plot_assistant.py:222,255,348` (`scope_limited` flag); UI banner at `PlotAssistantPanel.tsx:245-248` | When scope-limited, the model hedges instead of saying "not in your story" (answer-level, live; in the 2026-10-03 run). The UI amber banner has no frontend test (minor). |
| PA-C9 | Critical | Live-pod manual | **HUMAN_JUDGEMENT** | `backend/tests/test_plot_assistant_intel_scope.py::test_full_scope_still_returns_everything`; `test_plot_assistant_retrieval_t2a.py::test_planted_future_secret_never_reaches_a_chapter_scoped_prompt[full-*]`, `::test_mentions_are_sampled_across_the_whole_book`; `test_story_intel_provenance.py` (6) | Story-wide character evidence and Story Intelligence reach full-scope prompts (A13 and provenance). "Unified understanding of characters" is answer quality and needs UAT Q2. The owning task 4.9 is still open on the not-applicable relationship-extraction item (checklist L1512). |
| PA-H10 | High | PASS — automated (3/3 live) | **HUMAN_JUDGEMENT** | `backend/tests/test_stage9_targeted_issues.py::test_PA_H10_revelation_reaches_the_stored_summary` (live, stored `ChapterSummary` only; `stage-09-qa-rerun-results.md:77`) | The report (`docs/issues-and-bugs/open/phase-1-ai-writing-tools-qa-issues.docx`, PA High 10) is about multi-chapter summaries **produced by the assistant**. The test proves only that the stored per-chapter summary keeps the revelation. **Gap:** a Q&A-intent "summarise the story" never receives ChapterSummary rows: `answer_story_question` takes only passages + Story Intelligence (`routers/plot_assistant.py:213-226`, `services/ai_service.py:2406-2416`). No test covers assistant summary output. Needs UAT, or a live answer-level test. |
| PA-H11 | High | Live-pod manual | **HUMAN_JUDGEMENT** | `backend/tests/test_plot_assistant_retrieval_t2a.py::test_quota_spreads_when_other_chapters_are_near_equal`, `::test_mentions_are_sampled_across_the_whole_book`; `test_retrieval_scope.py::test_full_scope_includes_later_chapter_chunks` | The A13 chapter quota (QA, full scope, >5 chapters; `services/ai_service.py` `retrieve_chunks_from_store`, `diversify_chapters`) spreads evidence. Whether summaries actually balance later chapters is not asserted. The long-manuscript follow-up L3411 is open. Same structural note as PA-H10. |
| PA-H12 | High | Live-pod manual | **HUMAN_JUDGEMENT** | `backend/tests/test_plot_assistant_retrieval_t2a.py` (near-tie tests, as for PA-C6); `test_plot_importance_ranking.py` | Rule-level only (importance breaks near-ties). Whether the assistant separates minor events from major revelations is answer quality, and the real-manuscript measurement is open (L3411). |
| PA-H13 | High | Author judgement required | **HUMAN_JUDGEMENT** | `backend/tests/test_chapter_arc_fields.py::test_arc_notes_parsed_when_present`, `::test_resummarize_real_chapter_persists_well_typed_new_columns`; `test_plot_assistant_intel_scope.py::test_full_scope_still_returns_everything` | Arc data is captured and Story Intelligence (character arcs) reaches full-scope prompts. Arc-aware answers are subjective, so UAT Q2. 4.9 is open (L1512). |
| PA-H14 | High | Author judgement required | **HUMAN_JUDGEMENT** | No answer-level test. Supporting: `backend/tests/test_plot_assistant_retrieval_t2a.py::test_qa_prompt_always_fits_the_model_window`, `::test_intel_block_is_capped` (Story Intelligence now in Q&A, A13) | "Limited understanding of narrative significance" is purely judgement; UAT 9.6 is still open (checklist L2871). |
| SEARCH-1 | Critical | PASS — automated | **OPEN_TECHNICAL** (likely; reproduction not executed) | Backend green: `backend/tests/test_search_module.py::test_query_is_not_truncated_to_single_character`, `::test_multiword_query_matches_full_phrase_not_first_char`, `::test_long_multiword_query_is_not_dropped`. Frontend: `frontend/tests/studio/search-consistency.spec.ts` and `frontend/tests/browser/search-replace.spec.ts` set the query with a single `fill()`. **Defect:** `frontend/components/search/SearchPanel.tsx:120-163,166-175` | The backend matcher is correct, and 4.10 never found the original cause ("did not reproduce", L1531). The search panel fires a debounced request for every typing pause (250 ms exact, 600 ms semantic) and applies **every** response with no sequence or abort guard. A slow response for a prefix ("D") can overwrite the later full-term ("Devika") results. The editor highlights are then applied with the stale prefix (`write/page.tsx:95-99`). That is the reported symptom: a term reduced to part of the query. No test types incrementally. |
| SEARCH-2 | Critical | PASS — automated | **OPEN_TECHNICAL** (likely; same root cause as SEARCH-1) | Backend green: `backend/tests/test_search_module.py::test_multiword_query_matches_full_phrase_not_first_char`, `::test_known_term_occurrences_all_found_across_repeats`, `::test_shared_fixture_counts[*]`; frontend `search-match.spec.ts`. Defect location as SEARCH-1 | The full-term matcher is verified. A stale single-character response (the slowest, with the most matches and the largest payload) wins the race and shows "thousands" of single-character hits and highlights for a full term. This matches the report text ("Maren", "Son" work; others fall back to character-level). |
| SEARCH-3 | Critical | PASS — automated | **OPEN_TECHNICAL** (likely; same root cause) | `backend/tests/test_search_module.py::test_identical_query_returns_identical_results`, `::test_multiword_query_with_apostrophe_and_punctuation_neighbours`, `::test_special_character_queries_do_not_error`; `test_semantic_search_stability.py` (2). Defect location as SEARCH-1 | The backend is deterministic (re-run green). The UI result for the same term depends on typing rhythm and response order, so "some terms work, others are partially processed" is still reachable through the unguarded race. |
| SEARCH-4 | High/Critical | PASS — automated (backend only) | **FIXED_VERIFIED** | `backend/tests/test_search_module.py::test_shared_fixture_counts[*]`, `::test_count_equals_replace_all_and_markup_stays_valid[*]`, `::test_tags_are_never_counted_as_text`; `test_search_replace_routes.py::test_count_preview_and_replaced_agree`; `frontend/tests/studio/search-consistency.spec.ts` (19 cases: distinct highlights = count); live `frontend/tests/browser/search-replace.spec.ts` "count shown = highlights = Replace All preview" (4/4, Tranche 2; inside live browser 69/0/0 on 2026-10-03) | A9 unified the text model, and the displayed count is now tested in the browser. **Residual:** the SEARCH-1 race can still show a stale prefix's count. The SEARCH-4 severity decision (High vs Critical) is still unrecorded. |
| SEARCH-5 | High | Open — owning task not complete | **FIXED_VERIFIED** | `frontend/tests/studio/search-consistency.spec.ts` (A9 equivalence ×19); live `frontend/tests/browser/search-replace.spec.ts` (highlights across nested formatting, Replace One on the selected occurrence); `frontend/tests/search-match.spec.ts` (shared case table `backend/tests/fixtures/search_match_cases.json`); checklist 4.11 L1554-1561 now ticked | Highlight rendering is now audited and tested in Playwright, which was the Sept-27 gap. **Residual:** a stale-response highlight through the SEARCH-1 race. |
| SEARCH-6 | High | PASS — automated | **FIXED_VERIFIED** | `backend/tests/test_search_module.py::test_exact_mode_has_no_semantic_leakage_by_construction`, `::test_whole_word_excludes_partial_words`, `::test_replace_one_targets_exactly_the_nth_occurrence`, `::test_count_equals_replace_all_and_markup_stays_valid[*]`; `test_search_replace_routes.py::test_replace_one_changes_the_navigated_occurrence_and_keeps_a_version` | Exact mode is literal on the full query; whole word is opt-in and Unicode-aware. Re-run green. |
| SEARCH-7 | High | PASS — automated | **FIXED_VERIFIED** | `backend/tests/test_search_module.py::test_long_multiword_query_is_not_dropped`, `::test_whole_word_excludes_partial_words`, `::test_multiword_query_matches_full_phrase_not_first_char` | The report (report 1, High 7) says results come from partial matches instead of word-level matches. The backend matches the whole phrase and offers whole-word matching. Relevance was not otherwise measured (4.14 L1600). The SEARCH-1 race is a residual path to partial-match results. |
| SEARCH-8 | High | PASS — automated | **FIXED_VERIFIED** | `backend/tests/test_semantic_dedup.py::test_near_duplicate_overlap_is_dropped`, `::test_best_scoring_duplicate_is_the_one_kept`; route path `backend/routers/search.py:179-181` → `retrieve_chunks_from_store` → `_dedupe_chunks_by_content` (`services/ai_service.py`) | Content dedup sits on the only semantic-search path. **Caveat:** the tests are pure-function; no route test uses real overlapping chunks. Re-run green. |
| SEARCH-9 | High | PASS — automated | **FIXED_VERIFIED** | `backend/tests/test_semantic_dedup.py::test_near_duplicate_overlap_is_dropped`, `::test_respects_top_k_after_dedup`, `::test_distinct_passages_all_survive` | Same mechanism as SEARCH-8. Also applied before the A13 chapter quota (dedup then quota). |

## Summary counts (23 release-blocking: 14 PA + 9 SEARCH)

| CURRENT state | Critical | High | High/Critical (SEARCH-4) | Total |
|---|---|---|---|---|
| FIXED_VERIFIED | 6 (PA-C2, C3, C4, C5, C7, C8) | 5 (SEARCH-5, 6, 7, 8, 9) | 1 (SEARCH-4) | **12** |
| OPEN_TECHNICAL | 3 (SEARCH-1, 2, 3) | 0 | 0 | **3** |
| HUMAN_JUDGEMENT | 3 (PA-C1, C6, C9) | 5 (PA-H10, H11, H12, H13, H14) | 0 | **8** |
| ACCEPTED_LIMITATION | 0 | 0 | 0 | 0 |
| EXTERNAL_DEFERRED | 0 | 0 | 0 | 0 |
| NOT_APPLICABLE | 0 | 0 | 0 | 0 |
| **Total** | **12** | **10** | **1** | **23** |

By module:
- **Plot Assistant (14):** 6 FIXED_VERIFIED, 8 HUMAN_JUDGEMENT.
- **Search (9):** 6 FIXED_VERIFIED, 3 OPEN_TECHNICAL.

The CI wiring of the retrieval suite (4.15) is still externally deferred. It affects how regressions are guarded, not the state of any single issue.

## Remaining Critical/High needing owner decision

1. **PA-C1** (Critical): the owner confirms that D-1 option (b) with a visible toggle resolves "only uses Chapter 1". The manual check at 4.1 L1384 and UAT Q2(4) are outstanding.
2. **PA-C6** (Critical) and **PA-H12** (High): accept the rule-level evidence, or require the A13 long-manuscript ranking measurement (open box L3411) before closing.
3. **PA-C9** (Critical) and **PA-H13** (High): answer-quality judgement through UAT Q2. 4.9 is still open on the not-applicable relationship-extraction item (L1512), which needs the owner's explicit acceptance.
4. **PA-H10** and **PA-H11** (High): the stored-summary test does not exercise assistant-produced multi-chapter summaries. Decide between UAT, a live answer-level test, or a design change (see risk R-1 below).
5. **PA-H14** (High): judgement only; UAT 9.6 (L2871) is not started.
6. **SEARCH-4**: the severity label (High vs Critical) is still undecided. The fix itself is verified.
7. **SEARCH-1/2/3** (Critical): need a fix or a decision. See below.

## Open technical defects

### OD-1 (Critical: SEARCH-1, SEARCH-2, SEARCH-3; residual exposure for SEARCH-4/5/7): out-of-order search responses overwrite the current query's results

**Location:**
- `frontend/components/search/SearchPanel.tsx:166-175`: `handleQueryChange` debounces at 250 ms (exact) or 600 ms (semantic), and each pause launches a separate `runSearch(q)`.
- `SearchPanel.tsx:120-163`: `runSearch` awaits `beforeServerOp()` and then `searchApi.exact`. It then unconditionally calls `setExactResults`, `setTotalMatches`, `setGlobalIndex` and `onJumpToMatch(..., q, ...)`. There is no request id, no `AbortController`, and no check that `q` still equals the current `query`. The semantic branch (`setSemanticResults`) has the same problem.
- `frontend/app/(dashboard)/projects/[id]/write/page.tsx:95-99`: `handleJumpToMatch` passes the stale `q` to `applySearch`, so the editor highlights the prefix's matches.

**Why it is still present:**
- 4.10 checked only the backend and recorded "did not reproduce".
- A9 fixed the shared text model but did not add response ordering.
- Every UI test sets the query with a single `input.fill(...)`, so only one request is ever in flight.

**Reproduction idea:**
1. In a Playwright studio spec (mockApi), make `POST /api/search/exact/{id}` delay its response 1,500 ms when `query === 'D'` (returning, say, 400 matches) and answer 2 matches at once for `'Devika'`.
2. Run `input.pressSequentially('D')`, wait 300 ms, then `pressSequentially('evika')` and wait 2 s.
3. Expected: the panel shows 2 and the editor highlights "Devika".
4. With the current code: the panel shows 400 and the editor highlights single "D"s, while the input reads "Devika".

The same procedure with a slow semantic response reproduces it in semantic mode. On the live pod, a one-character query over a long manuscript is naturally the slowest and largest response, so no artificial delay is needed.

### Risk R-1 (not classified as a defect, since no failing behaviour has been demonstrated; affects PA-H10 and PA-H11): Q&A answers never see chapter summaries

**Location:** `routers/plot_assistant.py:213-226`; `services/ai_service.py:2406-2416`.

Q&A-intent answers, which is where "summarise the story" lands, get at most 10 paragraph passages plus Story Intelligence. They never get the ChapterSummary key events or arc notes that 4.5 and PA-H10 enriched. Only the creative and mixed paths receive summaries: `retrieve_relevant_chunks` top-6, plus `summary_list`, which is the **last 5** chapters (`order_by desc().limit(5)`, L88-92).

On a long manuscript, a story-level summary question may underrepresent chapters. This is unmeasured; it is the same gap as follow-up L3411.

**Reproduction idea:** on a 20+ chapter manuscript with a revelation in a middle chapter, ask (full scope) "Summarise the whole story so far", then check whether the revelation and late chapters appear.

## Batch table: awt

*(Classifications as found by the batch, before the Stage 12.1 fixes above.)*


Scope: `docs/testing/stage-09-qa-rerun-results.md`, matrix rows AWT-1…AWT-5 and AWT-A…AWT-J (L137–151), plus the "AWT per-issue sub-table (38 category issues)" (L252–295).

**How the count reconciles to 48:** the group rows AWT-1 to AWT-5 are not issues in their own right. They stand for 7 + 7 + 7 + 10 + 7 = **38 sub-issues**, and each sub-issue is listed separately below. The cross-module Criticals AWT-A to AWT-J add **10**, for a total of **48**. That matches `docs/issues-and-bugs/triage-register.md` L30 ("Phase 1 — AI Writing Tools | 48") and its share of the 114 release-blocking total.

**Severity, unchanged from the source:**
- AWT-A to AWT-J are Critical (10).
- AWT-1.x to AWT-4.x are High (31). This is the category severity; the docx has no per-issue severity.
- AWT-5.x (Translation) is "Medium (task priority)" but is still classified Release-blocking (7). The register flags this as a pending product-owner/0.6 decision, and it is kept as-is here.

**Checklist line numbers have moved since Sept 27.** The current lines in `docs/NarratIQ_Master_Implementation_Checklist.md` are:

| Task or item | Current line |
|---|---|
| 5.3 | L1731 |
| 5.4 | L1755 |
| 5.5 | L1777 (known limitation L1795) |
| 5.6 | L1797 |
| 5.7 | L1815; author review open at L1831 |
| 5.8 | L1834; both verification boxes now ticked with the Stage 9 MV-5.8-A numbers |
| 5.9 | L1854 |
| 5.10 | L1871; blind review open at L1889 |
| 5.11 | L1892; fluent-speaker review open at L1909 |
| 5.12 | L1913 |
| 5.16 | blind review open at L2018 and L2021 |
| Gate 3b | open at L2036 |
| Tranche 2 human items | L3407 (A15 Light thresholds), L3408 (children's rewrite meaning review) |

**Tests run for this reconciliation on 2026-10-03, against `narratiq_test`:**

| Test file | Result | Notes |
|---|---|---|
| `test_t2b_quality.py` | 62 passed | |
| `test_transform_preservation.py` | 27 passed | |
| `test_stage5_prompts_and_guard.py` | 36 passed | |
| `test_phase3_preservation.py` | 18 passed | |
| `test_ai_quality_invariants.py` | **12 passed**, 52 s | This file reached the live vLLM, which was up. Its fixture user and stories are deleted in teardown. It is the only non-deterministic file that was run. |

**Prompt-version note:** v4 is the current default (`test_stage5_prompts_and_guard.py::test_config_defaults_are_v4_with_v2_fallback`). v4 changes only the Style prompt (`test_t2b_quality.py::test_v4_changes_only_style`). Stage 9 live measurements of tone, emotion, age-adapt and translation under v3 therefore still describe the current prompts. Style measurements must come from the v4 runs.

## Per-issue table

Legend for CURRENT state: FIXED_VERIFIED, OPEN_TECHNICAL, HUMAN_JUDGEMENT, ACCEPTED_LIMITATION, EXTERNAL_DEFERRED, NOT_APPLICABLE.

| ID | sub-issue | severity | Sept-27 status | CURRENT state | evidence (test or doc, with path) | justification (one line) |
|---|---|---|---|---|---|---|
| AWT-A | Rewrite-first architecture | Critical | Author judgement required | HUMAN_JUDGEMENT | `backend/tests/test_ai_quality_invariants.py::test_locked_segment_is_byte_identical_after_transform` and `::test_already_suitable_passage_is_returned_unchanged` (both live, passed 2026-10-03); `test_phase3_preservation.py` (18 passed) | The preserve-first architecture (no-change gate, locks, strength) exists and is tested. Whether the product now "edits, not rewrites" is the blind review (L2018/L2036). See also the AWT-I open defect on Tone and Audience Light strength. |
| AWT-B | No author-voice preservation | Critical | Author judgement required | HUMAN_JUDGEMENT | `test_transform_preservation.py::test_run_constrained_transform_repairs_a_dropped_name_and_clears_the_violation` (names only); `backend/tests/fixtures/voice_convergence_stage9_20260927.json` | Voice has no automated metric; names are the only deterministic proxy; blind review at L2018 and Stage 7 task 7.12 are open. |
| AWT-C | No "no change required" layer | Critical | PASS (automated, 2026-09-27) | FIXED_VERIFIED | `test_ai_quality_invariants.py::test_already_suitable_passage_is_returned_unchanged[gothic-2, gothic-4, tech-3, adventure-3@ya]` (live, passed 2026-10-03); `test_t2b_quality.py::test_children_override_turns_already_suitable_into_the_normal_rewrite`; `test_stage5_prompts_and_guard.py::test_guard_retries_once_then_reports_no_change_honestly`; `backend/tests/fixtures/children_suitability_t2b_after_v4.json` | The layer exists and is live-verified. Its false positive (adventure-3, children) was fixed by A14 (8/10 → 0/10). Emotion and translation are excluded by the approved 5.5/5.8 design (L1786). |
| AWT-D | Over-transformation | Critical | Author judgement required | **OPEN_TECHNICAL** | `backend/tests/fixtures/strength_t2b_after_v4.json`: tone light median kept_share 0.568 vs strong 0.583, `light_below_strong_median` 0.525; age-adapt 0.524 vs 0.476; `count_check_flagged` 0/60 for tone. Checklist L3407 says "tone and age-adapt Light still overlap with Strong" (open). | Locks work, but the low-intervention default does not reduce how much Tone changes. The only enforcement (sentence count) never fires. Measured, not accepted. |
| AWT-E | Content injection | Critical | Author judgement required | HUMAN_JUDGEMENT | `test_t2b_quality.py::test_new_entity_check_flags_only_mid_sentence_inventions`, `::test_sentence_initial_invention_is_the_documented_blind_spot`; `backend/tests/fixtures/new_entities_t2b.json`; `frontend/tests/studio/stage12.spec.ts` "A16: a name the rewrite introduced is shown as a soft note…" | A16 added a warning-only check for invented names, which misses sentence-initial names. Invented imagery or plot has no check; that remains blind review. |
| AWT-F | Loss of literary subtlety | Critical | Author judgement required | HUMAN_JUDGEMENT | none (prompt-only); blind review L2018 | Inherently subjective. |
| AWT-G | Transformation consistency risk | Critical | Live-pod manual | **OPEN_TECHNICAL** | `backend/tests/fixtures/transform_golden_tranche2b_v4.json` (current default v4): mean stdev text 0.0743 (v1 baseline 0.0643; after_v2 0.0197; Stage 9 v3 0.0213); tech-4 style 2/3 unchanged and 1/3 rewritten; gothic-1 tone 0/3 unchanged here vs 3/3 in `transform_golden_stage9_20260927.json`, with an identical tone prompt and a no-change assessor at temperature 0.0 (`backend/services/ai_service.py:862`). Not recorded in the checklist or CHANGELOG. | The latest repo measurement under the shipping prompts shows run-to-run inconsistency at or worse than the pre-Stage-5 baseline, including no-change verdicts that flip. No pass/fail test guards this: `test_similarity_supporting_context_is_within_recorded_variance_band` only re-reads after_v2. |
| AWT-H | AI voice convergence | Critical | Author judgement required | HUMAN_JUDGEMENT | `backend/tests/fixtures/voice_convergence_stage9_20260927.json` (v3 tone prompt, identical in v4): text delta +0.0099, content delta −0.0076; harness `backend/tests/measure_voice_convergence.py` | Re-measured under the current tone prompt as flat (no convergence). The metric is one fixture pair at N=3 and is not "voice", so closure needs blind review. |
| AWT-I | Editing vs rewriting mismatch | Critical | Author judgement required | **OPEN_TECHNICAL** | `strength_t2b_after_v4.json`: style light 0.708 vs strong 0.576 (fixed for Style by A15, `test_t2b_quality.py::test_v4_style_light_drops_the_restructure_instruction_and_keeps_others`); tone light 0.568 vs strong 0.583, so Light is not lighter; age-adapt 0.524 vs 0.476. Checklist L3407 open. | "Adjust" and "rewrite" are still not distinct operations for Tone, and only marginally distinct for Audience. Style is fixed. |
| AWT-J | Preservation hierarchy missing | Critical | Author judgement required | HUMAN_JUDGEMENT | `test_transform_preservation.py::test_run_constrained_transform_repairs_a_dropped_name_and_clears_the_violation`, `::test_run_constrained_transform_reports_violation_when_retry_also_fails`, `::test_run_constrained_transform_no_retry_when_no_violation` (passed 2026-10-03); `backend/tests/fixtures/preservation_checks_measurement_t2b.json` (warn-only tense/POV/dialogue/timeline) | Enforced: names > strength > locks, plus warn-only checks. The docx's voice, style, genre, subtext and intent tiers are prompt-only, so judging them is human. |
| AWT-1.1 | Author voice preservation failure (tone) | High | Author judgement required | HUMAN_JUDGEMENT | `test_ai_quality_invariants.py::test_character_name_preservation_reports_no_violation` (live, passed) | Names only; voice needs the author review at L1831. |
| AWT-1.2 | Excessive content rewriting (tone) | High | Author judgement required | **OPEN_TECHNICAL** | `strength_t2b_after_v4.json` tone/light: median kept_share 0.568, so about 43% of the author's words are replaced at Light; it is indistinguishable from Strong (0.583); `count_check_flagged` 0/60. Proxy test `test_ai_quality_invariants.py::test_light_strength_does_not_trip_the_strength_violation_flag` passes only because it counts sentences. | Measured over-rewriting at the default Light. Open at L3407 and not accepted. |
| AWT-1.3 | Genre drift during tone changes | High | Author judgement required | HUMAN_JUDGEMENT | harness `backend/tests/measure_transform_golden_set.py`; `transform_golden_stage9_20260927.json` | Prompt-only; subjective. |
| AWT-1.4 | Narrative style replacement | High | Author judgement required | HUMAN_JUDGEMENT | same harness | Prompt-only; subjective. |
| AWT-1.5 | Metaphor/imagery injection | High | Author judgement required | HUMAN_JUDGEMENT | none for imagery (A16 covers names only: `test_t2b_quality.py::test_new_entity_check_flags_only_mid_sentence_inventions`) | No deterministic imagery check exists. |
| AWT-1.6 | Lack of transformation precision (tone) | High | Author judgement required | **OPEN_TECHNICAL** | same as 1.2 (`strength_t2b_after_v4.json` tone overlap; checklist L3407) | Light vs Strong Tone is not measurably more targeted. |
| AWT-1.7 | No preservation mode | High | Live-pod manual | FIXED_VERIFIED | `test_ai_quality_invariants.py::test_locked_segment_is_byte_identical_after_transform` (tone, live, passed 2026-10-03), `::test_already_suitable_passage_is_returned_unchanged` (live); `strength_t2b_after_v4.json` tone no_change 20/60 (the tone no-change gate fires live) | A preservation mode (locks, no-change gate, Light default) exists and is exercised live on the tone path. How light Light is belongs to 1.2/1.6. |
| AWT-2.1 | Emotional over-explanation | High | Open (owning task not complete) | HUMAN_JUDGEMENT | `backend/tests/fixtures/emotion_measurement_stage9_20260927.json` (MV-5.8-A run; 5.8 boxes now ticked, L1850–1851); `test_stage5_prompts_and_guard.py::test_emotion_harness_metrics_and_report_shape` | 5.8 is now complete; whether text over-explains is subjective. |
| AWT-2.2 | Subtext removal | High | Open (owning task not complete) | HUMAN_JUDGEMENT | same report | Subjective. |
| AWT-2.3 | Emotional nuance reduction | High | Open (owning task not complete) | HUMAN_JUDGEMENT | same report | Subjective. |
| AWT-2.4 | Emotion intensity inconsistency | High | Open (owning task not complete) | FIXED_VERIFIED | `emotion_measurement_stage9_20260927.json`: in 12/12 passage×emotion pairs, low intensity keeps more of the original than high (e.g. gothic-1/fear 0.786 vs 0.343); 0 unchanged outputs. The emotion prompt is unchanged in v4 (`test_t2b_quality.py::test_v4_changes_only_style`). | Intensity tracks the requested level monotonically in recorded live evidence. |
| AWT-2.5 | Weak emotion differentiation | High | Open (owning task not complete) | FIXED_VERIFIED | `emotion_measurement_stage9_20260927.json`: mean cross-emotion similarity 0.4985 (max 0.6365), against the ~0.85 failure line in `docs/testing/manual-verification/stage-05-manual-verification-guide.md` MV-5.8-A; checklist L1851 ticked | Measured clearly distinct against a pre-stated criterion. |
| AWT-2.6 | Generic emotional templates | High | Open (owning task not complete) | HUMAN_JUDGEMENT | same report: shared_phrase_rate 0.109 (no pre-stated threshold) | Metric exists but has no acceptance line; "generic" needs a reader. |
| AWT-2.7 | Authorial emotional style loss | High | Open (owning task not complete) | HUMAN_JUDGEMENT | same report | Subjective. |
| AWT-3.1 | Atmosphere preservation failure | High | Author judgement required | HUMAN_JUDGEMENT | harness `measure_transform_golden_set.py`; `transform_golden_tranche2b_v4.json` | Subjective. |
| AWT-3.2 | Emotional depth reduction | High | Author judgement required | HUMAN_JUDGEMENT | same; also `children_suitability_t2b_after_v4.json` (adventure-3 children rewrites keep a death term in only 1/10) | Subjective. The children's rewrite meaning review (L3408) is open. |
| AWT-3.3 | Character perspective drift | High | Author judgement required | HUMAN_JUDGEMENT | `test_phase3_preservation.py::test_pov_shift_detected` (passed); `preservation_checks_measurement_t2b.json`: POV recall 6/6 on broken rewrites, 0 POV flags on 27 fresh and 54 stored real outputs | Strong supporting evidence, but the check only warns and age drift is unmeasured. |
| AWT-3.4 | Rewriting already-suitable content | High | PASS (automated, 2026-09-27) | FIXED_VERIFIED | `test_ai_quality_invariants.py::test_already_suitable_passage_is_returned_unchanged[gothic-2, gothic-4, tech-3, adventure-3]` (live, passed 2026-10-03); `children_suitability_t2b_after_v4.json` suitable-* 10/10 unchanged | Re-verified live today. |
| AWT-3.5 | Literary quality regression | High | Author judgement required | HUMAN_JUDGEMENT | harness only | Subjective. |
| AWT-3.6 | Missing audience suitability detection | High | Author judgement required (known false positive) | FIXED_VERIFIED | `test_t2b_quality.py::test_children_override_turns_already_suitable_into_the_normal_rewrite`, `::test_children_terms_find_death_and_euphemism`, `::test_override_never_applies_to_ya_or_adult` (passed); `children_suitability_t2b_after_v4.json` (adventure-3 children no_change 0/10, was 8/10; euphemism-1 4/10 → 0/10); checklist A14 (L3400) | Detection exists in both directions, and the known false positive is fixed with a deterministic override plus live measurement. Rewrite meaning is a separate item (L3408). |
| AWT-3.7 | Lack of minimal-change mode (audience) | High | PASS (automated, 2026-09-27) | **OPEN_TECHNICAL** | No-change half is fixed (live test above). The Light half: `strength_t2b_after_v4.json` age_adapt light median kept 0.524 vs strong 0.476; 29% of Light runs fall below the Strong median; Light-only wording "measured, not adopted" (CHANGELOG Tranche 2b, Changed); checklist L3407 "age-adapt Light still overlap with Strong" | The Sept-27 PASS relied on a sentence-count proxy. Word-level measurement shows Light age adaptation replaces about half the words. Downgraded from PASS. |
| AWT-4.1 | Style via rewriting, not editing | High | Author judgement required | HUMAN_JUDGEMENT | `strength_t2b_after_v4.json` style light kept 0.708 (A15); `test_t2b_quality.py::test_v4_style_light_drops_the_restructure_instruction_and_keeps_others` | Improved and measured. The v3/v4 prompt removed the v2 brakes, so a blind re-judgement is needed (L1889). |
| AWT-4.2 | Unnecessary word/phrase replacement (style) | High | Author judgement required | HUMAN_JUDGEMENT | `strength_t2b_after_v4.json` style/light new_share median 0.29 | Whether about 29% new words at Light is "unnecessary" needs the A15 human labelling (L3407). |
| AWT-4.3 | No style strength control | High | PASS (automated, 2026-09-27) | FIXED_VERIFIED | `test_transform_preservation.py::test_build_strength_clause_known_levels_differ`, `::test_light_strength_flags_sentence_count_change`, `::test_strong_strength_never_flags_a_violation`; `test_t2b_quality.py::test_v4_style_light_drops_the_restructure_instruction_and_keeps_others`; `strength_t2b_after_v4.json` style light 0.708 vs strong 0.576 | The control exists, and for Style it now measurably changes the result (v3 was 0.597 vs 0.593). |
| AWT-4.4 | Genre trope exaggeration | High | Author judgement required | HUMAN_JUDGEMENT | `test_stage5_prompts_and_guard.py::test_style_v3_names_thriller_craft_levers_and_drops_the_v2_brakes` | Subjective; v3 removed the v2 anti-trope brake, so re-judge (L1889). |
| AWT-4.5 | Style stereotype dependency | High | Author judgement required | HUMAN_JUDGEMENT | same | Subjective. |
| AWT-4.6 | New content introduction (style) | High | Author judgement required | HUMAN_JUDGEMENT | A16 `test_t2b_quality.py::test_new_entity_check_flags_only_mid_sentence_inventions` (names only, warn) | Partial name check; new details or imagery are unchecked. |
| AWT-4.7 | Character voice modification | High | Author judgement required | HUMAN_JUDGEMENT | `test_phase3_preservation.py::test_dialogue_and_timeline_checks` (passed); `preservation_checks_measurement_t2b.json` dialogue_changed 0 | The check only warns; "voice" needs a reader. |
| AWT-4.8 | Style detection failure | High | Live-pod manual | HUMAN_JUDGEMENT | `test_stage5_prompts_and_guard.py::test_strong_style_skips_the_already_suitable_shortcut`, `::test_guard_retries_once_then_reports_no_change_honestly` (fake model); `strength_t2b_after_v4.json` style/light no_change 15/60 (gate fires live) | The style gate fires live, but no ground-truth "already in style" fixture exists, so correctness can only be judged by reading. Adding such a fixture is recommended. |
| AWT-4.9 | Literary style degradation | High | Author judgement required | HUMAN_JUDGEMENT | harness only | Subjective (L1889). |
| AWT-4.10 | Author identity erosion | High | Author judgement required | HUMAN_JUDGEMENT | harness only | Blind review L1889; 7.12 open. |
| AWT-5.1 | Interpretation instead of translation | Medium (task priority), release-blocking | Author judgement required | HUMAN_JUDGEMENT | none (translation is not in the golden set) | Fluent-speaker review L1909 open. |
| AWT-5.2 | Literary voice loss | Medium (task priority), release-blocking | Author judgement required | HUMAN_JUDGEMENT | none | Fluent-speaker review L1909. |
| AWT-5.3 | Imagery preservation | Medium (task priority), release-blocking | Author judgement required | HUMAN_JUDGEMENT | none | Fluent-speaker review L1909. |
| AWT-5.4 | Natural language quality inconsistency | Medium (task priority), release-blocking | Author judgement required | HUMAN_JUDGEMENT | none | Fluent-speaker review L1909. |
| AWT-5.5 | Contextual meaning drift | Medium (task priority), release-blocking | Author judgement required | HUMAN_JUDGEMENT | none | Fluent-speaker review L1909. |
| AWT-5.6 | Emotional nuance loss | Medium (task priority), release-blocking | Author judgement required | HUMAN_JUDGEMENT | none | Fluent-speaker review L1909. |
| AWT-5.7 | Cross-language consistency risk | Medium (task priority), release-blocking | Author judgement required | HUMAN_JUDGEMENT | `test_transform_preservation.py::test_translation_name_transliterated_per_glossary_is_not_a_violation`, `::test_translation_name_missing_entirely_is_flagged` (passed); live glossary check at checklist L1910 | Glossary name consistency is fixed. The docx's actual "architectural risk across language pairs" is untested, and the owner must accept the checklist's reinterpretation of it. |

## Summary counts (48)

| CURRENT state | Critical | High | Medium (task priority, still release-blocking) | Total |
|---|---|---|---|---|
| FIXED_VERIFIED | 1 (C) | 6 (1.7, 2.4, 2.5, 3.4, 3.6, 4.3) | 0 | 7 |
| OPEN_TECHNICAL | 3 (D, G, I) | 3 (1.2, 1.6, 3.7) | 0 | 6 |
| HUMAN_JUDGEMENT | 6 (A, B, E, F, H, J) | 22 | 7 (5.1–5.7) | 35 |
| ACCEPTED_LIMITATION | 0 | 0 | 0 | 0 |
| EXTERNAL_DEFERRED | 0 | 0 | 0 | 0 |
| NOT_APPLICABLE | 0 | 0 | 0 | 0 |
| **Total** | **10** | **31** | **7** | **48** |

The 22 High HUMAN_JUDGEMENT items are 1.1, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.6, 2.7, 3.1, 3.2, 3.3, 3.5, 4.1, 4.2, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9 and 4.10.

**Changes from Sept 27:**
- Moved to FIXED_VERIFIED:
  - 2.4 and 2.5: MV-5.8-A was run, and 5.8 is now complete.
  - 3.6: A14 fixed the false positive.
  - 1.7: the tone path is now evidenced live.
- Moved from PASS to OPEN_TECHNICAL:
  - 3.7: word-level measurement replaces the sentence-count proxy.
- Moved from author judgement or live-pod manual to OPEN_TECHNICAL:
  - D, I, 1.2 and 1.6: Tranche 2b's A15 measurements.
  - G: the Tranche 2b v4 golden run.
- No items were found accepted by the owner. The only AWT-adjacent owner acceptances, A17 and cast variability, are not AWT issues. The emotion/translation exclusion from the no-change layer is an approved design choice, noted under C.

## Remaining Critical/High items needing an owner decision (HUMAN_JUDGEMENT; none ACCEPTED, EXTERNAL or NOT_APPLICABLE)

Closure route: the Stage 5 blind author review (L2018/L2021), Gate 3b (L2036), the per-task author reviews (5.7 at L1831, 5.10 at L1889, 5.11 at L1909) and the Tranche 2 human items (L3407 A15 thresholds, L3408 children's rewrite meaning).

- **Critical (6):**
  - **AWT-A:** blind review, with automated support.
  - **AWT-B:** voice; blind review and 7.12.
  - **AWT-E:** A16 checks names only; imagery and plot need review. The owner could also commission an imagery/entity diff on the golden set.
  - **AWT-F:** subjective.
  - **AWT-H:** measured flat under the current tone prompt; needs blind confirmation.
  - **AWT-J:** the voice, style, subtext and intent tiers are prompt-only.
- **High (22):**
  - Tone 1.1, 1.3, 1.4, 1.5: author review at L1831.
  - Emotion 2.1, 2.2, 2.3, 2.6, 2.7: blind review.
  - Audience 3.1, 3.2, 3.3, 3.5: blind review plus L3408.
  - Style 4.1, 4.2, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10: L1889. These must be re-judged under the v3/v4 style prompt; 4.2 also depends on the L3407 labelling, and 4.8 would benefit from an "already in style" fixture.
- **Medium (task priority) but still release-blocking (7):** Translation 5.1–5.7. These need the fluent-speaker review (L1909). Two owner decisions are also pending:
  - whether Translation stays release-blocking at Medium priority (register note);
  - whether to accept checklist 5.11's reinterpretation of 5.7 as glossary consistency.

## Open technical defects

### OT-1: Light strength has no measurable effect for Tone, and only a marginal one for Audience adaptation (AWT-D Critical, AWT-I Critical, AWT-1.2 High, AWT-1.6 High, AWT-3.7 High)

- **Evidence:** `backend/tests/fixtures/strength_t2b_after_v4.json`, generated under the current default v4. Tone and age-adapt prompts are identical in v3 and v4.

  | Transform | Light kept_share median | Strong kept_share median | Light runs below Strong median |
  |---|---|---|---|
  | tone | 0.568 | 0.583 | 52.5% |
  | age-adapt | 0.524 | 0.476 | 29% |

  For comparison, Style moved to 0.708 vs 0.576 after A15. Light tone therefore replaces about 43% of the author's words, no less than Strong does.
- **Why it is still present:**
  - The Light instruction, `backend/services/transform_preservation.py:238-251` (`_STRENGTH_CLAUSES["light"]`), is not honoured by the 7B model for Tone or age adaptation. Light-only wording was tried in Tranche 2b and measured as having no effect, so it was not adopted (CHANGELOG, Tranche 2b → Changed).
  - The only enforcement, `check_strength_violation` (`transform_preservation.py:266-277`), counts sentences. It flagged 0 of 60 Tone Light runs, so the live test `test_light_strength_does_not_trip_the_strength_violation_flag` passes vacuously.
  - `strength_detail` (`backend/services/ai_service.py:976`, attached at :1135/:1218) is measured but drives no warning or retry, by design, pending the human labelling item at checklist L3407.
  - The item is explicitly open and not accepted: L3407 says "tone and age-adapt Light still overlap with Strong".
- **Reproduction:**
  1. `cd backend && PROMPT_VERSION=v4 python3 tests/measure_strength_t2b.py --label recheck --runs 5`.
  2. Compare `summary["tone/light"].kept_share.median` with `summary["tone/strong"].kept_share.median`. A fixed state would show Light clearly above Strong.
  3. For a quick check, POST `/api/ai/tone` on golden passage tech-1 five times each with `strength: "light"` and `strength: "strong"`, and compare `strength_detail.kept_share`.
- **Fix path:** this is blocked on the owner/human A15 labelling (L3407). After that, either an enforced retry or warning at a threshold, or a different Light mechanism such as constrained word-level editing.

### OT-2: Run-to-run inconsistency under the shipping prompts is at or above the pre-Stage-5 baseline, and is not recorded anywhere (AWT-G Critical)

- **Evidence:** `backend/tests/fixtures/transform_golden_tranche2b_v4.json`, the latest golden-set run (v4, N=3).
  - Mean stdev of text similarity:

    | Run | Mean stdev |
    |---|---|
    | v1 baseline | 0.0643 |
    | after_v2 | 0.0197 |
    | Stage 9 v3 | 0.0213 |
    | Tranche 2b v4 | **0.0743** (max 0.362) |

    Mean stdev of content similarity is 0.0223 (v2: 0.0051).
  - Concrete flips:
    - tech-4 style→cinematic is unchanged in 2 of 3 trials and rewritten in 1.
    - gothic-1 tone→suspenseful was unchanged 3/3 in the Stage 9 run but rewritten 0/3-unchanged here, although the tone prompt is identical (v4 changes only style). Its text similarity across the 3 trials ranges from 0.07 to 0.78.
  - The no-change assessor runs at temperature 0.0 (`backend/services/ai_service.py:862`), yet its verdict differs across identical inputs and runs.
  - The checklist 5.12-G claim ("~3× tighter", L1923) and Stage 9's "within noise" reflect older runs. Neither the checklist nor the CHANGELOG mentions the v4 numbers.
- **Why it is still present:** nothing guards consistency. `test_ai_quality_invariants.py::test_similarity_supporting_context_is_within_recorded_variance_band` only re-reads `transform_golden_after_v2.json` and generates nothing.
- **Caveats (confidence: medium):**
  - N=3 per scenario.
  - The `difflib.SequenceMatcher` text ratio is noisy on long strings (autojunk).
  - Part of the shift may come from the pod or model instance (fresh pod) rather than from code.
  - Even so, the no-change verdict flipping on identical input is a real behavioural inconsistency.
- **Reproduction:**
  1. `cd backend && python3 tests/measure_transform_golden_set.py --label recheck_a` and then `--label recheck_b` on the same pod (prefer N≥10 by raising `N_TRIALS`).
  2. Compare `consistency_summary` with after_v2, and compare `byte_identical_rate` for gothic-1 and tech-4 across the two runs.
  3. Or call `/api/ai/tone` (gothic-1, "suspenseful") ten times and count `no_change`.

## Notes

- No repository file was modified.
- Only `narratiq_test` was used. `test_ai_quality_invariants.py` reached the live vLLM; its fixture cleans up after itself.
- Translation severity is shown as in the source ("Medium (task priority)"), counted as release-blocking per the document, and not re-graded.

## Batch table: cast-audit-sug

*(Classifications as found by the batch, before the Stage 12.1 fixes above.)*


Analysis date: 2026-10-03. Read-only. Scope: Critical and High issues classified Release-blocking in `docs/testing/stage-09-qa-rerun-results.md` (per-issue matrix, lines 168–207).

Counts reconcile with `docs/issues-and-bugs/triage-register.md` lines 32–34:
- **Cast: 7.** C3, C4, H6–H10. C1, C2 and H5 are "Resolved (3.12)", so they are not release-blocking and are excluded.
- **Story Audit: 10.** C1–C5 and H6–H10.
- **Suggestions: 11.** C1, C2 and H3–H11.
- **Total: 28.** Severities are unchanged.

## Deterministic tests re-run today

All runs used `narratiq_test` with `SKIP_LLM_TESTS=1`. Live-model tests were skipped and not re-run.

| Test file | Result |
|---|---|
| `test_cast_t2a.py` | 15 passed |
| `test_character_duplicates.py` | 19 passed, 1 skipped (live BGE-M3 test) |
| `test_stage9_targeted_issues.py` | 2 passed, 6 skipped (live) |
| `test_t2b_quality.py` | 62 passed |
| `test_timeline_flash_text.py` | 7 passed |
| `test_suggestions_priority.py` | 11 passed |
| `test_stage5_signals.py` | 28 passed |
| `test_continuity_citation_validation.py` | 15 passed |
| `test_manuscript_report_citations.py` | 16 passed |
| `test_stage5_persistence.py` | 20 passed |
| `test_character_hint_sync.py` | 17 passed |
| `test_character_merge.py` | 4 passed |
| `test_plot_importance_ranking.py` | 5 passed |

Nothing failed.

## Per-issue table

| ID | Severity | Sept-27 status | CURRENT state | Evidence (path) | Justification (one line) |
|---|---|---|---|---|---|
| CAST-C3 | Critical | PASS — alias retrieval, automated; answer quality → UAT Q2 (gap: no extraction-time alias detection) | FIXED_VERIFIED | `backend/tests/test_stage9_targeted_issues.py::test_PA_C4_CAST_C3_alias_in_question_retrieves_that_character` (passed today); `backend/tests/test_character_hint_sync.py::test_alias_match_dismisses_the_hint`; extraction-time: `backend/tests/test_cast_t2a.py::test_alias_evidence_and_titles_still_merge`, `::test_shared_first_name_is_never_merged_by_subset`; `backend/tests/test_character_duplicates.py::test_flags_plausible_duplicates` | The Sept-27 gap (title/first-name variants not merged at extraction) is now covered by A11 cast merge tests and A7 duplicate flagging ("Captain Mara" vs "Mara Coste"). |
| CAST-C4 | Critical | No evidence found (detection not built) | FIXED_VERIFIED | A7. `backend/services/character_duplicates.py`; `backend/tests/test_character_duplicates.py` (19 passed today: `::test_cast_generation_flags_possible_duplicate`, `::test_merge_still_requires_the_author_and_works_on_a_candidate`, …); `test_character_merge.py::test_full_merge_end_to_end`. Checklist 4.8 (detect item, owner decision "detect → suggest → author-confirmed merge closes CAST-C4") | Detection, suggestion and confirmed merge exist and are tested; the owner recorded that this design closes C4. |
| CAST-H6 | High | PASS — automated (live, 4-character fixture) | **OPEN_TECHNICAL** | `docs/testing/stage-12/tranche3/cast-variability-probe.json`: raw model role for **Corvin Ashe = "antagonist" in 11/25 runs** (ground truth "supporting", per `backend/scripts/quality/cast_variability_probe.py:22` and `backend/tests/test_cast_classification_accuracy.py:44-49`). The guard `test_cast_classification_accuracy.py:84` asserts `accuracy >= 0.75`, so one wrong role in four still passes. | Role misclassification is in current recorded live evidence at 44% for one character. Nothing records or accepts it: the owner's 2026-10-03 acceptance covers presence only. The test threshold hides it. |
| CAST-H7 | High | Live-pod manual (order not asserted) | FIXED_VERIFIED | A12. `backend/routers/characters.py:37` (`_ROLE_ORDER`), `:310`, `:472`; `backend/tests/test_cast_t2a.py::test_generate_cast_presence_duplicates_counts_and_order`, `::test_saved_characters_stay_alphabetical_unless_importance_is_chosen` (passed today); `test_cast_classification_accuracy.py::test_extract_cast_does_not_over_promote_minor_unnamed_mentions` (live) | The importance order is now deterministic and asserted. Caveat: the order consumes the model's role, so the H6 error ranks Corvin above Hessa in 11/25 runs. |
| CAST-H8 | High | Open — owning task not complete (4.9 relationship-extraction item N/A; docx is about descriptions misstating relationships) | HUMAN_JUDGEMENT | Checklist 4.9 (L1512, L1522 unticked "NOT APPLICABLE", note L1528) and Stage 4 gate L1666/L1671 (open, awaiting the owner's acceptance). Partial technical remedy: A11 kinship grounding, `backend/tests/test_cast_t2a.py::test_misattributed_kinship_is_dropped_and_grounded_kinship_kept`; `backend/tests/fixtures/cast_consistency_after.json` (split relationship 0 → 1.0) | The not-applicable claim is not accepted by the owner. The description-relationship errors the docx reports are only partly addressed (kinship only), so the owner must decide whether N/A plus A11 closes H8. |
| CAST-H9 | High | No evidence found | FIXED_VERIFIED | A11. Checklist 4.9 L1523; `backend/tests/test_cast_t2a.py::test_description_and_evidence_come_from_the_earliest_window`, `::test_union_fields_combine_windows_without_repeating`, `::test_cut_off_json_keeps_complete_characters_only` (passed today); live `backend/tests/measure_cast_consistency.py` → `backend/tests/fixtures/cast_consistency_before.json` / `_after.json` (fact recall 0.64 → 0.907, stability 0.874) | Measured and fixed. The residual (model-made merges flagged, not merged) is recorded as owner-accepted in 4.9 L1523. |
| CAST-H10 | High | Live-pod manual (no classification test) | ACCEPTED_LIMITATION | A10 + migration `0027`. `backend/tests/test_cast_t2a.py::test_presence_on_page_wins_and_invalid_defaults_to_on_page`, `::test_confirm_persists_presence_and_it_can_be_edited`; `docs/testing/stage-12/tranche3/cast-variability-probe.json` (21/25; the 4 failures are on-page antagonist labelled `historical`); checklist Tranche 3 "Cast live variability investigated" + Tranche 2 follow-up | The mechanism is built and tested. The reported behaviour still occurs in 4/25 live runs; the owner accepted it as model variability on 2026-10-03. |
| AUDIT-C1 | Critical | Open — owning task not complete (memory/past-reference FPs not tested) | HUMAN_JUDGEMENT | `backend/tests/test_continuity_citation_validation.py` (15 passed today); `backend/tests/test_timeline_flash_text.py` (7 passed); `test_stage5_signals.py::test_flashback_cue_suppresses_the_reversal`; live `docs/testing/stage-12/tranche3/mv-5.14-a.json` (flashback 0/3) | Citation validation only *flags* real-chapter ungrounded claims (`::test_real_chapter_ungrounded_claim_is_flagged_not_suppressed`). Memory/past-reference false positives are still untested, so residual FP acceptability is the author's call (Stage 5 gate "All 15 Story Audit issues" L98 open). |
| AUDIT-C2 | Critical | Open — owning task not complete | HUMAN_JUDGEMENT | `test_stage5_signals.py::test_forward_moving_timeline_has_no_candidates`; `test_timeline_flash_text.py::test_mv514a_story_b_flashback_is_suppressed_and_story_a_still_reported`; `docs/testing/stage-12/tranche3/mv-5.14-a-before-fix.json` → `mv-5.14-a.json` (marked flashback 3/3 → 0/3); harness `backend/tests/measure_continuity_depth.py` | The measured FP (flashback) is fixed and tested. The LLM's own findings with real citations can still be false and are only flagged; acceptance sits with the author and Stage 5 gate L98. |
| AUDIT-C3 | Critical | Open — owning task not complete | HUMAN_JUDGEMENT | 5.14 item 2 (ticked); `backend/tests/measure_continuity_depth.py` + `backend/tests/fixtures/continuity_depth_report.json`, `continuity_depth_report_stage9_20260927.json` (harness, not pass/fail) | Depth of contradiction reasoning is prompt-level and measured only by a live harness. Closure is a quality judgement. |
| AUDIT-C4 | Critical | Open — owning task not complete (MV-5.14-A + D pending) | HUMAN_JUDGEMENT | `backend/services/timeline_signals.py`; `test_stage5_signals.py::test_date_reversal_is_detected_and_cites_both_chapters`, `::test_planted_fixture_full_recall_and_zero_false_on_the_control`; `test_timeline_flash_text.py`; live `docs/testing/stage-12/tranche3/mv-5.14-a.json` (reversal 3/3, flashback 0/3, pass) | MV-5.14-A passed after the A20 fix. The sub-item stays unticked pending the author's MV-5.14-D (checklist 5.14 timeline item; L2069). |
| AUDIT-C5 | Critical | Open — owning task not complete (MV-5.14-B + D pending) | HUMAN_JUDGEMENT | `backend/services/narrative_signals.py`; `test_stage5_signals.py::test_dead_end_thread_becomes_a_setup_signal`, `::test_character_disappearance_uses_the_dead_end_threshold`; live `docs/testing/stage-12/tranche3/mv-5.14-b.json` + `mv-5.14-b-section.png` (pass) | MV-5.14-B passed. Closure is the author's MV-5.14-D. |
| AUDIT-H6 | High | Open — owning task not complete ("would be PASS once 5.14 closes") | HUMAN_JUDGEMENT | `backend/tests/test_continuity_citation_validation.py` (15 passed); `backend/tests/test_manuscript_report_citations.py::test_mixed_report_false_positive_and_false_negative_count` (16 passed) | Fabricated-citation suppression is verified. Ungrounded real-chapter claims are deliberately shown (flagged), so whether the residual FP risk is acceptable needs author review (Stage 5 gate L98/L103). |
| AUDIT-H7 | High | Author judgement required | HUMAN_JUDGEMENT | `test_continuity_citation_validation.py::test_citation_groundedness_recognizes_arc_note_claims`; `test_manuscript_report_citations.py::test_character_arc_with_real_chapters_is_kept_and_unchanged_otherwise`; UI renders arcs (`frontend/components/plot-holes/ManuscriptReportPanel.tsx:261`) | Arc data is wired, cited and displayed. Whether the analysis is deep enough is subjective. |
| AUDIT-H8 | High | Open — owning task not complete (`deterministic_open_threads` not asserted) | **OPEN_TECHNICAL** | Backend computes it at `backend/services/ai_service.py:3426`/`:3449` and returns it at `backend/routers/manuscript_report.py:299`, `backend/schemas.py:303`. The **frontend never renders it**: absent from `frontend/lib/types.ts:150-166` (`ManuscriptReport`) and from `ManuscriptReportPanel.tsx`. The only test reference is a fixture dict (`backend/tests/test_stage5_persistence.py:53`); no assertion. | The 5.14 remedy ("an author can compare the two") does not reach the author, and no test asserts the cross-reference. (Dead-end threads do reach the UI via `narrative_signals`.) |
| AUDIT-H9 | High | Open — owning task not complete (citation-only test) | **OPEN_TECHNICAL** | `stakes` is generated (`ai_service.py:3306`), returned (`routers/manuscript_report.py:296`, `schemas.py:291`) and saved, but **not in `frontend/lib/types.ts` `ManuscriptReport` and not rendered in `ManuscriptReportPanel.tsx`** (the panel renders arcs, pacing, threads, strengths, improvements, relationships and signals at L261–417; no stakes). Only test: `test_manuscript_report_citations.py::test_stakes_escalation_point_with_fabricated_chapter_is_dropped_but_stakes_survives` | The "story stakes analysis" exists only in the API payload. An author using the product cannot see it, so the reported "stakes analysis missing" persists in the UI. |
| AUDIT-H10 | High | Open — owning task not complete (`chapter_plot_importance` not asserted) | **OPEN_TECHNICAL** | Computed at `ai_service.py:3425-3440`, returned at `routers/manuscript_report.py:298`, `schemas.py:297`. **Not rendered by the frontend** (no reference in `frontend/` outside node_modules). `backend/tests/test_plot_importance_ranking.py` tests only the retrieval helper; `chapter_plot_importance` is never asserted. | Checklist 5.14 claims it was "surfaced somewhere an author can see it for the first time". It is not displayed anywhere, and the report field is untested. |
| SUG-C1 | Critical | Author judgement required | HUMAN_JUDGEMENT | A17. `backend/tests/test_t2b_quality.py::test_praise_only_and_empty_recommendations_are_dropped`, `::test_real_advice_with_praise_words_is_kept` (passed today); `backend/tests/fixtures/suggestions_quality_t2b.json` (praise_in_observation 0, recall 0.933); 5.13 "Author review" L25 unticked | Praise-only items are now filtered deterministically. Whether output "reads as a developmental editor, not praise" (5.13 DoD) is the open author review. |
| SUG-C2 | Critical | Author judgement required | HUMAN_JUDGEMENT | `test_t2b_quality.py::test_praise_only_and_empty_recommendations_are_dropped` (empty recommendations dropped), `::test_all_filtered_retries_once_then_reports_honestly`; `test_ai_quality_invariants.py::test_suggestions_response_has_valid_structured_fields` (live) | Structure and non-empty recommendations are enforced. Actionability is subjective (5.13 author review open). |
| SUG-H3 | High | Author judgement required | HUMAN_JUDGEMENT | `backend/tests/measure_suggestions_t2b.py` → `fixtures/suggestions_quality_t2b.json` (recall current 0.80 → shipped 0.933; keyword proxy, owner-accepted measurement limitation per Tranche 2 A17) | Measured by a keyword-proxy harness, not a pass/fail test. The author confirms real weaknesses. |
| SUG-H4 | High | Author judgement required | HUMAN_JUDGEMENT | `fixtures/suggestions_quality_t2b.json` (praise_in_observation_items 0 in all variants); A17 hygiene tests | No measured positive bias, but bias is a judgement call (5.13 author review open). |
| SUG-H5 | High | Author judgement required | HUMAN_JUDGEMENT | Prompt only (`services/prompt_registry.py` suggestions v2+); no test | Genericness is subjective; no automated measure. |
| SUG-H6 | High | Author judgement required (no cross-run measurement) | HUMAN_JUDGEMENT | A17. `test_t2b_quality.py::test_in_response_duplicates_keep_the_higher_priority_item` (passed); `suggestions_quality_t2b.json` dup_pairs 0 | In-response repetition is fixed and tested. Cross-run repetition is still unmeasured, so judgement remains. |
| SUG-H7 | High | Author judgement required | HUMAN_JUDGEMENT | `suggestions_quality_t2b.json` (distinct categories 11, shipped variant) | Harness metric only. Variability is subjective. |
| SUG-H8 | High | Author judgement required | HUMAN_JUDGEMENT | Same harness (distinct categories 9 → 11 across variants); prompt "own words" instruction | No pass/fail test. Judgement. |
| SUG-H9 | High | PASS — wiring, automated; quality → UAT | FIXED_VERIFIED | `backend/tests/test_stage9_targeted_issues.py::test_SUG_H9_suggestions_receive_story_passages_and_genre` (passed today: asserts the retrieved story passage and genre reach `generate_suggestions`) | The technical root cause (no story context or genre passed) is fixed and tested. Overall suggestion quality remains part of the shared 5.13 author review. |
| SUG-H10 | High | Author judgement required (prompt-only) | HUMAN_JUDGEMENT | Prompt names "Narrative Risk" category (5.13 L17); no test | Prompt-only. Judgement. |
| SUG-H11 | High | Author judgement required | HUMAN_JUDGEMENT | `backend/tests/measure_suggestions_quality.py` info-dump golden case (`fixtures/suggestions_golden_set.py`); sharpening pass re-enabled (A17), `test_t2b_quality.py::test_v1_suggestions_stay_byte_identical`, `test_suggestions_priority.py` adversarial fail-open tests | Developmental depth is measured only by a harness. Judgement. |

## Summary counts

| CURRENT state | Critical | High | Total |
|---|---|---|---|
| FIXED_VERIFIED | 2 (CAST-C3, CAST-C4) | 3 (CAST-H7, CAST-H9, SUG-H9) | 5 |
| OPEN_TECHNICAL | 0 | 4 (CAST-H6, AUDIT-H8, AUDIT-H9, AUDIT-H10) | 4 |
| HUMAN_JUDGEMENT | 7 (AUDIT-C1–C5, SUG-C1, SUG-C2) | 11 (CAST-H8, AUDIT-H6, AUDIT-H7, SUG-H3–H8, SUG-H10, SUG-H11) | 18 |
| ACCEPTED_LIMITATION | 0 | 1 (CAST-H10) | 1 |
| EXTERNAL_DEFERRED | 0 | 0 | 0 |
| NOT_APPLICABLE | 0 | 0 | 0 |
| **Total** | **9** | **19** | **28** |

By category: Cast 7 (FV 4, OT 1, HJ 1, AL 1); Story Audit 10 (OT 3, HJ 7); Suggestions 11 (FV 1, HJ 10).

## Remaining Critical/High issues needing an owner decision

1. **MV-5.14-D (author).** Covers AUDIT-C4 (timeline) and AUDIT-C5 (narrative), and also Medium AUDIT-M11. MV-5.14-A, B and C all passed live (`docs/testing/stage-12/tranche3/mv-5.14-*.json`). The decision is the author's (checklist L2069, Tranche 3 A20).
2. **5.13 author review / Gate 3b (author UAT).** Covers SUG-C1, SUG-C2, SUG-H3, SUG-H4, SUG-H5, SUG-H6 (cross-run), SUG-H7, SUG-H8, SUG-H10 and SUG-H11 (checklist 5.13 "Author review" unticked; Stage 5 gate L103/L106).
3. **Stage 5 gate "All 15 Story Audit issues closed or accepted" (author).** Covers AUDIT-C1, AUDIT-C2, AUDIT-C3, AUDIT-H6 and AUDIT-H7. The residual FP risk from flagged-but-shown real-chapter claims and the depth of the analysis both need acceptance.
4. **CAST-H8 / 4.9 "relationship extraction not applicable" (owner).** The owner has not accepted it yet; it holds 4.9, the Stage 4 Cast gate line (L1666) and Gate 3a (L1671) open. The owner should also decide whether the A11 kinship grounding addresses the description-level relationship errors the docx actually reports.
5. **CAST-H6 role variability (owner, if not fixed).** If the team will not fix it, the owner must explicitly extend the 2026-10-03 model-variability acceptance to role labels. The current acceptance covers presence only.

## Open technical defects

1. **AUDIT-H9 (High): stakes analysis computed but never shown to authors.**
   - **Where:** `backend/schemas.py:291` (`stakes`) and `backend/routers/manuscript_report.py:296` return it. `frontend/lib/types.ts:150-166` omits `stakes` and `themes`, and `frontend/components/plot-holes/ManuscriptReportPanel.tsx` (sections L261–417) renders neither.
   - **Reproduce:** generate a Manuscript Report on a 2+ chapter indexed story, compare the JSON from `POST /api/stories/{id}/manuscript-report` (contains `stakes.summary` and `stakes.escalation`) with the panel (no Stakes section).
   - **Why it is still present:** 5.14 added the backend field only; no Stage 12 tranche touched the panel. Medium AUDIT-M12 (`themes`) has the same gap.
2. **AUDIT-H10 (High): plot-importance prioritisation not surfaced and not tested.**
   - **Where:** `backend/services/ai_service.py:3425-3440` computes `chapter_plot_importance` and `routers/manuscript_report.py:298` returns it. No frontend file references it, and no backend test asserts it (`test_plot_importance_ranking.py` covers only the retrieval helper).
   - **Reproduce:** as above. The payload carries a `{chapter: 0-100}` map; the UI shows nothing.
   - **Why it is still present:** the checklist 5.14 claim "surfaced somewhere an author can see it" is inaccurate.
3. **AUDIT-H8 (High): deterministic open-thread cross-reference not surfaced and not asserted.**
   - **Where:** `ai_service.py:3441-3449` and `routers/manuscript_report.py:299` produce `deterministic_open_threads`. The frontend type and panel omit it; the field appears only in a fixture dict at `backend/tests/test_stage5_persistence.py:53`.
   - **Reproduce:** run a narrative-thread scan, then generate the report. The API lists the open thread names; the panel shows only the LLM's `unresolved_threads`.
   - **Partial mitigation:** dead-end threads appear under "Things to check".
4. **CAST-H6 (High): role misclassification in current live evidence, masked by the regression threshold.**
   - **Where:** `docs/testing/stage-12/tranche3/cast-variability-probe.json`. The raw single-window model output labels Corvin Ashe "antagonist" in 11/25 runs; ground truth is "supporting" (`backend/scripts/quality/cast_variability_probe.py:22`).
   - **Cause:** the prompt `backend/services/prompt_registry.py:407` lists the role values with no definitions.
   - **Why tests miss it:** `backend/tests/test_cast_classification_accuracy.py:84` accepts `accuracy >= 0.75`, so one wrong role out of four passes, contrary to the "100% … pinned as a regression guard" claim in 4.9.
   - **Knock-on:** it also changes the A12 importance order (`routers/characters.py:37`, antagonist rank 1 above supporting rank 2).
   - **Reproduce:** `python3 backend/scripts/quality/cast_variability_probe.py 25 out.json` (live vLLM), then count Corvin roles.
   - **Status:** not recorded or accepted anywhere; the owner's acceptance names only presence.

## Notes on strictness

- **No NOT_APPLICABLE classification.** The 4.9 relationship-extraction N/A is still awaiting the owner's acceptance, and the docx defect is about generated descriptions, which do exist. CAST-H8 is therefore HUMAN_JUDGEMENT.
- **SUG-H9 is FIXED_VERIFIED on the technical root cause only.** The broader suggestion quality stays in the shared author review.
- **Live tests were not re-run** (`test_cast_classification_accuracy.py`, `test_ai_quality_invariants.py`, the live parts of `test_stage9_targeted_issues.py` and `test_character_duplicates.py`). The Stage 12 Tranche 3 record states a final isolated backend run of 1,142 passed / 0 failed.

## Batch table: ui

*(Classifications as found by the batch, before the Stage 12.1 fixes above.)*


Reconciled 2026-10-03 against the current working tree (read-only). Scope: the 15 issues classified Release-blocking (D-6 Critical+High) in `docs/issues-and-bugs/triage-register.md` L254-275 (UI-C1..C8, UI-H9..H15). This matches the register count of 15. The Medium issues M16-M18 are post-launch and out of scope.

Sources: `docs/testing/stage-09-qa-rerun-results.md` L233-247 (Sept-27 status); `docs/NarratIQ_Master_Implementation_Checklist.md` Stage 8 L2583-2770 (8.1-8.11 and the gate) and 9.1 L2796 (2026-10-03 Tranche 3 final runs: studio 104 passed (+3 skipped), a11y 13, variants 32, live browser 69/0/0); `docs/testing/manual-verification/stage-08-manual-verification-guide.md` (MV-8.4/8.5/8.6/8.7 all PENDING); the QA source text in `docs/issues-and-bugs/open/phase-1-ai-writing-tools-qa-issues.docx` (Editor UI section); `frontend/tests/`.

Freshness check: `frontend/.studio-results/.last-run.json` = `passed`, written 2026-10-03 09:14:50 UTC. No file under `frontend/app`, `components`, `lib` or `tests` is newer than that run, so the cited studio specs ran green against the current code. All test titles cited below exist verbatim in the current specs. Caveat: the studio suite uses a mocked API (`tests/studio/mockApi.ts`), and the real-browser layout check MV-8.6 is still PENDING.

## Per-issue table

| ID | Severity | Sept-27 status | CURRENT state | Evidence (with path) | Justification |
|---|---|---|---|---|---|
| UI-C1 | Critical | Author judgement required | HUMAN_JUDGEMENT | `frontend/tests/studio/modes.spec.ts` 'progressive disclosure: at least 30% fewer visible controls with the sidecar open' (baseline 53→≤37 open, <36 closed); checklist 8.3 L2626 / 8.4 L2642 author-review boxes open; MV-8.5 PENDING | The control count is enforced, but "congested / mentally tiring for long sessions" can only be judged by an author (MV-8.5, and 8.11/MV-8.7 for long sessions). |
| UI-C2 | Critical | Author judgement required | HUMAN_JUDGEMENT | `modes.spec.ts` 'Focus hides rail, binder and sidecar; Zen hides all chrome and Esc exits'; `components/ai-tools/AIToolsSidebar.tsx` (sidecar closed by default, 3 groups); checklist 8.3 L2626 open | Whether the manuscript "feels like the central focus" is subjective (8.3 focal-point review, MV-8.5 step 1). |
| UI-C3 | Critical | PASS (automated) | FIXED_VERIFIED | `frontend/tests/tool-homes.spec.ts` 'tool ids are unique — one row, one home', 'every Analyze panel in the registry has a Tool Homes row in Analyze'; `studio/navigation.spec.ts` 'every rail item routes to its workspace and is marked current'; `lib/registries/toolHomes.ts` (Plot/Cast/Notes/OCR/analyses homed in workspaces; sidecar = Rewrite/Generate/Versions only, `AIToolsSidebar.tsx` L70-72); checklist 8.1 ticked L2583 | The right panel is now only the AI sidecar, and every major tool has its own workspace. This is structural and is tested. |
| UI-C4 | Critical | PASS (automated) | FIXED_VERIFIED | `studio/navigation.spec.ts` 'section tabs follow the WAI-ARIA tab pattern and are remembered per story'; `studio/variants.spec.ts` 'the mock tool appears in Analyze, opens full width, and nothing else moves' (variants 32 passed 2026-10-03); 8.1 ticked | Plot/OCR/Notes/Cast/Audit now open as full-page workspaces or sections, not as sidebar tabs. |
| UI-C5 | Critical | PASS (automated) | FIXED_VERIFIED | `studio/variants.spec.ts` 'the mock tool appears in Analyze, opens full width, and nothing else moves', 'the mock tool is absent from the normal build output'; `docs/architecture/adding-a-studio-tool.md`; 8.7 ticked L2677 | Adding a tool is one registry row with no rail or Write change, proven in the mock-tool build. Also exercised for real by A8, which added `manuscript_import` to Write with the studio suite still green. |
| UI-C6 | Critical | Author judgement required | HUMAN_JUDGEMENT | `tool-homes.spec.ts` 'sections named in Tool Homes exist in their workspace'; workspace→section→tool hierarchy in `toolHomes.ts`; 8.4 author-review box L2643 open | The grouping exists and is tested. Whether authors can "easily distinguish" the tool types is a discoverability judgement (MV-8.5 step 2). |
| UI-C7 | Critical | PASS (automated) | FIXED_VERIFIED | `studio/navigation.spec.ts` 'every rail item routes to its workspace and is marked current', 'keyboard shortcuts Ctrl+1..7 switch workspaces'; 8.1 ticked | 7 workspaces (Write, Plan, Characters, World, Analyze, Assistant, Publish) match the requested structure, and routing is tested. |
| UI-C8 | Critical | PASS (automated) | FIXED_VERIFIED | `studio/layout.spec.ts` 'dragging the sidecar resizes it and the width survives a reload', 'Expand widens the sidecar for detailed work, hides the binder, and persists', 'layouts are per user: A resizes, B sees defaults, A gets A's layout back'; 8.2 ticked L2599 | Resizing by drag plus persistence is exercised. The sidecar expands to 65 %, not full width; this is a recorded deviation (checklist L2608), not an owner acceptance. It still meets the issue's "resizable, … expandable, or full-screen workspaces" direction. MV-8.6 (real-browser) is still pending. |
| UI-H9 | High | Author judgement required | HUMAN_JUDGEMENT | `modes.spec.ts` 'Edit is the default mode…', 'Draft hides every AI surface…', progressive-disclosure count; 8.3 author-review open | AI surfaces are hidden by default and in Draft. Whether they still "compete for attention" is subjective (MV-8.5). |
| UI-H10 | High | Author judgement required | HUMAN_JUDGEMENT | `modes.spec.ts` progressive-disclosure test; 8.4 "measured reduction" ticked L2642, "features remain discoverable" open L2643 | The density reduction is measured (34 % open / 25 % closed). The trade-off against discoverability needs the 8.4 author review. |
| UI-H11 | High | Author judgement required | HUMAN_JUDGEMENT | `modes.spec.ts` 'Draft hides every AI surface, is remembered per story, and Edit brings them back', 'Reading mode is read-only…'; 8.5 author-review box open L2658 | Draft/Edit/Reading modes exist and are tested. "Focused experience per task" needs the full drafting and editing sessions in MV-8.5 steps 3-4. |
| UI-H12 | High | Author judgement required | HUMAN_JUDGEMENT | `modes.spec.ts` (Draft/Edit, Reading); 8.5 L2658 open; 8.11 L2743 open (no authors recruited); MV-8.7 PENDING | Daily long-form workflow over weeks can only be validated by real authors in multi-hour sessions (8.11). No automated test covers it. |
| UI-H13 | High | Author judgement required | HUMAN_JUDGEMENT | `studio/navigation.spec.ts` 'palette deep links open a tool in its home', 'Search & replace opens in Write with Ctrl+F and from the palette'; 8.4 L2643 open | Deep links keep tools reachable. The trade-off between discoverability and clutter is the 8.4 author review (MV-8.5 step 2: 30-second find test). |
| UI-H14 | High | Author judgement required | HUMAN_JUDGEMENT | `modes.spec.ts` 'Reading mode is read-only, hides the chrome, and sends no chapter save', 'Focus hides rail, binder and sidecar; Zen hides all chrome and Esc exits'; 8.3 L2626 open | The requested modes (Focus, Reading, Zen/distraction-free) exist and are tested. "Sufficiently distraction-free" is the 8.3 author judgement. |
| UI-H15 | High | Live-pod manual | FIXED_VERIFIED | `studio/phase3.spec.ts` 'Versions and compare have room in the expanded sidecar' (mocked); live `--project=browser`: `tests/browser/phase3-pins-compare.spec.ts` 4/4, `sidecar-lock-and-strength.spec.ts` 3/3, `selection-toolbar.spec.ts` 17/17 (checklist 8.6 L2672, 2026-09-27); live suite 69/0/0 on 2026-10-03 (checklist L2246, L2796); 8.6 ticked L2662 | Advanced tools now have dedicated space: Plot/Audit/Cast/Notes in workspaces; versions, compare and locks in an expandable sidecar with a compare dialog. This passed against real AI. Long-session comfort remains under 8.11. |

## Summary counts (15 release-blocking)

| CURRENT state | Critical | High | Total |
|---|---|---|---|
| FIXED_VERIFIED | 5 (C3, C4, C5, C7, C8) | 1 (H15) | 6 |
| OPEN_TECHNICAL | 0 | 0 | 0 |
| HUMAN_JUDGEMENT | 3 (C1, C2, C6) | 6 (H9, H10, H11, H12, H13, H14) | 9 |
| ACCEPTED_LIMITATION | 0 | 0 | 0 |
| EXTERNAL_DEFERRED | 0 | 0 | 0 |
| NOT_APPLICABLE | 0 | 0 | 0 |
| **Total** | **8** | **7** | **15** |

Change from Sept-27: UI-H15 moved from "Live-pod manual" to FIXED_VERIFIED (8.6 live run 2026-09-27, still green in the 2026-10-03 live 69/0/0). Nothing else changed state. Stage 12 Tranches 1-3 (Next 15 upgrade, A8 import UI, selection-toolbar race fix) did not regress any cited spec: studio, a11y, variants and live suites are green, and no source file is newer than the last passing studio run.

No UI- issue is screen-reader- or CI-dependent. The 8.9 screen-reader pass (MV-8.4) and the CI a11y check (EXTERNAL_DEFERRED, task 6.1) belong to PG-09, not to a UI- issue, so they appear in no row above.

## Remaining Critical/High needing owner decision

All 9 need an author or design-owner review before Gate 8 can close. The owner can also choose to accept them under D-6 instead. No such acceptance is recorded today.
- **Critical:** UI-C1 (congestion), UI-C2 (writing-area priority), UI-C6 (tool hierarchy). Close via MV-8.5 steps 1-2: 8.3 L2626, 8.4 L2643.
- **High:** UI-H9, UI-H10, UI-H13, UI-H14 (MV-8.5 steps 1-2); UI-H11 (MV-8.5 steps 3-4, 8.5 L2658); UI-H12 (needs 8.11 multi-hour real-author session, MV-8.7; no authors recruited).
- Minor note on UI-C8 (already FIXED_VERIFIED): the "expand to full width" deviation (sidecar 65 %) is recorded but has no explicit owner acceptance. The owner may want to acknowledge it. MV-8.6 real-browser layout confirmation is still pending.

## Open technical defects

None found. Every cited spec exists with the cited title and exercises the behaviour, and the last studio run (2026-10-03 09:14 UTC) passed against unchanged source.

Documentation drift (not product defects):
- Stage 8 gate L2764 still says "7 verified in cloud, 11 await author review". With 8.6 ticked, the 18-issue split is now 8 verified (C3, C4, C5, C7, C8, H15, M16, M18) and 10 awaiting (C1, C2, C6, H9-H14, M17).
- The MV-8 guide summary still lists 8.6 / MV-8.2 and MV-8.3 as PENDING, although the checklist records them as done on 2026-09-27.
