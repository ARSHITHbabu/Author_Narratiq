# NarratIQ AI — Documentation

**NarratIQ AI** is a self-hosted, AI-powered studio for long-form fiction. It combines a chapter
editor with manuscript-scale story memory: retrieval-augmented plot assistance, character and
continuity intelligence, OCR and audio ingestion, and DOCX/PDF export. Every model runs on the
author's own hardware — Qwen2.5-7B-Instruct via vLLM, BGE-M3 embeddings in pgvector, GOT-OCR2.0,
faster-whisper. No manuscript text ever leaves the server.

This folder is organised **by document purpose**, not by file type. Folder names carry status:
`-completed` is delivered work, `open/` needs action, `archive/` is historical. One exception:
`phases/phase-3-planned/` keeps its original name so existing links resolve, **but Phase 3 is
implemented** (Stage 7).

---

## Where things are

| Folder | Contains |
|---|---|
| [`specifications/`](./specifications/) | Source-of-truth product and feature specifications |
| [`phases/`](./phases/) | Per-phase delivery records and plans ([status overview](./phases/README.md)) |
| [`issues-and-bugs/`](./issues-and-bugs/) | Defect reports awaiting fixes ([workflow](./issues-and-bugs/README.md)) |
| [`testing/`](./testing/) | Test plans, regression and QA results, manual verification guides, performance baselines |
| [`policies/`](./policies/) | Published policies (data retention and deletion) |
| [`architecture/`](./architecture/) | Contributor guides for extending the system |
| [`incidents/`](./incidents/) | Post-incident reports for production outages |
| [`operations/`](./operations/) | Running, deploying and configuring the stack ([overview](./operations/README.md)) |
| [`archive/`](./archive/) | Superseded or completed-task documents, kept for history ([caveats](./archive/README.md)) |

---

## Project status at a glance

| Phase | Scope | Status |
|---|---|---|
| **Phase 1** | Editor, RAG, characters, OCR, notes, export | ✅ Complete |
| **Phase 2** | Manuscript intelligence (P2-01 … P2-11) | ✅ Complete |
| **Production Hardening** | Rate limits, upload guards, concurrency, orphan recovery | ✅ Complete (see [`CLAUDE.md`](../CLAUDE.md), "Production Hardening (completed)") |
| **Phase 3 — Author-Centric AI Workflow** | Generation pins, partial regeneration, version compare (P3-01 … P3-11) | ✅ Implemented in Stage 7 (migrations `0019`–`0022`); real-author UAT pending |
| **Stages 0–12** | The remaining-work programme: defects, retrieval, generation quality, tests, studio UI, regression, production readiness, documentation, release | In progress, see the [Master Implementation Checklist](./NarratIQ_Master_Implementation_Checklist.md) |

> **Naming.** "Phase 3" means only **Phase 3 — Author-Centric AI Workflow**. Older documents also used
> "Phase 3" for the **Production Hardening** pass (rate limits, upload guards, semaphores, orphan
> recovery), which is a separate, earlier piece of work. Read any "Phase 3 hardening" in an older or
> archived document as "Production Hardening".

---

## Completed work

- [Phase 1 — Production Implementation Report](./phases/phase-1-completed/phase-1-production-implementation-report.docx) — architecture, 19 tables, 17 features
- [Phase 1 — Status Update](./phases/phase-1-completed/phase-1-status-update.docx) — every v3 spec item vs. what shipped
- [Phase 2 — Intelligence Expansion Roadmap](./phases/phase-2-completed/phase-2-intelligence-expansion-roadmap.docx) — the P2-01 … P2-11 specification, all delivered
- [Phase 2 — Acceptance Record](./phases/phase-2-completed/phase-2-acceptance-record.md) and [Implementation Report](./phases/phase-2-completed/phase-2-implementation-report.md) — formal acceptance against roadmap §16, §19, §20 (task 11.6)
- [Phase 3 — Author-Centric AI Workflow](./phases/phase-3-planned/phase-3-author-centric-ai-workflow.md) — specification, implemented in Stage 7 (Markdown is the source of truth; a [Word copy](./phases/phase-3-planned/phase-3-author-centric-ai-workflow.docx) exists for review)
- [Author-Style & Copyright Risk features](./specifications/author-style-and-copyright-risk-features.md) — design + implementation reference
- [Product & Technical Documentation v5](./specifications/narratiq-ai-product-and-technical-documentation.md) — the whole product as shipped ([Word copy](./specifications/narratiq-ai-product-and-technical-documentation.docx))

## Remaining work

- [Master Implementation Checklist](./NarratIQ_Master_Implementation_Checklist.md) — the execution tracker for all remaining work, with evidence per task. The analysis behind its order is in the [Master Execution Plan](./NarratIQ_Master_Execution_Plan_and_Document_Implementation_Order.md).

## Open issues

- [Phase 1 identified issues](./issues-and-bugs/open/phase-1-ai-writing-tools-qa-issues.docx) — per-issue Stage 9 status in [`testing/stage-09-qa-rerun-results.md`](./testing/stage-09-qa-rerun-results.md)
- [OCR image-to-text failure](./issues-and-bugs/ocr-extraction-got-ocr2-dynamiccache-failure.md) — High; **fixed 2026-10-02** (Stage 12 A2), awaiting the product owner's review
- [Triage register](./issues-and-bugs/triage-register.md) — every reported issue with severity and release-blocking status (decision D-6)
- [Stage 9 security findings](./testing/stage-09-security-findings.md) — open dependency advisories and the prompt-injection finding

Reference: [Story Bible failure-path audit](./issues-and-bugs/story-bible-failure-path-audit.md) (Stage 3).

Resolved: [Phase 2 identified issues](./issues-and-bugs/resolved/phase-2-production-testing-issues.docx) — all 14 fixed and re-verified 2026-09-27.

Also see the **Known Issues** summary in the [root README](../README.md#known-issues).

## Testing

- [Author feature test checklist](./testing/author-feature-test-checklist.docx) — one manual test per feature, covering editor, transforms, story intelligence, characters, ingestion and platform
- [Stage manual verification guides](./testing/manual-verification/) — per-stage lists of checks that need the pod, a browser or the author, with exact steps ([Stage 2](./testing/manual-verification/stage-02-manual-verification-guide.md), [Stage 5](./testing/manual-verification/stage-05-manual-verification-guide.md), [Stage 8](./testing/manual-verification/stage-08-manual-verification-guide.md), [Stage 10](./testing/manual-verification/stage-10-manual-verification-guide.md))
- [Automation matrix](./testing/author-feature-checklist-automation-matrix.md) and [issue-to-test traceability](./testing/issue-to-test-traceability.md) — which automated test covers which checklist row and issue
- Stage 9: [regression results](./testing/stage-09-regression-results.md), [QA re-run](./testing/stage-09-qa-rerun-results.md), [security findings](./testing/stage-09-security-findings.md), [UAT guide](./testing/stage-09-uat-guide.md)
- Stage 11 evidence ([`testing/stage-11/`](./testing/stage-11/)):
  - Phase 2 acceptance and 200-chapter scale probes
  - prompt-injection probes before and after the fix, the defence-design experiments, and legitimate-rewrite comparisons with the guard on and off
  - the verified vLLM launch arguments
- Stage 12 remediation evidence ([`testing/stage-12/`](./testing/stage-12/)):
  - Tranche 2: prompt-injection, clean-prose and legitimate-rewrite probes, plus the A18 output-check baselines
  - Tranche 3 ([`testing/stage-12/tranche3/`](./testing/stage-12/tranche3/)): security re-measurement (A19), the MV-5.14 live audit (A20), the Gate 1/2/7 revalidation (A24)
  - Stage 12.1 release gate verification ([`testing/stage-12/stage-12.1/gate-results.md`](./testing/stage-12/stage-12.1/gate-results.md)): per-gate results, the 114-issue matrix, security audits, the Gate 3b human review package, draft waivers
- [Performance baselines](./testing/performance-baselines.md) — latency targets and measurements (raw data in [`testing/performance/`](./testing/performance/))

## Incidents

- [RunPod port 3000 — 404 incident report](./incidents/runpod-port-3000-404-incident-report.md) (2026-07-24) — the app was healthy; ports 3000 and 8000 were never exposed on the pod. Markdown is the source of truth; a [Word copy](./incidents/runpod-port-3000-404-incident-report.docx) exists for sharing.
- [Database row-count discrepancy](./incidents/2026-09-22-database-row-count-discrepancy.md) (2026-09-22)
- [Postmortem template](./incidents/TEMPLATE.md) — used by the [incident response process](./operations/incident-response.md)

## Operations

- [How to run](./operations/how-to-run.md) — per-service startup and verification
- [RunPod deployment](./operations/runpod-deployment.md) — pod creation, storage, troubleshooting
- [RunPod environment variables](./operations/runpod-environment-variables.md) — which variables to set, precedence, and which stale ones break the app
- Production runbooks (Stage 10): [backup and restore](./operations/backup-and-restore.md), [monitoring and alerting](./operations/monitoring-and-alerting.md), [incident response](./operations/incident-response.md), [rollback](./operations/rollback.md), [model versions](./operations/model-versions.md), [capacity planning](./operations/capacity-planning.md), [containers](./operations/containers.md), [storage and persistence](./operations/storage-and-persistence.md)
- [Data retention and deletion policy](./policies/data-retention-and-deletion.md)

## Architecture guides

- [Adding a studio tool](./architecture/adding-a-studio-tool.md) — one registry row per new tool

## Archive

- [Technical Analysis Report v2](./archive/narratiq-ai-technical-analysis-report-v2.docx) — superseded by the Phase 1 Production Implementation Report
- [Documentation Recovery Changelog](./archive/documentation-recovery-changelog.md) — record of a completed one-off documentation task

---

## Recommended reading order for a new developer

1. [Root README](../README.md) — what the product is, quick start.
2. [`CLAUDE.md`](../CLAUDE.md) — architecture, service topology, config gotchas. The most accurate
   description of the system as it runs today.
3. [Product & technical documentation v5](./specifications/narratiq-ai-product-and-technical-documentation.md) — the full product spec and feature inventory.
4. [Phase 1 Production Implementation Report](./phases/phase-1-completed/phase-1-production-implementation-report.docx) — how the foundation was actually built.
5. [Phase 2 Intelligence Expansion Roadmap](./phases/phase-2-completed/phase-2-intelligence-expansion-roadmap.docx) — the intelligence layer on top of it.
6. [Triage register](./issues-and-bugs/triage-register.md) and the root README's Known Issues — what is
   currently broken. Read before touching the AI transform or analysis pipelines.
7. [Phase 3 — Author-Centric AI Workflow](./phases/phase-3-planned/phase-3-author-centric-ai-workflow.md) — the generation-management layer (implemented in Stage 7).
8. [Operations](./operations/) — only when you need to deploy or debug the pod.

---

## Conventions

- Filenames are `lowercase-kebab-case`.
- Where a document exists as both `.md` and `.docx`, **the Markdown file is the source of truth** —
  the Word file is a generated copy for sharing and review. Both are kept together in one folder
  with the same base filename. **Never edit the Word copy by hand.** See "Regenerating Word copies"
  below.
- Documents that are superseded move to [`archive/`](./archive/) rather than being deleted.
- `requirements*.txt` are dependency manifests, not documentation, and stay with the code.

### Regenerating Word copies

Managed `.md` → `.docx` pairs are listed in [`generated-docs.json`](./generated-docs.json), which also
records the SHA-256 of each Markdown source as of its last regeneration. After editing a managed
Markdown file:

```bash
make docs          # regenerate every Word copy with pandoc and refresh the recorded hashes
make docs-check    # exit 1 if any Markdown source changed without regenerating its Word copy
```

`make docs` needs **pandoc 3.7.0.2**. It uses `$PANDOC` if set, then `pandoc` on `PATH`, then
`/workspace/tools/pandoc-3.7.0.2/bin/pandoc`. To install it (Linux amd64, no root needed):

```bash
mkdir -p /workspace/tools && cd /workspace/tools
curl -fsSL -O https://github.com/jgm/pandoc/releases/download/3.7.0.2/pandoc-3.7.0.2-linux-amd64.tar.gz
sha256sum pandoc-3.7.0.2-linux-amd64.tar.gz   # expect 8f8f67fdd540b6519326b0ac49d5c55c5d5d15e43920e80a086e02c8aff83268
tar xzf pandoc-3.7.0.2-linux-amd64.tar.gz
```

`make docs-check` needs only Python and runs as the `docs-sync` suite of
`backend/tests/run_full_regression.sh`. CI is deferred (task 6.1), so until it exists this local suite
is the gate. To add a new pair, add its entry to `generated-docs.json` and run `make docs`.
