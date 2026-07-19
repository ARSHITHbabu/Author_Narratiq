# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Service Commands

```bash
# Start everything (handles installs, patches, vLLM, backend, frontend)
bash /workspace/narratiq-ai/start-narratiq.sh

# Manual vLLM start (NVIDIA Blackwell GPUs require these NCCL flags)
NCCL_P2P_DISABLE=1 NCCL_SHM_DISABLE=1 python3 -m vllm.entrypoints.openai.api_server \
  --model /workspace/models/Qwen2.5-7B-Instruct \
  --served-model-name "Qwen/Qwen2.5-7B-Instruct" \
  --dtype auto --gpu-memory-utilization 0.90 \
  --tensor-parallel-size 2 --max-model-len 16384 \
  --host 0.0.0.0 --port 9001

# Backend
cd backend && python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1

# Frontend
cd frontend && npm run dev

# Frontend environment (RunPod proxy URL) — written automatically by start-narratiq.sh.
# NEXT_PUBLIC_API_URL is inlined at BUILD time; changing it requires `npm run build`.
echo 'NEXT_PUBLIC_API_URL=https://{POD_ID}-8000.proxy.runpod.net' > frontend/.env.local
```

**Environment variables:** `start-narratiq.sh` generates everything mandatory. At most two are worth setting in the RunPod UI (`SECRET_KEY`, `HF_TOKEN`), and several stale ones actively break the app. Full analysis — precedence, generated values, obsolete variables, recovery workflow — in [`docs/RUNPOD_ENVIRONMENT_VARIABLE_RECOVERY.md`](docs/RUNPOD_ENVIRONMENT_VARIABLE_RECOVERY.md).

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

**Three-service stack:** vLLM (port 9001) → FastAPI backend (port 8000) → Next.js 14 frontend (port 3000).

**Backend startup sequence** (`main.py` `lifespan`): orphan-job recovery → upload dirs → model paths validated → BGE-M3 loaded synchronously via `get_bge()` → voice capability index → pgvector self-check → vLLM health check → warmup request → ready.

Only two conditions are hard failures (`RuntimeError`): **missing model weights** (`main.py:178-186`) and a **broken pgvector query path** (`main.py:221-226`). If vLLM is unreachable the backend logs a warning, sets `app.state.llm_ready = False` and **continues in degraded mode** (`main.py:235-241`) — `/api/health` reports `"vllm": "unavailable"` and AI endpoints return 503.

**AI text generation:** All LLM calls go through `_complete()` / `_stream_generate()` in `backend/services/ai_service.py` via the OpenAI-compatible vLLM endpoint. Model: `Qwen2.5-7B-Instruct`.

**Embeddings:** BGE-M3 (1024-dim) runs in-process via `sentence-transformers`. Embeddings stored as `vector(1024)` columns (pgvector) on `chapter_chunks`, `chapter_summaries`, `character_profiles` (×2), `story_notes`, and `note_cards`. Retrieval uses pgvector HNSW indexes with the `<=>` cosine distance operator via raw SQL — numpy cosine is no longer used.

**Database:** PostgreSQL 16 + pgvector + SQLAlchemy ORM. Connection pool: `pool_size=10, max_overflow=20`. Key tables: `stories`, `chapters`, `chapter_chunks` (350-word overlap chunks for RAG), `chapter_summaries`, `characters`, `character_profiles`, `character_relationships`. Alembic manages schema migrations (`backend/migrations/`). `start-narratiq.sh` runs `Base.metadata.create_all()` then `alembic upgrade head` before FastAPI starts.

**Background tasks:** `asyncio.create_task()` — no Redis or external queue. Used for re-embedding after profile updates.

**Auth:** JWT in `localStorage['narratiq_token']`. 401 interceptor in `frontend/lib/api.ts` clears token and redirects to `/login`.

**Character RAG:** Hybrid retrieval — cosine similarity on BGE-M3 embeddings + name-mention boost. 800-token budget cap per context window.

## Blackwell GPU Notes

The pod has 2× NVIDIA RTX PRO 4500 Blackwell (sm_120) GPUs. These require:
- vLLM **0.9.2+** (first release with sm_120 support)
- PyTorch **2.7.0+cu128** — the cu124/cu126 builds top out at sm_90
- `NCCL_P2P_DISABLE=1 NCCL_SHM_DISABLE=1` to prevent NCCL deadlock at init
- Clear `~/.cache/vllm/torch_compile_cache` after any failed start before retrying
- `ovis.py` patch: all `AutoConfig.register()` calls need `exist_ok=True` (transformers 4.51+ pre-registers these types). The startup script applies this patch automatically via `sed`.

## Key Files

| File | Purpose |
|------|---------|
| `backend/services/ai_service.py` | All LLM + BGE-M3 calls; `_complete()`, `_stream_generate()`, `get_bge()` |
| `backend/services/audio_service.py` | faster-whisper transcription + Qwen transcript cleanup |
| `backend/routers/audio.py` | Phase 2: audio upload → faster-whisper → Qwen cleanup → note append |
| `backend/routers/story_bible.py` | Phase 2: 5-section story bible generation via Qwen; DOCX export |
| `backend/routers/analysis.py` | Phase 2: emotional arc, duplicate scenes, style drift, continuity |
| `backend/routers/writing_tools.py` | Phase 2: chapter continuation (`:61`) **and** outline / beat sheet (`:145`) — there is no `continuation.py` or `outline.py` |
| `backend/routers/characters.py` | Character CRUD, relationships, **and** voice consistency via `check_dialogue_consistency` (`:1197,:1293`) — there is no `voice.py` |
| `backend/routers/voice_agent.py` | Real-time voice agent (WS + REST). **Different feature** from the P2-05 dialogue checker above — do not confuse the two |
| `backend/routers/pacing.py` | Phase 2: pacing goal setting + chapter progress tracking |
| `backend/models.py` | SQLAlchemy ORM models (full schema) |
| `backend/schemas.py` | Pydantic request/response schemas |
| `backend/config.py` | Settings loaded from `.env` via pydantic-settings (56 fields). `vllm_base_url` defaults to **9001**, matching `start-narratiq.sh`. `secret_key` is the only field with no default |
| `frontend/lib/api.ts` | Typed API client wrappers; JWT interceptor |
| `frontend/lib/types.ts` | TypeScript interfaces for all domain objects |
| `frontend/app/(dashboard)/projects/[id]/page.tsx` | 3-column editor layout; all 10 right panels lazy-loaded via `next/dynamic` |
| `frontend/app/(dashboard)/projects/[id]/error.tsx` | Next.js error boundary for the editor route |
| `frontend/components/chunk-error-recovery.tsx` | Auto-reload on ChunkLoadError; sessionStorage debounce to prevent loops |
| `start-narratiq.sh` | Full bootstrap: pip installs, ovis.py patch, numpy pin, cache clear, service launch |

## Phase 2 Features (P2-01 → P2-11)

| ID | Feature | Backend Router | AI Model | Endpoint Pattern |
|----|---------|---------------|----------|-----------------|
| P2-01 | Emotional Arc Analysis | `analysis.py` | Qwen | `GET /stories/{id}/emotional-arc` |
| P2-02 | Chapter Continuation | `continuation.py` | Qwen | `POST /stories/{id}/chapters/{id}/continue` |
| P2-03 | Scene Duplicate Detection | `analysis.py` | BGE-M3 + pgvector | `GET /stories/{id}/duplicate-scenes` |
| P2-04 | Style Drift Analysis | `analysis.py` | BGE-M3 centroids + Qwen | `GET /stories/{id}/style-drift` |
| P2-05 | Character Voice Check | `voice.py` | BGE-M3 + Qwen | `POST /stories/{id}/voice-check` |
| P2-06 | Story Bible Generator | `story_bible.py` | Qwen (5 sections) | `POST/GET /stories/{id}/story-bible` |
| P2-07 | Outline / Beat Sheet | `outline.py` | Qwen | `POST /stories/{id}/chapters/{id}/outline` |
| P2-08 | Continuity Check | `analysis.py` | Qwen | `GET /stories/{id}/continuity-check` |
| P2-09 | Pacing Goals | `pacing.py` | — (no AI) | `POST/GET /stories/{id}/pacing-goal` |
| P2-10 | OCR Inject | `ocr.py` | Tesseract/vision | `POST /stories/{id}/ocr` |
| P2-11 | Audio Transcription | `audio.py` | faster-whisper + Qwen | `POST /stories/{id}/audio` |

## Phase 2 New DB Tables

`story_bibles` — generated story bible (bible_id, story_id, user_id, content_json, version, created_at, updated_at)
`audio_uploads` — transcription records (audio_id, story_id, user_id, note_id, audio_path, status, raw_transcript, cleaned_text, language_detected, duration_seconds, confidence, word_count, confirmed, created_at, updated_at)
`pacing_goals` — per-story pacing target (goal_id, story_id, user_id, target_words_per_chapter, target_chapters, target_total_words, deadline, created_at, updated_at)

## Phase 2 Migrations (Alembic)

Current chain (15 migrations): `0001 → 0002 → 0007 → 0008 → 0009 → 0010 → 0011 → 0012 → 0013 → 0014 → 0015`

Revisions `0003`–`0006` were never created. The chain is unbroken — `0007` sets `down_revision = "0002"` — but the numbering gap looks like missing files when auditing.

- `0008` — `story_bibles`
- `0009` — `narrative_threads`
- `0010` — `pacing_goals`
- `0011` — `audio_uploads`
- `0012` — voice agent tables
- `0013` — `activity_events`
- `0014` — story intake analysis
- `0015` — story bible status

All migrations are idempotent and reversible. Always use `alembic revision --autogenerate` for new schema changes — never raw `ALTER TABLE`.

## Phase 2 AI Model Usage

| Feature | Primary Model | Why |
|---------|--------------|-----|
| Emotional arc | Qwen | Per-chapter emotional tone classification |
| Continuation | Qwen | Generative text continuation (3 options) |
| Duplicate detection | BGE-M3 + pgvector | Vector similarity, no generation needed |
| Style drift | BGE-M3 centroids + Qwen | Centroid math for drift score, Qwen for description |
| Voice check | BGE-M3 + pgvector + Qwen | Embedding similarity for inconsistency detection |
| Story bible | Qwen | 5 section generation (characters/locations/timeline/world_rules/themes) |
| Outline | Qwen | Beat-by-beat scene breakdown |
| Continuity | Qwen | Cross-chapter consistency analysis |
| Audio transcript | faster-whisper-large-v3-turbo | CTranslate2 in-process via `audio_service.py` |
| Audio cleanup | Qwen | Filler removal, paragraph formatting post-Whisper |

**Style drift centroid note:** `numpy` is used legitimately in `analysis.py` for computing centroid vectors (average across early/late chapter embedding arrays). This is not cosine retrieval — it's math to produce a single representative vector before calling pgvector `<=>`. This is the ONLY approved numpy usage; all retrieval must use pgvector SQL.

## Phase 2 Runtime Requirements

- `faster-whisper` installed via pip (CTranslate2 backend) — model: `Systran/faster-whisper-large-v3-turbo`
- Model loaded lazily on first audio transcription call (`_whisper_model: WhisperModel | None = None` pattern)
- Audio uploads stored at `backend/uploads/audio/` — ensure this path is writable on RunPod
- Audio max size: 100 MB (enforced via Content-Length header pre-check before body read, then byte count after read)
- Story bible concurrent generation guard: `_generating: set[str]` in `story_bible.py` prevents duplicate Qwen calls for same story

## Phase 2 Frontend Architecture

All 10 right-panel components in `/projects/[id]/page.tsx` are loaded via `next/dynamic` with `ssr: false`:
- `AIToolsSidebar`, `PlotAssistantPanel`, `OCRPanel`, `NotesPanel`, `CharacterList`
- `AuditPanel`, `StoryBiblePanel`, `PacingGoalPanel`, `AudioPanel`, `SearchPanel`

Bundle sizes after lazy loading:
- `/projects/[id]`: **108 kB** page-specific, **235 kB** First Load JS  ← was 143 kB / 270 kB before Phase 2 hardening
- Panels are cached after first load; tab switching after that is instant

`ChunkLoadError` auto-recovery is in `components/chunk-error-recovery.tsx` (window error listener + sessionStorage 10s debounce to prevent loops).

## Production Hardening (Phase 3)

**8 hardening items implemented. All configurable via `.env` / `config.py`. No hardcoded values.**

### New Files

| File | Purpose |
|------|---------|
| `backend/exceptions.py` | `AIServiceUnavailableError` (→ 503) and `UploadTooLargeError` (→ 413) |
| `backend/logger.py` | `setup_logging()` — text/JSON formatter, called first in `main.py` |
| `backend/middleware/rate_limit.py` | slowapi `Limiter` singleton + `get_user_id()` per-JWT key function |
| `backend/middleware/upload_guard.py` | `enforce_upload_size()` — Content-Length pre-check + post-read byte guard |
| `backend/middleware/concurrency.py` | `bg_ai_semaphore()` and `embedding_semaphore()` — lazy-init singletons |
| `backend/startup/orphan_recovery.py` | `recover_orphaned_jobs()` — startup sweep of stuck AudioUpload / ManuscriptJob / StoryIntelJob |

### New `.env` Variables (all optional, have sensible defaults)

| Variable | Default | Purpose |
|----------|---------|---------|
| `RATE_LIMIT_AUTH` | `5/minute` | Login + register per-IP |
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
| `JWT_EXPIRE_MINUTES` | `10080` | JWT lifetime (7 days) |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG/INFO/WARNING/ERROR) |
| `LOG_FORMAT` | `text` | `text` for dev, `json` for production log aggregators |

### Rate Limiting Architecture

- **slowapi** wraps the `limits` library. **Storage is unconditionally in-memory** — `middleware/rate_limit.py:67` constructs `Limiter(key_func=get_remote_address)` with no `storage_uri`. `SLOWAPI_STORAGE_URI` is named in comments but **read by nothing**; setting it has no effect. In-memory storage is also per-process, so limits are not shared across uvicorn workers
- Auth endpoints: per-IP (no JWT required at login time)
- All AI and upload endpoints: per-user JWT `sub` claim, falls back to IP if token absent/invalid
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

Phase 3 partial: removed hardcoded `ALGORITHM`/`ACCESS_TOKEN_EXPIRE_MINUTES` from `auth.py`. Both now configurable.
Phase B (future): HttpOnly cookie migration requires frontend auth flow changes.

### Bugs Fixed

- `clean_transcript()` in `audio_service.py`: `_complete(prompt, max_tokens=1024)` was missing the required `user` arg — transcript cleaning never ran. Fixed to `_complete(system=system, user=raw_text[:3000], max_tokens=1024)`.

### Migration Notes

- **Redis**: moving rate limits to Redis **requires a code change** — pass `storage_uri=` to the `Limiter` at `middleware/rate_limit.py:67`. Earlier revisions of this file claimed `SLOWAPI_STORAGE_URI` did this with zero code changes; that was never true
- **Celery**: Replace `asyncio.create_task()` calls with Celery `.delay()` — semaphore guards can be replaced with Celery worker concurrency limits
- **S3/R2**: Change `UPLOAD_DIR_AUDIO` and `UPLOAD_DIR_OCR` env vars to bucket prefixes; swap `open()` calls for boto3 client

## Config Gotchas

**vLLM port.** `config.py:59` defaults to `http://127.0.0.1:9001/v1`, matching `start-narratiq.sh:17`. The default moved from 8001 to 9001 in commit `b0f64be`; earlier revisions of this file said otherwise. **You do not need to set `VLLM_BASE_URL`.**

Two legacy files still reference the old port and are superseded: `start.sh:25` and `scripts/verify_runpod_setup.sh:14` (the latter reports a false failure against a working 9001 stack — override with `VLLM_PORT=9001`). This contradiction is documented, not fixed; see `docs/RUNPOD_ENVIRONMENT_VARIABLE_RECOVERY.md` §10.

**Environment precedence.** `pydantic-settings` resolves `OS env vars > backend/.env > field defaults`. `start-narratiq.sh` force-overwrites `DATABASE_URL`, `VLLM_BASE_URL`, `VLLM_MODEL_NAME` and `CORS_ORIGINS` in `backend/.env` on every run, but **a value left in the RunPod UI silently overrides all of them** for any manually started backend. A stale `VLLM_BASE_URL=…:8001/v1` is the classic cause of "healthy backend, every AI call 503".

**`.env` path is relative.** `config.py:238` sets `env_file: ".env"`, resolved against the current working directory — always start the backend from `backend/`.

**`extra="forbid"`.** `Settings` rejects any `.env` key that is not a declared field, with a non-empty value, at import time. Adding a key to `backend/.env` without adding the field to `config.py` will prevent the backend from starting.

`SECRET_KEY` is a **required** env var with no default. The backend refuses to start without it (validator rejects keys shorter than 32 chars). `start-narratiq.sh` auto-generates one into `backend/.env` on first run if absent. To generate manually: `python3 -c "import secrets; print(secrets.token_hex(32))"`. JWT tokens are signed with this key — changing it invalidates all active sessions.
