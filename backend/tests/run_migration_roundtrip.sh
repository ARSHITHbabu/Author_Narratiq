#!/usr/bin/env bash
# Stage 7 task 7.4 — Phase 3 migration round-trip against a POPULATED database.
#
# Local, repeatable substitute for the "migration test runs in CI" checkbox
# while CI/GitHub Actions is deferred by explicit author decision (Stage 6).
#
#   upgrade head → write Phase 3 rows (pin, idea card, preferences, plan)
#   → downgrade 0018 → assert: Phase 3 objects gone, author data byte-identical,
#     the idea card SURVIVES as an ordinary note card (spec §36.3)
#   → upgrade head again → assert schema restored and idempotent
#   → remove the rows this script created.
#
# Refuses to run unless DATABASE_URL names an allow-listed test database
# (tests/db_safety_guard.py — the same guard the pytest suite uses).
#
# Usage (from backend/):
#   DATABASE_URL=postgresql+psycopg2://narratiq:narratiq@localhost:5432/narratiq_test \
#       bash tests/run_migration_roundtrip.sh
set -euo pipefail
cd "$(dirname "$0")/.."

python3 - <<'PY'
import sys
sys.path.insert(0, "tests")
from db_safety_guard import allowed_test_dbs, is_allowed_test_db_name, refusal_message
from sqlalchemy.engine import make_url
import os
name = make_url(os.environ["DATABASE_URL"]).database
if not is_allowed_test_db_name(name, allowed_test_dbs()):
    print(refusal_message(name, allowed_test_dbs())); sys.exit(1)
print(f"[roundtrip] target: allow-listed test database {name!r}")
PY

step() { echo; echo "── $*"; }

step "upgrade head"
python3 -m alembic upgrade head 2>&1 | grep -E "Running upgrade|ERROR" || true

python3 - <<'PY'
import hashlib, json, os, sys
from datetime import datetime, timedelta
from sqlalchemy import create_engine, inspect, text

eng = create_engine(os.environ["DATABASE_URL"])
FP_SQL = {
  "users": "SELECT md5(string_agg(user_id||email||username, ',' ORDER BY user_id)) FROM users",
  "stories": "SELECT md5(string_agg(story_id||title, ',' ORDER BY story_id)) FROM stories",
  "chapters": "SELECT md5(string_agg(chapter_id||title||content, ',' ORDER BY chapter_id)) FROM chapters",
  "characters": "SELECT md5(string_agg(character_id||name, ',' ORDER BY character_id)) FROM characters",
  "story_notes": "SELECT md5(string_agg(note_id||content, ',' ORDER BY note_id)) FROM story_notes",
  "note_cards": "SELECT md5(string_agg(card_id||title||content||card_type, ',' ORDER BY card_id)) FROM note_cards",
  "preservation": "SELECT md5(string_agg(story_id||preserve_character_names::text||preserve_tone::text||author_notes, ',' ORDER BY story_id)) FROM story_preservation_settings",
}
def fp():
    with eng.connect() as c:
        return {k: c.execute(text(q)).scalar() for k, q in FP_SQL.items()}

with eng.begin() as c:
    row = c.execute(text("SELECT s.story_id, s.user_id, ch.chapter_id FROM stories s JOIN chapters ch ON ch.story_id = s.story_id ORDER BY s.story_id, ch.chapter_number LIMIT 1")).first()
    if row is None:
        print("[roundtrip] FAIL: database has no story/chapter to test against — populate it first"); sys.exit(1)
    sid, uid, chid = row
    pin_id, card_id = "roundtrip-pin-0001", "roundtrip-card-0001"
    content = "Roundtrip pin content."
    c.execute(text("""INSERT INTO ai_generation_pins (pin_id,user_id,story_id,chapter_id,tool,content,content_sha256,
                     content_bytes,word_count,root_pin_id,lineage_depth,expires_at,created_at)
                     VALUES (:p,:u,:s,:ch,'tone',:c,:h,:b,3,:p,0,:e,:n)"""),
              dict(p=pin_id, u=uid, s=sid, ch=chid, c=content, h=hashlib.sha256(content.encode()).hexdigest(),
                   b=len(content), e=datetime.utcnow() + timedelta(days=7), n=datetime.utcnow()))
    c.execute(text("""INSERT INTO note_cards (card_id,story_id,user_id,title,content,card_type,target_chapter_id,tags,status,source_pin_id,created_at,updated_at)
                     VALUES (:id,:s,:u,'Roundtrip idea','An idea that must survive rollback.','plot_twist',:ch,:t,'open',:p,now(),now())"""),
              dict(id=card_id, s=sid, u=uid, ch=chid, t=json.dumps(["act3"]), p=pin_id))
    c.execute(text("UPDATE story_preservation_settings SET preserve_rules = :r WHERE story_id = :s"),
              dict(r=json.dumps({"tense": True}), s=sid))
    c.execute(text("UPDATE users SET plan = 'pro' WHERE user_id = :u"), dict(u=uid))
before = fp()
json.dump({"before": before, "sid": sid, "uid": uid, "card_id": card_id}, open("/tmp/.narratiq_roundtrip.json", "w"))
print("[roundtrip] Phase 3 rows written; author-data fingerprint recorded")
PY

step "downgrade to 0018"
python3 -m alembic downgrade 0018 2>&1 | grep -E "Running downgrade|ERROR" || true

python3 - <<'PY'
import json, os, sys
from sqlalchemy import create_engine, inspect, text
eng = create_engine(os.environ["DATABASE_URL"])
st = json.load(open("/tmp/.narratiq_roundtrip.json"))
insp = inspect(eng)
fails = []
if insp.has_table("ai_generation_pins"): fails.append("ai_generation_pins still exists after downgrade")
cols = {c["name"] for c in insp.get_columns("note_cards")}
if cols & {"target_chapter_id", "tags", "status", "source_pin_id"}: fails.append(f"note_cards Phase 3 columns remain: {cols}")
if "plan" in {c["name"] for c in insp.get_columns("users")}: fails.append("users.plan remains")
if {"preserve_rules","style_prefs","pin_prefs"} & {c["name"] for c in insp.get_columns("story_preservation_settings")}: fails.append("preference columns remain")
with eng.connect() as c:
    ver = c.execute(text("SELECT version_num FROM alembic_version")).scalar()
    card = c.execute(text("SELECT content, card_type FROM note_cards WHERE card_id = :i"), dict(i=st["card_id"])).first()
    fp_sql = {
      "users": "SELECT md5(string_agg(user_id||email||username, ',' ORDER BY user_id)) FROM users",
      "stories": "SELECT md5(string_agg(story_id||title, ',' ORDER BY story_id)) FROM stories",
      "chapters": "SELECT md5(string_agg(chapter_id||title||content, ',' ORDER BY chapter_id)) FROM chapters",
      "characters": "SELECT md5(string_agg(character_id||name, ',' ORDER BY character_id)) FROM characters",
      "story_notes": "SELECT md5(string_agg(note_id||content, ',' ORDER BY note_id)) FROM story_notes",
      "note_cards": "SELECT md5(string_agg(card_id||title||content||card_type, ',' ORDER BY card_id)) FROM note_cards",
      "preservation": "SELECT md5(string_agg(story_id||preserve_character_names::text||preserve_tone::text||author_notes, ',' ORDER BY story_id)) FROM story_preservation_settings",
    }
    after = {k: c.execute(text(q)).scalar() for k, q in fp_sql.items()}
if ver != "0018": fails.append(f"alembic version {ver} != 0018")
if card is None: fails.append("IDEA CARD LOST ON ROLLBACK")
elif card.content != "An idea that must survive rollback.": fails.append("idea card content changed")
for k in after:
    if after[k] != st["before"][k]: fails.append(f"author data changed on downgrade: {k}")
if fails:
    print("[roundtrip] FAIL:\n  " + "\n  ".join(fails)); sys.exit(1)
print(f"[roundtrip] downgrade OK — Phase 3 objects removed; {len(after)}/{len(after)} author tables byte-identical; idea card survived as a '{card.card_type}' note card")
PY

step "upgrade head again (re-apply)"
python3 -m alembic upgrade head 2>&1 | grep -E "Running upgrade|ERROR" || true
step "upgrade head a third time (must be a no-op)"
python3 -m alembic upgrade head 2>&1 | grep -E "Running upgrade|ERROR" || echo "  (no-op, as expected)"

python3 - <<'PY'
import json, os, sys
from sqlalchemy import create_engine, inspect, text
eng = create_engine(os.environ["DATABASE_URL"])
st = json.load(open("/tmp/.narratiq_roundtrip.json"))
insp = inspect(eng)
fails = []
if not insp.has_table("ai_generation_pins"): fails.append("ai_generation_pins missing after re-upgrade")
idx = {i["name"] for i in insp.get_indexes("ai_generation_pins")}
need = {"ix_ai_generation_pins_expires_at","ix_ai_generation_pins_user_story","ix_ai_generation_pins_chapter",
        "ix_ai_generation_pins_content_sha","ix_ai_generation_pins_root"}
if need - idx: fails.append(f"missing indexes: {need - idx}")
with eng.begin() as c:
    ver = c.execute(text("SELECT version_num FROM alembic_version")).scalar()
    card = c.execute(text("SELECT status FROM note_cards WHERE card_id = :i"), dict(i=st["card_id"])).first()
    if ver != "0022": fails.append(f"alembic version {ver} != 0022")
    if card is None or card.status != "open": fails.append("idea card not readable as open after re-upgrade")
    c.execute(text("DELETE FROM note_cards WHERE card_id = :i"), dict(i=st["card_id"]))
    c.execute(text("UPDATE users SET plan = NULL WHERE user_id = :u"), dict(u=st["uid"]))
    c.execute(text("UPDATE story_preservation_settings SET preserve_rules = NULL WHERE story_id = :s"), dict(s=st["sid"]))
os.remove("/tmp/.narratiq_roundtrip.json")
if fails:
    print("[roundtrip] FAIL:\n  " + "\n  ".join(fails)); sys.exit(1)
print("[roundtrip] re-upgrade OK — schema restored, idempotent; script's own rows removed")
print("[roundtrip] PASS")
PY
