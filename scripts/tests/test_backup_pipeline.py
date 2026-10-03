"""
End-to-end test of the Stage 10 backup pipeline (task 10.1):
backup_database.sh → verify_backup.py (real restore) → backup_retention.py.

Uses a disposable source database, `narratiq_ci_verify` (on the project's
test-database allow-list, tests/db_safety_guard.py), cloned from the schema of
`narratiq_test` and filled with synthetic rows — never the live database.
Needs a local PostgreSQL superuser path (NARRATIQ_PG_SUPERUSER_CMD, default
`su postgres -c`); skips cleanly when that or the template is unavailable.

What it proves:
  * a backup set restores and verifies PASS, by content hash — chapters,
    chunks WITH their vectors, notes — and every upload file's SHA-256;
  * decision D9: pin rows are not in the dump and restore empty;
  * tampering is caught: altered table content, a changed upload file, and a
    corrupted archive all make verification FAIL;
  * retention keeps recent + daily sets, the .keep marker and the last verified set.

Run:  python3 -m unittest scripts/tests/test_backup_pipeline.py -v
"""
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import backup_retention  # noqa: E402

SOURCE_DB = "narratiq_ci_verify"
TEMPLATE_DB = os.environ.get("NARRATIQ_BACKUP_TEST_TEMPLATE", "narratiq_test")
SU = shlex.split(os.environ.get("NARRATIQ_PG_SUPERUSER_CMD", "su postgres -c"))
PG = {"PGHOST": "localhost", "PGPORT": "5432", "PGUSER": "narratiq", "PGPASSWORD": "narratiq"}


def su(cmd: str) -> subprocess.CompletedProcess:
    return subprocess.run(SU + [cmd], capture_output=True, text=True)


def psql(sql: str, db: str = SOURCE_DB) -> str:
    env = {**os.environ, **PG, "PGDATABASE": db}
    r = subprocess.run(["psql", "-v", "ON_ERROR_STOP=1", "-Atqc", sql], env=env, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr)
    return r.stdout.strip()


def available() -> bool:
    try:
        return su(f"psql -Atqc \"select 1 from pg_database where datname='{TEMPLATE_DB}'\"").stdout.strip() == "1"
    except FileNotFoundError:
        return False


@unittest.skipUnless(available(), "needs a local PostgreSQL superuser and the narratiq_test template")
class BackupPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="backup-pipeline-"))
        os.chmod(cls.tmp, 0o755)
        cls.backups = cls.tmp / "backups"
        cls.uploads = cls.tmp / "uploads"
        (cls.uploads / "ocr").mkdir(parents=True)
        (cls.uploads / "audio").mkdir(parents=True)
        for d in (cls.tmp, cls.backups):
            d.mkdir(exist_ok=True)
            os.chmod(d, 0o777)          # the postgres OS user must read the dump
        su(f"dropdb --if-exists {SOURCE_DB}")
        r = su(f"createdb -O narratiq -T {TEMPLATE_DB} {SOURCE_DB}")
        if r.returncode != 0:
            raise unittest.SkipTest(f"could not clone the template: {r.stderr.strip()}")
        # createdb -T copies the template's ROWS too. Only its schema is wanted:
        # rows other suites left in narratiq_test (e.g. an audio upload from the
        # live audio spec) reference files this test's uploads dir does not hold.
        tables = psql("SELECT string_agg(format('%I', tablename), ',') FROM pg_tables "
                      "WHERE schemaname='public' AND tablename <> 'alembic_version'")
        psql(f"TRUNCATE {tables} CASCADE")
        cls._seed()
        cls.env_file = cls.tmp / ".env"
        cls.env_file.write_text(f"DATABASE_URL=postgresql+psycopg2://narratiq:narratiq@localhost:5432/{SOURCE_DB}\n")

    @classmethod
    def tearDownClass(cls):
        su(f"dropdb --if-exists {SOURCE_DB}")
        su("dropdb --if-exists narratiq_restorecheck")
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def _seed(cls):
        uid, sid = str(uuid.uuid4()), str(uuid.uuid4())
        vec = "[" + ",".join(["0.0123"] * 1024) + "]"
        img = cls.uploads / "ocr" / "page-1.png"
        img.write_bytes(os.urandom(4096))
        (cls.uploads / "audio" / "clip.webm").write_bytes(os.urandom(2048))
        cls.uid, cls.sid = uid, sid
        stmts = [
            f"INSERT INTO users (user_id, email, username, hashed_password, created_at, token_version) "
            f"VALUES ('{uid}', 'b-{uid[:8]}@narratiq-internal-test.com', 'b{uid[:8]}', 'x', now(), 0)",
            f"INSERT INTO stories (story_id, user_id, title, created_at, updated_at) "
            f"VALUES ('{sid}', '{uid}', 'Backup test story', now(), now())",
        ]
        for n in (1, 2, 3):
            cid = str(uuid.uuid4())
            stmts += [
                f"INSERT INTO chapters (chapter_id, story_id, chapter_number, title, content, word_count, created_at, updated_at) "
                f"VALUES ('{cid}', '{sid}', {n}, 'Chapter {n}', '<p>Chapter {n}: the lamp guttered, and Mara counted the doors.</p>', 10, now(), now())",
                f"INSERT INTO chapter_chunks (chunk_id, chapter_id, story_id, chapter_number, chunk_index, text, embedding) "
                f"VALUES ('{uuid.uuid4()}', '{cid}', '{sid}', {n}, 0, 'chunk {n}', '{vec}')",
            ]
        stmts += [
            f"INSERT INTO ocr_uploads (upload_id, story_id, user_id, image_path, raw_ocr_text, cleaned_text, confirmed, created_at) "
            f"VALUES ('{uuid.uuid4()}', '{sid}', '{uid}', '{img}', 'raw', 'clean', false, now())",
            f"INSERT INTO ai_generation_pins (pin_id, user_id, story_id, tool, scope, content, content_sha256, expires_at, created_at) "
            f"VALUES ('{uuid.uuid4()}', '{uid}', '{sid}', 'tone', 'selection', 'draft', 'h', now() + interval '7 days', now())",
        ]
        for s in stmts:
            psql(s)

    def backup(self) -> str:
        env = {**{k: v for k, v in os.environ.items() if not k.startswith("PG")},
               "BACKUP_DIR": str(self.backups), "ENV_FILE": str(self.env_file),
               "NARRATIQ_UPLOADS_DIR": str(self.uploads)}
        r = subprocess.run(["bash", str(REPO / "scripts" / "backup_database.sh")], env=env,
                           capture_output=True, text=True, timeout=600)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        sums = sorted(self.backups.glob("narratiq-2*.SHA256SUMS"), key=lambda p: p.stat().st_mtime)
        return sums[-1].name[: -len(".SHA256SUMS")]

    def verify(self, stem: str) -> dict:
        env = {**os.environ, **PG, "PGDATABASE": SOURCE_DB}
        r = subprocess.run([sys.executable, str(REPO / "scripts" / "verify_backup.py"),
                            "--backup-dir", str(self.backups), "--set", stem],
                           env=env, capture_output=True, text=True, timeout=900)
        result = json.loads((self.backups / "LAST-VERIFY.json").read_text())
        self.assertEqual(r.returncode, 0 if result["result"] == "PASS" else 1, r.stderr)
        return result

    def test_1_backup_set_restores_and_verifies_by_content(self):
        stem = self.backup()
        manifest = json.loads((self.backups / f"{stem}.manifest.json").read_text())
        # The template may already hold fixture data, so compare with the source itself.
        self.assertEqual(manifest["tables"]["chapters"]["rows"], int(psql("SELECT count(*) FROM chapters")))
        self.assertEqual(manifest["checks"]["embeddings_stored"]["chapter_chunks.embedding"],
                         int(psql("SELECT count(embedding) FROM chapter_chunks")))
        self.assertEqual(int(psql(f"SELECT count(*) FROM chapters WHERE story_id = '{self.sid}'")), 3)
        self.assertEqual(set(manifest["uploads"]["files"]), {"ocr/page-1.png", "audio/clip.webm"})
        self.assertTrue(manifest["tables"]["ai_generation_pins"]["excluded"])
        self.assertEqual(manifest["uploads"]["referenced_but_missing"], 0)
        result = self.verify(stem)
        self.assertEqual(result["result"], "PASS", result["problems"])
        self.assertEqual(result["upload_files_verified"], 2)
        self.assertGreaterEqual(result["tables_checked"], 50)
        self.assertEqual(result["chapters"], manifest["tables"]["chapters"]["rows"])
        self.__class__.good_stem = stem

    def test_2_altered_content_fails_verification(self):
        stem = self.backup()
        mf = self.backups / f"{stem}.manifest.json"
        m = json.loads(mf.read_text())
        m["tables"]["chapters"]["content_md5"] = "0" * 32       # the backup "claims" other text
        mf.write_text(json.dumps(m))
        self._rewrite_sums(stem)
        result = self.verify(stem)
        self.assertEqual(result["result"], "FAIL")
        self.assertIn("chapters: restored content differs from the backup", result["problems"])

    def test_3_changed_upload_file_fails_verification(self):
        stem = self.backup()
        mf = self.backups / f"{stem}.manifest.json"
        m = json.loads(mf.read_text())
        m["uploads"]["files"]["ocr/page-1.png"] = "f" * 64
        mf.write_text(json.dumps(m))
        self._rewrite_sums(stem)
        result = self.verify(stem)
        self.assertEqual(result["result"], "FAIL")
        self.assertTrue(any("page-1.png" in p for p in result["problems"]), result["problems"])

    def test_4_corrupted_archive_fails_on_checksum(self):
        stem = self.backup()
        dump = self.backups / f"{stem}.dump"
        data = bytearray(dump.read_bytes())
        data[len(data) // 2] ^= 0xFF
        dump.write_bytes(bytes(data))
        result = self.verify(stem)
        self.assertEqual(result["result"], "FAIL")
        self.assertTrue(any("checksum mismatch" in p for p in result["problems"]), result["problems"])

    def _rewrite_sums(self, stem: str):
        stamp = stem[len("narratiq-"):]
        files = [f"{stem}.dump", f"{stem}.manifest.json", f"narratiq-uploads-{stamp}.tar.gz",
                 f"narratiq-globals-{stamp}.sql"]
        out = subprocess.run(["sha256sum", *files], cwd=self.backups, capture_output=True, text=True, check=True)
        (self.backups / f"{stem}.SHA256SUMS").write_text(out.stdout)


class RetentionTests(unittest.TestCase):
    def _make(self, d: Path, when: datetime) -> str:
        stamp = when.strftime("%Y%m%dT%H%M%SZ")
        for name in (f"narratiq-{stamp}.dump", f"narratiq-{stamp}.manifest.json",
                     f"narratiq-uploads-{stamp}.tar.gz", f"narratiq-globals-{stamp}.sql"):
            (d / name).write_text("x")
        return stamp

    def test_gfs_keeps_recent_daily_markers_and_last_verified(self):
        d = Path(tempfile.mkdtemp())
        now = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)
        stamps = [self._make(d, now - timedelta(hours=h)) for h in range(0, 24 * 10, 1)]   # 10 days hourly
        (d / "unrelated.txt").write_text("keep me")
        old_marked = stamps[-1]
        (d / f"narratiq-{old_marked}.keep").write_text("")
        verified = stamps[-2]
        (d / "LAST-VERIFY.json").write_text(json.dumps({"result": "PASS", "backup_set": f"narratiq-{verified}"}))
        p = backup_retention.plan(d, keep_recent=24, keep_daily_days=7, now=now)
        kept = set(p["keep"])
        self.assertTrue(set(stamps[:24]) <= kept)                   # the newest 24
        days = {s[:8] for s in kept}
        self.assertGreaterEqual(len(days), 8)                       # one per day within 7 days (+ today)
        self.assertIn(old_marked, kept)
        self.assertIn(verified, kept)
        self.assertEqual(len(p["delete"]) + len(kept), len(stamps))
        # --apply deletes only whole recognised sets.
        r = subprocess.run([sys.executable, str(REPO / "scripts" / "backup_retention.py"),
                            "--backup-dir", str(d), "--apply"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((d / "unrelated.txt").exists())
        for s in p["delete"][:5]:
            self.assertFalse(any(d.glob(f"*{s}*")))
        shutil.rmtree(d)

    def test_few_backups_are_never_pruned(self):
        d = Path(tempfile.mkdtemp())
        now = datetime(2026, 9, 29, tzinfo=timezone.utc)
        for h in range(5):
            self._make(d, now - timedelta(days=30 + h))              # old, but only five
        p = backup_retention.plan(d, keep_recent=24, keep_daily_days=7, now=now)
        self.assertEqual(p["delete"], [])
        shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main()
