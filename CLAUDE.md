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
| `backend/routers/characters.py` | Character CRUD + relationship graph endpoints |
| `backend/models.py` | SQLAlchemy ORM models (full schema) |
| `backend/schemas.py` | Pydantic request/response schemas |
| `backend/config.py` | Settings loaded from `.env` via pydantic-settings; `vllm_base_url` defaults to port 8001 but the running instance uses **9001** |
| `frontend/lib/api.ts` | Typed API client wrappers; JWT interceptor |
| `frontend/lib/types.ts` | TypeScript interfaces for all domain objects |
| `start-narratiq.sh` | Full bootstrap: pip installs, ovis.py patch, numpy pin, cache clear, service launch |

## Config Gotchas

`config.py` `vllm_base_url` defaults to `http://127.0.0.1:8001/v1` but the actual vLLM process listens on **9001**. The `.env` file must set `VLLM_BASE_URL=http://127.0.0.1:9001/v1` or the backend will target the wrong port.

`SECRET_KEY` is a **required** env var with no default. The backend refuses to start without it (validator rejects keys shorter than 32 chars). `start-narratiq.sh` auto-generates one into `backend/.env` on first run if absent. To generate manually: `python3 -c "import secrets; print(secrets.token_hex(32))"`. JWT tokens are signed with this key — changing it invalidates all active sessions.
