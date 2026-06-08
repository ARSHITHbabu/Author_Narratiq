#!/bin/bash
# Download all NarratIQ AI models from Hugging Face into /workspace/models.
#
# Usage:
#   bash scripts/download_models.sh
#
# With a Hugging Face token (for gated models or higher rate limits):
#   HF_TOKEN=hf_xxx bash scripts/download_models.sh
#
# Safe to re-run — skips directories that are already populated.

set -euo pipefail

MODEL_BASE_DIR="${MODEL_BASE_DIR:-/workspace/models}"
HF_TOKEN="${HF_TOKEN:-}"

echo "======================================================"
echo " NarratIQ AI — Model Download"
echo " Destination: ${MODEL_BASE_DIR}"
echo "======================================================"

# ── 1. Authenticate (optional) ───────────────────────────────────────────────
if [ -n "${HF_TOKEN}" ]; then
    echo "[auth] Logging in to Hugging Face with provided token..."
    hf auth login --token "${HF_TOKEN}"
else
    echo "[auth] No HF_TOKEN set — downloading public models without authentication."
    echo "       Set HF_TOKEN=hf_xxx if you need gated model access or higher rate limits."
fi

# ── 2. Create destination directory ──────────────────────────────────────────
mkdir -p "${MODEL_BASE_DIR}"

# ── Helper function ───────────────────────────────────────────────────────────
download_model() {
    local repo_id="$1"
    local local_dir="$2"
    local friendly_name="$3"

    if [ -f "${local_dir}/config.json" ]; then
        echo ""
        echo "[skip] ${friendly_name} already exists at ${local_dir}"
        return 0
    fi

    echo ""
    echo "[download] ${friendly_name}"
    echo "  From : ${repo_id}"
    echo "  To   : ${local_dir}"
    mkdir -p "${local_dir}"

    hf download "${repo_id}" \
        --local-dir "${local_dir}"

    echo "  Done : ${friendly_name}"
}

# ── 3. Download models ────────────────────────────────────────────────────────
echo ""
echo "Downloading models. Qwen2.5-7B-Instruct is ~14 GB — be patient."

download_model \
    "Qwen/Qwen2.5-7B-Instruct" \
    "${MODEL_BASE_DIR}/Qwen2.5-7B-Instruct" \
    "Qwen2.5-7B-Instruct (LLM, ~14 GB)"

download_model \
    "BAAI/bge-m3" \
    "${MODEL_BASE_DIR}/bge-m3" \
    "BGE-M3 (embeddings, ~570 MB)"

download_model \
    "stepfun-ai/GOT-OCR2_0" \
    "${MODEL_BASE_DIR}/GOT-OCR2_0" \
    "GOT-OCR2.0 (handwritten OCR, ~1.4 GB)"

# ── 4. Summary ────────────────────────────────────────────────────────────────
echo ""
echo "======================================================"
echo " Download complete. Model directory sizes:"
du -sh "${MODEL_BASE_DIR}"/*/  2>/dev/null || true
echo "======================================================"
