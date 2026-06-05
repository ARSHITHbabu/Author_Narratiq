#!/bin/bash
# NarratIQ AI — RunPod startup script
#
# Execution order:
#   0. Detect GPUs, auto-configure TP / MAX_MODEL_LEN / GPU_MEMORY_UTILIZATION
#   1. Validate model paths exist
#   2. Start vLLM (background) — loads Qwen2.5-7B-Instruct into GPU VRAM
#   3. Wait for vLLM /health endpoint
#   4. Start FastAPI (foreground) — pre-loads BGE-M3, warms up vLLM
#
# GPU auto-detection:
#   TENSOR_PARALLEL_SIZE, GPU_MEMORY_UTILIZATION, and MAX_MODEL_LEN are all
#   set automatically based on how many GPUs are present.
#   Override any of them by setting the env var before running this script.
#
# Example — force specific values:
#   TENSOR_PARALLEL_SIZE=2 MAX_MODEL_LEN=32768 bash start.sh
set -euo pipefail

# ── Static config (path / port / model name) ──────────────────────────────────
MODEL_BASE_DIR="${MODEL_BASE_DIR:-/workspace/models}"
VLLM_MODEL_NAME="${VLLM_MODEL_NAME:-Qwen/Qwen2.5-7B-Instruct}"
LLM_MODEL_PATH="${LLM_MODEL_PATH:-${MODEL_BASE_DIR}/Qwen2.5-7B-Instruct}"
BGE_MODEL_PATH="${BGE_MODEL_PATH:-${MODEL_BASE_DIR}/bge-m3}"
VLLM_PORT="${VLLM_PORT:-8001}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
BACKEND_DIR="${BACKEND_DIR:-/workspace/narratiq-ai/backend}"

# ── STEP 0: GPU Detection ─────────────────────────────────────────────────────
echo ""
echo "======================================================"
echo " NarratIQ AI — GPU Detection"
echo "======================================================"

if ! command -v nvidia-smi &>/dev/null; then
    echo "ERROR: nvidia-smi not found. Is this a GPU pod?"
    echo "  Make sure you are using a RunPod GPU template."
    exit 1
fi

# Count GPUs
GPU_COUNT=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | wc -l | tr -d ' ')

if [ "${GPU_COUNT}" -eq 0 ]; then
    echo "ERROR: nvidia-smi found no GPUs. Check pod GPU allocation."
    exit 1
fi

# Per-GPU VRAM in MiB (e.g. RTX 4090 = 24564 MiB ≈ 24 GB)
GPU_VRAM_MIB=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null \
    | head -1 | tr -d ' ')
GPU_VRAM_GB=$((GPU_VRAM_MIB / 1024))
TOTAL_VRAM_GB=$((GPU_COUNT * GPU_VRAM_GB))

# GPU name(s) for display
GPU_MODEL=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 | xargs)

echo ""
echo "  GPUs found : ${GPU_COUNT}× ${GPU_MODEL}"
echo "  VRAM/GPU   : ${GPU_VRAM_GB} GB  (${GPU_VRAM_MIB} MiB)"
echo "  Total VRAM : ${TOTAL_VRAM_GB} GB"

# ── Auto-select TENSOR_PARALLEL_SIZE ─────────────────────────────────────────
# Qwen2.5-7B-Instruct uses GQA with num_key_value_heads = 4.
# vLLM requires TP to evenly divide num_key_value_heads.
# Valid TP values for this model: 1, 2, 4   (TP=3 crashes vLLM)
#
# If TENSOR_PARALLEL_SIZE is already set in env, respect it.
# Otherwise, auto-detect from GPU count.

if [ -n "${TENSOR_PARALLEL_SIZE:-}" ]; then
    TP_NOTE="(manually overridden)"
else
    case "${GPU_COUNT}" in
        1)
            TENSOR_PARALLEL_SIZE=1
            TP_NOTE="(auto: 1 GPU → TP=1)"
            ;;
        2)
            TENSOR_PARALLEL_SIZE=2
            TP_NOTE="(auto: 2 GPUs → TP=2)"
            ;;
        3)
            # TP=3 is invalid for Qwen2.5-7B-Instruct (4 KV heads not divisible by 3).
            # Use TP=2 — vLLM uses GPU 0+1; GPU 2 remains available for BGE-M3 if cuda.
            TENSOR_PARALLEL_SIZE=2
            TP_NOTE="(auto: 3 GPUs → TP=2 — TP=3 is invalid for this model's 4 KV heads)"
            ;;
        *)
            # 4+ GPUs: use TP=4 (next valid divisor of 4 KV heads after 2)
            TENSOR_PARALLEL_SIZE=4
            TP_NOTE="(auto: ${GPU_COUNT} GPUs → TP=4)"
            ;;
    esac
fi

# Effective VRAM for the TP group
EFFECTIVE_VRAM_GB=$((GPU_VRAM_GB * TENSOR_PARALLEL_SIZE))

# ── Auto-set GPU_MEMORY_UTILIZATION ──────────────────────────────────────────
# Multi-GPU: use 0.90 (more total VRAM means more KV cache headroom is fine).
# Single GPU: use 0.88 (leaves ~3 GB free for BGE-M3 on CPU + OS).
if [ -n "${GPU_MEMORY_UTILIZATION:-}" ]; then
    UTIL_NOTE="(manually overridden)"
else
    if [ "${GPU_COUNT}" -ge 2 ]; then
        GPU_MEMORY_UTILIZATION=0.90
        UTIL_NOTE="(auto: multi-GPU)"
    else
        GPU_MEMORY_UTILIZATION=0.88
        UTIL_NOTE="(auto: single GPU)"
    fi
fi

# ── Auto-scale MAX_MODEL_LEN based on effective VRAM ─────────────────────────
# More VRAM = larger KV cache pool = larger context window can be served.
# KV cache for Qwen2.5-7B @ fp16: ~0.5 MB per token per layer.
# These limits are conservative to ensure stable operation.
if [ -n "${MAX_MODEL_LEN:-}" ]; then
    LEN_NOTE="(manually overridden)"
else
    if [ "${EFFECTIVE_VRAM_GB}" -ge 48 ]; then
        MAX_MODEL_LEN=32768
        LEN_NOTE="(auto: ${EFFECTIVE_VRAM_GB} GB effective VRAM → 32K ctx)"
    elif [ "${EFFECTIVE_VRAM_GB}" -ge 24 ]; then
        MAX_MODEL_LEN=16384
        LEN_NOTE="(auto: ${EFFECTIVE_VRAM_GB} GB effective VRAM → 16K ctx)"
    else
        MAX_MODEL_LEN=8192
        LEN_NOTE="(auto: ${EFFECTIVE_VRAM_GB} GB effective VRAM → 8K ctx)"
    fi
fi

VLLM_BASE_URL="${VLLM_BASE_URL:-http://127.0.0.1:${VLLM_PORT}/v1}"

# Print final resolved configuration
echo ""
echo "======================================================"
echo " NarratIQ AI — Launch Configuration"
echo "======================================================"
echo " LLM model    : ${LLM_MODEL_PATH}"
echo " vLLM port    : ${VLLM_PORT}"
echo " API port     : ${BACKEND_PORT}"
echo ""
echo " TP size      : ${TENSOR_PARALLEL_SIZE} ${TP_NOTE}"
echo " GPU util     : ${GPU_MEMORY_UTILIZATION} ${UTIL_NOTE}"
echo " Max ctx      : ${MAX_MODEL_LEN} tokens ${LEN_NOTE}"
echo ""
echo " VRAM budget  : ${EFFECTIVE_VRAM_GB} GB × ${GPU_MEMORY_UTILIZATION}"
echo "   → vLLM gets ~$(echo "${EFFECTIVE_VRAM_GB} ${GPU_MEMORY_UTILIZATION}" \
    | awk '{printf "%.0f", $1*$2}') GB for weights + KV cache"
echo "======================================================"

# ── STEP 1: Validate model paths ─────────────────────────────────────────────
echo ""
echo "[1/4] Validating model paths..."

if [ ! -d "${LLM_MODEL_PATH}" ]; then
    echo ""
    echo "ERROR: LLM model directory not found: ${LLM_MODEL_PATH}"
    echo "  Run: bash scripts/download_models.sh"
    exit 1
fi

if [ ! -d "${BGE_MODEL_PATH}" ]; then
    echo ""
    echo "ERROR: BGE-M3 model directory not found: ${BGE_MODEL_PATH}"
    echo "  Run: bash scripts/download_models.sh"
    exit 1
fi

echo "  LLM  : ${LLM_MODEL_PATH} [OK]"
echo "  BGE  : ${BGE_MODEL_PATH} [OK]"

# ── STEP 2: Start vLLM ───────────────────────────────────────────────────────
echo ""
echo "[2/4] Launching vLLM on port ${VLLM_PORT} with TP=${TENSOR_PARALLEL_SIZE}..."

python3 -m vllm.entrypoints.openai.api_server \
    --model                  "${LLM_MODEL_PATH}"         \
    --served-model-name      "${VLLM_MODEL_NAME}"        \
    --dtype                  auto                        \
    --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION}" \
    --tensor-parallel-size   "${TENSOR_PARALLEL_SIZE}"   \
    --max-model-len          "${MAX_MODEL_LEN}"          \
    --max-num-seqs           256                         \
    --enable-chunked-prefill                             \
    --enable-prefix-caching                              \
    --host                   0.0.0.0                     \
    --port                   "${VLLM_PORT}"              \
    --disable-log-requests                               \
    &

VLLM_PID=$!

# ── STEP 3: Wait for vLLM health ─────────────────────────────────────────────
echo ""
echo "[3/4] Waiting for vLLM to load model weights into GPU VRAM..."
echo "      Health URL : http://localhost:${VLLM_PORT}/health"
echo "      Timeout    : 600 s  (multi-GPU loads faster — usually 60–120 s)"

ELAPSED=0
until curl -sf "http://localhost:${VLLM_PORT}/health" > /dev/null 2>&1; do
    sleep 5
    ELAPSED=$((ELAPSED + 5))
    if [ "${ELAPSED}" -ge 600 ]; then
        echo ""
        echo "ERROR: vLLM did not become healthy within 600 s."
        echo ""
        echo "  Check for these errors in the output above:"
        echo "    CUDA out of memory  → lower GPU_MEMORY_UTILIZATION or MAX_MODEL_LEN"
        echo "    Weights not found   → re-run scripts/download_models.sh"
        echo "    Port in use         → fuser -k ${VLLM_PORT}/tcp"
        echo "    TP mismatch         → check TENSOR_PARALLEL_SIZE vs GPU count"
        echo ""
        kill "${VLLM_PID}" 2>/dev/null
        exit 1
    fi
    echo "  ...waiting (${ELAPSED}s elapsed)"
done
echo "  vLLM healthy after ${ELAPSED}s."

# ── STEP 4: Start FastAPI ─────────────────────────────────────────────────────
echo ""
echo "[4/4] Starting FastAPI on port ${BACKEND_PORT}..."
cd "${BACKEND_DIR}"

# Export all resolved values so FastAPI's pydantic-settings picks them up.
# These override anything in backend/.env for the GPU-tuned values.
export MODEL_BASE_DIR="${MODEL_BASE_DIR}"
export LLM_MODEL_PATH="${LLM_MODEL_PATH}"
export BGE_MODEL_PATH="${BGE_MODEL_PATH}"
export VLLM_BASE_URL="${VLLM_BASE_URL}"
export VLLM_MODEL_NAME="${VLLM_MODEL_NAME}"
export GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION}"
export TENSOR_PARALLEL_SIZE="${TENSOR_PARALLEL_SIZE}"
export MAX_MODEL_LEN="${MAX_MODEL_LEN}"
export BACKEND_HOST="0.0.0.0"
export BACKEND_PORT="${BACKEND_PORT}"

# Single worker — async handles concurrency; vLLM handles inference throughput.
# Multiple uvicorn workers would each load BGE-M3, wasting RAM.
exec uvicorn main:app \
    --host 0.0.0.0    \
    --port "${BACKEND_PORT}" \
    --workers 1       \
    --no-access-log
