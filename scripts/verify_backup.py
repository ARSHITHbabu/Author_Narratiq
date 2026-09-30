#!/usr/bin/env python3
"""
Automated backup integrity verification by real restore (Stage 10, task 10.1).

For one backup set (default: the newest) it proves the backup can bring the
data back, not merely that a file exists:

  1. every checksum in the set matches the bytes on disk;
  2. `pg_restore --list` can read the archive;
  3. the dump is restored into a throw-away database (`narratiq_restorecheck`,
     the ONLY name this script will ever drop or create);
  4. the restored database's content fingerprint — every table's row count and
     content hash (vectors included), the chapter-text hash and the number of
     stored embeddings per vector column — must equal the manifest recorded at
     backup time; ai_generation_pins must restore empty (decision D9);
  5. the uploads archive is unpacked and every file's SHA-256 must equal the
     manifest.

The result is written to BACKUP_DIR/LAST-VERIFY.json (read by /api/ops/metrics
and the watchdog, which alerts on FAIL) and appended to VERIFY-RECORD.jsonl.
The scratch database is dropped afterwards (unless --keep-db). The live
database is only ever read by nothing here: restores go to the scratch name.

Superuser work (create/drop the scratch database, create the vector
extension, run pg_restore) runs through NARRATIQ_PG_SUPERUSER_CMD
(default: `su postgres -c`), because the application role cannot create
databases. The fingerprint is read as the application role (PG* environment).

Exit code 0 = PASS, 1 = FAIL, 2 = could not run (e.g. no backup found).

Usage:
    verify_backup.py [--backup-dir DIR] [--set narratiq-<stamp>] [--keep-db]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backup_snapshot import EXCLUDED_DATA, database_manifest  # noqa: E402

SCRATCH_DB = "narratiq_restorecheck"
SUPERUSER_CMD = os.environ.get("NARRATIQ_PG_SUPERUSER_CMD", "su postgres -c")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _su(cmd: str, stdin=None) -> subprocess.CompletedProcess:
    # The application role's libpq variables (PGUSER, PGHOST, …) must not leak
    # into the superuser's commands, or they would run as the application role.
    env = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
    return subprocess.run(shlex.split(SUPERUSER_CMD) + [cmd], capture_output=True, env=env,
                          stdin=stdin, text=stdin is None)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def find_set(backup_dir: Path, name: str | None) -> dict | None:
    if name:
        dump = backup_dir / f"{name}.dump"
    else:
        dumps = sorted((p for p in backup_dir.glob("narratiq-2*.dump")
                        if (backup_dir / (p.stem + ".manifest.json")).exists()),
                       key=lambda p: p.stat().st_mtime)
        if not dumps:
            return None
        dump = dumps[-1]
    stem = dump.stem                                   # narratiq-<stamp>
    stamp = stem[len("narratiq-"):]
    return {
        "stem": stem,
        "dump": dump,
        "manifest": backup_dir / f"{stem}.manifest.json",
        "sums": backup_dir / f"{stem}.SHA256SUMS",
        "globals": backup_dir / f"narratiq-globals-{stamp}.sql",
        "uploads": backup_dir / f"narratiq-uploads-{stamp}.tar.gz",
    }


def check_sums(s: dict, problems: list[str]) -> None:
    if not s["sums"].exists():
        # Older sets (before Stage 10) carry only <dump>.sha256.
        legacy = Path(str(s["dump"]) + ".sha256")
        if legacy.exists():
            want = legacy.read_text().split()[0]
            if _sha256(s["dump"]) != want:
                problems.append("dump checksum mismatch")
        else:
            problems.append("no checksum file for this set")
        return
    for line in s["sums"].read_text().splitlines():
        if not line.strip():
            continue
        want, fname = line.split(None, 1)
        f = s["dump"].parent / fname.strip().lstrip("*")
        if not f.exists():
            problems.append(f"missing file listed in checksums: {f.name}")
        elif _sha256(f) != want:
            problems.append(f"checksum mismatch: {f.name}")


def restore(s: dict, owner: str, problems: list[str]) -> float:
    started = time.monotonic()
    steps = [
        f"dropdb --if-exists {SCRATCH_DB}",
        f"createdb -O {shlex.quote(owner)} {SCRATCH_DB}",
        f"psql -v ON_ERROR_STOP=1 -q -d {SCRATCH_DB} -c 'CREATE EXTENSION IF NOT EXISTS vector'",
    ]
    for step in steps:
        r = _su(step)
        if r.returncode != 0:
            problems.append(f"scratch database setup failed: {step.split()[0]}: {r.stderr.strip()[:200]}")
            return time.monotonic() - started
    # The extension already exists (created above as superuser); leave its
    # catalogue entries out so the restore has no expected-error noise at all.
    listing = subprocess.run(["pg_restore", "--list", str(s["dump"])], capture_output=True, text=True)
    if listing.returncode != 0:
        problems.append("pg_restore cannot read the archive's table of contents")
        return time.monotonic() - started
    keep = [ln for ln in listing.stdout.splitlines() if " EXTENSION " not in ln]
    with tempfile.NamedTemporaryFile("w", suffix=".list", delete=False) as fh:
        fh.write("\n".join(keep) + "\n")
        list_file = fh.name
    os.chmod(list_file, 0o644)
    # The dump is streamed on stdin: backup files stay mode 600 (they hold
    # manuscript text) and the database superuser never needs to read them.
    try:
        with s["dump"].open("rb") as fh:
            r = _su(f"pg_restore --no-owner --role={shlex.quote(owner)} --exit-on-error "
                    f"-L {shlex.quote(list_file)} -d {SCRATCH_DB}", stdin=fh)
    finally:
        os.unlink(list_file)
    if r.returncode != 0:
        err = r.stderr.decode("utf-8", "replace") if isinstance(r.stderr, bytes) else r.stderr
        problems.append(f"pg_restore failed: {err.strip()[:300]}")
    return time.monotonic() - started


def compare(expected: dict, actual: dict, problems: list[str]) -> dict:
    summary = {"tables_checked": 0, "rows_checked": 0}
    for table, want in expected["tables"].items():
        got = actual["tables"].get(table)
        if got is None:
            problems.append(f"table missing after restore: {table}")
            continue
        if want.get("excluded"):
            if got["rows"] != 0:
                problems.append(f"{table}: excluded data was restored ({got['rows']} rows)")
            continue
        summary["tables_checked"] += 1
        summary["rows_checked"] += got["rows"]
        if got["rows"] != want["rows"]:
            problems.append(f"{table}: {got['rows']} rows restored, {want['rows']} backed up")
        elif got["content_md5"] != want["content_md5"]:
            problems.append(f"{table}: restored content differs from the backup")
    for extra in set(actual["tables"]) - set(expected["tables"]):
        problems.append(f"unexpected table after restore: {extra}")
    if expected["checks"].get("chapter_text") != actual["checks"].get("chapter_text"):
        problems.append("chapter text differs after restore")
    if expected["checks"].get("embeddings_stored") != actual["checks"].get("embeddings_stored"):
        problems.append("stored embedding counts differ after restore")
    if expected.get("alembic_revision") != actual.get("alembic_revision"):
        problems.append("schema revision differs after restore")
    summary["chapters"] = expected["checks"].get("chapter_text", {}).get("chapters")
    summary["embeddings"] = sum(expected["checks"].get("embeddings_stored", {}).values())
    return summary


def check_uploads(s: dict, manifest: dict, problems: list[str]) -> int:
    uploads = manifest.get("uploads")
    if not uploads:
        return 0
    if not s["uploads"].exists():
        problems.append("uploads archive missing")
        return 0
    want: dict = uploads["files"]
    seen = 0
    with tarfile.open(s["uploads"], "r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            data = tar.extractfile(member).read()
            seen += 1
            if want.get(member.name) != hashlib.sha256(data).hexdigest():
                problems.append(f"upload file differs or is unexpected: {member.name}")
    if seen != len(want):
        problems.append(f"uploads archive holds {seen} files, manifest lists {len(want)}")
    return seen


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify a NarratIQ backup by restoring it")
    ap.add_argument("--backup-dir", default=os.environ.get("BACKUP_DIR", "/workspace/backups"))
    ap.add_argument("--set", dest="set_name", help="narratiq-<stamp> (default: newest with a manifest)")
    ap.add_argument("--keep-db", action="store_true", help="leave the scratch database for inspection")
    args = ap.parse_args()

    backup_dir = Path(args.backup_dir)
    live_db = os.environ.get("PGDATABASE", "")
    if live_db == SCRATCH_DB:
        print("Refusing: the application database must not be the scratch database name.", file=sys.stderr)
        return 2
    s = find_set(backup_dir, args.set_name)
    if not s or not s["dump"].exists() or not s["manifest"].exists():
        print("No backup set with a manifest was found.", file=sys.stderr)
        return 2

    started = time.monotonic()
    problems: list[str] = []
    manifest = json.loads(s["manifest"].read_text())
    check_sums(s, problems)
    owner = os.environ.get("PGUSER", "narratiq")
    restore_seconds = restore(s, owner, problems) if not problems else 0.0
    summary: dict = {}
    if not problems:
        import psycopg2
        conn = psycopg2.connect(dbname=SCRATCH_DB)
        try:
            actual = database_manifest(conn.cursor())
        finally:
            conn.close()
        summary = compare(manifest, actual, problems)
    upload_files = check_uploads(s, manifest, problems)
    if not args.keep_db:
        _su(f"dropdb --if-exists {SCRATCH_DB}")

    result = {
        "result": "PASS" if not problems else "FAIL",
        "verified_at": _now(),
        "backup_set": s["stem"],
        "snapshot_taken_at": manifest.get("snapshot_taken_at"),
        "restore_seconds": round(restore_seconds, 1),
        "total_seconds": round(time.monotonic() - started, 1),
        "upload_files_verified": upload_files,
        "excluded_table_data": list(EXCLUDED_DATA),
        "problems": problems[:50],
        **summary,
    }
    for name, mode in (("LAST-VERIFY.json", "w"), ("VERIFY-RECORD.jsonl", "a")):
        try:
            with (backup_dir / name).open(mode) as fh:
                fh.write(json.dumps(result, sort_keys=True) + ("\n" if mode == "a" else ""))
        except OSError as exc:
            print(f"could not write {name}: {exc}", file=sys.stderr)
    print(json.dumps(result, indent=1, sort_keys=True))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
