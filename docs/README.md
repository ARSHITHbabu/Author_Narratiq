# NarratIQ AI — Documentation

**NarratIQ AI** is a self-hosted, AI-powered studio for long-form fiction. It combines a chapter
editor with manuscript-scale story memory: retrieval-augmented plot assistance, character and
continuity intelligence, OCR and audio ingestion, and DOCX/PDF export. Every model runs on the
author's own hardware — Qwen2.5-7B-Instruct via vLLM, BGE-M3 embeddings in pgvector, GOT-OCR2.0,
faster-whisper. No manuscript text ever leaves the server.

This folder is organised **by document purpose**, not by file type. Folder names carry status:
`-completed` is delivered work, `-planned` is not built yet, `open/` needs action, `archive/` is
historical.

---

## Where things are

| Folder | Contains |
|---|---|
| [`specifications/`](./specifications/) | Source-of-truth product and feature specifications |
| [`phases/`](./phases/) | Per-phase delivery records and plans ([status overview](./phases/README.md)) |
| [`issues-and-bugs/`](./issues-and-bugs/) | Defect reports awaiting fixes ([workflow](./issues-and-bugs/README.md)) |
| [`testing/`](./testing/) | Manual test plans and QA checklists |
| [`incidents/`](./incidents/) | Post-incident reports for production outages |
| [`operations/`](./operations/) | Running, deploying and configuring the stack ([overview](./operations/README.md)) |
| [`archive/`](./archive/) | Superseded or completed-task documents, kept for history ([caveats](./archive/README.md)) |

---

## Project status at a glance

| Phase | Scope | Status |
|---|---|---|
| **Phase 1** | Editor, RAG, characters, OCR, notes, export | ✅ Complete |
| **Phase 2** | Manuscript intelligence (P2-01 … P2-11) | ✅ Complete |
| **Phase 3 — production hardening** | Rate limits, upload guards, concurrency, orphan recovery | ✅ Complete (see [`CLAUDE.md`](../CLAUDE.md)) |
| **Phase 3 — author-centric workflow** | Generation pins, partial regeneration, version compare (P3-01 … P3-11) | ⏳ **Design approved, not implemented** |

> Two different things are called "Phase 3". The **production hardening** work is finished and is
> documented in [`CLAUDE.md`](../CLAUDE.md). The **author-centric AI workflow** phase (P3-01 … P3-11)
> is a design specification only — no `P3-*` tables or migrations exist in the codebase yet.

---

## Completed work

- [Phase 1 — Production Implementation Report](./phases/phase-1-completed/phase-1-production-implementation-report.docx) — architecture, 19 tables, 17 features
- [Phase 1 — Status Update](./phases/phase-1-completed/phase-1-status-update.docx) — every v3 spec item vs. what shipped
- [Phase 2 — Intelligence Expansion Roadmap](./phases/phase-2-completed/phase-2-intelligence-expansion-roadmap.docx) — the P2-01 … P2-11 specification, all delivered
- [Author-Style & Copyright Risk features](./specifications/author-style-and-copyright-risk-features.md) — design + implementation reference

## Upcoming work

Everything below still needs action. Nothing here describes shipped behaviour.

- [Phase 3 — Author-Centric AI Workflow & Generation Management](./phases/phase-3-planned/phase-3-author-centric-ai-workflow.md) — **the next phase to build** (Markdown is the source of truth; a [Word copy](./phases/phase-3-planned/phase-3-author-centric-ai-workflow.docx) exists for review)
- [Phase 1 — AI Writing Tools QA Issues](./issues-and-bugs/open/phase-1-ai-writing-tools-qa-issues.docx) — author-voice preservation across the transform engine, plus a full UI/UX redesign recommendation
- [Phase 2 — Production Testing Issues](./issues-and-bugs/open/phase-2-production-testing-issues.docx) — 14 defects, several rated High (plot holes, continuity, continuation, voice agent)

## Open issues

- [Phase 1 identified issues](./issues-and-bugs/open/phase-1-ai-writing-tools-qa-issues.docx)
- [Phase 2 identified issues](./issues-and-bugs/open/phase-2-production-testing-issues.docx)

Also see the **Known Issues** summary in the [root README](../README.md#known-issues).

## Testing

- [Author feature test checklist](./testing/author-feature-test-checklist.docx) — one manual test per feature, covering editor, transforms, story intelligence, characters, ingestion and platform

## Incidents

- [RunPod port 3000 — 404 incident report](./incidents/runpod-port-3000-404-incident-report.md) (2026-07-24) — the app was healthy; ports 3000 and 8000 were never exposed on the pod. Markdown is the source of truth; a [Word copy](./incidents/runpod-port-3000-404-incident-report.docx) exists for sharing.

## Operations

- [How to run](./operations/how-to-run.md) — per-service startup and verification
- [RunPod deployment](./operations/runpod-deployment.md) — pod creation, storage, troubleshooting
- [RunPod environment variables](./operations/runpod-environment-variables.md) — which variables to set, precedence, and which stale ones break the app

## Archive

- [Technical Analysis Report v2](./archive/narratiq-ai-technical-analysis-report-v2.docx) — superseded by the Phase 1 Production Implementation Report
- [Documentation Recovery Changelog](./archive/documentation-recovery-changelog.md) — record of a completed one-off documentation task

---

## Recommended reading order for a new developer

1. [Root README](../README.md) — what the product is, quick start.
2. [`CLAUDE.md`](../CLAUDE.md) — architecture, service topology, config gotchas. The most accurate
   description of the system as it runs today.
3. [Product & technical documentation](./specifications/narratiq-ai-product-and-technical-documentation.docx) — the full product spec and feature inventory.
4. [Phase 1 Production Implementation Report](./phases/phase-1-completed/phase-1-production-implementation-report.docx) — how the foundation was actually built.
5. [Phase 2 Intelligence Expansion Roadmap](./phases/phase-2-completed/phase-2-intelligence-expansion-roadmap.docx) — the intelligence layer on top of it.
6. [Open issues](./issues-and-bugs/open/) — what is currently broken. Read before touching the AI
   transform or analysis pipelines.
7. [Phase 3 — Author-Centric AI Workflow](./phases/phase-3-planned/phase-3-author-centric-ai-workflow.md) — what is being built next.
8. [Operations](./operations/) — only when you need to deploy or debug the pod.

---

## Conventions

- Filenames are `lowercase-kebab-case`.
- Where a document exists as both `.md` and `.docx`, **the Markdown file is the source of truth** —
  the Word file is a generated copy for sharing and review. Both are kept together in one folder
  with the same base filename.
- Documents that are superseded move to [`archive/`](./archive/) rather than being deleted.
- `requirements*.txt` are dependency manifests, not documentation, and stay with the code.
