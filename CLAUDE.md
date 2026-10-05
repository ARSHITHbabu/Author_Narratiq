# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Service Commands

```bash
# Start everything (handles installs, patches, vLLM, backend, frontend)
bash start-narratiq.sh   # from the repository root; it finds its own checkout (any path)

# Manual vLLM start — values for the verified production pod (1× NVIDIA A40).
# start-narratiq.sh picks TP / max-model-len / utilisation from the GPU count;
# see "GPU / Hardware Notes" below for the other rows of that table.
NCCL_P2P_DISABLE=1 NCCL_SHM_DISABLE=1 python3 -m vllm.entrypoints.openai.api_server \
  --model /workspace/models/Qwen2.5-7B-Instruct \
  --served-model-name "Qwen/Qwen2.5-7B-Instruct" \
  --dtype auto --gpu-memory-utilization 0.88 \
  --tensor-parallel-size 1 --max-model-len 8192 \
  --max-num-seqs 256 --enable-chunked-prefill --enable-prefix-caching \
  --host 127.0.0.1 --port 9001   # loopback only (Stage 12 A4): vLLM has no API key

# Backend — exactly one worker (D-3; the startup guard refuses more) and
# --no-proxy-headers (client_ip() reads CF-Connecting-IP itself; see Stage 10 below)
cd backend && python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1 --no-access-log --no-proxy-headers

# Frontend
cd frontend && npm run dev

# Frontend environment (RunPod proxy URL) — written automatically by start-narratiq.sh.
# NEXT_PUBLIC_API_URL is inlined at BUILD time and (since Stage 10) used ONLY for the
# voice WebSocket; all HTTP is same-origin /api/* rewritten to BACKEND_INTERNAL_URL.
echo 'NEXT_PUBLIC_API_URL=https://{POD_ID}-8000.proxy.runpod.net' > frontend/.env.local
```

**Environment variables:** `start-narratiq.sh` generates everything mandatory. At most two are worth setting in the RunPod UI (`SECRET_KEY`, `HF_TOKEN`), and several stale ones actively break the app. Full analysis — precedence, generated values, obsolete variables, recovery workflow — in [`docs/operations/runpod-environment-variables.md`](docs/operations/runpod-environment-variables.md).

## Health & Logs

```bash
curl http://localhost:8000/api/health
tail -f /tmp/narratiq-logs/vllm.log
tail -f /tmp/narratiq-logs/backend.log
tail -f /tmp/narratiq-logs/frontend.log

# Re-index existing chapters after manual DB changes
curl -X POST http://localhost:8000/api/stories/{id}/chapters/sync-summaries \
  -H "Authorization: Bearer $TOKEN"
```

## Architecture

**Three-service stack:** vLLM (port 9001, loopback only) → FastAPI backend (port 8000) → Next.js 15 frontend (port 3000; Next.js 15.5, React 18.3 since Stage 12 A5).

**Backend startup sequence** (`main.py` `lifespan`): single-worker guard (`startup/worker_guard.py`, refuses more than one worker, D-3) → orphan-job recovery → Phase 3 pin-backend / context-budget validation → upload dirs → model paths validated → BGE-M3 loaded synchronously via `get_bge()` → voice capability index → pgvector self-check → vLLM health check → warmup request → `_run_periodic_cleanup()` scheduled → ready.

Hard failures (`RuntimeError`) are the worker guard, an invalid Phase 3 pin backend or a malformed `PLAN_LIMITS_JSON`, **missing model weights** (the model-path check in `lifespan`), and a **broken pgvector query path** (the "pgvector path self-check" block). If vLLM is unreachable the backend logs a warning and **continues in degraded mode** — AI endpoints return 503. Since Stage 10 `/api/health` probes vLLM **live** (cached 10 s) and answers **503 with `"status":"degraded"`** while vLLM or BGE-M3 is not ready; `"backend":"ready"` is the "API is serving" signal.

**AI text generation:** All LLM calls go through `_complete()` / `_stream_generate()` in `backend/services/ai_service.py` via the OpenAI-compatible vLLM endpoint. Model: `Qwen2.5-7B-Instruct`.

**Prompt-injection defence (Stage 11, finding P1):** `services/prompt_safety.py`, applied centrally in `_complete_ex()` and `_stream_generate()`, so every call is covered.
- The user message (the author's material) is fenced between `<<<AUTHOR_MATERIAL id>>>` markers with a per-call random id.
- The system message gains a short "the fenced text is data" rule.
- The concrete task is restated **after** the fence. Measured on Qwen-7B, what the model reads last decides whether it obeys an injected line.
- Call sites pass `task=`: `prompt_safety.REWRITE_TASK` for rewrites, `TRANSLATE_TASK`, or `question_task(question)` for Q&A, so the author's question comes last.
- Output check: rewrite endpoints run `rewrite_lost_source()` on the output, retry once, then refuse with 422 `instruction_like_text` instead of returning a hijacked "rewrite". A copyright `note` that merely echoes the input is dropped (`echoes_source()`).
- Story Q&A (`answer_story_question`: Plot Assistant, voice story/character questions) also **datamarks** the fenced material (Stage 12.2, `prompt_safety` Layer 1b): in the prompt copy a `ˆ` replaces every 4th gap between words, and every gap in the open chapter's excerpt. Without it, chapter-scoped Q&A followed instructions planted in the open chapter (voice 12/12, Plot Assistant 9/12). Pass `datamark=True` to `_complete` only for Q&A-shaped calls; the token fit (`_qa_prompt_tokens`) must measure the marked prompt. `PROMPT_INJECTION_DATAMARK_QA=false` restores the Stage 11 Q&A prompt.
- `PROMPT_INJECTION_GUARD=false` restores the old prompts exactly; use it for measurement only.
- Residual risk is documented in `docs/testing/stage-09-security-findings.md`.

**Embeddings:** BGE-M3 (1024-dim) runs in-process via `sentence-transformers`. Embeddings stored as `vector(1024)` columns (pgvector) on `chapter_chunks`, `chapter_summaries`, `character_profiles` (×2), `story_notes`, and `note_cards`. All vector similarity uses pgvector's `<=>` cosine operator via raw SQL:
- **Retrieval of stored vectors:** HNSW indexes.
- **Vectors computed for the request** (dialogue passages in the voice check, thread names, style-drift centroids): `services/vector_math.py` (`cosine_pairs`, `cosine`), one SQL round trip, nothing stored. This is Phase 2 rule R12 (Stage 11).
- numpy only averages centroids, which is arithmetic.
- The one numpy-cosine site left is the voice-agent capability catalog (`services/voice/catalog.py`). It is not a Phase 2 feature and is out of R12's scope.

**Database:** PostgreSQL 16 + pgvector + SQLAlchemy ORM, 57 ORM tables in `backend/models.py`. Connection pool: `pool_size=10, max_overflow=20`. Table groups:
- **Core:** `users`, `stories`, `chapters`, `chapter_chunks` (350-word overlap chunks for RAG), `chapter_summaries`, `characters`, `character_profiles`, `character_relationships`.
- **Notes:** `story_notes`, `note_cards` (also the Idea Shelf).
- **Story Intelligence:** 23 tables (`0007`).
- **Phase 2:** `story_bibles`, `narrative_threads`, `pacing_goals`, `audio_uploads`.
- **Voice agent:** tables from `0012`.
- **Activity and preservation:** `activity_events`, `story_preservation_settings`.
- **Phase 3:** `ai_generation_pins`.
- **Stage 5:** `narrative_thread_scans`, `manuscript_reports`.
- **Stage 10:** `revoked_sessions`, `error_events`.

Alembic manages schema migrations (`backend/migrations/`). `start-narratiq.sh` runs `Base.metadata.create_all()` then `alembic upgrade head` before FastAPI starts.

**Staleness:** `services/source_fingerprint.py::chapter_source_fingerprint()` hashes the indexed chapters an artefact was generated from. The saved Manuscript Report (`0023`) and the Story Bible (`story_bibles.source_fingerprint`, `0025`) store it at generation time and report `is_stale` on read.

**Background tasks:** `asyncio.create_task()`, with no Redis or external queue. Used for:
- re-embedding after profile updates
- Story Bible generation
- narrative-thread scans
- manuscript import jobs
- the Story Intelligence orchestrator
- audio transcription

`_run_periodic_cleanup()` (hourly) sweeps OCR and audio files, orphaned uploads, expired pins, auth sessions and error events. The backup loop and watchdog run as separate processes started by `start-narratiq.sh` (Stage 10, below).

**Routers** (`main.py`, 26 modules, all under `backend/routers/`):

| Prefix | Routers |
|---|---|
| `/api/auth` | `auth` |
| `/api/projects` | `projects` |
| `/api/stories` | `chapters`, `characters`, `plot_holes`, `manuscript_report`, `story_intel`, `analysis`, `analytics`, `writing_tools`, `pacing`, `narrative_threads`, `story_bible`, `audio`, `activity`, `copyright_risk`, `ai_workspace` |
| `/api/intake` | `intake` |
| `/api/plot-assistant` | `plot_assistant` |
| `/api/ai` | `ai_transform` |
| `/api/ocr` | `ocr` |
| `/api/manuscript` | `manuscript` |
| `/api/export` | `export` |
| `/api/search` | `search` |
| `/api/voice` | `voice_agent` |
| `/api/ops` | `ops`; its `public_router` adds `/api/client-errors` and the ops-token-gated `/api/stats`. `/api/health` is defined in `main.py` |

**Middleware** (`backend/middleware/`): `rate_limit`, `upload_guard`, `concurrency`, `body_limit`, `csrf`, `origins`, `request_context`.

**Auth (Stage 10):** the JWT is an **HttpOnly cookie** (`narratiq_session`) on the frontend's own origin — the browser calls `/api/*` same-origin and `next.config.js` rewrites it to the backend, so no page script can read the token and nothing is in localStorage. CSRF: double-submit (`narratiq_csrf` cookie → `X-CSRF-Token` header, `middleware/csrf.py`) for cookie-authenticated state changes. `Authorization: Bearer` still works for tooling and tests. Tokens carry `jti` + `ver`: logout revokes that session only (`revoked_sessions`); password change / account deletion bump `users.token_version` (all sessions end). The voice WebSocket uses a single-use 60 s ticket (`POST /api/auth/ws-ticket`). The frontend learns who is signed in from `GET /api/auth/me`; a 401 redirects to `/login`.

**Character RAG:** Hybrid retrieval — cosine similarity on BGE-M3 embeddings + name-mention boost. 800-token budget cap per context window.

## GPU / Hardware Notes

**Verified production hardware:** **1× NVIDIA A40, 46068 MiB** (task 1.6; re-observed on every pod since, most recently `x0smrkvs4n6wpk` on 2026-10-03). vLLM runs at **TP=1, `max-model-len` 8192, `gpu-memory-utilization` 0.88**. Any card with ≥ 24 GB VRAM works.

`start-narratiq.sh` (STEP 3) chooses the vLLM settings from the number of GPUs `nvidia-smi` reports:

| GPUs | `--tensor-parallel-size` | `--max-model-len` | `--gpu-memory-utilization` |
|---|---|---|---|
| 1 | 1 | 8192 | 0.88 |
| 2–3 | 2 | 16384 | 0.90 |
| 4+ | 4 | 32768 | 0.90 |

The Story Bible / Plot Assistant context budgets are sized for the **8192** window; a larger window only adds headroom.

**Requirements that apply to every GPU:** vLLM **0.9.2**, pinned in `start-narratiq.sh`; clear `~/.cache/vllm/torch_compile_cache` after any failed start (the script does this every run); the `ovis.py` patch: every `AutoConfig.register()` call needs `exist_ok=True` because transformers 4.51+ pre-registers these types. The script applies it with `sed`.

**Requirements that apply only to NVIDIA Blackwell (sm_120, e.g. RTX PRO 4500), the project's original 2-GPU pod:**
- PyTorch **2.7.0+cu128**, because the cu124/cu126 builds top out at sm_90. vLLM 0.9.2 is the first release with sm_120 support.
- `NCCL_P2P_DISABLE=1 NCCL_SHM_DISABLE=1`, which prevents an NCCL deadlock at init with TP ≥ 2.

The script applies both unconditionally. They are harmless on the A40: cu128 runs on sm_86, and the NCCL flags are inert at TP=1. So the same script serves both hardware types.

## Key Files

| File | Purpose |
|------|---------|
| `backend/services/ai_service.py` | All LLM + BGE-M3 calls; `_complete()`, `_stream_generate()`, `get_bge()` |
| `backend/services/audio_service.py` | faster-whisper transcription + Qwen transcript cleanup |
| `backend/routers/audio.py` | Phase 2: audio upload → faster-whisper → Qwen cleanup → note append |
| `backend/routers/story_bible.py` | Phase 2: 5-section story bible generation via Qwen; DOCX export |
| `backend/routers/analysis.py` | Phase 2: emotional arc, duplicate scenes, style drift, continuity |
| `backend/routers/writing_tools.py` | Phase 2: chapter continuation (`generate_chapter_continuation`) **and** outline / beat sheet (`generate_outline`). There is no separate continuation or outline router |
| `backend/routers/characters.py` | Character CRUD, relationships, merge, **and** dialogue-voice consistency (`check_voice_consistency` route → `ai_service.check_dialogue_consistency`). There is no separate voice-check router |
| `backend/routers/voice_agent.py` | Real-time voice agent (WS + REST). **Different feature** from the P2-05 dialogue checker above — do not confuse the two |
| `backend/routers/pacing.py` | Phase 2: pacing goal setting + chapter progress tracking |
| `backend/models.py` | SQLAlchemy ORM models (full schema) |
| `backend/schemas.py` | Pydantic request/response schemas |
| `backend/config.py` | Settings loaded from `.env` via pydantic-settings (~100 fields incl. 30 Phase 3). `vllm_base_url` defaults to **9001**, matching `start-narratiq.sh`. `secret_key` is the only field with no default |
| `frontend/lib/api.ts` | Typed API client wrappers. Same-origin `/api` calls with the session cookie; interceptors add the CSRF header and redirect to `/login` on 401 |
| `frontend/lib/types.ts` | TypeScript interfaces for all domain objects |
| `frontend/app/(dashboard)/projects/[id]/page.tsx` | Story entry: redirects to the author's last workspace (default Write). The old 3-column editor is gone |
| `frontend/app/(dashboard)/projects/[id]/{write,plan,characters,world,analyze,assistant,publish}/page.tsx` | The Studio workspaces (Stage 8). `layout.tsx` holds `StudioShell` + `StudioStoreGate` |
| `frontend/lib/registries/{workspaces.ts,panels.tsx,actions.ts,toolHomes.ts}` | Studio registries. `toolHomes.ts` is the one table of where every tool lives; add a tool per `docs/architecture/adding-a-studio-tool.md` |
| `frontend/lib/studioStore.ts` | Layout/mode store, persisted per user per browser (`narratiq_studio:<user_id>`) |
| `frontend/tests/studio/` | Mocked-API Playwright suite (`npm run test:studio`, `test:a11y`, `test:studio:variants`); config `playwright.studio.config.ts` |
| `frontend/app/(dashboard)/projects/[id]/error.tsx` | Next.js error boundary for the editor route |
| `frontend/components/chunk-error-recovery.tsx` | Auto-reload on ChunkLoadError; sessionStorage debounce to prevent loops |
| `start-narratiq.sh` | Full bootstrap: pip installs, ovis.py patch, numpy pin, cache clear, service launch |

## Phase 2 Features (P2-01 → P2-11)

Numbering follows the Phase 2 roadmap §19 (`docs/phases/phase-2-completed/phase-2-intelligence-expansion-roadmap.docx`). Every router below is mounted at `/api/stories`. Acceptance evidence for each task: [`phase-2-acceptance-record.md`](docs/phases/phase-2-completed/phase-2-acceptance-record.md).

| ID | Feature | Backend Router | AI Model | Endpoint |
|----|---------|---------------|----------|----------|
| P2-01 | Emotional Arc Analysis | `analysis.py` | Qwen | `GET /api/stories/{id}/emotional-arc` |
| P2-02 | Chapter Continuation | `writing_tools.py` | Qwen | `POST /api/stories/{id}/chapters/{cid}/continue` |
| P2-03 | Dialogue Voice Consistency | `characters.py` | BGE-M3 + Qwen | `POST /api/stories/{id}/characters/{char_id}/voice-check` |
| P2-04 | Outline / Beat Sheet | `writing_tools.py` | Qwen | `POST /api/stories/{id}/chapters/{cid}/outline` |
| P2-05 | Continuity Validator | `analysis.py` | Qwen | `POST /api/stories/{id}/continuity-check` (synchronous; see the acceptance record, R10) |
| P2-06 | Story Bible Generator | `story_bible.py` | Qwen (5 sections) | `POST/GET /api/stories/{id}/story-bible`, `POST …/story-bible/sections/{section}`, `GET …/story-bible/export` |
| P2-07 | Narrative Thread Tracker | `narrative_threads.py` | Qwen | `POST …/narrative-threads/scan`, `GET …/narrative-threads`, `PATCH …/narrative-threads/{thread_id}` |
| P2-08 | Style Drift Detection | `analysis.py` | BGE-M3 centroids + Qwen | `POST /api/stories/{id}/style-drift` |
| P2-09 | Pacing Goals | `pacing.py` | none | `POST/GET /api/stories/{id}/pacing-goals` |
| P2-10 | Duplicate Scene Detection | `analysis.py` | BGE-M3 + pgvector | `POST /api/stories/{id}/duplicate-scenes` |
| P2-11 | Audio Transcription | `audio.py` | faster-whisper + Qwen | `POST /api/stories/{id}/audio`, `GET …/audio/{audio_id}`, `POST …/audio/{audio_id}/confirm` |

OCR (`POST /api/ocr/extract/{story_id}`, `routers/ocr.py`, GOT-OCR2.0) is a **Phase 1** feature, not a Phase 2 task. Extraction works since Stage 12 A2 (2026-10-02): `ocr_service._ensure_got_cache_compat()` restores two cache members GOT-OCR2.0's vendored code needs from the pinned transformers. History: `docs/issues-and-bugs/ocr-extraction-got-ocr2-dynamiccache-failure.md`. GOT-OCR needs a GPU; handwriting quality is not measured.

## Phase 2 New DB Tables

`story_bibles` — generated story bible (bible_id, story_id, user_id, content_json, version, created_at, updated_at)
`audio_uploads` — transcription records (audio_id, story_id, user_id, note_id, audio_path, status, raw_transcript, cleaned_text, language_detected, duration_seconds, confidence, word_count, confirmed, created_at, updated_at)
`pacing_goals` — per-story pacing target (goal_id, story_id, user_id, target_words_per_chapter, target_chapters, target_total_words, deadline, created_at, updated_at)

## Database Migrations (Alembic)

Current chain: **23 migration files**, head **`0027`**:
`0001 → 0002 → 0007 → 0008 → … → 0027`

Revisions `0003`–`0006` were never created. The chain is unbroken, because `0007` sets `down_revision = "0002"`, but the numbering gap looks like missing files when auditing. The Phase 1 Production Implementation Report's `0003_story_bibles` / `0004_narrative_threads` / `0005_pacing_goals` names are wrong; the files are `0008`–`0010`.

| Revision | Adds | Origin |
|---|---|---|
| `0001` | HNSW vector indexes | Phase 1 |
| `0002` | `manuscript_jobs` | Phase 1 |
| `0007` | Story Intelligence (23 tables) | Phase 1 |
| `0008` | `story_bibles` | Phase 2 (P2-06) |
| `0009` | `narrative_threads` | Phase 2 (P2-07) |
| `0010` | `pacing_goals` | Phase 2 (P2-09) |
| `0011` | `audio_uploads` | Phase 2 (P2-11) |
| `0012` | voice agent tables | voice agent |
| `0013` | `activity_events` | activity feed |
| `0014` | story intake analysis | intake |
| `0015` | `story_bibles.status` | Stage 3 (3.2) |
| `0016` | `story_bibles.failed_sections` | Stage 3 (3.2) |
| `0017` | chapter-summary arc / relationship fields | Stage 4 (4.5) |
| `0018` | `story_preservation_settings` | Stage 5 |
| `0019` | `ai_generation_pins` | Phase 3 (Stage 7) |
| `0020` | AI preference columns on `story_preservation_settings` | Phase 3 (Stage 7) |
| `0021` | Idea Shelf columns on `note_cards` | Phase 3 (Stage 7) |
| `0022` | `users.plan` | Phase 3 (Stage 7) |
| `0023` | `narrative_thread_scans`, `manuscript_reports` | Stage 5 live-review fixes D1/D2 |
| `0024` | `users.token_version`, `revoked_sessions`, `error_events` | Stage 10 |
| `0025` | `story_bibles.source_fingerprint` (Story Bible stale warning) | Stage 11 (P2-06) |
| `0026` | Records in Alembic four columns that only `create_all()` / the startup guard ever created (`character_profiles.goals`, `.traits`, `chapter_chunks.character_ids`, `chapter_summaries.character_ids`). Guarded no-op where present; downgrade deliberately keeps them (author data) | Stage 11 (R11) |
| `0027` | `characters.presence` (on page / mentioned only / in the past), separate from life status | Stage 12 A10 |

The Phase 3 spec numbered its migrations `0016`–`0019`; they were renumbered `0019`–`0022` at implementation (decision C7-1).

All migrations are idempotent and reversible. Never hand-apply raw `ALTER TABLE` to a live database. Write migrations by hand with `_table_exists` / `_index_exists` / `_column_exists` guards (template: `0011_audio_uploads.py`). This matters because `start-narratiq.sh` runs `create_all()` **before** `alembic upgrade head`, so every migration must tolerate objects that already exist.

Use `alembic check` (or `alembic revision --autogenerate` into a scratch file) only as a **drift check** (Stage 7 decision C7-3). It reports pre-existing index-only drift from migrations 0001–0013 (indexes not declared in the models).

Tests:
- **Round trip on a populated test database:** `DATABASE_URL=…/narratiq_test bash backend/tests/run_migration_roundtrip.sh`
- **Full downgrade walk:** `backend/tests/run_downgrade_walk.py`

## Phase 2 AI Model Usage

| Feature | Primary Model | Why |
|---------|--------------|-----|
| Emotional arc | Qwen | Per-chapter emotional tone classification |
| Continuation | Qwen | Generative text continuation (3 options) |
| Duplicate detection | BGE-M3 + pgvector | Vector similarity, no generation needed |
| Style drift | BGE-M3 centroids + pgvector + Qwen | Centroid average (numpy), cosine via pgvector, Qwen for description |
| Voice check | BGE-M3 + pgvector + Qwen | Pairwise cosine via pgvector (`vector_math.cosine_pairs`), then Qwen describes the flagged pairs |
| Story bible | Qwen | 5 section generation (characters/locations/timeline/world_rules/themes) |
| Outline | Qwen | Beat-by-beat scene breakdown |
| Continuity | Qwen | Cross-chapter consistency analysis |
| Audio transcript | faster-whisper-large-v3-turbo | CTranslate2 in-process via `audio_service.py` |
| Audio cleanup | Qwen | Filler removal, paragraph formatting post-Whisper |

**Similarity note (R12, Stage 11):** the voice check, thread-name clustering and style drift compute every similarity with pgvector through `services/vector_math.py`. Style drift's representative passages are retrieved with `ORDER BY embedding <=> centroid`. numpy only averages the centroid vectors.

## Phase 2 Runtime Requirements

- `faster-whisper` installed via pip (CTranslate2 backend). Model: `deepdml/faster-whisper-large-v3-turbo-ct2` at a pinned revision (`config.whisper_model_id`), because `Systran/faster-whisper-large-v3-turbo` now returns 401. It runs on CPU, int8 (`whisper_device`, `whisper_compute_type`), and `start-narratiq.sh` STEP 2 downloads it to `/workspace/models/faster-whisper-large-v3-turbo`
- Model loaded lazily on first audio transcription call (`_whisper_model: WhisperModel | None = None` pattern)
- Audio uploads are stored in `settings.upload_dir_audio` (default `uploads/audio`, relative to `backend/`). The directory is created at startup, not committed, and must be writable
- Audio max size: 100 MB (enforced via Content-Length header pre-check before body read, then byte count after read)
- Story bible concurrent generation guard: `_generating: set[str]` in `story_bible.py` prevents duplicate Qwen calls for same story

## Studio Frontend Architecture (Stage 8)

The editor is a set of workspaces under `/projects/[id]/`: Write, Plan, Characters, World, Analyze, Assistant, Publish. Each tool has exactly one home, listed in `lib/registries/toolHomes.ts` and enforced by `tests/tool-homes.spec.ts`. Plan (plot, pacing) and World (bible, notes + Idea Shelf, OCR) use `components/studio/SectionTabs.tsx` with `?section=` deep links. Analyze tools come from `lib/registries/panels.tsx`. The Command Palette (Ctrl/⌘K) reads `lib/registries/actions.ts`.

- Write: binder, editor, AI sidecar (`AIToolsSidebar`, groups Rewrite / Generate / Versions), Search & replace (Ctrl/⌘F). Draft/Edit mode per story (Edit is the default); Reading mode is read-only and sends no saves; View menu has Focus, Zen, Typewriter, Fullscreen. Ctrl+\\ expands the sidecar.
- Layout sizes, modes and last sections persist in `lib/studioStore.ts`, keyed per user (`narratiq_studio:<user_id>`) and bound by `StudioStoreGate` in the project layout.
- Panels and sections are lazy-loaded with `next/dynamic` (`ssr: false`).
- `AuditPanel` was dead code and was removed in Stage 8.
- Tests: `tests/studio/` runs against a mocked API (build with `NEXT_PUBLIC_API_URL=http://mock-api.test`; separate `NEXT_DIST_DIR` so the real `.next` is never touched). Includes axe (zero serious/critical), a 1920→768 viewport matrix and build variants (`STUDIO_VARIANT=mock-tool|p3-off`). The live specs in `tests/browser/` still need a pod.

Bundle (Stage 8, `next build`): `/projects/[id]/write` **128 kB** page-specific, **290 kB** First Load JS (baseline on `main`: 129 kB / 262 kB). The First Load rise is mostly accounting: the Radix menu chunk (≈26 kB gzip) the project layout already loaded is now also imported by the Write page, so Next counts it for the route. Gzipped JS a browser downloads on a cold Write load went from 313.0 kB to 318.2 kB (+5.2 kB).

`ChunkLoadError` auto-recovery is in `components/chunk-error-recovery.tsx` (window error listener + sessionStorage 10s debounce to prevent loops).

## Production Hardening (completed)

> Earlier revisions titled this section "Production Hardening (Phase 3)". It is **not** Phase 3. "Phase 3" always means the feature phase **Phase 3 — Author-Centric AI Workflow** (section below). This hardening pass predates Stages 0–12.

**8 hardening items implemented. All configurable via `.env` / `config.py`. No hardcoded values.**

### New Files

| File | Purpose |
|------|---------|
| `backend/exceptions.py` | `AIServiceUnavailableError` (→ 503) and `UploadTooLargeError` (→ 413) |
| `backend/logger.py` | `setup_logging()` — text/JSON formatter, called first in `main.py` |
| `backend/middleware/rate_limit.py` | slowapi `Limiter` singleton + `get_user_id()` per-user key function (session cookie or Bearer) |
| `backend/middleware/upload_guard.py` | `enforce_upload_size()` — Content-Length pre-check + post-read byte guard |
| `backend/middleware/concurrency.py` | `bg_ai_semaphore()` and `embedding_semaphore()` — lazy-init singletons |
| `backend/startup/orphan_recovery.py` | `recover_orphaned_jobs()` — startup sweep of stuck AudioUpload / ManuscriptJob / StoryIntelJob |

### New `.env` Variables (all optional, have sensible defaults)

| Variable | Default | Purpose |
|----------|---------|---------|
| `RATE_LIMIT_AUTH` | `5/minute` | Login + register per client IP |
| `RATE_LIMIT_REALTIME_AI` | `20/minute` | All ai_transform endpoints per-user |
| `RATE_LIMIT_HEAVY_AI` | `5/minute` | Continuity, analysis, plot-holes, intake per-user |
| `RATE_LIMIT_BACKGROUND_AI` | `3/minute` | Story bible, narrative threads per-user |
| `RATE_LIMIT_UPLOAD` | `10/minute` | Audio/OCR/manuscript upload per-user |
| `MAX_AUDIO_UPLOAD_MB` | `100` | Audio upload hard limit |
| `MAX_OCR_UPLOAD_MB` | `50` | OCR upload hard limit |
| `MAX_MANUSCRIPT_UPLOAD_MB` | `25` | Manuscript upload hard limit |
| `UPLOAD_DIR_AUDIO` | `uploads/audio` | Local audio storage path (swap for S3 prefix) |
| `UPLOAD_DIR_OCR` | `uploads/ocr` | Local OCR storage path |
| `BG_AI_CONCURRENCY` | `3` | Max concurrent Qwen background tasks |
| `EMBEDDING_CONCURRENCY` | `2` | Max concurrent BGE-M3 background tasks |
| `JWT_EXPIRE_MINUTES` | `10080` | Session lifetime (7 days): JWT `exp` and session-cookie max-age |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG/INFO/WARNING/ERROR) |
| `LOG_FORMAT` | `text` | `text` for dev, `json` for production log aggregators |

Variables added after this pass are declared in `config.py`; most are mirrored in `.env.example`. Examples: `OPS_TOKEN`, `TRUSTED_PROXY_CIDRS`, `ALLOW_MULTI_WORKER` and the session/CSRF cookie names (Stage 10); `PLAN_LIMITS_JSON` (Phase 3); and the shell-only hooks `NARRATIQ_OFFPOD_COMMAND` / `NARRATIQ_ALERT_COMMAND` read by `scripts/periodic_backup_loop.sh` and `scripts/watchdog.py`.

### Rate Limiting Architecture

- **slowapi** wraps the `limits` library. **Storage is unconditionally in-memory.** The module-level `limiter = Limiter(key_func=get_remote_address)` in `middleware/rate_limit.py` has no `storage_uri`, and `SLOWAPI_STORAGE_URI` is read by nothing. Storage is per-process, which is correct only because exactly one worker runs (D-3, enforced by `startup/worker_guard.py`)
- Auth endpoints: per client IP. `get_remote_address` is the module's own function (not slowapi's) and calls `client_ip()`, which reads `CF-Connecting-IP` / `X-Forwarded-For` **only** when the TCP peer is inside `TRUSTED_PROXY_CIDRS` (Stage 10)
- All AI and upload endpoints: per-user key from the JWT `sub` (session cookie or Bearer header), falling back to the client IP if the token is absent or invalid
- Global handler: `RateLimitExceeded` → HTTP 429 with `Retry-After` header

### AI Error Handling

- `_complete()` and `_stream_generate()` in `ai_service.py` catch `APIConnectionError` → `AIServiceUnavailableError`
- `APIStatusError` with status 429/500/502/503/504 → `AIServiceUnavailableError`
- Global handler returns HTTP 503 `{"detail": "...", "retry_after": 30}`
- Background tasks catch `AIServiceUnavailableError` → sets DB record status to `failed`/`error`

### Background AI Concurrency

- `bg_ai_semaphore` (default=3): guards all Qwen background calls in audio, manuscript, chapters, story_bible, narrative_threads, story_intel_orchestrator, ocr
- `embedding_semaphore` (default=2): guards BGE-M3 calls in ocr `_embed_*` functions
- Both are lazy-init module singletons — replaceable with Redis/Celery locks without changing call sites

### Orphan Job Recovery

Runs at startup (first step in `lifespan()`), before model loading:
- `AudioUpload` status=`processing` → `failed`
- `ManuscriptJob` status=`processing` → `error`
- `StoryIntelJob` status in `(pending, running)` → `error`

### JWT Staging Plan (Deferred)

Hardening pass (step A): removed hardcoded `ALGORITHM`/`ACCESS_TOKEN_EXPIRE_MINUTES` from `routers/auth.py`. Both are now configurable.
Phase B: **done in Stage 10 (task 10.7)** — HttpOnly cookie sessions, CSRF, server-side revocation; see "Auth (Stage 10)" above.

### Bugs Fixed

- `clean_transcript()` in `audio_service.py`: `_complete(prompt, max_tokens=1024)` was missing the required `user` arg — transcript cleaning never ran. Fixed to `_complete(system=system, user=raw_text[:3000], max_tokens=1024)`.

### Migration Notes

- **Redis**: moving rate limits to Redis **requires a code change**: pass `storage_uri=` to the `Limiter` in `middleware/rate_limit.py`. Earlier revisions of this file claimed `SLOWAPI_STORAGE_URI` did this with zero code changes; that was never true
- **Celery**: Replace `asyncio.create_task()` calls with Celery `.delay()` — semaphore guards can be replaced with Celery worker concurrency limits
- **S3/R2**: Change `UPLOAD_DIR_AUDIO` and `UPLOAD_DIR_OCR` env vars to bucket prefixes; swap `open()` calls for boto3 client

## Phase 3 — Author-Centric AI Workflow (implemented in Stage 7)

Spec: `docs/phases/phase-3-planned/phase-3-author-centric-ai-workflow.md`. The folder name `phase-3-planned/` is historical and kept so existing links resolve; the phase **is implemented**. Product rule R1: **unpinned generations are never stored** (session history lives only in the browser, `lib/generationStore.ts`, not persisted).

| ID | Capability | Where |
|----|-----------|-------|
| P3-01 | Temporary pins | `routers/ai_workspace.py` (`/api/stories/{id}/ai/pins…`), `services/pin_store.py`, `services/plans.py` |
| P3-02 | Sentence locks / partial regeneration | Stage 5 engine: `services/transform_preservation.py` + `ai_service._run_constrained_transform` (`locked_ranges`) |
| P3-03/06/07/08/10 | Pins as context, generate from a version, avoid-set, consistency, voice | optional `controls` on `/api/ai/{tone,emotion,age-adapt,style}` → `services/generation_context.py` (the ONLY place Phase 3 prompt context is assembled), `services/consistency.py` |
| P3-04 | Compare & merge | `frontend/lib/diff.ts` (client-side), `/api/ai/compare-summary`, `/api/ai/merge-versions` (`services/version_tools.py`) |
| P3-05 | Preservation rules | `/api/stories/{id}/ai/preferences`; checks in `transform_preservation.verify_preservation` (heuristics warn-only by default) |
| P3-09 | Idea Shelf | `note_cards` + idea types; filters on `/api/ocr/{story_id}/note-cards`; `components/ideas/*` |
| P3-11 | Similarity | `services/similarity.py`, `POST /api/stories/{id}/ai/similarity` |

- **Ownership:** every Phase 3 id goes through `services/ownership.py` — foreign and non-existent ids are indistinguishable (same 404; one generic warning for batch ids). `/api/ai/*` also verifies `story_id` ownership.
- **Tables:** `ai_generation_pins` (new, `0019`); `story_preservation_settings` +3 JSON prefs (`0020`); `note_cards` +`target_chapter_id`/`tags`/`status`/`source_pin_id` (`0021`); `users.plan` (`0022`, NULL = free; assigned manually for now — decision D2).
- **Pin content** is read/written only via `PinContentStore` (`get_pin_store()`); pins are excluded from RAG and from logical backups (`--exclude-table-data=public.ai_generation_pins` in both backup scripts, decision D9).
- **Expiry:** `main._cleanup_expired_pins()` runs at startup and hourly inside `_run_periodic_cleanup()`; it logs `[pin_cleanup] cleanup_rows=N` every run, and `[pin_metrics]` daily (storage-growth triggers, spec §16.3).
- **Settings:** 30 fields in `config.py` under "Phase 3 — generation management", mirrored in `.env.example`. Plan limits: `services/plans.py` defaults (decision D1), overridable with `PLAN_LIMITS_JSON` (validated at import — a malformed value stops startup).
- **Frontend:** Versions tab and rules panel in `AIToolsSidebar`; pin / Idea Shelf / similarity actions on results (`components/generation/*`); compare dialog lazy-loaded in the Write workspace. Build with `NEXT_PUBLIC_P3_ENABLED=false` to switch the Phase 3 UI off (rollback).
- **Errors:** Phase 3 raises `exceptions.ApiError` → flat `{detail, code, …}` bodies (e.g. `pin_limit_reached` 409 with `oldest_pin`, `pin_too_large` 413, `too_many_context_pins` 422, `no_unlocked_segments` 422).

## Config Gotchas

**vLLM port.** `config.vllm_base_url` defaults to `http://127.0.0.1:9001/v1`, matching `VLLM_PORT=9001` in `start-narratiq.sh`. The default moved from 8001 to 9001 in commit `b0f64be`; earlier revisions of this file said otherwise. **You do not need to set `VLLM_BASE_URL`.**

Nothing in the repository still defaults to 8001: the legacy `start.sh` was deleted (decision D-2), and `scripts/verify_runpod_setup.sh` defaults to `VLLM_PORT=9001`. History: `docs/operations/runpod-environment-variables.md` §10.

**Environment precedence.** `pydantic-settings` resolves `OS env vars > backend/.env > field defaults`. `start-narratiq.sh` force-overwrites `DATABASE_URL`, `VLLM_BASE_URL`, `VLLM_MODEL_NAME` and `CORS_ORIGINS` in `backend/.env` on every run, but **a value left in the RunPod UI silently overrides all of them** for any manually started backend. A stale `VLLM_BASE_URL=…:8001/v1` is the classic cause of "healthy backend, every AI call 503".

**`.env` path is relative.** `Settings.model_config` sets `env_file: ".env"`, resolved against the current working directory — always start the backend from `backend/`.

**`extra="forbid"`.** `Settings` rejects any `.env` key that is not a declared field, with a non-empty value, at import time. Adding a key to `backend/.env` without adding the field to `config.py` will prevent the backend from starting.

`SECRET_KEY` is a **required** env var with no default. The backend refuses to start without it (validator rejects keys shorter than 32 chars). `start-narratiq.sh` auto-generates one into `backend/.env` on first run if absent. To generate manually: `python3 -c "import secrets; print(secrets.token_hex(32))"`. JWT tokens are signed with this key — changing it invalidates all active sessions.

## Stages 3–9: where the work landed

Full evidence for each stage is in `docs/NarratIQ_Master_Implementation_Checklist.md`.

| Stage | What changed in the code | Where |
|---|---|---|
| 3 — Phase 2 defects | Retrieval call-signature fix (continuation/outline); Story Bible `completed`/`partial`/`failed` per-section status, `failed_sections` and per-section retry; `_extract_json` hard-fail audit; voice-agent action execution and honest success reporting | `routers/writing_tools.py`, `routers/story_bible.py` (`derive_status`), `services/ai_service.py`, `services/voice/`; migrations `0015`, `0016` |
| 4 — Retrieval correctness | Plot Assistant chapter-scoped by default with a full-manuscript option (D-1); chapter-capped character evidence; character merge; search fixes; arc/relationship summary fields | `routers/plot_assistant.py`, `services/character_merge.py`, `routers/search.py`; migration `0017` |
| 5 — Generation quality | Versioned prompts (`v1` frozen baseline, `v2`; later `v3`, and `v4` — the default since Stage 12 A15, with `v2` as the fallback); the preservation engine (sentence locks, strength control, name/glossary preservation); suggestions and Story Audit overhaul | `services/prompt_registry.py`, `services/transform_preservation.py`, `services/narrative_signals.py`, `timeline_signals.py`, `relationship_arcs.py`; migrations `0018`, `0023` |
| 6 — Test automation | Backend/frontend regression suites; CI deferred (6.1) | `backend/tests/run_full_regression.sh`, `frontend/tests/` |
| 7 — Phase 3 | See "Phase 3 — Author-Centric AI Workflow" above | migrations `0019`–`0022` |
| 8 — Studio UI | See "Studio Frontend Architecture" above | `frontend/app/(dashboard)/projects/[id]/` |
| 9 — Regression, security, UAT | Cross-user isolation fixes I1–I7; upload/CORS fixes; `author` field length cap; security and prompt-injection probes | `backend/tests/test_security_stage9.py`, `backend/scripts/security/`; results in `docs/testing/stage-09-*.md` |

## Stage 10 — Production readiness (2026-09-29)

| Area | Where |
|------|-------|
| Backups: snapshot dump + integrity manifest (per-table content hashes, vectors included) + uploads archive; restore verification into `narratiq_restorecheck`; GFS retention; off-pod copy **deferred** (hook `NARRATIQ_OFFPOD_COMMAND`) | `scripts/backup_snapshot.py`, `verify_backup.py`, `backup_retention.py`, `periodic_backup_loop.sh`; runbook `docs/operations/backup-and-restore.md` |
| Monitoring: live `/api/health`, `/api/ops/{status,metrics,errors}` (header `X-Ops-Token` = `OPS_TOKEN`), built-in scrubbed error tracking (`error_events`), request ids, JSON logs, watchdog → `/workspace/logs/alerts.jsonl` (no external channel, S10-D) | `routers/ops.py`, `services/error_tracking.py`, `middleware/request_context.py`, `scripts/watchdog.py`; `docs/operations/monitoring-and-alerting.md` |
| Containers (dev; RunPod stays production) | `backend/Dockerfile`, `frontend/Dockerfile`, `docker-compose.yml`, `scripts/verify_containers.sh`; `docs/operations/containers.md` |
| One worker enforced; `--no-proxy-headers`; rate-limit key = `CF-Connecting-IP` from trusted proxies | `startup/worker_guard.py`, `middleware/rate_limit.py` (`TRUSTED_PROXY_CIDRS`) |
| Rollback: downgrade walk test, pinned model revisions, `.next.prev` + `scripts/rollback_frontend.sh` | `docs/operations/rollback.md`, `model-versions.md`, `backend/tests/run_downgrade_walk.py` |
| Account deletion (`DELETE /api/auth/account`), chapter-deletion fix, orphan upload sweep, published policy (`/data-policy`) | `services/account_deletion.py`, `docs/policies/data-retention-and-deletion.md` |
| Sessions / CSRF / WS tickets | `routers/auth.py`, `middleware/csrf.py`, migration `0024` |
| Incident response, severity levels, postmortem template | `docs/operations/incident-response.md`, `docs/incidents/TEMPLATE.md` |

`backend/requirements.txt` is now the single source of truth (equals the pod runtime); `start-narratiq.sh` installs from it and uses `npm ci`. Migration `0024` = `users.token_version`, `revoked_sessions`, `error_events`.

**Shell gotcha found in Stage 10:** never `pkill -f`/`pgrep -f` a pattern like `next start` or `uvicorn main:app` from an interactive tool command — the tool's own command line contains the pattern and gets killed. Use PID files (`/tmp/narratiq-logs/*.pid`) or run the kill from a script file.
