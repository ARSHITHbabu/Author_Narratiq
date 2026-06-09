#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  NarratIQ AI v3.0 — Phase 1 Smoke Test
#
#  Run after start-narratiq.sh to verify every Phase 1 subsystem.
#  Usage: bash /workspace/narratiq-ai/scripts/smoke_test_phase1.sh
#
#  Prerequisites: all services must already be running.
#  Pass: each check prints OK.  Fail: prints FAIL and exits 1.
# ═══════════════════════════════════════════════════════════════
set -uo pipefail

BACKEND="http://localhost:8000"
VLLM="http://localhost:9001"
FRONTEND="http://localhost:3000"
DB_NAME="narratiq"
DB_USER="narratiq"
DB_PASS="narratiq"

PASS=0
FAIL=0

ok()   { echo "  [OK]   $1"; PASS=$((PASS+1)); }
fail() { echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }

section() {
  echo ""
  echo "──────────────────────────────────────────────────────────"
  echo "  $1"
  echo "──────────────────────────────────────────────────────────"
}

# ══════════════════════════════════════════════════════════════
section "1. PostgreSQL — user / database / pgvector"
# ══════════════════════════════════════════════════════════════

if PGPASSWORD="$DB_PASS" psql -h localhost -U "$DB_USER" -d "$DB_NAME" \
    -c "SELECT 1;" > /dev/null 2>&1; then
  ok "DB connection (narratiq@localhost:5432/narratiq)"
else
  fail "DB connection failed — check pg_hba.conf and ALTER USER narratiq WITH PASSWORD 'narratiq'"
fi

PG_VEC=$(PGPASSWORD="$DB_PASS" psql -h localhost -U "$DB_USER" -d "$DB_NAME" \
  -t -c "SELECT extname FROM pg_extension WHERE extname='vector';" 2>/dev/null | tr -d ' \n')
if [ "$PG_VEC" = "vector" ]; then
  ok "pgvector extension enabled"
else
  fail "pgvector extension NOT found — run: sudo -u postgres psql -d narratiq -c \"CREATE EXTENSION IF NOT EXISTS vector;\""
fi

# Users table exists
USERS_TABLE=$(PGPASSWORD="$DB_PASS" psql -h localhost -U "$DB_USER" -d "$DB_NAME" \
  -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='users';" 2>/dev/null | tr -d ' \n')
if [ "$USERS_TABLE" = "1" ]; then
  ok "users table exists"
else
  fail "users table missing — ORM create_all may have failed"
fi

# Chapters table
CHAPTERS_TABLE=$(PGPASSWORD="$DB_PASS" psql -h localhost -U "$DB_USER" -d "$DB_NAME" \
  -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='chapters';" 2>/dev/null | tr -d ' \n')
if [ "$CHAPTERS_TABLE" = "1" ]; then
  ok "chapters table exists"
else
  fail "chapters table missing"
fi

# ══════════════════════════════════════════════════════════════
section "2. Backend — health endpoint"
# ══════════════════════════════════════════════════════════════

HEALTH=$(curl -sf "$BACKEND/api/health" 2>/dev/null)
if echo "$HEALTH" | grep -q '"status":"ok"'; then
  ok "Backend health endpoint returns {status: ok}"
  BGE=$(echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('bge_m3',''))" 2>/dev/null)
  if [ "$BGE" = "ready" ]; then
    ok "BGE-M3 embeddings model loaded"
  else
    fail "BGE-M3 not ready (bge_m3=$BGE) — embedding-dependent features will fail"
  fi
else
  fail "Backend health endpoint unreachable or returned error (is uvicorn running?)"
fi

# ══════════════════════════════════════════════════════════════
section "3. vLLM — health endpoint"
# ══════════════════════════════════════════════════════════════

if curl -sf "$VLLM/health" > /dev/null 2>&1; then
  ok "vLLM health endpoint OK (port 9001)"
  VLLM_STATUS=$(echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('vllm',''))" 2>/dev/null)
  if [ "$VLLM_STATUS" = "ready" ]; then
    ok "Backend reports vLLM as ready"
  else
    fail "Backend reports vLLM=$VLLM_STATUS (model may still be loading)"
  fi
else
  fail "vLLM health endpoint unreachable on port 9001"
fi

# ══════════════════════════════════════════════════════════════
section "4. Frontend — HTTP response"
# ══════════════════════════════════════════════════════════════

FE_STATUS=$(curl -so /dev/null -w "%{http_code}" "$FRONTEND" 2>/dev/null)
if [ "$FE_STATUS" = "200" ]; then
  ok "Frontend returns HTTP 200"
else
  fail "Frontend HTTP $FE_STATUS (expected 200) — check npm start log"
fi

# Check that the response contains Tailwind-generated CSS (bundle contains class names)
FE_BODY=$(curl -sf "$FRONTEND" 2>/dev/null)
if echo "$FE_BODY" | grep -q "_next/static"; then
  ok "Frontend serves Next.js static assets (bundle present)"
else
  fail "Frontend HTML missing _next/static references — Tailwind/JS bundle may be broken"
fi

# ══════════════════════════════════════════════════════════════
section "5. Auth — signup and login"
# ══════════════════════════════════════════════════════════════

SMOKE_EMAIL="smoketest_$(date +%s)@example.com"
SMOKE_USER="smoketest$(date +%s)"
SMOKE_PASS="SmokePass123!"

REGISTER=$(curl -sf -X POST "$BACKEND/api/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$SMOKE_EMAIL\",\"username\":\"$SMOKE_USER\",\"password\":\"$SMOKE_PASS\"}" 2>/dev/null)

if echo "$REGISTER" | grep -q '"access_token"'; then
  ok "Register endpoint returns JWT token"
  TOKEN=$(echo "$REGISTER" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null)
else
  fail "Register failed: $REGISTER"
  TOKEN=""
fi

if [ -n "$TOKEN" ]; then
  LOGIN=$(curl -sf -X POST "$BACKEND/api/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$SMOKE_EMAIL\",\"password\":\"$SMOKE_PASS\"}" 2>/dev/null)
  if echo "$LOGIN" | grep -q '"access_token"'; then
    ok "Login endpoint returns JWT token"
  else
    fail "Login failed: $LOGIN"
  fi

  # ════════════════════════════════════════════════════════════
  section "6. Project / Story creation"
  # ════════════════════════════════════════════════════════════

  PROJECT=$(curl -sf -X POST "$BACKEND/api/projects/" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"title":"Smoke Test Novel","description":"auto smoke test"}' 2>/dev/null)

  if echo "$PROJECT" | grep -q '"story_id"'; then
    ok "Project creation returns story object"
    STORY_ID=$(echo "$PROJECT" | python3 -c "import sys,json; print(json.load(sys.stdin)['story_id'])" 2>/dev/null)
  else
    fail "Project creation failed: $PROJECT"
    STORY_ID=""
  fi

  # ════════════════════════════════════════════════════════════
  section "7. Chapter creation / content save / reload"
  # ════════════════════════════════════════════════════════════

  if [ -n "$STORY_ID" ]; then
    CH=$(curl -sf -X POST "$BACKEND/api/stories/$STORY_ID/chapters" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $TOKEN" \
      -d '{"title":"Chapter 1","content":""}' 2>/dev/null)

    if echo "$CH" | grep -q '"chapter_id"'; then
      ok "Chapter creation returns chapter object"
      CH_ID=$(echo "$CH" | python3 -c "import sys,json; print(json.load(sys.stdin)['chapter_id'])" 2>/dev/null)
    else
      fail "Chapter creation failed: $CH"
      CH_ID=""
    fi

    if [ -n "$CH_ID" ]; then
      # Save content
      CONTENT="<p>The smoke test chapter content. It has multiple words so word count is non-zero.</p>"
      SAVE=$(curl -sf -X PATCH "$BACKEND/api/stories/$STORY_ID/chapters/$CH_ID" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $TOKEN" \
        -d "{\"content\":\"$CONTENT\"}" 2>/dev/null)

      WC=$(echo "$SAVE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('word_count',0))" 2>/dev/null)
      if [ "${WC:-0}" -gt 0 ]; then
        ok "Chapter save returns non-zero word_count ($WC words)"
      else
        fail "Chapter save returned word_count=0 or save failed: $SAVE"
      fi

      # Reload
      RELOAD=$(curl -sf "$BACKEND/api/stories/$STORY_ID/chapters/$CH_ID" \
        -H "Authorization: Bearer $TOKEN" 2>/dev/null)
      RELOAD_CONTENT=$(echo "$RELOAD" | python3 -c "import sys,json; print(json.load(sys.stdin).get('content',''))" 2>/dev/null)
      if echo "$RELOAD_CONTENT" | grep -q "smoke test"; then
        ok "Chapter content persists and reloads correctly"
      else
        fail "Chapter reload returned unexpected content: $RELOAD_CONTENT"
      fi

      # Verify the full list API also works (word_count present)
      LIST=$(curl -sf "$BACKEND/api/stories/$STORY_ID/chapters" \
        -H "Authorization: Bearer $TOKEN" 2>/dev/null)
      LIST_WC=$(echo "$LIST" | python3 -c "import sys,json; d=json.load(sys.stdin); ch=next((c for c in d if c['chapter_id']=='$CH_ID'),None); print(ch.get('word_count',0) if ch else 0)" 2>/dev/null)
      if [ "${LIST_WC:-0}" -gt 0 ]; then
        ok "Chapters list returns chapter with correct word_count ($LIST_WC)"
      else
        fail "Chapters list word_count wrong: $LIST"
      fi
    fi
  fi

  # ════════════════════════════════════════════════════════════
  section "8. Genre detection (backend prompt + response shape)"
  # ════════════════════════════════════════════════════════════

  if [ -n "$STORY_ID" ]; then
    INTAKE=$(curl -sf -X POST "$BACKEND/api/intake/$STORY_ID" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $TOKEN" \
      -d '{"description":"A retired soldier discovers a secret underground city beneath New York where forgotten memories are traded like currency. She must navigate political factions and recover her own stolen past before the city collapses."}' 2>/dev/null)

    if echo "$INTAKE" | grep -q '"intake_id"'; then
      ok "Genre detection returns intake_id"
      GENRE=$(echo "$INTAKE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['genre_profile']['genre'])" 2>/dev/null)
      CONF=$(echo "$INTAKE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['genre_profile']['confidence'])" 2>/dev/null)
      if [ -n "$GENRE" ]; then
        ok "Genre detected: $GENRE (confidence=$CONF)"
      else
        fail "Genre field empty in intake response"
      fi
    else
      # vLLM may not be ready; this is a soft fail
      echo "  [WARN] Genre detection returned no intake_id (vLLM may still be loading)"
      echo "         Response: $INTAKE"
    fi
  fi

  # ════════════════════════════════════════════════════════════
  section "9. Story checking / cache detection (sync-summaries)"
  # ════════════════════════════════════════════════════════════

  if [ -n "$STORY_ID" ]; then
    SYNC=$(curl -sf -X POST "$BACKEND/api/stories/$STORY_ID/chapters/sync-summaries" \
      -H "Authorization: Bearer $TOKEN" 2>/dev/null)
    if echo "$SYNC" | grep -q '"chapters_queued"'; then
      ok "sync-summaries endpoint responds correctly"
    else
      fail "sync-summaries failed: $SYNC"
    fi
  fi

  # ════════════════════════════════════════════════════════════
  section "10. Plot assistant (requires vLLM)"
  # ════════════════════════════════════════════════════════════

  if [ -n "$STORY_ID" ]; then
    PLOT=$(curl -sf -X POST "$BACKEND/api/plot-assistant/" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $TOKEN" \
      -d "{\"story_id\":\"$STORY_ID\",\"question\":\"What should happen next in my story?\",\"current_chapter_text\":\"The smoke test chapter.\",\"current_chapter_number\":1}" 2>/dev/null)

    if echo "$PLOT" | grep -q '"session_id"'; then
      ok "Plot assistant returns session_id"
      MODE=$(echo "$PLOT" | python3 -c "import sys,json; print(json.load(sys.stdin)['mode'])" 2>/dev/null)
      ok "Plot assistant mode: $MODE"
    elif echo "$PLOT" | grep -q '"detail"'; then
      DETAIL=$(echo "$PLOT" | python3 -c "import sys,json; print(json.load(sys.stdin)['detail'])" 2>/dev/null)
      echo "  [WARN] Plot assistant returned error (likely vLLM not ready): $DETAIL"
    else
      fail "Plot assistant unexpected response: $PLOT"
    fi
  fi

fi

# ══════════════════════════════════════════════════════════════
section "RESULTS"
# ══════════════════════════════════════════════════════════════

echo ""
echo "  Passed : $PASS"
echo "  Failed : $FAIL"
echo ""

if [ "$FAIL" -eq 0 ]; then
  echo "  ✓ All Phase 1 smoke tests PASSED"
  exit 0
else
  echo "  ✗ $FAIL test(s) FAILED — see details above"
  exit 1
fi
