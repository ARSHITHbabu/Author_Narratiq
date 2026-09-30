#!/bin/bash
# Clean container build + end-to-end check (Stage 10, task 10.3 verification:
# "A clean container build produces a working stack").
#
# Run on a machine with Docker (a RunPod pod has no container runtime, so this
# cannot run there). It builds every image from scratch (--no-cache), starts the
# stack, and checks through the FRONTEND origin, as a browser would:
#   1. the backend answers /api/health with "backend":"ready"
#      (vLLM may be "unavailable" if none is reachable — that is reported, not failed);
#   2. the frontend serves /login;
#   3. register → session cookie (HttpOnly) → /api/auth/me → create a manuscript
#      (with the CSRF header) → list it → sign out → /api/auth/me refused.
# Then it removes the stack AND its volumes (a throw-away dev database).
#
# Usage:  NARRATIQ_MODELS_DIR=/path/to/models bash scripts/verify_containers.sh
set -euo pipefail
cd "$(dirname "$0")/.."

FRONT="http://localhost:3000"
JAR="$(mktemp)"
trap 'rm -f "$JAR"; docker compose down -v >/dev/null 2>&1 || true' EXIT
ok()   { echo "  [PASS] $*"; }
fail() { echo "  [FAIL] $*"; exit 1; }

echo "── Building images from scratch"
docker compose build --no-cache
echo "── Starting the stack"
docker compose up -d

echo "── Waiting for the backend (model load can take a few minutes)"
for i in $(seq 1 90); do
  if curl -s "$FRONT/api/health" | grep -q '"backend":"ready"'; then break; fi
  [ "$i" -eq 90 ] && { docker compose logs --tail 80 backend; fail "backend never became ready"; }
  sleep 5
done
HEALTH="$(curl -s "$FRONT/api/health")"
ok "backend ready through the frontend origin: $HEALTH"
echo "$HEALTH" | grep -q '"vllm":"ready"' || echo "  [NOTE] vLLM not reachable — AI features will answer 503 (expected without a GPU)"

curl -sf "$FRONT/login" >/dev/null && ok "frontend serves /login" || fail "frontend /login"

EMAIL="container-check-$(date +%s)@example.test"
curl -sf -c "$JAR" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"username\":\"cc$(date +%s)\",\"password\":\"container-check-pw\"}" \
  "$FRONT/api/auth/register" | grep -q '"user"' && ok "register" || fail "register"
grep -q narratiq_session "$JAR" && ok "session cookie set" || fail "no session cookie"
grep narratiq_session "$JAR" | grep -q '#HttpOnly_' && ok "session cookie is HttpOnly" || fail "session cookie not HttpOnly"
curl -sf -b "$JAR" "$FRONT/api/auth/me" | grep -q "$EMAIL" && ok "/api/auth/me" || fail "/api/auth/me"
CSRF="$(awk '$6=="narratiq_csrf"{print $7}' "$JAR")"
curl -sf -b "$JAR" -H "X-CSRF-Token: $CSRF" -H 'Content-Type: application/json' \
  -d '{"title":"Container check"}' "$FRONT/api/projects/" >/dev/null && ok "create manuscript" || fail "create manuscript"
curl -sf -b "$JAR" "$FRONT/api/projects/" | grep -q 'Container check' && ok "manuscript persisted" || fail "list manuscripts"
curl -sf -b "$JAR" -c "$JAR" -X POST "$FRONT/api/auth/logout" >/dev/null && ok "sign out"
[ "$(curl -s -o /dev/null -w '%{http_code}' -b "$JAR" "$FRONT/api/auth/me")" = "401" ] \
  && ok "session ended after sign-out" || fail "session still valid after sign-out"

echo ""
echo "Container stack verified. Record the output and the image digests:"
docker compose images
