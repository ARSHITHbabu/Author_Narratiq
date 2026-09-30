"""
Account and data deletion (Stage 10, task 10.6; decision S10-G — immediate
hard delete after password re-confirmation).

What "delete my account" removes:
  * every database row that belongs to the account — found by following
    foreign keys outward from the `users` row across the whole schema, so a
    table added later is covered without editing this file (the test suite
    asserts nothing is left behind). That includes all manuscript text,
    chunks and every pgvector embedding column, since those live in rows;
  * the uploaded OCR images and audio files those rows point to;
  * AI-generation pins, through the pin store as well (so a future non-DB
    pin backend is cleaned too).

Order of operations:
  1. collect the owned row ids and the file paths (read-only);
  2. delete every owned row, children before parents, and the users row,
     in ONE transaction — either the account is entirely gone or nothing is;
  3. only after the commit, remove the files. A file that cannot be removed
     is logged (by count, never by name) and retried by remove_orphan_upload_files(),
     which the hourly cleanup also runs; the author's data rows are already gone.

What it cannot remove (stated in docs/policies/data-retention-and-deletion.md):
  * copies inside database backups taken before the deletion — they age out
    with backup rotation;
  * aggregate counters that hold no account id (voice_usage_daily rows with a
    NULL user, error_events — which never hold a user id by construction).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_CHUNK = 5000
_FILE_COLUMNS = (("ocr_uploads", "image_path"), ("audio_uploads", "audio_path"))


def owned_rows(db: Session, user_id: str) -> dict[str, set]:
    """{table: primary keys} of every row belonging, directly or through a
    chain of foreign keys, to the account. Read-only."""
    from database import Base

    doomed: dict[tuple[str, str], set] = {("users", "user_id"): {user_id}}
    per_table: dict[str, set] = {}
    for table in Base.metadata.sorted_tables:
        pk_cols = list(table.primary_key.columns)
        if len(pk_cols) != 1:
            raise RuntimeError(f"account deletion does not support composite primary keys ({table.name})")
        pk = pk_cols[0]
        conds = []
        for fk in table.foreign_keys:
            ids = doomed.get((fk.column.table.name, fk.column.name))
            if ids:
                conds.extend(fk.parent.in_(chunk) for chunk in _chunks(ids))
        if table.name == "users":
            conds.append(pk == user_id)
        if not conds:
            continue
        found = {r[0] for r in db.execute(select(pk).where(or_(*conds))).all()}
        if found:
            per_table[table.name] = found
            doomed.setdefault((table.name, pk.name), set()).update(found)
    return per_table


def _chunks(ids) -> list[list]:
    ids = list(ids)
    return [ids[i:i + _CHUNK] for i in range(0, len(ids), _CHUNK)] or [[]]


def _file_paths(db: Session, per_table: dict[str, set]) -> list[str]:
    from database import Base
    paths: list[str] = []
    for table_name, column in _FILE_COLUMNS:
        ids = per_table.get(table_name)
        if not ids:
            continue
        table = Base.metadata.tables[table_name]
        pk = list(table.primary_key.columns)[0]
        for chunk in _chunks(ids):
            paths.extend(p for (p,) in db.execute(select(table.c[column]).where(pk.in_(chunk))).all() if p)
    return paths


def _remove_files(paths: list[str]) -> tuple[int, int]:
    removed = failed = 0
    for p in paths:
        try:
            if os.path.exists(p):
                os.remove(p)
            removed += 1
        except OSError:
            failed += 1
    return removed, failed


def delete_account(db: Session, user_id: str) -> dict:
    """Permanently delete the account and everything it owns. Returns counts
    only (rows per table, files). Raises on any database failure, in which
    case nothing was deleted."""
    from database import Base
    from models import AiGenerationPin
    from services.pin_store import get_pin_store

    per_table = owned_rows(db, user_id)
    if "users" not in per_table:
        raise LookupError("account not found")
    paths = _file_paths(db, per_table)

    try:
        pins = db.query(AiGenerationPin).filter(AiGenerationPin.user_id == user_id).all()
        if pins:
            get_pin_store().delete_many(pins)
        counts: dict[str, int] = {}
        for table in reversed(Base.metadata.sorted_tables):
            ids = per_table.get(table.name)
            if not ids:
                continue
            pk = list(table.primary_key.columns)[0]
            n = 0
            for chunk in _chunks(ids):
                n += db.execute(table.delete().where(pk.in_(chunk))).rowcount or 0
            counts[table.name] = n
        db.commit()
    except Exception:
        db.rollback()
        raise

    removed, failed = _remove_files(paths)
    if failed:
        logger.warning("[account_deletion] %d uploaded file(s) could not be removed yet; "
                       "the hourly orphan-file sweep will retry", failed)
    logger.info("[account_deletion] account %s deleted: %d rows in %d tables, %d files",
                user_id[:8], sum(counts.values()), len(counts), removed)
    return {"rows": counts, "files_removed": removed, "files_pending": failed}


def remove_orphan_upload_files(upload_dirs: list[str], min_age_seconds: int = 6 * 3600) -> int:
    """Delete files in the upload directories that no database row points to
    (left by a failed post-commit removal, or by a crash between a file write
    and its row). Files younger than `min_age_seconds` are left alone, so an
    upload that is still being processed is never touched. Never raises."""
    import time
    from database import SessionLocal, Base

    db = SessionLocal()
    try:
        referenced: set[str] = set()
        for table_name, column in _FILE_COLUMNS:
            col = Base.metadata.tables[table_name].c[column]
            referenced.update(os.path.abspath(p) for (p,) in db.execute(select(col).where(col.isnot(None))).all())
    except Exception as exc:                            # noqa: BLE001
        logger.warning("[orphan_files] could not read referenced paths: %s", type(exc).__name__)
        return 0
    finally:
        db.close()

    now, removed = time.time(), 0
    for d in upload_dirs:
        root = Path(d)
        if not root.is_dir():
            continue
        for f in root.iterdir():
            try:
                if (f.is_file() and os.path.abspath(f) not in referenced
                        and now - f.stat().st_mtime >= min_age_seconds):
                    f.unlink()
                    removed += 1
            except OSError:
                continue
    if removed:
        logger.info("[orphan_files] removed %d unreferenced upload file(s)", removed)
    return removed
