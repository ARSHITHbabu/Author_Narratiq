# Project Phases

One folder per delivery phase. The folder suffix is the status — `-completed` means shipped and
running in production, `-planned` means specified but not built.

| Folder | Phase | Status |
|---|---|---|
| [`phase-1-completed/`](./phase-1-completed/) | Manuscript platform — editor, RAG, characters, OCR, notes, export | ✅ Delivered |
| [`phase-2-completed/`](./phase-2-completed/) | Manuscript intelligence — P2-01 … P2-11 | ✅ Delivered |
| [`phase-3-planned/`](./phase-3-planned/) | Author-centric AI workflow & generation management — P3-01 … P3-11 | ⏳ Not implemented |

## Phase 1 — completed

- [`phase-1-production-implementation-report.docx`](./phase-1-completed/phase-1-production-implementation-report.docx)
  — the architecture reference for the v3.0.0 release: three-service stack, all 19 database tables,
  all 17 features, security and background-job architecture.
- [`phase-1-status-update.docx`](./phase-1-completed/phase-1-status-update.docx) — a feature-by-feature
  audit of the original v3 specification against what was actually delivered. Records the seven
  deliberate architecture upgrades (pgvector over Qdrant, PostgreSQL over SQLite, GOT-OCR2.0 over
  TrOCR + EasyOCR).

## Phase 2 — completed

- [`phase-2-intelligence-expansion-roadmap.docx`](./phase-2-completed/phase-2-intelligence-expansion-roadmap.docx)
  — the authoritative Phase 2 specification (emotional arc, continuation, duplicate scenes, style
  drift, voice check, story bible, outline, continuity, pacing, OCR inject, audio transcription).
  Every task in it has shipped; see [`CLAUDE.md`](../../CLAUDE.md) for the delivered endpoints.

Known defects found while testing this phase are **open** and live in
[`../issues-and-bugs/open/`](../issues-and-bugs/open/).

## Phase 3 — planned

- [`phase-3-author-centric-ai-workflow.md`](./phase-3-planned/phase-3-author-centric-ai-workflow.md)
  — **source of truth.** Eleven capabilities (P3-01 … P3-11) that make the generate → reject →
  regenerate loop lossless: generation pins, sentence-level locks, version comparison, preservation
  rules, lineage.
- [`phase-3-author-centric-ai-workflow.docx`](./phase-3-planned/phase-3-author-centric-ai-workflow.docx)
  — Word copy of the same content, for review outside the repository.

**Nothing in Phase 3 is implemented.** No `P3-*` tables exist in `backend/models.py` and no
corresponding Alembic migration exists. Treat the whole folder as forward-looking design.

> Not to be confused with the **Phase 3 production-hardening** work (rate limiting, upload guards,
> concurrency semaphores, orphan-job recovery), which *is* complete and is documented in
> [`CLAUDE.md`](../../CLAUDE.md).
