# Stage 12.1 — Section 3: Gate 4 review (the 114 release-blocking issues, regenerated)

Regenerated 2026-10-03, after:
- the owner's Section 1 decision (4.9: Option B);
- the AWT-G 10-trial measurement (`awt-g-consistency.md`) and the owner's direction on it;
- the Story Bible prompt-example fix (a Gate 2 defect; not one of the 114, recorded below);
- the PA-C6 / PA-H12 long-manuscript measurement (`pa-long-manuscript-measurement.md`) and the two defects it exposed, both fixed: chapter summaries read only the first 8,000 characters, and BGE-M3 CPU threads ignored the container quota (indexing 44 min → 220 s);
- all Tranche 1–3 and Stage 12.1 evidence.

Severities unchanged. **Nothing below is closed on the basis of the pending Section 2A/2B/2C/2D judgements.** Each issue appears exactly once. Per-issue evidence: `gate4-release-blocking-matrix.md`.

## Summary

| Category | Critical | High | Total |
|---|---:|---:|---:|
| 1. Fixed and verified | 17 | 16 | **33** |
| 2. Accepted / owner-decision candidates | 0 | 2 | **2** |
| 3. Human quality review pending | 20 | 46 | **66** |
| 4. Technical work still required | 0 | 0 | **0** |
| 5. Model variability / known-limitation candidates | 2 | 2 | **4** |
| 6. External or other blockers | 0 | 9 | **9** |
| **Total** | **39** | **75** | **114** |

**Gate 4 ("zero open Critical; every High fixed or explicitly accepted"): not passed.**
- 22 Critical are not fixed: 20 human review, 2 known-limitation candidates (AWT-G, PA-C6). **No technically resolvable Critical or High defect remains open.**
- 57 High are neither fixed nor accepted.

## 1. Fixed and verified (33)

| | Issues |
|---|---|
| Critical (17) | AWT-C; PA-C2, C3, C4, C5, C7, C8; SEARCH-1, 2, 3 (Stage 12.1 race fix); CAST-C3, C4; UI-C3, C4, C5, C7, C8 |
| High (16) | AWT-1.7, 2.4, 2.5, 3.4, 3.6, 4.3; SEARCH-4–9; CAST-H7, H9; SUG-H9; UI-H15 |

## 2. Accepted / owner-decision candidates (2)

| Issue | Status |
|---|---|
| CAST-H10 (High), presence classification variability | **Accepted** by the owner 2026-10-03 (model variability) |
| CAST-H8 (High), relationship understanding errors | **Accepted as not applicable** by the owner 2026-10-03 (Section 1, Option B): no AI relationship-extraction pipeline exists. The A11 family-claim grounding and the `relationship_changes` Manuscript Report section are recorded separately. **Post-release follow-up** (non-blocking): measure the accuracy of relationship statements in AI-generated character descriptions, including non-family relationships |

## 3. Human quality review pending (66)

Grouped so each decision has one meaning:

| Group | Issues | Decided by | Notes |
|---|---|---|---|
| **G1 — Light strength** | AWT-D, AWT-I (Critical); AWT-1.2, 1.6, 3.7 (High) | **Section 2B labels** | Measured: Light barely differs from Strong for tone and age adaptation. Your labels decide whether this is an acceptable limitation (→ category 5) or needs technical work (→ category 4: a warning or retry threshold from your labels) |
| **G3 — Rewrite quality and voice** | AWT-A, B, E, F, H, J (Critical); tone 1.1, 1.3, 1.4, 1.5; emotion 2.1, 2.2, 2.3, 2.6, 2.7; audience 3.1, 3.2, 3.3, 3.5; style 4.1, 4.2, 4.4–4.10 (22 High) | **Section 2A blind review** (+ **2C** for the audience items) | AWT-E: the A16 invented-name note checks names, not imagery |
| **G5 — Story Audit** | AUDIT-C1–C5 (Critical); AUDIT-H6–H10 (High) | **Section 2D (MV-5.14-D)** and the 5.14 author review | AUDIT-H8/H9/H10's display gap fixed in Stage 12.1; the usefulness of the content is still your judgement |
| **G6 — Suggestions** | SUG-C1, C2 (Critical); SUG-H3–H8, H10, H11 (High) | 5.13 author review (try Suggestions on your own manuscript) | SUG-H9's technical cause fixed (category 1) |
| **G7 — Plot Assistant answers** | PA-C1, PA-C9 (Critical); PA-H10, H11, H13 (High) | Your Plot Assistant use or UAT | PA-C1's technical part is now verified (studio and live 4.1 check, 3/3; summary-evidence metadata defect fixed). Risk noted for H10/H11: summary questions get passages, not chapter summaries (not classified as a defect). Long-manuscript evidence: revelations in stored summaries 4/7 (the 8,000-character truncation found here is **fixed**; the 3 misses are the model's choice of what to summarise); C9 character coverage 3/3, 4/6, 4/5 |
| **G8 — Workspace and UI** | UI-C1, C2, C6 (Critical); UI-H9, H10, H11, H13, H14 (High) | 8.3 / 8.4 / 8.5 author reviews | UI-C8: the sidecar expands to 65 % width (recorded deviation, never explicitly accepted) |

Critical in this category: 6 (G3) + 2 (G1) + 5 (G5) + 2 (G6) + 2 (G7) + 3 (G8) = **20**. High: 3 + 22 + 5 + 8 + 3 + 5 = **46**.

## 4. Technical work still required (0)

PA-C6 and PA-H12 were here. The long-manuscript measurement has now run (`pa-long-manuscript-measurement.md`): 40 chapters, 32,228 words, 14 planted scenarios, the production path.
- **Recall:** criterion A was met in 12–13 of 14 scenarios.
- **Ordering:** criterion B (critical ranked above every decoy) was met in only 7–9 of 14.
- **Root cause:** BGE-M3 similarity. Decoys share more words with the question. The ranking code reproduces cosine order; no code defect.
- **Moved to category 5.**
- **Two real defects found along the way, both fixed with tests:**
  - chapter-summary truncation at 8,000 characters;
  - BGE CPU thread oversubscription.

(If your 2B labels reject Light strength, G1's five issues move here.)

## 5. Model variability / known-limitation candidates (2)

| Issue | Measured | Status |
|---|---|---|
| **AWT-G (Critical)**, run-to-run consistency | 120 transforms (12 × 10). Mean stdev text **0.0866** vs the **0.0643** baseline: **criterion NOT met**. Concentrated in borderline unchanged-vs-rewrite decisions (3/12 scenarios; the no-change check flips 19/20, 15/20, 3/20 on identical input); the rewrites themselves are stable (0.031) | The owner directed: record as **model variability, not a code defect**; the author stays in control (nothing applied without Replace); **no caching or other metric-improving workaround**. **Not passing its original criterion.** Formal acceptance as a known limitation is the owner's Gate 4 decision |
| **PA-C6 (Critical)**, Plot Assistant context prioritisation | Long manuscript, 12 PA-C6 scenarios. The critical passage is delivered in **12/12** (one run) and **11/12** (re-index). It is ranked above every decoy in **7/12**, **6/12** full-manuscript, and 8/12 capped at the chapter. Decoys win on BGE-M3 cosine (e.g. 0.600 vs 0.515). A summary-blend design was measured offline and gave partial, non-monotonic gains, so it was **not implemented** | **Criterion B not met.** No code defect. Owner decision: accept as a documented retrieval limitation (the model still receives the critical passage almost always), or commission a retrieval-design change (summary blend, query expansion or a re-ranker) |
| **PA-H12 (High)**, minor vs major events | 1/2 abstract "what major thing did X do" scenarios pass. For Liesel Marr the poisoning passage is not retrieved: it is not in the cosine top 40 | Same owner decision as PA-C6 |
| **CAST-H6 (High)**, role classification | A reluctant ally is labelled antagonist 11/25 (44 %); general role definitions were measured **worse (22/25)** and reverted | **Not fixed.** Owner decision: accept as documented model variability (roles are editable; unknown roles fall back to "supporting"), or require deeper non-prompt work |

## 6. External or other blockers (9)

| Issue | Blocker |
|---|---|
| AWT-5.1–5.7 (7 High), translation | **A fluent-speaker review is required** (owner, 2026-10-03: not a limitation, not reclassified). The French evidence already shows apparent language errors ("le console", "la navire", "chuchora", "l'cloche", "l'orchard", "je ferai") |
| PA-H14 (High), Plot Assistant usefulness over a writing session | Real-author UAT (9.6) |
| UI-H12 (High), long-session fatigue / multi-hour use | The multi-hour real-author session (8.11) |

## Owner decisions that would be needed next (in order)

1. **Sections 2A–2D** (still pending): they decide G1, G3, G5 and part of G7/G8, which is **66 issues, 20 of them Critical**.
2. **G1 after 2B:** accept Light strength as a limitation, or require threshold work.
3. **AWT-G and CAST-H6:** formally accept each as a documented model-variability limitation, or require work.
4. **PA-C6 / PA-H12:** measured. Accept the ordering limitation, or commission a retrieval-design change.
5. **G6 Suggestions, G7 Plot Assistant, G8 UI:** your own review sessions, or defer to UAT.
6. **Translation:** name the fluent reviewer(s) and language(s).
7. **UAT (9.6 / 8.11):** schedule real authors, or record a decision to release without them.
