#!/bin/bash
# Verify that the RunPod environment is correctly set up before running NarratIQ AI.
# Run this script AFTER downloading models and BEFORE running start.sh.
#
# Usage:
#   bash scripts/verify_runpod_setup.sh

set -uo pipefail

MODEL_BASE_DIR="${MODEL_BASE_DIR:-/workspace/models}"
LLM_MODEL_PATH="${LLM_MODEL_PATH:-${MODEL_BASE_DIR}/Qwen2.5-7B-Instruct}"
BGE_MODEL_PATH="${BGE_MODEL_PATH:-${MODEL_BASE_DIR}/bge-m3}"
GOT_OCR_MODEL_PATH="${GOT_OCR_MODEL_PATH:-${MODEL_BASE_DIR}/GOT-OCR2_0}"
VLLM_PORT="${VLLM_PORT:-8001}"
BACKEND_PORT="${BACKEND_PORT:-8000}"

PASS=0
FAIL=0

ok()   { echo "  [OK]  $1"; PASS=$((PASS+1)); }
fail() { echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }
warn() { echo "  [WARN] $1"; }
hdr()  { echo ""; echo "── $1"; }

echo "======================================================"
echo " NarratIQ AI — RunPod Setup Verification"
echo "======================================================"

# ── Python ────────────────────────────────────────────────────────────────────
hdr "Python"
if command -v python3 &>/dev/null; then
    PY_VER=$(python3 --version 2>&1)
    ok "Python found: ${PY_VER}"
    # Check version >= 3.10
    PY_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")
    PY_MAJOR=$(python3 -c "import sys; print(sys.version_info.major)")
    if [ "${PY_MAJOR}" -ge 3 ] && [ "${PY_MINOR}" -ge 10 ]; then
        ok "Python >= 3.10"
    else
        fail "Python 3.10+ required — found ${PY_VER}"
    fi
else
    fail "python3 not found"
fi

# ── GPU / CUDA ────────────────────────────────────────────────────────────────
hdr "GPU / CUDA"
if command -v nvidia-smi &>/dev/null; then
    GPU_INFO=$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null | head -1)
    if [ -n "${GPU_INFO}" ]; then
        ok "GPU visible: ${GPU_INFO}"
    else
        fail "nvidia-smi ran but returned no GPU info"
    fi
else
    fail "nvidia-smi not found — GPU driver not installed or not a GPU pod"
fi

if python3 -c "import torch; assert torch.cuda.is_available()" 2>/dev/null; then
    CUDA_VER=$(python3 -c "import torch; print(torch.version.cuda)")
    ok "PyTorch CUDA available — CUDA ${CUDA_VER}"
else
    fail "PyTorch CUDA not available — check torch installation"
fi

# ── Model directories ─────────────────────────────────────────────────────────
hdr "Model Directories (MODEL_BASE_DIR=${MODEL_BASE_DIR})"

check_model_dir() {
    local label="$1"
    local path="$2"
    if [ -d "${path}" ] && [ "$(ls -A "${path}" 2>/dev/null)" ]; then
        local size
        size=$(du -sh "${path}" 2>/dev/null | cut -f1)
        ok "${label}: ${path}  (${size})"
    elif [ -d "${path}" ]; then
        fail "${label}: directory exists but is EMPTY — ${path}"
        echo "        → Re-run scripts/download_models.sh"
    else
        fail "${label}: directory NOT FOUND — ${path}"
        echo "        → Run scripts/download_models.sh"
    fi
}

check_model_dir "LLM (Qwen2.5-7B-Instruct)" "${LLM_MODEL_PATH}"
check_model_dir "BGE-M3 (embeddings)"         "${BGE_MODEL_PATH}"
check_model_dir "GOT-OCR2.0 (OCR, required)"  "${GOT_OCR_MODEL_PATH}"

# ── Key model files ───────────────────────────────────────────────────────────
hdr "Key Model Files"
if [ -d "${LLM_MODEL_PATH}" ]; then
    if ls "${LLM_MODEL_PATH}"/config.json &>/dev/null; then
        ok "Qwen config.json present"
    else
        fail "Qwen config.json missing — download may be incomplete"
    fi
    if ls "${LLM_MODEL_PATH}"/*.safetensors &>/dev/null 2>&1 || ls "${LLM_MODEL_PATH}"/*.bin &>/dev/null 2>&1; then
        ok "Qwen model weights (.safetensors or .bin) present"
    else
        fail "Qwen model weights missing — download may be incomplete"
    fi
fi

# ── Python packages ───────────────────────────────────────────────────────────
hdr "Python Packages"
check_pkg() {
    local pkg="$1"
    local import_name="${2:-$1}"
    if python3 -c "import ${import_name}" 2>/dev/null; then
        local ver
        ver=$(python3 -c "import importlib.metadata; print(importlib.metadata.version('${pkg}'))" 2>/dev/null || echo "unknown")
        ok "${pkg} installed (${ver})"
    else
        fail "${pkg} NOT installed — run: pip install ${pkg}"
    fi
}

check_pkg "fastapi"
check_pkg "uvicorn"
check_pkg "sqlalchemy" "sqlalchemy"
check_pkg "pydantic-settings" "pydantic_settings"
check_pkg "openai"
check_pkg "sentence-transformers" "sentence_transformers"
check_pkg "transformers"
check_pkg "torch"
check_pkg "Pillow" "PIL"
check_pkg "httpx"

# vLLM (RunPod-only)
if python3 -c "import vllm" 2>/dev/null; then
    VER=$(python3 -c "import importlib.metadata; print(importlib.metadata.version('vllm'))" 2>/dev/null || echo "unknown")
    ok "vllm installed (${VER})"
else
    fail "vllm NOT installed — run: pip install -r requirements.vllm.txt"
fi

# ── Port availability ─────────────────────────────────────────────────────────
hdr "Port Availability"
check_port() {
    local port="$1"
    local label="$2"
    if ss -tlnp 2>/dev/null | grep -q ":${port} " || netstat -tlnp 2>/dev/null | grep -q ":${port} "; then
        warn "Port ${port} (${label}) is already in use — something is running on it"
    else
        ok "Port ${port} (${label}) is free"
    fi
}

check_port "${VLLM_PORT}"    "vLLM"
check_port "${BACKEND_PORT}" "FastAPI"

# ── Disk space ────────────────────────────────────────────────────────────────
hdr "Disk Space (/workspace)"
if command -v df &>/dev/null; then
    AVAIL_GB=$(df -BG /workspace 2>/dev/null | awk 'NR==2 {gsub("G",""); print $4}')
    if [ -n "${AVAIL_GB}" ]; then
        if [ "${AVAIL_GB}" -ge 30 ]; then
            ok "Available disk: ${AVAIL_GB} GB (>= 30 GB required)"
        else
            fail "Available disk: ${AVAIL_GB} GB — need at least 30 GB for all three models"
        fi
    fi
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "======================================================"
echo " Verification Summary"
echo "   PASSED : ${PASS}"
echo "   FAILED : ${FAIL}"
echo "======================================================"

if [ "${FAIL}" -gt 0 ]; then
    echo ""
    echo " Fix the FAILED items above, then re-run this script."
    echo " See docs/operations/runpod-deployment.md for step-by-step instructions."
    exit 1
else
    echo ""
    echo " All checks passed! You can now run:"
    echo "   bash start.sh"
    exit 0
fi
