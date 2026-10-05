# NarratIQ AI

**AI-Powered Long-Form Storytelling Platform**

A full-stack web application for novelists, fiction authors, and serious storytellers.

---

## Quick Start

### On RunPod (recommended)

```bash
# start-narratiq.sh finds its own checkout: run it from wherever you cloned the repository
cd /workspace/narratiq-ai        # or /workspace/Author_Narratiq, or any other path
bash start-narratiq.sh
```

One command. It installs every dependency, downloads models, configures PostgreSQL + pgvector, runs
migrations, and starts all three services, the hourly backup loop and the watchdog. Safe to rerun.
A fresh pod takes roughly 15–30 minutes, most of it model downloads.

- **Environment variables:** [`docs/operations/runpod-environment-variables.md`](docs/operations/runpod-environment-variables.md)
- **Pod setup and troubleshooting:** [`docs/operations/runpod-deployment.md`](docs/operations/runpod-deployment.md)
- **Manual / per-service startup:** [`docs/operations/how-to-run.md`](docs/operations/how-to-run.md)

### Manual

Requires PostgreSQL 16 + pgvector, ~22 GB of model weights, and a CUDA GPU with ≥24 GB VRAM.

```bash
# 1 — vLLM (port 9001)
python3 -m vllm.entrypoints.openai.api_server \
  --model /workspace/models/Qwen2.5-7B-Instruct \
  --served-model-name "Qwen/Qwen2.5-7B-Instruct" \
  --host 127.0.0.1 --port 9001 --max-model-len 8192   # loopback only: vLLM has no API key

# 2 — Backend (port 8000). MUST run from backend/ so config.py finds ./.env,
#     with exactly one worker (the startup guard refuses more; decision D-3).
#     backend/.env needs at least SECRET_KEY (≥ 32 chars) and DATABASE_URL.
cd backend
pip install -r requirements.txt
python3 -m alembic upgrade head
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1 --no-proxy-headers

# 3 — Frontend (port 3000). The browser calls /api/* on the frontend's own
#     origin and Next.js forwards it to BACKEND_INTERNAL_URL (default
#     http://127.0.0.1:8000). NEXT_PUBLIC_API_URL is used only by the voice
#     WebSocket.
cd ../frontend
npm ci
echo 'NEXT_PUBLIC_API_URL=http://localhost:8000' > .env.local
npm run dev
```

API docs: **http://localhost:8000/docs** (Swagger UI)

---

## Architecture

```
vLLM :9001   →   FastAPI :8000   →   Next.js :3000
(Qwen2.5-7B)     (+ BGE-M3 in-process, PostgreSQL 16 + pgvector)
```

**AI generation.** Every LLM call goes through `_complete()` / `_complete_json()` /
`_stream_generate()` in `backend/services/ai_service.py`, which talks to vLLM over the
OpenAI-compatible API. There are no stubs or placeholders anywhere in the codebase.

**Embeddings.** BGE-M3 (1024-dim) runs in-process via `sentence-transformers`. Vectors are stored in
`vector(1024)` columns and retrieved with pgvector HNSW indexes using the `<=>` cosine operator.

**Database.** PostgreSQL 16 + pgvector, 57 tables, 23 Alembic migrations (`0001` → `0027`; numbers
`0003`–`0006` were never used, the chain itself is unbroken). **SQLite is not supported** — a
pgvector self-check at startup fails hard without it.

**Startup order** (`backend/main.py`): single-worker guard → orphan-job recovery → upload dirs → model paths validated
(**hard fail** if missing) → BGE-M3 load → voice capability index → pgvector self-check (**hard
fail** if broken) → vLLM health probe (**warning only**; the backend starts in degraded mode and AI
endpoints return 503; `/api/health` reports `degraded`).

**Sessions.** Sign-in sets an HttpOnly session cookie on the frontend's origin, with CSRF protection
and server-side revocation. No token is stored where page scripts can read it. See `CLAUDE.md`,
"Auth (Stage 10)".

---

## Project Structure

```
narratiq-ai/
├── backend/                      # FastAPI, 26 router modules
│   ├── main.py                   # Entry point, lifespan, router registration, /api/health
│   ├── config.py                 # pydantic-settings; ~100 env-configurable fields
│   ├── database.py               # SQLAlchemy engine (pool_size=10, max_overflow=20)
│   ├── models.py                 # 57 ORM tables
│   ├── migrations/               # Alembic 0001 → 0027
│   ├── middleware/               # rate_limit, upload_guard, concurrency, body_limit,
│   │                             # csrf, origins, request_context
│   ├── startup/                  # worker_guard, orphan_recovery
│   ├── routers/
│   │   ├── auth · projects · chapters · characters
│   │   ├── intake · plot_assistant · ai_transform · ai_workspace · writing_tools
│   │   ├── analysis · analytics · plot_holes · narrative_threads · story_intel
│   │   ├── story_bible · pacing · copyright_risk
│   │   ├── ocr · audio · manuscript · manuscript_report
│   │   └── search · export · activity · voice_agent · ops
│   └── services/
│       ├── ai_service.py         # All LLM + BGE-M3 calls
│       ├── audio_service.py      # faster-whisper transcription
│       ├── ocr_service.py        # GOT-OCR2.0
│       ├── story_intel_*.py      # Story intelligence orchestration
│       └── voice/                # Real-time voice agent (20 modules)
│
├── scripts/                      # backups, restore checks, watchdog, rollback, docs tooling
└── frontend/                     # Next.js 15
    ├── app/(dashboard)/projects/[id]/
    │   ├── write · plan · characters · world
    │   └── analyze · assistant · publish        # 7 author workspaces
    ├── components/               # editor, ai-tools, analysis, characters,
    │                             # voice, studio, story-bible, notes, …
    └── lib/
        ├── api.ts                # Typed API client (same-origin /api, session cookie, CSRF header)
        ├── registries/           # Declarative workspace + panel registries
        └── types.ts
```

The editor is organised into **7 workspaces** (Write, Plan, Characters, World, Analyze, Assistant,
Publish) driven declaratively by `frontend/lib/registries/workspaces.ts`. Adding a workspace is a
single row — no routing or navigation edits.

---

## AI Models

| Feature | Model |
|---|---|
| Text generation, analysis, rewriting | Qwen2.5-7B-Instruct (via vLLM) |
| Embeddings and retrieval | BAAI/bge-m3 (1024-dim, in-process) |
| OCR (handwriting, full page) | stepfun-ai/GOT-OCR2_0 (lazy-loaded) |
| Audio transcription | faster-whisper-large-v3-turbo (CTranslate2) |
| Live voice partials | faster-whisper-base |

All are local weights under `MODEL_BASE_DIR` (default `/workspace/models`, ~22 GB total, measured 2026-10-05).
No external AI API is called.

---

## Selected API Routes

Full interactive documentation at `/docs`.

| Method | Route | Description |
|---|---|---|
| POST | `/api/auth/register` · `/login` · `/logout` | Account and session (HttpOnly cookie) |
| GET / DELETE | `/api/auth/me` · `/api/auth/account` | Current user · delete account and all data |
| GET/POST | `/api/projects/` | Story CRUD |
| GET/PATCH | `/api/stories/{id}/chapters` | Chapters + autosave + version history |
| POST | `/api/intake/{id}` | Genre detection |
| POST | `/api/plot-assistant/` | Plot suggestions (RAG over chapter chunks) |
| POST | `/api/ai/refine` · `/tone` · `/emotion` · `/translate` · `/author-style` | Selection transforms (+ `/stream` variants) |
| GET | `/api/ai/author-styles` | Author-style catalogue |
| POST | `/api/stories/{id}/chapters/{cid}/continue` | Chapter continuation |
| POST | `/api/stories/{id}/chapters/{cid}/outline` | Beat sheet / scene outline |
| GET | `/api/stories/{id}/emotional-arc` | Emotional arc |
| POST | `/api/stories/{id}/continuity-check` · `/style-drift` · `/duplicate-scenes` | Analysis |
| POST | `/api/stories/{id}/plot-holes` | Plot hole detection |
| POST/GET | `/api/stories/{id}/story-bible` | Story bible generation |
| POST | `/api/stories/{id}/copyright-risk` | Copyright / plagiarism risk |
| POST | `/api/ocr/extract/{story_id}` · `/api/stories/{id}/audio` | OCR and audio ingestion |
| POST | `/api/stories/{id}/ai/pins` · `/ai/similarity` | Phase 3 pins and similarity |
| POST | `/api/manuscript/upload/{id}` | Full manuscript ingestion |
| WS | `/api/voice/stream` | Real-time voice agent |
| POST | `/api/export/` | DOCX / PDF export |
| GET | `/api/health` · `/api/ops/status` | Health (public) · operations status (`X-Ops-Token`) |

---

## Tech Stack

**Frontend** Next.js 15, TypeScript, TailwindCSS, TipTap, Radix UI, TanStack Query, Zustand, Lucide
**Backend** FastAPI, SQLAlchemy 2, Pydantic v2, Alembic, python-jose (session JWT in an HttpOnly cookie), slowapi
**Database** PostgreSQL 16 + pgvector (HNSW)
**AI** Qwen2.5-7B-Instruct, BAAI/bge-m3, GOT-OCR2.0, faster-whisper
**Inference** vLLM 0.9.2 (OpenAI-compatible server)

---

## Features

### Core
- [x] Landing page, user auth (register / login / logout, HttpOnly cookie sessions, change password)
- [x] Account deletion (immediate, all data) and a published data policy (`/data-policy`)
- [x] Projects dashboard with statistics
- [x] Story intake — AI genre detection with editable results
- [x] 7-workspace author studio with command palette and selection toolbar
- [x] Chapter management — add, rename, delete, autosave, version history
- [x] AI transforms — refine, tone (9), emotion (6), audience, style, translation
- [x] Author-inspired style rewrite (public-domain authors only)
- [x] AI Plot Assistant with RAG over chapter chunks
- [x] Handwritten notes OCR (GOT-OCR2.0) — extraction fixed in Stage 12 (A2); needs a GPU, handwriting quality not yet measured
- [x] Writing analytics — word count, readability, dialogue ratio
- [x] Full manuscript import (.txt / .docx) from the Write binder ("Import manuscript…", Stage 12 A8); chapters are saved before success is reported
- [x] Export to DOCX / PDF
- [x] Global search (semantic + exact)

### Story intelligence
- [x] Emotional arc analysis
- [x] Chapter continuation (3 options)
- [x] Scene duplicate detection
- [x] Style drift analysis
- [x] Character voice consistency
- [x] Story bible generator (5 sections)
- [x] Chapter outline / beat sheet
- [x] Continuity checking
- [x] Plot hole detection
- [x] Narrative thread tracking
- [x] Character cast, profiles, relationship graph, arc timeline
- [x] Pacing goals and progress tracking
- [x] Audio transcription (faster-whisper + cleanup)
- [x] Real-time voice agent (streaming STT, multi-step planning)
- [x] Activity timeline
- [x] Copyright / plagiarism risk detection

### Author-centric AI workflow (Phase 3)
- [x] Temporary pins for AI generations (unpinned generations are never stored)
- [x] Sentence locks and partial regeneration
- [x] Generate from a pinned version, use pins as context, avoid repeats
- [x] Compare and merge versions
- [x] Per-story preservation rules for AI rewrites
- [x] Idea Shelf
- [x] Similarity check

### Production hardening
- [x] Per-user and per-IP rate limiting (8 configurable limits, single worker enforced)
- [x] Upload size guards (audio / OCR / manuscript)
- [x] Background AI concurrency semaphores
- [x] Orphan job recovery at startup
- [x] Structured logging (text / JSON)
- [x] Graceful AI-unavailable handling (503 with `Retry-After`)

### Operations (Stage 10)
- [x] Hourly verified database backups with retention; restore rehearsed (off-pod copy not yet configured)
- [x] Live health checks, operations metrics, built-in error tracking, watchdog alerts to a local file
- [x] Rollback procedures for schema, frontend build and pinned model revisions
- [x] Development containers (`backend/Dockerfile`, `frontend/Dockerfile`; RunPod stays the production host)

### Not yet built
- [ ] EPUB / Kindle export (DOCX and PDF are supported)
- [ ] Batched / hierarchical plot-hole strategies for manuscripts over 60 chapters (see Known Issues)
- [ ] Multi-user collaboration — the permission seam exists but always grants access
  (`StoryContextEngine.tsx`), so the app is single-owner today

---

## Known Issues

**The single, current list of known limitations is in the release-candidate notes:
[`docs/releases/v3.3.0-rc-release-notes.md` → Known limitations](docs/releases/v3.3.0-rc-release-notes.md#known-limitations).**
It separates release-blocking operational risks, measured criteria that were not met, pending owner decisions and
human reviews, external requirements, and accepted limitations. The full issue register, with severity and
release-blocking status, is [`docs/issues-and-bugs/triage-register.md`](docs/issues-and-bugs/triage-register.md).

The most important items (2026-10-05):

1. **⚠ No off-pod backup copy.** Backups stay on the RunPod network volume. Losing the pod and its volume — this
   project's pod has been replaced three times — loses the database and every backup together. **No real author data
   may be stored until an approved off-pod copy exists and a restore from it is verified** (W-3, not waived).
2. **No person-delivered alerts** (W-4, waived with a required daily manual check: `scripts/daily_check.sh`).
3. **Measured criteria not met:** rewrite run-to-run consistency (AWT-G), Plot Assistant context ordering (PA-C6,
   PA-H12) and AI role suggestions (CAST-H6) are accepted as known limitations for this release (2026-10-05) — the
   criteria stay recorded as not met; Light vs Strong for tone and age adaptation awaits human labels.
   (The chapter-scoped story Q&A prompt-injection finding of 2026-10-05 was fixed the same day; its residual risk
   awaits the owner's S1 decision.)
4. **Human reviews pending:** blind rewrite review, children's rewrites, Story Bible reading, translation by a fluent
   speaker, real-author UAT, legal review of the copyright-risk disclaimer.
5. **Accepted for launch:** plot-hole detection and the manuscript report read at most 60 chapters (decision D-8);
   the batched and hierarchical strategies that would lift the cap are not written.

Resolved since earlier revisions of this list: OCR extraction (Stage 12 A2), the missing manuscript-upload
control (A8), duplicate-character detection (A7), the Next.js 14 advisories (A5), the vLLM port contradiction (9001 everywhere; `start.sh`
retired), Story Bible placeholders stored as content (per-section `completed`/`partial`/`failed`
status since Stage 3), and the outline / continuation / continuity / plot-hole failures. Those had
**two** causes, not one: a retrieval call-signature bug (task 3.1) and schema handling of model output
(tasks 3.4, 3.5).

---

## Documentation

**Start here: [`docs/README.md`](docs/README.md)** — the full documentation index, organised by
purpose (phases, open issues, testing, incidents, operations, archive).

| File | Purpose |
|---|---|
| [`docs/README.md`](docs/README.md) | Documentation index and recommended reading order |
| [`docs/NarratIQ_Master_Implementation_Checklist.md`](docs/NarratIQ_Master_Implementation_Checklist.md) | Execution tracker: every remaining task, its evidence and stage gates |
| [`docs/operations/how-to-run.md`](docs/operations/how-to-run.md) | Starting each service, verification, common problems |
| [`docs/operations/runpod-deployment.md`](docs/operations/runpod-deployment.md) | Pod creation, storage, deployment, GPU requirements, troubleshooting |
| [`docs/operations/runpod-environment-variables.md`](docs/operations/runpod-environment-variables.md) | Which env vars to set, precedence, generated values |
| [`docs/operations/README.md`](docs/operations/README.md) | Operations runbooks: backup and restore, monitoring, incident response, rollback, capacity, containers, model versions |
| [`docs/policies/data-retention-and-deletion.md`](docs/policies/data-retention-and-deletion.md) | What is stored, for how long, and how deletion works |
| [`docs/specifications/narratiq-ai-product-and-technical-documentation.md`](docs/specifications/narratiq-ai-product-and-technical-documentation.md) | Product and technical specification (v5) |
| [`docs/phases/phase-3-planned/phase-3-author-centric-ai-workflow.md`](docs/phases/phase-3-planned/phase-3-author-centric-ai-workflow.md) | Phase 3 — Author-Centric AI Workflow specification (implemented in Stage 7) |
| [`docs/issues-and-bugs/triage-register.md`](docs/issues-and-bugs/triage-register.md) | Every reported issue with severity and release-blocking status |
| [`CLAUDE.md`](CLAUDE.md) | Architecture reference for contributors and AI assistants |
| [`CHANGELOG.md`](CHANGELOG.md) | Release history |
| [`.env.example`](.env.example) | Annotated configuration template |
