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

# vLLM 0.9.2+ required for NVIDIA Blackwell (sm_120) GPUs via PyTorch 2.7+
# (0.8.5 was for CUDA 12.7 / pre-Blackwell hardware)
VLLM_VERSION="0.9.2"
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

# ── 1b. PostgreSQL 16 + pgvector ─────────────────────────────────────────────
if ! command -v psql &>/dev/null; then
  echo "  PostgreSQL not found — installing PostgreSQL 16 + pgvector..."
  # Add PGDG repo if postgresql-16 is not in the default apt sources
  # (Ubuntu 22.04 ships postgresql-14 by default; 16 requires PGDG)
  if ! apt-cache show postgresql-16 &>/dev/null 2>&1; then
    echo "  Adding PGDG apt repository for PostgreSQL 16..."
    apt-get install -y curl gnupg lsb-release >> "$LOG_DIR/pg-install.log" 2>&1
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
      | gpg --dearmor -o /usr/share/keyrings/postgresql-archive-keyring.gpg \
      >> "$LOG_DIR/pg-install.log" 2>&1
    echo "deb [signed-by=/usr/share/keyrings/postgresql-archive-keyring.gpg] \
https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
      > /etc/apt/sources.list.d/pgdg.list
    apt-get update -qq >> "$LOG_DIR/pg-install.log" 2>&1
  fi
  apt-get install -y postgresql-16 postgresql-client-16 postgresql-16-pgvector \
    >> "$LOG_DIR/pg-install.log" 2>&1
  echo "  PostgreSQL 16 + pgvector — installed"
else
  echo "  PostgreSQL: $(psql --version 2>/dev/null | head -1 | awk '{print $3}') — OK"
fi

# ── 1b-ii. Remove packages only incompatible with old CUDA 12.7 vLLM installs ──
# (flashinfer/tvm-ffi are fine on CUDA 12.8+/13.x — only remove if stale 0.8.x artifacts remain)
if pip show vllm 2>/dev/null | grep -q "Version: 0\.8\."; then
  for pkg in flashinfer-cubin flashinfer-python apache-tvm-ffi torch-c-dlpack-ext; do
    if pip show "$pkg" > /dev/null 2>&1; then
      echo "  Removing old vLLM 0.8.x incompatible package: $pkg"
      pip uninstall -y "$pkg" >> "$LOG_DIR/pip-cleanup.log" 2>&1
    fi
  done
fi

# ── 1c. vLLM ─────────────────────────────────────────────────
VLLM_INSTALLED=$(pip show vllm 2>/dev/null | grep "^Version:" | awk '{print $2}')
if [ "$VLLM_INSTALLED" != "$VLLM_VERSION" ]; then
  echo "  Installing vllm==${VLLM_VERSION} — takes 2-4 min on first run..."
  pip install "vllm==${VLLM_VERSION}" > "$LOG_DIR/pip-vllm.log" 2>&1
  echo "  vllm ${VLLM_VERSION} installed"
else
  echo "  vllm ${VLLM_VERSION} — OK"
fi

# ── 1d. PyTorch cu128 — required for Blackwell (sm_120) GPUs ─
# vLLM's pip install pulls torch+cu126 which has no sm_120 kernels.
# Force the cu128 build so CUDA ops work on RTX 4500 Blackwell and newer.
TORCH_VER=$(python3 -c "import torch; print(torch.__version__)" 2>/dev/null)
if echo "$TORCH_VER" | grep -qv "cu128"; then
  echo "  Installing PyTorch cu128 (Blackwell sm_120 support)..."
  pip install --force-reinstall torch==2.7.0 torchvision==0.22.0 torchaudio==2.7.0 \
    --index-url https://download.pytorch.org/whl/cu128 \
    >> "$LOG_DIR/pip-torch-cu128.log" 2>&1
  echo "  PyTorch cu128 — installed"
else
  echo "  PyTorch ${TORCH_VER} (cu128) — OK"
fi

# ── 1e. Patch vLLM ovis.py — AutoConfig.register exist_ok=True ─
# vLLM 0.9.2 registers 'aimv2' without exist_ok=True; transformers 4.51+
# already has it, causing ValueError on import. Only patches lines missing exist_ok.
OVIS_PY=$(python3 -c "import vllm; import os; print(os.path.dirname(vllm.__file__))" 2>/dev/null)/transformers_utils/configs/ovis.py
if [ -f "$OVIS_PY" ] && grep -q "AutoConfig.register" "$OVIS_PY"; then
  # Only modify lines that have AutoConfig.register but NOT exist_ok
  sed -i '/AutoConfig\.register/{ /exist_ok/!s/)$/, exist_ok=True)/; }' "$OVIS_PY" 2>/dev/null || true
fi

# ── 1f. NumPy — pin ≤2.2 (numba requires <=2.2; torch cu128 pulls 2.4) ─
NUMPY_VER=$(python3 -c "import numpy; print(numpy.__version__)" 2>/dev/null)
NUMPY_MINOR=$(echo "$NUMPY_VER" | cut -d. -f2)
if [ "${NUMPY_MINOR:-0}" -gt 2 ] 2>/dev/null; then
  echo "  Downgrading NumPy ${NUMPY_VER} → 2.2 (numba compatibility)..."
  pip install "numpy>=2.0,<=2.2" >> "$LOG_DIR/pip-numpy.log" 2>&1
  echo "  NumPy — downgraded"
else
  echo "  NumPy ${NUMPY_VER} — OK"
fi

# ── 1g. transformers — vLLM 0.9+ works with both 4.x and 5.x ─
TRANSFORMERS_VER=$(pip show transformers 2>/dev/null | grep "^Version:" | awk '{print $2}')
echo "  transformers ${TRANSFORMERS_VER:-not installed} — OK"

# ── 1f. Backend Python dependencies ──────────────────────────
echo "  Installing backend Python packages..."
pip install \
  "sqlalchemy==2.0.30" \
  "psycopg2-binary>=2.9.9" \
  "pgvector>=0.3.0" \
  "python-jose[cryptography]==3.3.0" \
  "bcrypt==4.0.1" \
  "aiofiles==23.2.1" \
  "httpx>=0.27.0,<0.28" \
  "alembic==1.13.1" \
  "sentence-transformers>=3.0.0" \
  "accelerate>=0.30.0" \
  "python-multipart>=0.0.9" \
  "python-dotenv>=1.0.0" \
  "Pillow>=11.1.0" \
  "pillow-heif>=1.0.0" \
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

# Clear torch compile cache — a prior failed run on a different GPU/CUDA version
# leaves corrupted artifacts that cause "BackendCompilerFailed" on next start.
rm -rf ~/.cache/vllm/torch_compile_cache 2>/dev/null || true

GPU_COUNT=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | wc -l | tr -d ' ')
GPU_VRAM_MIB=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d ' ')
GPU_VRAM_GB=$((GPU_VRAM_MIB / 1024))
echo "  GPUs: ${GPU_COUNT}x ${GPU_VRAM_GB}GB"

# Qwen2.5-7B has 4 KV heads — TP must divide 4 (valid: 1, 2, 4)
if   [ "$GPU_COUNT" -ge 4 ]; then TP=4; MML=32768; UTIL=0.90
elif [ "$GPU_COUNT" -ge 2 ]; then TP=2; MML=16384; UTIL=0.90
else                                TP=1; MML=8192;  UTIL=0.88
fi


# Blackwell (sm_120) requires NCCL_P2P_DISABLE=1 + NCCL_SHM_DISABLE=1:
# the Blackwell P2P/SHM paths in NCCL 2.21/2.26 deadlock during ncclCommInitRank.
# Fall back to socket transport, which works correctly on all architectures.
NCCL_P2P_DISABLE=1 NCCL_SHM_DISABLE=1 \
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
# STEP 4b — Ensure SECRET_KEY is set in backend/.env
# ══════════════════════════════════════════════════════════════
ENV_FILE="$BACKEND_DIR/.env"
if ! grep -q "^SECRET_KEY=" "$ENV_FILE" 2>/dev/null; then
  SK=$(python3 -c "import secrets; print(secrets.token_hex(32))")
  echo "SECRET_KEY=${SK}" >> "$ENV_FILE"
  echo "  [setup] Generated new SECRET_KEY and saved to backend/.env"
else
  echo "  SECRET_KEY: OK"
fi

# ══════════════════════════════════════════════════════════════
# STEP 4c — PostgreSQL: start, create DB, enable pgvector,
#            write DATABASE_URL, create tables, run migrations
# ══════════════════════════════════════════════════════════════
echo ""
echo "[4c/6] Setting up PostgreSQL database..."

# Start PostgreSQL (idempotent — no-op if already running)
pg_ctlcluster 16 main start 2>/dev/null \
  || service postgresql start 2>/dev/null \
  || true
sleep 2

# Create role + database + extension (all idempotent)
sudo -u postgres psql -c "CREATE USER narratiq WITH PASSWORD 'narratiq';" 2>/dev/null || true
sudo -u postgres psql -c "CREATE DATABASE narratiq OWNER narratiq;" 2>/dev/null || true
sudo -u postgres psql -d narratiq -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>/dev/null || true
echo "  Database 'narratiq' ready, pgvector extension enabled"

# Write DATABASE_URL to backend/.env (idempotent)
if ! grep -q "^DATABASE_URL=" "$ENV_FILE" 2>/dev/null; then
  echo "DATABASE_URL=postgresql+psycopg2://narratiq:narratiq@localhost:5432/narratiq" >> "$ENV_FILE"
  echo "  DATABASE_URL written to backend/.env"
else
  echo "  DATABASE_URL: OK"
fi

# Pre-create tables from ORM models (idempotent; needed before alembic runs)
cd "$BACKEND_DIR"
python3 - <<'PYEOF'
import models  # noqa: F401 — registers all ORM models
from database import engine, Base, run_db_migrations
Base.metadata.create_all(bind=engine)
run_db_migrations(engine)
print("[setup] Tables created/verified")
PYEOF

# Apply Alembic migrations (HNSW indexes + future schema changes, idempotent)
cd "$BACKEND_DIR"
python3 -m alembic upgrade head
echo "  Alembic migrations applied"

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
