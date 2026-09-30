#!/bin/bash
# Periodic backup loop for the NarratIQ PostgreSQL database and uploads.
#
# Why this exists: scripts/startup_backup.sh only ever runs once, when
# start-narratiq.sh is invoked. This loop keeps backups current between
# restarts (2026-09-21 persistence investigation,
# docs/operations/storage-and-persistence.md).
#
# Each cycle (Stage 10, task 10.1):
#   1. scripts/backup_database.sh      — dump + integrity manifest + uploads
#                                         archive from one snapshot, checksummed;
#   2. scripts/backup_retention.py     — grandfather–father–son rotation
#                                         (24 hourly + 7 daily by default);
#   3. scripts/verify_backup.py        — restore the newest set into a scratch
#                                         database and compare every table's
#                                         content hash and every upload's SHA-256
#                                         (first cycle, then every VERIFY_EVERY_HOURS);
#   4. NARRATIQ_OFFPOD_COMMAND, if set — a provider-neutral hook that receives
#                                         the new set's file paths. NOT configured
#                                         in Stage 10 (decision S10-B); without it
#                                         LAST-OFFPOD.json records "not_configured".
#
# A failure in any step is logged and recorded; it never stops the loop, and a
# failed verification or off-pod step never prevents the next backup.
#
# Started once by start-narratiq.sh as a background process, guarded there by a
# PID file so re-running start-narratiq.sh never spawns a duplicate loop. Safe
# to kill at any time.
#
# Environment overrides:
#   NARRATIQ_PERIODIC_BACKUP_INTERVAL_HOURS  default 1   (the RPO target, see backup-and-restore.md)
#   NARRATIQ_BACKUP_KEEP_RECENT              default 24
#   NARRATIQ_BACKUP_KEEP_DAILY_DAYS          default 7
#   NARRATIQ_BACKUP_VERIFY_EVERY_HOURS       default 24  (0 = never)
#   NARRATIQ_OFFPOD_COMMAND                  unset (deferred)
#   BACKUP_DIR                               default /workspace/backups

set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-/workspace/backups}"
INTERVAL_HOURS="${NARRATIQ_PERIODIC_BACKUP_INTERVAL_HOURS:-1}"
VERIFY_EVERY_HOURS="${NARRATIQ_BACKUP_VERIFY_EVERY_HOURS:-24}"
LOCK_FILE="${BACKUP_DIR}/.periodic-backup.lock"
# Each cycle runs in a subshell (under flock), so the last verification time is
# kept in a file, not a variable. Missing file = never verified = verify now.
VERIFY_STAMP_FILE="${BACKUP_DIR}/.last-verify-epoch"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [periodic-backup] $*"; }

# A typo must not produce a busy loop (interval="") or disable verification silently.
case "${INTERVAL_HOURS}" in
    ''|*[!0-9]*|0)
        log "WARNING: NARRATIQ_PERIODIC_BACKUP_INTERVAL_HOURS='${INTERVAL_HOURS}' is not a positive whole number — using 1."
        INTERVAL_HOURS=1 ;;
esac
case "${VERIFY_EVERY_HOURS}" in
    ''|*[!0-9]*)
        log "WARNING: NARRATIQ_BACKUP_VERIFY_EVERY_HOURS='${VERIFY_EVERY_HOURS}' is invalid — using 24."
        VERIFY_EVERY_HOURS=24 ;;
esac

# The backup scripts read the DB connection from backend/.env themselves; the
# verifier and the hook need the same libpq environment.
export_pg_env() {
    local vars
    vars="$(python3 - "${REPO_ROOT}/backend/.env" <<'PYEOF' || true
import sys, shlex
from urllib.parse import urlsplit
url = None
for line in open(sys.argv[1], encoding="utf-8"):
    line = line.strip()
    if line.startswith("DATABASE_URL="):
        url = line.split("=", 1)[1].strip().strip('"').strip("'")
if not url:
    sys.exit(1)
scheme, _, rest = url.partition("://")
p = urlsplit("//" + rest)
for k, v in (("PGHOST", p.hostname), ("PGPORT", p.port or 5432), ("PGUSER", p.username),
             ("PGPASSWORD", p.password or ""), ("PGDATABASE", (p.path or "").lstrip("/"))):
    print(f"export {k}={shlex.quote(str(v))}")
PYEOF
)"
    [ -n "${vars}" ] && eval "${vars}"
}

record_offpod() {  # status, detail
    printf '{"status": "%s", "at": "%s", "detail": "%s"}\n' "$1" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$2" \
        > "${BACKUP_DIR}/LAST-OFFPOD.json" 2>/dev/null || true
}

run_cycle() {
    log "Running scheduled backup..."
    if ! bash "${REPO_ROOT}/scripts/backup_database.sh"; then
        log "WARNING: scheduled backup failed — see the output above. The next cycle will try again."
        return 0
    fi
    log "Scheduled backup complete."

    python3 "${REPO_ROOT}/scripts/backup_retention.py" --backup-dir "${BACKUP_DIR}" --apply \
        || log "WARNING: retention step failed; no backups were deleted by it."

    local now last_verify
    now="$(date +%s)"
    last_verify="$(cat "${VERIFY_STAMP_FILE}" 2>/dev/null || echo 0)"
    case "${last_verify}" in ''|*[!0-9]*) last_verify=0 ;; esac
    if [ "${VERIFY_EVERY_HOURS}" -gt 0 ] && [ $(( now - last_verify )) -ge $(( VERIFY_EVERY_HOURS * 3600 )) ]; then
        log "Verifying the newest backup by restoring it into a scratch database..."
        export_pg_env
        if BACKUP_DIR="${BACKUP_DIR}" python3 "${REPO_ROOT}/scripts/verify_backup.py" --backup-dir "${BACKUP_DIR}"; then
            log "Backup verification PASSED."
        else
            log "WARNING: backup verification FAILED — see LAST-VERIFY.json. The watchdog alerts on this."
        fi
        echo "${now}" > "${VERIFY_STAMP_FILE}" 2>/dev/null || true
    fi

    if [ -n "${NARRATIQ_OFFPOD_COMMAND:-}" ]; then
        local newest stem
        newest="$(ls -1t "${BACKUP_DIR}"/narratiq-2*.SHA256SUMS 2>/dev/null | head -1 || true)"
        if [ -z "${newest}" ]; then
            record_offpod "failed" "no backup set found"
            return 0
        fi
        stem="$(basename "${newest}" .SHA256SUMS)"
        local stamp="${stem#narratiq-}"
        if timeout 3600 bash -c "${NARRATIQ_OFFPOD_COMMAND} \"\$@\"" offpod \
                "${BACKUP_DIR}/${stem}.dump" "${BACKUP_DIR}/${stem}.manifest.json" \
                "${BACKUP_DIR}/${stem}.SHA256SUMS" "${BACKUP_DIR}/narratiq-globals-${stamp}.sql" \
                "${BACKUP_DIR}/narratiq-uploads-${stamp}.tar.gz"; then
            record_offpod "ok" "${stem}"
            log "Off-pod hook completed for ${stem}."
        else
            record_offpod "failed" "${stem}"
            log "WARNING: off-pod hook failed for ${stem}. Local backups are unaffected."
        fi
    else
        record_offpod "not_configured" "off-pod copy deferred (Stage 10, S10-B)"
    fi
}

log "Periodic backup loop started (interval=${INTERVAL_HOURS}h, verify every ${VERIFY_EVERY_HOURS}h, PID $$)"

while true; do
    sleep "$(( INTERVAL_HOURS * 3600 ))"
    (
        flock -n 9 || { log "Skipped — another backup is already running."; exit 0; }
        run_cycle
    ) 9>"${LOCK_FILE}" || log "WARNING: backup cycle ended unexpectedly; the loop continues."
done
