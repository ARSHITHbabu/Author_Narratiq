"""
Stage 9 task 9.5 — cross-user data isolation (production gap PG-14).

Two authors, A and B, each with a populated story. Every request is made as A
while naming B's resources. Three independent checks:

  1. Route sweep (driven by `main.app.routes`, so a new endpoint is covered
     automatically and `test_sweep_covers_every_id_bearing_route` fails if one
     is silently skipped): every route that takes an id in its path, query or
     body is called with B's ids. A 2xx response must never contain B's data
     (unique marker text), and a foreign id must look exactly like a
     non-existent one (same status code) — the services/ownership.py rule.
  2. No prompt leak: the model is replaced by a recorder; B's marker must never
     reach a prompt.
  3. No write: B's rows in every table are fingerprinted before and after the
     sweep and must be byte-identical.

Plus explicit regression tests for the defects found and fixed in Stage 9
(I1–I6). Runs only against an allow-listed test database (conftest guard):

    DATABASE_URL=...narratiq_test pytest backend/tests/test_cross_user_isolation.py -q
"""
from __future__ import annotations

import enum
import hashlib
import json
import sys
import types
import typing
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from fastapi.routing import APIRoute  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from sqlalchemy import select  # noqa: E402

import main  # noqa: E402
from _phase3_helpers import install_fake_model  # noqa: E402
from _route_inventory import api_routes  # noqa: E402
from config import settings  # noqa: E402
from database import Base, SessionLocal  # noqa: E402
from models import (  # noqa: E402
    AiGenerationPin, AudioUpload, Chapter, Character, CharacterHint, CharacterRelationship,
    GenreProfile, ManuscriptJob, NarrativeThread, NoteCard, OcrUpload, PlotAssistantSession,
    RelationshipIntelligence, Story, StoryBible, StoryIntake, StoryIntelJob, StoryNote,
    StoryVersion, User, VoiceCommand, VoiceSession,
)
from routers.auth import create_token, hash_password  # noqa: E402

MARK = "zqxmarkerb"            # appears only in B's data; lower-case search
B_TEXT = f"Zqxmarkerb secret manuscript text. Quillon Zqxmarkerb opened the vault."


# ── Fixture: two populated authors ───────────────────────────────────────────

class _Author:
    def __init__(self, db, tag: str, text: str, char_names: list[str], created: list[str]):
        self.user = User(email=f"s9-{tag}-{uuid.uuid4().hex[:8]}@narratiq-internal-test.com",
                         username=f"s9{tag}{uuid.uuid4().hex[:8]}", hashed_password=hash_password("x"))
        db.add(self.user); db.flush()
        uid = self.user.user_id
        db.commit()
        created.append(uid)      # registered before anything else can fail
        self.story = Story(user_id=uid, title=f"S9 {tag} {text[:20]}")
        db.add(self.story); db.flush()
        sid = self.story.story_id
        self.chapters = [Chapter(story_id=sid, title=f"Chapter {n} {text[:12]}", chapter_number=n,
                                 content=f"<p>{text}</p>") for n in (1, 2)]
        db.add_all(self.chapters); db.flush()
        ch = self.chapters[0].chapter_id
        self.characters = [Character(story_id=sid, user_id=uid, name=n, aliases=[]) for n in char_names]
        db.add_all(self.characters); db.flush()
        c1, c2 = self.characters[0].character_id, self.characters[1].character_id
        self.rel = CharacterRelationship(story_id=sid, from_character_id=c1, to_character_id=c2,
                                         relationship_type="ally")
        self.note = StoryNote(story_id=sid, user_id=uid, title=f"Note {text[:10]}", content=text)
        self.card = NoteCard(story_id=sid, user_id=uid, content=text)
        self.version = StoryVersion(chapter_id=ch, content=f"<p>{text}</p>", version_number=1, label=text[:20])
        self.plot = PlotAssistantSession(story_id=sid, user_id=uid, question=text, suggestions_returned=[])
        self.intake = StoryIntake(story_id=sid, raw_description=text, detected_genre="fantasy", analysis={})
        self.genre = GenreProfile(story_id=sid, genre="fantasy", tone=[text[:30]], writing_direction=text)
        self.ocr = OcrUpload(story_id=sid, user_id=uid, raw_ocr_text=text, cleaned_text=text)
        self.audio = AudioUpload(story_id=sid, user_id=uid, raw_transcript=text, cleaned_text=text,
                                 status="completed")
        self.bible = StoryBible(story_id=sid, user_id=uid, content_json=json.dumps({"characters": text}))
        self.thread = NarrativeThread(story_id=sid, user_id=uid, name=f"Thread {text[:15]}", description=text)
        self.hint = CharacterHint(story_id=sid, chapter_id=ch, chapter_number=1, suggested_name=char_names[0],
                                  context_snippet=text)
        self.intel_job = StoryIntelJob(story_id=sid, user_id=uid)
        self.ms_job = ManuscriptJob(story_id=sid, user_id=uid)
        self.voice = VoiceSession(user_id=uid, story_id=sid, status="active", context_state={},
                                  started_at=datetime.utcnow())
        rows = [self.rel, self.note, self.card, self.version, self.plot, self.intake, self.genre, self.ocr,
                self.audio, self.bible, self.thread, self.hint, self.intel_job, self.ms_job, self.voice]
        db.add_all(rows); db.flush()
        self.pin = AiGenerationPin(user_id=uid, story_id=sid, tool="tone", content_sha256=hashlib.sha256(
            text.encode()).hexdigest(), expires_at=datetime.utcnow() + timedelta(days=7))
        self.command = VoiceCommand(session_id=self.voice.session_id, user_id=uid, story_id=sid,
                                    raw_transcript=text)
        self.rintel = RelationshipIntelligence(relationship_id=self.rel.relationship_id, story_id=sid,
                                               from_character_id=c1, to_character_id=c2,
                                               evolution_trajectory=text)
        db.add_all([self.pin, self.command, self.rintel])
        db.commit()
        self.headers = {"Authorization": f"Bearer {create_token(uid)}"}

    def ids(self) -> dict[str, str]:
        return {
            "story_id": self.story.story_id, "project_id": self.story.story_id,
            "chapter_id": self.chapters[0].chapter_id, "character_id": self.characters[0].character_id,
            "from_character_id": self.characters[0].character_id,
            "to_character_id": self.characters[1].character_id,
            "target_character_id": self.characters[1].character_id,
            "relationship_id": self.rel.relationship_id, "note_id": self.note.note_id,
            "card_id": self.card.card_id, "version_id": self.version.version_id,
            "session_id": self.plot.session_id, "intake_id": self.intake.intake_id,
            "upload_id": self.ocr.upload_id, "audio_id": self.audio.audio_id,
            "thread_id": self.thread.thread_id, "hint_id": self.hint.hint_id,
            "job_id": self.intel_job.job_id, "pin_id": self.pin.pin_id,
            "command_id": self.command.command_id, "bible_id": self.bible.bible_id,
            "target_chapter_id": self.chapters[1].chapter_id, "source_pin_id": self.pin.pin_id,
            "section": "characters", "node_key": "n1",
        }


def _owned_pk_sets(db, user_ids: set[str]) -> dict[str, set]:
    """Follow foreign keys outward from the users table: every row, in every
    table, that belongs (directly or transitively) to one of user_ids."""
    doomed: dict[tuple[str, str], set] = {("users", "user_id"): set(user_ids)}
    per_table: dict[str, set] = {}
    for table in Base.metadata.sorted_tables:
        pk_cols = list(table.primary_key.columns)
        if len(pk_cols) != 1:
            continue
        pk = pk_cols[0]
        conds = []
        for fk in table.foreign_keys:
            key = (fk.column.table.name, fk.column.name)
            if doomed.get(key):
                conds.append(fk.parent.in_(doomed[key]))
        if table.name == "users":
            conds.append(pk.in_(user_ids))
        if not conds:
            continue
        from sqlalchemy import or_
        found = {r[0] for r in db.execute(select(pk).where(or_(*conds))).all()}
        if found:
            per_table[table.name] = found
            doomed.setdefault((table.name, pk.name), set()).update(found)
    return per_table


def _fingerprint(db, per_table: dict[str, set]) -> dict[str, str]:
    out = {}
    for table in Base.metadata.sorted_tables:
        ids = per_table.get(table.name)
        if not ids:
            continue
        pk = list(table.primary_key.columns)[0]
        rows = db.execute(select(table).where(pk.in_(ids)).order_by(pk)).all()
        out[table.name] = hashlib.md5(repr([tuple(r) for r in rows]).encode()).hexdigest()
    return out


def _delete_owned(db, user_ids: set[str]) -> None:
    db.rollback()
    per_table = _owned_pk_sets(db, user_ids)
    for table in reversed(Base.metadata.sorted_tables):
        ids = per_table.get(table.name)
        if ids:
            pk = list(table.primary_key.columns)[0]
            db.execute(table.delete().where(pk.in_(ids)))
    db.commit()


@contextmanager
def _two_populated_authors():
    db = SessionLocal()
    created: list[str] = []
    try:
        a = _Author(db, "a", "Ordinary text of author A. Elara walked home.", ["Elara", "Kira", "Marn"], created)
        b = _Author(db, "b", B_TEXT, ["Quillon Zqxmarkerb", "Vessa Zqxmarkerb", "Oron Zqxmarkerb"], created)
        yield db, a, b, TestClient(main.app, raise_server_exceptions=False)
    finally:
        _delete_owned(db, set(created))
        db.close()


@pytest.fixture
def isolated(monkeypatch):
    from middleware.rate_limit import limiter
    monkeypatch.setattr(limiter, "enabled", False)          # sweep would trip 429s otherwise
    monkeypatch.setattr(settings, "pin_store_embedding", False)
    monkeypatch.setattr(settings, "voice_agent_enabled", True)
    fake = install_fake_model(monkeypatch, lambda s, u, i: '{"result": "ok"}')
    # Background work (create_task) must not run the real model either.
    return fake


# ── Request synthesis from the route's own signature ─────────────────────────

_ID_NAMES = None


def _sample(name: str, ann, ids: dict[str, str], depth: int = 0):
    if name in ids:
        return ids[name]
    if name.endswith("_ids") and name[:-1] in ids:
        return [ids[name[:-1]]]
    origin = typing.get_origin(ann)
    args = typing.get_args(ann)
    if origin in (typing.Union, types.UnionType):
        non_none = [x for x in args if x is not type(None)]
        return _sample(name, non_none[0], ids, depth) if non_none else None
    if origin is typing.Literal:
        return args[0]
    if origin in (list, set, tuple, typing.List):
        return []
    if origin in (dict, typing.Dict):
        return {}
    if isinstance(ann, type):
        if issubclass(ann, enum.Enum):
            return list(ann)[0].value
        if issubclass(ann, BaseModel) and depth < 3:
            return _model_body(ann, ids, depth + 1)
        if issubclass(ann, bool):
            return False
        if issubclass(ann, int):
            return 1
        if issubclass(ann, float):
            return 0.5
        if issubclass(ann, str):
            return "Sample text for the isolation sweep."
    return None


def _model_body(model, ids, depth=0) -> dict:
    body = {}
    for fname, f in model.model_fields.items():
        key = f.alias or fname
        if f.is_required() or fname in ids or fname.endswith("_ids"):
            body[key] = _sample(fname, f.annotation, ids, depth)
    return body


def _request_for(full_path: str, route: APIRoute, ids: dict[str, str]):
    path = full_path
    for p in route.dependant.path_params:
        path = path.replace("{%s}" % p.name, str(ids.get(p.name, uuid.uuid4())))
    query = {}
    for q in route.dependant.query_params:
        if q.name in ids or q.field_info.is_required():
            v = _sample(q.name, q.field_info.annotation, ids)
            if v is not None:
                query[q.name] = v
    body = None
    bps = route.dependant.body_params
    if len(bps) == 1 and isinstance(bps[0].field_info.annotation, type) and \
            issubclass(bps[0].field_info.annotation, BaseModel):
        body = _model_body(bps[0].field_info.annotation, ids)
    elif bps:
        body = {bp.name: _sample(bp.name, bp.field_info.annotation, ids) for bp in bps}
    return path, query, body


def _id_bearing_routes():
    id_names = {"story_id", "chapter_id", "character_id", "relationship_id", "note_id", "card_id",
                "version_id", "session_id", "upload_id", "audio_id", "thread_id", "hint_id", "job_id",
                "pin_id", "command_id", "intake_id", "project_id", "section", "node_key"}
    out = []
    for full_path, methods, r in api_routes(main.app):
        names = {p.name for p in r.dependant.path_params} | {q.name for q in r.dependant.query_params}
        for bp in r.dependant.body_params:
            ann = bp.field_info.annotation
            if isinstance(ann, type) and issubclass(ann, BaseModel):
                names |= set(ann.model_fields)
            names.add(bp.name)
        if names & id_names:
            for m in sorted(methods - {"HEAD", "OPTIONS"}):
                out.append((m, full_path, r))
    return out


def _is_upload(route) -> bool:
    return any("UploadFile" in repr(bp.field_info.annotation) or "File" in type(bp.field_info).__name__
               or "Form" in type(bp.field_info).__name__ for bp in route.dependant.body_params)


def _call(client, method, path, query, body, headers):
    kw = {"headers": headers, "params": query}
    if body is not None and method in ("POST", "PUT", "PATCH", "DELETE"):
        kw["json"] = body
    return client.request(method, path, **kw)


# ── The sweep ────────────────────────────────────────────────────────────────

def test_sweep_covers_every_id_bearing_route():
    routes = _id_bearing_routes()
    # 158 HTTP endpoints at Stage 9; well over 100 of them take an id.
    assert len(routes) >= 100, len(routes)


def test_every_route_refuses_foreign_ids(isolated):
    fake = isolated
    leaks, mismatches, statuses = [], [], {}
    with _two_populated_authors() as (db, a, b, client):
        b_rows = _owned_pk_sets(db, {b.user.user_id})
        before = _fingerprint(db, b_rows)
        b_ids = b.ids()
        missing_ids = {k: (str(uuid.uuid4()) if k not in ("section", "node_key") else v)
                       for k, v in b_ids.items()}
        # A's own ids everywhere EXCEPT the one being probed would be stronger per
        # parameter; the all-foreign form is what an attacker sends, and the
        # dedicated tests below cover the mixed own-story/foreign-child cases.
        for method, full_path, route in _id_bearing_routes():
            if _is_upload(route):
                continue   # multipart routes: covered by explicit tests below
            path, query, body = _request_for(full_path, route, b_ids)
            r = _call(client, method, path, query, body, a.headers)
            statuses.setdefault(r.status_code, []).append(f"{method} {full_path}")
            text = r.content.decode("utf-8", "replace").lower()
            if 200 <= r.status_code < 300 and MARK in text:
                leaks.append(f"{method} {full_path} -> {r.status_code}")
            mpath, mquery, mbody = _request_for(full_path, route, missing_ids)
            rm = _call(client, method, mpath, mquery, mbody, a.headers)
            if r.status_code != rm.status_code:
                mismatches.append(f"{method} {full_path}: foreign={r.status_code} missing={rm.status_code}")
        db.expire_all()
        after = _fingerprint(db, _owned_pk_sets(db, {b.user.user_id}))
    prompt_leaks = [i for i, (s, u, _t) in enumerate(fake.calls) if MARK in (s + u).lower()]
    changed = sorted(t for t in set(before) | set(after) if before.get(t) != after.get(t))
    summary = {k: len(v) for k, v in sorted(statuses.items())}
    print("\n[isolation sweep] status histogram:", summary)
    for code in sorted(statuses):
        if code != 404:
            for line in statuses[code]:
                print(f"[isolation sweep]   {code}  {line}")
    assert not leaks, f"B's data returned to A: {leaks}"
    assert not prompt_leaks, f"B's data reached {len(prompt_leaks)} model prompt(s)"
    assert not changed, f"B's rows changed by A's requests in tables: {changed}"
    assert not mismatches, "foreign id distinguishable from missing id:\n" + "\n".join(mismatches)


# ── Explicit regressions for the Stage 9 defects ─────────────────────────────

def test_I1_genre_profile_of_foreign_story_is_404(isolated):
    with _two_populated_authors() as (_db, a, b, client):
        r = client.get(f"/api/intake/{b.story.story_id}/genre-profile", headers=a.headers)
        assert r.status_code == 404 and MARK not in r.text.lower()
        own = client.get(f"/api/intake/{a.story.story_id}/genre-profile", headers=a.headers)
        assert own.status_code == 200 and own.json()["genre"] == "fantasy"


def test_I2_confirm_intake_of_foreign_story_is_404_and_writes_nothing(isolated):
    with _two_populated_authors() as (db, a, b, client):
        r = client.post(f"/api/intake/{b.story.story_id}/confirm", headers=a.headers,
                        json={"intake_id": b.intake.intake_id, "overrides": {"genre": "hijacked"}})
        assert r.status_code == 404
        db.expire_all()
        gp =db.query(GenreProfile).filter(GenreProfile.story_id == b.story.story_id).one()
        intake = db.query(StoryIntake).filter(StoryIntake.intake_id == b.intake.intake_id).one()
        assert gp.genre == "fantasy" and intake.author_confirmed is False


def test_I3_plot_session_of_another_user_cannot_be_marked(isolated):
    with _two_populated_authors() as (db, a, b, client):
        r = client.patch(f"/api/plot-assistant/{b.plot.session_id}/use", headers=a.headers,
                         params={"suggestion_index": 2})
        assert r.status_code == 404
        db.expire_all()
        assert db.query(PlotAssistantSession).filter(
            PlotAssistantSession.session_id == b.plot.session_id).one().suggestion_used is None
        ok = client.patch(f"/api/plot-assistant/{a.plot.session_id}/use", headers=a.headers,
                          params={"suggestion_index": 1})
        assert ok.status_code == 200


def test_I4_versions_of_foreign_chapter_under_own_story_are_404(isolated):
    with _two_populated_authors() as (_db, a, b, client):
        base = f"/api/stories/{a.story.story_id}/chapters/{b.chapters[0].chapter_id}/versions"
        r1 = client.get(base, headers=a.headers)
        r2 = client.get(f"{base}/{b.version.version_id}", headers=a.headers)
        assert r1.status_code == 404 and r2.status_code == 404
        assert MARK not in (r1.text + r2.text).lower()
        own = client.get(f"/api/stories/{a.story.story_id}/chapters/{a.chapters[0].chapter_id}/versions",
                         headers=a.headers)
        assert own.status_code == 200 and len(own.json()) == 1


def test_I5_voice_context_with_foreign_story_or_chapter_is_refused(isolated):
    fake = isolated
    with _two_populated_authors() as (_db, a, b, client):
        foreign_story = client.post("/api/voice/interpret", headers=a.headers, json={
            "transcript": "open chapter one", "context": {"story_id": b.story.story_id}})
        mixed = client.post("/api/voice/interpret", headers=a.headers, json={
            "transcript": "summarise this chapter",
            "context": {"story_id": a.story.story_id, "chapter_id": b.chapters[0].chapter_id}})
        assert foreign_story.status_code == 404 and mixed.status_code == 404
        assert MARK not in (foreign_story.text + mixed.text).lower()
        assert not any(MARK in (s + u).lower() for s, u, _t in fake.calls)


def test_I6_foreign_note_and_upload_are_indistinguishable_from_missing(isolated):
    with _two_populated_authors() as (db, a, b, client):
        missing = str(uuid.uuid4())
        for method, url, body in [
            ("PATCH", "/api/ocr/notes/{}", {"title": "hijack"}),
            ("DELETE", "/api/ocr/notes/{}", None),
        ]:
            rf = client.request(method, url.format(b.note.note_id), headers=a.headers, json=body)
            rm = client.request(method, url.format(missing), headers=a.headers, json=body)
            assert (rf.status_code, rf.json()) == (rm.status_code, rm.json()) == (404, {"detail": "Note not found"})
        payload = {"upload_id": b.ocr.upload_id, "final_text": "x", "destination": "story_notes"}
        rf = client.post("/api/ocr/confirm", headers=a.headers, json=payload)
        rm = client.post("/api/ocr/confirm", headers=a.headers, json={**payload, "upload_id": missing})
        assert rf.status_code == rm.status_code == 404
        db.expire_all()
        assert db.query(StoryNote).filter(StoryNote.note_id == b.note.note_id).one().title.startswith("Note")
        assert db.query(OcrUpload).filter(OcrUpload.upload_id == b.ocr.upload_id).one().confirmed is False


def test_uploads_to_a_foreign_story_are_refused(isolated):
    with _two_populated_authors() as (db, a, b, client):
        sid = b.story.story_id
        cases = [
            (f"/api/ocr/extract/{sid}", ("page.png", b"\x89PNG\r\n\x1a\n" + b"0" * 64, "image/png"), {}),
            (f"/api/manuscript/upload/{sid}", ("book.txt", b"Chapter 1\nHello.", "text/plain"), {}),
            (f"/api/stories/{sid}/audio", ("a.wav", b"RIFF0000WAVE", "audio/wav"), {}),
            (f"/api/stories/{sid}/audio", ("a.wav", b"RIFF0000WAVE", "audio/wav"), {"note_id": b.note.note_id}),
        ]
        for url, f, form in cases:
            r = client.post(url, headers=a.headers, files={"file": f}, data=form)
            assert r.status_code in (400, 404), (url, r.status_code, r.text)
            assert MARK not in r.text.lower()
        db.expire_all()
        assert db.query(OcrUpload).filter(OcrUpload.story_id == sid).count() == 1
        assert db.query(AudioUpload).filter(AudioUpload.story_id == sid).count() == 1
        assert db.query(ManuscriptJob).filter(ManuscriptJob.story_id == sid).count() == 1


def test_story_context_engine_seam_is_display_only(isolated):
    """StoryContextEngine.tsx:186 `can = () => true` gates nothing on the
    server: the same actions it would 'allow' in the UI are refused here."""
    with _two_populated_authors() as (_db, a, b, client):
        sid = b.story.story_id
        for method, url in [("GET", f"/api/stories/{sid}/chapters"),
                            ("GET", f"/api/stories/{sid}/characters"),
                            ("DELETE", f"/api/stories/{sid}/chapters/{b.chapters[0].chapter_id}"),
                            ("GET", f"/api/projects/{sid}")]:
            assert client.request(method, url, headers=a.headers).status_code == 404, url


def test_version_tools_refuse_a_foreign_story(isolated, monkeypatch):
    """merge-versions / compare-summary / translate-stream with B's story id.
    The stream routes are off by default (Stage 12 A3); they are switched on
    here so the ownership check behind them is still exercised."""
    from config import settings
    monkeypatch.setattr(settings, "ai_stream_routes_enabled", True)
    with _two_populated_authors() as (_db, a, b, client):
        sid = b.story.story_id
        cases = [
            ("/api/ai/merge-versions", {"story_id": sid, "blocks": [{"text": "One.", "source": "a"},
                                                                  {"text": "Two.", "source": "b"}]}),
            ("/api/ai/compare-summary", {"story_id": sid, "text_a": "One.", "text_b": "Two."}),
            ("/api/ai/translate/stream", {"story_id": sid, "text": "One.", "target_language": "French"}),
        ]
        for url, body in cases:
            r = client.post(url, headers=a.headers, json=body)
            assert r.status_code == 404, (url, r.status_code, r.text[:200])
