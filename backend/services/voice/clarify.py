"""
Clarification system (E).

Turns a missing internal parameter into a natural, author-facing question that
NEVER mentions internal field names (character_id, story_id, chapter_id, router,
endpoint, …). Where a choice is needed, it offers story-facing names (character
names, chapter titles), not ids.
"""
from __future__ import annotations

# Internal fields the author must never be asked for directly.
_INTERNAL = {"story_id", "chapter_id", "character_id", "project_id", "note_id",
             "version_id", "intake_id", "workflow_id", "command_id"}

_FRIENDLY = {
    "text":            "Select the text you'd like me to change, then try again.",
    "content":         "What should it say?",
    "query":           "What should I search for?",
    "replacement":     "What should I replace it with?",
    "title":           "What would you like to call it?",
    "tone":            "What tone are you going for?",
    "emotion":         "Which emotion should I lean into?",
    "target_age":      "Which audience — children, young adult, or adult?",
    "target_language": "Which language should I translate into?",
    "chapter_goal":    "What should this chapter accomplish?",
    "description":     "Give me a sentence or two describing the story.",
}


def _chapter_options(story_id, db):
    from models import Chapter
    rows = (db.query(Chapter).filter(Chapter.story_id == story_id)
            .order_by(Chapter.chapter_number).all())
    return [{"label": (c.title or f"Chapter {c.chapter_number}"),
             "chapter_number": c.chapter_number} for c in rows]


def _character_options(story_id, db):
    from models import Character
    rows = db.query(Character).filter(Character.story_id == story_id).all()
    return [{"label": c.name} for c in rows if c.name]


def build_clarification(missing: list[str], story_id, db, *, capability: str = ""):
    """Return (question, options) — both author-facing, no internal ids."""
    missing = list(dict.fromkeys(missing))  # de-dup, keep order

    # No story context at all → the author isn't inside a story.
    if "story_id" in missing and not story_id:
        return "Open a story first, then I can help with that.", None

    # Prefer the most user-meaningful missing field for the question.
    if "chapter_id" in missing:
        opts = _chapter_options(story_id, db) if story_id else []
        return "Which chapter?", opts or None
    if "character_id" in missing:
        opts = _character_options(story_id, db) if story_id else []
        return "Which character?", opts or None
    if "version_id" in missing:
        return "Which version would you like to restore?", None

    for f in missing:
        if f in _FRIENDLY:
            return _FRIENDLY[f], None

    # Anything left that is internal must not be surfaced verbatim.
    visible = [f for f in missing if f not in _INTERNAL]
    if visible:
        return f"Could you tell me the {visible[0].replace('_', ' ')}?", None
    return "Could you give me a little more detail?", None
