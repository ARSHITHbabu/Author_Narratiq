# Stage 12.1 — owner decisions recorded (not yet applied to the checklist)

Decisions given by the product owner in the Stage 12.1 owner review. The checklist will be updated only at Stage 12.1's completion approval.

## 2026-10-03

### Section 1 — Gate 3a / task 4.9 "Fix relationship extraction errors": **Option B**

- **Accepted as NOT APPLICABLE** to the current product requirement. NarratIQ contains **no AI relationship-extraction pipeline that creates relationship records**: relationship records are author-created; `run_p24_relationship_intel` only analyses an existing one.
- **Recorded separately; neither is an AI relationship-extraction pipeline:**
  - **A11 family-claim grounding** (Tranche 2): a kinship claim in a generated character description must be supported by the text near that character's name.
  - **`relationship_changes` / Manuscript Report Relationships section:** the chapter summariser records per-chapter relationship changes, shown in chronological order (MV-5.14-C).
- **Post-release follow-up (does not block Gate 3a for this release unless another existing release criterion independently requires it):** *"Measure the accuracy of relationship statements appearing in AI-generated character descriptions against manuscript evidence, including non-family relationships."*
- CAST-H8 follows this decision.

### Section 2E — Story Bible copied example World Rule: **fix now**

"Lattice sessions require an induction collar [Ch 1]" is unsupported by the fixture manuscript and comes from the prompt example. The owner classifies it as **a real technical hallucination defect, not a quality judgement**. Fix with the Stage 4.16 approach; the acceptance criterion is not weakened.

### Section 2F — Translation

- **Not** accepted as a known limitation; **not** reclassified out of release-blocking.
- **The fluent-speaker review requirement stays open.**
- Recorded: the current French evidence (`../tranche3/legit-rewrite-probe-tranche3.json`) already shows **apparent language-quality problems that need fluent review**: "le console", "la navire", "chuchora", "l'cloche", "l'orchard", "je ferai", "chapel" → "église".
- No broad translation prompt changes until the fluent-speaker judgement exists.

### Sections 2A / 2B / 2C / 2D — **pending**

The blind review, the Light-vs-Strong labels, the children's rewrite labels and MV-5.14-D are still with the owner. The prepared review material in `gate3b-review/` is preserved unchanged.

### AWT-G — owner direction

See `awt-g-consistency.md`. Criterion **not met**; model variability; no metric-improving workaround.

### Task 4.1 manual box — **TICK** (owner, 2026-10-03)

The live automated browser verification (`tests/browser/plot-assistant-scope.spec.ts`, 3/3) directly exercised the intended behaviour and is sufficient evidence for the item.

## 2026-10-05

### S1 — residual prompt-injection risk: **ACCEPTED RESIDUAL RISK**

Owner, verbatim: *"I accept S1 as ACCEPTED RESIDUAL RISK based on the post-fix evidence."* Given after the Stage 12.2
remediation of chapter-scoped story Q&A (`docs/testing/stage-12/stage-12.2/injection-coverage.md` §4: Plot Assistant
default request 9/12 hijacked → 0/12, voice 12/12 → 0/12; 0 obeyed in 72 adversarial runs; clean prose 60/60). Not to
be re-presented unless new evidence changes it. Applied: the Tranche 2 "Owner — A18 residual prompt-injection risk"
box is ticked. **No other decision is inferred from it:** S2–S6, D1/D3, 11.7 (legal and the owner's review of the
saved author-style outputs) and every other package item stay open.

### Stage 12.3 preparation — owner decisions (2026-10-05, with APPROVE IMPLEMENTATION for the technical 12.3 preparation)

Recorded as given. **No other decision is inferred.**

| Item | Decision | Recorded meaning |
|---|---|---|
| **B1 AWT-G** | **ACCEPT** | Run-to-run variability accepted as a known limitation. The measured criterion stays **NOT MET** (mean stdev 0.0866 vs the 0.0643 baseline); never rewritten as a pass |
| **B2 CAST-H6** | **ACCEPT** | Reluctant-ally role-classification variability (antagonist 11/25) accepted as a known limitation |
| **B3 PA-C6** | **ACCEPT + FOLLOW-UP** | Retrieval ordering accepted for this release; measured result preserved (critical passage delivered 12/12, ranked above every decoy 7/12). Post-release follow-up: retrieval design measured on a held-out manuscript |
| **B4 PA-H12** | **ACCEPT + FOLLOW-UP** | Broad "major event" retrieval limitation (1/2) accepted for this release; part of the same follow-up |
| **S2** | **CONFIRM** | The vLLM 0.9.2 advisory acceptance (2 Critical / 10 High in the vLLM stack; xgrammar 2 High; transformers 4 High) stands **while vLLM is bound only to 127.0.0.1** |
| **S3** | **ACCEPT** | transformers ×4 and ecdsa (requirements, High): unreachable execution paths as documented |
| **S4** | **ACCEPT + FOLLOW-UP** | lxml XXE (proven unreachable by test), urllib3 ×6, soupsieve ×2 accepted; dependency hygiene upgrades are a post-release follow-up |
| **S5** | **ACCEPT + FOLLOW-UP** | RunPod-image Jupyter stack (2 Critical / 33 High; 403 without auth) accepted for this release; removing Jupyter from the future pod template is an external follow-up |
| **S6** | **ACCEPT** | npm postcss (production, build time) and braces (dev) accepted as build-time-only risk |
| **Presence** | **ACCEPT** | Rolling back past migration `0027` loses `characters.presence` labels. **Rollback is not completely lossless**; this exception stays documented |
| **W-1 CI** | **WAIVE WITH CONDITION** | Valid for a release only if the complete regression suite is run and recorded against that exact release candidate/commit — for every release until CI exists |
| **W-2 Docker** | **WAIVE** | While RunPod is the only supported deployment target |
| **W-4 alerts** | **WAIVE + DAILY MANUAL CHECK** | A documented daily manual operational check is required until alert delivery exists |
| **W-3 off-pod backup** | **NOT WAIVED for real author data** | **Hard condition:** no real author manuscripts or data may be accepted or stored in production until an approved off-pod destination exists and at least one off-pod restore has been verified. No provider configured |
| **W-5 SECRET_KEY copy** | **OPEN** | Until the owner personally confirms the key is copied to a separate secret store |
| **Deletion vs data loss at startup** | **No permanent decision yet** | The two synthetic backup sets on pod `55zfw2ol0sx1gi` are preserved; the guard is not weakened |

**Still open, explicitly not inferred:** A1 blind review; A2 Light vs Strong; A3 children's rewrite meaning; A4
MV-5.14-D (no earlier explicit decision covers it); A5 Story Bible semantic review; A6 author reviews; G6 Suggestions;
G7 Plot Assistant; G8 Studio UI; real-author UAT; the multi-hour writing session; the fluent-speaker translation
review; the legal review; the 11.7 saved author-style output review; the 7.3 undo browser re-check; the tabletop
exercise; W-5; the MV-10.8 onboarding limit.

### Applied to the checklist (2026-10-03, Stage 12.1 technical reconciliation, on the owner's instruction)

- Section 1 Option B: the 4.9 relationship-extraction item is ticked as not applicable.
- The 4.1 box is ticked.
- The 3.10 OCR manual journey is ticked on the same standard (live browser spec `ocr-to-editor.spec.ts`, 2/2). **This applies the 4.1 standard by analogy**; the owner may reverse it.
- Every other pending decision (2A–2D, Story Bible semantic reading, B1–B4, G6–G8, S1–S6, rollback presence loss, UAT, W-1–W-5, deletion vs loss) is **not** applied. See `stage-12.1-final-decision-package.md`.

## 2026-10-06 — owner decisions OD-01 – OD-20 (Owner Decision Package), OD-21 blocked

Given by the product owner in writing (chat, 2026-10-06), transcribed into
`docs/testing/stage-12/stage-12.3/review-packages/NarratIQ_Owner_Decision_Package.docx`.

| ID | Decision |
|---|---|
| OD-01 | **B** — the three partial MV-5.14-D items accepted with follow-up (known limitations). Not unconditional acceptance of every Story Audit defect: the G5 issues are decided issue by issue from HR-09; any Major/Blocking stays open unless separately accepted |
| OD-02 | **A** — all 30 post-launch issues accepted as deferred post-launch Medium issues; not blocking; preserved as the backlog; never shown as fixed |
| OD-03 | **A** — latency accepted as meeting the supported production envelope; the ~50 % Tier-2 search tail is an accepted known limitation, recorded, never claimed absent |
| OD-04 | **A** — envelope ~60 active per pod, ~150–200 registered, < 10 % simultaneous Tier-2; initial envelope, not an unlimited claim; growth needs capacity and revalidation |
| OD-05 | **B** — operator `.disposable` marker per backup set; implemented as designed; startup data-loss protection not weakened |
| OD-06 | **B** — the final known-issues list needs the owner's confirmation before its box is ticked; engineering builds the reconciled list from recorded decisions, residual risks, limitations, deferred Mediums and the human review |
| OD-07 | **A** — the Stage 12.1 decision-package box closes automatically once every constituent item is recorded |
| OD-08 | **B** — "AI quality improvement demonstrated" closes only after the current human re-validation and Gate 3b evidence support it |
| OD-09 | **A** — restore Writing Suggestions as an accessible Studio tool; then HR-11 against it |
| OD-10 | **A** — the 6.5 regression alarm rule approved as implemented and verified (agreed threshold) |
| OD-11 | **A** — G3 per-issue closure (Critical: HR-05 Accept and no tagged Blocking; High: transform summary Accept and no tagged Blocking) |
| OD-12 | **A** — HR-06 exactly 6/12 = FAIL |
| OD-13 | **A** — Light warning/retry threshold derived from the HR-07 labels |
| OD-14 | **A** — children's meaning strict: every item Kept |
| OD-15 / OD-16 / OD-18 | **A** — None/Minor close; Major/Blocking stay open (G5, G6 — Suggestions must be reachable — and G8) |
| OD-17 | **A** — Plot Assistant: Correct passes; Partly correct only if incomplete but accurate; contradiction / Incorrect / Invented fail |
| OD-19 | **A** ×3 — 5.15 Partly allowed with a note; 7.12 "closely" beats Off in ≥ 2 of 3 chapters; 5.10 summary governs, every 1–2 rating surfaced |
| OD-20 | **A** — Possible imitation goes to legal counsel (pending, not a pass); Clear imitation fails |
| OD-21 | **Not approved yet — prerequisites not complete** (explicitly not a rejection). Release sign-off stays blocked; nothing signed |

The owner also authorised the implementation agent to perform the human reviews HR-01 – HR-21 and record the
answers. Recording agent-produced answers in the Human Review Package was **blocked by the agent environment's
permission check** on 2026-10-06; no human-review answer has been recorded, and the owner was asked how to proceed.
