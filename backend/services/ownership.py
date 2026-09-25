"""
Ownership resolution for every user-owned identifier Phase 3 accepts
(Stage 7 conflict decision C7-6 and the author's added isolation requirement).

One rule, applied identically everywhere:

    A resource that does not exist and a resource that belongs to someone
    else are INDISTINGUISHABLE to the caller — same status code, same body,
    same warning text. Nothing ever reveals that an id exists.

Direct lookups (a path parameter, or a single referenced id) raise 404 with a
fixed, generic detail string. Batch lookups (context_pin_ids, avoid_pin_ids,
exemplar card ids) never raise per id: unavailable ids are dropped and
reported only as a COUNT in one generic warning, so an expired pin, a deleted
pin, a foreign pin and a made-up id all produce the same observable result.

Every function here filters by the caller's user_id AND the parent story in
the query itself — a foreign row is never loaded into memory and then
rejected, so no code path can accidentally leak it later.
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional

from fastapi import HTTPException

STORY_NOT_FOUND = "Story not found"
CHAPTER_NOT_FOUND = "Chapter not found"
PIN_NOT_FOUND = "Pin not found"
CARD_NOT_FOUND = "Note card not found"


def owned_story(story_id: Optional[str], user_id: str, db):
    """The story if it exists AND belongs to user_id, else 404."""
    from models import Story
    story = None
    if story_id:
        story = db.query(Story).filter(Story.story_id == story_id, Story.user_id == user_id).first()
    if story is None:
        raise HTTPException(status_code=404, detail=STORY_NOT_FOUND)
    return story


def owned_story_or_none(story_id: Optional[str], user_id: str, db):
    """For endpoints where story_id is optional: None stays None (no story
    context is used at all); any supplied id must be owned, else 404."""
    if not story_id:
        return None
    return owned_story(story_id, user_id, db)


def owned_chapter(chapter_id: Optional[str], story_id: str, user_id: str, db):
    """The chapter if it belongs to story_id AND that story belongs to user_id."""
    from models import Chapter, Story
    chapter = None
    if chapter_id:
        chapter = (
            db.query(Chapter)
            .join(Story, Story.story_id == Chapter.story_id)
            .filter(Chapter.chapter_id == chapter_id,
                    Chapter.story_id == story_id,
                    Story.user_id == user_id)
            .first()
        )
    if chapter is None:
        raise HTTPException(status_code=404, detail=CHAPTER_NOT_FOUND)
    return chapter


def owned_chapter_or_none(chapter_id: Optional[str], story_id: Optional[str], user_id: str, db):
    if not chapter_id:
        return None
    if not story_id:
        # A chapter id without its story cannot be ownership-checked
        # against a story scope; treat exactly like an unknown chapter.
        raise HTTPException(status_code=404, detail=CHAPTER_NOT_FOUND)
    return owned_chapter(chapter_id, story_id, user_id, db)


def _live_pin_query(db, story_id: str, user_id: str):
    from models import AiGenerationPin
    return db.query(AiGenerationPin).filter(
        AiGenerationPin.story_id == story_id,
        AiGenerationPin.user_id == user_id,
        # A pin past expires_at is treated as gone even before the hourly
        # sweep deletes it — "expired" and "never existed" look identical.
        AiGenerationPin.expires_at > datetime.utcnow(),
    )


def owned_pin(pin_id: Optional[str], story_id: str, user_id: str, db):
    from models import AiGenerationPin
    pin = None
    if pin_id:
        pin = _live_pin_query(db, story_id, user_id).filter(AiGenerationPin.pin_id == pin_id).first()
    if pin is None:
        raise HTTPException(status_code=404, detail=PIN_NOT_FOUND)
    return pin


def resolve_owned_pins(pin_ids: Iterable[str], story_id: str, user_id: str, db) -> tuple[list, int]:
    """Batch resolution. Returns (pins in the caller's requested order,
    count of ids that were unavailable). Duplicates are collapsed first so
    the count cannot be used to probe anything either."""
    from models import AiGenerationPin
    wanted: list[str] = []
    for pid in pin_ids or []:
        if isinstance(pid, str) and pid and pid not in wanted:
            wanted.append(pid)
    if not wanted:
        return [], 0
    rows = _live_pin_query(db, story_id, user_id).filter(AiGenerationPin.pin_id.in_(wanted)).all()
    by_id = {p.pin_id: p for p in rows}
    ordered = [by_id[p] for p in wanted if p in by_id]
    return ordered, len(wanted) - len(ordered)


def unavailable_pins_warning(count: int) -> Optional[str]:
    """The ONE warning text for unusable pin ids, whatever the reason."""
    if count <= 0:
        return None
    noun = "version was" if count == 1 else "versions were"
    return f"{count} selected {noun} not available (it may have expired or been deleted) and not used."


def owned_card(card_id: Optional[str], user_id: str, db, story_id: Optional[str] = None):
    from models import NoteCard
    card = None
    if card_id:
        q = db.query(NoteCard).filter(NoteCard.card_id == card_id, NoteCard.user_id == user_id)
        if story_id:
            q = q.filter(NoteCard.story_id == story_id)
        card = q.first()
    if card is None:
        raise HTTPException(status_code=404, detail=CARD_NOT_FOUND)
    return card


def resolve_owned_cards(card_ids: Iterable[str], story_id: str, user_id: str, db) -> tuple[list, int]:
    from models import NoteCard
    wanted = [c for c in dict.fromkeys(card_ids or []) if isinstance(c, str) and c]
    if not wanted:
        return [], 0
    rows = db.query(NoteCard).filter(
        NoteCard.card_id.in_(wanted), NoteCard.story_id == story_id, NoteCard.user_id == user_id,
    ).all()
    by_id = {c.card_id: c for c in rows}
    ordered = [by_id[c] for c in wanted if c in by_id]
    return ordered, len(wanted) - len(ordered)
