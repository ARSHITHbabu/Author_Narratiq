# NarratIQ AI — v3.0

**AI-Powered Long-Form Storytelling Platform**

A full-stack web application for novelists, fiction authors, and serious storytellers.

---

## Quick Start

### On RunPod (recommended)

```bash
cd /workspace/narratiq-ai
bash start-narratiq.sh
```

One command. It installs every dependency, downloads models, configures PostgreSQL + pgvector, runs
migrations, and starts all three services. Safe to rerun.

- **Environment variables:** [`docs/operations/runpod-environment-variables.md`](docs/operations/runpod-environment-variables.md)
- **Pod setup and troubleshooting:** [`docs/operations/runpod-deployment.md`](docs/operations/runpod-deployment.md)
- **Manual / per-service startup:** [`docs/operations/how-to-run.md`](docs/operations/how-to-run.md)

### Manual

Requires PostgreSQL 16 + pgvector, ~17 GB of model weights, and a CUDA GPU with ≥24 GB VRAM.

```bash
# 1 — vLLM (port 9001)
python3 -m vllm.entrypoints.openai.api_server \
  --model /workspace/models/Qwen2.5-7B-Instruct \
  --served-model-name "Qwen/Qwen2.5-7B-Instruct" \
  --host 0.0.0.0 --port 9001 --max-model-len 8192

# 2 — Backend (port 8000). MUST run from backend/ so config.py finds ./.env
cd backend
pip install -r requirements.txt
python3 -m alembic upgrade head
uvicorn main:app --host 0.0.0.0 --port 8000

# 3 — Frontend (port 3000)
cd frontend
npm install
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

**Database.** PostgreSQL 16 + pgvector, 51 tables, 15 Alembic migrations (`0001` → `0015`; numbers
`0003`–`0006` were never used, the chain itself is unbroken). **SQLite is not supported** — a
pgvector self-check at startup fails hard without it.

**Startup order** (`backend/main.py`): orphan-job recovery → upload dirs → model paths validated
(**hard fail** if missing) → BGE-M3 load → voice capability index → pgvector self-check (**hard
fail** if broken) → vLLM health probe (**warning only**; the backend starts in degraded mode and AI
endpoints return 503).

---

## Project Structure

```
narratiq-ai/
├── backend/                      # FastAPI, 23 routers
│   ├── main.py                   # Entry point, lifespan, router registration
│   ├── config.py                 # pydantic-settings; 56 env-configurable fields
│   ├── database.py               # SQLAlchemy engine (pool_size=10, max_overflow=20)
│   ├── models.py                 # 51 ORM tables
│   ├── migrations/               # Alembic 0001 → 0015
│   ├── middleware/               # rate_limit, upload_guard, concurrency
│   ├── startup/                  # orphan_recovery
│   ├── routers/
│   │   ├── auth · projects · chapters · characters
│   │   ├── intake · plot_assistant · ai_transform · writing_tools
│   │   ├── analysis · plot_holes · narrative_threads · story_intel
│   │   ├── story_bible · pacing · copyright_risk
│   │   ├── ocr · audio · manuscript · manuscript_report
│   │   └── search · export · activity · voice_agent
│   └── services/
│       ├── ai_service.py         # All LLM + BGE-M3 calls
│       ├── audio_service.py      # faster-whisper transcription
│       ├── ocr_service.py        # GOT-OCR2.0
│       ├── story_intel_*.py      # Story intelligence orchestration
│       └── voice/                # Real-time voice agent (20 modules)
│
└── frontend/                     # Next.js 14
    ├── app/(dashboard)/projects/[id]/
    │   ├── write · plan · characters · world
    │   └── analyze · assistant · publish        # 7 author workspaces
    ├── components/               # editor, ai-tools, analysis, characters,
    │                             # voice, studio, story-bible, notes, …
    └── lib/
        ├── api.ts                # Typed API client + JWT interceptor
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

All are local weights under `MODEL_BASE_DIR` (default `/workspace/models`, ~17 GB total).
No external AI API is called.

---

## Selected API Routes

Full interactive documentation at `/docs`.

| Method | Route | Description |
|---|---|---|
| POST | `/api/auth/register` · `/api/auth/login` | Account + JWT |
| GET/POST | `/api/projects/` | Story CRUD |
| GET/PATCH | `/api/stories/{id}/chapters` | Chapters + autosave + version history |
| POST | `/api/intake/{id}` | Genre detection |
| POST | `/api/plot-assistant/` | Plot suggestions (RAG over chapter chunks) |
| POST | `/api/ai/refine` · `/tone` · `/emotion` · `/translate` · `/author-style` | Selection transforms (+ `/stream` variants) |
| GET | `/api/ai/author-styles` | Author-style catalogue |
| POST | `/api/stories/{id}/chapters/{cid}/continue` | Chapter continuation |
| POST | `/api/stories/{id}/chapters/{cid}/outline` | Beat sheet / scene outline |
| GET | `/api/stories/{id}/emotional-arc` · `/continuity-check` · `/style-drift` · `/duplicate-scenes` | Analysis |
| GET | `/api/stories/{id}/plot-holes` | Plot hole detection |
| POST/GET | `/api/stories/{id}/story-bible` | Story bible generation |
| POST | `/api/stories/{id}/copyright-risk` | Copyright / plagiarism risk |
| POST | `/api/stories/{id}/ocr` · `/audio` | OCR and audio ingestion |
| POST | `/api/manuscript/upload/{id}` | Full manuscript ingestion |
| WS | `/api/voice/stream` | Real-time voice agent |
| POST | `/api/export/` | DOCX / PDF export |

---

## Tech Stack

**Frontend** Next.js 14, TypeScript, TailwindCSS, TipTap, Radix UI, TanStack Query, Zustand, Lucide
**Backend** FastAPI, SQLAlchemy 2, Pydantic v2, Alembic, python-jose (JWT), slowapi
**Database** PostgreSQL 16 + pgvector (HNSW)
**AI** Qwen2.5-7B-Instruct, BAAI/bge-m3, GOT-OCR2.0, faster-whisper
**Inference** vLLM 0.9.2 (OpenAI-compatible server)

---

## Features

### Core
- [x] Landing page, user auth (register / login / JWT)
- [x] Projects dashboard with statistics
- [x] Story intake — AI genre detection with editable results
- [x] 7-workspace author studio with command palette and selection toolbar
- [x] Chapter management — add, rename, delete, autosave, version history
- [x] AI transforms — refine, tone (9), emotion (6), audience, style, translation
- [x] Author-inspired style rewrite (public-domain authors only)
- [x] AI Plot Assistant with RAG over chapter chunks
- [x] Handwritten notes OCR (GOT-OCR2.0)
- [x] Writing analytics — word count, readability, dialogue ratio
- [x] Full manuscript upload + background ingestion
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

### Production hardening
- [x] Per-user and per-IP rate limiting (6 independent limits)
- [x] Upload size guards (audio / OCR / manuscript)
- [x] Background AI concurrency semaphores
- [x] Orphan job recovery at startup
- [x] Structured logging (text / JSON)
- [x] Graceful AI-unavailable handling (503 with `Retry-After`)

### Not yet built
- [ ] EPUB / Kindle export (DOCX and PDF are supported)
- [ ] Multi-user collaboration — the permission seam exists but always grants access
  (`StoryContextEngine.tsx`), so the app is single-owner today

---

## Known Issues

Tracked in [`docs/issues-and-bugs/open/`](docs/issues-and-bugs/) — see
[Phase 1 QA issues](docs/issues-and-bugs/open/phase-1-ai-writing-tools-qa-issues.docx) and
[Phase 2 production testing issues](docs/issues-and-bugs/open/phase-2-production-testing-issues.docx).
(A code-level audit, `NarratIQ_Project_Recovery_Report.docx`, is referenced by older documents but is
not present in this repository.) Highest priority:

1. **vLLM port contradiction** — `start-narratiq.sh` and `config.py` use 9001; the legacy `start.sh`
   and `scripts/verify_runpod_setup.sh` still use 8001. See
   [`docs/operations/runpod-deployment.md`](docs/operations/runpod-deployment.md).
2. **Story Bible can persist placeholder text** while marking the job `completed`
   (`routers/story_bible.py:138-147`).
3. **Outline / continuation / continuity / plot-hole failures** share one root cause — invalid AI
   output is not handled gracefully in the response parsing layer.
4. **Plot Assistant retrieval** favours Chapter 1 over later chapters.
5. **Plot hole detection caps at 60 chapters** (`ai_service.py:1534`); the batched and hierarchical
   strategies are written but not enabled.

---

## Documentation

**Start here: [`docs/README.md`](docs/README.md)** — the full documentation index, organised by
purpose (phases, open issues, testing, incidents, operations, archive).

| File | Purpose |
|---|---|
| [`docs/README.md`](docs/README.md) | Documentation index and recommended reading order |
| [`docs/operations/how-to-run.md`](docs/operations/how-to-run.md) | Starting each service, verification, common problems |
| [`docs/operations/runpod-deployment.md`](docs/operations/runpod-deployment.md) | Pod creation, storage, deployment, troubleshooting |
| [`docs/operations/runpod-environment-variables.md`](docs/operations/runpod-environment-variables.md) | Which env vars to set, precedence, generated values |
| [`docs/phases/phase-3-planned/phase-3-author-centric-ai-workflow.md`](docs/phases/phase-3-planned/phase-3-author-centric-ai-workflow.md) | Next phase to be built (design specification) |
| [`CLAUDE.md`](CLAUDE.md) | Architecture reference for contributors and AI assistants |
| [`CHANGELOG.md`](CHANGELOG.md) | Release history |
| [`.env.example`](.env.example) | Annotated configuration template |
