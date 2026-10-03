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

### Applied to the checklist (2026-10-03, Stage 12.1 technical reconciliation, on the owner's instruction)

- Section 1 Option B: the 4.9 relationship-extraction item is ticked as not applicable.
- The 4.1 box is ticked.
- The 3.10 OCR manual journey is ticked on the same standard (live browser spec `ocr-to-editor.spec.ts`, 2/2). **This applies the 4.1 standard by analogy**; the owner may reverse it.
- Every other pending decision (2A–2D, Story Bible semantic reading, B1–B4, G6–G8, S1–S6, rollback presence loss, UAT, W-1–W-5, deletion vs loss) is **not** applied. See `stage-12.1-final-decision-package.md`.
