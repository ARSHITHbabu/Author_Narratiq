# Gate 3b — AI quality acceptable: human review package (Stage 12.1)

Prepared 2026-10-03. Everything here comes from **saved model outputs or recorded measurements**: no new
judgement, and no decision has been made for you. Gate 3b (Master Execution Plan §13) needs:

| Exit criterion | Technical evidence already collected | Human part (this package) |
|---|---|---|
| Measured improvement over the baseline | Stage 5 task 5.16 golden set (v1 → v2); Tranche 2 measurements (A14 children 8/10 → 0/10 false "already suitable"; A15 Light keeps 0.708 vs Strong 0.576 for Style; A17 suggestions); Tranche 3 A20 | — |
| Blind author review passes | — | **1. `blind-review.md`** |
| No-change requests return unchanged text | `test_ai_quality_invariants.py` (already-suitable passages unchanged; 12/12 on 2026-10-03, with the deliberate-regression proof in `../gate6-regression-detection.md`) | — |
| Every continuity finding cites evidence | Citation validation (`test_continuity_citation_validation.py`); MV-5.14-B live: every finding cites real chapters | **4. MV-5.14-D** |

Do them in this order. Each takes 15–60 minutes.

## 1. Blind author review (MV-5.BR) — `blind-review.md`

- 12 golden-set passages, covering tone, audience, style (including Thriller) and the lock scenarios.
- Each shows two rewrites in random order: the pre-Stage-12 v2 prompts and the current v4 prompts.
- Pick **A / B / no difference** for each.
- Only then open `blind-review-KEY.json` and tally.

MV-5.BR's expected result: the current version preferred or equal on style, and no transform clearly worse.

**Records:**
- the tally;
- your decision on the Stage 5 gate lines "Blind author review passed" and **Gate 3b**.

Rebuild: `cd backend && python3 scripts/quality/build_gate3b_review_package.py <dir>` (fixed seed, identical output).

## 2. A15 Light thresholds — `a15-light-labelling.md`

- 90 Light-strength rewrites (30 each for tone, age adaptation and style; prompt v4).
- Label each **acceptable** or **too much**.

**Records:** the labels. With them, engineering can set the warning/retry thresholds A15 deliberately did not guess.

**Known measurement, for context, not a verdict** (Gate 4 reconciliation): at Light, Tone keeps a median 0.57 of the author's words and age adaptation 0.52; at Strong they keep 0.58 and 0.48. Style keeps 0.71 at Light against 0.58 at Strong. In other words, Light currently barely differs from Strong for Tone and age adaptation (AWT-D/I, 1.2, 1.6, 3.7 in the Gate 4 matrix).

## 3. Children's adaptation — `children-meaning-review.md`

- 8 grief and euphemism passages × 10 children's rewrites each.
- For each rewrite: is every difficult event kept, with the same meaning? Mark **kept** or **changed**.

**Records:** the Tranche 2 open item "Human — children's rewrite meaning review".

## 4. MV-5.14-D — accept (or not) 5.14's three Story Audit items

Procedure, from `docs/testing/manual-verification/stage-05-manual-verification-guide.md`: for each item, record **accept**, **accept with a follow-up** (name it) or **reject** (say what is missing), with the date.

| Item | Evidence (Tranche 3, A20) |
|---|---|
| Critical 4 — timeline reasoning | `../../tranche3/mv-5.14-a.json` (planted reversal reported 3/3, marked flashback 0/3 after the Tranche 3 fix); `../../tranche3/mv-5.14-a-before-fix.json` |
| Critical 5 — narrative reasoning | `../../tranche3/mv-5.14-b.json`, screenshot `../../tranche3/mv-5.14-b-section.png` |
| Medium 11 — relationship arcs | `../../tranche3/mv-5.14-c.json`, screenshot `../../tranche3/mv-5.14-c-section.png` (one pair, one change on the fixture) |

Observed while measuring, for your judgement: some continuity runs on the tiny fixtures added weak findings, for example that Felix burning bread contradicts his promise to help (`mv-5.14-a.json`, story b).

Also new since Stage 5: the Manuscript Report now **shows** stakes, themes, where the plot moves most, and the threads still open in Narrative Threads. The backend produced them, but the panel never displayed them; this was fixed in Stage 12.1 (AUDIT-H8/H9/H10).

## 5. Other author reviews that feed Gate 3b

- **MV-5.AR:** the open per-task author-review boxes 5.7, 5.10, 5.11, 5.13, 5.15 and 5.16, as written in each task.
- **Story Bible "never asserts unsupported facts" (Gate 2 phase text):** read one generated Story Bible against its story. A24's live run logged per-section provenance (characters 28/28, locations 12/12, timeline 13/13, world rules 6/6, themes 7/11 entries cited). The themes section is the one to read most closely.
- **Translation (AWT-5.x):** a fluent-speaker review (task 5.11).
