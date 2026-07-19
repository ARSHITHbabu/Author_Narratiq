# NarratIQ AI v3.0 — How to Run

**Short version:** one command, `bash start-narratiq.sh`. Everything below is detail.

For RunPod environment variables, see
**[`docs/RUNPOD_ENVIRONMENT_VARIABLE_RECOVERY.md`](docs/RUNPOD_ENVIRONMENT_VARIABLE_RECOVERY.md)**.
For pod creation and troubleshooting, see [`RUNPOD_DEPLOYMENT.md`](RUNPOD_DEPLOYMENT.md).

---

## Before you start

### Repository path is fixed

`start-narratiq.sh:14-15` hardcodes `/workspace/narratiq-ai`. Clone there, or symlink:

```bash
ln -s /workspace/Author_Narratiq /workspace/narratiq-ai
ls /workspace/narratiq-ai/start-narratiq.sh   # must exist
```

### Environment variables

You need **none**. The script generates everything mandatory. Two are worth setting in the RunPod UI:

```env
SECRET_KEY=replace_with_64_hex_chars    # keeps logins working across a re-clone
HF_TOKEN=hf_your_token_here             # raises HF download rate limits
```

> **Returning to an old pod?** Delete any `VLLM_BASE_URL` still set in the RunPod UI. An older guide
> told you to set port 8001; vLLM now runs on **9001**, and the stale value silently overrides the
> correct one whenever the backend is started manually.

### Your RunPod URLs

Click **Connect** on the pod. Your URLs are:

```
https://{POD_ID}-3000.proxy.runpod.net     ← Frontend (open this)
https://{POD_ID}-8000.proxy.runpod.net     ← Backend API
```

`{POD_ID}` changes when you create a new pod, but is stable across stop/start of the same pod.
The startup script reads `RUNPOD_POD_ID` and wires both URLs automatically.

---

## Option A — One command (recommended)

```bash
cd /workspace/narratiq-ai
bash start-narratiq.sh
```

| | |
|---|---|
| First run | 20–40 min (dependencies + ~17 GB of models) |
| Later runs | 3–5 min |

Safe to rerun — every step is idempotent. It installs dependencies, downloads missing models,
configures PostgreSQL + pgvector, runs migrations, and starts all three services.

When it finishes it prints your frontend URL. Skip to
[Verify everything is working](#verify-everything-is-working).

---

## Option B — Manual, three terminals

Use this to see each service's logs separately, or when the script fails at a specific step.
Run Option A at least once first — it installs PostgreSQL, the Python packages and the models,
none of which the steps below do.

### Terminal 1 — vLLM

```bash
cd /workspace/narratiq-ai/backend

python3 -m vllm.entrypoints.openai.api_server \
  --model /workspace/models/Qwen2.5-7B-Instruct \
  --served-model-name "Qwen/Qwen2.5-7B-Instruct" \
  --dtype auto \
  --gpu-memory-utilization 0.88 \
  --tensor-parallel-size 1 \
  --max-model-len 8192 \
  --max-num-seqs 256 \
  --enable-chunked-prefill \
  --enable-prefix-caching \
  --host 0.0.0.0 \
  --port 9001 \
  --disable-log-requests
```

Wait for:
```
INFO:     Uvicorn running on http://0.0.0.0:9001
```

Loading takes 2–4 minutes. Adjust for your GPU count — Qwen2.5-7B has 4 KV heads, so
`--tensor-parallel-size` must be **1, 2 or 4** (never 3):

| GPUs | `--tensor-parallel-size` | `--max-model-len` | `--gpu-memory-utilization` |
|---|---|---|---|
| 1 | 1 | 8192 | 0.88 |
| 2–3 | 2 | 16384 | 0.90 |
| 4+ | 4 | 32768 | 0.90 |

### Terminal 2 — PostgreSQL and the backend

PostgreSQL must be running with the `narratiq` database and the `vector` extension.
`start-narratiq.sh` sets this up; to start it manually:

```bash
pg_ctlcluster 16 main start || service postgresql start
pg_isready -h localhost -U postgres     # expect "accepting connections"
```

Then:

```bash
cd /workspace/narratiq-ai/backend      # ← REQUIRED, see note below
python3 -m alembic upgrade head
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1 --no-access-log
```

Wait for:
```
[startup] NarratIQ ready
INFO:     Uvicorn running on http://0.0.0.0:8000
```

> **You must `cd backend` first.** `config.py` reads `./.env` relative to the current working
> directory. Started from anywhere else, `backend/.env` is silently ignored, `SECRET_KEY` is unset,
> and startup fails with `ValidationError: SECRET_KEY must be at least 32 characters`.

Startup takes 30–60 s — BGE-M3 loads into memory, then a pgvector self-check runs, then vLLM is
probed. Two of those are hard failures:

| Condition | Behaviour |
|---|---|
| Model weights missing | **Hard fail** — `RuntimeError` |
| pgvector query path broken | **Hard fail** — `RuntimeError` |
| vLLM unreachable | **Warning only** — backend starts, all AI returns 503 |

### Terminal 3 — Frontend

```bash
cd /workspace/narratiq-ai/frontend

# On RunPod (substitute your pod ID):
echo 'NEXT_PUBLIC_API_URL=https://abc123xyz-8000.proxy.runpod.net' > .env.local
# Locally:
# echo 'NEXT_PUBLIC_API_URL=http://localhost:8000' > .env.local

npm run dev
```

Wait for:
```
▲ Next.js 14.2.3
- Local:   http://localhost:3000
Ready in Xs
```

Then open `https://{POD_ID}-3000.proxy.runpod.net`.

> `NEXT_PUBLIC_API_URL` is inlined into the JS bundle at **build** time. After changing it, run
> `npm run build` again — a restart alone will not pick it up. If the variable is also set in the
> RunPod UI it overrides `.env.local` entirely; delete it there.

---

## Option C — Frontend on your local machine

```bash
cd path/to/narratiq-ai/frontend
echo 'NEXT_PUBLIC_API_URL=https://{POD_ID}-8000.proxy.runpod.net' > .env.local
npm run dev
```

Open `http://localhost:3000`. CORS already permits any `https://*.proxy.runpod.net` origin, and
`http://localhost:3000` is in the default allow-list.

---

## Verify everything is working

```bash
curl -s http://localhost:8000/api/health | python3 -m json.tool
```

Expected:
```json
{
  "status": "ok",
  "vllm": "ready",
  "bge_m3": "ready",
  "got_ocr": "lazy"
}
```

- `"vllm": "unavailable"` — vLLM is still loading, or the backend is pointed at the wrong port.
  Check `curl http://localhost:9001/health`, then confirm what the backend resolved:
  ```bash
  cd /workspace/narratiq-ai/backend
  python3 -c "from config import settings; print(settings.vllm_base_url)"
  ```
  Anything other than `http://127.0.0.1:9001/v1` means a stale `VLLM_BASE_URL` is overriding
  `backend/.env` — almost always a leftover in the RunPod UI.
- `"bge_m3": "loading"` — still initialising; wait a few seconds.

---

## Indexing existing chapters

Chapters you write are indexed automatically 1.5 s after you stop typing (summary + embeddings).

If Plot Assistant reports "no prior context" for chapters that predate indexing, backfill once:

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"your@email.com","password":"yourpassword"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -s -X POST "http://localhost:8000/api/stories/YOUR_STORY_ID/chapters/sync-summaries" \
  -H "Authorization: Bearer $TOKEN"
```

Allow 15–30 s per chapter. The story ID is in the URL when you open a story.

---

## Reference

### Service ports

| Service | Port | URL | Exposed on RunPod? |
|---|---|---|---|
| vLLM (Qwen2.5-7B) | 9001 | `http://localhost:9001/v1` | No — internal |
| FastAPI backend | 8000 | `http://localhost:8000` | Yes |
| Next.js frontend | 3000 | `http://localhost:3000` | Yes |
| PostgreSQL | 5432 | `localhost:5432` | No — internal |

> The legacy `start.sh` and `scripts/verify_runpod_setup.sh` still default vLLM to **8001**.
> They are superseded by `start-narratiq.sh`. See `RUNPOD_DEPLOYMENT.md` → Port contradiction.

### Log files

| Service | Log |
|---|---|
| vLLM | `tail -f /tmp/narratiq-logs/vllm.log` |
| Backend | `tail -f /tmp/narratiq-logs/backend.log` |
| Frontend | `tail -f /tmp/narratiq-logs/frontend.log` |
| Installs | `/tmp/narratiq-logs/pip-*.log`, `npm-install.log`, `pg-install.log` |

---

## Common problems

**vLLM will not start**
```bash
nvidia-smi                                    # confirm the GPU is visible
tail -50 /tmp/narratiq-logs/vllm.log
rm -rf ~/.cache/vllm/torch_compile_cache      # clear after a failed run on different hardware
```
With one GPU use `--tensor-parallel-size 1 --max-model-len 8192`.

**`SECRET_KEY must be at least 32 characters`**
You started the backend from the wrong directory, or `backend/.env` is missing. `cd backend` first.
The script regenerates the file if absent.

**`Extra inputs are not permitted`**
`backend/.env` contains a key that is not a `Settings` field — `pydantic-settings` uses
`extra="forbid"`. The error names the key; delete that line. Historically caused by copying an old
`.env.example` containing `TROCR_MODEL_ID`.

**`pgvector query path self-check FAILED`**
PostgreSQL is not running, or `DATABASE_URL` points at SQLite, or the `vector` extension is missing:
```bash
runuser -u postgres -- psql -d narratiq -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

**Frontend cannot reach the backend**
Rebuild after any `NEXT_PUBLIC_API_URL` change, and make sure it is not also set in the RunPod UI:
```bash
cd /workspace/narratiq-ai/frontend
echo "NEXT_PUBLIC_API_URL=https://${RUNPOD_POD_ID}-8000.proxy.runpod.net" > .env.local
npm run build && npm start -- --port 3000
```

**Port already in use**
```bash
pkill -f "vllm.entrypoints.openai.api_server"
pkill -f "uvicorn main:app"
fuser -k 3000/tcp
```

---

## Fastest path

```
1. Open the RunPod terminal
2. bash /workspace/narratiq-ai/start-narratiq.sh
3. Wait (first run 20-40 min; later runs 3-5 min)
4. Open https://{POD_ID}-3000.proxy.runpod.net
```
