#!/bin/bash
# Automatic pre-migration safety backup for the NarratIQ PostgreSQL database.
#
# Invoked by start-narratiq.sh immediately AFTER the database connection has been
# verified and BEFORE anything writes to the schema — create_all(),
# run_db_migrations() and `alembic upgrade head` all run after this returns.
#
# This is the UNATTENDED path. scripts/backup_database.sh remains the deliberate,
# operator-run path and is unchanged; this script is separate because a startup gate
# needs behaviour a manual backup must not have: freshness skipping, empty-database
# detection, and the authority to abort the boot.
#
# Decision table
#   database unreachable                     -> exit 1  (migrations must not run blind)
#   database empty / brand-new environment    -> exit 0  (nothing to protect; logged, no dump)
#   schema change pending, or FORCE set       -> backup REQUIRED; failure exits 1
#   no schema change + fresh backup exists    -> exit 0  (no duplicate dump)
#   no schema change + backup stale/absent    -> backup attempted; failure only warns
#
# Never restores. Restoring is deliberate and manual by design — an automatic restore
# would let an old dump silently overwrite newer data.
#
# Produces, per run, in BACKUP_DIR:
#   narratiq-<UTC timestamp>.dump           pg_dump custom-format archive
#   narratiq-<UTC timestamp>.dump.sha256    checksum of the archive
#   narratiq-globals-<UTC timestamp>.sql    role definitions (no password hashes)
#   narratiq-globals-<UTC timestamp>.sql.sha256
#   and appends an entry to BACKUP-RECORD.txt
#
# Exit codes
#   0  startup may continue
#   1  a REQUIRED safety backup could not be produced — caller must abort
#
# Environment overrides
#   BACKUP_DIR                      destination        (default: /workspace/backups)
#   ENV_FILE                        path to backend/.env
#   NARRATIQ_BACKUP_MAX_AGE_HOURS   freshness window   (default: 24)
#   NARRATIQ_BACKUP_FORCE           1 = always dump, and treat it as required
#   NARRATIQ_BACKUP_SKIP_PROBE      1 = skip the pending-schema probe, assume pending

set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-/workspace/backups}"
ENV_FILE="${ENV_FILE:-${REPO_ROOT}/backend/.env}"
RECORD_FILE="${BACKUP_DIR}/BACKUP-RECORD.txt"
MAX_AGE_HOURS="${NARRATIQ_BACKUP_MAX_AGE_HOURS:-24}"
FORCE="${NARRATIQ_BACKUP_FORCE:-0}"

# Validate the freshness window early — a typo here silently disables the age rule.
case "${MAX_AGE_HOURS}" in
    ''|*[!0-9]*)
        echo "  [backup] WARNING: NARRATIQ_BACKUP_MAX_AGE_HOURS='${MAX_AGE_HOURS}' is not a whole number — using 24."
        MAX_AGE_HOURS=24
        ;;
esac
MAX_AGE_SECONDS=$(( MAX_AGE_HOURS * 3600 ))

log()  { echo "  [backup] $*"; }
warn() { echo "  [backup] WARNING: $*"; }

# Set once the decision is made that this backup gates a destructive operation.
BACKUP_REQUIRED="no"

# Files created by THIS run, so a failure cleans up only its own partial output and
# never touches a previously good backup.
CREATED_FILES=()

fail() {
    # Abort only when the backup was protecting a pending destructive operation.
    local msg="$1"
    for f in "${CREATED_FILES[@]:-}"; do
        [ -n "${f}" ] && [ -e "${f}" ] && rm -f "${f}"
    done
    if [ "${BACKUP_REQUIRED}" = "yes" ]; then
        echo ""
        echo "  ══════════════════════════════════════════════════════════════"
        echo "   SAFETY BACKUP FAILED — STARTUP ABORTED"
        echo "  ══════════════════════════════════════════════════════════════"
        echo "   ${msg}"
        echo ""
        echo "   A schema change was about to run against a database holding data,"
        echo "   and no verified backup could be written first. Nothing has been"
        echo "   migrated; the database is unchanged."
        echo ""
        echo "   Partial files from this attempt were removed. Existing backups in"
        echo "   ${BACKUP_DIR} were not touched."
        echo ""
        echo "   Investigate, then re-run start-narratiq.sh."
        echo "  ══════════════════════════════════════════════════════════════"
        exit 1
    fi
    warn "${msg}"
    warn "No destructive operation is pending, so startup continues — but this"
    warn "database is running without a fresh backup. Fix this before the next migration."
    exit 0
}

echo ""
echo "[4d/6] Pre-migration database safety backup..."

# ── Tooling ───────────────────────────────────────────────────────────────────
for tool in pg_dump pg_dumpall pg_restore psql sha256sum python3; do
    command -v "${tool}" >/dev/null 2>&1 \
        || { BACKUP_REQUIRED="yes"; fail "${tool} not found on PATH. Install postgresql-client-16."; }
done

# ── Destination ───────────────────────────────────────────────────────────────
# Created unconditionally, even for an empty database, so the backup infrastructure
# exists from the first boot of a new environment.
umask 077
if [ ! -d "${BACKUP_DIR}" ]; then
    mkdir -p "${BACKUP_DIR}" || { BACKUP_REQUIRED="yes"; fail "Cannot create ${BACKUP_DIR}."; }
    log "Created ${BACKUP_DIR}"
fi
chmod 700 "${BACKUP_DIR}" 2>/dev/null || true

# The /workspace FUSE mount accepts chmod, reports success, then forces group/other
# bits to mirror owner bits. Report what actually took rather than what was asked for.
ACTUAL_MODE="$(stat -c '%a' "${BACKUP_DIR}" 2>/dev/null || echo '?')"
if [ "${ACTUAL_MODE}" != "700" ]; then
    log "Note: ${BACKUP_DIR} is mode ${ACTUAL_MODE} — this filesystem does not enforce chmod."
fi

[ -w "${BACKUP_DIR}" ] || { BACKUP_REQUIRED="yes"; fail "${BACKUP_DIR} is not writable."; }

# ── Connection details ────────────────────────────────────────────────────────
# Parsed out of DATABASE_URL in python so percent-encoded passwords decode correctly.
# The password reaches libpq through PGPASSWORD in this process's environment only:
# never on a command line, never in a log line, never written to disk by this script.
[ -f "${ENV_FILE}" ] || { BACKUP_REQUIRED="yes"; fail "Environment file not found: ${ENV_FILE}"; }

CONN_VARS="$(python3 - "${ENV_FILE}" <<'PYEOF' || true
import sys, shlex
from urllib.parse import urlsplit

url = None
with open(sys.argv[1], "r", encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if line.startswith("DATABASE_URL="):
            url = line.split("=", 1)[1].strip().strip('"').strip("'")

if not url:
    sys.exit(1)

# postgresql+psycopg2://user:pass@host:port/db -> drop the SQLAlchemy driver suffix
scheme, _, rest = url.partition("://")
parts = urlsplit("//" + rest, scheme=scheme.split("+", 1)[0])

host, port = parts.hostname, parts.port or 5432
user, password = parts.username, parts.password or ""
dbname = (parts.path or "").lstrip("/")

if not (host and user and dbname):
    sys.exit(1)

for name, value in (
    ("PGHOST", host), ("PGPORT", port), ("PGUSER", user),
    ("PGDATABASE", dbname), ("PGPASSWORD", password),
):
    print(f"{name}={shlex.quote(str(value))}")
PYEOF
)"

[ -n "${CONN_VARS}" ] || { BACKUP_REQUIRED="yes"; fail "Could not parse DATABASE_URL from ${ENV_FILE}."; }
eval "$(printf '%s\n' "${CONN_VARS}" | sed 's/^/export /')"

log "Source: ${PGUSER}@${PGHOST}:${PGPORT}/${PGDATABASE}"

# ── Reachability ──────────────────────────────────────────────────────────────
# Migrations run immediately after this script, so an unreachable database here is
# always fatal — it is not a state in which it is safe to proceed blind.
if ! psql -Atqc 'SELECT 1' >/dev/null 2>&1; then
    BACKUP_REQUIRED="yes"
    fail "Cannot connect to ${PGDATABASE} at ${PGHOST}:${PGPORT} as ${PGUSER}."
fi

DB_SIZE="$(psql -Atqc 'SELECT pg_size_pretty(pg_database_size(current_database()))' 2>/dev/null || echo 'unknown')"
TABLE_COUNT="$(psql -Atqc "SELECT count(*) FROM pg_tables WHERE schemaname='public'" 2>/dev/null || echo '0')"

# ── Does this database hold any data worth protecting? ────────────────────────
# EXISTS-per-table via query_to_xml rather than count(*): it short-circuits on the
# first row of each table, so cost does not grow with manuscript size. alembic_version
# is excluded — it is schema bookkeeping, not author data, and a schema-only database
# that has run migrations must still be treated as empty.
NONEMPTY_TABLES="$(psql -Atqc "
    SELECT COALESCE(sum(
        (xpath('/row/c/text()',
               query_to_xml(format('SELECT count(*) AS c FROM (SELECT 1 FROM %I.%I LIMIT 1) t',
                                   schemaname, tablename),
                            false, true, '')))[1]::text::int
    ), 0)
    FROM pg_tables
    WHERE schemaname = 'public' AND tablename <> 'alembic_version'
" 2>/dev/null || echo 'error')"

case "${NONEMPTY_TABLES}" in
    ''|*[!0-9]*)
        # Probe failed. Assume there IS data — the expensive mistake is skipping a
        # backup for a database that turns out to be full.
        warn "Could not determine whether the database holds data — assuming it does."
        HAS_DATA="yes"
        NONEMPTY_TABLES="unknown"
        ;;
    0) HAS_DATA="no"  ;;
    *) HAS_DATA="yes" ;;
esac

log "Database: ${DB_SIZE}, ${TABLE_COUNT} tables in public schema, ${NONEMPTY_TABLES} holding rows"

# ── Pending schema change? ────────────────────────────────────────────────────
# start-narratiq.sh always calls create_all(), run_db_migrations() and
# `alembic upgrade head`. On a converged database all three are no-ops, and dumping on
# every restart would be waste. So detect whether they would actually change anything:
# missing tables, missing columns, or unapplied Alembic revisions.
#
# Any failure of this probe is treated as "pending" — the safe direction.
PENDING_REASON=""
if [ "${NARRATIQ_BACKUP_SKIP_PROBE:-0}" = "1" ]; then
    SCHEMA_PENDING="yes"
    PENDING_REASON="probe skipped by NARRATIQ_BACKUP_SKIP_PROBE"
    ALEMBIC_REV="unknown"
else
    PROBE="$(cd "${REPO_ROOT}/backend" && python3 - <<'PYEOF' 2>/dev/null || true
import json

result = {"pending": True, "reason": "probe did not complete", "revision": "unknown"}
try:
    import models  # noqa: F401 — registers every ORM model on Base.metadata
    from database import engine, Base
    from sqlalchemy import inspect as sa_inspect

    insp = sa_inspect(engine)
    existing = set(insp.get_table_names())
    declared = set(Base.metadata.tables.keys())

    missing_tables = sorted(declared - existing)
    missing_cols = []
    for tname, table in Base.metadata.tables.items():
        if tname not in existing:
            continue
        have = {c["name"] for c in insp.get_columns(tname)}
        missing_cols.extend(f"{tname}.{c.name}" for c in table.columns if c.name not in have)

    # Unapplied Alembic revisions
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from alembic.runtime.migration import MigrationContext

    script = ScriptDirectory.from_config(Config("alembic.ini"))
    heads = set(script.get_heads())
    with engine.connect() as conn:
        current = set(MigrationContext.configure(conn).get_current_heads())
    unapplied = sorted(heads - current)

    reasons = []
    if missing_tables:
        reasons.append(f"{len(missing_tables)} table(s) to create: {', '.join(missing_tables[:5])}")
    if missing_cols:
        reasons.append(f"{len(missing_cols)} column(s) to add: {', '.join(missing_cols[:5])}")
    if unapplied:
        reasons.append(f"unapplied Alembic revision(s): {', '.join(unapplied)}")

    result = {
        "pending": bool(reasons),
        "reason": "; ".join(reasons) if reasons else "schema already matches models and Alembic head",
        "revision": ",".join(sorted(current)) if current else "none",
    }
except Exception as exc:  # noqa: BLE001 — any failure must land on the safe side
    result = {"pending": True, "reason": f"probe failed: {type(exc).__name__}: {exc}", "revision": "unknown"}

print(json.dumps(result))
PYEOF
)"

    if [ -z "${PROBE}" ]; then
        SCHEMA_PENDING="yes"
        PENDING_REASON="schema probe produced no output"
        ALEMBIC_REV="unknown"
    else
        SCHEMA_PENDING="$(printf '%s' "${PROBE}" | python3 -c \
            'import json,sys; print("yes" if json.load(sys.stdin).get("pending") else "no")' 2>/dev/null || echo yes)"
        PENDING_REASON="$(printf '%s' "${PROBE}" | python3 -c \
            'import json,sys; print(json.load(sys.stdin).get("reason",""))' 2>/dev/null || echo 'probe unreadable')"
        ALEMBIC_REV="$(printf '%s' "${PROBE}" | python3 -c \
            'import json,sys; print(json.load(sys.stdin).get("revision","unknown"))' 2>/dev/null || echo unknown)"
    fi
fi

log "Alembic revision: ${ALEMBIC_REV}"
if [ "${SCHEMA_PENDING}" = "yes" ]; then
    log "Pending schema change: YES — ${PENDING_REASON}"
else
    log "Pending schema change: no (${PENDING_REASON})"
fi

# ── Newest valid existing backup ──────────────────────────────────────────────
# "Valid" = a .dump whose table of contents pg_restore can read, and which has a
# recorded checksum. The checksum is not re-verified here: on every startup that
# would mean re-hashing the whole archive to answer a scheduling question. Corruption
# is caught by `sha256sum -c` at restore time, which is when it matters.
LATEST_BACKUP=""
LATEST_AGE_SECONDS=0
NOW_EPOCH="$(date -u +%s)"

while IFS= read -r candidate; do
    [ -n "${candidate}" ] || continue
    [ -f "${candidate}.sha256" ] || continue
    pg_restore --list "${candidate}" >/dev/null 2>&1 || continue
    LATEST_BACKUP="${candidate}"
    LATEST_AGE_SECONDS=$(( NOW_EPOCH - $(stat -c '%Y' "${candidate}") ))
    break
done <<< "$(find "${BACKUP_DIR}" -maxdepth 1 -type f -name 'narratiq-*.dump' \
              -printf '%T@ %p\n' 2>/dev/null | sort -rn | cut -d' ' -f2-)"

if [ -n "${LATEST_BACKUP}" ]; then
    log "Newest valid backup: $(basename "${LATEST_BACKUP}") ($(( LATEST_AGE_SECONDS / 3600 ))h old)"
else
    log "Newest valid backup: none found"
fi

# ── Decide ────────────────────────────────────────────────────────────────────
DO_BACKUP="no"
DECISION=""

if [ "${HAS_DATA}" = "no" ]; then
    # New or empty environment. There is no previous data, so any dump written here
    # would be an empty archive carrying a reassuring filename — worse than nothing.
    DECISION="empty database — no data to back up"
    log "This database holds no author data (new or freshly provisioned environment)."
    log "No backup written: an empty archive would misrepresent itself as protection."
    log "Backup directory and record are in place; the first real backup happens once"
    log "the database holds data."
    if [ "${TABLE_COUNT}" != "0" ]; then
        log "Schema is present but every table is empty. If this pod is a rebuild and you"
        log "expected data here, the data is NOT here — restore explicitly. Startup never"
        log "restores by itself, so an old dump can never silently overwrite newer data."
        log "See the Restore: line of the newest entry in ${RECORD_FILE}."
    fi
    # Record the observation. A run that legitimately produced no backup should still
    # leave evidence of why, so a later audit can tell "empty database" apart from
    # "the backup step never ran".
    {
        echo ""
        echo "--- Automatic backup skipped: empty database (start-narratiq.sh) ---"
        echo "Recorded:    $(date -u +%Y-%m-%dT%H:%M:%SZ) (UTC)"
        echo "Database:    ${PGDATABASE} on ${PGHOST}:${PGPORT}"
        echo "Size:        ${DB_SIZE}, ${TABLE_COUNT} tables in public schema, 0 holding rows"
        echo "Revision:    alembic ${ALEMBIC_REV}"
        echo "Result:      NO BACKUP CREATED — the database contains no author data."
        echo "             This is not a failure. There was nothing to protect."
        echo "Note:        No dump file was written, deliberately. An empty archive named"
        echo "             like a real backup would misrepresent itself as protection."
    } >> "${RECORD_FILE}" 2>/dev/null || warn "Could not update ${RECORD_FILE}."
    chmod 600 "${RECORD_FILE}" 2>/dev/null || true
elif [ "${FORCE}" = "1" ]; then
    DO_BACKUP="yes"; BACKUP_REQUIRED="yes"
    DECISION="forced by NARRATIQ_BACKUP_FORCE=1"
elif [ "${SCHEMA_PENDING}" = "yes" ]; then
    DO_BACKUP="yes"; BACKUP_REQUIRED="yes"
    DECISION="pre-migration safety backup (${PENDING_REASON})"
elif [ -z "${LATEST_BACKUP}" ]; then
    DO_BACKUP="yes"
    DECISION="no valid backup exists"
elif [ "${LATEST_AGE_SECONDS}" -gt "${MAX_AGE_SECONDS}" ]; then
    DO_BACKUP="yes"
    DECISION="newest backup is $(( LATEST_AGE_SECONDS / 3600 ))h old, older than ${MAX_AGE_HOURS}h"
else
    DECISION="a backup $(( LATEST_AGE_SECONDS / 3600 ))h old already exists (limit ${MAX_AGE_HOURS}h) and no schema change is pending"
fi

if [ "${DO_BACKUP}" = "no" ]; then
    log "Decision: skip — ${DECISION}"
    echo "  Pre-migration backup check complete."
    exit 0
fi

if [ "${BACKUP_REQUIRED}" = "yes" ]; then
    log "Decision: BACKUP REQUIRED — ${DECISION}"
    log "Startup will abort if this backup cannot be completed and verified."
else
    log "Decision: backup — ${DECISION}"
fi

# ── Filenames that cannot clobber an existing backup ──────────────────────────
# Second-resolution timestamps can collide (two runs in the same second, or a clock
# step). Probe for a free name rather than trusting the timestamp to be unique.
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
SUFFIX=""
ATTEMPT=0
while :; do
    DUMP_FILE="${BACKUP_DIR}/narratiq-${TIMESTAMP}${SUFFIX}.dump"
    GLOBALS_FILE="${BACKUP_DIR}/narratiq-globals-${TIMESTAMP}${SUFFIX}.sql"
    if [ ! -e "${DUMP_FILE}" ] && [ ! -e "${GLOBALS_FILE}" ] \
       && [ ! -e "${DUMP_FILE}.sha256" ] && [ ! -e "${GLOBALS_FILE}.sha256" ]; then
        break
    fi
    ATTEMPT=$(( ATTEMPT + 1 ))
    [ "${ATTEMPT}" -le 99 ] || fail "Could not find a free backup filename for ${TIMESTAMP} after 99 attempts."
    SUFFIX="-${ATTEMPT}"
done
[ "${ATTEMPT}" -gt 0 ] && log "Name ${TIMESTAMP} was taken — using suffix ${SUFFIX} so no existing backup is overwritten."

DUMP_SHA="${DUMP_FILE}.sha256"
GLOBALS_SHA="${GLOBALS_FILE}.sha256"

# ── Dump ──────────────────────────────────────────────────────────────────────
# Read-only, MVCC snapshot — the running backend keeps serving while this happens.
CREATED_FILES+=("${DUMP_FILE}")
pg_dump --format=custom --compress=6 --file="${DUMP_FILE}" \
    || fail "pg_dump failed. No usable backup was produced."
chmod 600 "${DUMP_FILE}" 2>/dev/null || true
log "Wrote $(basename "${DUMP_FILE}") ($(du -h "${DUMP_FILE}" | cut -f1))"

# Roles are not in pg_dump output; without them a restore onto a rebuilt pod fails on
# the first ALTER ... OWNER TO. --no-role-passwords keeps SCRAM verifiers off disk.
CREATED_FILES+=("${GLOBALS_FILE}")
pg_dumpall --globals-only --no-role-passwords -l "${PGDATABASE}" -f "${GLOBALS_FILE}" \
    || fail "pg_dumpall failed while writing role definitions."
chmod 600 "${GLOBALS_FILE}" 2>/dev/null || true
log "Wrote $(basename "${GLOBALS_FILE}")"

# ── Verify before trusting it ─────────────────────────────────────────────────
# A truncated archive is worse than no archive: it looks like protection.
TOC_ENTRIES="$(pg_restore --list "${DUMP_FILE}" 2>/dev/null | grep -c ';' || true)"
[ "${TOC_ENTRIES:-0}" -gt 0 ] \
    || fail "pg_restore cannot read the table of contents of $(basename "${DUMP_FILE}") — the archive is unusable."
DATA_ENTRIES="$(pg_restore --list "${DUMP_FILE}" 2>/dev/null | grep -c 'TABLE DATA' || true)"
log "Archive verified — ${TOC_ENTRIES} catalogue entries, ${DATA_ENTRIES} table-data entries"

# ── Checksums ─────────────────────────────────────────────────────────────────
CREATED_FILES+=("${DUMP_SHA}" "${GLOBALS_SHA}")
( cd "${BACKUP_DIR}" && sha256sum "$(basename "${DUMP_FILE}")"    > "$(basename "${DUMP_SHA}")" ) \
    || fail "Could not write the checksum for $(basename "${DUMP_FILE}")."
( cd "${BACKUP_DIR}" && sha256sum "$(basename "${GLOBALS_FILE}")" > "$(basename "${GLOBALS_SHA}")" ) \
    || fail "Could not write the checksum for $(basename "${GLOBALS_FILE}")."
chmod 600 "${DUMP_SHA}" "${GLOBALS_SHA}" 2>/dev/null || true

# Read the checksums back and confirm they match the files on disk. This is the one
# place a full re-hash is worth its cost — it proves the bytes that landed on the
# volume are the bytes that were hashed.
( cd "${BACKUP_DIR}" && sha256sum -c --quiet "$(basename "${DUMP_SHA}")" "$(basename "${GLOBALS_SHA}")" ) \
    || fail "Checksum verification failed immediately after writing — the volume may be faulty."
DUMP_HASH="$(cut -d' ' -f1 "${DUMP_SHA}")"
log "SHA-256 verified: ${DUMP_HASH}"

# ── Record ────────────────────────────────────────────────────────────────────
# Appended, never rewritten, so earlier entries survive.
{
    echo ""
    echo "--- Automatic pre-migration backup (start-narratiq.sh) ---"
    echo "Recorded:    $(date -u +%Y-%m-%dT%H:%M:%SZ) (UTC)"
    echo "Database:    ${PGDATABASE} on ${PGHOST}:${PGPORT}"
    echo "Size:        ${DB_SIZE}, ${TABLE_COUNT} tables in public schema"
    echo "Revision:    alembic ${ALEMBIC_REV}"
    echo "Trigger:     ${DECISION}"
    echo "Required:    ${BACKUP_REQUIRED}"
    echo "Result:      SUCCESS — archive verified, ${TOC_ENTRIES} catalogue entries, ${DATA_ENTRIES} table-data entries"
    echo "Dump:        $(basename "${DUMP_FILE}") ($(du -h "${DUMP_FILE}" | cut -f1))"
    echo "             SHA-256 ${DUMP_HASH}"
    echo "Globals:     $(basename "${GLOBALS_FILE}")"
    echo "             SHA-256 $(cut -d' ' -f1 "${GLOBALS_SHA}")"
    echo "Verify:      cd ${BACKUP_DIR} && sha256sum -c $(basename "${DUMP_SHA}")"
    echo "Restore:     # DELIBERATE, MANUAL ONLY — never run automatically at startup."
    echo "             #   1. stop the backend:  pkill -f 'uvicorn main:app'"
    echo "             #   2. roles (new pod):   psql -U postgres -f ${BACKUP_DIR}/$(basename "${GLOBALS_FILE}")"
    echo "             #   3. restore:"
    echo "             pg_restore --clean --if-exists --no-owner --role=${PGUSER} \\"
    echo "                 -h ${PGHOST} -p ${PGPORT} -U ${PGUSER} -d ${PGDATABASE} \\"
    echo "                 ${BACKUP_DIR}/$(basename "${DUMP_FILE}")"
    echo "             # --clean DROPS existing objects. Take a pre-restore dump first."
    echo "Off-pod:     NO — ${BACKUP_DIR} is on the RunPod network volume. It survives pod"
    echo "             recreation, but not deletion or loss of the volume itself."
} >> "${RECORD_FILE}" || warn "Backup succeeded but the record file could not be updated."
chmod 600 "${RECORD_FILE}" 2>/dev/null || true
log "Recorded in $(basename "${RECORD_FILE}")"

# Success — disarm the cleanup list so nothing removes what we just verified.
CREATED_FILES=()

echo "  Pre-migration backup complete. Safe to migrate."
exit 0
