# NarratIQ AI v3.0 — How to Run the Project

Every time you start the RunPod pod, follow these steps in order.
Open **3 separate terminals** on RunPod (use Jupyter → Terminal, or the RunPod terminal tab).

---

## Before You Start — Get Your RunPod Public URL

When you open RunPod, you will see a **Connect** button on your pod.
Click it and note your pod's public proxy URL. It looks like:

```
https://abc123xyz-8000.proxy.runpod.net     ← Backend URL
https://abc123xyz-3000.proxy.runpod.net     ← Frontend URL
```

The `abc123xyz` part is your **Pod ID** — it changes each time you create a new pod
but stays the same if you stop/start the same pod.

---

## OPTION A — One Command (Easiest)

Open **1 terminal** on RunPod and run:

```bash
bash /workspace/narratiq-ai/start-narratiq.sh
```

This does everything automatically:
- Starts vLLM (waits 1–3 min for model to load)
- Starts FastAPI backend
- Builds and starts the Next.js frontend

Then open in your browser:
```
https://{YOUR_POD_ID}-3000.proxy.runpod.net
```

Done. Skip to the **Verify Everything is Working** section below.

---

## OPTION B — Manual Step-by-Step (3 Terminals)

Use this if you want to see each service's logs separately,
or if the startup script fails for any reason.

---

### TERMINAL 1 — Start vLLM (the AI brain)

Open Terminal 1 on RunPod and run:

```bash
cd /workspace/narratiq-ai/backend
```

Then run this to start vLLM (this takes **1–3 minutes** to load the model):

```bash
python3 -m vllm.entrypoints.openai.api_server \
  --model /workspace/models/Qwen2.5-7B-Instruct \
  --served-model-name "Qwen/Qwen2.5-7B-Instruct" \
  --dtype auto \
  --gpu-memory-utilization 0.90 \
  --tensor-parallel-size 2 \
  --max-model-len 16384 \
  --max-num-seqs 256 \
  --enable-chunked-prefill \
  --enable-prefix-caching \
  --host 0.0.0.0 \
  --port 9001 \
  --disable-log-requests
```

**Wait until you see this line in Terminal 1:**
```
INFO:     Uvicorn running on http://0.0.0.0:9001
```

> **Note:** If you only have 1 GPU (not 2), change `--tensor-parallel-size 2` to `--tensor-parallel-size 1`
> and `--max-model-len 16384` to `--max-model-len 8192`

---

### TERMINAL 2 — Start the Backend (FastAPI)

Open a **new** Terminal 2 on RunPod (keep Terminal 1 running).

```bash
cd /workspace/narratiq-ai/backend
```

```bash
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1 --no-access-log
```

**Wait until you see:**
```
NarratIQ ready.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

> The backend loads BGE-M3 embeddings model at startup — takes about 5–10 seconds.

---

### TERMINAL 3 — Start the Frontend (Next.js)

Open a **new** Terminal 3 on RunPod (keep Terminals 1 and 2 running).

**Step 1 — Go to the frontend folder:**
```bash
cd /workspace/narratiq-ai/frontend
```

**Step 2 — Set the backend URL** (replace `abc123xyz` with YOUR actual Pod ID):
```bash
echo 'NEXT_PUBLIC_API_URL=https://abc123xyz-8000.proxy.runpod.net' > .env.local
```

> **Important:** Do this step every time if your Pod ID changes.
> To find your Pod ID: look at the RunPod dashboard URL or the proxy URL in Connect tab.

**Step 3 — Start the frontend:**
```bash
npm run dev
```

**Wait until you see:**
```
▲ Next.js 13.x.x
- Local:   http://localhost:3000
Ready in Xs
```

**Step 4 — Open in your browser:**
```
https://{YOUR_POD_ID}-3000.proxy.runpod.net
```

---

## OPTION C — Run Frontend on Your Local Machine

If you prefer to run the frontend on your laptop (not on RunPod):

**On your local machine**, go to the frontend folder you already have:

```bash
cd path/to/narratiq-ai/frontend
```

Open the file `.env.local` in a text editor and make sure it has:
```
NEXT_PUBLIC_API_URL=https://{YOUR_POD_ID}-8000.proxy.runpod.net
```

Replace `{YOUR_POD_ID}` with your actual RunPod pod ID.

Then run:
```bash
npm run dev
```

Open in browser: `http://localhost:3000`

---

## Verify Everything is Working

After all three services are up, open a new terminal and run:

```bash
curl http://localhost:8000/api/health
```

You should see:
```json
{
  "status": "ok",
  "vllm": "ready",
  "bge_m3": "ready"
}
```

If `vllm` shows `"unavailable"`, vLLM is still loading — wait another minute and try again.

---

## First Time Using a New Story

When you write chapters in the editor, they are **automatically indexed** in the background
(summary + embeddings are generated 1.5 seconds after you stop typing).

If you have existing chapters from before and Plot Assistant shows "no prior context",
run this once to index them. Open a terminal and run:

```bash
cd /workspace/narratiq-ai/backend

# Get a login token first (replace with your actual email and password):
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"your@email.com","password":"yourpassword"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Replace YOUR_STORY_ID with the story ID from the URL when you open a story:
curl -s -X POST "http://localhost:8000/api/stories/YOUR_STORY_ID/chapters/sync-summaries" \
  -H "Authorization: Bearer $TOKEN"
```

Wait about 15–30 seconds per chapter, then Plot Assistant will have full context.

---

## Quick Reference — Service Ports

| Service | Port | URL |
|---------|------|-----|
| vLLM (Qwen) | 9001 | `http://localhost:9001/v1` |
| FastAPI Backend | 8000 | `http://localhost:8000` |
| Next.js Frontend | 3000 | `http://localhost:3000` |

## Quick Reference — Log Files (when using startup script)

| Service | Log file |
|---------|----------|
| vLLM | `tail -f /tmp/narratiq-logs/vllm.log` |
| Backend | `tail -f /tmp/narratiq-logs/backend.log` |
| Frontend | `tail -f /tmp/narratiq-logs/frontend.log` |

---

## Common Problems & Fixes

**Problem: vLLM takes too long or fails to start**
```bash
# Check what GPU you have:
nvidia-smi

# If only 1 GPU, use tensor-parallel-size 1:
--tensor-parallel-size 1 --max-model-len 8192
```

**Problem: Frontend shows "Plot assistant failed"**
```bash
# Check if backend is running:
curl http://localhost:8000/api/health

# If vllm shows "unavailable", vLLM is still loading. Wait and retry.
```

**Problem: "NEXT_PUBLIC_API_URL" wrong / API calls failing from browser**
```bash
# Re-set the backend URL with your current pod ID and rebuild:
cd /workspace/narratiq-ai/frontend
echo 'NEXT_PUBLIC_API_URL=https://YOUR_POD_ID-8000.proxy.runpod.net' > .env.local
npm run build
npm start -- --port 3000
```

**Problem: Port 9001 or 8000 already in use**
```bash
# Kill old processes:
pkill -f "vllm.entrypoints.openai.api_server"
pkill -f "uvicorn main:app"
# Then start them again
```

---

## Summary — Fastest Way to Start

```
1. Open RunPod → open 1 terminal
2. Run: bash /workspace/narratiq-ai/start-narratiq.sh
3. Wait 2-3 minutes for model to load
4. Open browser: https://{YOUR_POD_ID}-3000.proxy.runpod.net
5. Done ✓
```
