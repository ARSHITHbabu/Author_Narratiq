#!/usr/bin/env python3
"""
Backup retention and rotation (Stage 10, task 10.1).

Policy (grandfather–father–son, on-pod):
  * keep the newest KEEP_RECENT backup sets (default 24 — one day at the
    hourly cadence);
  * additionally keep the newest set of each UTC day for KEEP_DAILY_DAYS days
    (default 7);
  * never delete: a set with a `<stem>.keep` marker file, or the newest set
    that passed automated restore verification (LAST-VERIFY.json);
  * never delete anything that is not a recognised backup artefact.
  * a `<stem>.disposable` marker (OD-05; backup_evidence.py mark-disposable)
    does NOT keep a set: a marked set is rotated like any other and its marker
    is deleted with it (decided 2026-10-06; backup-and-restore.md §2).

This bounds the "deleted data persists in backups" window stated in the data
policy (docs/policies/data-retention-and-deletion.md): at most KEEP_DAILY_DAYS
days, plus the time until the next daily set.

A "set" is every file sharing one stamp:
  narratiq-<stamp>.dump(.sha256)  narratiq-<stamp>.manifest.json
  narratiq-<stamp>.SHA256SUMS     narratiq-globals-<stamp>.sql(.sha256)
  narratiq-uploads-<stamp>.tar.gz

Dry run by default; pass --apply to delete.
    backup_retention.py [--backup-dir DIR] [--keep-recent N] [--keep-daily-days D] [--apply]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

STAMP = re.compile(r"^narratiq-(\d{8}T\d{6}Z(?:-\d+)?)\.dump$")


def _stamp_time(stamp: str) -> datetime:
    return datetime.strptime(stamp[:16], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)


def set_files(backup_dir: Path, stamp: str) -> list[Path]:
    names = [f"narratiq-{stamp}.dump", f"narratiq-{stamp}.dump.sha256", f"narratiq-{stamp}.manifest.json",
             f"narratiq-{stamp}.SHA256SUMS", f"narratiq-globals-{stamp}.sql",
             f"narratiq-globals-{stamp}.sql.sha256", f"narratiq-uploads-{stamp}.tar.gz",
             # An operator .disposable marker (OD-05) belongs to its set: it does not keep
             # the set, and it goes when the set goes (it could never match another set).
             f"narratiq-{stamp}.disposable"]
    return [backup_dir / n for n in names if (backup_dir / n).exists()]


def plan(backup_dir: Path, keep_recent: int, keep_daily_days: int, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    stamps = sorted((m.group(1) for p in backup_dir.iterdir() if (m := STAMP.match(p.name))),
                    key=_stamp_time, reverse=True)
    keep: dict[str, str] = {}
    for s in stamps[:keep_recent]:
        keep[s] = "recent"
    cutoff = now - timedelta(days=keep_daily_days)
    seen_days: set[str] = set()
    for s in stamps:                                    # newest first
        t = _stamp_time(s)
        day = t.strftime("%Y-%m-%d")
        if t >= cutoff and day not in seen_days:
            seen_days.add(day)
            keep.setdefault(s, "daily")
    for s in stamps:
        if (backup_dir / f"narratiq-{s}.keep").exists():
            keep[s] = "keep-marker"
    try:
        last = json.loads((backup_dir / "LAST-VERIFY.json").read_text())
        if last.get("result") == "PASS":
            verified = str(last.get("backup_set", ""))[len("narratiq-"):]
            if verified in stamps:
                keep[verified] = "last-verified"
    except (OSError, ValueError):
        pass
    delete = [s for s in stamps if s not in keep]
    return {"keep": keep, "delete": delete, "total": len(stamps)}


def main() -> int:
    ap = argparse.ArgumentParser(description="Rotate NarratIQ on-pod backups")
    ap.add_argument("--backup-dir", default=os.environ.get("BACKUP_DIR", "/workspace/backups"))
    ap.add_argument("--keep-recent", type=int,
                    default=int(os.environ.get("NARRATIQ_BACKUP_KEEP_RECENT", 24)))
    ap.add_argument("--keep-daily-days", type=int,
                    default=int(os.environ.get("NARRATIQ_BACKUP_KEEP_DAILY_DAYS", 7)))
    ap.add_argument("--apply", action="store_true", help="actually delete (default: dry run)")
    args = ap.parse_args()
    if args.keep_recent < 1 or args.keep_daily_days < 1:
        print("keep-recent and keep-daily-days must be at least 1", file=sys.stderr)
        return 2
    d = Path(args.backup_dir)
    if not d.is_dir():
        print(f"no backup directory at {d}", file=sys.stderr)
        return 2
    p = plan(d, args.keep_recent, args.keep_daily_days)
    for s in p["delete"]:
        files = set_files(d, s)
        verb = "Deleting" if args.apply else "Would delete"
        print(f"  {verb} backup set {s} ({len(files)} files)")
        if args.apply:
            for f in files:
                f.unlink(missing_ok=True)
    print(f"  Retention: {p['total']} sets, keeping {len(p['keep'])}, "
          f"{'deleted' if args.apply else 'would delete'} {len(p['delete'])} "
          f"(recent={args.keep_recent}, daily={args.keep_daily_days}d)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
