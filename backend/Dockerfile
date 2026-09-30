# NarratIQ backend image (Stage 10, task 10.3).
#
# Proportional scope: RunPod + start-narratiq.sh remains the production path.
# This image makes the backend reproducible outside that one bash script — for
# local development (docker-compose.yml at the repository root) and as the
# starting point for any future container deployment.
#
# What it is:  the FastAPI app, CPU PyTorch (BGE-M3 embeddings run on CPU in
#              production too), one uvicorn worker (decision D-3; the startup
#              guard refuses more).
# What it is not: vLLM. The LLM server is external — point VLLM_BASE_URL at it.
# Model weights are NOT baked in (tens of GB): mount them at /models.
#
# Versions: every base image and package is pinned to an exact version. The
# base-image DIGEST is recorded at the first verified build (see
# docs/operations/containers.md) — it could not be resolved from the pod, which
# has no container runtime.
FROM python:3.11.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MODEL_BASE_DIR=/models \
    LOG_FORMAT=json

# postgresql-client: pg_dump/pg_restore for the backup scripts; curl: healthcheck.
RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend

# CPU build of the torch version the pod runs (2.7.0), from PyTorch's own index,
# BEFORE requirements.txt so its `torch>=2.7.0` floor is already satisfied.
RUN pip install torch==2.7.0 --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN useradd --create-home --uid 10001 narratiq \
 && mkdir -p uploads/audio uploads/ocr \
 && chown -R narratiq:narratiq /app
USER narratiq

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=3 \
  CMD curl -s http://127.0.0.1:8000/api/health | grep -q '"backend":"ready"' || exit 1

# docker-entrypoint.sh: schema (create_all + alembic upgrade head) when
# RUN_MIGRATIONS=1, then exactly one uvicorn worker.
ENTRYPOINT ["bash", "docker-entrypoint.sh"]
