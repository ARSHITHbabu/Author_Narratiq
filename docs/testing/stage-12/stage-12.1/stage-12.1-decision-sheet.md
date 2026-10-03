# Stage 12.1 — consolidated owner decision sheet

Prepared 2026-10-03 from evidence already recorded. **No answer is filled in for you.** Decisions already given (Section 1 = 4.9 Option B; 2E fix = done; 2F translation stays open; AWT-G direction) are in `owner-decisions.md` and are not asked again.

Each line below is one judgement. Where one judgement decides several Gate 4 issues, they are grouped. For every group the three possible answers mean:
- **accept**: you judge the quality acceptable for release. The issues close as owner-accepted.
- **defer**: no judgement now. The issues stay open, and Gate 4 / 3b stay not passed.
- **reject "…"**: you name what is wrong. Engineering then treats it as a defect (category 4).

---

## A. Gate 3b human quality reviews (material in `gate3b-review/`, unchanged)

| # | Judgement | Material | Decides | Reply format |
|---|---|---|---|---|
| A1 | **2A blind rewrite review** (MV-5.BR): for each of 12 passages, which rewrite is better? | `gate3b-review/blind-review.md` (do **not** open `blind-review-KEY.json`) | the Stage 5 line "Blind author review passed"; Gate 3b; G3 = AWT-A, B, E, F, H, J (Critical) and 22 High (tone 1.1/1.3/1.4/1.5, emotion 2.1/2.2/2.3/2.6/2.7, audience 3.1/3.2/3.3/3.5, style 4.1/4.2/4.4–4.10) | `Blind: 1=A 2=N 3=B … 12=…`, then `G3=accept / defer / reject "…"` |
| A2 | **2B Light vs Strong**: is Light an acceptable light edit, and is it clearly lighter? 15 pairs | `gate3b-review/a15-sample-light-vs-strong.md` | G1 = AWT-D, AWT-I (Critical); AWT-1.2, 1.6, 3.7 (High) | `Light: S1=yes/no,yes/no … S15=…`, or `G1=defer` |
| A3 | **2C children's rewrites**: meaning kept? appropriate? 16 rewrites | `gate3b-review/children-sample.md` (full set: `children-meaning-review.md`) | the Tranche 2 item "children's rewrite meaning review"; with A1, the audience items AWT-3.1/3.2/3.3/3.5 | `Children: all yes` or list the "no"s, or `defer` |
| A4 | **2D MV-5.14-D**: accept 5.14's three Story Audit items | evidence table in `owner-decision-guide.md` §2D | 5.14; G5 = AUDIT-C1–C5 (Critical), AUDIT-H6–H10 (High) | `MV-5.14-D: C4=accept / accept+follow-up "…" / reject "…"; C5=…; M11=…`, then `G5=accept / defer` |
| A5 | **Story Bible semantic reading**: "never asserts unsupported facts" (Gate 2 phase text). The copied-example defect is fixed (0 leaks in 10 × 5 sections). The semantic reading of a real bible is still yours | Generate a bible on a story you know; read themes most closely (A24: themes 7/11 entries cited) | the Gate 2 / 3b Story Bible line | `Story Bible: no unsupported facts`, or a list, or `defer` |
| A6 | **MV-5.AR**: the per-task author-review boxes 5.7, 5.10, 5.13, 5.15, 5.16 (5.11 is translation, which stays open) | each task's own text in the checklist | those boxes | `MV-5.AR: accept / defer` (per task if mixed) |

## B. Known-limitation decisions (not accepted on your behalf)

| # | Issue | Measured facts | If accepted | If not accepted |
|---|---|---|---|---|
| B1 | **AWT-G** (Critical), run-to-run consistency | 120 transforms (12 scenarios × 10). Mean stdev **0.0866** against the **0.0643** baseline: **criterion not met**. The variability is concentrated in the borderline unchanged-vs-rewrite decision (19/20, 15/20, 3/20 on identical input); rewrites themselves are stable (0.031). The author must press Replace, so nothing is applied unseen. No caching or other metric workaround, by your direction | Documented known limitation: "the same request can return 'already suitable' on one run and a rewrite on the next" | Stays an open Critical. Gate 4 cannot pass. The only real lever is model/serving work (a different model or a deterministic decoding path), which is a separate project |
| B2 | **CAST-H6** (High), role classification | A reluctant ally is labelled antagonist 11/25 (44 %). The general role-definition prompt made it worse (22/25) and was reverted. Roles are editable; an invalid role falls back to "supporting" | Documented limitation: "AI-suggested roles can be wrong for morally ambiguous characters; review them" | Stays open. The next step would be non-prompt work (e.g. a role-evidence check), which is new design |
| B3 | **PA-C6** (Critical), context prioritisation | 40-chapter manuscript, 12 scenarios, production path. **Critical evidence reaches the model** 12/12, and 11/12 after a re-index. **Ranked above every decoy:** only 7/12 and 6/12 (capped scope 8/12), so **criterion not met**. Cause: **BGE-M3 semantic similarity** (decoys share more words with the question; production order follows cosine order); **no deterministic NarratIQ code defect** found. A summary-blend weighting was measured offline (partial, non-monotonic gains) and **not implemented**: picking a weight would be fitting the fixture | Documented limitation: "the assistant receives the right passage, but not always first; a similar-sounding passage can outrank it" | Stays open. The next step would be a retrieval-design change (re-ranker, query expansion or summary blend), measured on a **second, held-out** manuscript |
| B4 | **PA-H12** (High), minor vs major events | 1/2 abstract "what major thing did X do" scenarios pass. For Liesel Marr, the poisoning passage is not in the top 40 by similarity | as B3 | as B3 |

Reply: `B1=accept / not accepted; B2=…; B3=…; B4=…`

## C. Suggestions, Plot Assistant and UI reviews (G6 / G7 / G8)

The technical causes found in these groups are fixed (SUG-H9; Plot Assistant scope accessibility and test, Stage 12.1). What is left is one judgement per group, made by using the feature on a real manuscript.

| # | Judgement | Issues decided | Evidence already in hand | Reply |
|---|---|---|---|---|
| C1 | **Suggestions read like a developmental editor** (5.13 author review): actionable, not praise, not generic, not repetitive | SUG-C1, C2 (Critical); SUG-H3, H4, H5, H6, H7, H8, H10, H11 (High) | praise-only and empty items filtered (tests); in-response duplicates removed; recall 0.933 on the keyword-proxy harness; 11 distinct categories | `G6=accept / defer / reject "…"` |
| C2 | **Plot Assistant answers are sound on your manuscript**: whole-story understanding, character continuity, arcs, summaries | PA-C1, PA-C9 (Critical); PA-H10, H11, H13 (High) | D-1 scope: studio test, plus the live 4.1 check 3/3 (chapter scope stayed in Chapter 1; full scope reached Chapters 2–3); the creative-intent evidence metadata was fixed; long-manuscript coverage: revelations in summaries 4/7 (truncation defect fixed), character coverage 3/3, 4/6, 4/5; broad questions reach chapters across the book | `G7=accept / defer / reject "…"` |
| C3 | **The Studio UI is focused and not congested** (MV-8.5 steps 1–4; 8.3 / 8.4 / 8.5 author reviews) | UI-C1, C2, C6 (Critical); UI-H9, H10, H11, H13, H14 (High) | progressive disclosure −34 % / −25 % controls; Focus / Zen / Reading / Draft modes tested; every tool reachable from the palette; axe 0 serious/critical | `G8=accept / defer / reject "…"` |

## D. Gate 5, 6 and 8 owner decisions (from `owner-decision-guide.md` §4–6)

| # | Decision | Reply |
|---|---|---|
| D1 | Security residual risks S1–S6 (S2 already accepted 2026-10-02; confirm) | `S1=…; S2=…; S3=…; S4=…; S5=…; S6=…` |
| D2 | Rollback past `0027` loses presence labels only (55/57 tables byte-identical; no manuscript data lost): does this satisfy 10.5's "without data loss"? | `Rollback presence loss: accept / require data-preserving downgrade` |
| D3 | Real-author UAT (9.6) | `UAT: run before release / release without UAT (decision) / defer` |

## E. Waivers (drafts: `draft-waivers.md`)

| # | Waiver | Technical risk statement | Reply |
|---|---|---|---|
| W-1 | CI | low data risk | `accept / reject` (+ conditions) |
| W-2 | Docker / MV-10.3 (PG-04) | low; operational only | `accept / reject` |
| W-3 | Off-pod backup ⚠ | **not technically safe to defer once real author data is present** | `accept / reject` (+ conditions) |
| W-4 | Alerts to a person | moderate | `accept / reject` (+ manual check routine) |
| W-5 | `SECRET_KEY` in a team store | very low; a 2-minute owner action closes it | `closed (copied) / accept / reject` |

## F. Stays open whatever you answer (cannot be completed truthfully now)

- **Fluent-speaker translation review:** AWT-5.1–5.7; task 5.11 (your 2F decision).
- **Real-author UAT:** 9.6; PA-H14.
- **The multi-hour author session:** 8.11; UI-H12; MV-8.7.
- **Legal review of the copyright-risk disclaimer:** 11.7.
- **External infrastructure:** CI (6.1), the Docker build, off-pod backup and person-delivered alerting, unless you waive them (E). A waiver records a decision; it does not make the item done.
- **Owner data-retention decision:** telling intentional deletion apart from data loss at startup.
- **Follow-ups:** the injection-probe coverage follow-up; the 4.9 relationship-accuracy follow-up.

## How your answers turn into the checklist

- **Gate 3b:** passes only if A1 passes and A2–A6 are accepted, or explicitly waived.
- **Gate 4:** needs every Critical closed (fixed or owner-accepted) and every High fixed or accepted. With F open, AWT-5.x, PA-H14 and UI-H12 keep Gate 4 open unless you accept them.
- **Gates 5 and 8:** need D1, and D2 / W-2.
- **Gate 6:** needs W-1 and D3.
- Every box is ticked only where it is evidenced or has an explicit decision. Everything else is left open and named in the closure report.
