"""Reusable genre-profile context system.

Single source of truth for turning a story's persisted intake intelligence into a
prompt-ready context block. Used by every genre-aware AI tool — selected-text
rewrites (tone/emotion/style/age), chapter tools (continuation/outline) and the
plot assistant — so context is injected consistently and we never duplicate the
formatting logic per router.

Core, author-confirmed fields come from ``genre_profiles`` (respecting overrides).
Richer Story-Intelligence fields (structure, emotional arc, pacing, narrative POV,
comparable titles, market category, themes, conflict, genre conventions) come from
the ``story_intakes.analysis`` snapshot. Everything is clipped so the block stays
concise and does not bloat the model's token budget.
"""
from typing import Optional

from sqlalchemy.orm import Session

from models import GenreProfile, StoryIntake


# Keep the injected block small — these caps bound token usage regardless of how
# verbose the intake analysis was.
_MAX_FIELD_CHARS = 180
_MAX_THEMES = 6
_MAX_COMPS = 3
_MAX_WARNINGS = 5


def get_genre_profile(story_id: str, db: Session) -> Optional[GenreProfile]:
    return db.query(GenreProfile).filter(GenreProfile.story_id == story_id).first()


def _clip(value, limit: int = _MAX_FIELD_CHARS) -> str:
    s = ("" if value is None else str(value)).strip()
    if len(s) <= limit:
        return s
    return s[: limit - 1].rstrip() + "…"


def _join_list(value, limit: int) -> str:
    if isinstance(value, list):
        items = [str(x).strip() for x in value if str(x).strip()]
    elif isinstance(value, str) and value.strip():
        items = [value.strip()]
    else:
        items = []
    return ", ".join(items[:limit])


def build_genre_context(story_id: str, db: Session) -> str:
    """Return a concise, prompt-ready genre/story-intelligence block, or "".

    Safe for any story: returns an empty string when the author skipped Story
    Intake, so callers can pass the result straight into a prompt.
    """
    profile = get_genre_profile(story_id, db)
    intake = db.query(StoryIntake).filter(StoryIntake.story_id == story_id).first()
    analysis = intake.analysis if (intake and isinstance(intake.analysis, dict)) else {}
    return _format(profile, analysis)


def _format(profile: Optional[GenreProfile], analysis: dict) -> str:
    analysis = analysis or {}
    has_core = bool(profile and (profile.genre or profile.sub_genre or profile.tone))
    has_rich = bool(analysis)
    if not has_core and not has_rich:
        return ""

    lines: list[str] = []

    def add(label: str, value: str):
        if value:
            lines.append(f"- {label}: {value}")

    # ── Core (author-confirmed) ───────────────────────────────────────────────
    if profile:
        add("Genre", _clip(profile.genre))
        add("Sub-genre", _clip(profile.sub_genre))
        tones = profile.tone if profile.tone is not None else analysis.get("tone")
        add("Tone", _join_list(tones, 6))
        add("Target audience", _clip(profile.target_audience or analysis.get("audience")))
    else:
        add("Genre", _clip(analysis.get("genre")))
        add("Sub-genre", _clip(analysis.get("sub_genre")))
        add("Tone", _join_list(analysis.get("tone"), 6))
        add("Target audience", _clip(analysis.get("audience")))

    # ── Richer Story-Intelligence (read-only snapshot) ────────────────────────
    add("Narrative POV", _clip(analysis.get("narrative_pov")))
    add("Pacing", _clip(analysis.get("pacing")))
    add("Emotional arc", _clip(analysis.get("emotional_arc")))
    add("Suggested structure", _clip(analysis.get("structure")))
    add("Core conflict / stakes", _clip(analysis.get("conflict")))
    add("Themes", _join_list(analysis.get("themes"), _MAX_THEMES))
    add("Genre blends", _join_list(analysis.get("secondary_genres"), 3))
    add("Comparable tone/positioning", _join_list(analysis.get("comparable_titles"), _MAX_COMPS))
    add("Market category", _clip(analysis.get("marketing_category")))
    add("Content sensitivities", _join_list(analysis.get("content_warnings"), _MAX_WARNINGS))

    # Writing direction: confirmed value first, else the detected snapshot.
    direction = (profile.writing_direction if profile else "") or analysis.get("writing_direction")
    add("Writing direction", _clip(direction))
    add("Craft notes", _clip(analysis.get("intelligence_notes")))

    if not lines:
        return ""

    return (
        "Story genre profile (honor these conventions and the story's expected "
        "mood, structure, pacing and audience promise unless the instruction below "
        "overrides them):\n" + "\n".join(lines)
    )
