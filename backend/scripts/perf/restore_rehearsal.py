#!/usr/bin/env python3
"""
Stage 10 (task 10.1) — full backup → restore rehearsal at realistic size.

1. clones the schema of `narratiq_test` into the allow-listed scratch source
   database `narratiq_ci_verify` (never the live database);
2. fills it with a realistic corpus: N authors, each with a ~200k-word
   manuscript (10 chapters), 580 chunks with 1024-dim vectors, chapter
   summaries with vectors, notes — and real upload files on disk;
3. runs the production backup script (scripts/backup_database.sh) against it;
4. runs the production verifier (scripts/verify_backup.py): real restore into
   `narratiq_restorecheck`, table-by-table content hashes, chapter text,
   embedding counts, every upload's SHA-256;
5. reports sizes and timings (the restore part of the RTO), then drops both
   databases and deletes its files.

    python3 backend/scripts/perf/restore_rehearsal.py --authors 100 --out /tmp/rehearsal.json
Needs a local PostgreSQL superuser path (NARRATIQ_PG_SUPERUSER_CMD, default `su postgres -c`).
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SOURCE = "narratiq_ci_verify"
SU = shlex.split(os.environ.get("NARRATIQ_PG_SUPERUSER_CMD", "su postgres -c"))
PG = {"PGHOST": "localhost", "PGPORT": "5432", "PGUSER": "narratiq", "PGPASSWORD": "narratiq"}
WORDS = ("the lamp guttered and she counted doors along the corridor while rain pressed "
         "against glass and somewhere below a clock began again").split()


def su(cmd: str) -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
    r = subprocess.run(SU + [cmd], capture_output=True, text=True, env=env)
    if r.returncode != 0:
        raise RuntimeError(r.stderr)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--authors", type=int, default=100)
    ap.add_argument("--chunks", type=int, default=580)
    ap.add_argument("--uploads", type=int, default=200, help="upload files (≈200 KB each)")
    ap.add_argument("--out", default="/tmp/narratiq-restore-rehearsal.json")
    args = ap.parse_args()

    import psycopg2
    tmp = Path(tempfile.mkdtemp(prefix="rehearsal-"))
    backups, uploads = tmp / "backups", tmp / "uploads"
    (uploads / "ocr").mkdir(parents=True)
    backups.mkdir()
    for d in (tmp, backups):
        os.chmod(d, 0o755)
    result: dict = {"authors": args.authors}
    try:
        su(f"dropdb --if-exists {SOURCE}")
        su(f"createdb -O narratiq -T narratiq_test {SOURCE}")
        rng = random.Random(7)
        t0 = time.monotonic()
        conn = psycopg2.connect(dbname=SOURCE, **{k.lower()[2:]: v for k, v in PG.items()})
        cur = conn.cursor()
        vec = lambda: "[" + ",".join(f"{rng.uniform(-1, 1):.5f}" for _ in range(1024)) + "]"  # noqa: E731
        files = 0
        for a in range(args.authors):
            uid, sid = str(uuid.uuid4()), str(uuid.uuid4())
            cur.execute("INSERT INTO users (user_id,email,username,hashed_password,created_at,token_version) "
                        "VALUES (%s,%s,%s,'x',now(),0)", (uid, f"reh-{a}-{uid[:6]}@narratiq-internal-test.com", f"reh{a}{uid[:6]}"))
            cur.execute("INSERT INTO stories (story_id,user_id,title,created_at,updated_at) VALUES (%s,%s,%s,now(),now())",
                        (sid, uid, f"Rehearsal manuscript {a}"))
            chapter_ids = []
            for n in range(1, 11):
                cid = str(uuid.uuid4())
                chapter_ids.append(cid)
                text = " ".join(rng.choice(WORDS) for _ in range(20000))
                cur.execute("INSERT INTO chapters (chapter_id,story_id,chapter_number,title,content,word_count,created_at,updated_at) "
                            "VALUES (%s,%s,%s,%s,%s,20000,now(),now())", (cid, sid, n, f"Chapter {n}", f"<p>{text}</p>"))
                cur.execute("INSERT INTO chapter_summaries (summary_id,chapter_id,story_id,chapter_number,embedding) "
                            "VALUES (%s,%s,%s,%s,%s)", (str(uuid.uuid4()), cid, sid, n, vec()))
            for i in range(args.chunks):
                n = i * 10 // args.chunks
                cur.execute("INSERT INTO chapter_chunks (chunk_id,chapter_id,story_id,chapter_number,chunk_index,text,embedding) "
                            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                            (str(uuid.uuid4()), chapter_ids[n], sid, n + 1, i, " ".join(rng.choice(WORDS) for _ in range(350)), vec()))
            if files < args.uploads:
                for _ in range(max(1, args.uploads // args.authors)):
                    p = uploads / "ocr" / f"{uuid.uuid4()}.png"
                    p.write_bytes(os.urandom(200_000))
                    cur.execute("INSERT INTO ocr_uploads (upload_id,story_id,user_id,image_path,raw_ocr_text,cleaned_text,confirmed,created_at) "
                                "VALUES (%s,%s,%s,%s,'r','c',false,now())", (str(uuid.uuid4()), sid, uid, str(p)))
                    files += 1
            conn.commit()
        cur.execute("SELECT pg_size_pretty(pg_database_size(current_database())), pg_database_size(current_database())")
        pretty, size = cur.fetchone()
        conn.close()
        result.update(seed_seconds=round(time.monotonic() - t0, 1), database_size=pretty, database_bytes=size,
                      chapters=args.authors * 10, chunks=args.authors * args.chunks, upload_files=files)
        print(f"[rehearsal] seeded {pretty} in {result['seed_seconds']}s", flush=True)

        env_file = tmp / ".env"
        env_file.write_text(f"DATABASE_URL=postgresql+psycopg2://narratiq:narratiq@localhost:5432/{SOURCE}\n")
        env = {**{k: v for k, v in os.environ.items() if not k.startswith("PG")},
               "BACKUP_DIR": str(backups), "ENV_FILE": str(env_file), "NARRATIQ_UPLOADS_DIR": str(uploads)}
        t = time.monotonic()
        r = subprocess.run(["bash", str(REPO / "scripts" / "backup_database.sh")], env=env, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError("backup failed:\n" + r.stdout[-2000:] + r.stderr[-2000:])
        result["backup_seconds"] = round(time.monotonic() - t, 1)
        stem = sorted(backups.glob("narratiq-2*.SHA256SUMS"))[-1].name[:-len(".SHA256SUMS")]
        result["dump_bytes"] = (backups / f"{stem}.dump").stat().st_size
        result["uploads_archive_bytes"] = next(backups.glob("narratiq-uploads-*.tar.gz")).stat().st_size
        print(f"[rehearsal] backup {result['backup_seconds']}s", flush=True)

        venv = {**os.environ, **PG, "PGDATABASE": SOURCE}
        r = subprocess.run([sys.executable, str(REPO / "scripts" / "verify_backup.py"), "--backup-dir", str(backups),
                            "--set", stem], env=venv, capture_output=True, text=True)
        verify = json.loads((backups / "LAST-VERIFY.json").read_text())
        result["verify"] = verify
        print(f"[rehearsal] verify {verify['result']} restore {verify['restore_seconds']}s total {verify['total_seconds']}s",
              flush=True)
    finally:
        for db in (SOURCE, "narratiq_restorecheck"):
            try:
                su(f"dropdb --if-exists {db}")
            except Exception as exc:                  # noqa: BLE001
                print(f"[rehearsal] could not drop {db}: {exc}")
        shutil.rmtree(tmp, ignore_errors=True)
    Path(args.out).write_text(json.dumps(result, indent=1))
    print(json.dumps({k: v for k, v in result.items() if k != "verify"}, indent=1))
    return 0 if result.get("verify", {}).get("result") == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
