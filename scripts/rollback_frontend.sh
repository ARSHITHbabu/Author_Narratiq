#!/bin/bash
# Frontend rollback (Stage 10, task 10.5).
#
# start-narratiq.sh keeps the previous production build as frontend/.next.prev
# every time it rebuilds. This script swaps the two builds and restarts ONLY the
# Next.js server, so a bad frontend release is reversed in seconds without a
# rebuild, a backend restart or a pod restart. Running it again swaps back.
#
# Since Stage 10 (10.7) the build no longer embeds the backend's pod URL for
# HTTP (the browser calls /api on its own origin), so a previous build keeps
# working on a new pod. The one build-time URL left is NEXT_PUBLIC_API_URL for
# the voice WebSocket: a build made on a DIFFERENT pod would point voice at the
# old pod — the script warns when that is the case.
#
# Usage:  bash scripts/rollback_frontend.sh [--dry-run]
#
# Stage 12 remediation (A6): only the server listening on $PORT is stopped —
# never every Next.js process on the pod (a second frontend, a test server or a
# rollback rehearsal on another port is left alone) — and FRONTEND_DIR defaults
# to the checkout this script lives in, not a hard-coded path.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="${FRONTEND_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)/frontend}"
PORT="${FRONTEND_PORT:-3000}"
LOG_DIR="${LOG_DIR:-/tmp/narratiq-logs}"
DRY="${1:-}"

cur="$FRONTEND_DIR/.next"
prev="$FRONTEND_DIR/.next.prev"
[ -d "$prev" ] || { echo "No previous build at $prev — nothing to roll back to."; exit 1; }
[ -d "$cur" ]  || { echo "No current build at $cur."; exit 1; }

echo "Current build : $(cat "$cur/BUILD_ID" 2>/dev/null || echo '?')"
echo "Previous build: $(cat "$prev/BUILD_ID" 2>/dev/null || echo '?')"
if [ -n "${RUNPOD_POD_ID:-}" ] && ! grep -rqs "${RUNPOD_POD_ID}-8000" "$prev/static" 2>/dev/null; then
  echo "WARNING: the previous build's voice WebSocket URL is not this pod's (${RUNPOD_POD_ID})."
  echo "         Everything except the voice agent will work; rebuild to fix voice."
fi
[ "$DRY" = "--dry-run" ] && { echo "(dry run — nothing changed)"; exit 0; }

# PIDs of the processes listening on $PORT (ss is part of iproute2 and present
# on the pod; fuser/lsof are not).
port_pids() {
  # `|| true`: grep finds nothing once the port is free, and under pipefail
  # that would abort the script at the assignment.
  { ss -ltnpH "sport = :${PORT}" 2>/dev/null | grep -o 'pid=[0-9]*' | cut -d= -f2 | sort -u; } || true
}

pids="$(port_pids)"
if [ -n "$pids" ]; then
  echo "Stopping the server on :${PORT} (PID $(echo $pids))"
  kill -TERM $pids 2>/dev/null || true
  for i in $(seq 1 10); do
    [ -z "$(port_pids)" ] && break
    sleep 1
  done
  pids="$(port_pids)"
  [ -n "$pids" ] && kill -KILL $pids 2>/dev/null || true
  sleep 1
else
  echo "Nothing is listening on :${PORT}."
fi
if [ -n "$(port_pids)" ]; then
  echo "Port ${PORT} is still in use — not swapping builds."; exit 1
fi

mv "$cur" "$FRONTEND_DIR/.next.swap"
mv "$prev" "$cur"
mv "$FRONTEND_DIR/.next.swap" "$prev"

cd "$FRONTEND_DIR"
mkdir -p "$LOG_DIR"
nohup npm start -- --port "$PORT" >> "$LOG_DIR/frontend.log" 2>&1 &
for i in $(seq 1 30); do
  if curl -so /dev/null -w '%{http_code}' "http://localhost:${PORT}/login" | grep -q 200; then
    echo "Rolled back. Serving build $(cat "$cur/BUILD_ID") on :${PORT} (the replaced build is now .next.prev)."
    exit 0
  fi
  sleep 1
done
echo "The frontend did not answer within 30 s — check $LOG_DIR/frontend.log. Run this script again to swap back."
exit 1
