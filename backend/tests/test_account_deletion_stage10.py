"""
Stage 10 — task 10.6 (account and data deletion, decision S10-G) and the
chapter-deletion defect found while planning it.

Verification the checklist asks for, by database state — not by status code:
  * account deletion removes ALL associated rows, including every pgvector
    column (all nine embedding columns are populated first);
  * no orphaned data: nothing anywhere still references the deleted account's
    user, stories or chapters, and its upload files are gone from disk;
  * the other author's rows are byte-identical before and after;
  * wrong password / missing confirmation delete nothing; every session ends.

    DATABASE_URL=...narratiq_test pytest backend/tests/test_account_deletion_stage10.py -q
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from sqlalchemy import select, text  # noqa: E402

from config import settings  # noqa: E402
from database import Base  # noqa: E402
from models import (  # noqa: E402
    ActivityEvent, ChapterChunk, ChapterSummary, CharacterArcSnapshot, CharacterMention,
    CharacterProfile, RevokedSession, StoryGraphNode, StoryMemoryEntry, StoryTimelineEvent,
    User, VoiceSession, VoiceUsageDaily,
)
from routers.auth import create_token, hash_password  # noqa: E402
from services.account_deletion import owned_rows, remove_orphan_upload_files  # noqa: E402
from test_cross_user_isolation import _fingerprint, _owned_pk_sets, _two_populated_authors  # noqa: E402

VEC = [0.01] * 1024
EMBEDDING_COLUMNS = [
    ("chapter_chunks", "embedding"), ("chapter_summaries", "embedding"),
    ("character_profiles", "embedding"), ("character_profiles", "mention_embedding"),
    ("story_notes", "embedding"), ("note_cards", "embedding"),
    ("story_memory_entries", "embedding"), ("story_graph_nodes", "embedding"),
    ("ai_generation_pins", "embedding"),
]


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch):
    from middleware.rate_limit import limiter
    monkeypatch.setattr(limiter, "enabled", False)


def _enrich(db, a, tmp_path: Path) -> list[Path]:
    """Add the derived / vector / file-backed rows the isolation fixture does
    not create, so deletion is tested against a fully populated account."""
    uid, sid = a.user.user_id, a.story.story_id
    ch = a.chapters[0].chapter_id
    c1 = a.characters[0].character_id
    a.user.hashed_password = hash_password("pw-for-delete")
    db.add_all([
        ChapterChunk(chapter_id=ch, story_id=sid, chapter_number=1, chunk_index=0, text="chunk", embedding=VEC),
        ChapterSummary(chapter_id=ch, story_id=sid, chapter_number=1, embedding=VEC),
        CharacterProfile(character_id=c1, story_id=sid, embedding=VEC, mention_embedding=VEC),
        StoryMemoryEntry(story_id=sid, memory_type="fact", memory_key="k", content="c", embedding=VEC),
        StoryGraphNode(story_id=sid, node_type="character", label="n", embedding=VEC),
        CharacterMention(character_id=c1, story_id=sid, chapter_id=ch, chapter_number=1, passage_text="p"),
        CharacterArcSnapshot(character_id=c1, story_id=sid, chapter_id=ch, chapter_number=1),
        StoryTimelineEvent(story_id=sid, chapter_id=ch, chapter_number=1),
        ActivityEvent(story_id=sid, user_id=uid, category="writing", type="chapter_saved"),
        VoiceSession(user_id=uid, story_id=None, status="ended", context_state={}, started_at=datetime.utcnow()),
        VoiceUsageDaily(day=date(2026, 9, 29), user_id=uid),
        RevokedSession(jti=uuid.uuid4().hex, user_id=uid, expires_at=datetime(2030, 1, 1)),
    ])
    a.note.embedding = VEC
    a.card.embedding = VEC
    a.pin.embedding = VEC
    files = []
    for row, attr, name in ((a.ocr, "image_path", "img.png"), (a.audio, "audio_path", "clip.webm")):
        f = tmp_path / f"{uuid.uuid4().hex}-{name}"
        f.write_bytes(b"author upload")
        setattr(row, attr, str(f))
        files.append(f)
    db.commit()
    return files


def _references_left(db, user_id: str, story_ids: set[str], chapter_ids: set[str]) -> list[str]:
    """Every column named user_id / story_id / chapter_id, in every table,
    checked for the deleted account's values."""
    left = []
    for table in Base.metadata.sorted_tables:
        for col, ids in (("user_id", {user_id}), ("story_id", story_ids), ("chapter_id", chapter_ids)):
            if col in table.c and ids:
                n = db.execute(select(table.c[col]).where(table.c[col].in_(ids))).first()
                if n:
                    left.append(f"{table.name}.{col}")
    return left


def test_account_deletion_removes_everything_and_touches_nothing_else(tmp_path):
    with _two_populated_authors() as (db, a, b, client):
        files = _enrich(db, a, tmp_path)
        uid, sid = a.user.user_id, a.story.story_id
        chapter_ids = {c.chapter_id for c in a.chapters}
        for table, col in EMBEDDING_COLUMNS:       # precondition: every vector column populated
            n = db.execute(text(f"SELECT count(*) FROM {table} t WHERE {col} IS NOT NULL AND "
                                f"t.story_id = :sid"), {"sid": sid}).scalar()
            assert n >= 1, f"fixture did not populate {table}.{col}"
        b_rows = _owned_pk_sets(db, {b.user.user_id})
        b_before = _fingerprint(db, b_rows)
        owned = owned_rows(db, uid)
        assert len(owned) >= 25, sorted(owned)     # the walk reaches the whole account

        # Refusals delete nothing.
        r = client.request("DELETE", "/api/auth/account", headers=a.headers,
                           json={"password": "wrong", "confirm": "DELETE"})
        assert r.status_code == 403
        r = client.request("DELETE", "/api/auth/account", headers=a.headers,
                           json={"password": "pw-for-delete", "confirm": "delete"})
        assert r.status_code == 422
        db.expire_all()
        assert db.query(User).filter(User.user_id == uid).count() == 1

        r = client.request("DELETE", "/api/auth/account", headers=a.headers,
                           json={"password": "pw-for-delete", "confirm": "DELETE"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["deleted"] is True and body["files_pending"] == 0
        assert body["rows_deleted"] == sum(len(v) for v in owned.values())

        db.expire_all()
        assert _owned_pk_sets(db, {uid}) == {}
        assert _references_left(db, uid, {sid}, chapter_ids) == []
        for table, col in EMBEDDING_COLUMNS:
            n = db.execute(text(f"SELECT count(*) FROM {table} WHERE {col} IS NOT NULL AND story_id = :sid"),
                           {"sid": sid}).scalar()
            assert n == 0, f"{table}.{col} still has vectors for the deleted story"
        assert not any(f.exists() for f in files), "upload files were not removed"
        # The deleted account's session no longer works.
        assert client.get("/api/auth/me", headers=a.headers).status_code == 401
        # The other author is untouched, row for row.
        assert _fingerprint(db, _owned_pk_sets(db, {b.user.user_id})) == b_before
        assert client.get("/api/projects/", headers=b.headers).status_code == 200


def test_account_deletion_requires_a_session():
    from fastapi.testclient import TestClient
    import main
    r = TestClient(main.app).request("DELETE", "/api/auth/account", json={"password": "x", "confirm": "DELETE"})
    assert r.status_code == 401


def test_story_deletion_leaves_no_rows_behind(tmp_path):
    """Deleting a fully populated story through the API removes every row
    that references it (vectors included) and keeps the account."""
    with _two_populated_authors() as (db, a, b, client):
        _enrich(db, a, tmp_path)
        sid = a.story.story_id
        chapter_ids = {c.chapter_id for c in a.chapters}
        r = client.delete(f"/api/projects/{sid}", headers=a.headers)
        assert r.status_code in (200, 204), r.text
        db.expire_all()
        left = [x for x in _references_left(db, "__none__", {sid}, chapter_ids)]
        assert left == [], left
        assert db.query(User).filter(User.user_id == a.user.user_id).count() == 1


def test_chapter_deletion_after_indexing_succeeds(tmp_path):
    """Defect found in Stage 10: an indexed chapter (with a summary, mentions,
    hints, arc snapshots, timeline events) could not be deleted — HTTP 500."""
    with _two_populated_authors() as (db, a, b, client):
        _enrich(db, a, tmp_path)
        ch = a.chapters[0].chapter_id
        r = client.delete(f"/api/stories/{a.story.story_id}/chapters/{ch}", headers=a.headers)
        assert r.status_code == 200, r.text
        db.expire_all()
        assert _references_left(db, "__none__", set(), {ch}) == []
        # The timeline event survives without its chapter link; the rest of the story is intact.
        assert db.query(StoryTimelineEvent).filter(StoryTimelineEvent.story_id == a.story.story_id).count() == 1
        remaining = client.get(f"/api/stories/{a.story.story_id}/chapters", headers=a.headers).json()
        assert [c["chapter_number"] for c in remaining] == [1]


def test_orphan_upload_sweep_removes_only_unreferenced_old_files(tmp_path):
    with _two_populated_authors() as (db, a, b, client):
        files = _enrich(db, a, tmp_path)
        stray_old = tmp_path / "stray-old.png"
        stray_new = tmp_path / "stray-new.png"
        stray_old.write_bytes(b"x")
        stray_new.write_bytes(b"x")
        old = datetime(2026, 1, 1).timestamp()
        for f in (stray_old, *files):
            os.utime(f, (old, old))
        assert remove_orphan_upload_files([str(tmp_path)]) == 1
        assert not stray_old.exists()
        assert stray_new.exists()                           # too young: may still be in use
        assert all(f.exists() for f in files)               # referenced by a row


def test_create_token_for_deleted_user_is_refused():
    from fastapi.testclient import TestClient
    import main
    tok = create_token(str(uuid.uuid4()))
    assert TestClient(main.app).get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"}).status_code == 401


def test_settings_have_upload_dirs():
    assert settings.upload_dir_audio and settings.upload_dir_ocr
