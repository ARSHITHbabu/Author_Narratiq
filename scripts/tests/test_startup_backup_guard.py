"""
Stage 12 Tranche 3 — the startup empty-database guard (scripts/startup_backup.sh).

The guard stops startup when the live database is empty but a backup proves
author data existed: the data may have been lost (PostgreSQL's data directory
is on the container's ephemeral disk). It used to treat ANY valid dump as that
proof, so a legitimately empty pod whose only backups were of the empty
database could not restart. scripts/backup_evidence.py now reads each set's
checksummed manifest; only a set that may hold author data counts.

Runs the REAL script against a disposable database (`narratiq_ci_verify`, on
the test allow-list), with backup sets made by the real backup_database.sh in a
temporary directory. Never touches the live database or /workspace/backups.

  A   first boot, nothing at all (no schema, no backups)          -> starts
  A2  schema present, every table empty, no backups               -> starts
  B   empty database, backups exist but all are of the empty DB   -> starts
  C   empty database, a backup holding author data exists         -> BLOCKED
  C2  ... and newer empty-DB backups exist (must not mask it)     -> BLOCKED
  C3  ... a data backup whose manifest is missing / tampered      -> BLOCKED
  C4  author data deleted on purpose, its backup still on disk    -> BLOCKED
      (indistinguishable from an accidental loss with the information stored
      today; see the Tranche 3 final addendum)
  D   database holds data                                         -> starts (guard not involved)
  E   documented override on C: exact phrase starts, '1' does not

Run:  python3 -m unittest scripts/tests/test_startup_backup_guard.py -v
"""
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import backup_evidence  # noqa: E402

DB = "narratiq_ci_verify"
TEMPLATE_DB = os.environ.get("NARRATIQ_BACKUP_TEST_TEMPLATE", "narratiq_test")
SU = shlex.split(os.environ.get("NARRATIQ_PG_SUPERUSER_CMD", "su postgres -c"))
PG = {"PGHOST": "localhost", "PGPORT": "5432", "PGUSER": "narratiq", "PGPASSWORD": "narratiq"}
URL = f"postgresql+psycopg2://narratiq:narratiq@localhost:5432/{DB}"
ACK = "yes-start-empty-intentionally"
BLOCKED = "UNEXPECTED EMPTY DATABASE"


def su(cmd: str) -> subprocess.CompletedProcess:
    return subprocess.run(SU + [cmd], capture_output=True, text=True)


def psql(sql: str) -> str:
    env = {**os.environ, **PG, "PGDATABASE": DB}
    r = subprocess.run(["psql", "-v", "ON_ERROR_STOP=1", "-Atqc", sql], env=env, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr)
    return r.stdout.strip()


def available() -> bool:
    try:
        return su(f"psql -Atqc \"select 1 from pg_database where datname='{TEMPLATE_DB}'\"").stdout.strip() == "1"
    except FileNotFoundError:
        return False


def _clean_env() -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("PG") and k not in ("NARRATIQ_ACKNOWLEDGE_EMPTY_RESTART", "DATABASE_URL")}
    env["DATABASE_URL"] = URL      # the guard's schema probe imports the backend config
    return env


@unittest.skipUnless(available(), "needs a local PostgreSQL superuser and the narratiq_test template")
class StartupGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="startup-guard-"))
        os.chmod(self.tmp, 0o777)
        self.backups = self.tmp / "backups"
        self.uploads = self.tmp / "uploads"
        self.backups.mkdir()
        (self.uploads / "ocr").mkdir(parents=True)
        os.chmod(self.backups, 0o777)
        self.env_file = self.tmp / ".env"
        self.env_file.write_text(f"DATABASE_URL={URL}\n")
        su(f"dropdb --if-exists {DB}")

    def tearDown(self):
        su(f"dropdb --if-exists {DB}")
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ── database states ───────────────────────────────────────────────────────
    def fresh_database(self):                     # what a wiped PGDATA + reinstall gives
        r = su(f"createdb -O narratiq {DB}")
        self.assertEqual(r.returncode, 0, r.stderr)
        su(f"psql -d {DB} -qc 'CREATE EXTENSION IF NOT EXISTS vector'")

    def schema_database(self):                    # schema at head, every table emptied
        r = su(f"createdb -O narratiq -T {TEMPLATE_DB} {DB}")
        if r.returncode != 0:
            raise unittest.SkipTest(f"could not clone the template: {r.stderr.strip()}")
        self.empty_rows()

    def empty_rows(self):
        tables = psql("SELECT string_agg(format('%I', tablename), ',') FROM pg_tables "
                      "WHERE schemaname='public' AND tablename <> 'alembic_version'")
        psql(f"TRUNCATE {tables} CASCADE")

    def add_author_data(self):
        uid, sid = str(uuid.uuid4()), str(uuid.uuid4())
        psql(f"INSERT INTO users (user_id, email, username, hashed_password, created_at, token_version) "
             f"VALUES ('{uid}', 'g-{uid[:8]}@narratiq-internal-test.com', 'g{uid[:8]}', 'x', now(), 0)")
        psql(f"INSERT INTO stories (story_id, user_id, title, created_at, updated_at) "
             f"VALUES ('{sid}', '{uid}', 'Guard test story', now(), now())")
        psql(f"INSERT INTO chapters (chapter_id, story_id, chapter_number, title, content, word_count, created_at, updated_at) "
             f"VALUES ('{uuid.uuid4()}', '{sid}', 1, 'One', '<p>The lamp held.</p>', 3, now(), now())")

    # ── tools ─────────────────────────────────────────────────────────────────
    def backup(self) -> Path:
        time.sleep(1.1)                           # set names have one-second resolution
        env = {**_clean_env(), "BACKUP_DIR": str(self.backups), "ENV_FILE": str(self.env_file),
               "NARRATIQ_UPLOADS_DIR": str(self.uploads)}
        r = subprocess.run(["bash", str(REPO / "scripts" / "backup_database.sh")], env=env,
                           capture_output=True, text=True, timeout=600)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return max(self.backups.glob("narratiq-2*.dump"), key=lambda p: p.stat().st_mtime)

    def start(self, ack: str | None = None) -> subprocess.CompletedProcess:
        env = {**_clean_env(), "BACKUP_DIR": str(self.backups), "ENV_FILE": str(self.env_file)}
        if ack is not None:
            env["NARRATIQ_ACKNOWLEDGE_EMPTY_RESTART"] = ack
        return subprocess.run(["bash", str(REPO / "scripts" / "startup_backup.sh")], env=env,
                              capture_output=True, text=True, timeout=600)

    def assertStarts(self, r):
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-2000:])
        self.assertNotIn(BLOCKED, r.stdout)

    def assertBlocked(self, r):
        self.assertEqual(r.returncode, 1, r.stdout[-3000:])
        self.assertIn(BLOCKED, r.stdout)

    # ── scenarios ─────────────────────────────────────────────────────────────
    def test_A_first_boot_no_schema_no_backups(self):
        self.fresh_database()
        self.assertStarts(self.start())

    def test_A2_schema_present_empty_no_backups(self):
        self.schema_database()
        self.assertStarts(self.start())

    def test_B_only_empty_database_backups(self):
        self.schema_database()
        dump = self.backup()                      # the hourly loop backing up an empty pod
        self.backup()
        self.assertFalse(backup_evidence.assess(dump)[0])
        r = self.start()
        self.assertStarts(r)
        self.assertIn("Ignored 2 backup set(s)", r.stdout)

    def test_C_backup_with_author_data_blocks(self):
        self.schema_database()
        self.add_author_data()
        dump = self.backup()
        self.assertTrue(backup_evidence.assess(dump)[0])
        su(f"dropdb {DB}")                        # PGDATA wiped: database rebuilt from nothing
        self.fresh_database()
        r = self.start()
        self.assertBlocked(r)
        self.assertIn(dump.name, r.stdout)

    def test_C2_newer_empty_backups_do_not_mask_an_older_data_backup(self):
        self.schema_database()
        self.add_author_data()
        data_dump = self.backup()
        self.empty_rows()
        self.backup()                             # loop keeps backing up after the loss
        self.backup()
        r = self.start()
        self.assertBlocked(r)
        self.assertIn(data_dump.name, r.stdout)

    def test_C3_unprovable_manifest_counts_as_evidence(self):
        self.schema_database()
        dump = self.backup()                      # genuinely empty set ...
        manifest = dump.with_name(dump.name.replace(".dump", ".manifest.json"))
        data = json.loads(manifest.read_text())
        data["note"] = "edited"                   # ... but its manifest no longer matches SHA256SUMS
        manifest.write_text(json.dumps(data))
        self.assertTrue(backup_evidence.assess(dump)[0])
        self.assertBlocked(self.start())
        manifest.unlink()                         # missing manifest: same
        self.assertBlocked(self.start())

    def test_C4_deliberate_deletion_with_data_backup_still_blocks(self):
        # The live database cannot show WHY its rows are gone: an author deleting
        # their account and an accidental or malicious delete leave the same state.
        self.schema_database()
        self.add_author_data()
        self.backup()
        self.empty_rows()
        self.assertBlocked(self.start())

    def test_D_database_with_data_starts(self):
        self.schema_database()
        self.add_author_data()
        self.backup()
        self.assertStarts(self.start())

    def test_E_override_is_exact(self):
        self.schema_database()
        self.add_author_data()
        self.backup()
        self.empty_rows()
        self.assertBlocked(self.start(ack="1"))
        self.assertBlocked(self.start(ack="true"))
        r = self.start(ack=ACK)
        self.assertStarts(r)
        self.assertIn("acknowledged via NARRATIQ_ACKNOWLEDGE_EMPTY_RESTART", r.stdout)


class EvidenceUnitTests(unittest.TestCase):
    """backup_evidence.assess on synthetic sets (no database)."""

    def make_set(self, tables: dict, chapters=0, version=1, list_manifest=True) -> Path:
        d = Path(tempfile.mkdtemp(prefix="evidence-"))
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        dump = d / "narratiq-20261003T000000Z.dump"
        dump.write_bytes(b"x")
        manifest = d / "narratiq-20261003T000000Z.manifest.json"
        manifest.write_text(json.dumps({"manifest_version": version, "tables": tables,
                                        "checks": {"chapter_text": {"chapters": chapters}}}))
        line = f"{backup_evidence._sha256(manifest)}  {manifest.name}\n" if list_manifest else ""
        (d / "narratiq-20261003T000000Z.SHA256SUMS").write_text(line)
        return dump

    def test_empty_snapshot_is_not_evidence(self):
        dump = self.make_set({"alembic_version": {"rows": 1, "excluded": False},
                              "voice_usage_daily": {"rows": 1, "excluded": False},
                              "users": {"rows": 0, "excluded": False},
                              "ai_generation_pins": {"rows": 3, "excluded": True}})
        self.assertEqual(backup_evidence.assess(dump), (False, "manifest shows 0 author rows"))

    def test_any_author_row_is_evidence(self):
        dump = self.make_set({"users": {"rows": 1, "excluded": False}})
        self.assertTrue(backup_evidence.assess(dump)[0])

    def test_unknown_format_unlisted_or_bad_counts_are_evidence(self):
        self.assertTrue(backup_evidence.assess(self.make_set({}, version=2))[0])
        self.assertTrue(backup_evidence.assess(self.make_set({}, list_manifest=False))[0])
        self.assertTrue(backup_evidence.assess(self.make_set({"users": {"rows": "?"}}))[0])
        self.assertTrue(backup_evidence.assess(self.make_set({}, chapters=2))[0])


if __name__ == "__main__":
    unittest.main()
