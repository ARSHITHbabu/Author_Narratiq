# Defect reintroduction: evidence for checklist 6.6, "Reintroducing any closed defect turns the suite red"

Produced 2026-10-06 by a sub-agent, in an isolated git worktree of commit `2b63b51`
(`.claude/worktrees/agent-ab67cbede685e063d`). The main checkout was never modified, and only this directory
was written into it. Nothing was committed. The worktree ended with no tracked modifications (`git diff --quiet`
was clean after every item and at the end).

## Scope (the owner-approved revised 6.6 criterion)

* **(a) Phase 2, issue by issue.** Every P2 issue whose mapped guard is a deterministic backend test or a pure
  frontend test was run here: P2-2, P2-4, P2-5, P2-8, P2-9, P2-10 (unit half), P2-12, P2-13, P2-14.
  P2-1, P2-3, P2-6, P2-7 and P2-11 are guarded **only** by live browser specs, and the studio half of P2-10 needs
  a working Chromium. Those are **PREPARED, NOT RUN**: see `browser-prepared/` (one patch each, plus `RUNBOOK.md`).
* **(b) Stage 5, at task granularity.** Every task with a deterministic suite test: 5.1, 5.3, 5.4, 5.6, 5.11,
  5.13, 5.14 and 5.15, with one mutation per task aimed at that task's own guarantee (5.14 has two, one per
  mapped file).
* **Out of the suite-red proof:** 5.2, 5.5, 5.7–5.10, 5.12 and 5.16 are guarded by live measurement or the live
  invariant harness (see the 6.5 regression gate). They were deliberately not mutated.
* **Not in scope:** the 147 individual Phase 1 issue numbers (deferred by the revised criterion).

## Method (per item)

1. Run the mapped test file(s) on the unmodified tree. This baseline must pass.
2. Apply ONE minimal, realistic mutation that reintroduces the closed defect at its fix site. Save it with
   `git diff` as `patches/<item>.patch`.
3. Run only the mapped test file(s). They must fail. The failing test ids and the summary line are recorded.
4. Restore with `git checkout -- <file>`, then require `git diff --quiet` to be clean.
5. Run the mapped tests again. They must pass.

Items marked **probe** are an extra, equally realistic regression of the same issue, written to look for
places the guard doesn't reach. When a probe kept its mapped tests green, the mutated tree was also run against
the **whole backend suite** and compared with an unmutated full-suite baseline (`fullsuite_gap_probes.log`).

Kinds:
* **primary**: reintroduces the closed defect.
* **probe**: looks for guard gaps.
* **supplementary**: a deterministic unit spec that is not in the traceability table but covers a browser-only
  item.

The whole run is scripted and reproducible: `python3 tooling/driver.py tooling/muts.py [item ...]`. The scripts
contain the exact anchors and replacement text for every mutation. They hard-code this agent's worktree and
scratch paths in `WT`/`SCR`; adjust those before reusing them.

## Environment

* Python 3.11, system pytest. Node v20.20.2 / npm 10.8.2, with `npm ci` in the worktree.
  Playwright `--project=unit` (pure, no browser).
* `DATABASE_URL=postgresql+psycopg2://narratiq:narratiq@localhost:5432/narratiq_ci_verify` (on the allow-list).
  `SKIP_LLM_TESTS=1`. `SECRET_KEY` was a random 64-hex value generated locally and never printed.
  `VLLM_BASE_URL=http://127.0.0.1:9/v1` was set for the final evidence run (a dead port; see "Other findings").
* **No test database was available to this agent.** PostgreSQL 16 was up, but `narratiq_ci_verify` did not
  exist. The `narratiq` role has no CREATEDB, and this sandbox could not run commands as the `postgres` OS user.
  To avoid colliding with the main session, the agent did not use `narratiq_test`. Consequences:
  * every **mapped** file used for a primary item runs without a DB, except three DB-backed tests in
    `test_story_bible_quality.py`. Those were excluded with
    `-k "not end_to_end and not manuscript_a and not manuscript_b"`, and the other 6 tests in that file ran.
    `test_cast_hint_sync_integration.py` (the second P2-9 file, 2 tests) needs a DB and was not run.
  * the full-suite gap checks ran with `--continue-on-collection-errors`. The unmutated baseline was 41 failed,
    880 passed, 9 skipped and 48 errors, all of them DB- or live-model-dependent. Each probe was judged by
    **new** failures against that baseline, so the DB-backed tests could not take part.
* The live browser suite and the studio spec were not run (see `browser-prepared/RUNBOOK.md`).

## Results (final evidence run, `results.log`)

| Item | Issue | Kind | Production file mutated | Mutation | Mapped tests | Baseline | Mutated | Restored | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| [P2-02-plot-hole-coercion](patches/P2-02-plot-hole-coercion.patch) | P2-2 | primary | `backend/services/ai_service.py` | coerce_plot_hole_result made all-or-nothing again: one malformed finding (non-object or no description) discards the whole response instead of salvaging the usable findings (pre-3.4 hard-fail on invalid AI output) | `test_extract_json_audit.py` | 21 passed in 7.29s | 1 failed, 20 passed in 7.55s<br>`test_parser_metrics_record_each_outcome` | 21 passed in 6.96s | **RED AS EXPECTED** |
| [P2-02b-extract-json-repair](patches/P2-02b-extract-json-repair.patch) | P2-2 | probe | `backend/services/ai_service.py` | _extract_json JSON-repair step broken: the balanced-brace span extraction (JSON embedded in prose / after a preamble) is removed, so only bare or fenced JSON parses | `test_extract_json_audit.py` | 21 passed in 6.82s | 21 passed in 6.78s<br>probe `test_degraded_output.py`, `test_generation_limits.py`: 49 passed in 5.32s | 21 passed in 6.63s | **GUARD GAP (mapped tests stayed green)** |
| [P2-04-voice-intent-silent-guess](patches/P2-04-voice-intent-silent-guess.patch) | P2-4 | primary | `backend/services/voice/intent.py` | voice intent.classify reverted to the pre-3.6 silent fallback: raw _complete + _extract_json(raw, fallback={}) so an unreadable classification becomes a repaired guess at confidence 0.4 instead of an honest failure | `test_voice_execution.py` | 45 passed in 0.70s | 1 failed, 44 passed in 0.79s<br>`test_unreadable_classification_fails_honestly_instead_of_guessing` | 45 passed in 0.75s | **RED AS EXPECTED** |
| [P2-05-voice-false-success](patches/P2-05-voice-false-success.patch) | P2-5 | primary | `backend/services/voice/lifecycle.py` | derive_command_status reports a dispatched-but-unexecuted plan (READY/PLANNED nodes) as SUCCEEDED — the original 'success at plan time' defect | `test_voice_execution.py`<br>`test_voice_unit.py`<br>(`-k not test_planner_drops_invalid_capability`) | 79 passed, 1 deselected in 6.48s | 1 failed, 78 passed, 1 deselected in 6.20s<br>`test_a_plan_that_has_only_been_dispatched_is_not_success` | 79 passed, 1 deselected in 6.94s | **RED AS EXPECTED** |
| [P2-08-bible-status-integrity](patches/P2-08-bible-status-integrity.patch) | P2-8 | primary | `backend/routers/story_bible.py` | derive_status returns STATUS_COMPLETED unconditionally (pre-3.2): a bible whose sections failed/were truncated/empty still reports 'completed' | `test_story_bible_outcomes.py`<br>`test_story_bible_quality.py`<br>(`-k not end_to_end and not manuscript_a and not manuscript_b`) | 97 passed, 3 deselected in 11.47s | 14 failed, 83 passed, 3 deselected in 11.23s<br>`   routers.story_bible:story_bible.py:671 [story_bible] section regeneration failed for s1/themes: context assembly failed`<br>`test_status_is_failed_when_every_section_fails`<br>`test_status_is_partial_when_some_sections_fail` (+12 more) | 97 passed, 3 deselected in 9.30s | **RED AS EXPECTED** |
| [P2-08b-bible-grounding-rules](patches/P2-08b-bible-grounding-rules.patch) | P2-8 | primary | `backend/services/ai_service.py` | generate_story_bible_section grounding rules removed (pre-3.3): no 'cite the source tag' rule, no BIBLE_NOT_ESTABLISHED way to decline, no 'never state anything you cannot attribute' — only the bare 'do not invent' instruction that produced the hallucinated bible | `test_story_bible_outcomes.py`<br>`test_story_bible_quality.py`<br>(`-k not end_to_end and not manuscript_a and not manuscript_b`) | 97 passed, 3 deselected in 9.65s | 1 failed, 96 passed, 3 deselected in 10.20s<br>`test_prompt_requires_citation_and_offers_a_way_to_decline` | 97 passed, 3 deselected in 9.24s | **RED AS EXPECTED** |
| [P2-09-hint-reconcile-noop](patches/P2-09-hint-reconcile-noop.patch) | P2-9 | primary | `backend/services/character_names.py` | resolve_hints_for_names made a no-op: registering/confirming a character never dismisses the matching unrecognised-name hint (the original 'nothing made that decision' defect) | `test_character_hint_sync.py` | 17 passed in 0.14s | 7 failed, 10 passed in 0.23s<br>`test_exact_name_match_dismisses_the_hint`<br>`test_case_insensitive_match_dismisses_the_hint`<br>`test_whitespace_normalised_match_dismisses_the_hint` (+4 more) | 17 passed in 0.16s | **RED AS EXPECTED** |
| [P2-09b-create-character-wiring](patches/P2-09b-create-character-wiring.patch) | P2-9 | probe | `backend/routers/characters.py` | create_character no longer calls resolve_hints_for_names (router wiring removed; service left intact) — a hand-added character stays in the unrecognised list | `test_character_hint_sync.py` | 17 passed in 0.15s | 17 passed in 0.15s | 17 passed in 0.15s | **GUARD GAP (mapped tests stayed green)** |
| [P2-12-outline-beats-field](patches/P2-12-outline-beats-field.patch) | P2-12 | primary | `frontend/components/ai-tools/AIToolsSidebar.tsx` | scene-outline UI reads res.data.beats again (backend returns `outline`) — outline renders nothing | `test_generation_limits.py` | 24 passed in 5.78s | 1 failed, 23 passed in 5.32s<br>`test_frontend_reads_outline_not_beats` | 24 passed in 5.43s | **RED AS EXPECTED** |
| [P2-12b-retrieval-query-kwarg](patches/P2-12b-retrieval-query-kwarg.patch) | P2-12/P2-13 | probe | `backend/routers/writing_tools.py` | PRE-1 root cause restored: writing_tools calls retrieve_relevant_chunks(query=...) instead of question= (TypeError at runtime -> outline/continuation fail) | `test_generation_limits.py` | 24 passed in 5.76s | 24 passed in 6.02s<br>probe `test_retrieval_signatures.py`: 1 failed, 17 passed in 5.62s `test_continuation_passes_question_and_story_id` | 24 passed in 5.04s | **GUARD GAP (mapped tests stayed green)** |
| [P2-13-continuation-token-budget](patches/P2-13-continuation-token-budget.patch) | P2-13 | primary | `backend/services/ai_service.py` | continuation max_tokens fixed at 1600 regardless of requested length (pre-3.1) — Long truncates | `test_generation_limits.py` | 24 passed in 5.36s | 2 failed, 22 passed in 5.27s<br>`test_max_tokens_scales_with_continuation_length`<br>`test_long_budget_clears_the_measured_truncation_point` | 24 passed in 5.35s | **RED AS EXPECTED** |
| [P2-14-continuity-silent-all-clear](patches/P2-14-continuity-silent-all-clear.patch) | P2-14 | primary | `backend/services/ai_service.py` | check_continuity reverted to raw _complete + _extract_json(raw, fallback=[]) — unreadable model output becomes an empty list, i.e. a false 'no contradictions found' | `test_extract_json_audit.py`<br>`test_continuity_citation_validation.py` | 36 passed in 6.41s | 1 failed, 35 passed in 6.47s<br>`test_no_new_direct_extract_json_callers` | 36 passed in 7.16s | **RED AS EXPECTED** |
| [P2-14b-continuity-failure-not-flagged](patches/P2-14b-continuity-failure-not-flagged.patch) | P2-14 | probe | `backend/services/ai_service.py` | check_continuity keeps the structured contract but reports an unreadable response as a clean, non-degraded empty result (false all-clear via the meta instead of via the parser) | `test_extract_json_audit.py`<br>`test_continuity_citation_validation.py` | 36 passed in 6.75s | 36 passed in 7.03s<br>probe `test_degraded_output.py`: 25 passed in 6.26s | 36 passed in 6.96s | **GUARD GAP (mapped tests stayed green)** |
| [S5-5.1-version-label-only](patches/S5-5.1-version-label-only.patch) | Stage 5 task 5.1 | primary | `backend/services/prompt_registry.py` | resolve_prompt_version always runs the fallback's builder but reports the requested version — the version becomes a logged label, not actual prompt content | `test_prompt_registry.py` | 9 passed in 0.03s | 2 failed, 7 passed in 0.07s<br>`test_selecting_a_version_actually_changes_the_builder_not_just_a_label`<br>`test_unknown_version_fails_safe_to_the_configured_fallback` | 9 passed in 0.05s | **RED AS EXPECTED** |
| [S5-5.3-name-preservation-check](patches/S5-5.3-name-preservation-check.patch) | Stage 5 task 5.3 | primary | `backend/services/transform_preservation.py` | check_character_name_preservation never reports a dropped character name (the deterministic preservation check is neutralised, so the repair-retry never fires) | `test_transform_preservation.py` | 27 passed in 5.41s | 3 failed, 24 passed in 4.90s<br>`test_check_character_name_preservation_detects_a_dropped_name`<br>`test_run_constrained_transform_repairs_a_dropped_name_and_clears_the_violation`<br>`test_run_constrained_transform_reports_violation_when_retry_also_fails` | 27 passed in 5.93s | **RED AS EXPECTED** |
| [S5-5.4-lock-byte-identity](patches/S5-5.4-lock-byte-identity.patch) | Stage 5 task 5.4 | primary | `backend/services/transform_preservation.py` | reconstruct_with_locks trusts the model's echo of each [KEEP] segment instead of splicing the original captured bytes — locked sentences can be silently rewritten | `test_transform_preservation.py` | 27 passed in 5.68s | 1 failed, 26 passed in 5.23s<br>`test_reconstruct_splices_original_bytes_for_locked_segments_never_model_echo` | 27 passed in 5.01s | **RED AS EXPECTED** |
| [S5-5.6-strength-proxy](patches/S5-5.6-strength-proxy.patch) | Stage 5 task 5.6 | primary | `backend/services/transform_preservation.py` | check_strength_violation never flags a 'light' edit, whatever the sentence-count change (strength control has no deterministic ceiling) | `test_transform_preservation.py` | 27 passed in 4.89s | 1 failed, 26 passed in 5.51s<br>`test_light_strength_flags_sentence_count_change` | 27 passed in 5.66s | **RED AS EXPECTED** |
| [S5-5.11-glossary-consistency](patches/S5-5.11-glossary-consistency.patch) | Stage 5 task 5.11 | primary | `backend/services/transform_preservation.py` | check_translation_name_consistency ignores the glossary: a name correctly transliterated per the approved glossary is flagged missing (byte-identity semantics wrongly applied to translation) | `test_transform_preservation.py` | 27 passed in 5.18s | 1 failed, 26 passed in 4.97s<br>`test_translation_name_transliterated_per_glossary_is_not_a_violation` | 27 passed in 5.02s | **RED AS EXPECTED** |
| [S5-5.13-priority-sort](patches/S5-5.13-priority-sort.patch) | Stage 5 task 5.13 | primary | `backend/services/ai_service.py` | coerce_writing_suggestions no longer orders suggestions high > medium > low (model's arbitrary order returned) | `test_suggestions_priority.py` | 11 passed in 5.38s | 1 failed, 10 passed in 5.21s<br>`test_suggestions_sorted_high_before_medium_before_low` | 11 passed in 5.17s | **RED AS EXPECTED** |
| [S5-5.14-continuity-tier1](patches/S5-5.14-continuity-tier1.patch) | Stage 5 task 5.14 | primary | `backend/services/ai_service.py` | validate_continuity_citations Tier-1 existence check removed: findings citing fabricated / out-of-range chapters are kept | `test_continuity_citation_validation.py`<br>`test_manuscript_report_citations.py` | 31 passed in 5.38s | 2 failed, 29 passed in 5.05s<br>`test_fabricated_out_of_range_chapter_is_suppressed`<br>`test_partially_fabricated_ref_set_is_suppressed` | 31 passed in 5.25s | **RED AS EXPECTED** |
| [S5-5.14b-report-citations](patches/S5-5.14b-report-citations.patch) | Stage 5 task 5.14 | primary | `backend/services/ai_service.py` | validate_manuscript_report_citations._valid accepts every chapter reference, so fabricated chapters survive in arcs/pacing/threads/strengths/improvements/themes | `test_continuity_citation_validation.py`<br>`test_manuscript_report_citations.py` | 31 passed in 5.34s | 7 failed, 24 passed in 5.26s<br>`test_character_arc_with_partially_fabricated_chapters_keeps_only_real_ones`<br>`test_character_arc_with_entirely_fabricated_chapters_is_suppressed`<br>`test_pacing_chapters_are_filtered_to_real_ones` (+4 more) | 31 passed in 5.17s | **RED AS EXPECTED** |
| [S5-5.15-syllable-count](patches/S5-5.15-syllable-count.patch) | Stage 5 task 5.15 | primary | `backend/services/analytics_service.py` | _count_syllables back to vowel-LETTER counting (old frontend regex): 'queue' scores 4, skewing readability | `test_analytics_service.py` | 22 passed in 0.05s | 1 failed, 21 passed in 0.07s<br>`test_queue_scores_one_syllable_not_four` | 22 passed in 0.06s | **RED AS EXPECTED** |
| [P2-10-notes-duplicated-in-plan](patches/P2-10-notes-duplicated-in-plan.patch) | P2-10 | primary | `frontend/app/(dashboard)/projects/[id]/plan/page.tsx` | Notes re-mounted as a 'Notes' section of the Plan workspace (it also lives in World) — the pre-8.8 duplicated-across-navigation state | `tool-homes.spec.ts` | 8 passed (2.1s) | 2 failed | 6 passed (2.3s)<br>`tests/tool-homes.spec.ts:17:5 › Plan and World pages offer exactly the registered sections`<br>`tests/tool-homes.spec.ts:22:5 › Notes and Narrative Threads are no longer duplicated (Phase 2 Issue 10)` | 8 passed (2.2s) | **RED AS EXPECTED** |
| [P2-01u-toolbar-escape-dismiss](patches/P2-01u-toolbar-escape-dismiss.patch) | P2-1 | supplementary | `frontend/lib/selectionOwnership.ts` | resolveToolbarMode ignores `dismissed` — Escape no longer hides the toolbar (same mutation as browser-prepared/P2-01-toolbar-escape-dismiss.patch) | `selection-ownership.spec.ts` | 34 passed (8.0s) | 2 failed | 32 passed (8.2s)<br>`tests/selection-ownership.spec.ts:99:5 › Escape hides the toolbar even with a live selection`<br>`tests/selection-ownership.spec.ts:215:5 › Escape dismissal applies to the dismissed selection object only` | 34 passed (7.6s) | **RED AS EXPECTED** |
| [P2-11u-toolbar-with-sidebar-open](patches/P2-11u-toolbar-with-sidebar-open.patch) | P2-11 | supplementary | `frontend/lib/selectionOwnership.ts` | selectionOwner no longer gives the selection to the open AI sidebar — the floating toolbar shows alongside it (same mutation as browser-prepared/P2-11-toolbar-with-sidebar-open.patch) | `selection-ownership.spec.ts` | 34 passed (7.1s) | 6 failed | 28 passed (8.2s)<br>`tests/selection-ownership.spec.ts:44:5 › the sidebar owns the selection whenever it is visible`<br>`tests/selection-ownership.spec.ts:48:5 › the sidebar still owns the selection when nothing is selected — it uses the full chapter`<br>`tests/selection-ownership.spec.ts:61:5 › the two surfaces are never both owners — for every input combination` (+3 more) | 34 passed (7.5s) | **RED AS EXPECTED** |

The P2-10 row is the deterministic `tool-homes.spec.ts`, which was run. The second mapped file,
`tests/studio/navigation.spec.ts`, was attempted on the unmutated tree and could not start Chromium:
`libnspr4.so` is missing (`raw/studio-navigation-baseline-attempt.log`). It is prepared, not run, with the same
patch.

## Counts

* **Primary items attempted: 19.** These cover 9 Phase 2 issues (P2-2, 4, 5, 8 (×2), 9, 10, 12, 13, 14) and
  8 Stage 5 tasks (5.1, 5.3, 5.4, 5.6, 5.11, 5.13, 5.14 (×2), 5.15). **19 / 19 turned their mapped tests red**,
  and all were green before and after.
* **Supplementary: 2 / 2 red.** These are P2-1 and P2-11 against `frontend/tests/selection-ownership.spec.ts`.
* **Probes: 4. All 4 kept their mapped tests green.**
  * 1 of them is caught elsewhere in the suite, so the gap is in the traceability mapping only.
  * 3 are not caught by any test that could run here.
* **Prepared, not run: 6.** P2-1, P2-3, P2-6, P2-7 and P2-11 need the live browser suite. The studio half of
  P2-10 needs Chromium.

## Guard gaps found (FINDINGS; nothing was changed to fix them)

1. **P2-2: the JSON-repair step itself is unguarded** (`P2-02b-extract-json-repair`). Removing
   `_extract_json`'s balanced-span extraction stops it parsing JSON embedded in prose or after a preamble.
   `test_extract_json_audit.py` stayed green (21/21), and so did the whole DB-less backend suite: **0 new
   failures**. The mapped file pins the coercers and the caller register, but nothing in the suite feeds
   `_extract_json` a prose-wrapped payload. *Proposed assertion* (`test_extract_json_audit.py`):
   `assert ai_service._extract_json('Here are the issues: {"issues": [{"description": "d"}]} Hope this helps.', None) == {"issues": [{"description": "d"}]}`.
   Add the same for a fenced block and for a trailing comma.
2. **P2-9: the router wiring is unguarded** (`P2-09b-create-character-wiring`). If `create_character` stops
   calling `resolve_hints_for_names`, a hand-added character stays in the unrecognised list, which is the
   literal Issue 9 symptom. `test_character_hint_sync.py` stayed green, and so did the whole DB-less suite. The
   DB-backed `test_cast_hint_sync_integration.py` calls `resolve_hints_for_names` **directly**, not through any
   router. So by inspection (it was not run) it would not catch this either: it proves the service and the
   transaction, not the wiring in `routers/characters.py` (the call sites at lines 577 confirm-cast, 703 create,
   802 and 1125). *Proposed assertion:* a source-level wiring test like those in `test_voice_execution.py`.
   For each of those four handlers, assert that `inspect.getsource(handler)` contains
   `resolve_hints_for_names(`. Better still, add a DB-backed test that goes through the handler.
3. **P2-14: the false all-clear is guarded only at the parser site** (`P2-14b-continuity-failure-not-flagged`).
   With the structured contract kept, `check_continuity` returning `DegradedMeta(False, None, ...)` on an
   unreadable response is exactly Issue 14's "consistent manuscript" lie. Both mapped files and the whole
   DB-less suite stayed green, including `test_degraded_output.py`, which tests the contract and not this caller.
   The primary P2-14 mutation (going back to `_extract_json(raw, fallback=[])`) **is** caught, but only by the
   register tripwire `test_no_new_direct_extract_json_callers`. *Proposed assertion:* stub `_complete_ex` to
   return unparseable text twice, then assert that `check_continuity(...)` returns `([], meta)` with
   `meta.degraded is True` and `"could not be checked" in meta.reason`.
4. **P2-12 / P2-13: the traceability table points at the wrong guard for the root cause**
   (`P2-12b-retrieval-query-kwarg`). Restoring the PRE-1 `retrieve_relevant_chunks(query=...)` call (the actual
   cause of Issues 12 and 13, per task 3.1) left the mapped `test_generation_limits.py` green (24/24). **The
   suite does turn red**, through `test_retrieval_signatures.py::test_continuation_passes_question_and_story_id`
   and `test_model_call_contract.py::test_every_ai_service_call_binds_to_the_real_signature`. *Proposed fix:* add
   `test_retrieval_signatures.py` and `test_model_call_contract.py` to the P2-12 and P2-13 rows of
   `docs/testing/issue-to-test-traceability.md`.

## Other findings

* **A "deterministic" mapped test makes a live model call.**
  `tests/test_voice_unit.py::test_planner_drops_invalid_capability` (a P2-5 mapped file) stubs
  `services.ai_service._complete`. But the planner's fallback `intent.classify` goes through
  `complete_structured` → `_complete_ex`, which is **not** stubbed, so the test reaches the real vLLM.
  This is proven by the run with `VLLM_BASE_URL` pointed at a dead port, where it fails with
  `AIServiceUnavailableError` / `httpx.ConnectError`. Its result therefore depends on whether vLLM is up: it
  failed in this agent's very first baseline while the model was unreachable, and passed later.
  **Disclosure:** in the agent's first pass (`results.run1.log`), before this was noticed, the file ran a few
  times with vLLM (:9001) up, so the test made a handful of small real classification calls (`max_tokens=300`,
  at most 2 attempts each). For the final evidence run (`results.log`) and the full-suite probes, every test
  process had `VLLM_BASE_URL` pointed at a dead port, and P2-5 excluded this one test with `-k` (79 of the 80
  tests in the two files ran). *Proposed fix:* that test should also stub `services.ai_service._complete_ex`
  (or `complete_structured`).
* `--deselect tests/<file>::<test>` run from `backend/` did **not** deselect the three DB-backed
  `test_story_bible_quality.py` tests, so the first P2-8 attempt in `results.run1.log` was INCONCLUSIVE. The
  re-run used `-k`.
* Playwright writes the tracked `frontend/test-results/.last-run.json`, and the studio build rewrites the tracked
  `frontend/next-env.d.ts`. Both make `git diff` dirty without any source change, and the first P2-10 run in
  `results.run1.log` stopped on the clean-tree assertion for that reason. The driver now passes `--output` to a
  scratch directory. Both files were reverted in the worktree.

## Files

* `README.md`: this file.
* `results.log`: the final evidence run (all items). `results.run1.log` is the first pass, which includes the
  aborted and inconclusive attempts explained above and was run before vLLM was blocked.
* `results.json`: per-item baseline, mutated and restored summaries, plus failing ids.
* `patches/*.patch`: one per executed mutation (the `git diff` taken while it was applied).
* `browser-prepared/*.patch` and `browser-prepared/RUNBOOK.md`: the browser-only items (PREPARED, NOT RUN).
  Each patch was checked with `git apply --check`.
* `fullsuite_gap_probes.log`: whole-suite comparisons for the probe items.
* `raw/`: full pytest and Playwright output for every step, including the full-suite baseline and each probe's
  full-suite run.
* `tooling/`: `driver.py`, `muts.py` (the mutation catalogue), `gap_full.py`, `mkpatch.py`, `table.py`.

## Guard gaps closed (main session, 2026-10-06)

The three gaps above are closed by `backend/tests/test_reintroduction_guard_gaps.py` (10 tests, green on the
current code against `narratiq_test`). Each was proven **red** by applying its recorded probe patch to a scratch
copy of the current backend (never to the checkout) and running that file (`guard-gaps-closed.log`):

| Probe | New guard | With the probe patch |
|---|---|---|
| `P2-02b-extract-json-repair` | `test_extract_json_repairs_the_shapes_a_7b_model_actually_returns` (prose-wrapped, fenced, trailing commas, preamble array) | **3 failed** |
| `P2-09b-create-character-wiring` | route-level hint reconciliation for create, rename, confirm-cast and promote | **1 failed** (create) |
| `P2-14b-continuity-failure-not-flagged` | unreadable continuity output must be `degraded` with "could not be checked" | **1 failed** |

The P2-12/13 mapping gap is fixed in `docs/testing/issue-to-test-traceability.md` (`test_retrieval_signatures.py`,
`test_model_call_contract.py` added). `test_voice_unit.py::test_planner_drops_invalid_capability` now also stubs
`_complete_ex` and passes with vLLM unreachable. `frontend/tests/selection-ownership.spec.ts` is added to the
P2-1 and P2-11 rows.

## Browser-only items run (main session, 2026-10-06)

Isolated stack as in `docs/testing/stage-09-regression-results.md`: test backend on :8100 bound to `narratiq_test`
(test-only raised rate limits), frontend built from a **scratch copy** of the checkout with
`NEXT_DIST_DIR=.next-e2e` and served on :3200, fixtures from `seed_fixture.py` + `seed_browser_fixtures.py`,
`--workers=1`. Each patch from `browser-prepared/` was applied to the scratch copy, rebuilt, run, then reversed;
the restored build was re-run (`browser-run.log`).

| Item | Spec | Baseline | Mutated | Restored | Verdict |
|---|---|---|---|---|---|
| P2-03 analytics not scrollable | `analytics-scroll.spec.ts` | 9 passed | **9 failed** (last section never visible) | 9 passed | RED |
| P2-06 OCR upload hidden without a chapter | `ocr-panel.spec.ts` | 5 passed | **5 failed** | 5 passed | RED |
| P2-07 notes failure shown as empty | `notes-reliability.spec.ts` | 13 passed | **12 failed**, 1 passed | 13 passed | RED |

P2-1 and P2-11 were proven red by the unit spec (`selection-ownership.spec.ts`, rows P2-01u / P2-11u) and
P2-10 by its unit half; their live-browser / studio patches were not additionally run.

**Coverage of the revised 6.6 criterion:** Phase 2 **14/14** issues proven (reintroduced → red → restored → green);
Stage 5 **8/8** tasks with a suite test proven; the no-change behaviour of 5.5 is guarded by the 6.5 regression
gate, which detected an injected regression (`../ai-quality-gate/README.md`). Stage 5 tasks guarded only by
measurement scripts (5.2, 5.7–5.10, 5.12, 5.16) are not suite tests and were not mutated. The 147 individual
Phase 1 issue numbers stay deferred by the approved revised criterion.
