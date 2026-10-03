#!/usr/bin/env python3
"""
Does a backup set prove that author data existed? (startup_backup.sh empty-database guard)

The guard stops startup when the live database is empty but a valid backup
exists, because that backup proves real data was there and may have been lost.
It used to count ANY valid dump as that proof. A dump taken of an empty database
(the hourly loop backs up whatever is there) proves nothing was lost, and it
made a legitimately empty pod refuse to restart (Stage 12 Tranche 2 follow-up).

A set counts as evidence of author data unless its own integrity manifest
shows, positively, that the snapshot held none:
  * the manifest exists next to the dump, and
  * its SHA-256 matches the set's SHA256SUMS (so it belongs to this set and is
    unaltered), and
  * its format is understood (manifest_version 1), and
  * every table outside the guard's own bookkeeping exclusions
    (alembic_version, voice_usage_daily; the same list the live check uses) has
    0 rows, ignoring tables whose rows are never dumped (excluded_table_data),
    and it records 0 chapters.
Anything missing, unreadable, mismatched or unknown counts as evidence. That is
the safe direction: an unprovable set keeps the guard's protection.

  python3 scripts/backup_evidence.py /workspace/backups/narratiq-<stamp>.dump
  -> prints "author-data <reason>" (exit 0) or "no-author-data <reason>" (exit 0)
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

# Must match the exclusions in startup_backup.sh's live "holds data" probe.
BOOKKEEPING_TABLES = frozenset({"alembic_version", "voice_usage_daily"})


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def assess(dump: Path) -> tuple[bool, str]:
    """(holds_author_data, reason). True unless the manifest proves the set empty."""
    stem = dump.name[:-len(".dump")] if dump.name.endswith(".dump") else dump.name
    manifest = dump.with_name(stem + ".manifest.json")
    sums = dump.with_name(stem + ".SHA256SUMS")
    if not manifest.is_file():
        return True, "no manifest (cannot prove the set is empty)"
    if not sums.is_file():
        return True, "no SHA256SUMS (cannot verify the manifest)"
    recorded = None
    for line in sums.read_text(errors="replace").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == manifest.name:
            recorded = parts[0].lower()
    if recorded is None:
        return True, "manifest not listed in SHA256SUMS"
    if recorded != _sha256(manifest):
        return True, "manifest checksum mismatch"
    try:
        data = json.loads(manifest.read_text())
    except (OSError, ValueError):
        return True, "manifest unreadable"
    if data.get("manifest_version") != 1 or not isinstance(data.get("tables"), dict):
        return True, "unknown manifest format"
    holding = []
    for table, info in data["tables"].items():
        if table in BOOKKEEPING_TABLES or not isinstance(info, dict) or info.get("excluded"):
            continue
        rows = info.get("rows")
        if not isinstance(rows, int):
            return True, f"row count unreadable for {table}"
        if rows > 0:
            holding.append(table)
    chapters = (((data.get("checks") or {}).get("chapter_text") or {}).get("chapters"))
    if holding:
        return True, f"{len(holding)} table(s) held rows, e.g. {', '.join(sorted(holding)[:3])}"
    if chapters not in (0, None):
        return True, "manifest records chapters"
    return False, "manifest shows 0 author rows"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: backup_evidence.py <set>.dump", file=sys.stderr)
        return 2
    try:
        holds, reason = assess(Path(argv[1]))
    except Exception as exc:  # noqa: BLE001 — any failure keeps the protection
        holds, reason = True, f"assessment failed: {type(exc).__name__}"
    print(("author-data " if holds else "no-author-data ") + reason)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
