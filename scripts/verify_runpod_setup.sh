#!/bin/bash
# Verify that the RunPod environment is correctly set up for NarratIQ AI.
#
# Safe to run at any point: before the stack has ever been started (checks
# dependencies, models, disk space) or after `bash start-narratiq.sh` has brought
# everything up (additionally verifies each service is actually healthy, not just
# that its port is occupied). A service that isn't running yet is reported as
# NOT STARTED (informational), not a failure — this script does not require the
# stack to be up to be useful.
#
# Read-only with respect to application and manuscript data: every live check
# either calls a health/models endpoint or runs a throwaway smoke request (a
# 4-token completion, a literal-vector distance query) — nothing here reads,
# lists, or touches real story/chapter/user rows, and nothing here stops or
# restarts any service.
#
# Usage:
#   bash scripts/verify_runpod_setup.sh                    # pre-start or any time
#   bash scripts/verify_runpod_setup.sh --expect-running   # after start-narratiq.sh
#
# Modes:
#   default           A service that is not listening is reported NOT STARTED as a
#                     warning, so the script is useful before the stack is up.
#   --expect-running  (or EXPECT_RUNNING=1) For checking a stack that should be up.
#                     A service that is not listening, and an exposed-but-dead proxy
#                     port (HTTP 502), count as FAILURES, so a crashed service can
#                     never produce "All checks passed".
#
# Optional environment:
#   RUNPOD_API_KEY    Injected by RunPod into every pod. When set together with
#                     RUNPOD_POD_ID, the pod's exposed-port list is read from the
#                     RunPod API to confirm 3000/8000 are exposed. The key is sent
#                     on stdin as a header — never in a URL, argv, or output.
#   RUNPOD_API_URL, RUNPOD_PROXY_URL_TEMPLATE
#                     TEST-ONLY seams used by scripts/tests/test_verify_runpod_setup.py
#                     to point the RunPod checks at local stubs. Only https:// or
#                     http://127.0.0.1 values are accepted. Do not set in production.

set -uo pipefail

EXPECT_RUNNING="${EXPECT_RUNNING:-0}"
for arg in "$@"; do
    case "${arg}" in
        --expect-running) EXPECT_RUNNING=1 ;;
        -h|--help) sed -n '2,40p' "$0"; exit 0 ;;
        *) echo "Unknown argument: ${arg} (see --help)" >&2; exit 2 ;;
    esac
done
[ "${EXPECT_RUNNING}" = "1" ] || EXPECT_RUNNING=0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

MODEL_BASE_DIR="${MODEL_BASE_DIR:-/workspace/models}"
LLM_MODEL_PATH="${LLM_MODEL_PATH:-${MODEL_BASE_DIR}/Qwen2.5-7B-Instruct}"
BGE_MODEL_PATH="${BGE_MODEL_PATH:-${MODEL_BASE_DIR}/bge-m3}"
GOT_OCR_MODEL_PATH="${GOT_OCR_MODEL_PATH:-${MODEL_BASE_DIR}/GOT-OCR2_0}"
WHISPER_MODEL_PATH="${WHISPER_MODEL_PATH:-${MODEL_BASE_DIR}/faster-whisper-large-v3-turbo}"
VLLM_PORT="${VLLM_PORT:-9001}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

PASS=0
FAIL=0

ok()   { echo "  [OK]  $1"; PASS=$((PASS+1)); }
fail() { echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }
warn() { echo "  [WARN] $1"; }
hdr()  { echo ""; echo "── $1"; }
# A service that isn't up: informational before start, a failure in --expect-running mode.
not_started() {
    if [ "${EXPECT_RUNNING}" -eq 1 ]; then
        fail "$1 — NOT RUNNING, but --expect-running was given (check: bash start-narratiq.sh, /tmp/narratiq-logs/)"
    else
        warn "$1 — NOT STARTED (run: bash start-narratiq.sh)"
    fi
}
# Accept only https:// or loopback http:// for the test seams, so a stray value can
# never send the RunPod key in plaintext to an arbitrary host.
url_allowed() {
    case "$1" in
        https://*|http://127.0.0.1:*|http://127.0.0.1/*) return 0 ;;
        *) return 1 ;;
    esac
}

echo "======================================================"
echo " NarratIQ AI — RunPod Setup Verification"
if [ "${EXPECT_RUNNING}" -eq 1 ]; then
    echo " Mode: --expect-running (a service that is down is a FAILURE)"
else
    echo " Mode: default (a service that is down is NOT STARTED, a warning)"
fi
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

# ── Node.js ───────────────────────────────────────────────────────────────────
hdr "Node.js"
if command -v node &>/dev/null; then
    NODE_VER=$(node --version)
    ok "Node found: ${NODE_VER}"
else
    fail "node not found — required for the frontend (start-narratiq.sh installs Node 20)"
fi

# ── PostgreSQL / pgvector ───────────────────────────────────────────────────────
hdr "PostgreSQL / pgvector"
if command -v psql &>/dev/null; then
    ok "psql client found"
    if pg_isready -h localhost -p 5432 &>/dev/null; then
        ok "PostgreSQL is accepting connections on localhost:5432"
        DB_URL_ENV="${DATABASE_URL:-}"
        if PGPASSWORD=narratiq psql -h localhost -U narratiq -d narratiq -tAc "SELECT 1;" &>/dev/null; then
            ok "Can connect to the 'narratiq' database as the 'narratiq' role"
            VEC_VER=$(PGPASSWORD=narratiq psql -h localhost -U narratiq -d narratiq -tAc \
                "SELECT extversion FROM pg_extension WHERE extname='vector';" 2>/dev/null | tr -d '[:space:]')
            if [ -n "${VEC_VER}" ]; then
                ok "pgvector extension enabled (version ${VEC_VER})"
            else
                fail "pgvector extension is NOT enabled in the 'narratiq' database"
            fi
        else
            warn "Could not connect to the 'narratiq' database as 'narratiq' — may not be created yet (run start-narratiq.sh)"
        fi
    else
        warn "PostgreSQL is not accepting connections yet — may not be started (run start-narratiq.sh, or: pg_ctlcluster 16 main start)"
    fi
else
    fail "psql not found — PostgreSQL is required (SQLite is not supported); start-narratiq.sh installs it"
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

check_model_dir "LLM (Qwen2.5-7B-Instruct)"          "${LLM_MODEL_PATH}"
check_model_dir "BGE-M3 (embeddings)"                  "${BGE_MODEL_PATH}"
check_model_dir "GOT-OCR2.0 (OCR, required)"           "${GOT_OCR_MODEL_PATH}"
check_model_dir "faster-whisper-large-v3-turbo (audio, required)" "${WHISPER_MODEL_PATH}"

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

# ── Service health ───────────────────────────────────────────────────────────
# Each service is reported NOT STARTED (informational, not a failure) if its port
# isn't listening yet — this script is safe to run before the stack has ever been
# brought up. If a port IS listening, its actual health is checked, not just its
# occupancy, so a stuck/broken service is caught rather than mistaken for healthy.
hdr "Service Health"

# ss, then netstat, then a direct loopback connect via bash's /dev/tcp — each tried
# in turn, so a missing or restricted tool falls through to the next. Before the
# /dev/tcp fallback existed, a host with neither ss nor netstat reported every
# running service as NOT STARTED and could exit 0 without checking a single service.
port_listening() {
    { command -v ss &>/dev/null && ss -tln 2>/dev/null | grep -q ":$1 "; } ||
    { command -v netstat &>/dev/null && netstat -tln 2>/dev/null | grep -q ":$1 "; } ||
    timeout 2 bash -c "exec 3<>/dev/tcp/127.0.0.1/$1" 2>/dev/null
}

VLLM_UP=0
if port_listening "${VLLM_PORT}"; then
    # -f: an HTTP error status (e.g. 500) is not "healthy".
    if curl -sf -m 5 "http://localhost:${VLLM_PORT}/health" &>/dev/null; then
        ok "vLLM is listening on ${VLLM_PORT} and reports healthy"
        VLLM_UP=1
    else
        fail "vLLM is listening on ${VLLM_PORT} but /health did not respond with success — check tail -50 /tmp/narratiq-logs/vllm.log"
    fi
else
    not_started "vLLM (port ${VLLM_PORT})"
fi

BACKEND_UP=0
BACKEND_HEALTH_JSON=""
if port_listening "${BACKEND_PORT}"; then
    BACKEND_HEALTH_JSON=$(curl -s -m 5 "http://localhost:${BACKEND_PORT}/api/health" 2>/dev/null)
    if echo "${BACKEND_HEALTH_JSON}" | grep -q '"status":\s*"ok"'; then
        ok "Backend is listening on ${BACKEND_PORT} and /api/health reports ok"
        BACKEND_UP=1
        if echo "${BACKEND_HEALTH_JSON}" | grep -q '"vllm":\s*"ready"'; then
            ok "Backend reports vLLM as ready (not degraded)"
        else
            fail "Backend is up but reports vLLM NOT ready — every AI endpoint will return 503. Check for a stale VLLM_BASE_URL (§1.2 of runpod-environment-variables.md)"
        fi
        if echo "${BACKEND_HEALTH_JSON}" | grep -q '"bge_m3":\s*"ready"'; then
            ok "Backend reports BGE-M3 as ready"
        else
            fail "Backend is up but BGE-M3 is not ready — embedding-dependent features will fail"
        fi
    else
        fail "Backend is listening on ${BACKEND_PORT} but /api/health did not report ok — check tail -50 /tmp/narratiq-logs/backend.log"
    fi
else
    not_started "Backend (port ${BACKEND_PORT})"
fi

FRONTEND_UP=0
if port_listening "${FRONTEND_PORT}"; then
    if curl -s -o /dev/null -m 5 -w "%{http_code}" "http://localhost:${FRONTEND_PORT}/" 2>/dev/null | grep -q "^200$"; then
        ok "Frontend is listening on ${FRONTEND_PORT} and returns HTTP 200"
        FRONTEND_UP=1
    else
        fail "Frontend is listening on ${FRONTEND_PORT} but did not return HTTP 200 — check tail -50 /tmp/narratiq-logs/frontend.log"
    fi
else
    not_started "Frontend (port ${FRONTEND_PORT})"
fi

# ── External proxy reachability (RunPod only; skipped in local/non-RunPod dev) ─
hdr "External Proxy Reachability"
if [ -n "${RUNPOD_POD_ID:-}" ]; then
    # Hits each service's own known-good path, not just "/" — a bare "/" on the
    # backend is a legitimate FastAPI 404 (JSON body {"detail":"Not Found"}) that
    # must not be confused with RunPod's own unexposed-port 404 (empty body).
    # {port} is replaced per check. (Not written as ${VAR:-default}: the literal
    # "}" of {port} would end that expansion early.)
    PROXY_TEMPLATE="https://${RUNPOD_POD_ID}-{port}.proxy.runpod.net"
    [ -n "${RUNPOD_PROXY_URL_TEMPLATE:-}" ] && PROXY_TEMPLATE="${RUNPOD_PROXY_URL_TEMPLATE}"
    check_proxy() {
        local port="$1" label="$2" path="$3"
        if ! url_allowed "${PROXY_TEMPLATE}"; then
            fail "RUNPOD_PROXY_URL_TEMPLATE must be https:// or http://127.0.0.1 — refusing to use it"
            return
        fi
        local url="${PROXY_TEMPLATE//\{port\}/${port}}${path}"
        local resp code body
        resp=$(curl -s -m 8 -w "\n%{http_code}" "${url}" 2>/dev/null)
        code=$(echo "${resp}" | tail -1)
        body=$(echo "${resp}" | sed '$d')
        case "${code}" in
            200) ok "${label} proxy (${port}) reachable — HTTP 200" ;;
            502)
                if [ "${EXPECT_RUNNING}" -eq 1 ]; then
                    fail "${label} proxy (${port}) is exposed but nothing answers behind it (HTTP 502) — the service is down"
                else
                    warn "${label} proxy (${port}) exposed but nothing listening yet (HTTP 502) — expected if the service hasn't started"
                fi
                ;;
            404)
                if [ -z "${body}" ]; then
                    fail "${label} proxy (${port}) returned an EMPTY-BODY 404 — port likely NOT EXPOSED at pod creation (see docs/operations/runpod-deployment.md, pod-creation prerequisite). This is never an application fault"
                else
                    fail "${label} proxy (${port}) returned HTTP 404 with a response body (${body}) — this is an APPLICATION 404 (wrong path), not the unexposed-port signature. Port exposure looks fine; check the path/route instead"
                fi
                ;;
            # curl reports 000 (not an empty string) when it gets no HTTP response at all.
            ""|000) fail "${label} proxy (${port}) — no response (timeout or connection failure)" ;;
            *) warn "${label} proxy (${port}) returned unexpected HTTP ${code}" ;;
        esac
    }
    check_proxy "${FRONTEND_PORT}" "Frontend" "/"
    check_proxy "${BACKEND_PORT}"  "Backend"  "/api/health"
else
    warn "RUNPOD_POD_ID not set — skipping external proxy checks (not a RunPod pod, or run from outside it)"
fi

# ── RunPod exposed-port list (RunPod only; needs RUNPOD_API_KEY) ──────────────
# Root cause of the 2026-07 port-3000 404 incident: 3000/8000 were never exposed
# at pod creation. The proxy check above can only infer that from an empty-body
# 404; this reads the pod's port table directly. The query shape
# (runtime { ports { privatePort type } }) is the one used live in
# docs/incidents/runpod-port-3000-404-incident-report.md. An API error, a missing
# permission or an unexpected response is a WARN ("could not determine"), never a
# FAIL — only a successful answer that lacks a port is a failure.
hdr "RunPod Port Exposure"
if [ -z "${RUNPOD_POD_ID:-}" ] || [ -z "${RUNPOD_API_KEY:-}" ]; then
    warn "RUNPOD_POD_ID or RUNPOD_API_KEY not set — skipping the RunPod port-list check"
else
    RUNPOD_API="${RUNPOD_API_URL:-https://api.runpod.io/graphql}"
    if ! url_allowed "${RUNPOD_API}"; then
        warn "RUNPOD_API_URL must be https:// or http://127.0.0.1 — refusing to send the API key there; port-list check skipped"
    else
        PORT_QUERY=$(python3 -c 'import json,sys; print(json.dumps({"query": "query($id: String!) { pod(input: {podId: $id}) { id runtime { ports { privatePort publicPort type } } } }", "variables": {"id": sys.argv[1]}}))' "${RUNPOD_POD_ID}")
        # The key goes in on stdin (-H @-): not in the URL, not in argv, not in output.
        PORT_RESP=$(printf 'Authorization: Bearer %s\n' "${RUNPOD_API_KEY}" | curl -s -m 10 -X POST \
            -H @- -H "Content-Type: application/json" --data "${PORT_QUERY}" \
            -w "\n%{http_code}" "${RUNPOD_API}" 2>/dev/null)
        PORT_CODE=$(echo "${PORT_RESP}" | tail -1)
        PORT_BODY=$(echo "${PORT_RESP}" | sed '$d')
        if [ "${PORT_CODE}" != "200" ]; then
            warn "RunPod API answered HTTP ${PORT_CODE:-none} — could not determine the exposed-port list (the proxy check above still applies)"
        else
            PORT_VERDICT=$(printf '%s' "${PORT_BODY}" | python3 -c '
import json, sys
wanted = [int(p) for p in sys.argv[1:]]
try:
    doc = json.load(sys.stdin)
except Exception:
    print("UNKNOWN response was not JSON"); sys.exit()
if not isinstance(doc, dict) or doc.get("errors"):
    print("UNKNOWN the API returned an error (possibly a key without pod-read permission)"); sys.exit()
pod = (doc.get("data") or {}).get("pod")
runtime = pod.get("runtime") if isinstance(pod, dict) else None
ports = runtime.get("ports") if isinstance(runtime, dict) else None
if not isinstance(ports, list):
    print("UNKNOWN no runtime port table (pod not running, or unexpected response shape)"); sys.exit()
exposed = {(p.get("privatePort"), str(p.get("type", "")).lower()) for p in ports if isinstance(p, dict)}
for w in wanted:
    print(("PRESENT " if (w, "http") in exposed else "MISSING ") + str(w))
' "${FRONTEND_PORT}" "${BACKEND_PORT}")
            while read -r verdict detail; do
                case "${verdict}" in
                    PRESENT) ok "Port ${detail} is exposed as an HTTP port on pod ${RUNPOD_POD_ID}" ;;
                    MISSING) fail "Port ${detail} is NOT exposed as an HTTP port on pod ${RUNPOD_POD_ID} — ports are fixed at pod creation; add it via Edit Pod (see docs/operations/runpod-deployment.md, pod-creation prerequisite)" ;;
                    UNKNOWN) warn "Could not determine the exposed-port list — ${detail} (the proxy check above still applies)" ;;
                    *) warn "Could not determine the exposed-port list — unexpected parser output" ;;
                esac
            done <<< "${PORT_VERDICT}"
        fi
    fi
fi

# ── Frontend API URL drift ────────────────────────────────────────────────────
# Next.js gives an OS-level NEXT_PUBLIC_API_URL precedence over frontend/.env.local
# (demonstrated 2026-09-25, runpod-environment-variables.md §11 item 2), so a stale
# value left in the RunPod UI would be baked into any manual `npm run build`.
# start-narratiq.sh passes the computed value explicitly, so its own build is safe.
hdr "Frontend API URL"
ENV_LOCAL_FILE="${REPO_DIR}/frontend/.env.local"
ENV_LOCAL_URL=""
if [ -f "${ENV_LOCAL_FILE}" ]; then
    ENV_LOCAL_URL=$(grep -E '^NEXT_PUBLIC_API_URL=' "${ENV_LOCAL_FILE}" | tail -1 | cut -d= -f2-)
fi
if [ -n "${NEXT_PUBLIC_API_URL:-}" ]; then
    if [ "${NEXT_PUBLIC_API_URL}" != "${ENV_LOCAL_URL}" ]; then
        warn "NEXT_PUBLIC_API_URL is set in the OS environment (${NEXT_PUBLIC_API_URL}) and differs from frontend/.env.local (${ENV_LOCAL_URL:-<not set>}). It wins over .env.local in any manual 'npm run build'. Remove it from the RunPod UI unless intended"
    else
        ok "OS NEXT_PUBLIC_API_URL matches frontend/.env.local"
    fi
else
    ok "No OS-level NEXT_PUBLIC_API_URL override (frontend/.env.local governs builds)"
fi

# ── Smoke tests (real but throwaway requests; read-only w.r.t. application data) ─
hdr "Smoke Tests"
if [ "${VLLM_UP}" -eq 1 ]; then
    SMOKE_OUT=$(curl -s -m 15 "http://localhost:${VLLM_PORT}/v1/completions" \
        -H "Content-Type: application/json" \
        -d '{"model":"Qwen/Qwen2.5-7B-Instruct","prompt":"Say OK","max_tokens":4}' 2>/dev/null)
    if echo "${SMOKE_OUT}" | grep -q '"text"'; then
        ok "vLLM generation smoke test passed (real completion returned)"
    else
        fail "vLLM generation smoke test failed — no completion text in response"
    fi
else
    warn "Skipping vLLM generation smoke test — vLLM is not up"
fi

if [ "${BACKEND_UP}" -eq 1 ] && command -v psql &>/dev/null; then
    PGVEC_OUT=$(PGPASSWORD=narratiq psql -h localhost -U narratiq -d narratiq -tAc \
        "SELECT '[1,2,3]'::vector <=> '[1,2,3]'::vector;" 2>/dev/null | tr -d '[:space:]')
    if [ "${PGVEC_OUT}" = "0" ]; then
        ok "pgvector query smoke test passed (self-distance = 0, using a literal test vector — no application data read)"
    else
        fail "pgvector query smoke test failed — expected 0, got '${PGVEC_OUT}'"
    fi
else
    warn "Skipping pgvector query smoke test — backend/database not confirmed up"
fi

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
    if [ "${BACKEND_UP:-0}" -eq 1 ] && [ "${FRONTEND_UP:-0}" -eq 1 ] && [ "${VLLM_UP:-0}" -eq 1 ]; then
        echo " All checks passed and the stack is already up and healthy."
    else
        echo " All checks passed! Start the stack with:"
        echo "   bash start-narratiq.sh"
    fi
    exit 0
fi
