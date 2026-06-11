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

# Frontend environment (RunPod proxy URL)
echo 'NEXT_PUBLIC_API_URL=https://{POD_ID}-8000.proxy.runpod.net' > frontend/.env.local
```

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

**Backend startup sequence:** BGE-M3 loaded synchronously via `get_bge()` → vLLM health check → warmup request → ready. Backend will refuse to start if vLLM is unreachable.

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
| `backend/routers/characters.py` | Character CRUD + relationship graph endpoints |
| `backend/routers/audio.py` | Phase 2: audio upload → faster-whisper → Qwen cleanup → note append |
| `backend/routers/story_bible.py` | Phase 2: 5-section story bible generation via Qwen; DOCX export |
| `backend/routers/analysis.py` | Phase 2: emotional arc, duplicate scenes, style drift, continuity |
| `backend/routers/voice.py` | Phase 2: character voice consistency check via BGE-M3 cosine |
| `backend/routers/continuation.py` | Phase 2: chapter continuation suggestions (3 options) |
| `backend/routers/outline.py` | Phase 2: chapter outline / beat sheet generation |
| `backend/routers/pacing.py` | Phase 2: pacing goal setting + chapter progress tracking |
| `backend/models.py` | SQLAlchemy ORM models (full schema) |
| `backend/schemas.py` | Pydantic request/response schemas |
| `backend/config.py` | Settings loaded from `.env` via pydantic-settings; `vllm_base_url` defaults to port 8001 but the running instance uses **9001** |
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

Migration chain: `0001 → 0002 → 0007 → 0008 → 0009 → 0010 → 0011`
- `0008` — adds `story_bibles` table
- `0009` — adds `audio_uploads` table  
- `0010` — adds `pacing_goals` table
- `0011` — any subsequent Phase 2 schema additions

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

## Config Gotchas

`config.py` `vllm_base_url` defaults to `http://127.0.0.1:8001/v1` but the actual vLLM process listens on **9001**. The `.env` file must set `VLLM_BASE_URL=http://127.0.0.1:9001/v1` or the backend will target the wrong port.

`SECRET_KEY` is a **required** env var with no default. The backend refuses to start without it (validator rejects keys shorter than 32 chars). `start-narratiq.sh` auto-generates one into `backend/.env` on first run if absent. To generate manually: `python3 -c "import secrets; print(secrets.token_hex(32))"`. JWT tokens are signed with this key — changing it invalidates all active sessions.
