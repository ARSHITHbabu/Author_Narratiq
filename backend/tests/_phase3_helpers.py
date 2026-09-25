"""
Shared fixtures for the Stage 7 (Phase 3) integration tests.

Every fixture creates its own uniquely-named users/stories and deletes
exactly those rows afterwards (scoped by the ids it created — never by
pattern). The DB safety guard in conftest.py guarantees these only ever run
against an allow-listed test database.
"""
from __future__ import annotations

import sys
import uuid
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import AiGenerationPin, Chapter, Character, NoteCard, Story, StoryPreservationSettings, User  # noqa: E402
from routers.auth import create_token, hash_password  # noqa: E402

CHAPTER_TEXT = (
    "Elara walked down the long corridor. She was tired, and she looked at every door. "
    "Kira waited by the window and said nothing. They had come too far to turn back."
)


class Author:
    def __init__(self, db, tag: str, plan: str | None = None):
        self.user = User(email=f"s7-{tag}-{uuid.uuid4().hex[:8]}@narratiq-internal-test.com",
                         username=f"s7{tag}{uuid.uuid4().hex[:8]}", hashed_password=hash_password("x"), plan=plan)
        db.add(self.user)
        db.flush()
        self.story = Story(user_id=self.user.user_id, title=f"S7 {tag} story")
        db.add(self.story)
        db.flush()
        self.chapters = []
        for n in (1, 2, 3):
            ch = Chapter(story_id=self.story.story_id, title=f"Chapter {n}", chapter_number=n,
                         content=f"<p>{CHAPTER_TEXT}</p>")
            db.add(ch)
            self.chapters.append(ch)
        for name in ("Elara", "Kira", "Marn"):
            db.add(Character(story_id=self.story.story_id, user_id=self.user.user_id, name=name, aliases=[]))
        db.commit()
        self.headers = {"Authorization": f"Bearer {create_token(self.user.user_id)}"}

    @property
    def sid(self) -> str:
        return self.story.story_id

    @property
    def uid(self) -> str:
        return self.user.user_id


def cleanup_authors(db, authors) -> None:
    db.rollback()
    for a in authors:
        uid = a.user.user_id
        db.query(AiGenerationPin).filter(AiGenerationPin.user_id == uid).delete(synchronize_session=False)
        db.query(NoteCard).filter(NoteCard.user_id == uid).delete(synchronize_session=False)
        for s in db.query(Story).filter(Story.user_id == uid).all():
            db.delete(s)
        db.commit()
        u = db.query(User).filter(User.user_id == uid).first()
        if u is not None:
            db.delete(u)
        db.commit()


@contextmanager
def two_authors(plan_a: str | None = None, plan_b: str | None = None):
    db = SessionLocal()
    a = Author(db, "a", plan_a)
    b = Author(db, "b", plan_b)
    try:
        yield db, a, b, TestClient(main.app)
    finally:
        cleanup_authors(db, [a, b])
        db.close()


def pin_payload(content: str = "The corridor breathed. Elara counted four doors.", **extra) -> dict:
    body = {"tool": "tone", "scope": "selection", "tool_params": {"tone": "dark"},
            "content": content, "source_excerpt": "The corridor was long.", "label": ""}
    body.update(extra)
    return body


class FakeModel:
    """Deterministic stand-in for vLLM. `responder(system, user, call_index)`
    returns the model text. Records every prompt so tests can assert what
    reached the model."""

    def __init__(self, responder):
        self.responder = responder
        self.calls: list[tuple[str, str, float]] = []

    async def __call__(self, system, user, temperature=0.0, max_tokens=512, response_format=None):
        self.calls.append((system, user, temperature))
        return self.responder(system, user, len(self.calls) - 1)


def install_fake_model(monkeypatch, responder) -> FakeModel:
    from services import ai_service
    fake = FakeModel(responder)
    monkeypatch.setattr(ai_service, "_complete", fake)

    async def _complete_ex(system, user, temperature=0.0, max_tokens=512, response_format=None):
        return await fake(system, user, temperature, max_tokens, response_format), "stop"
    monkeypatch.setattr(ai_service, "_complete_ex", _complete_ex)   # complete_structured() path

    async def _always_needs_change(text, target, transform_type):
        return True, ""
    monkeypatch.setattr(ai_service, "_assess_change_needed", _always_needs_change)
    return fake


def tiny_plan(monkeypatch, **overrides):
    """Adds a 'test_tiny' plan so cap behaviour is testable without 20+ pins."""
    from dataclasses import replace
    from services import plans
    base = plans._DEFAULT_PLANS["free"]
    values = dict(max_pins=2, max_context_pins=2, max_idea_cards=2, max_style_samples=1)
    values.update(overrides)
    patched = dict(plans._PLANS)
    patched["test_tiny"] = replace(base, **values)
    monkeypatch.setattr(plans, "_PLANS", patched)
