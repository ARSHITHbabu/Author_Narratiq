# Archive

Documents that are **no longer the source of truth** but are kept for history. Nothing here should
be used to make a decision about the current system — check the active folders first.

| Document | Why it is archived |
|---|---|
| [`narratiq-ai-technical-analysis-report-v2.docx`](./narratiq-ai-technical-analysis-report-v2.docx) | Analysis v2.0 (June 2026). Explicitly superseded by the [Phase 1 Production Implementation Report](../phases/phase-1-completed/phase-1-production-implementation-report.docx). Its "outstanding gaps" — hardcoded secret key, SQLite, numpy cosine, missing OCR cleanup — have all since been closed. Useful only as a record of where the project stood mid-Phase-1. |
| [`documentation-recovery-changelog.md`](./documentation-recovery-changelog.md) | Record of a completed one-off task: the documentation rewrite performed at commit `9827587`. The task is finished, so the changelog is history rather than guidance. Its deliverable, [`runpod-environment-variables.md`](../operations/runpod-environment-variables.md), is still active. |

## ⚠️ File paths inside archived documents are stale

Archived documents reference the **pre-reorganisation** repository layout — for example
`RUNPOD_DEPLOYMENT.md` at the repository root, or `docs/RUNPOD_ENVIRONMENT_VARIABLE_RECOVERY.md`.
Those paths were deliberately **not** rewritten: an archived record should say what it said when it
was written. Use this mapping when following a reference out of an archived document:

| Path in archived document | Current path |
|---|---|
| `HOW_TO_RUN.md` | [`docs/operations/how-to-run.md`](../operations/how-to-run.md) |
| `RUNPOD_DEPLOYMENT.md` | [`docs/operations/runpod-deployment.md`](../operations/runpod-deployment.md) |
| `docs/RUNPOD_ENVIRONMENT_VARIABLE_RECOVERY.md` | [`docs/operations/runpod-environment-variables.md`](../operations/runpod-environment-variables.md) |
| `issues_i_found_phase1.docx` | [`docs/issues-and-bugs/open/phase-1-ai-writing-tools-qa-issues.docx`](../issues-and-bugs/open/phase-1-ai-writing-tools-qa-issues.docx) |
| `issues_i_found_phase2.docx` | [`docs/issues-and-bugs/open/phase-2-production-testing-issues.docx`](../issues-and-bugs/open/phase-2-production-testing-issues.docx) |
| `NarratIQ_AI_Production_Implementation_Report.docx` | [`docs/phases/phase-1-completed/phase-1-production-implementation-report.docx`](../phases/phase-1-completed/phase-1-production-implementation-report.docx) |
| `NarratIQ_AI_Documentation_v3_Phase1_Status_Update.docx` | [`docs/phases/phase-1-completed/phase-1-status-update.docx`](../phases/phase-1-completed/phase-1-status-update.docx) |
| `NarratIQ_AI_Phase2_Intelligence_Expansion_Roadmap.docx` | [`docs/phases/phase-2-completed/phase-2-intelligence-expansion-roadmap.docx`](../phases/phase-2-completed/phase-2-intelligence-expansion-roadmap.docx) |
| `NarratIQ_AI_Documentation_v3.docx` | [`docs/specifications/narratiq-ai-product-and-technical-documentation.docx`](../specifications/narratiq-ai-product-and-technical-documentation.docx) |
| `NarratIQ_AI_Analysis_Report.docx` | [`docs/archive/narratiq-ai-technical-analysis-report-v2.docx`](./narratiq-ai-technical-analysis-report-v2.docx) |
| `NarratIQ_Project_Recovery_Report.docx` | **Not in this repository** — referenced by older documents but never committed |

## Rules

- Archive, do not delete. Superseded documents still explain *why* decisions were made.
- Anything moved here must be listed in the table above with a reason.
