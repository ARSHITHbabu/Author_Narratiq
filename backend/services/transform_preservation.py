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


def build_preservation_clause(story_id: str | None, db, rules: dict | None = None) -> str:
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
    # Stage 7: when resolved Phase 3 rules are supplied (request → project →
    # server), they decide; otherwise the Stage 5 DB-settings behaviour is
    # used unchanged. Only an explicit True puts a rule in the prompt —
    # "warn" means check-and-report only.
    names_on = (rules.get("character_names") is True) if rules is not None \
        else getattr(settings_row, "preserve_character_names", True)
    tone_on = (rules.get("tone") is True) if rules is not None \
        else getattr(settings_row, "preserve_tone", True)

    from models import Character
    characters = db.query(Character).filter(Character.story_id == story_id).all()
    names = sorted({c.name for c in characters if c.name})

    clauses = []
    if names_on and names:
        clauses.append(
            "Preserve every character name exactly as written — do not rename, "
            f"omit, or alter: {', '.join(names)}."
        )
    if tone_on:
        clauses.append(
            "Preserve the author's underlying narrative voice; change only "
            "what this specific transform asks for."
        )
    notes = getattr(settings_row, "author_notes", "") or ""
    if notes.strip():
        clauses.append(f"Author-defined constraint: {notes.strip()}")
    return " ".join(clauses)


def check_character_name_preservation(original: str, transformed: str, story_id: str | None, db,
                                      rules: dict | None = None) -> list[str]:
    """
    Deterministic check (task 5.3 §25.3): character names present in
    `original` that vanished from `transformed`. Empty list = no violation.
    Reuses services.ai_service._make_name_pattern so alias matching is
    identical to every other name-matching path in the app (lazy import to
    avoid a circular import — ai_service already imports this module).
    """
    if not story_id or db is None:
        return []
    if rules is not None:
        if rules.get("character_names") not in (True, "warn"):
            return []
    else:
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



# ══════════════════════════════════════════════════════════════════════════
# Stage 7 (Phase 3 P3-02 / P3-05 acceptance gaps) — locked-range validation,
# rule resolution, and the conservative deterministic checks of spec §25.3.
#
# Guiding rule (author decision, Stage 7 approval): heuristic checks only
# ever WARN. Nothing here rewrites author or model text; name "autofix" is a
# suggestion payload the author applies with an explicit click. Only rules
# the author explicitly set to True can trigger the single repair retry.
# ══════════════════════════════════════════════════════════════════════════

def validate_locked_ranges(text: str, locked_ranges: list[dict] | None) -> None:
    """Rejects ranges that would corrupt reassembly (out of bounds, empty,
    overlapping) or leave nothing to regenerate (spec edge case E4).
    Raises exceptions.ApiError(422) — never silently clamps an offset."""
    if not locked_ranges:
        return
    from exceptions import ApiError
    n = len(text)
    ordered = sorted(locked_ranges, key=lambda r: r["start"])
    prev_end = -1
    for r in ordered:
        start, end = r["start"], r["end"]
        if start < 0 or end > n or start >= end:
            raise ApiError(422, "A locked sentence no longer matches the selected text. "
                                "Reselect the passage and lock the sentences again.",
                           code="invalid_locked_range")
        if start < prev_end:
            raise ApiError(422, "Two locked sentences overlap. Reselect the passage and lock them again.",
                           code="invalid_locked_range")
        prev_end = end
    covered = [False] * n
    for r in ordered:
        for i in range(r["start"], r["end"]):
            covered[i] = True
    if all(covered[i] or text[i].isspace() for i in range(n)):
        raise ApiError(422, "Every sentence is locked, so there is nothing left to rewrite. "
                            "Unlock at least one sentence.",
                       code="no_unlocked_segments")


# Server defaults (spec §25.1's DEFAULT_PRESERVE_RULES, with Stage 7's
# conservative interpretation): names and tone keep their Stage 5 behaviour;
# the new heuristic checks default to "warn" (report only, no prompt change,
# no retry) so a default request's prompt stays byte-identical to Stage 5.
DEFAULT_PRESERVE_RULES: dict = {
    "character_names": True,
    "tone": True,
    "tense": "warn",
    "pov": "warn",
    "dialogue_meaning": "warn",
    "timeline": "warn",
    "story_facts": False,
}
PRESERVE_RULE_KEYS = tuple(DEFAULT_PRESERVE_RULES)


def _valid_rule_value(v) -> bool:
    return v is True or v is False or v == "warn"


def resolve_preserve_rules(story_id: str | None, db, request_overrides: dict | None = None) -> dict:
    """Resolution order (spec §25.1): this request → project defaults →
    server default. None at any level means inherit."""
    resolved = dict(DEFAULT_PRESERVE_RULES)
    if story_id and db is not None:
        row = get_or_default_preservation_settings(story_id, db)
        resolved["character_names"] = bool(getattr(row, "preserve_character_names", True))
        resolved["tone"] = bool(getattr(row, "preserve_tone", True))
        for k, v in (getattr(row, "preserve_rules", None) or {}).items():
            if k in resolved and k not in ("character_names", "tone") and _valid_rule_value(v):
                resolved[k] = v
    for k, v in (request_overrides or {}).items():
        if k in resolved and v is not None and _valid_rule_value(v):
            resolved[k] = v
    return resolved


# ── Language / quotation helpers ──────────────────────────────────────────

_EN_STOPWORDS = frozenset(
    "the a an and or but of to in on at for with from by as is was were are be been "
    "he she it they we you i his her their our my your this that not no".split()
)
_QUOTE_RE = _re.compile(r'"[^"]{1,2000}"|“[^”]{1,2000}”')
_WORD_RE = _re.compile(r"[A-Za-z']+")


def is_probably_english(text: str) -> bool:
    words = [w.lower() for w in _WORD_RE.findall(text or "")]
    if len(words) < 8:
        return False
    letters = [c for c in text if c.isalpha()]
    if letters and sum(1 for c in letters if c.isascii()) / len(letters) < 0.9:
        return False
    return sum(1 for w in words if w in _EN_STOPWORDS) / len(words) >= 0.15


def _narration(text: str) -> str:
    """Text with quoted dialogue removed — dialogue legitimately uses other
    tenses and persons than the narration around it."""
    return _QUOTE_RE.sub(" ", text or "")


def quoted_spans(text: str) -> list[str]:
    return [m.group(0)[1:-1] for m in _QUOTE_RE.finditer(text or "")]


# ── Tense ────────────────────────────────────────────────────────────────

_PAST_WORDS = frozenset(
    "was were had did said went came saw took knew thought felt looked made told gave found "
    "left stood sat ran heard began seemed turned kept held brought wrote spoke stopped".split()
)
_PRESENT_WORDS = frozenset(
    "is are am has does says goes comes sees takes knows thinks feels looks makes tells gives finds "
    "leaves stands sits runs hears begins seems turns keeps holds brings writes speaks stops".split()
)


# Base forms count as present ONLY directly after a plural/1st/2nd-person
# subject ("I walk", "they wait") — on their own they are too ambiguous.
_BASE_VERBS = frozenset(
    "walk look turn wait go come see take know think feel make tell give find leave stand sit "
    "run hear begin seem keep hold bring write speak stop open close move watch want need try "
    "ask say".split()
)
_BASE_SUBJECTS = frozenset("i we you they".split())


def tense_profile(text: str) -> tuple[int, int]:
    past = present = 0
    prev = ""
    for w in _WORD_RE.findall(_narration(text)):
        lw = w.lower()
        if lw in _PAST_WORDS or (len(lw) > 4 and lw.endswith("ed")):
            past += 1
        elif lw in _PRESENT_WORDS or lw == "am" or (lw in _BASE_VERBS and prev in _BASE_SUBJECTS):
            present += 1
        prev = lw
    return past, present


def dominant_tense(text: str, min_markers: int = 4) -> str | None:
    past, present = tense_profile(text)
    if past + present < min_markers:
        return None
    return "past" if past >= present else "present"


def check_tense_shift(source: str, output: str, margin: float) -> bool:
    """True only when the narration's dominant tense clearly flips. Needs at
    least 4 markers on each side and a balance swing larger than `margin`."""
    sp, sn = tense_profile(source)
    op, on = tense_profile(output)
    if sp + sn < 4 or op + on < 4:
        return False
    s_bal = (sp - sn) / (sp + sn)
    o_bal = (op - on) / (op + on)
    return (s_bal > 0) != (o_bal > 0) and abs(s_bal - o_bal) > margin * 2


# ── Point of view ────────────────────────────────────────────────────────

_POV_WORDS = {
    "first": frozenset("i me my mine myself we us our ours ourselves".split()),
    "second": frozenset("you your yours yourself yourselves".split()),
    "third": frozenset("he him his himself she her hers herself they them their theirs themselves".split()),
}


def pov_profile(text: str) -> dict[str, int]:
    counts = {k: 0 for k in _POV_WORDS}
    for w in _WORD_RE.findall(_narration(text)):
        lw = w.lower()
        for k, words in _POV_WORDS.items():
            if lw in words:
                counts[k] += 1
    return counts


def dominant_pov(text: str, min_pronouns: int = 5) -> str | None:
    c = pov_profile(text)
    total = sum(c.values())
    if total < min_pronouns:
        return None
    return max(c, key=c.get)


def check_pov_shift(source: str, output: str, margin: float) -> bool:
    sc, oc = pov_profile(source), pov_profile(output)
    st, ot = sum(sc.values()), sum(oc.values())
    if st < 5 or ot < 5:
        return False
    s_dom, o_dom = max(sc, key=sc.get), max(oc, key=oc.get)
    if s_dom == o_dom:
        return False
    return (oc[o_dom] / ot) - (sc[o_dom] / st) > margin


# ── Dialogue meaning ─────────────────────────────────────────────────────

def _norm_words(s: str) -> str:
    return " ".join(_re.sub(r"[^\w\s]", " ", (s or "").lower()).split())


def check_dialogue_changes(source: str, output: str, min_similarity: float) -> list[str]:
    """Soft check: quoted speech in the source should survive in meaning.
    Returns human-readable issues; empty when nothing to report."""
    from difflib import SequenceMatcher
    src, out = quoted_spans(source), quoted_spans(output)
    if not src:
        return []
    if len(src) != len(out):
        return [f"The passage had {len(src)} line(s) of dialogue; the rewrite has {len(out)}."]
    issues = []
    for i, (a, b) in enumerate(zip(src, out), start=1):
        if SequenceMatcher(None, _norm_words(a), _norm_words(b)).ratio() < min_similarity:
            issues.append(f"Dialogue line {i} was reworded substantially.")
    return issues[:3]


# ── Timeline markers ─────────────────────────────────────────────────────

_NUM = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|a few|several)"
_TIME_PATTERNS = [
    r"\byesterday\b", r"\btomorrow\b", r"\btonight\b",
    r"\b(?:next|last|the following|the previous) (?:day|night|morning|evening|week|month|year|summer|winter|spring|autumn)\b",
    rf"\b{_NUM} (?:hours?|days?|weeks?|months?|years?|decades?) (?:later|ago|before|after|earlier)\b",
    r"\b(?:at|by|before|until|after) (?:dawn|dusk|midnight|noon|sunrise|sunset|daybreak|nightfall|morning|evening|night)\b",
    r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    r"\b(?:january|february|march|april|june|july|august|september|october|november|december)\b",
    r"\bin \d{3,4}\b",
]
_TIME_RE = _re.compile("|".join(_TIME_PATTERNS), _re.IGNORECASE)

# Equivalent times of day are one class: rewording "by morning" as "by dawn"
# is not a new time reference (found by the Stage 7 golden-set measurement —
# tests/fixtures/preservation_checks_measurement.json).
_TIME_OF_DAY = {
    "dawn": "morning", "sunrise": "morning", "daybreak": "morning", "morning": "morning",
    "dusk": "evening", "sunset": "evening", "evening": "evening",
    "midnight": "night", "nightfall": "night", "night": "night", "noon": "noon",
}
_TOD_RE = _re.compile(r"^(?:at|by|before|until|after) (\w+)$")


def _marker_class(marker: str) -> str:
    m = _TOD_RE.match(marker)
    if m and m.group(1) in _TIME_OF_DAY:
        return f"time-of-day:{_TIME_OF_DAY[m.group(1)]}"
    return marker


def temporal_markers(text: str) -> set[str]:
    return {m.group(0).lower() for m in _TIME_RE.finditer(text or "")}


def _source_classes(text: str) -> set[str]:
    """Classes already present in the source — includes bare time-of-day
    words ("the morning was cold") so a rewrite that makes them explicit is
    not reported as an addition."""
    classes = {_marker_class(m) for m in temporal_markers(text)}
    for w in _re.findall(r"[a-z]+", (text or "").lower()):
        if w in _TIME_OF_DAY:
            classes.add(f"time-of-day:{_TIME_OF_DAY[w]}")
    return classes


def check_timeline_additions(source: str, output: str) -> list[str]:
    have = _source_classes(source)
    added = {m for m in temporal_markers(output) if _marker_class(m) not in have}
    return sorted(added)[:5]


# ── Character names: autofix suggestions ─────────────────────────────────

def suggest_name_autofix(output: str, missing_names: list[str], story_id: str | None, db) -> list[dict]:
    """For each character name the model dropped, find a near-miss spelling
    in the output (e.g. "Elarah" for "Elara") that is NOT itself a known
    character or alias. Returned as {replace, with} pairs the author can
    apply with one click — never applied automatically."""
    if not missing_names or not story_id or db is None:
        return []
    from difflib import SequenceMatcher
    from models import Character
    known = set()
    for c in db.query(Character).filter(Character.story_id == story_id).all():
        known.add((c.name or "").lower())
        known.update(a.lower() for a in (c.aliases or []) if a)
    candidates = {w for w in _re.findall(r"\b[A-Z][a-zA-Z'-]{1,}\b", output or "")}
    fixes: list[dict] = []
    for name in missing_names:
        first = name.split()[0]
        best, best_score = None, 0.0
        for cand in candidates:
            if cand.lower() in known or cand.lower() in _EN_STOPWORDS:
                continue
            score = SequenceMatcher(None, cand.lower(), first.lower()).ratio()
            if score > best_score:
                best, best_score = cand, score
        if best and best_score >= 0.75 and best != first:
            fixes.append({"replace": best, "with": first})
    return fixes


def verify_preservation(source: str, output: str, rules: dict, *, tool: str) -> list[dict]:
    """Deterministic, conservative post-generation checks (spec §25.3) for
    the rules the name check does not already cover. Returns warning dicts
    in the schemas.GenerationWarning shape. Severity "hard" is only used for
    rules the author explicitly enforced (True); "warn" rules are soft.
    Tense/POV are skipped for translation and non-English text (E13, E14)."""
    from config import settings
    warnings: list[dict] = []
    english = is_probably_english(source)
    tense_pov_applicable = tool != "translate" and english

    def _sev(key: str) -> str:
        return "hard" if rules.get(key) is True else "soft"

    if rules.get("tense") in (True, "warn") and tense_pov_applicable:
        if check_tense_shift(source, output, settings.tense_flip_margin):
            warnings.append({"kind": "tense_shift", "severity": _sev("tense"),
                             "message": f"The rewrite appears to switch the narration from "
                                        f"{dominant_tense(source) or 'its'} tense to {dominant_tense(output) or 'another'} tense."})
    if rules.get("pov") in (True, "warn") and tense_pov_applicable:
        if check_pov_shift(source, output, settings.pov_shift_margin):
            warnings.append({"kind": "pov_shift", "severity": _sev("pov"),
                             "message": f"The rewrite appears to change the point of view from "
                                        f"{dominant_pov(source) or 'the original'} person to {dominant_pov(output) or 'another'} person."})
    if rules.get("dialogue_meaning") in (True, "warn") and tool not in ("translate",):
        for issue in check_dialogue_changes(source, output, settings.dialogue_similarity_min):
            warnings.append({"kind": "dialogue_changed", "severity": "soft", "message": issue})
    if rules.get("timeline") in (True, "warn") and english:
        added = check_timeline_additions(source, output)
        if added:
            warnings.append({"kind": "timeline_added", "severity": "soft",
                             "message": "The rewrite adds time references that were not in your text: "
                                        + ", ".join(f"“{a}”" for a in added) + "."})
    return warnings


def build_extra_rules_clause(rules: dict, source: str, story_dna=None) -> str:
    """Prompt text for the rules the author explicitly ENFORCED (True) beyond
    names/tone — with concrete values interpolated (spec §25.2). Empty for
    default rules, so a default request's prompt is unchanged."""
    parts = []
    if rules.get("tense") is True:
        tense = (getattr(story_dna, "tense", "") or "").strip() or dominant_tense(source)
        parts.append(f"Keep the narration in {tense} tense." if tense else "Keep the narration's tense exactly as written.")
    if rules.get("pov") is True:
        pov = (getattr(story_dna, "pov_style", "") or "").strip()
        if not pov:
            dom = dominant_pov(source)
            pov = f"{dom} person" if dom else ""
        parts.append(f"Keep the point of view ({pov})." if pov else "Keep the point of view exactly as written.")
    if rules.get("dialogue_meaning") is True:
        parts.append("Keep every line of dialogue saying the same thing; do not add or remove spoken lines.")
    if rules.get("timeline") is True:
        parts.append("Do not add new time references (days, dates, 'later', 'ago').")
    if rules.get("story_facts") is True:
        parts.append("Do not contradict or add to the established story facts provided.")
    return " ".join(parts)
