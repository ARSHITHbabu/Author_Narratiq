#!/bin/bash
# Daily manual operational check (owner decision W-4, 2026-10-05).
#
# Until alerts are delivered to a person (S10-D / W-4), an operator runs this
# once a day and records the result. It is READ-ONLY: it never restarts,
# repairs, deletes or backs up anything, and never prints a secret.
#
# Usage:  bash scripts/daily_check.sh            # prints the report
#         bash scripts/daily_check.sh --record   # also appends the verdict to $LOG
#
# Exit code: 0 = all checks OK, 1 = at least one needs attention (see the
# ATTENTION lines and docs/operations/incident-response.md).
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-/workspace/backups}"
PERSIST_LOG_DIR="${PERSIST_LOG_DIR:-/workspace/logs}"
RUN_DIR="${LOG_DIR:-/tmp/narratiq-logs}"
LOG="${PERSIST_LOG_DIR}/daily-check.log"
BACKEND="${BACKEND_URL:-http://127.0.0.1:8000}"
MAX_BACKUP_AGE_H="${NARRATIQ_ALERT_BACKUP_MAX_AGE_HOURS:-3}"
ATTENTION=0

ok()   { echo "  OK         $*"; }
warn() { echo "  ATTENTION  $*"; ATTENTION=1; }

echo "NarratIQ daily check — $(date -u +%FT%TZ) — pod ${RUNPOD_POD_ID:-unknown}"

# 1. Service health (503 = degraded; see monitoring-and-alerting.md §1)
code=$(curl -s -o /tmp/.nq-health.json -w '%{http_code}' --max-time 10 "$BACKEND/api/health" || echo 000)
if [ "$code" = "200" ]; then ok "backend /api/health 200 ($(tr -d '\n' < /tmp/.nq-health.json | cut -c1-120))"
else warn "backend /api/health answered $code"; fi
rm -f /tmp/.nq-health.json

# 2. Alerts raised in the last 24 h (watchdog → alerts.jsonl)
python3 - "$PERSIST_LOG_DIR/alerts.jsonl" <<'PY' || ATTENTION=1
import json, sys
from datetime import datetime, timedelta, timezone
path = sys.argv[1]
since = datetime.now(timezone.utc) - timedelta(hours=24)
firing, resolved = {}, set()
try:
    lines = open(path).read().splitlines()
except FileNotFoundError:
    print(f"  ATTENTION  no alert log at {path} — is the watchdog running?"); sys.exit(1)
for line in lines:
    try:
        a = json.loads(line)
        ts = datetime.strptime(a["ts"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception:
        continue
    if ts < since:
        continue
    if a.get("state") == "resolved":
        resolved.add(a["alert"]); firing.pop(a["alert"], None)
    else:
        firing[a["alert"]] = a
n = sum(1 for l in lines if l.strip())
if firing:
    for k, a in firing.items():
        print(f"  ATTENTION  alert still firing: {k} ({a.get('severity')}) since {a.get('ts')}")
    sys.exit(1)
print(f"  OK         no alert still firing in the last 24 h ({len(resolved)} raised and resolved; {n} lines in total)")
PY

# 3. Backups: newest set, its age, the last restore verification, the off-pod status
newest=$(ls -1t "$BACKUP_DIR"/narratiq-2*.SHA256SUMS 2>/dev/null | head -1)
if [ -z "$newest" ]; then warn "no backup set in $BACKUP_DIR"
else
  age_h=$(( ( $(date +%s) - $(stat -c %Y "$newest") ) / 3600 ))
  if [ "$age_h" -le "$MAX_BACKUP_AGE_H" ]; then ok "newest backup $(basename "$newest" .SHA256SUMS), ${age_h} h old"
  else warn "newest backup is ${age_h} h old (limit ${MAX_BACKUP_AGE_H} h)"; fi
fi
python3 - "$BACKUP_DIR" <<'PY' || ATTENTION=1
import json, sys
d = sys.argv[1]
try:
    v = json.load(open(f"{d}/LAST-VERIFY.json"))
    if v.get("result") == "PASS":
        print(f"  OK         last restore verification PASS ({v.get('backup_set')}, {v.get('verified_at')})")
    else:
        print(f"  ATTENTION  last restore verification {v.get('result')}: {v.get('problems')}"); sys.exit(1)
except FileNotFoundError:
    print("  ATTENTION  no LAST-VERIFY.json yet"); sys.exit(1)
try:
    o = json.load(open(f"{d}/LAST-OFFPOD.json"))
    status = o.get("status")
    # W-3: no real author data may be stored until an off-pod copy exists and a restore from it was verified.
    print(f"  {'OK        ' if status == 'ok' else 'ATTENTION '} off-pod copy: {status} — {o.get('detail', '')}")
    if status != "ok":
        print("             W-3: real author data must not be stored until an approved off-pod copy is verified")
        sys.exit(1)
except FileNotFoundError:
    print("  ATTENTION  no LAST-OFFPOD.json"); sys.exit(1)
PY

# 4. Background processes started by start-narratiq.sh
for name in watchdog periodic-backup; do
  pidf="$RUN_DIR/$name.pid"
  if [ -f "$pidf" ] && kill -0 "$(cat "$pidf")" 2>/dev/null; then ok "$name running (pid $(cat "$pidf"))"
  else warn "$name is not running"; fi
done
hb="$PERSIST_LOG_DIR/watchdog.heartbeat"
[ -f "$hb" ] && [ $(( $(date +%s) - $(stat -c %Y "$hb") )) -le 300 ] && ok "watchdog heartbeat fresh" \
  || warn "watchdog heartbeat missing or older than 5 min"

# 5. Disk space on the volume and the container layer
for mnt in /workspace /; do
  pct=$(df --output=pcent "$mnt" | tail -1 | tr -dc 0-9)
  if [ "${pct:-100}" -lt 85 ]; then ok "disk $mnt ${pct}% used"; else warn "disk $mnt ${pct}% used"; fi
done

# 6. Recent errors and failed jobs (ops token read from backend/.env, never printed)
tok=$(grep -E '^OPS_TOKEN=' "$REPO/backend/.env" 2>/dev/null | cut -d= -f2-)
if [ -n "$tok" ]; then
  curl -s --max-time 10 -H "X-Ops-Token: $tok" "$BACKEND/api/ops/metrics" > /tmp/.nq-metrics.json
  python3 - /tmp/.nq-metrics.json <<'PY' || ATTENTION=1
import json, sys
try:
    m = json.load(open(sys.argv[1]))
except Exception:
    print("  ATTENTION  /api/ops/metrics unreadable"); sys.exit(1)
h60 = (m.get("http") or {}).get("last_60m", {})
failed = {k: v.get("failed_last_60m", 0) for k, v in (m.get("background_jobs") or {}).items() if v.get("failed_last_60m")}
errs = m.get("error_events_last_60m", 0)
bad = bool(h60.get("server_errors", 0) or h60.get("ai_unavailable", 0) or failed or errs or m.get("vllm") != "ready")
label = "ATTENTION " if bad else "OK        "
print(f"  {label} last 60 min: {h60.get('requests', 0)} requests, {h60.get('server_errors', 0)} server errors, "
      f"{h60.get('ai_unavailable', 0)} AI unavailable, {errs} error records, failed jobs {failed or 'none'}, "
      f"vLLM {m.get('vllm')}")
sys.exit(1 if bad else 0)
PY
  rm -f /tmp/.nq-metrics.json
else
  warn "OPS_TOKEN not set in backend/.env — ops metrics not checked"
fi

verdict=$([ "$ATTENTION" -eq 0 ] && echo "ALL OK" || echo "NEEDS ATTENTION")
echo "Verdict: $verdict"
if [ "${1:-}" = "--record" ]; then
  mkdir -p "$PERSIST_LOG_DIR"
  echo "$(date -u +%FT%TZ) ${USER:-operator} $verdict" >> "$LOG"
  echo "Recorded in $LOG"
fi
exit "$ATTENTION"
