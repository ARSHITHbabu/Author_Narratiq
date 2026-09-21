"""
Stage 5 — shared transform infrastructure for tasks 5.3 (preservation rules),
5.4 (sentence-level locking), 5.5 (no-change decision layer), 5.6 (strength
control), and 5.11's translation glossary. One shared module so tone,
emotion, audience, and style transforms (5.7-5.10) all hook into the same
mechanism (cross-cutting decision C in the approved design) — translation
(5.11) uses its own glossary-aware check instead, since "preservation" means
something structurally different there (see check_translation_name_consistency).

Nothing here calls the LLM except _assess_change_needed (5.5) and
ensure_translation_glossary (5.11's one-time-per-language glossary build) —
everything else is deterministic: DB reads, regex matching, counting.
"""
from __future__ import annotations

import logging
import re as _re

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# 5.3 — Preservation settings, prompt clause, deterministic check
# ══════════════════════════════════════════════════════════════════════════

class _DefaultPreservationSettings:
    """Stand-in used when a story has no settings row — matches what every
    transform already implicitly tried to do before Stage 5 existed, so a
    story with no row behaves exactly as it did pre-Stage-5."""
    preserve_character_names = True
    preserve_tone = True
    author_notes = ""
    translation_glossary: dict = {}


def get_or_default_preservation_settings(story_id: str | None, db):
    if not story_id or db is None:
        return _DefaultPreservationSettings()
    from models import StoryPreservationSettings
    row = db.query(StoryPreservationSettings).filter(
        StoryPreservationSettings.story_id == story_id
    ).first()
    return row if row is not None else _DefaultPreservationSettings()


def build_preservation_clause(story_id: str | None, db) -> str:
    """
    The prompt-injected constraint clause, assembled in the fixed hierarchy
    order the approved design specifies (author voice → narrative style →
    genre identity → character voice → emotional subtext → literary quality
    → story intent) — enforced by instruction ORDER only (LLMs are
    measurably more compliant with instructions stated first), not by any
    runtime category-judging logic, which would not be deterministic.
    """
    if not story_id or db is None:
        return ""
    settings_row = get_or_default_preservation_settings(story_id, db)

    from models import Character
    characters = db.query(Character).filter(Character.story_id == story_id).all()
    names = sorted({c.name for c in characters if c.name})

    clauses = []
    if getattr(settings_row, "preserve_character_names", True) and names:
        clauses.append(
            "Preserve every character name exactly as written — do not rename, "
            f"omit, or alter: {', '.join(names)}."
        )
    if getattr(settings_row, "preserve_tone", True):
        clauses.append(
            "Preserve the author's underlying narrative voice; change only "
            "what this specific transform asks for."
        )
    notes = getattr(settings_row, "author_notes", "") or ""
    if notes.strip():
        clauses.append(f"Author-defined constraint: {notes.strip()}")
    return " ".join(clauses)


def check_character_name_preservation(original: str, transformed: str, story_id: str | None, db) -> list[str]:
    """
    Deterministic check (task 5.3 §25.3): character names present in
    `original` that vanished from `transformed`. Empty list = no violation.
    Reuses services.ai_service._make_name_pattern so alias matching is
    identical to every other name-matching path in the app (lazy import to
    avoid a circular import — ai_service already imports this module).
    """
    if not story_id or db is None:
        return []
    settings_row = get_or_default_preservation_settings(story_id, db)
    if not getattr(settings_row, "preserve_character_names", True):
        return []

    from models import Character
    from services.ai_service import _make_name_pattern

    characters = db.query(Character).filter(Character.story_id == story_id).all()
    violations = []
    for c in characters:
        pattern = _make_name_pattern(c.name, c.aliases or [])
        if pattern and pattern.search(original) and not pattern.search(transformed):
            violations.append(c.name)
    return violations


# ══════════════════════════════════════════════════════════════════════════
# 5.11 — Translation glossary (a DIFFERENT preservation semantics — see the
# approved correction: names are checked against transliteration, not for
# byte-identity)
# ══════════════════════════════════════════════════════════════════════════

async def ensure_translation_glossary(story_id: str | None, target_language: str, db) -> dict:
    """
    Returns {source_name: translated_name} for (story_id, target_language),
    building it with ONE structured LLM call the first time this pair is
    seen, then caching it on story_preservation_settings. Idempotent:
    subsequent calls for the same (story, language) return the cached
    mapping without another LLM call.

    Deterministic write-path guard against the approved correction's
    explicit requirement ("do not allow the translation glossary to
    silently introduce unsupported character names"): only entries whose
    KEY is a real Character.name for this story are ever written — a
    hallucinated or malformed key from the model's JSON is dropped, not
    stored, and logged.
    """
    if not story_id or db is None:
        return {}

    from models import Character, StoryPreservationSettings

    settings_row = db.query(StoryPreservationSettings).filter(
        StoryPreservationSettings.story_id == story_id
    ).first()
    existing = (settings_row.translation_glossary or {}) if settings_row else {}
    if target_language in existing:
        return existing[target_language]

    characters = db.query(Character).filter(Character.story_id == story_id).all()
    known_names = sorted({c.name for c in characters if c.name})
    if not known_names:
        return {}

    from services.ai_service import complete_structured

    def _coerce_glossary(parsed):
        if not isinstance(parsed, dict):
            return None, len(known_names)
        return parsed, 0

    system = (
        "You are a professional literary translator. For each character name below, "
        f"give its standard transliteration/rendering in {target_language} as it would "
        "naturally appear in a translated novel (not a literal dictionary translation of "
        "the word, unless the name is not proper-noun-like). Return ONLY a JSON object "
        "mapping each EXACT input name to its transliteration, e.g. "
        '{"Devika": "デヴィカ"}. Include every name listed, unchanged if a '
        "name is already used as-is in the target language."
    )
    user = "Names:\n" + "\n".join(known_names)
    result, meta = await complete_structured(
        system, user, coerce=_coerce_glossary,
        temperature=0.1, max_tokens=300, label="translation_glossary",
    )

    mapping: dict[str, str] = {}
    if isinstance(result, dict):
        for k, v in result.items():
            if k in known_names and isinstance(v, str) and v.strip():
                mapping[k] = v.strip()
            else:
                logger.warning(
                    "[translation_glossary] refused unrecognized/malformed entry "
                    "%r -> %r for story=%s target=%s — not a known character name",
                    k, v, story_id[:8], target_language,
                )
    # Names the model dropped entirely still get a deterministic fallback:
    # untransliterated (their own name), never silently absent from the map.
    for name in known_names:
        mapping.setdefault(name, name)

    if settings_row is None:
        settings_row = StoryPreservationSettings(story_id=story_id, translation_glossary={})
        db.add(settings_row)
        db.flush()
    glossary = dict(settings_row.translation_glossary or {})
    glossary[target_language] = mapping
    settings_row.translation_glossary = glossary
    db.commit()
    return mapping


def build_translation_glossary_clause(glossary: dict) -> str:
    if not glossary:
        return ""
    pairs = "; ".join(f"{src} → {dst}" for src, dst in glossary.items())
    return f"Use these exact name translations consistently: {pairs}."


def check_translation_name_consistency(original: str, transformed: str, glossary: dict) -> dict:
    """
    Translation's version of the preservation check (task 5.11, per the
    approved correction): a name is NOT a violation merely for no longer
    being byte-identical — it is checked against the glossary's approved
    transliteration, or against being left as-is (both legitimate). Only a
    name that is NEITHER its original form NOR its glossary form anywhere
    in the output is reported as missing.
    """
    missing = []
    for source_name, translated_name in glossary.items():
        if source_name not in original:
            continue
        if translated_name in transformed or source_name in transformed:
            continue
        missing.append(source_name)
    return {"missing": missing}


# ══════════════════════════════════════════════════════════════════════════
# 5.6 — Strength control: measurable, not just prompt wording
# ══════════════════════════════════════════════════════════════════════════

STRENGTH_LEVELS = ("light", "moderate", "strong")

_STRENGTH_CLAUSES = {
    "light": (
        "STRENGTH: light. Edit word choice and connectives only. Do not restructure "
        "sentences, and do not add or remove clauses or sentences."
    ),
    "moderate": (
        "STRENGTH: moderate. Sentence-level rewriting is allowed, but do not add, "
        "remove, or reorder paragraphs."
    ),
    "strong": (
        "STRENGTH: strong. Full rewrite is allowed within the preservation constraints "
        "already stated above."
    ),
}


def build_strength_clause(strength: str) -> str:
    return _STRENGTH_CLAUSES.get(strength, _STRENGTH_CLAUSES["light"])


def _count_sentences(text: str) -> int:
    return len([s for s in _re.split(r"(?<=[.!?])\s+", text.strip()) if s])


def _count_paragraphs(text: str) -> int:
    return len([p for p in text.split("\n\n") if p.strip()]) or 1


def check_strength_violation(original: str, transformed: str, strength: str) -> bool:
    """
    Deterministic proxy for "did the model exceed the requested edit
    degree" — cheap (count-based), not a semantic diff, deliberately: a
    coarse, reproducible signal is preferred over an expensive one per the
    approved design's own "do not overengineer" instruction.
    """
    if strength == "light":
        return abs(_count_sentences(original) - _count_sentences(transformed)) > 1
    if strength == "moderate":
        return _count_paragraphs(original) != _count_paragraphs(transformed)
    return False  # "strong" has no structural ceiling beyond preservation rules


# ══════════════════════════════════════════════════════════════════════════
# 5.4 — Sentence-level lock and partial regeneration
# ══════════════════════════════════════════════════════════════════════════

class LockedRange:
    __slots__ = ("start", "end")

    def __init__(self, start: int, end: int):
        self.start, self.end = start, end


def mark_locked_segments(text: str, locked_ranges: list[dict] | None) -> tuple[str, list[dict]]:
    """
    Splits `text` into an ordered list of segments, each tagged locked/not,
    and returns (marked_text_for_the_model, segments) where marked_text
    wraps locked spans in [KEEP]...[/KEEP] and unlocked spans in
    [REWRITE]...[/REWRITE]. Ranges are character offsets into `text` itself
    (the already-captured selection substring — see the approved design's
    contract), not document-absolute positions.
    """
    if not locked_ranges:
        return text, [{"locked": False, "text": text}]

    ranges = sorted(
        (LockedRange(r["start"], r["end"]) for r in locked_ranges),
        key=lambda r: r.start,
    )
    segments = []
    cursor = 0
    for r in ranges:
        if r.start > cursor:
            segments.append({"locked": False, "text": text[cursor:r.start]})
        segments.append({"locked": True, "text": text[r.start:r.end]})
        cursor = r.end
    if cursor < len(text):
        segments.append({"locked": False, "text": text[cursor:]})

    marked = "".join(
        f"[KEEP]{s['text']}[/KEEP]" if s["locked"] else f"[REWRITE]{s['text']}[/REWRITE]"
        for s in segments
    )
    return marked, segments


def reconstruct_with_locks(model_output: str, segments: list[dict]) -> tuple[str | None, bool]:
    """
    Splits the model's marked output back into segments and reconstructs the
    final text — but NEVER trusts the model's copy of a [KEEP] segment: it
    always splices in the ORIGINAL captured bytes for locked segments,
    unconditionally. This is what makes the byte-identity guarantee true by
    construction, not by validating the model's output after the fact.

    Returns (reconstructed_text_or_None, shape_ok). shape_ok=False means the
    model's output didn't have the expected number of [REWRITE] segments —
    the caller's retry ladder handles that case; this function never guesses.
    """
    rewrite_pattern = _re.compile(r"\[REWRITE\](.*?)\[/REWRITE\]", _re.DOTALL)
    model_rewrites = rewrite_pattern.findall(model_output)

    expected_rewrite_count = sum(1 for s in segments if not s["locked"])
    if len(model_rewrites) != expected_rewrite_count:
        return None, False

    rewrite_iter = iter(model_rewrites)
    out_parts = []
    for s in segments:
        if s["locked"]:
            out_parts.append(s["text"])  # original bytes, never the model's echo
        else:
            out_parts.append(next(rewrite_iter))
    return "".join(out_parts), True


def verify_lock_byte_identity(original_segments: list[dict], reconstructed: str) -> bool:
    """Regression-guard assertion: every locked segment's bytes must appear,
    unmodified, in the reconstructed output. Exact string containment check
    — no normalization, no whitespace trimming, matching the approved
    'exact equality including whitespace and punctuation' requirement."""
    for s in original_segments:
        if s["locked"] and s["text"] not in reconstructed:
            return False
    return True
