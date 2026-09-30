# Containers

**Stage 10, task 10.3 (production gap PG-04).** Proportional by decision: **RunPod + `start-narratiq.sh` remains the production deployment path.** The container files make the stack reproducible on any Docker host (local development, a future host) so deployment no longer depends solely on one bash script and one RunPod base image.

| File | What it builds |
|---|---|
| `backend/Dockerfile` | FastAPI backend: Python 3.11.10, CPU PyTorch 2.7.0, `backend/requirements.txt`, one uvicorn worker, non-root user, health check. **No vLLM** and **no model weights** (mount them at `/models`). |
| `backend/docker-entrypoint.sh` | `create_all` + `alembic upgrade head` when `RUN_MIGRATIONS=1`, then uvicorn. It takes **no backup** — never point it at real manuscripts with migrations on. |
| `frontend/Dockerfile` | Next.js build with the same build-time settings as the pod (`BACKEND_INTERNAL_URL`, `NEXT_PUBLIC_API_URL`), `npm ci` from `package-lock.json`, Node 20.20.2. |
| `docker-compose.yml` | PostgreSQL 16 + pgvector 0.8.0, backend, frontend — **development only** (placeholder secrets). vLLM is external (`VLLM_BASE_URL`, default the Docker host's :9001); without it the backend runs in its documented degraded mode. |
| `scripts/verify_containers.sh` | Clean `--no-cache` build, then an end-to-end check through the frontend origin (health, `/login`, register → HttpOnly cookie → `/me` → create/list a manuscript with CSRF → sign out → session refused), then removes the stack and its volumes. |

## Version pinning

* Python packages: `backend/requirements.txt` — every package pinned to the version verified on the pod. Stage 9 finding D2 (the file did not match the runtime; four required packages were missing) is closed: on 2026-09-29 `pip install --dry-run -r backend/requirements.txt` on the running pod installed nothing. `start-narratiq.sh` now installs from this file too — one source of truth.
* Node packages: `package-lock.json` via `npm ci` (image and `start-narratiq.sh`); `frontend/.nvmrc` and `engines` pin Node 20.
* Base images: exact version tags (`python:3.11.10-slim-bookworm`, `node:20.20.2-bookworm-slim`, `pgvector/pgvector:0.8.0-pg16`). **Digests are not yet pinned**: the pod has no container runtime, so they could not be resolved. Record them from the first verified build (`docker compose images` / `docker inspect --format '{{index .RepoDigests 0}}'`) and change each `FROM` to `image:tag@sha256:…`.

## Relationship to `start-narratiq.sh`

| Concern | Pod (`start-narratiq.sh`) | Containers |
|---|---|---|
| vLLM + GPU | installs and runs vLLM 0.9.2 | external |
| Python deps | `requirements.txt` + CUDA torch | `requirements.txt` + CPU torch |
| Database | PostgreSQL 16 on the container layer, backups to `/workspace/backups` | `pgvector` image, named volume, no backups (dev) |
| Schema | backup → `create_all` → `alembic upgrade head` | `create_all` → `alembic upgrade head` (no backup) |
| Frontend | same build settings | same build settings |
| Watchdog, backup loop | started | not included |

## Verification status

**"A clean container build produces a working stack" has NOT been verified in Stage 10**: it needs a Docker host, and a RunPod pod cannot run Docker. On a machine with Docker:

```bash
NARRATIQ_MODELS_DIR=/path/containing/bge-m3 bash scripts/verify_containers.sh
```

The files were reviewed against the pod's working configuration; that is not a substitute for the build. The checklist box stays open until this script passes on a real Docker host.
