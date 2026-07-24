#!/bin/bash
# Take a logical backup of the live NarratIQ PostgreSQL database.
#
# Produces three files in BACKUP_DIR, all mode 600:
#   narratiq-<UTC timestamp>.dump          pg_dump custom-format archive (compressed)
#   narratiq-<UTC timestamp>.dump.sha256   SHA-256 of the archive, for corruption detection
#   narratiq-globals-<UTC timestamp>.sql   role definitions, without password hashes
#
# The archive is verified with `pg_restore --list` before the script reports success;
# a partial archive is deleted rather than left behind looking like a backup.
#
# Read-only against the database. No downtime — pg_dump takes an MVCC snapshot, so the
# backend, vLLM and frontend can keep serving traffic while this runs.
#
# Backups are written OUTSIDE the git repository, onto the /workspace network volume.
# They contain full manuscript text. Do not move them into the repo — .gitignore has no
# rule for *.dump and they would become committable.
#
# Usage:
#   bash scripts/backup_database.sh
#
# Environment overrides:
#   BACKUP_DIR   destination directory   (default: /workspace/backups)
#   ENV_FILE     path to backend/.env    (default: <repo root>/backend/.env)

set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-/workspace/backups}"
ENV_FILE="${ENV_FILE:-${REPO_ROOT}/backend/.env}"

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DUMP_FILE="${BACKUP_DIR}/narratiq-${TIMESTAMP}.dump"
GLOBALS_FILE="${BACKUP_DIR}/narratiq-globals-${TIMESTAMP}.sql"
CHECKSUM_FILE="${DUMP_FILE}.sha256"

die() { echo "ERROR: $*" >&2; exit 1; }

# Remove half-written artifacts so a failed run never leaves something that looks
# like a usable backup. Only touches files this run created.
cleanup_partial() {
    local status=$?
    if [ "${status}" -ne 0 ]; then
        local removed=""
        for f in "${DUMP_FILE}" "${GLOBALS_FILE}" "${CHECKSUM_FILE}"; do
            if [ -e "${f}" ]; then rm -f "${f}"; removed="yes"; fi
        done
        if [ -n "${removed}" ]; then
            echo "Backup failed — partial files removed. The database was not modified." >&2
        else
            echo "Backup did not run. Nothing was written and the database was not modified." >&2
        fi
    fi
}
trap cleanup_partial EXIT

echo "======================================================"
echo " NarratIQ AI — Database Backup"
echo "======================================================"

# ── Validate environment ──────────────────────────────────────────────────────
command -v pg_dump    >/dev/null 2>&1 || die "pg_dump not found on PATH. Install postgresql-client-16."
command -v pg_restore >/dev/null 2>&1 || die "pg_restore not found on PATH. Install postgresql-client-16."
command -v pg_dumpall >/dev/null 2>&1 || die "pg_dumpall not found on PATH. Install postgresql-client-16."
command -v sha256sum  >/dev/null 2>&1 || die "sha256sum not found on PATH."
command -v python3    >/dev/null 2>&1 || die "python3 not found on PATH (required to parse DATABASE_URL)."

[ -f "${ENV_FILE}" ] || die "Environment file not found: ${ENV_FILE}
Start the stack once with start-narratiq.sh, or set ENV_FILE to the correct path."

grep -q '^DATABASE_URL=' "${ENV_FILE}" || die "DATABASE_URL is not set in ${ENV_FILE}
The backup cannot run without connection details."

# Parse DATABASE_URL into shell variables. Done in python3 rather than with a regex so
# percent-encoded passwords are decoded correctly. The password is passed to this script's
# environment only — never onto a command line, never into a log line.
CONN_VARS="$(python3 - "${ENV_FILE}" <<'PYEOF' || true
import sys, shlex
from urllib.parse import urlsplit, unquote

env_path = sys.argv[1]
url = None
with open(env_path, "r", encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if line.startswith("DATABASE_URL="):
            url = line.split("=", 1)[1].strip().strip('"').strip("'")

if not url:
    sys.exit(1)

# postgresql+psycopg2://user:pass@host:port/dbname -> strip the SQLAlchemy driver suffix
scheme, _, rest = url.partition("://")
parts = urlsplit("//" + rest, scheme=scheme.split("+", 1)[0])

host = parts.hostname
port = parts.port or 5432
user = parts.username
password = parts.password or ""
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

[ -n "${CONN_VARS}" ] || die "Could not parse DATABASE_URL from ${ENV_FILE}
Expected the form: postgresql+psycopg2://user:password@host:port/dbname"

eval "$(printf '%s\n' "${CONN_VARS}" | sed 's/^/export /')"

[ -n "${PGHOST:-}" ] && [ -n "${PGUSER:-}" ] && [ -n "${PGDATABASE:-}" ] \
    || die "DATABASE_URL parsed but is missing host, user or database name."

echo "  Source:      ${PGUSER}@${PGHOST}:${PGPORT}/${PGDATABASE}"
echo "  Destination: ${BACKUP_DIR}"

# ── Confirm the database is reachable before writing anything ─────────────────
psql -Atqc 'SELECT 1' >/dev/null 2>&1 \
    || die "Cannot connect to ${PGDATABASE} at ${PGHOST}:${PGPORT} as ${PGUSER}.
Check that PostgreSQL is running and that DATABASE_URL in ${ENV_FILE} is correct."

DB_SIZE="$(psql -Atqc 'SELECT pg_size_pretty(pg_database_size(current_database()))')"
TABLE_COUNT="$(psql -Atqc "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")"
echo "  Database:    ${DB_SIZE}, ${TABLE_COUNT} tables in public schema"

# ── Prepare the destination ───────────────────────────────────────────────────
# umask first so files are created 600 rather than being briefly world-readable.
umask 077
mkdir -p "${BACKUP_DIR}"
chmod 700 "${BACKUP_DIR}"

# The RunPod network volume is a FUSE mount that does not honour chmod — it forces
# group/other bits to mirror the owner bits, so 700/600 come back as 777/666. chmod
# still returns success, so this is checked explicitly rather than assumed. Warn
# instead of failing: the alternative is writing backups to ephemeral storage, which
# is worse. Verified once here so the mode is never silently misreported.
warn_if_mode_not_enforced() {
    local path="$1" want="$2" actual
    actual="$(stat -c '%a' "${path}")"
    if [ "${actual}" != "${want}" ]; then
        echo "  [WARN] ${path} is mode ${actual}, not ${want} — this filesystem does not enforce chmod."
        return 1
    fi
    return 0
}
if ! warn_if_mode_not_enforced "${BACKUP_DIR}" 700; then
    echo "         Backups contain full manuscript text. Treat this directory as readable"
    echo "         by anything with access to the volume, and rely on off-pod storage for"
    echo "         confidentiality. (backend/.env on this same volume is already mode 666.)"
    PERMS_ENFORCED="no"
else
    PERMS_ENFORCED="yes"
fi

# ── Dump ──────────────────────────────────────────────────────────────────────
echo ""
echo "── Dumping database"
pg_dump --format=custom --compress=6 --file="${DUMP_FILE}" \
    || die "pg_dump failed. No backup was produced."
chmod 600 "${DUMP_FILE}"
echo "  Wrote $(basename "${DUMP_FILE}") ($(du -h "${DUMP_FILE}" | cut -f1))"

# Roles are not included in pg_dump output. Without them a restore onto a rebuilt pod
# fails on the first `ALTER ... OWNER TO`. --no-role-passwords keeps SCRAM verifiers off
# disk; the password itself lives in backend/.env, which is backed up separately.
echo ""
echo "── Dumping role definitions"
pg_dumpall --globals-only --no-role-passwords -l "${PGDATABASE}" -f "${GLOBALS_FILE}" \
    || die "pg_dumpall failed while writing role definitions."
chmod 600 "${GLOBALS_FILE}"
echo "  Wrote $(basename "${GLOBALS_FILE}")"

# ── Verify the archive is readable ────────────────────────────────────────────
# A truncated dump is worse than no dump: it looks like protection and is not.
echo ""
echo "── Verifying archive"
TOC_ENTRIES="$(pg_restore --list "${DUMP_FILE}" 2>/dev/null | grep -c ';' || true)"
[ "${TOC_ENTRIES}" -gt 0 ] \
    || die "pg_restore could not read the table of contents of ${DUMP_FILE}.
The archive is unusable and has been removed."

DATA_ENTRIES="$(pg_restore --list "${DUMP_FILE}" 2>/dev/null | grep -c 'TABLE DATA' || true)"
echo "  Archive readable — ${TOC_ENTRIES} catalogue entries, ${DATA_ENTRIES} table-data entries"

# ── Checksum ──────────────────────────────────────────────────────────────────
# Recorded at creation time so later corruption is detectable.
( cd "${BACKUP_DIR}" && sha256sum "$(basename "${DUMP_FILE}")" > "$(basename "${CHECKSUM_FILE}")" )
chmod 600 "${CHECKSUM_FILE}"
echo "  SHA-256: $(cut -d' ' -f1 "${CHECKSUM_FILE}")"

echo ""
echo "======================================================"
echo " Backup complete"
echo "======================================================"
echo "  ${DUMP_FILE}"
echo "  ${GLOBALS_FILE}"
echo "  ${CHECKSUM_FILE}"
if [ "${PERMS_ENFORCED}" = "no" ]; then
    echo ""
    echo " NOTE: file permissions are not enforced on this volume — see the warning above."
fi
echo ""
echo " This backup is on the pod. It is not safe until a copy exists off-pod."
