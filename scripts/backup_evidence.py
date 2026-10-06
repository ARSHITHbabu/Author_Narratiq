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

Operator `.disposable` marker (owner decision OD-05, option B, 2026-10-06)
--------------------------------------------------------------------------
A set that holds author data can be taken out of the evidence ONLY by an
operator who deliberately marks it as disposable test data that was deleted on
purpose. The marker sits next to the set, like the retention `.keep` marker:
    narratiq-<stamp>.disposable
It is created by this script's `mark-disposable` command, never by hand and
never by any automatic path (start script, backup loop, retention). It is a
JSON record of who marked the set, when and why, bound to the set's identity:
its name and the SHA-256 of its dump. It is honoured only if ALL of these hold:
  * it parses, is marker_version 1, names this set and this dump file, and
    carries a non-empty operator and reason;
  * its dump_sha256 equals the set's recorded checksum (<stamp>.dump.sha256),
    equals the dump's entry in SHA256SUMS when one is listed, and equals the
    SHA-256 of the dump file on disk right now.
Anything else: the marker is IGNORED, the set still counts as evidence, and the
verdict says so loudly ("DISPOSABLE MARKER IGNORED"). A marker therefore cannot
silently apply to a different, replaced or rewritten dump. Marking never hides
another set: the guard still considers every other set, and the newest
unmarked set that holds author data still blocks startup.

Marking a set that holds REAL author data is forbidden: real data that is
missing must be restored (docs/operations/backup-and-restore.md §4, §4a).

  python3 scripts/backup_evidence.py /workspace/backups/narratiq-<stamp>.dump
  -> prints one line, exit 0:
       "author-data <reason>"        counts as evidence of lost author data
       "no-author-data <reason>"     manifest proves the snapshot empty
       "disposable <reason>"         held author data, operator-marked disposable

  python3 scripts/backup_evidence.py mark-disposable narratiq-<stamp> \
      --reason "why this data was deliberately deleted" --operator NAME [--backup-dir DIR]
  -> writes narratiq-<stamp>.disposable and prints exactly what it marked.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Must match the exclusions in startup_backup.sh's live "holds data" probe.
BOOKKEEPING_TABLES = frozenset({"alembic_version", "voice_usage_daily"})

MARKER_SUFFIX = ".disposable"
MARKER_VERSION = 1
DUMP_NAME = re.compile(r"^narratiq-\d{8}T\d{6}Z(?:-\d+)?\.dump$")
MIN_REASON_CHARS = 10


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _stem(dump: Path) -> str:
    return dump.name[:-len(".dump")] if dump.name.endswith(".dump") else dump.name


def marker_path(dump: Path) -> Path:
    return dump.with_name(_stem(dump) + MARKER_SUFFIX)


def _one_line(text: str) -> str:
    return " ".join(str(text).split())


def assess(dump: Path) -> tuple[bool, str]:
    """(holds_author_data, reason). True unless the manifest proves the set empty."""
    stem = _stem(dump)
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


def _recorded_dump_sha(dump: Path) -> str | None:
    """The dump's checksum as recorded in <stamp>.dump.sha256 (None if absent/unreadable)."""
    try:
        parts = Path(str(dump) + ".sha256").read_text(errors="replace").split()
    except OSError:
        return None
    if len(parts) >= 2 and parts[1].lstrip("*") == dump.name and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
        return parts[0].lower()
    return None


def _sums_dump_sha(dump: Path) -> str | None:
    """The dump's entry in <stamp>.SHA256SUMS, if the set lists it."""
    try:
        text = dump.with_name(_stem(dump) + ".SHA256SUMS").read_text(errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == dump.name:
            return parts[0].lower()
    return None


def check_marker(dump: Path) -> tuple[str, str]:
    """('none'|'valid'|'invalid', detail) for this set's .disposable marker."""
    marker = marker_path(dump)
    if not marker.exists():
        return "none", ""
    try:
        data = json.loads(marker.read_text())
    except (OSError, ValueError):
        return "invalid", "marker unreadable (not the JSON written by mark-disposable)"
    if not isinstance(data, dict) or data.get("marker_version") != MARKER_VERSION:
        return "invalid", "unknown marker format"
    if data.get("set") != _stem(dump) or data.get("dump") != dump.name:
        return "invalid", f"marker names a different set ({_one_line(data.get('set'))!s})"
    operator, reason = data.get("operator"), data.get("reason")
    if not (isinstance(operator, str) and operator.strip() and isinstance(reason, str) and reason.strip()):
        return "invalid", "marker has no operator or reason"
    want = str(data.get("dump_sha256", "")).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", want):
        return "invalid", "marker has no dump checksum"
    recorded = _recorded_dump_sha(dump)
    if recorded is None:
        return "invalid", "set has no readable .dump.sha256 to bind the marker to"
    if recorded != want:
        return "invalid", "checksum mismatch: marker does not match the set's recorded .dump.sha256"
    listed = _sums_dump_sha(dump)
    if listed is not None and listed != want:
        return "invalid", "checksum mismatch: marker does not match the dump's SHA256SUMS entry"
    if _sha256(dump) != want:
        return "invalid", "checksum mismatch: the dump on disk is not the file that was marked"
    return "valid", (f"marked by {_one_line(operator)} at {_one_line(data.get('marked_at', '?'))}: "
                     f"{_one_line(reason)}")


def verdict(dump: Path) -> tuple[str, str]:
    """('author-data'|'no-author-data'|'disposable', reason) — what the guard acts on."""
    holds, reason = assess(dump)
    if not holds:
        return "no-author-data", reason
    state, detail = check_marker(dump)
    if state == "valid":
        return "disposable", f"operator-marked disposable, {detail} (set held author data: {reason})"
    if state == "invalid":
        return "author-data", f"{reason}; DISPOSABLE MARKER IGNORED ({detail}) — {marker_path(dump).name}"
    return "author-data", reason


# ── mark-disposable (operator command) ────────────────────────────────────────
def _refuse(msg: str) -> int:
    print(f"REFUSED: {msg}", file=sys.stderr)
    print("Nothing was marked.", file=sys.stderr)
    return 2


def _resolve_set(name: str, backup_dir: Path) -> Path:
    p = Path(name)
    if p.suffix != ".dump":
        p = p.with_name(p.name + ".dump")
    if not p.is_absolute() and len(p.parts) == 1:
        p = backup_dir / p
    return p


def mark_disposable(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        prog="backup_evidence.py mark-disposable",
        description="Mark ONE backup set as disposable test data that was deliberately deleted, so the "
                    "startup empty-database guard no longer treats it as evidence of lost author data. "
                    "Never mark a set holding real author data: restore it instead.")
    ap.add_argument("set", help="narratiq-<stamp> or the path to narratiq-<stamp>.dump")
    ap.add_argument("--reason", help=f"why this data was deleted on purpose (at least {MIN_REASON_CHARS} characters)")
    ap.add_argument("--operator", help="who is making this decision")
    ap.add_argument("--backup-dir", default=os.environ.get("BACKUP_DIR", "/workspace/backups"))
    args = ap.parse_args(argv)

    operator = _one_line(args.operator or "")
    reason = _one_line(args.reason or "")
    if not operator:
        return _refuse("--operator NAME is required (who is deciding this data was disposable).")
    if len(reason) < MIN_REASON_CHARS:
        return _refuse(f"--reason is required and must say why the data was deleted on purpose "
                       f"(at least {MIN_REASON_CHARS} characters).")

    dump = _resolve_set(args.set, Path(args.backup_dir))
    if not DUMP_NAME.match(dump.name):
        return _refuse(f"{dump.name} is not a backup set dump (narratiq-<stamp>.dump).")
    if not dump.is_file():
        return _refuse(f"no such backup set: {dump}")
    marker = marker_path(dump)
    if marker.exists():
        return _refuse(f"{marker.name} already exists. Inspect it; delete it first if it must be re-made.")
    recorded = _recorded_dump_sha(dump)
    if recorded is None:
        return _refuse(f"{dump.name}.sha256 is missing or unreadable: the set's identity cannot be bound.")
    actual = _sha256(dump)
    if actual != recorded:
        return _refuse(f"{dump.name} does not match its recorded checksum: the set is damaged or replaced.")
    listed = _sums_dump_sha(dump)
    if listed is not None and listed != actual:
        return _refuse(f"{dump.name} does not match its SHA256SUMS entry: the set is damaged or replaced.")
    holds, why = assess(dump)
    if not holds:
        return _refuse(f"{dump.name} is not evidence of author data ({why}); it needs no marker.")

    record = {
        "marker_version": MARKER_VERSION,
        "set": _stem(dump),
        "dump": dump.name,
        "dump_sha256": actual,
        "operator": operator,
        "reason": reason,
        "marked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "evidence_at_marking": why,
        "meaning": "Operator decision (OD-05 option B): this set's author data was disposable test data "
                   "deleted on purpose; it is not evidence of data loss. Bound to dump_sha256.",
    }
    fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump(record, fh, indent=2)
        fh.write("\n")

    print("Marked backup set as DISPOSABLE (not evidence of lost author data):")
    print(f"  Set:        {record['set']}")
    print(f"  Dump:       {dump}")
    print(f"  SHA-256:    {actual}")
    print(f"  Held:       {why}")
    print(f"  Operator:   {operator}")
    print(f"  Reason:     {reason}")
    print(f"  Marked at:  {record['marked_at']} (UTC)")
    print(f"  Marker:     {marker}")
    print("This marker applies to this one set only. Every other set is still checked by the startup guard.")
    print(f"If this was a mistake, delete the marker now: rm {marker}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[1] == "mark-disposable":
        return mark_disposable(argv[2:])
    if len(argv) != 2 or argv[1].startswith("-"):
        print("usage: backup_evidence.py <set>.dump\n"
              "       backup_evidence.py mark-disposable <set> --reason TEXT --operator NAME [--backup-dir DIR]",
              file=sys.stderr)
        return 2
    try:
        label, reason = verdict(Path(argv[1]))
    except Exception as exc:  # noqa: BLE001 — any failure keeps the protection
        label, reason = "author-data", f"assessment failed: {type(exc).__name__}"
    print(f"{label} {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
