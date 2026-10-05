# Stage 12 final human review — running decision record

Started 2026-10-05 (Stage 12 final human review package). Each answer is recorded as the owner gave it, in this session.
No decision is made on the owner's behalf; this file is only the record.

## A1 — Blind rewrite review (MV-5.BR)

Material: `blind-review.md` (12 pairs). The key (`blind-review-KEY.json`) was opened only after all 12 answers.

| Pair | Scenario | Owner's choice | Preferred version |
|---|---|---|---|
| 1 | adventure-1 · age_adapt (children) | B | v2 |
| 2 | adventure-2 · age_adapt (children) | B | v4 |
| 3 | adventure-3 · age_adapt (children) | B | v2 (returned the original unchanged) |
| 4 | adventure-4 · age_adapt (children) | B | v4 (returned the original unchanged) |
| 5 | gothic-1 · tone (suspenseful) | B | v4 (rewrite; v2 unchanged) |
| 6 | gothic-2 · age_adapt (adult) | N | identical texts |
| 7 | gothic-3 · tone (suspenseful) | N | identical texts |
| 8 | gothic-4 · age_adapt (YA) | N | identical texts |
| 9 | tech-1 · style (cinematic) | B | v4 |
| 10 | tech-2 · style (cinematic) | B | v4 |
| 11 | tech-3 · age_adapt (adult) | N | identical texts |
| 12 | tech-4 · style (cinematic) | B | v2 (rewrite; v4 unchanged) |

Tally: v4 preferred 5, v2 preferred 3, no difference 4. By transform: style v4 2 / v2 1; tone v4 1 / v2 0 / N 1;
age_adapt v4 2 / v2 2 / N 3. MV-5.BR expected result ("current version preferred or equal on style; no transform
clearly worse"): met by the owner's choices.

**Result: PASS** (owner's instruction 2026-10-05: the answers are the decision; the result follows objectively from
the existing criterion). Applied: 5.16 "Conduct blind author review" and "Blind author review passes", the Stage 5 gate
line "Blind author review passed", 5.7 "Author review on tone transforms" ticked. Observation kept for A3: in pairs
3 and 4 the owner preferred the version that left the original unchanged over a children's rewrite.

## A2 — Light vs Strong (A15 sample)

Material: `a15-sample-light-vs-strong.md` (15 pairs: 6 tone, 6 age adaptation, 3 style control). Two questions per
pair: (1) is Light an acceptable light edit? (2) is Light clearly lighter than Strong?

| Pair | Transform · passage | (1) | (2) |
|---|---|---|---|
| S1 | tone · adventure-3 | N | N |
| S2 | tone · adventure-4 | N | Y |
| S3 | tone · gothic-1 | Y | Y |
| S4 | tone · gothic-2 | Y | Y |
| S5 | tone · gothic-4 | N | N |
| S6 | tone · tech-1 | Y | Y |
| S7 | age_adapt · adventure-1 (Light and Strong identical) | Y | N |
| S8 | age_adapt · adventure-2 | N | Y |
| S9 | age_adapt · adventure-3 | N | Y |
| S10 | age_adapt · gothic-1 | Y | Y |
| S11 | age_adapt · gothic-2 | Y | N |
| S12 | age_adapt · gothic-3 | Y | Y |
| S13 | style · adventure-2 (control) | Y | Y |
| S14 | style · adventure-3 (control) | N | Y |
| S15 | style · adventure-4 (control) | Y | Y |

Both yes: tone 3/6, age adaptation 2/6 (tone + age 5/12); style control 2/3. Acceptable alone: tone 3/6, age 4/6;
lighter alone: tone 4/6, age 4/6.

Existing rule (`owner-decision-guide.md` 2B): acceptable **and** lighter for most tone and age pairs → accepted-limitation
candidates; otherwise → technical work. **Result: FAIL — 5/12 pairs meet both; AWT-D, AWT-I (Critical) and AWT-1.2,
1.6, 3.7 (High) require technical work** (Gate 4 category 4). Not fixed during the review session (owner's instruction);
for the final analysis. The Tranche 2 box "Human — A15 Light thresholds" (60–100 labels) is not satisfied by this
15-pair sample and stays open.

### A2 — engineering follow-through (2026-10-05, owner instruction: fix what is technically fixable)

The labels showed the problem is measurable: of the profile measures, **new-word share** separated the owner's
judgements best — every accepted Light edit ≤ 0.438; above 0.45, 4 of the 6 rejected and none of the 9 accepted.
Fix (existing architecture): at Light, a rewrite over 0.45 is retried once with explicit feedback; the retry is kept
only if it is lighter and loses no character name; still too heavy → `strength_violation` (the amber note); requests
for something new are exempt. Re-measured with the A15 harness (12 passages × 3 transforms × 3 strengths × 5 runs):

| Light outputs over 0.45 new words | Before (v4) | After |
|---|---|---|
| Age adaptation | 21/41 (51%) | 6/43 (14%) |
| Tone | 13/40 (32%) | 8/40 (20%) |
| Style (control) | 11/45 (24%) | 9/39 (23%) |

Median new-word share at Light: age 0.471 → 0.304, tone 0.389 → 0.358 (Strong: 0.50, 0.48). **The A2 criterion stays
FAILED as recorded** — it is a human judgement on the outputs the owner saw; the fix needs human re-validation, which
this session did not ask for (owner's instruction). For tone, Strong often keeps the original and adds flourishes, so
Light is lighter by new words but not by kept words — a remaining weakness for that re-validation.

## A3–A6, G6–G8, 11.7, tabletop, UAT, multi-hour, translation, legal — not answered in this session

The owner stopped the interactive questionnaire (2026-10-05). A3 was presented (euphemism-1) and not answered;
nothing is recorded for it. Each item was checked for an objective resolution from existing evidence:

| Item | Objective resolution possible? | Status |
|---|---|---|
| A3 children's rewrite meaning | No — "same meaning" is the human reading the Tranche 2 box asks for | Open |
| A4 MV-5.14-D | No — the criterion is the owner's accept / accept + follow-up / reject per item | Open |
| A5 Story Bible semantic reading | No — citations prove a source exists, not that it supports the claim; a human reading is the requirement | Open |
| A6 5.15 interpretability, 7.12 style match, 5.10 author identity | No — author judgements by definition | Open |
| G6 / G7 / G8 usage reviews | No — usefulness and perceived workload | Open (or with UAT) |
| 7.3 single-step undo | **Yes** — an objective editor behaviour | **Closed by browser automation** (`frontend/tests/studio/undo.spec.ts`) |
| 11.7 saved author-style output review | Partly — automated: 0/15 living authors named, 0 obeyed; the box asks for the owner's review of the saved outputs | Open |
| Incident tabletop (MV-10.9) | No — an exercise run by the people on call | Open |
| UAT (9.6), multi-hour session (8.11) | No — real authors | Open |
| Translation (5.11) | No — a fluent speaker | Open |
| Legal (11.7) | No — legal counsel | Open |
