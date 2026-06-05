# NarratIQ AI — RunPod Deployment Guide

## Architecture Overview

```
RunPod RTX 4090 (24 GB VRAM)
│
├── /workspace/narratiq-ai/          ← project code (cloned here)
├── /workspace/models/               ← downloaded model weights
│   ├── Qwen2.5-7B-Instruct/         ← ~14 GB
│   ├── bge-m3/                      ← ~570 MB
│   └── GOT-OCR2_0/                  ← ~1.4 GB
│
├── vLLM server (port 8001)
│   └── Loads Qwen2.5-7B-Instruct once, serves OpenAI-compatible API
│
└── FastAPI backend (port 8000)
    ├── Calls vLLM via OpenAI-compatible client
    ├── Pre-loads BGE-M3 at startup (CPU)
    ├── Lazy-loads GOT-OCR2.0 on first OCR request (GPU if ≥2.5 GB free, else CPU)
    └── Exposes streaming AI endpoints
```

---

## For Testing (fresh pod, no persistent volume)

Download models into `/workspace/models` each time the pod boots.
Models will need to be re-downloaded if the pod is restarted without a Network Volume.

## For Production (Network Volume)

Attach a RunPod Network Volume and point `MODEL_BASE_DIR` to it (e.g. `/runpod-volume/models`).
Models download once and persist across pod restarts. **Recommended for saving time and bandwidth.**

---

## Step-by-Step Deployment

### 1. Create a RunPod Pod

**Recommended settings:**
- **GPU:** RTX 4090 (24 GB VRAM) — minimum for Qwen2.5-7B with comfortable headroom
- **Template:** `RunPod PyTorch 2.4.0` (includes CUDA 12.1, Python 3.10, pip)
- **Container Disk:** 50 GB (for OS, packages, and temp space)
- **Volume Disk:** 30 GB+ if using Network Volume (recommended for production)
- **Expose HTTP Ports:** `8000` (FastAPI), `8001` (vLLM, optional external access)

### 2. Open a Terminal

Use the RunPod web terminal or connect via SSH.

### 3. Clone the Project

```bash
cd /workspace
git clone <your-repo-url> narratiq-ai
cd narratiq-ai
```

Or if transferring a zip:

```bash
cd /workspace
unzip narratiq-ai.zip
mv narratiq-ai-main narratiq-ai
cd narratiq-ai
```

### 4. Install Dependencies

Install vLLM and GPU dependencies first (this takes a few minutes):

```bash
pip install -r requirements.vllm.txt
```

Install backend dependencies:

```bash
pip install -r backend/requirements.txt
```

Verify the environment is correct:

```bash
bash scripts/verify_runpod_setup.sh
```

### 5. Set Environment Variables

**Option A — Set as RunPod pod environment variables (recommended)**

In the RunPod pod configuration UI, add these variables:

```
MODEL_BASE_DIR=/workspace/models
VLLM_BASE_URL=http://127.0.0.1:8001/v1
VLLM_MODEL_NAME=Qwen/Qwen2.5-7B-Instruct
GPU_MEMORY_UTILIZATION=0.88
MAX_MODEL_LEN=8192
BGE_DEVICE=cpu
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
SECRET_KEY=<generate a random 64-char hex string>
HF_TOKEN=<your HF token, optional for public models>
```

**Option B — Create a `.env` file**

```bash
cp .env.example backend/.env
nano backend/.env   # or vim backend/.env
```

Edit at minimum:
- `SECRET_KEY` — generate with: `python3 -c "import secrets; print(secrets.token_hex(32))"`
- `MODEL_BASE_DIR` — set to your model directory (default: `/workspace/models`)

### 6. Download Models from Hugging Face

Install download tooling:

```bash
pip install -r requirements.setup.txt
```

Enable fast downloads (optional but recommended for the 14 GB LLM):

```bash
export HF_HUB_ENABLE_HF_TRANSFER=1
```

If you have a HF token (not required for these public models, but raises rate limits):

```bash
export HF_TOKEN=hf_your_token_here
```

Run the download script:

```bash
bash scripts/download_models.sh
```

This downloads all three models (~16 GB total). Qwen2.5-7B-Instruct takes the longest.
The script is safe to re-run — it skips files that already exist.

**Where models are stored:**

```
/workspace/models/
├── Qwen2.5-7B-Instruct/   ← ~14 GB
├── bge-m3/                ← ~570 MB
└── GOT-OCR2_0/            ← ~1.4 GB
```

### 7. Start the Application

```bash
cd /workspace/narratiq-ai
bash start.sh
```

`start.sh` will:
1. Validate that model directories exist
2. Launch vLLM on port 8001 (loads Qwen into VRAM — takes 1–3 min)
3. Wait until vLLM `/health` returns 200
4. Launch FastAPI on port 8000 (pre-loads BGE-M3, warms up vLLM)

You'll see this when ready:

```
  vLLM healthy after 90s.
[3/3] Starting FastAPI on port 8000...
NarratIQ startup: loading BGE-M3 embeddings model...
BGE-M3 loaded on cpu.
vLLM health check passed.
vLLM warmup complete — first user request will be fast.
NarratIQ ready.
```

### 8. Verify vLLM is Running

Check the vLLM health endpoint:

```bash
curl http://localhost:8001/health
# Expected: {"status":"ok"}  or HTTP 200
```

List available models:

```bash
curl http://localhost:8001/v1/models | python3 -m json.tool
# Should show Qwen/Qwen2.5-7B-Instruct
```

### 9. Verify FastAPI is Running

Check the NarratIQ health endpoint:

```bash
curl http://localhost:8000/api/health | python3 -m json.tool
```

Expected response:

```json
{
  "status": "ok",
  "version": "3.0.0",
  "platform": "NarratIQ AI",
  "backend": "ready",
  "vllm": "ready",
  "bge_m3": "ready",
  "got_ocr": "lazy"
}
```

If `"vllm": "unavailable"`, vLLM hasn't started yet — check its logs.

### 10. Test an AI Request

Test a genre detection call (replace `<YOUR_TOKEN>` with a JWT from `/api/auth/login`):

```bash
# 1. Register a test user
curl -s -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","username":"testuser","password":"testpass123"}' \
  | python3 -m json.tool

# 2. Extract the access_token from the response, then test AI
curl -s -X POST http://localhost:8000/api/ai/refine \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_TOKEN>" \
  -d '{"text":"The old man walked slowly down the street.","mode":"literary"}' \
  | python3 -m json.tool
```

Test streaming:

```bash
curl -s -N -X POST http://localhost:8000/api/ai/refine/stream \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_TOKEN>" \
  -d '{"text":"The old man walked slowly.","mode":"literary"}'
# Tokens arrive progressively as SSE events
```

### 11. Expose the RunPod Port

In RunPod, go to your pod → **Connect** → **HTTP Service** → expose port `8000`.

This gives you a public URL like:

```
https://<pod-id>-8000.proxy.runpod.net
```

Update your frontend's `NEXT_PUBLIC_API_URL` to this URL.

Update `CORS_ORIGINS` in your env vars:

```
CORS_ORIGINS=["https://<pod-id>-8000.proxy.runpod.net","http://localhost:3000"]
```

---

## Production: RunPod Network Volume

Using a Network Volume keeps models between pod restarts and saves you ~30 min of download time per boot.

### Setup (one time)

1. Create a Network Volume in RunPod (at least 30 GB, same region as pod).
2. Attach the volume to your pod at `/runpod-volume`.
3. Download models into the volume:

```bash
MODEL_BASE_DIR=/runpod-volume/models bash scripts/download_models.sh
```

4. Set the env var permanently:

```
MODEL_BASE_DIR=/runpod-volume/models
```

### Subsequent Pod Starts

Models are already on the volume — no re-download needed. Just run:

```bash
bash start.sh
```

---

## GPU Memory Reference

| GPU            | VRAM   | GPU_MEMORY_UTILIZATION | Headroom | MAX_MODEL_LEN |
|----------------|--------|------------------------|----------|---------------|
| RTX 4090       | 24 GB  | 0.88                   | ~3 GB    | 8192          |
| A100 40 GB     | 40 GB  | 0.90                   | ~4 GB    | 16384         |
| A100 80 GB     | 80 GB  | 0.90                   | ~8 GB    | 32768         |
| 2× A100 40 GB  | 80 GB  | 0.90 + TP=2            | ~8 GB    | 32768         |

For RTX 4090: keep `BGE_DEVICE=cpu` (safe, ~100ms per embedding).
For A100 with leftover VRAM: `BGE_DEVICE=cuda` is safe.

---

## Common Errors and Fixes

### `CUDA out of memory`

```
torch.cuda.OutOfMemoryError: CUDA out of memory
```

Fix: Lower `GPU_MEMORY_UTILIZATION` (try 0.80) or reduce `MAX_MODEL_LEN`:

```bash
GPU_MEMORY_UTILIZATION=0.80 MAX_MODEL_LEN=4096 bash start.sh
```

### `vLLM did not become healthy after 600s`

Causes:
- Insufficient VRAM — lower `GPU_MEMORY_UTILIZATION`
- Model weights corrupted or incomplete — re-run `scripts/download_models.sh`
- Port 8001 already in use — kill the existing process: `fuser -k 8001/tcp`

### `Required model directories not found`

FastAPI refuses to start:

```
RuntimeError: Required model directories not found. Run scripts/download_models.sh first.
  Missing:
    LLM (Qwen2.5-7B-Instruct): '/workspace/models/Qwen2.5-7B-Instruct'
```

Fix:

```bash
bash scripts/download_models.sh
```

### `vLLM not reachable ... AI generation features will be unavailable`

FastAPI started before vLLM was ready. This is a warning, not a fatal error.
vLLM might still be loading. Check:

```bash
curl http://localhost:8001/health
```

If vLLM never comes up, check its logs in the terminal where `start.sh` is running.

### `flash-attn` install fails

Some RunPod templates don't include the right CUDA headers for `flash-attn`.

Fix: comment out `flash-attn` in `requirements.vllm.txt` and reinstall:

```bash
pip install -r requirements.vllm.txt
```

vLLM works without Flash Attention, just with slightly higher memory usage.

### Models re-downloading every pod restart

You are not using a Network Volume. Attach a RunPod Network Volume and set:

```
MODEL_BASE_DIR=/runpod-volume/models
```

---

## Verifying All Three Models Work

### 1. LLM (Qwen2.5-7B-Instruct via vLLM)

```bash
curl -s -X POST http://localhost:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer vllm-local" \
  -d '{
    "model": "Qwen/Qwen2.5-7B-Instruct",
    "messages": [{"role": "user", "content": "Say hello in one sentence."}],
    "max_tokens": 50
  }' | python3 -m json.tool
```

Expected: `choices[0].message.content` contains a sentence.

### 2. BGE-M3 (embeddings)

```bash
python3 -c "
from sentence_transformers import SentenceTransformer
m = SentenceTransformer('/workspace/models/bge-m3', device='cpu')
emb = m.encode('Test sentence', normalize_embeddings=True)
print(f'BGE-M3 OK — embedding dim: {len(emb)}')
"
```

Expected: `BGE-M3 OK — embedding dim: 1024`

### 3. GOT-OCR2.0 (OCR)

```bash
python3 -c "
from transformers import AutoTokenizer, AutoModel
import os
model_path = '/workspace/models/GOT-OCR2_0'
assert os.path.isdir(model_path), f'GOT-OCR2.0 not found at {model_path}'
tok = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
print('GOT-OCR2.0 OK — tokenizer loaded successfully')
"
```

Expected: `GOT-OCR2.0 OK — tokenizer loaded successfully`

> **Note:** Full model load (~1.2 GB into memory) happens on the first OCR request, not at startup.
> GOT-OCR2.0 uses GPU if ≥2.5 GB VRAM is free; otherwise falls back to CPU (~25–60 s/page).

---

## Quick Command Reference

```bash
# Install GPU dependencies
pip install -r requirements.vllm.txt

# Install backend dependencies
pip install -r backend/requirements.txt

# Download all models
bash scripts/download_models.sh

# Verify environment
bash scripts/verify_runpod_setup.sh

# Start everything
bash start.sh

# Check vLLM health
curl http://localhost:8001/health

# Check FastAPI health
curl http://localhost:8000/api/health

# Watch logs (if running start.sh in background)
# vLLM logs appear in the start.sh terminal before FastAPI starts
```
