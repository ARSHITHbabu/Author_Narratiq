"""
OD-05 (owner decision 2026-10-06, option B) — the operator `.disposable` marker
per backup set, for the startup empty-database guard (scripts/startup_backup.sh,
scripts/backup_evidence.py).

A set holding author data stops counting as evidence of lost data ONLY when an
operator has marked that one set with `backup_evidence.py mark-disposable`, and
the marker still matches the set's dump checksum. Everything else keeps the
protection.

Database scenarios (real scripts, disposable database `narratiq_ci_verify`,
backup sets in a temporary directory; never the live database or
/workspace/backups) — reuse StartupGuardTests' fixtures:
  F   the only data set is marked disposable                      -> starts
  F2  newest data set marked, an OLDER unmarked data set remains  -> BLOCKED on the older one
  F3  older data set marked, a NEWER unmarked data set remains    -> BLOCKED on the newer one
  F4  marker whose checksum no longer matches (dump replaced)     -> BLOCKED, loud warning
  F5  the block message offers the marker for disposable data only
  F6  backup + start never create a marker

Unit tests (no database): marker validation, the mark-disposable CLI refusals,
retention treatment, and a static scan that nothing outside the operator
command writes markers.

Run:  python3 -m unittest scripts/tests/test_disposable_marker.py -v
"""
import ast
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import backup_evidence  # noqa: E402
import backup_retention  # noqa: E402
import test_startup_backup_guard as guard  # noqa: E402  (module import: its classes must not be collected twice)

EVIDENCE = REPO / "scripts" / "backup_evidence.py"
REASON = "disposable guard-test author deleted on purpose"


def mark(dump: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(EVIDENCE), "mark-disposable", str(dump), *extra],
                          capture_output=True, text=True)


def mark_ok(test: unittest.TestCase, dump: Path) -> Path:
    r = mark(dump, "--reason", REASON, "--operator", "guard-test")
    test.assertEqual(r.returncode, 0, r.stdout + r.stderr)
    return backup_evidence.marker_path(dump)


@unittest.skipUnless(guard.available(), "needs a local PostgreSQL superuser and the narratiq_test template")
class DisposableMarkerGuardTests(guard.StartupGuardTests):
    # Re-running the inherited scenarios here would only repeat them.
    test_A_first_boot_no_schema_no_backups = None
    test_A2_schema_present_empty_no_backups = None
    test_B_only_empty_database_backups = None
    test_C_backup_with_author_data_blocks = None
    test_C2_newer_empty_backups_do_not_mask_an_older_data_backup = None
    test_C3_unprovable_manifest_counts_as_evidence = None
    test_C4_deliberate_deletion_with_data_backup_still_blocks = None
    test_D_database_with_data_starts = None
    test_E_override_is_exact = None

    def data_sets(self, n: int) -> list:
        self.schema_database()
        self.add_author_data()
        dumps = [self.backup() for _ in range(n)]
        self.empty_rows()                         # the disposable author is deleted
        return dumps                              # oldest first

    def test_F_marked_data_set_no_longer_blocks(self):
        (dump,) = self.data_sets(1)
        self.assertBlocked(self.start())
        mark_ok(self, dump)
        r = self.start()
        self.assertStarts(r)
        self.assertIn("Ignored 1 backup set(s) an operator marked DISPOSABLE", r.stdout)
        self.assertIn("guard-test", r.stdout)

    def test_F2_older_unmarked_data_set_is_not_masked_by_a_newer_marked_one(self):
        older, newer = self.data_sets(2)
        mark_ok(self, newer)
        r = self.start()
        self.assertBlocked(r)
        self.assertIn(f"Newest backup holding author data: {older.name}", r.stdout)

    def test_F3_partial_marking_still_blocks(self):
        older, newer = self.data_sets(2)
        mark_ok(self, older)
        r = self.start()
        self.assertBlocked(r)
        self.assertIn(f"Newest backup holding author data: {newer.name}", r.stdout)
        mark_ok(self, newer)                      # every data set marked -> starts
        self.assertStarts(self.start())

    def test_F4_marker_for_a_replaced_dump_is_ignored_loudly(self):
        (dump,) = self.data_sets(1)
        mark_ok(self, dump)
        other = self.backup()                     # a different (empty-database) dump ...
        shutil.copyfile(other, dump)              # ... swapped in under the marked name,
        Path(f"{dump}.sha256").write_text(        # with a matching checksum file
            f"{backup_evidence._sha256(dump)}  {dump.name}\n")
        r = self.start()
        self.assertBlocked(r)
        self.assertIn("DISPOSABLE MARKER IGNORED", r.stdout)
        self.assertIn("checksum mismatch", r.stdout)

    def test_F5_block_message_offers_the_marker_for_disposable_data_only(self):
        self.data_sets(1)
        r = self.start()
        self.assertBlocked(r)
        self.assertIn("backup_evidence.py mark-disposable", r.stdout)
        self.assertIn("NEVER mark a set that holds real author data", r.stdout)

    def test_F6_backup_and_start_never_create_markers(self):
        self.data_sets(2)
        self.start()
        self.start(ack=guard.ACK)
        self.assertEqual(list(self.backups.glob("*" + backup_evidence.MARKER_SUFFIX)), [])


class MarkerUnitTests(unittest.TestCase):
    """Synthetic sets, no database."""

    def make_set(self, rows=1, stamp="20261003T000000Z", d: Path | None = None) -> Path:
        if d is None:
            d = Path(tempfile.mkdtemp(prefix="disposable-"))
            self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        dump = d / f"narratiq-{stamp}.dump"
        dump.write_bytes(f"dump {stamp} {rows}".encode())
        manifest = d / f"narratiq-{stamp}.manifest.json"
        manifest.write_text(json.dumps({"manifest_version": 1, "tables": {"users": {"rows": rows, "excluded": False}},
                                        "checks": {"chapter_text": {"chapters": rows}}}))
        sha = backup_evidence._sha256
        Path(f"{dump}.sha256").write_text(f"{sha(dump)}  {dump.name}\n")
        (d / f"narratiq-{stamp}.SHA256SUMS").write_text(f"{sha(dump)}  {dump.name}\n{sha(manifest)}  {manifest.name}\n")
        return dump

    def test_marker_is_honoured_and_records_who_when_why(self):
        dump = self.make_set()
        self.assertEqual(backup_evidence.verdict(dump)[0], "author-data")
        r = mark(dump, "--reason", REASON, "--operator", "ops-alice")
        self.assertEqual(r.returncode, 0, r.stderr)
        sha = backup_evidence._sha256(dump)
        for text in (dump.name[:-5], sha, "ops-alice", REASON, str(backup_evidence.marker_path(dump))):
            self.assertIn(text, r.stdout)
        data = json.loads(backup_evidence.marker_path(dump).read_text())
        self.assertEqual((data["set"], data["dump"], data["dump_sha256"], data["operator"], data["reason"]),
                         (dump.name[:-5], dump.name, sha, "ops-alice", REASON))
        datetime.strptime(data["marked_at"], "%Y-%m-%dT%H:%M:%SZ")
        label, why = backup_evidence.verdict(dump)
        self.assertEqual(label, "disposable")
        self.assertIn("ops-alice", why)
        out = subprocess.run([sys.executable, str(EVIDENCE), str(dump)], capture_output=True, text=True).stdout
        self.assertTrue(out.startswith("disposable "), out)

    def test_set_name_resolves_against_backup_dir(self):
        dump = self.make_set()
        r = mark(Path(dump.name[:-5]), "--reason", REASON, "--operator", "ops", "--backup-dir", str(dump.parent))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(backup_evidence.verdict(dump)[0], "disposable")

    def test_cli_refuses_without_reason_or_operator(self):
        dump = self.make_set()
        for extra in ([], ["--reason", REASON], ["--operator", "ops"], ["--reason", REASON, "--operator", "  "],
                      ["--reason", "  ", "--operator", "ops"], ["--reason", "test", "--operator", "ops"]):
            r = mark(dump, *extra)
            self.assertEqual(r.returncode, 2, extra)
            self.assertIn("REFUSED", r.stderr)
            self.assertFalse(backup_evidence.marker_path(dump).exists(), extra)
        self.assertEqual(backup_evidence.verdict(dump)[0], "author-data")

    def test_cli_refuses_damaged_unbound_empty_or_already_marked_sets(self):
        dump = self.make_set()
        dump.write_bytes(b"replaced")                         # no longer matches .dump.sha256
        self.assertEqual(mark(dump, "--reason", REASON, "--operator", "ops").returncode, 2)
        dump = self.make_set(stamp="20261003T010000Z")
        Path(f"{dump}.sha256").unlink()                       # nothing to bind to
        self.assertEqual(mark(dump, "--reason", REASON, "--operator", "ops").returncode, 2)
        empty = self.make_set(rows=0, stamp="20261003T020000Z")   # proven empty: needs no marker
        r = mark(empty, "--reason", REASON, "--operator", "ops")
        self.assertEqual(r.returncode, 2)
        self.assertIn("needs no marker", r.stderr)
        dump = self.make_set(stamp="20261003T030000Z")
        mark_ok(self, dump)
        before = backup_evidence.marker_path(dump).read_text()
        self.assertEqual(mark(dump, "--reason", REASON + " again", "--operator", "other").returncode, 2)
        self.assertEqual(backup_evidence.marker_path(dump).read_text(), before)   # never overwritten
        for d in (dump.parent,):
            self.assertEqual(len(list(d.glob("*.disposable"))), 1)

    def test_marker_with_wrong_checksum_is_ignored_loudly(self):
        dump = self.make_set()
        marker = mark_ok(self, dump)
        data = json.loads(marker.read_text())
        data["dump_sha256"] = "0" * 64
        marker.write_text(json.dumps(data))
        label, why = backup_evidence.verdict(dump)
        self.assertEqual(label, "author-data")
        self.assertIn("DISPOSABLE MARKER IGNORED", why)
        self.assertIn("checksum mismatch", why)

    def test_marker_does_not_follow_a_replaced_dump(self):
        dump = self.make_set()
        mark_ok(self, dump)
        dump.write_bytes(b"a different archive")                 # replaced, checksum files left
        self.assertEqual(backup_evidence.verdict(dump)[0], "author-data")
        sha = backup_evidence._sha256(dump)                      # ... and checksum files rewritten too
        Path(f"{dump}.sha256").write_text(f"{sha}  {dump.name}\n")
        label, why = backup_evidence.verdict(dump)
        self.assertEqual(label, "author-data")
        self.assertIn("DISPOSABLE MARKER IGNORED", why)

    def test_marker_copied_to_another_set_or_hand_written_is_ignored(self):
        a = self.make_set()
        b = self.make_set(stamp="20261003T010000Z", d=a.parent)
        shutil.copyfile(mark_ok(self, a), backup_evidence.marker_path(b))
        self.assertIn("DISPOSABLE MARKER IGNORED", backup_evidence.verdict(b)[1])
        c = self.make_set(stamp="20261003T020000Z", d=a.parent)
        backup_evidence.marker_path(c).write_text("")            # `touch` like a .keep marker
        self.assertIn("DISPOSABLE MARKER IGNORED", backup_evidence.verdict(c)[1])
        self.assertEqual(backup_evidence.verdict(a)[0], "disposable")

    def test_retention_unchanged_marker_removed_with_its_set(self):
        d = Path(tempfile.mkdtemp(prefix="disposable-retention-"))
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        old = self.make_set(stamp="20200101T000000Z", d=d)
        self.make_set(stamp="20200102T000000Z", d=d)
        mark_ok(self, old)
        now = datetime(2020, 1, 2, 12, tzinfo=timezone.utc)
        p = backup_retention.plan(d, keep_recent=1, keep_daily_days=1, now=now)
        self.assertEqual(p["delete"], ["20200101T000000Z"])      # a marked set is not kept by its marker
        self.assertIn(backup_evidence.marker_path(old), backup_retention.set_files(d, "20200101T000000Z"))

    def test_nothing_outside_the_operator_command_creates_markers(self):
        # Only backup_evidence.py's mark-disposable writes a marker. Any other code that
        # mentions the marker or the command (start script, backup loop, retention,
        # verifier, backend) must only read or delete it, never create it.
        allowed = {REPO / "scripts" / "backup_evidence.py", REPO / "scripts" / "backup_retention.py",
                   REPO / "scripts" / "startup_backup.sh"}
        offenders = []
        for path in list(REPO.glob("*.sh")) + list((REPO / "scripts").glob("*.sh")) + \
                list((REPO / "scripts").glob("*.py")) + list((REPO / "backend").rglob("*.py")):
            if path in allowed or "tests" in path.parts or "node_modules" in path.parts or "venv" in path.parts:
                continue
            text = path.read_text(errors="replace")
            if ".disposable" in text or "mark-disposable" in text or "mark_disposable" in text:
                offenders.append(str(path.relative_to(REPO)))
        self.assertEqual(offenders, [])
        # The start script may mention the command only in comments and in the text it
        # prints for the operator, never run it.
        sh = REPO / "scripts" / "startup_backup.sh"
        code = "\n".join(l for l in sh.read_text().splitlines()
                         if not l.lstrip().startswith(("#", "echo ", "log ", "warn ")))
        self.assertIsNone(re.search(r"mark-disposable|mark_disposable|\.disposable", code))
        # Retention only lists the marker among a set's files (to delete it with the set).
        tree = ast.parse((REPO / "scripts" / "backup_retention.py").read_text())
        docstring = ast.get_docstring(tree, clean=False)
        texts = [n.value for n in ast.walk(tree)          # includes the literal parts of f-strings
                 if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value != docstring]
        self.assertEqual([t for t in texts if "disposable" in t], [".disposable"])
        self.assertNotIn("backup_evidence", (REPO / "scripts" / "backup_retention.py").read_text()
                         .replace(docstring, ""))


if __name__ == "__main__":
    unittest.main()
