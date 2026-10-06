# Stage 12.3 — technical completion and review packages (2026-10-06)

**Baseline:** `main` at `2b63b51` ("stage 12.3 half completed", committed and pushed by the owner on 2026-10-05
before the previous pod was deleted). **Changes of this tranche are uncommitted**; no commit, push, tag, version
change or sign-off was made. **Pod:** `12j8ehik2alm0j` (1× A40), new; rebuilt from the repository with
`start-narratiq.sh` (Node 20, PostgreSQL 16 + pgvector, vLLM 0.9.2, Qwen2.5-7B-Instruct, BGE-M3, faster-whisper;
GOT-OCR lazy). Live database `narratiq` empty at `0027`; allow-listed `narratiq_test` created, migrated to head and
seeded (`seed_fixture.py`, `seed_browser_fixtures.py`). No data, backups or runtime from the deleted pod exist or
were sought. W-3 and W-5 unchanged (open); no external infrastructure configured; `SECRET_KEY` never printed.

## 1. Technical work

| Item | What changed | Verification |
|---|---|---|
| **Cast test (owner-approved treatment)** | `backend/tests/_cast_identity.py` (identity check); `test_cast_classification_accuracy.py`: identity hard by name, presence label a separate `xfail(strict=False)` test citing CAST-H10; `test_cast_t2a.py`: replay of the observed failure shape (probe run 7) through `extract_cast` and the generate-cast route, and a self-test that the identity check catches lost / merged / invented / duplicated / flagged characters | deterministic 31/31 with the other new tests; live 6 consecutive runs: identity 6/6 pass (run 3 had Vell labelled `historical` — identity held), presence test XPASS 6/6 |
| **7.10 Tier-2 warning text** | `services/consistency.py`: the check asks for the rule, an exact passage quote and a describing sentence; the quote is verified against the output; an echo of the rule is rewritten from the verified quote ("The rewrite says “…”, which contradicts an established world rule: “…”") or dropped when nothing in the passage supports it. Never edits the passage | `test_consistency_tier2_text.py` 8/8; live probe `scripts/quality/tier2_warning_text_probe.py`, 4 world-rule scenarios × 5 runs, same path with the old vs new prompt: restating **12/20 → 0/20**, describing 8/20 → **20/20**, contradictions flagged 20/20 → 20/20 (`tier2-warning-text-{before,after}.json`) |
| **6.5 regression gate** | `tests/ai_quality_regression_gate.py`: each harness invariant N=20 live; one-sided Fisher exact vs a recorded baseline, family α 0.01 (Bonferroni over 11); HTTP errors invalidate a run | `test_ai_quality_regression_gate.py` 8/8; live: baseline (adventure-3 17/20, others 20/20), unchanged re-run no alarm, the Stage 12.1 degradation changes nothing (no alarm, correct), prompt/parser drift **ALARM** on exactly the 4 no-change invariants (0/20) — `ai-quality-gate/README.md` |
| **6.6 defect reintroduction** | Evidence only, plus closing the gaps it found: `tests/test_reintroduction_guard_gaps.py` (JSON repair, character-route hint wiring ×4, continuity false all-clear); `test_voice_unit.py` no longer reaches the live model; traceability table corrected | Phase 2 14/14 and Stage 5 8/8 reintroduced → red → restored → green (19 + 2 backend/unit, 3 live-browser); each new guard red against its probe patch — `defect-reintroduction/README.md` |
| **Documentation and code-comment corrections** | `backend/config.py` and `services/ai_service.py` docstrings (retired `start.sh`, RTX 4090 table, wrong vLLM URL); `runpod-environment-variables.md` row; release notes (gates, baseline, A1, CAST, Suggestions availability); sign-off record (baseline, new pod, §5, §7, §9); `gate4-section3-review.md` addendum; checklist reconciliation (below) | `make docs-check` 3 pairs in sync, `make docs-paths` 0 unresolved |

### New finding (not changed by engineering)

**Writing Suggestions has no way in from the studio.** `aiApi.suggestions` (`frontend/lib/api.ts`) has no caller;
the last UI call was removed by `34dc303` ("ui/ux update", 2026-06-12), before the Stage 5 overhaul, which was
verified at the API level only. A sweep of every client API function found no other author-facing AI feature
without a caller. Restoring a studio tool (or retiring the feature) is an owner decision (Stage 8 information
architecture): new owner box in the checklist's Stage 12.3 record; Owner Decision Package OD-09.

## 2. Checklist reconciliation (evidence only)

* **Ticked on existing evidence (8):** 1.6 and "Feed all findings into task 11.4" (done by 11.4); Stage 9 gate
  "Security suite passed including cross-user isolation"; Final checklist: D-1…D-8 recorded and applied,
  D1…D12 recorded and applied, C-1…C-8 resolved, backup/restore and rollback rehearsed, security suite passed.
* **Unticked as contradicted (3):** 5.12-G and "Repeated identical transforms produce stable results" (AWT-G
  criterion NOT MET on the current code, B1); Stage 4 gate "Retrieval regression suite green in CI" (no CI exists;
  W-1).
* **Ticked by today's work (5):** the cast-test owner box (decided and implemented); 7.10's Tier-2 item and the 7.10
  task; 6.5 "A deliberate prompt regression is detected by the harness"; 6.6 "Reintroducing any closed defect
  turns the suite red".
* **Added (1, open):** the Writing Suggestions finding (owner).

## 3. Review packages

* `review-packages/NarratIQ_Human_Review_Package.docx` — 32/32 human-review boxes mapped, 26 reviews (HR-01–HR-26),
  468 answer fields, D-6 human items 20/20 Critical and 46/46 High; everything PENDING HUMAN REVIEW.
* `review-packages/NarratIQ_Owner_Decision_Package.docx` — 21 open owner boxes + 1 already decided (cast test)
  mapped; 21 decisions (11 with boxes, 10 review pass rules); final sign-off separated and BLOCKED.

## 4. Regression on this tree (not the W-1 release-commit record)

`backend/tests/run_full_regression.sh`, one suite at a time, on `2b63b51` + this tranche's uncommitted changes
(pod `12j8ehik2alm0j`, `narratiq_test`). **Not the W-1 record**: W-1 needs a clean, committed release candidate.

| Suite | Result |
|---|---|
| backend | **1,225 passed, 0 failed**, 1 xfailed (the known strict chapter-reorder product gap), 1 xpassed (CAST-H10 presence test, non-blocking), 4 deselected (known-defects marker) |
| known-defects | 4 passed |
| retrieval | 147 passed, 1 xpassed |
| migration round trip | PASS |
| AI invariants (harness) | 12 passed |
| docs-sync / docs-paths | 3 pairs in sync / 0 unresolved |
| frontend unit / studio / a11y / variants | 108 / 109 / 13 / 20 passed |
| live browser (subset run for 6.6) | analytics-scroll 9, ocr-panel 5, notes-reliability 13 passed (baseline and restored) |
| new focused tests | cast 31 deterministic + 6 live runs; Tier-2 text 8; regression gate 8; guard gaps 10; voice planner offline 1 |

**First backend run: 14 failed, 2 errors — caused by this tranche, fixed, re-run green.** Every failure was
`AIServiceUnavailableError` from a closed vLLM client: the new gate unit test entered `with TestClient(main.app)`,
and the app lifespan's shutdown closes the shared client for every later test in the process. The test now never
enters the lifespan; the affected live tests pass after it in the same process, and the full re-run is the line
above.

Not run in this tranche (unchanged since their last recorded runs, or W-1 scope): the full live browser suite, the
script tests (`scripts/tests`), the prompt-injection probes and the dependency audits — all part of the W-1
release-commit regression (`docs/operations/release-regression.md`).

## 5. Owner-authorised agent human review — technical defects found and fixed (2026-10-06, later)

The owner authorised the agent to perform HR-01 – HR-21 (Option 1). Every defect the review found that code could fix
was fixed with the smallest change, its original evidence preserved under `agent-review/`, a regression test added
(each frontend fix and the rewrite/bible fixes proven **red on the old code**), and only the affected review re-run.

| # | Defect (review) | Severity | Fix | Regression test |
|---|---|---|---|---|
| 1 | Pressing Ctrl/⌘Z a few times after opening a chapter emptied it (or restored the previously open chapter) and autosave saved that — chapter 40 of the review story lost 684 words (HR-15, seen in HR-17) | **Critical** | `StoryEditor.loadIntoEditor()`: chapter loads are not undo steps | `frontend/tests/studio/undo-safety.spec.ts` (2, red on old code); live re-check: 6× undo, chapter intact |
| 2 | Manuscript Report on 40 chapters: 6,820 + 1,800 tokens over the 8,192 window → "AI unavailable" (HR-09) | High | `_fit_manuscript_lines`: shorten events, never drop a chapter, say so | `test_manuscript_report_fit.py` (4) |
| 3 | "Where the plot moves most" all 0.0 (capped retrieval boost reused for display) (HR-09) | Major | uncapped display score; section hidden when flat | `test_report_plot_importance.py` (3) |
| 4 | Story Bible timeline "truncated" at 1,500 tokens on 40 chapters (HR-10) | High | 1,900 tokens + one short line per event; context budget follows | `test_story_bible_outcomes.py` |
| 5 | Story Bible characters "truncated" in 3/5 live runs, 6/8 samples (a card per townsperson; a looping list) (HR-10) | High | ≤ 10 full cards + one "Also appears" line; one fresh sample on a length stop; a run-on list closed with complete cards kept | `test_story_bible_character_budget.py` (14); live: 2/2 full runs complete |
| 6 | Suggestions with no selection sent text cut mid-word → "excerpt ends mid-sentence" (HR-11) | High | `lib/suggestionText.wholeSentences` | `frontend/tests/suggestion-text.spec.ts` (5); live: 1,912 chars ending at a full stop |
| 7 | Suggestions claimed "'Wren pushed her way through the throng' is repeated verbatim" — it occurs once (HR-11) | High | `suggestion_hygiene.false_repetition_claim` | `test_suggestion_repetition_claims.py` (7); live: item dropped |
| 8 | A restored AI panel took focus on page load; the first Tab skipped "Skip to content" (HR-16) | High | `AISidecar`: move focus only when opened from a focused control | `tests/studio/a11y.spec.ts` (red on old code) |
| 9 | The manuscript editor had no role or accessible name (HR-16) | High | `role=textbox`, `aria-multiline`, `aria-label="Chapter text"` | `a11y.spec.ts` |
| 10 | Story Bible section content not keyboard-scrollable — axe serious `scrollable-region-focusable` with real data (HR-16) | High | focusable named region | `a11y.spec.ts`; live axe 0 violations on 7 workspaces |
| 11 | A "Match my voice closely" rewrite returned `Before: "<original>" After: "<rewrite>"` (HR-18) | High | `_unwrap_before_after` in the shared rewrite step | `test_rewrite_before_after_echo.py` (6, red on old code) |

Also implemented: **OD-13** (tone/style Light limit 0.24 derived from the HR-07 labels; `LIGHT_NEW_SHARE_MAX_TONE_STYLE`;
`test_light_strength_repair.py` +4); one pre-OD-13 test premise corrected (`test_generation_context.py`: its fake
rewrite changed 33 % of the words and now also gets the Light retry); HR-21 tabletop clarified
`docs/operations/backup-and-restore.md` §4 step 2. Test data: chapter 40 of the synthetic review story restored
from the source manuscript after defect 1.

Not fixed (design or model quality, recorded for the owner): Story Audit/Bible/Suggestions content accuracy; Compare
versions and Search & replace discoverability; the "Coming Soon" analytics panel; voice matching shown above Continue,
which ignores it; Story Bible character cards mostly without [Ch N] tags.

**OD-13 side effect (recorded, not hidden).** The full backend run after the review had one failure:
`test_ai_quality_invariants.py::test_light_strength_does_not_trip_the_strength_violation_flag` (live model). Under
the owner-rule Light limit of 0.24 for tone, the Light rewrite of `tech-1` is flagged in 4 of 5 runs (it was never
flagged at 0.45). This is the open G1 finding (HR-06 FAIL), so the test was moved to the honestly-red
`known_stage5_defect` set rather than relaxed. The 6.5 AI-quality gate's `light_not_flagged:tech-1` probe uses the
same check and will alarm against its pre-OD-13 baseline (20/20): re-baselining it is a deliberate owner-visible
step and was **not** done.

**Regression after the agent review** (`run_full_regression.sh`, `narratiq_test`, same uncommitted tree; not the W-1
record): backend **1,263 passed, 1 failed** (the OD-13 invariant above, since marked known-defect; that file then
11 passed / 1 deselected), 4 deselected, 1 xfailed, 1 xpassed · frontend unit **113** · studio **116** · a11y **16** ·
variants **20** · docs-sync 0 unresolved — all passed.
