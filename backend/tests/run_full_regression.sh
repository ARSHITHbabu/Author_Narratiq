#!/usr/bin/env bash
# Stage 9 task 9.1 — one runner for the full regression pass.
#
# Runs, in order, every automated suite this repository has and writes one
# summary line per suite to $OUT (default /tmp/narratiq-regression/summary.txt),
# with the full log of each suite next to it. It never touches the live
# `narratiq` database: every backend step uses $TEST_DATABASE_URL, which the
# conftest safety guard also enforces.
#
# Prerequisites (see docs/testing/stage-09-regression-results.md):
#   * the stack is up (vLLM :9001, backend :8000, frontend :3000);
#   * narratiq_test exists, has the vector extension, is at alembic head and
#     holds the seeded fixture story (scripts/seed_fixture.py);
#   * E2E_EMAIL / E2E_PASSWORD / E2E_STORY_ID for the live browser suite, and
#     E2E_BASE_URL / E2E_API_URL when the stack under test is not :3000 / :8000
#     (the specs log in through E2E_API_URL; it defaults to the live :8000).
#
# Usage:  bash backend/tests/run_full_regression.sh [suite ...]
#   suites: backend known-defects retrieval migration fe-unit fe-studio fe-a11y
#           fe-variants fe-browser ai-harness     (default: all)
set -uo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
BACKEND="$REPO/backend"
FRONTEND="$REPO/frontend"
TEST_DATABASE_URL="${TEST_DATABASE_URL:-postgresql+psycopg2://narratiq:narratiq@localhost:5432/narratiq_test}"
OUTDIR="${OUTDIR:-/tmp/narratiq-regression}"
OUT="$OUTDIR/summary.txt"
mkdir -p "$OUTDIR"
SUITES=("$@")
[ ${#SUITES[@]} -eq 0 ] && SUITES=(backend known-defects retrieval migration fe-unit fe-studio fe-a11y fe-variants fe-browser ai-harness)

record() {  # name, exit code, log
  local tail_line
  tail_line="$(grep -E '(passed|failed|error)' "$3" | tail -1)"
  printf '%s | %-14s | exit=%s | %s\n' "$(date -u +%FT%TZ)" "$1" "$2" "${tail_line:-see log}" | tee -a "$OUT"
}

run() {  # name, dir, command...
  local name="$1" dir="$2"; shift 2
  local log="$OUTDIR/$name.log"
  echo "── $name ──"
  (cd "$dir" && "$@") >"$log" 2>&1
  record "$name" "$?" "$log"
}

for s in "${SUITES[@]}"; do
  case "$s" in
    backend)
      run backend "$REPO" env DATABASE_URL="$TEST_DATABASE_URL" \
        python3 -m pytest backend/tests -m "not known_stage5_defect" -q -p no:cacheprovider ;;
    known-defects)
      run known-defects "$REPO" env DATABASE_URL="$TEST_DATABASE_URL" \
        python3 -m pytest backend/tests -m known_stage5_defect -q -p no:cacheprovider ;;
    retrieval)
      run retrieval "$BACKEND" env DATABASE_URL="$TEST_DATABASE_URL" bash tests/run_stage4_retrieval_suite.sh ;;
    migration)
      run migration "$BACKEND" env DATABASE_URL="$TEST_DATABASE_URL" bash tests/run_migration_roundtrip.sh ;;
    fe-unit)     run fe-unit     "$FRONTEND" npm test ;;
    fe-studio)   run fe-studio   "$FRONTEND" npm run test:studio ;;
    fe-a11y)     run fe-a11y     "$FRONTEND" npm run test:a11y ;;
    fe-variants) run fe-variants "$FRONTEND" npm run test:studio:variants ;;
    fe-browser)  run fe-browser  "$FRONTEND" npm run test:browser ;;
    ai-harness)
      run ai-invariants "$REPO" env DATABASE_URL="$TEST_DATABASE_URL" \
        python3 -m pytest backend/tests/test_ai_quality_invariants.py -q -p no:cacheprovider ;;
    *) echo "unknown suite: $s" >&2 ;;
  esac
done
echo "Summary: $OUT"
