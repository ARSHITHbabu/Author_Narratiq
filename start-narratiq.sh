#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  NarratIQ AI v3.0 — Self-Bootstrapping Startup Script
#
#  Works on a BRAND NEW pod — installs every dependency
#  automatically, then starts vLLM + Backend + Frontend.
#
#  Usage:  bash /workspace/narratiq-ai/start-narratiq.sh
#
#  Subsequent runs skip already-installed packages (fast).
# ═══════════════════════════════════════════════════════════════
set -e

BACKEND_DIR="/workspace/narratiq-ai/backend"
FRONTEND_DIR="/workspace/narratiq-ai/frontend"
MODEL_DIR="/workspace/models"
VLLM_PORT=9001
BACKEND_PORT=8000
FRONTEND_PORT=3000
LOG_DIR="/tmp/narratiq-logs"
mkdir -p "$LOG_DIR"

# Pinned versions that are confirmed to work with CUDA 12.7
VLLM_VERSION="0.8.5"
NODE_MAJOR="20"

# ── Detect RunPod public URLs ──────────────────────────────────
POD_ID="${RUNPOD_POD_ID:-local}"
if [ "$POD_ID" != "local" ]; then
  BACKEND_PUBLIC_URL="https://${POD_ID}-${BACKEND_PORT}.proxy.runpod.net"
  FRONTEND_PUBLIC_URL="https://${POD_ID}-${FRONTEND_PORT}.proxy.runpod.net"
else
  BACKEND_PUBLIC_URL="http://localhost:${BACKEND_PORT}"
  FRONTEND_PUBLIC_URL="http://localhost:${FRONTEND_PORT}"
fi

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║         NarratIQ AI v3.0 — Self-Bootstrapping           ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║  Backend  : $BACKEND_PUBLIC_URL"
echo "║  Frontend : $FRONTEND_PUBLIC_URL"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ══════════════════════════════════════════════════════════════
# STEP 1 — Install system & Python dependencies (skipped if OK)
# ══════════════════════════════════════════════════════════════
echo "[1/6] Checking and installing dependencies..."

# ── 1a. Node.js ───────────────────────────────────────────────
if ! command -v node &>/dev/null; then
  echo "  Node.js not found — installing Node ${NODE_MAJOR}..."
  curl -fsSL https://deb.nodesource.com/setup_${NODE_MAJOR}.x | bash - >> "$LOG_DIR/node-install.log" 2>&1
  apt-get install -y nodejs >> "$LOG_DIR/node-install.log" 2>&1
  echo "  Node.js: $(node --version) installed"
else
  echo "  Node.js: $(node --version) — OK"
fi

# ── 1b. Remove packages left by wrong vllm versions ──────────
# (vllm >0.8.5 installs flashinfer/tvm-ffi built for newer CUDA;
#  they break on CUDA 12.7 driver with an undefined-symbol error)
for pkg in flashinfer-cubin flashinfer-python apache-tvm-ffi torch-c-dlpack-ext; do
  if pip show "$pkg" > /dev/null 2>&1; then
    echo "  Removing incompatible package: $pkg"
    pip uninstall -y "$pkg" >> "$LOG_DIR/pip-cleanup.log" 2>&1
  fi
done

# ── 1c. vLLM (must be exactly 0.8.5 for CUDA 12.7) ──────────
VLLM_INSTALLED=$(pip show vllm 2>/dev/null | grep "^Version:" | awk '{print $2}')
if [ "$VLLM_INSTALLED" != "$VLLM_VERSION" ]; then
  echo "  Installing vllm==${VLLM_VERSION} — takes 2-4 min on first run..."
  pip install "vllm==${VLLM_VERSION}" > "$LOG_DIR/pip-vllm.log" 2>&1
  echo "  vllm ${VLLM_VERSION} installed"
else
  echo "  vllm ${VLLM_VERSION} — OK"
fi

# ── 1d. Remove any leftover incompatible packages again ───────
# (vllm install may have pulled them back in)
for pkg in flashinfer-cubin flashinfer-python apache-tvm-ffi torch-c-dlpack-ext; do
  if pip show "$pkg" > /dev/null 2>&1; then
    echo "  Removing post-install incompatible package: $pkg"
    pip uninstall -y "$pkg" >> "$LOG_DIR/pip-cleanup.log" 2>&1
  fi
done

# ── 1e. transformers must be 4.x (vllm 0.8.5 breaks with 5.x)
TRANSFORMERS_MAJOR=$(pip show transformers 2>/dev/null | grep "^Version:" | awk '{print $2}' | cut -d. -f1)
if [ "${TRANSFORMERS_MAJOR:-0}" -ge 5 ]; then
  echo "  Downgrading transformers 5.x → 4.x (required by vllm 0.8.5)..."
  pip install "transformers>=4.51.1,<5.0" >> "$LOG_DIR/pip-transformers.log" 2>&1
  echo "  transformers downgraded"
else
  TRANSFORMERS_VER=$(pip show transformers 2>/dev/null | grep "^Version:" | awk '{print $2}')
  echo "  transformers ${TRANSFORMERS_VER:-not installed} — OK"
fi

# ── 1f. Backend Python dependencies ──────────────────────────
echo "  Installing backend Python packages..."
pip install \
  "sqlalchemy==2.0.30" \
  "python-jose[cryptography]==3.3.0" \
  "bcrypt==4.0.1" \
  "aiofiles==23.2.1" \
  "httpx>=0.27.0,<0.28" \
  "alembic==1.13.1" \
  "sentence-transformers>=3.0.0" \
  "accelerate>=0.30.0" \
  "python-multipart>=0.0.9" \
  "python-dotenv>=1.0.0" \
  "Pillow>=10.0.0" \
  "sentencepiece>=0.2.0" \
  "tiktoken" \
  "einops" \
  "transformers_stream_generator" \
  "verovio" \
  >> "$LOG_DIR/pip-backend.log" 2>&1
# Also ensure HF download tooling is available (needed for model downloads)
pip install -q "huggingface-hub>=0.24.0" "hf-transfer>=0.1.8" >> "$LOG_DIR/pip-backend.log" 2>&1
echo "  Backend packages — OK"

# ── 1g. Frontend npm install (only when node_modules missing) -
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  echo "  node_modules missing — running npm install (~1-2 min)..."
  cd "$FRONTEND_DIR"
  npm install >> "$LOG_DIR/npm-install.log" 2>&1
  echo "  npm install — OK"
else
  echo "  node_modules — OK"
fi

# Fix execute permissions on Next.js CLI (can be lost on new pods)
chmod -R +x "$FRONTEND_DIR/node_modules/.bin/" 2>/dev/null || true

echo "  All dependencies ready."

# ══════════════════════════════════════════════════════════════
# STEP 2 — Download models if missing (skips files that exist)
# ══════════════════════════════════════════════════════════════
echo ""
echo "[2/6] Checking model files..."

MODELS_MISSING=0
# Required models: LLM, embeddings, and GOT-OCR2.0 (replaced TrOCR + EasyOCR)
for model in "Qwen2.5-7B-Instruct" "bge-m3" "GOT-OCR2_0"; do
  if [ ! -d "$MODEL_DIR/$model" ] || [ -z "$(ls -A "$MODEL_DIR/$model" 2>/dev/null)" ]; then
    echo "  Missing: $model"
    MODELS_MISSING=1
  fi
done

if [ "$MODELS_MISSING" -eq 1 ]; then
  echo "  One or more models missing — starting download..."
  echo "  (Qwen2.5-7B is ~14 GB, GOT-OCR2.0 is ~1.4 GB — first run takes 10-20 min)"
  echo "  Tip: set HF_TOKEN=hf_xxx before running for higher rate limits"
  echo ""
  # Enable fast Rust-based downloader for ~3x speed
  export HF_HUB_ENABLE_HF_TRANSFER=1
  export MODEL_BASE_DIR="$MODEL_DIR"
  bash /workspace/narratiq-ai/scripts/download_models.sh 2>&1 | tee "$LOG_DIR/model-download.log"
  echo ""
  echo "  Download complete."
else
  echo "  Models: OK (Qwen2.5-7B + BGE-M3 + GOT-OCR2.0)"
fi

# ══════════════════════════════════════════════════════════════
# STEP 3 — Start vLLM
# ══════════════════════════════════════════════════════════════
echo ""
echo "[3/6] Starting vLLM (Qwen2.5-7B-Instruct)..."

pkill -f "vllm.entrypoints.openai.api_server" 2>/dev/null || true
sleep 2

GPU_COUNT=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | wc -l | tr -d ' ')
GPU_VRAM_MIB=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d ' ')
GPU_VRAM_GB=$((GPU_VRAM_MIB / 1024))
echo "  GPUs: ${GPU_COUNT}x ${GPU_VRAM_GB}GB"

# Qwen2.5-7B has 4 KV heads — TP must divide 4 (valid: 1, 2, 4)
if   [ "$GPU_COUNT" -ge 4 ]; then TP=4; MML=32768; UTIL=0.90
elif [ "$GPU_COUNT" -ge 2 ]; then TP=2; MML=16384; UTIL=0.90
else                                TP=1; MML=8192;  UTIL=0.88
fi

python3 -m vllm.entrypoints.openai.api_server \
  --model                  "$MODEL_DIR/Qwen2.5-7B-Instruct" \
  --served-model-name      "Qwen/Qwen2.5-7B-Instruct" \
  --dtype                  auto \
  --gpu-memory-utilization $UTIL \
  --tensor-parallel-size   $TP \
  --max-model-len          $MML \
  --max-num-seqs           256 \
  --enable-chunked-prefill \
  --enable-prefix-caching \
  --host                   0.0.0.0 \
  --port                   $VLLM_PORT \
  --disable-log-requests \
  > "$LOG_DIR/vllm.log" 2>&1 &

VLLM_PID=$!
echo "  vLLM PID: $VLLM_PID  (loading 15 GB model — takes 2-4 min)"

# ══════════════════════════════════════════════════════════════
# STEP 4 — Wait for vLLM health
# ══════════════════════════════════════════════════════════════
echo ""
echo "[4/6] Waiting for vLLM to load model into GPU VRAM..."
for i in $(seq 1 72); do
  if curl -s "http://localhost:${VLLM_PORT}/health" > /dev/null 2>&1; then
    echo "  vLLM ready after ~$((i*5))s"
    break
  fi
  if [ $i -eq 72 ]; then
    echo ""
    echo "  ERROR: vLLM did not start in 6 minutes."
    echo "  Check: tail -50 $LOG_DIR/vllm.log"
    exit 1
  fi
  printf "  waiting... (%ds)\r" $((i*5))
  sleep 5
done

# ══════════════════════════════════════════════════════════════
# STEP 5 — Start FastAPI backend
# ══════════════════════════════════════════════════════════════
echo ""
echo "[5/6] Starting FastAPI backend..."
pkill -f "uvicorn main:app" 2>/dev/null || true
sleep 1

cd "$BACKEND_DIR"

# Tell the backend where vLLM is (port 9001, not the default 8001)
export VLLM_BASE_URL="http://127.0.0.1:${VLLM_PORT}/v1"
export VLLM_MODEL_NAME="Qwen/Qwen2.5-7B-Instruct"
export MODEL_BASE_DIR="$MODEL_DIR"
# CORS: allow the RunPod proxy URL + localhost for development
export CORS_ORIGINS='["'"${FRONTEND_PUBLIC_URL}"'","http://localhost:3000","http://127.0.0.1:3000"]'

python3 -m uvicorn main:app \
  --host    0.0.0.0 \
  --port    $BACKEND_PORT \
  --workers 1 \
  --no-access-log \
  > "$LOG_DIR/backend.log" 2>&1 &

BACKEND_PID=$!
echo "  Backend PID: $BACKEND_PID"

for i in $(seq 1 15); do
  if curl -s "http://localhost:${BACKEND_PORT}/api/health" > /dev/null 2>&1; then
    echo "  Backend ready"
    break
  fi
  sleep 2
done

# ══════════════════════════════════════════════════════════════
# STEP 6 — Build & start Next.js frontend
# ══════════════════════════════════════════════════════════════
echo ""
echo "[6/6] Building & starting Next.js frontend..."

cd "$FRONTEND_DIR"

# Bake the backend URL into the JS bundle at build time
cat > .env.local << EOF
NEXT_PUBLIC_API_URL=${BACKEND_PUBLIC_URL}
EOF
echo "  NEXT_PUBLIC_API_URL=${BACKEND_PUBLIC_URL}"

echo "  Building (~30-60s)..."
npm run build > "$LOG_DIR/frontend-build.log" 2>&1

npm start -- --port $FRONTEND_PORT > "$LOG_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!
sleep 4
echo "  Frontend PID: $FRONTEND_PID"

# ══════════════════════════════════════════════════════════════
# Done
# ══════════════════════════════════════════════════════════════
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║                 NarratIQ AI is READY                    ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║  Open in browser:                                        ║"
echo "║  $FRONTEND_PUBLIC_URL"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║  Logs (if anything seems wrong):                         ║"
echo "║    vLLM    : tail -f $LOG_DIR/vllm.log"
echo "║    Backend : tail -f $LOG_DIR/backend.log"
echo "║    Frontend: tail -f $LOG_DIR/frontend.log"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "PIDs: vLLM=$VLLM_PID  Backend=$BACKEND_PID  Frontend=$FRONTEND_PID"
echo ""
