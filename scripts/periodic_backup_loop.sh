#!/bin/bash
# Lightweight periodic backup loop for the NarratIQ PostgreSQL database.
#
# Why this exists: scripts/startup_backup.sh only ever runs once, when
# start-narratiq.sh is invoked. A long-running session with no restart in
# between gets no further backups until the next manual run or the next
# restart — the exact window flagged during the 2026-09-21 persistence
# investigation (docs/operations/storage-and-persistence.md). This loop closes
# that window with the smallest reasonable mechanism: call the existing,
# already-verified scripts/backup_database.sh on a fixed interval, then prune
# old backups so disk usage stays bounded. No new backup logic is introduced —
# this only schedules and rotates the existing script.
#
# Started once by start-narratiq.sh as a background process, guarded there by
# a PID file so re-running start-narratiq.sh never spawns a duplicate loop.
# Safe to kill at any time (SIGTERM/SIGKILL) — it holds no state between runs
# beyond the files backup_database.sh itself already writes.
#
# Environment overrides:
#   NARRATIQ_PERIODIC_BACKUP_INTERVAL_HOURS   default 4
#   NARRATIQ_PERIODIC_BACKUP_RETENTION_COUNT  default 12  (~48h of history at the default interval)
#   BACKUP_DIR                                default /workspace/backups

set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-/workspace/backups}"
INTERVAL_HOURS="${NARRATIQ_PERIODIC_BACKUP_INTERVAL_HOURS:-4}"
RETENTION_COUNT="${NARRATIQ_PERIODIC_BACKUP_RETENTION_COUNT:-12}"
LOCK_FILE="${BACKUP_DIR}/.periodic-backup.lock"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [periodic-backup] $*"; }

# Validate the numeric overrides early — a typo should not silently produce a
# busy-loop (interval="") or a retention of zero that deletes everything.
case "${INTERVAL_HOURS}" in
    ''|*[!0-9]*)
        log "WARNING: NARRATIQ_PERIODIC_BACKUP_INTERVAL_HOURS='${INTERVAL_HOURS}' is not a whole number — using 4."
        INTERVAL_HOURS=4
        ;;
esac
case "${RETENTION_COUNT}" in
    ''|*[!0-9]*|0)
        log "WARNING: NARRATIQ_PERIODIC_BACKUP_RETENTION_COUNT='${RETENTION_COUNT}' is invalid — using 12."
        RETENTION_COUNT=12
        ;;
esac

prune_old_backups() {
    # Keep the RETENTION_COUNT most recent dump sets (dump + sha256 + matching
    # globals + sha256); delete older ones. A directory with RETENTION_COUNT or
    # fewer backups is never touched — this can only remove backups beyond the
    # kept count, never the only copy, and never a file that is not itself a
    # recognised narratiq-*.dump backup artefact.
    local dumps count=0 f ts
    dumps="$(find "${BACKUP_DIR}" -maxdepth 1 -type f -name 'narratiq-*.dump' -printf '%T@ %p\n' 2>/dev/null \
             | sort -rn | cut -d' ' -f2-)"
    while IFS= read -r f; do
        [ -n "${f}" ] || continue
        count=$((count + 1))
        if [ "${count}" -gt "${RETENTION_COUNT}" ]; then
            ts="$(basename "${f}" .dump | sed 's/^narratiq-//')"
            log "Pruning backup beyond retention of ${RETENTION_COUNT}: $(basename "${f}")"
            rm -f "${f}" "${f}.sha256" \
                  "${BACKUP_DIR}/narratiq-globals-${ts}.sql" \
                  "${BACKUP_DIR}/narratiq-globals-${ts}.sql.sha256"
        fi
    done <<< "${dumps}"
}

log "Periodic backup loop started (interval=${INTERVAL_HOURS}h, retention=${RETENTION_COUNT} backups, PID $$)"

while true; do
    sleep "$(( INTERVAL_HOURS * 3600 ))"
    (
        flock -n 9 || { log "Skipped — another backup is already running."; exit 0; }
        log "Running scheduled backup..."
        if bash "${REPO_ROOT}/scripts/backup_database.sh"; then
            log "Scheduled backup complete."
            prune_old_backups
        else
            log "WARNING: scheduled backup failed — see this log for pg_dump output above."
        fi
    ) 9>"${LOCK_FILE}"
done
