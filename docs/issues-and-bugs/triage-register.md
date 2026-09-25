# Open-Issue Triage Register

**Purpose:** the single reconciliation point between the two raw QA `.docx` reports (168 issues:
154 Phase 1 + 14 Phase 2) and the execution checklist (`docs/NarratIQ_Master_Implementation_Checklist.md`).
Produced under checklist task **0.9**, 2026-09-21.

**Method:** both source `.docx` files were extracted and read in full (1,213 lines of raw text).
Every issue below is mapped to the checklist task that owns its fix. Classification uses the
**proposed default rule**, pending formal confirmation as task **0.6**'s severity bar:

> **Proposed rule:** Critical and High severity → **release-blocking**. Medium and Low severity →
> **post-launch**. An issue already closed by a completed checklist task → **Resolved**. No issue is
> classified **won't-fix** from evidence alone — that requires a product decision, not an inference,
> and none is proposed here.
>
> Where the source report gives no per-issue severity (the 38 AI Writing Tools category issues,
> 1.1–5.7), the severity of the **checklist task that owns the fix** is used instead — the checklist
> already made that call when it set task priorities.

This is a **proposed** classification, not a final one. See the accompanying message for which
items are genuinely product-sensitive and were brought to the product owner rather than inferred.

---

## Summary

| Source | Issues | Resolved | Release-blocking (proposed) | Post-launch (proposed) | Won't-fix |
|---|---:|---:|---:|---:|---:|
| Phase 2 production testing | 14 | 14 | 0 | 0 | 0 |
| Phase 1 — AI Writing Tools | 48 | 0 | 48 | 0 | 0 |
| Phase 1 — Plot Assistant | 16 | 0 | 14 | 2 | 0 |
| Phase 1 — AI Suggestions | 16 | 0 | 11 | 5 | 0 |
| Phase 1 — Cast Generation & Character Mgmt | 14 | 3 | 8 | 3 | 0 |
| Phase 1 — Story Audit | 15 | 0 | 10 | 5 | 0 |
| Phase 1 — Writing Analytics | 6 | 0 | 0 | 6 | 0 |
| Phase 1 — Search (2 sub-reports, merged) | 21 raw → 14 unique | 0 | 9 | 5 | 0 |
| Phase 1 — Editor UI / Author Workspace | 18 | 0 | 15 | 3 | 0 |
| **Total (unique defects)** | **161** *(168 raw, 7 removed as Search duplicates)* | **17** | **115** | **29** | **0** |

Merge note: the Search module has two sub-reports (9 + 12 = 21 raw issues) that substantially restate
the same underlying defects. 7 issues in Report 1 are near-duplicates of Report 2 and are recorded
below as cross-references, not counted twice.

---

## Phase 2 — Production Testing (all 14 — all Resolved)

| ID | Title | Severity | Classification | Checklist task | Closed |
|---|---|---|---|---|---|
| P2-1 | Selection toolbar doesn't dismiss, blocks controls | Medium–High | Resolved | 3.8 | 2026-07-26 |
| P2-2 | Plot hole detection fails on invalid AI output | High | Resolved | 3.4 | 2026-07-26 |
| P2-3 | Writing analytics page not scrollable | Medium | Resolved | 3.9 | 2026-07-26 |
| P2-4 | Voice agent doesn't execute recognized actions | High | Resolved | 3.6 | 2026-07-26 |
| P2-5 | Voice agent reports success without verifying completion | High | Resolved | 3.7 | 2026-07-26 |
| P2-6 | OCR module shows no upload interface | High | Resolved | 3.10 | 2026-07-26 |
| P2-7 | Notes module loads inconsistently | Medium–High | Resolved | 3.11 | 2026-07-26 |
| P2-8 | Story Bible hallucinates content outside the manuscript | Critical | Resolved | 3.2, 3.3 | 2026-07-26 |
| P2-9 | Character recognition not synced with added profiles | Medium–High | Resolved | 3.12 | 2026-07-26 |
| P2-10 | Notes/Threads duplicated across navigation | Medium | Resolved (Stage 8, branch `claude/stage-8-studio-workspaces`, not yet on `main`) | 8.8 | 2026-09-25 |
| P2-11 | Floating toolbar appears when AI sidebar is open | Medium | Resolved | 3.8 | 2026-07-26 |
| P2-12 | Scene outline generation produces nothing | High | Resolved | 3.1 | 2026-07-24 |
| P2-13 | Chapter continuation generation fails | High | Resolved | 3.1 | 2026-07-24 |
| P2-14 | Continuity analysis not functional | High | Resolved | 3.4 | 2026-07-26 |

**Note on P2-10 (updated 2026-09-25, Stage 8 task 8.8):** fixed. Notes, note cards and the Idea
Shelf now live only in World → Notes; Narrative Threads lives only in Analyze. The one remaining
second view (per-chapter "ideas waiting" markers in the Write binder) is read-only and recorded with
its reason (decision D10) in `frontend/lib/registries/toolHomes.ts`. Evidence: `frontend/tests/tool-homes.spec.ts`
("Notes and Narrative Threads are no longer duplicated") and `frontend/tests/studio/navigation.spec.ts`.
Until 2026-09-25 this row wrongly read "Resolved" in the summary count while the duplication still
existed; the count is now accurate. The fix is on the Stage 8 branch and reaches production only when
that branch is merged.

---

## Phase 1 — AI Writing Tools (48 — all release-blocking, proposed)

No per-issue severity is given in the source document for the 38 category issues; classification
follows the owning checklist task's priority (all Critical or High).

| Category | Issue IDs | Checklist task | Task priority | Classification |
|---|---|---|---|---|
| Tone Transformation | AWT-1.1 – AWT-1.7 (7) | 5.7 (1.7 → 5.5) | High | Release-blocking |
| Emotion Transformation | AWT-2.1 – AWT-2.7 (7) | 5.8 | High | Release-blocking |
| Audience Adaptation | AWT-3.1 – AWT-3.7 (7) | 5.9 (3.6, 3.7 → 5.5) | High | Release-blocking |
| Style Transformation | AWT-4.1 – AWT-4.10 (10) | 5.10 (4.3 → 5.6, 4.8 → 5.5) | High | Release-blocking |
| Translation | AWT-5.1 – AWT-5.7 (7) | 5.11 | Medium | Release-blocking *(see note)* |
| Cross-module Critical A | Rewrite-first architecture | 5.3, 5.12 | Critical | Release-blocking |
| Cross-module Critical B | No author-voice preservation | 5.3 | Critical | Release-blocking |
| Cross-module Critical C | No "no change required" layer | 5.5 | Critical | Release-blocking |
| Cross-module Critical D | Over-transformation | 5.3, 5.4 | Critical | Release-blocking |
| Cross-module Critical E | Content injection | 5.12 | Critical | Release-blocking |
| Cross-module Critical F | Loss of literary subtlety | 5.12 | Critical | Release-blocking |
| Cross-module Critical G | Transformation consistency risk | 5.12 | Critical | Release-blocking |
| Cross-module Critical H | AI voice convergence | 5.12 | Critical | Release-blocking |
| Cross-module Critical I | Editing vs rewriting mismatch | 5.3, 5.6 | Critical | Release-blocking |
| Cross-module Critical J | Preservation hierarchy missing | 5.3 | Critical | Release-blocking |

*Note on Translation (5.11, task priority Medium):* flagged here as release-blocking despite a Medium
task priority because it is part of the same 48-issue cluster the checklist calls "the product's core
value and its largest defect cluster" (Stage 5 preamble) — brought to the product owner as a borderline
case rather than silently overridden.

---

## Phase 1 — AI Plot Assistant (16)

All 9 Critical issues are the D-1 retrieval-scope defect and its consequences (now unblocked —
see task 0.1). High/Medium issues are downstream of the same root cause per the report's own Root
Cause Assessment, cross-corroborated by the Search and Audit modules successfully retrieving
story-wide content while Plot Assistant did not.

| ID | Title | Severity | Checklist task | Classification |
|---|---|---|---|---|
| PA-C1 | Only uses Chapter 1 context | Critical | 4.1 | Release-blocking |
| PA-C2 | Multi-chapter retrieval failure | Critical | 4.1, 4.2 | Release-blocking |
| PA-C3 | Character retrieval failure (later chapters) | Critical | 4.1, 4.2 | Release-blocking |
| PA-C4 | Character alias resolution failure | Critical | 4.6 | Release-blocking |
| PA-C5 | Wrong-chapter retrieval | Critical | 4.1, 4.3 | Release-blocking |
| PA-C6 | Context prioritisation failure (keyword vs relevance) | Critical | 4.3 | Release-blocking |
| PA-C7 | Existing information reported as missing | Critical | 4.3, 4.4 | Release-blocking |
| PA-C8 | Retrieval failure vs knowledge failure confusion | Critical | 4.4 | Release-blocking |
| PA-C9 | Story-wide character memory failure | Critical | 4.1, 4.9 | Release-blocking |
| PA-H10 | Major revelations omitted from summaries | High | 4.5 | Release-blocking |
| PA-H11 | Later-chapter content underrepresented | High | 4.2, 4.5 | Release-blocking |
| PA-H12 | Plot importance ranking failure | High | 4.5 | Release-blocking |
| PA-H13 | Character arc understanding failure | High | 4.9 | Release-blocking |
| PA-H14 | Story reasoning layer insufficient | High | 4.5 | Release-blocking |
| PA-M15 | Emotional arc not captured in summaries | Medium | 4.5 | Post-launch |
| PA-M16 | Relationship intelligence incomplete | Medium | 4.5 | Post-launch |

---

## Phase 1 — AI Suggestions / Writing Tips (16)

| ID | Title | Severity | Checklist task | Classification |
|---|---|---|---|---|
| SUG-C1 | Suggestions are praise, not suggestions | Critical | 5.13 | Release-blocking |
| SUG-C2 | Lack of actionable feedback | Critical | 5.13 | Release-blocking |
| SUG-H3 | No weakness detection | High | 5.13 | Release-blocking |
| SUG-H4 | Positive bias | High | 5.13 | Release-blocking |
| SUG-H5 | Generic feedback | High | 5.13 | Release-blocking |
| SUG-H6 | Repetitive suggestions | High | 5.13 | Release-blocking |
| SUG-H7 | Low recommendation variability | High | 5.13 | Release-blocking |
| SUG-H8 | Over-reliance on fixed categories | High | 5.13 | Release-blocking |
| SUG-H9 | Missing story-specific analysis | High | 5.13 | Release-blocking |
| SUG-H10 | Missing narrative risk detection | High | 5.13 | Release-blocking |
| SUG-H11 | Lack of developmental editing feedback | High | 5.13 | Release-blocking |
| SUG-M12 | Limited editorial depth | Medium | 5.13 | Post-launch |
| SUG-M13 | Lack of recommendation prioritisation | Medium | 5.13 | Post-launch |
| SUG-M14 | Missing contrarian analysis | Medium | 5.13 | Post-launch |
| SUG-M15 | Insufficient story-intelligence integration | Medium | 5.13 | Post-launch |
| SUG-M16 | Observation vs recommendation mismatch | Medium | 5.13 | Post-launch |

---

## Phase 1 — Cast Generation & Character Management (14 — 3 already Resolved)

| ID | Title | Severity | Checklist task | Classification |
|---|---|---|---|---|
| CAST-C1 | Character recognition not syncing after cast generation | Critical | 3.12 | **Resolved** 2026-07-26 |
| CAST-C2 | Cast generation / unrecognized-name detection out of sync | Critical | 3.12 | **Resolved** 2026-07-26 |
| CAST-C3 | Alias resolution failure | Critical | 4.6 | Release-blocking |
| CAST-C4 | Character deduplication failure | Critical | 4.8 | Release-blocking |
| CAST-H5 | Unrecognized-names queue doesn't refresh | High | 3.12 | **Resolved** 2026-07-26 |
| CAST-H6 | Character role classification inaccuracy | High | 4.9 | Release-blocking |
| CAST-H7 | Character importance ranking weak | High | 4.9 | Release-blocking |
| CAST-H8 | Relationship understanding errors | High | 4.9 | Release-blocking |
| CAST-H9 | Character description inconsistencies | High | 4.9 | Release-blocking |
| CAST-H10 | Mention classification errors | High | 4.9 | Release-blocking |
| CAST-M11 | Minor character promotion | Medium | 4.9 | Post-launch |
| CAST-M12 | Mention-to-character linking failure | Medium | 4.9 | Post-launch |
| CAST-M13 | Character memory fragmentation | Medium | 4.8 | Post-launch |
| CAST-M14 | Story-wide character consolidation failure | Medium | 4.8 | Post-launch |

---

## Phase 1 — Story Audit (15)

| ID | Title | Severity | Checklist task | Classification |
|---|---|---|---|---|
| AUDIT-C1 | False character-inconsistency detection | Critical | 5.14 | Release-blocking |
| AUDIT-C2 | False continuity-break detection | Critical | 5.14 | Release-blocking |
| AUDIT-C3 | Surface-level contradiction detection | Critical | 5.14 | Release-blocking |
| AUDIT-C4 | Weak timeline reasoning | Critical | 5.14 | Release-blocking |
| AUDIT-C5 | Limited narrative reasoning | Critical | 5.14 | Release-blocking |
| AUDIT-H6 | High false-positive risk | High | 5.14 | Release-blocking |
| AUDIT-H7 | Character arc analysis too shallow | High | 5.14 | Release-blocking |
| AUDIT-H8 | Incomplete unresolved-thread detection | High | 5.14 | Release-blocking |
| AUDIT-H9 | Story stakes analysis missing | High | 5.14 | Release-blocking |
| AUDIT-H10 | Plot importance prioritisation weak | High | 5.14 | Release-blocking |
| AUDIT-M11 | Relationship arc analysis missing | Medium | 5.14 | Post-launch |
| AUDIT-M12 | Theme analysis missing | Medium | 5.14 | Post-launch |
| AUDIT-M13 | Generic improvement recommendations | Medium | 5.14 | Post-launch |
| AUDIT-M14 | Limited developmental editing insights | Medium | 5.14 | Post-launch |
| AUDIT-M15 | Narrative intelligence depth limited | Medium | 5.14 | Post-launch |

---

## Phase 1 — Writing Analytics (6 — all post-launch, proposed)

Explicitly the lowest-severity report ("Overall Severity: Low to Medium... significantly more stable
and reliable" than other modules). None describe broken functionality — all describe missing
explanation/context for numbers that are already correct.

| ID | Title | Severity | Checklist task | Classification |
|---|---|---|---|---|
| ANLY-M1 | Analytics lack transparency | Medium | 5.15 | Post-launch |
| ANLY-M2 | Readability score lacks explanation | Medium | 5.15 | Post-launch |
| ANLY-M3 | Dialogue ratio lacks genre context | Medium | 5.15 | Post-launch |
| ANLY-M4 | No genre-aware analytics | Medium | 5.15 | Post-launch |
| ANLY-M5 | Limited actionability | Medium | 5.15 | Post-launch |
| ANLY-M6 | Missing story-intelligence integration | Medium | 5.15 | Post-launch |

---

## Phase 1 — Search Module (2 sub-reports, 21 raw → 14 unique)

Report 2 is a superset of Report 1 for exact-search defects; Report 1's matching issues are recorded
as corroborating duplicates, not counted separately.

| ID | Title | Severity | Report 1 ref | Report 2 ref | Checklist task | Classification |
|---|---|---|---|---|---|---|
| SEARCH-1 | Partial query truncation | Critical | Critical 1 | Critical 1 | 4.10 | Release-blocking |
| SEARCH-2 | Character-level matching instead of full-term | Critical | Critical 2 | Critical 2 | 4.10 | Release-blocking |
| SEARCH-3 | Query processing inconsistency | Critical | Critical 3 | Critical 3 | 4.10, 4.14 | Release-blocking |
| SEARCH-4 | Incorrect match counting | High/Critical | Critical 4 | High 4 | 4.11 | Release-blocking |
| SEARCH-5 | Highlighting logic failure | High | High 5 | High 5 | 4.11 | Release-blocking |
| SEARCH-6 | Exact search mode not respecting full query | High | High 6 | High 6 | 4.12 | Release-blocking |
| SEARCH-7 | Search result relevance degradation | High | High 7 | — | 4.14 | Release-blocking |
| SEARCH-8 | Duplicate semantic search results | High | — | High 7 | 4.13 | Release-blocking |
| SEARCH-9 | Chunk deduplication failure | High | — | High 8 | 4.13 | Release-blocking |
| SEARCH-10 | Search engine consistency problems | Medium | Medium 8 | — | 4.14 | Post-launch |
| SEARCH-11 | Regex/tokenisation handling issue | Medium | Medium 9 | Medium 11 | 4.14 | Post-launch |
| SEARCH-12 | Overlapping chunk results | Medium | — | Medium 9 | 4.13 | Post-launch |
| SEARCH-13 | Search result diversity reduction | Medium | — | Medium 10 | 4.13 | Post-launch |
| SEARCH-14 | Result ranking optimisation needed | Medium | — | Medium 12 | 4.14 | Post-launch |

Positive finding recorded for context, not an issue: semantic search's multi-chapter retrieval
already works correctly and is cited by both reports as evidence that the Plot Assistant's failure
(above) is isolated to its own pipeline, not a story-wide ingestion problem.

---

## Phase 1 — Editor UI / Author Workspace (18)

| ID | Title | Severity | Checklist task | Classification |
|---|---|---|---|---|
| UI-C1 | UI too congested for long-term use | Critical | 8.3, 8.4 | Release-blocking |
| UI-C2 | Writing area not prioritised | Critical | 8.3 | Release-blocking |
| UI-C3 | Right-side panel overloaded | Critical | 8.1 | Release-blocking |
| UI-C4 | Major tools treated as small tabs | Critical | 8.1 | Release-blocking |
| UI-C5 | UI doesn't scale for future features | Critical | 8.7 | Release-blocking |
| UI-C6 | Tool hierarchy not clear | Critical | 8.4 | Release-blocking |
| UI-C7 | No workspace-based navigation | Critical | 8.1 | Release-blocking |
| UI-C8 | Side panel cannot be resized | Critical | 8.2 | Release-blocking |
| UI-H9 | AI tools visually compete with manuscript | High | 8.3 | Release-blocking |
| UI-H10 | Navigation density too high | High | 8.4 | Release-blocking |
| UI-H11 | No drafting/editing mode separation | High | 8.5 | Release-blocking |
| UI-H12 | Long-form workflow not respected | High | 8.3, 8.5 | Release-blocking |
| UI-H13 | Feature discoverability creates clutter | High | 8.4 | Release-blocking |
| UI-H14 | No focused reading/writing mode | High | 8.3 | Release-blocking |
| UI-H15 | Advanced AI features need dedicated space | High | 8.6 | Release-blocking |
| UI-M16 | Information architecture needs redesign | Medium | 8.8 | Post-launch *(see note)* |
| UI-M17 | Layout feels like a dashboard, not a studio | Medium | 8.3 | Post-launch |
| UI-M18 | Future feature expansion will increase friction | Medium | 8.7 | Post-launch |

*Note on UI-M16:* also carries Phase 2 Issue 10 (Notes/Threads navigation duplication) via task 8.8 —
see the Phase 2 table above, which classifies the combined item as release-blocking despite this row's
Medium source severity, since it gates Stage 8's own completion gate.

*Stage 8 status (2026-09-25, branch `claude/stage-8-studio-workspaces`):* all 18 have an implemented
fix and cloud tests on a mocked API. C3, C4, C5, C7, C8, M16 and M18 are verified in the cloud. C1, C2,
C6, H9–H15 and M17 are implemented but stay open until the author reviews named in checklist tasks
8.3–8.6 and the 8.11 usability session. See `docs/testing/manual-verification/stage-08-manual-verification-guide.md`.

---

## Items requiring product-owner decision (not resolved by the default rule alone)

1. **Whether a full Editor UI redesign (Stage 8, 15 of 18 issues proposed release-blocking) is
   actually a v1 release blocker**, or whether v1 can ship on the current UI with Stage 8 as a
   fast-follow. This is the single largest scope commitment in the "release-blocking" column.
2. **Translation (task 5.11, 7 issues)** — proposed release-blocking despite the checklist's own
   Medium task priority, because it's part of the same 48-issue Stage 5 cluster. Confirm or override.
3. **The default rule itself** — task 0.6 is where this rule is meant to be formally set. Everything
   above is provisional until that happens.

This register does not itself close task 0.9 — see the consolidated Stage 0 decision request for
what's being brought to the product owner now.
