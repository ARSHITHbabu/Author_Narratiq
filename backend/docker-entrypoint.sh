#!/bin/bash
# Container entrypoint for the NarratIQ backend (Stage 10, task 10.3).
#
# Mirrors start-narratiq.sh's schema order: Base.metadata.create_all() and the
# lightweight column migrations, then `alembic upgrade head`, then ONE uvicorn
# worker. Migrations run only when RUN_MIGRATIONS=1 (the compose default for
# local development). A production deployment takes a backup first
# (scripts/startup_backup.sh) — this entrypoint does not, so it must not be
# pointed at a database holding real manuscripts with RUN_MIGRATIONS=1.
set -euo pipefail

if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
  echo "[entrypoint] applying schema (create_all + alembic upgrade head)..."
  python3 -c "from database import engine, Base, run_db_migrations; import models; Base.metadata.create_all(bind=engine); run_db_migrations(engine)"
  alembic upgrade head
fi

# --no-proxy-headers: middleware/rate_limit.client_ip is the one place forwarding
# headers are interpreted (uvicorn's own handling keyed rate limits on a changing
# Cloudflare edge address — Stage 10 live finding).
exec python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1 --no-access-log --no-proxy-headers
