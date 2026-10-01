# Project Phases

One folder per delivery phase. The folder suffix records the status when the folder was created:
`-completed` means shipped. **`phase-3-planned/` is the exception.** Its name is historical and kept so
existing links resolve; Phase 3 was implemented in Stage 7.

| Folder | Phase | Status |
|---|---|---|
| [`phase-1-completed/`](./phase-1-completed/) | Manuscript platform — editor, RAG, characters, OCR, notes, export | ✅ Delivered |
| [`phase-2-completed/`](./phase-2-completed/) | Manuscript intelligence — P2-01 … P2-11 | ✅ Delivered |
| [`phase-3-planned/`](./phase-3-planned/) | Phase 3 — Author-Centric AI Workflow & generation management — P3-01 … P3-11 | ✅ Implemented (Stage 7); real-author UAT pending |

## Phase 1 — completed

- [`phase-1-production-implementation-report.docx`](./phase-1-completed/phase-1-production-implementation-report.docx)
  — the architecture reference for the v3.0.0 release: three-service stack, all 19 database tables,
  all 17 features, security and background-job architecture. **Superseded for Phase 2** by
  [`phase-2-implementation-report.md`](./phase-2-completed/phase-2-implementation-report.md). Its §12
  migration names `0003_story_bibles` / `0004_narrative_threads` / `0005_pacing_goals` are wrong; the
  files are `0008`–`0010` (conflict C-6).
- [`phase-1-status-update.docx`](./phase-1-completed/phase-1-status-update.docx) — a feature-by-feature
  audit of the original v3 specification against what was actually delivered. Records the seven
  deliberate architecture upgrades (pgvector over Qdrant, PostgreSQL over SQLite, GOT-OCR2.0 over
  TrOCR + EasyOCR).

## Phase 2 — completed

- [`phase-2-intelligence-expansion-roadmap.docx`](./phase-2-completed/phase-2-intelligence-expansion-roadmap.docx)
  — the authoritative Phase 2 specification (§19: P2-01 emotional arc, P2-02 continuation, P2-03
  dialogue voice consistency, P2-04 outline, P2-05 continuity, P2-06 story bible, P2-07 narrative
  threads, P2-08 style drift, P2-09 pacing goals, P2-10 duplicate scenes, P2-11 audio transcription).
- [`phase-2-acceptance-record.md`](./phase-2-completed/phase-2-acceptance-record.md) — the formal
  acceptance (task 11.6): every §20.4 criterion, §16 rule and §19 task with verdict, evidence, verifier
  and date, including the recorded deviations.
- [`phase-2-implementation-report.md`](./phase-2-completed/phase-2-implementation-report.md) — what
  Phase 2 delivered and where it lives. Supersedes the Phase 1 report for Phase 2 (roadmap §20.4 item 7).

The 14 defects found by Phase 2 production testing are all resolved
([report](../issues-and-bugs/resolved/phase-2-production-testing-issues.docx)).

## Phase 3 — Author-Centric AI Workflow (implemented)

- [`phase-3-author-centric-ai-workflow.md`](./phase-3-planned/phase-3-author-centric-ai-workflow.md)
  — **source of truth.** Eleven capabilities (P3-01 … P3-11) that make the generate → reject →
  regenerate loop lossless: generation pins, sentence-level locks, version comparison, preservation
  rules, lineage.
- [`phase-3-author-centric-ai-workflow.docx`](./phase-3-planned/phase-3-author-centric-ai-workflow.docx)
  — Word copy of the same content, for review outside the repository.

**Phase 3 is implemented** (Stage 7, migrations `0019`–`0022`; the spec's numbering `0016`–`0019`
was changed at implementation, decision C7-1). Where it lives in the code: [`CLAUDE.md`](../../CLAUDE.md),
"Phase 3 — Author-Centric AI Workflow". Deviations from the spec are listed in the
[`CHANGELOG.md`](../../CHANGELOG.md) Phase 3 entry.

> **Naming.** Older documents also called the **Production Hardening** pass (rate limiting, upload
> guards, concurrency semaphores, orphan-job recovery) "Phase 3". That is separate, earlier work,
> documented in [`CLAUDE.md`](../../CLAUDE.md) under "Production Hardening (completed)". "Phase 3" now
> means only the Author-Centric AI Workflow.
