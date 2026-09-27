# Issues and Bugs

Defect reports produced by manual QA and production testing. These describe **problems that still
need action** — they are not implementation records. Completed work belongs in
[`../phases/`](../phases/).

## Status folders

| Folder | Meaning |
|---|---|
| [`open/`](./open/) | Reported, not yet fixed or not yet verified as fixed |
| [`resolved/`](./resolved/) | Closed out and re-verified; the fixing commit is recorded in the triage register |

## Triage register

[`triage-register.md`](./triage-register.md) — the reconciliation of both reports below against the
execution checklist (`docs/NarratIQ_Master_Implementation_Checklist.md`, task 0.9): every issue's
severity, owning checklist task, and proposed release-blocking / post-launch / won't-fix
classification. Produced 2026-09-21.

## Open

### [`open/phase-1-ai-writing-tools-qa-issues.docx`](./open/phase-1-ai-writing-tools-qa-issues.docx)

Consolidated QA report on the AI writing tools. Roughly 40 issues grouped by transform category —
tone, emotion, audience adaptation, style — plus a UI/UX assessment.

The recurring theme is one root problem: **the transform engine rewrites instead of adjusting**, so
the author's voice, subtext and stylistic choices are replaced with generic AI prose. There is no
minimal-change or preservation mode. The report closes with a recommendation to redesign the author
workspace around a writing-first workflow rather than patching the right-hand panel.

Directly relevant to [Phase 3](../phases/phase-3-planned/), which specifies preservation rules and
sentence-level locks as the fix.

Also open, outside the two reports: [`ocr-extraction-got-ocr2-dynamiccache-failure.md`](./ocr-extraction-got-ocr2-dynamiccache-failure.md)
(High — OCR image-to-text inference fails; the upload interface itself, Phase 2 Issue 6, is fixed).

## Resolved

### [`resolved/phase-2-production-testing-issues.docx`](./resolved/phase-2-production-testing-issues.docx)

Fourteen defects found during production testing of the Phase 2 intelligence features. All 14 are
fixed, and all 14 were re-verified on 2026-09-27 (Stage 9 task 9.2). The fixing commit and the test
evidence for each issue are in the Phase 2 table of [`triage-register.md`](./triage-register.md); the
run itself is in [`../testing/stage-09-qa-rerun-results.md`](../testing/stage-09-qa-rerun-results.md).
(Earlier text here said Issues 2, 12, 13 and 14 shared one root cause. Stage 3 found two: 12 and 13
were a call-signature bug in `writing_tools.py`; 2 and 14 were unvalidated AI output.)

## Adding a new report

1. Name it `phase-<n>-<topic>.docx` or `<topic>-issues.md` in `lowercase-kebab-case`.
2. Put it in `open/`.
3. Add a short entry to this file describing scope and severity.
4. When every issue in it is fixed and re-verified, move it to `resolved/` and record each fixing
   commit in the triage register — do not delete it.
