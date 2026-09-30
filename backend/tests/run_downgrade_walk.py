#!/usr/bin/env python3
"""
Stage 10 (task 10.5) — schema rollback rehearsal on a POPULATED database.

Walks the Alembic chain one revision at a time from head DOWN to a floor
(default 0016 — the oldest revision a supported rollback would reach), then
back UP to head, and after every single step proves that nothing outside the
migration being reversed or re-applied was touched:

  * every table is fingerprinted PER COLUMN: row count, and for each column an
    md5 over that column's values in primary-key order (byte order), vectors
    included;
  * after each step, every column that exists both before and after the step
    must be identical, and every table that exists on both sides must keep its
    row count. A column or table the migration itself drops or creates is the
    migration's own object — reported, not failed;
  * after the full walk back to head, every column of every table that was not
    dropped by some step must equal its value at the start.

Rows this script writes into tables that a downgrade drops (pins, revoked
sessions, error events) are expected to go with their table. The idea card it
writes into note_cards (a table that survives) must survive the whole walk.

Refuses to run unless DATABASE_URL names an allow-listed test database
(tests/db_safety_guard.py). Needs at least one story with a chapter
(backend/scripts/seed_fixture.py).

    DATABASE_URL=postgresql+psycopg2://narratiq:narratiq@localhost:5432/narratiq_test \
        python3 tests/run_downgrade_walk.py [--floor 0016]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(BACKEND))

from db_safety_guard import allowed_test_dbs, is_allowed_test_db_name, refusal_message  # noqa: E402
from sqlalchemy import create_engine, inspect, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402


def _q(s: str) -> str:
    return '"' + s.replace('"', '""') + '"'


def alembic(*args: str) -> None:
    r = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"alembic {' '.join(args)} failed:\n{r.stderr[-2000:]}")


def chain() -> list[str]:
    """Revision ids, base → head."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    return [r.revision for r in reversed(list(ScriptDirectory.from_config(cfg).walk_revisions()))]


def fingerprint(eng) -> dict[str, dict]:
    """{table: {"rows": n, "cols": {column: md5}}} for every table."""
    insp = inspect(eng)
    out: dict[str, dict] = {}
    with eng.connect() as c:
        for t in insp.get_table_names():
            if t == "alembic_version":      # changes by definition; checked separately per step
                continue
            pk = insp.get_pk_constraint(t).get("constrained_columns") or []
            order = f"t.{_q(pk[0])}::text COLLATE \"C\"" if len(pk) == 1 else "md5(t::text) COLLATE \"C\""
            cols = [col["name"] for col in insp.get_columns(t)]
            exprs = ", ".join(f"md5(coalesce(string_agg(md5(coalesce(t.{_q(col)}::text, '<null>')), '' "
                              f"ORDER BY {order}), ''))" for col in cols)
            row = c.execute(text(f"SELECT count(*), {exprs} FROM {_q(t)} t")).one()
            out[t] = {"rows": row[0], "cols": dict(zip(cols, row[1:]))}
    return out


def diff(before: dict, after: dict) -> tuple[list[str], list[str]]:
    """(problems, migration-owned changes) between two fingerprints."""
    problems, owned = [], []
    for t in sorted(set(before) | set(after)):
        if t not in after:
            owned.append(f"table {t} dropped")
            continue
        if t not in before:
            owned.append(f"table {t} created")
            continue
        b, a = before[t], after[t]
        if b["rows"] != a["rows"]:
            problems.append(f"{t}: {b['rows']} rows before, {a['rows']} after")
        for col in b["cols"]:
            if col not in a["cols"]:
                owned.append(f"column {t}.{col} dropped")
            elif b["cols"][col] != a["cols"][col]:
                problems.append(f"{t}.{col}: values changed")
        for col in a["cols"]:
            if col not in b["cols"]:
                owned.append(f"column {t}.{col} added")
    return problems, owned


def seed(eng) -> dict:
    with eng.begin() as c:
        row = c.execute(text("SELECT s.story_id, s.user_id, ch.chapter_id FROM stories s JOIN chapters ch "
                             "ON ch.story_id = s.story_id ORDER BY s.story_id, ch.chapter_number LIMIT 1")).first()
        if row is None:
            print("[walk] FAIL: no story/chapter to test against — run scripts/seed_fixture.py first")
            sys.exit(1)
        sid, uid, chid = row
        tag = uuid.uuid4().hex[:8]
        now = datetime.utcnow()
        c.execute(text("""INSERT INTO ai_generation_pins (pin_id,user_id,story_id,chapter_id,tool,content,content_sha256,
                          content_bytes,word_count,root_pin_id,lineage_depth,expires_at,created_at)
                          VALUES (:p,:u,:s,:ch,'tone','walk pin',:h,8,2,:p,0,:e,:n)"""),
                  dict(p=f"walk-pin-{tag}", u=uid, s=sid, ch=chid, h=hashlib.sha256(b"walk pin").hexdigest(),
                       e=now + timedelta(days=7), n=now))
        c.execute(text("""INSERT INTO note_cards (card_id,story_id,user_id,title,content,card_type,created_at,updated_at)
                          VALUES (:id,:s,:u,'Walk idea','An idea that must survive every rollback.','plot_twist',now(),now())"""),
                  dict(id=f"walk-card-{tag}", s=sid, u=uid))
        c.execute(text("INSERT INTO revoked_sessions (jti,user_id,expires_at,revoked_at) VALUES (:j,:u,:e,:n)"),
                  dict(j=f"walk-{tag}", u=uid, e=now + timedelta(days=1), n=now))
        c.execute(text("""INSERT INTO error_events (event_id,source,kind,fingerprint,occurrences,first_seen,last_seen)
                          VALUES (:i,'backend','WalkError',:f,1,:n,:n)"""), dict(i=f"walk-{tag}", f="0" * 64, n=now))
    return {"uid": uid, "card": f"walk-card-{tag}", "tag": tag}


def cleanup(eng, s: dict) -> None:
    with eng.begin() as c:
        for table, col, val in (("note_cards", "card_id", s["card"]),
                                ("ai_generation_pins", "pin_id", f"walk-pin-{s['tag']}"),
                                ("revoked_sessions", "jti", f"walk-{s['tag']}"),
                                ("error_events", "event_id", f"walk-{s['tag']}")):
            c.execute(text(f"DELETE FROM {table} WHERE {col} = :v"), dict(v=val))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--floor", default="0016")
    args = ap.parse_args()
    url = os.environ["DATABASE_URL"]
    name = make_url(url).database
    if not is_allowed_test_db_name(name, allowed_test_dbs()):
        print(refusal_message(name, allowed_test_dbs()))
        return 1
    print(f"[walk] target: allow-listed test database {name!r}")
    revs = chain()
    head = revs[-1]
    if args.floor not in revs:
        print(f"[walk] unknown floor {args.floor}")
        return 1
    down = list(reversed(revs[revs.index(args.floor):-1]))          # head-1 … floor
    up = list(reversed(down))[1:] + [head]                          # floor+1 … head
    eng = create_engine(url)
    alembic("upgrade", "head")
    s = seed(eng)
    start = fingerprint(eng)
    problems: list[str] = []
    dropped: set[str] = set()
    t0 = time.monotonic()
    current = start
    for op, target in [("downgrade", r) for r in down] + [("upgrade", r) for r in up]:
        alembic(op, target)
        after = fingerprint(eng)
        step_problems, owned = diff(current, after)
        dropped.update(o.split()[1] for o in owned if o.startswith(("table", "column")) and "dropped" in o)
        with eng.connect() as c:
            ver = c.execute(text("SELECT version_num FROM alembic_version")).scalar()
        if ver != target:
            step_problems.append(f"alembic reports {ver}")
        problems += [f"{op} → {target}: {p}" for p in step_problems]
        print(f"[walk] {op:9s} → {target}: {'ok' if not step_problems else 'CHANGED DATA'}"
              + (f"  (own objects: {'; '.join(owned)})" if owned else ""))
        current = after

    # Head again: everything never dropped along the way must equal the start.
    end_problems, _ = diff(start, current)
    for p in end_problems:
        obj = p.split(":")[0]
        if obj not in dropped and obj.split(".")[0] not in dropped:
            problems.append(f"after the full walk: {p}")
    with eng.connect() as c:
        card = c.execute(text("SELECT content FROM note_cards WHERE card_id=:i"), dict(i=s["card"])).scalar()
    if card != "An idea that must survive every rollback.":
        problems.append("the idea card did not survive the walk")
    cleanup(eng, s)
    summary = {"result": "PASS" if not problems else "FAIL", "steps": len(down) + len(up),
               "floor": args.floor, "head": head, "tables": len(start),
               "seconds": round(time.monotonic() - t0, 1), "problems": problems[:30]}
    print(json.dumps(summary, indent=1))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
