#!/usr/bin/env python3
"""
Consistent database dump + integrity manifest + uploads archive
(Stage 10, task 10.1 — internal, provider-neutral).

Why: a row count proves a table is not empty; it does not prove the data is
right. The manifest records, for the SAME snapshot the dump was taken from,
a content hash of every table (every column of every row, pgvector columns
included), the chapter-text hash, the number of stored embeddings per vector
column, and a SHA-256 for every uploaded file. scripts/verify_backup.py
restores the dump into a scratch database and recomputes all of it; any
difference fails the verification.

Consistency: the manifest transaction exports its snapshot and pg_dump runs
with --snapshot=<it>, so the dump and the manifest describe exactly the same
data even while authors keep writing (no downtime, read-only).

Decision D9: ai_generation_pins rows are excluded from the dump; the manifest
records the live count as `excluded` and expects 0 rows after a restore.

Connection details come from the libpq environment (PGHOST, PGPORT, PGUSER,
PGPASSWORD, PGDATABASE) — the calling bash scripts export them from
backend/.env, and nothing here prints a credential.

Usage (called by backup_database.sh / startup_backup.sh):
    backup_snapshot.py dump --dump FILE --manifest FILE \
        [--uploads-dir backend/uploads --uploads-archive FILE]
    backup_snapshot.py manifest --database NAME   # print a DB manifest (JSON)
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path

EXCLUDED_DATA = ("ai_generation_pins",)          # decision D9
MANIFEST_VERSION = 1


def _connect(dbname: str | None = None):
    import psycopg2
    kwargs = {"dbname": dbname} if dbname else {}
    conn = psycopg2.connect(**kwargs)
    conn.set_session(isolation_level="REPEATABLE READ", readonly=True)
    return conn


def _tables(cur) -> list[tuple[str, str]]:
    """(table, single primary-key column) for every table in public."""
    cur.execute("""
        SELECT c.relname, a.attname
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
        JOIN pg_index i ON i.indrelid = c.oid AND i.indisprimary
        JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = ANY(i.indkey)
        WHERE c.relkind = 'r'
        ORDER BY c.relname
    """)
    rows = cur.fetchall()
    seen: dict[str, list[str]] = {}
    for t, col in rows:
        seen.setdefault(t, []).append(col)
    cur.execute("""SELECT relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                   WHERE n.nspname = 'public' AND c.relkind = 'r' ORDER BY relname""")
    out = []
    for (t,) in cur.fetchall():
        pk = seen.get(t, [])
        out.append((t, pk[0] if len(pk) == 1 else ""))
    return out


def _q(ident: str) -> str:
    return '"' + ident.replace('"', '""') + '"'


def database_manifest(cur) -> dict:
    """Content fingerprint of the database visible to `cur`'s snapshot."""
    tables = {}
    for table, pk in _tables(cur):
        # Byte order (COLLATE "C"), so the hash does not depend on the server's
        # collation — a restore onto a differently configured server still matches.
        order = f'ORDER BY t.{_q(pk)}::text COLLATE "C"' if pk else 'ORDER BY md5(t::text) COLLATE "C"'
        cur.execute(f"SELECT count(*), md5(coalesce(string_agg(md5(t::text), '' {order}), '')) "
                    f"FROM {_q(table)} t")
        n, h = cur.fetchone()
        tables[table] = {"rows": n, "content_md5": h, "excluded": table in EXCLUDED_DATA}
    checks = {}
    if "chapters" in tables:
        cur.execute("SELECT count(*), md5(coalesce(string_agg(chapter_id || ':' || md5(coalesce(content, '')), "
                    "',' ORDER BY chapter_id COLLATE \"C\"), '')) FROM chapters")
        n, h = cur.fetchone()
        checks["chapter_text"] = {"chapters": n, "md5": h}
    cur.execute("""SELECT c.table_name, c.column_name FROM information_schema.columns c
                   WHERE c.table_schema = 'public' AND c.udt_name = 'vector' ORDER BY 1, 2""")
    vectors = {}
    for table, col in cur.fetchall():
        if table in EXCLUDED_DATA:
            continue
        cur.execute(f"SELECT count({_q(col)}) FROM {_q(table)}")
        vectors[f"{table}.{col}"] = cur.fetchone()[0]
    checks["embeddings_stored"] = vectors
    alembic = None
    if "alembic_version" in tables:
        cur.execute("SELECT version_num FROM alembic_version")
        row = cur.fetchone()
        alembic = row[0] if row else None
    return {"tables": tables, "checks": checks, "alembic_revision": alembic}


def archive_uploads(root: Path, archive: Path) -> dict:
    """tar.gz of every file under `root`, hashing each file from the bytes that
    go into the archive. Returns {relative path: sha256}."""
    files: dict[str, str] = {}
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "w:gz", compresslevel=6) as tar:
        if root.is_dir():
            for path in sorted(p for p in root.rglob("*") if p.is_file()):
                rel = path.relative_to(root).as_posix()
                try:
                    data = path.read_bytes()
                except OSError:
                    continue                      # removed by the TTL sweep mid-backup
                info = tarfile.TarInfo(rel)
                info.size = len(data)
                info.mtime = int(path.stat().st_mtime) if path.exists() else int(time.time())
                info.mode = 0o600
                tar.addfile(info, io.BytesIO(data))
                files[rel] = hashlib.sha256(data).hexdigest()
    os.chmod(archive, 0o600)
    return files


def referenced_files_missing(cur, uploads_root: Path) -> int:
    """Rows that point at an upload file that is not on disk (should be 0)."""
    missing = 0
    for table, col in (("ocr_uploads", "image_path"), ("audio_uploads", "audio_path")):
        try:
            cur.execute(f"SELECT {_q(col)} FROM {_q(table)} WHERE {_q(col)} IS NOT NULL")
        except Exception:                          # noqa: BLE001 — table absent on an old schema
            cur.connection.rollback()
            continue
        for (p,) in cur.fetchall():
            path = Path(p)
            if not path.is_absolute():
                path = uploads_root.parent / p     # stored relative to backend/
            if not path.exists():
                missing += 1
    return missing


def cmd_dump(args) -> int:
    started = time.monotonic()
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT pg_export_snapshot(), current_database(), now()")
        snapshot, dbname, taken_at = cur.fetchone()
        # pg_dump joins the exported snapshot while this transaction stays open.
        dump = subprocess.run(
            ["pg_dump", "--format=custom", "--compress=6", f"--file={args.dump}",
             f"--snapshot={snapshot}",
             *[f"--exclude-table-data=public.{t}" for t in EXCLUDED_DATA]],
            capture_output=True, text=True)
        if dump.returncode != 0:
            sys.stderr.write(dump.stderr)
            return 2
        os.chmod(args.dump, 0o600)
        manifest = database_manifest(cur)
        uploads_root = Path(args.uploads_dir).resolve() if args.uploads_dir else None
        missing = referenced_files_missing(cur, uploads_root) if uploads_root else None
        conn.rollback()
    finally:
        conn.close()

    uploads = None
    if args.uploads_archive and uploads_root is not None:
        uploads = {"archive": os.path.basename(args.uploads_archive),
                   "files": archive_uploads(uploads_root, Path(args.uploads_archive)),
                   "referenced_but_missing": missing}
    manifest.update({
        "manifest_version": MANIFEST_VERSION,
        "database": dbname,
        "snapshot_taken_at": taken_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dump": os.path.basename(args.dump),
        "uploads": uploads,
        "excluded_table_data": list(EXCLUDED_DATA),
        "duration_seconds": round(time.monotonic() - started, 2),
    })
    tmp = Path(args.manifest + ".tmp")
    tmp.write_text(json.dumps(manifest, indent=1, sort_keys=True))
    os.chmod(tmp, 0o600)
    tmp.replace(args.manifest)
    rows = sum(t["rows"] for t in manifest["tables"].values() if not t["excluded"])
    print(f"  Snapshot dump + manifest: {len(manifest['tables'])} tables, {rows} rows, "
          f"{len(uploads['files']) if uploads else 0} upload files "
          f"({manifest['duration_seconds']}s)")
    if missing:
        print(f"  [WARN] {missing} database row(s) point at upload files that are not on disk.")
    return 0


def cmd_manifest(args) -> int:
    conn = _connect(args.database)
    try:
        print(json.dumps(database_manifest(conn.cursor()), indent=1, sort_keys=True))
    finally:
        conn.close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="NarratIQ consistent backup snapshot")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dump")
    d.add_argument("--dump", required=True)
    d.add_argument("--manifest", required=True)
    d.add_argument("--uploads-dir")
    d.add_argument("--uploads-archive")
    m = sub.add_parser("manifest")
    m.add_argument("--database")
    args = ap.parse_args()
    return cmd_dump(args) if args.cmd == "dump" else cmd_manifest(args)


if __name__ == "__main__":
    sys.exit(main())
