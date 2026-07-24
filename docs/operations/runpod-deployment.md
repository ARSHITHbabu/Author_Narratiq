# NarratIQ AI — RunPod Deployment Guide

**Authoritative startup path:** `bash start-narratiq.sh`.
For which environment variables to enter in the RunPod UI, see
**[`docs/operations/runpod-environment-variables.md`](runpod-environment-variables.md)**.

---

## Architecture Overview

```
RunPod pod (1+ NVIDIA GPU, >= 24 GB VRAM)
│
├── /workspace/narratiq-ai/          ← project code (path is REQUIRED, see Step 3)
├── /workspace/models/               ← model weights (~17 GB total)
│   ├── Qwen2.5-7B-Instruct/                 ~14 GB
│   ├── bge-m3/                              ~570 MB
│   ├── GOT-OCR2_0/                          ~1.4 GB
│   └── faster-whisper-large-v3-turbo/       ~1.5 GB
│
├── vLLM server (port 9001)          ← serves Qwen via OpenAI-compatible API
│
├── FastAPI backend (port 8000)
│   ├── Calls vLLM over the OpenAI-compatible client
│   ├── Loads BGE-M3 at startup (in-process, CPU by default)
│   ├── Lazy-loads GOT-OCR2.0 on first OCR request
│   └── PostgreSQL 16 + pgvector for all storage and vector retrieval
│
└── Next.js frontend (port 3000)
```

> **Port note.** vLLM runs on **9001**. Older revisions of this guide said 8001, and the legacy
> `start.sh` and `scripts/verify_runpod_setup.sh` still default to 8001. See
> [Port contradiction](#port-contradiction) before trusting any 8001 reference.

**Database:** PostgreSQL 16 with the `pgvector` extension is **required**. SQLite is not supported —
retrieval uses pgvector HNSW indexes and the `<=>` cosine operator, and a startup self-check in
`backend/main.py` raises `RuntimeError` if the pgvector query path does not work.
`start-narratiq.sh` installs and configures PostgreSQL for you.

---

## Storage options

**Testing (no Network Volume).** Models download into `/workspace/models` on first run and are lost
when the pod is destroyed. Budget 10–20 minutes for the first boot.

**Production (Network Volume).** Attach a RunPod Network Volume so the ~17 GB of weights persists.

> **Caveat.** `start-narratiq.sh:16` hardcodes `MODEL_DIR="/workspace/models"` and re-exports
> `MODEL_BASE_DIR` at `:501`, so setting `MODEL_BASE_DIR=/runpod-volume/models` in the RunPod UI has
> **no effect** on the scripted path. Symlink instead:
> ```bash
> mkdir -p /runpod-volume/models
> ln -s /runpod-volume/models /workspace/models
> ```

---

## Step-by-Step Deployment

### 1. Create a RunPod Pod

| Setting | Recommendation |
|---|---|
| **GPU** | One card with ≥24 GB VRAM. The script auto-detects count and sets tensor-parallel size |
| **Template** | Any recent PyTorch/CUDA image on Ubuntu 22.04. The script installs everything else |
| **Container Disk** | 60 GB+ |
| **Volume Disk** | 30 GB+ if using a Network Volume |
| **Expose HTTP Ports** | `8000` (backend), `3000` (frontend). Port 9001 is internal only |

Qwen2.5-7B-Instruct has **4 KV heads**, so tensor-parallel size must divide 4 — valid values are
**1, 2 or 4**, never 3. The script handles this:

| GPUs | TP | `max-model-len` | GPU util |
|---|---|---|---|
| 1 | 1 | 8192 | 0.88 |
| 2–3 | 2 | 16384 | 0.90 |
| 4+ | 4 | 32768 | 0.90 |

### 2. Add Environment Variables

In the RunPod pod configuration, add **at most these two**:

```env
SECRET_KEY=replace_with_64_hex_chars_from_secrets_token_hex_32
HF_TOKEN=hf_your_token_here
```

Both are **optional**. A pod with no environment variables at all will start correctly, because
`start-narratiq.sh` generates everything mandatory.

- `SECRET_KEY` — signs JWTs. The script generates one if `backend/.env` lacks it, but `backend/.env`
  is gitignored, so a fresh clone regenerates it and **invalidates every existing login**. Set it in
  the RunPod UI to keep logins stable across re-clones.
  Generate: `python3 -c "import secrets; print(secrets.token_hex(32))"`
- `HF_TOKEN` — raises Hugging Face download rate limits. All required models are public, so this is
  a convenience only. Read exclusively by `scripts/download_models.sh`.

> **Do not set** `DATABASE_URL`, `VLLM_BASE_URL`, `VLLM_MODEL_NAME`, `CORS_ORIGINS` or
> `NEXT_PUBLIC_API_URL`. The script generates or force-overwrites all of them on every run.
>
> **If you are returning to an older pod, delete any `VLLM_BASE_URL` left in the RunPod UI.**
> Earlier versions of this guide told you to set `http://127.0.0.1:8001/v1`. Because OS environment
> variables take precedence over `backend/.env`, that stale value silently overrides the correct one
> whenever the backend is started by hand — the app appears healthy while every AI call returns 503.
> Full explanation: [`docs/operations/runpod-environment-variables.md`](runpod-environment-variables.md) §1.2.

### 3. Open the Workspace and Clone

Use the pod's **Connect** button → Jupyter terminal or the web terminal.

Authenticate to GitHub without putting a token in the URL (it would be written to shell history and
to `.git/config`):

```bash
# Option A — GitHub CLI (interactive)
gh auth login

# Option B — SSH key
ssh-keygen -t ed25519 -C "runpod"
cat ~/.ssh/id_ed25519.pub    # add to GitHub → Settings → SSH and GPG keys
ssh -T git@github.com
```

A public repository needs no authentication over HTTPS.

```bash
cd /workspace
git clone https://github.com/ARSHITHbabu/Author_Narratiq.git narratiq-ai
```

**The directory name matters.** `start-narratiq.sh:14-15` hardcodes `/workspace/narratiq-ai`.
If you cloned elsewhere, symlink rather than editing the script:

```bash
ln -s /workspace/Author_Narratiq /workspace/narratiq-ai
ls /workspace/narratiq-ai/start-narratiq.sh   # must exist before continuing
```

### 4. Run the Startup Script

```bash
cd /workspace/narratiq-ai
bash start-narratiq.sh
```

That is the entire deployment. The script is self-bootstrapping and **safe to rerun** — every step is
idempotent.

| | |
|---|---|
| First run | 20–40 min (dependencies + ~17 GB of model downloads) |
| Later runs | 3–5 min |

What it does, in order:

1. Installs Node 20, PostgreSQL 16 + pgvector, vLLM 0.9.2, PyTorch cu128; pins NumPy ≤2.2 and
   transformers <5.0; patches `ovis.py` and `prometheus_fastapi_instrumentator`; installs backend pip
   packages and runs `npm install`.
2. Downloads any missing models (skips files already present).
3. Starts vLLM on port 9001 and waits up to 6 minutes for `/health`.
4. Generates `SECRET_KEY` into `backend/.env` **if absent**.
5. Starts PostgreSQL, creates the `narratiq` role and database, enables `pgvector`, force-writes
   `DATABASE_URL` / `VLLM_BASE_URL` / `VLLM_MODEL_NAME` / `CORS_ORIGINS` into `backend/.env`, creates
   tables, runs `alembic upgrade head`.
6. Starts the FastAPI backend on port 8000.
7. Writes `frontend/.env.local`, wipes `.next`, rebuilds, and starts Next.js on port 3000.
8. Prints the public URLs, log paths and PIDs.

### 5. Monitor

```bash
tail -f /tmp/narratiq-logs/vllm.log
tail -f /tmp/narratiq-logs/backend.log
tail -f /tmp/narratiq-logs/frontend.log
```

### 6. Verify

```bash
# vLLM
curl http://localhost:9001/health
curl -s http://localhost:9001/v1/models | python3 -m json.tool   # expect Qwen/Qwen2.5-7B-Instruct

# Backend
curl -s http://localhost:8000/api/health | python3 -m json.tool
# expect: "status":"ok", "vllm":"ready", "bge_m3":"ready"

# Frontend
curl -so /dev/null -w "%{http_code}\n" http://localhost:3000    # expect 200 or 3xx
```

### 7. Open the Application

```bash
echo "Frontend: https://${RUNPOD_POD_ID}-3000.proxy.runpod.net"
echo "Backend : https://${RUNPOD_POD_ID}-8000.proxy.runpod.net"
```

The script prints both on completion. `backend/main.py` already allows any
`https://*.proxy.runpod.net` origin via regex, so CORS works without manual configuration.

---

## Port contradiction

Not yet resolved in code. Documented here so it does not cause confusion.

| Source | Port | Status |
|---|---|---|
| `start-narratiq.sh:17` | **9001** | **Authoritative** — the path in use |
| `backend/config.py:59` | **9001** | Consistent |
| `start.sh:25` | 8001 | **Legacy**, superseded — predates the Postgres migration |
| `scripts/verify_runpod_setup.sh:14` | 8001 | Legacy — reports a **false failure** against a working 9001 stack |

The default moved from 8001 to 9001 in commit `b0f64be`. If you must run the verifier, override it:

```bash
VLLM_PORT=9001 bash scripts/verify_runpod_setup.sh
```

---

## Manual start (three terminals)

Use only when debugging a specific service. The scripted path above is preferred.

```bash
# Terminal 1 — vLLM (1 GPU; use TP=2/4 and a larger context for more cards)
python3 -m vllm.entrypoints.openai.api_server \
  --model /workspace/models/Qwen2.5-7B-Instruct \
  --served-model-name "Qwen/Qwen2.5-7B-Instruct" \
  --dtype auto --gpu-memory-utilization 0.88 \
  --tensor-parallel-size 1 --max-model-len 8192 \
  --host 0.0.0.0 --port 9001

# Terminal 2 — backend. MUST run from backend/ so config.py finds ./.env
cd /workspace/narratiq-ai/backend
python3 -m alembic upgrade head
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1

# Terminal 3 — frontend
cd /workspace/narratiq-ai/frontend
echo "NEXT_PUBLIC_API_URL=https://${RUNPOD_POD_ID}-8000.proxy.runpod.net" > .env.local
npm run build && npm start -- --port 3000
```

Two traps specific to the manual path:

- **Start the backend from `backend/`.** `config.py` reads `./.env` relative to the working
  directory. From anywhere else the file is silently ignored, `SECRET_KEY` is unset, and startup
  fails with a `ValidationError`.
- **A stale `VLLM_BASE_URL` in the RunPod UI bites here.** The scripted path masks it via its own
  `export`; a manual `uvicorn` does not. Check what actually resolved:
  ```bash
  cd /workspace/narratiq-ai/backend
  python3 -c "from config import settings; print(settings.vllm_base_url)"
  ```

---

## Common Errors and Fixes

### `vllm: unavailable` in `/api/health` while everything else is `ok`
The backend cannot reach vLLM. In order of likelihood:
1. **A stale `VLLM_BASE_URL` in the RunPod UI** pointing at 8001 — delete it, then rerun.
2. vLLM is still loading. `tail -f /tmp/narratiq-logs/vllm.log` and wait for
   `Uvicorn running on http://0.0.0.0:9001`.
3. vLLM crashed — check the same log.

The backend does **not** refuse to start when vLLM is unreachable; it logs a warning and continues in
degraded mode, so this fails quietly.

### `ValidationError: ... Extra inputs are not permitted`
`backend/.env` contains a key that is not a field on the `Settings` class. `pydantic-settings` uses
`extra="forbid"`. Historically this was caused by copying an older `.env.example` containing
`TROCR_MODEL_ID`, left over from the TrOCR → GOT-OCR2.0 migration. Remove the offending key — the
error message names it. Only non-empty values trigger this; `FOO=` is ignored.

### `SECRET_KEY must be at least 32 characters`
Either `SECRET_KEY` is unset, or the backend was started from the wrong directory so `backend/.env`
was never loaded. `cd backend` first.

### `pgvector query path self-check FAILED`
`DATABASE_URL` points at SQLite or at a database without the `vector` extension. Re-run
`start-narratiq.sh`, or manually:
```bash
runuser -u postgres -- psql -d narratiq -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### `Required model directories not found`
Weights are missing. Re-run the script, or:
```bash
MODEL_BASE_DIR=/workspace/models bash scripts/download_models.sh
```

### `CUDA out of memory`
Lower the vLLM context or utilisation. On a single 24 GB card use
`--max-model-len 8192 --gpu-memory-utilization 0.88`. Keep `BGE_DEVICE=cpu` and
`WHISPER_DEVICE=cpu` unless there is clear VRAM headroom.

### Frontend calls the wrong backend URL
`NEXT_PUBLIC_API_URL` is inlined into the JS bundle at **build** time. A restart is not enough —
the bundle must be rebuilt. If the value is also set in the RunPod UI it overrides
`frontend/.env.local` entirely; delete it there and rerun the script.

### Port already in use
```bash
pkill -f "vllm.entrypoints.openai.api_server"
pkill -f "uvicorn main:app"
fuser -k 3000/tcp
```

### Models re-downloading every pod restart
Use a Network Volume and symlink it — see [Storage options](#storage-options).

---

## Quick Command Reference

```bash
# Full startup (installs, configures, launches everything)
bash /workspace/narratiq-ai/start-narratiq.sh

# Health
curl http://localhost:9001/health                       # vLLM
curl -s http://localhost:8000/api/health | python3 -m json.tool
curl -so /dev/null -w "%{http_code}\n" http://localhost:3000

# Logs
tail -f /tmp/narratiq-logs/{vllm,backend,frontend}.log

# Models only
MODEL_BASE_DIR=/workspace/models bash scripts/download_models.sh

# What the backend actually resolved
cd /workspace/narratiq-ai/backend && python3 -c "from config import settings; print(settings.vllm_base_url, settings.database_url)"

# Re-index chapters after manual DB changes
curl -X POST http://localhost:8000/api/stories/{id}/chapters/sync-summaries \
  -H "Authorization: Bearer $TOKEN"
```

---

*This guide describes the repository at commit `9827587`. It has not been validated against a running
pod; see the uncertainties section of
[`docs/operations/runpod-environment-variables.md`](runpod-environment-variables.md).*
