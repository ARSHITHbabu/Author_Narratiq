"""
Stage 5 task 5.1 — prompt versioning registry.

A version identifier resolves to ACTUAL prompt-building functions, not merely
a logged label. Reverting to a prior version means calling a different
function from this registry — never a code change, per task 5.1's own
definition of done.

"v1" is the frozen pre-Stage-5 baseline: every builder under "v1" is a
byte-identical copy of the prompt-construction logic as it existed at the
close of Stage 4, and is never edited again once Stage 5 work begins — it is
the thing every later version is measured against (task 5.2's baseline).

"v2" is Stage 5's improved prompts (tasks 5.3, 5.5, 5.6, 5.7-5.11 land here).
One version bump covering the whole stage, not one per task — the checklist
only requires "a distinct version" for later changes, and per-task versions
would be registry bookkeeping with no measurable benefit over one clean
before/after pair. New tasks that touch prompts again later add "v3" etc.
without editing "v1" or "v2".

Deliberately NOT a database table or an admin UI — a small code/config
registry is what task 5.1 asks for, and everything it needs (import-time
availability, code review for changes, git history for prompt changes) is
better served by code than by a runtime-editable store.
"""
from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)


def _with_genre(system: str, genre_context: str) -> str:
    """Prepend the story's genre profile to a system prompt when available.
    Duplicated (not imported) from ai_service.py deliberately: it is a
    trivial, stateless two-line function, and duplicating it here avoids a
    circular import between this module and ai_service.py. If it ever
    changes, both copies must change together — small enough surface that a
    grep before editing is sufficient; not worth a shared-utils module for
    one two-line function."""
    return f"{genre_context}\n\n{system}" if genre_context else system


# ══════════════════════════════════════════════════════════════════════════
# v1 — frozen pre-Stage-5 baseline. DO NOT EDIT once Stage 5 work begins.
# ══════════════════════════════════════════════════════════════════════════

def _tone_v1(tone: str, genre_context: str, **_ignored) -> str:
    return _with_genre(
        f"You are a literary writing coach. Rewrite the passage in a {tone} tone. "
        "Keep all events and characters identical — only change style, word choice, and mood. "
        "Return ONLY the rewritten passage.",
        genre_context,
    )


def _emotion_v1(emotion: str, intensity: str, genre_context: str, **_ignored) -> str:
    return _with_genre(
        f"You are a fiction editor. Rewrite the passage so it deeply conveys {emotion} at "
        f"{intensity} intensity using sensory detail and interiority — not emotional labels. "
        "Return ONLY the rewritten passage.",
        genre_context,
    )


_AGE_GUIDE_V1 = {
    "children": "children aged 5–10 — simple vocabulary, short sentences, no violence or adult themes",
    "ya":       "young adult readers aged 10–18 — age-appropriate complexity and themes",
    "adult":    "adult readers — full vocabulary and thematic depth",
}


def _age_adapt_v1(target_age: str, genre_context: str, **_ignored) -> str:
    guide = _AGE_GUIDE_V1.get(target_age, _AGE_GUIDE_V1["adult"])
    return _with_genre(
        f"You are an editor. Adapt the text for {guide}. "
        "Preserve the story meaning. Return ONLY the adapted text.",
        genre_context,
    )


def _style_v1(style: str, genre_context: str, **_ignored) -> str:
    return _with_genre(
        f"Rewrite the passage in the literary style of {style} — capturing their characteristic "
        "sentence structure, diction, rhythm, and voice. Return ONLY the rewritten passage.",
        genre_context,
    )


def _translate_v1(source_language: str, target_language: str, **_ignored) -> str:
    return (
        f"You are a professional literary translator. Translate from {source_language} to "
        f"{target_language}, preserving tone, style, and literary quality. Return ONLY the translation."
    )


def _suggestions_v1(**_ignored) -> str:
    return (
        "You are a literary coach giving manuscript feedback. Analyse the excerpt and return ONLY "
        "a JSON array of exactly 4 objects: {id: int, category: string, text: string, reason: string}. "
        "Categories: Prose Quality | Show Don't Tell | Dialogue | Pacing | Characterisation | Structure."
    )


def _author_style_v1(author: str, genre_context: str, **_ignored) -> str:
    # Author-style is not one of Stage 5's targeted transforms (5.7-5.11 map to
    # tone/emotion/audience/style/translation) and already has its own strong,
    # hand-written preservation clause (_AUTHOR_SAFETY_CLAUSE) plus copyright-
    # safety logic that must not be duplicated or drift out of sync. v1 and v2
    # both delegate to the existing, unchanged function — registered here only
    # so it participates in version logging/tracing like every other transform.
    from services.ai_service import _author_style_system
    return _author_style_system(author, genre_context)


PROMPT_REGISTRY: dict[str, dict[str, Callable]] = {
    "v1": {
        "tone": _tone_v1,
        "emotion": _emotion_v1,
        "age_adapt": _age_adapt_v1,
        "style": _style_v1,
        "translate": _translate_v1,
        "suggestions": _suggestions_v1,
        "author_style": _author_style_v1,
    },
}


# ══════════════════════════════════════════════════════════════════════════
# v2 — Stage 5 improved prompts. One version bump covering the whole stage's
# prompt-level changes (tasks 5.7-5.11), not one per task — the checklist
# only requires "a distinct version" for later changes, and per-task
# versions would be pure registry bookkeeping with no measurable benefit.
# v1 above is never edited; this is purely additive.
#
# Every v2 builder accepts two new optional kwargs beyond v1's own params:
#   preservation_clause — task 5.3's constraint clause (character names,
#                          tone, author notes), already-assembled by
#                          services.transform_preservation.build_preservation_clause
#   strength_clause      — task 5.6's edit-degree instruction, already-
#                          assembled by
#                          services.transform_preservation.build_strength_clause
# Both default to "" so a caller that hasn't wired them yet still gets valid
# (if unconstrained) output rather than a TypeError.
# ══════════════════════════════════════════════════════════════════════════

def _tone_v2(tone: str, genre_context: str, preservation_clause: str = "",
             strength_clause: str = "", **_ignored) -> str:
    base = (
        f"You are a literary writing coach. Rewrite the passage in a {tone} tone, "
        "adjusting the AUTHOR'S OWN voice, not replacing it with a generic one — "
        "keep their sentence rhythm and characteristic phrasing wherever the tone "
        "shift doesn't require changing it. "
        "Keep all events and characters identical — only change style, word choice, "
        "and mood. Do NOT add new metaphors, imagery, or figurative language that "
        "isn't already present in some form in the original — a tone shift should "
        "feel like the same scene lit differently, not a different scene. "
        "Make the smallest change that achieves the requested tone; do not rewrite "
        "sentences that are already consistent with the target tone. "
        "Return ONLY the rewritten passage."
    )
    if preservation_clause:
        base += f" {preservation_clause}"
    if strength_clause:
        base += f" {strength_clause}"
    return _with_genre(base, genre_context)


def _emotion_v2(emotion: str, intensity: str, genre_context: str,
                 preservation_clause: str = "", strength_clause: str = "", **_ignored) -> str:
    base = (
        f"You are a fiction editor. Rewrite the passage so it conveys {emotion} at "
        f"{intensity} intensity using sensory detail and interiority — not emotional "
        "labels. If the original passage is already emotionally restrained or "
        "understated, PRESERVE that restraint: conveying an emotion more clearly "
        "does not mean stating it more explicitly or adding more emotional language "
        "than the scene's own register supports. Preserve whatever subtext and "
        "nuance the original already carries — do not flatten an ambiguous or "
        "mixed feeling into a single clean emotion. Avoid generic emotional "
        "phrasing ('her heart raced', 'tears welled up') unless the original "
        "already leans that way. "
        "Return ONLY the rewritten passage."
    )
    if preservation_clause:
        base += f" {preservation_clause}"
    if strength_clause:
        base += f" {strength_clause}"
    return _with_genre(base, genre_context)


_AGE_GUIDE_V2 = dict(_AGE_GUIDE_V1)  # same guide text; only the instruction around it changes


def _age_adapt_v2(target_age: str, genre_context: str,
                   preservation_clause: str = "", strength_clause: str = "", **_ignored) -> str:
    guide = _AGE_GUIDE_V2.get(target_age, _AGE_GUIDE_V2["adult"])
    base = (
        f"You are an editor. Adapt the text for {guide}. Adjust VOCABULARY and "
        "SENTENCE COMPLEXITY only — do not change who is narrating, their age, or "
        "their perspective on events; do not remove emotional depth, only make it "
        "accessible at the target complexity level. Preserve the story meaning and "
        "literary quality; simplifying language is not the same as flattening the "
        "writing. Return ONLY the adapted text."
    )
    if preservation_clause:
        base += f" {preservation_clause}"
    if strength_clause:
        base += f" {strength_clause}"
    return _with_genre(base, genre_context)


def _style_v2(style: str, genre_context: str,
              preservation_clause: str = "", strength_clause: str = "", **_ignored) -> str:
    base = (
        f"Apply the literary style of {style} to this passage by EDITING it — "
        "adjusting sentence structure, diction, and rhythm to match that style's "
        "characteristic markers — not by rewriting it from scratch. Do not "
        "introduce new plot content, new details, or new imagery beyond what "
        "stylistic rephrasing requires. Do not change how any character speaks "
        "in dialogue — style applies to narration, not to a character's own "
        "voice. Avoid leaning on surface-level genre tropes or stereotypes "
        "associated with this style; capture its actual sentence-level craft "
        "instead. The original author's own identity should still be "
        "recognizable underneath the applied style. Return ONLY the rewritten "
        "passage."
    )
    if preservation_clause:
        base += f" {preservation_clause}"
    if strength_clause:
        base += f" {strength_clause}"
    return _with_genre(base, genre_context)


def _translate_v2(source_language: str, target_language: str,
                   glossary_clause: str = "", **_ignored) -> str:
    base = (
        f"You are a professional literary translator. Translate this passage from "
        f"{source_language} to {target_language} — TRANSLATE, do not summarize, "
        "interpret, or explain. Preserve the tone, style, and literary quality of "
        "the original, including its imagery and figures of speech wherever the "
        "target language has a natural equivalent (do not drop imagery just "
        "because a literal rendering is awkward — find the closest natural "
        "equivalent instead). Preserve emotional nuance — do not flatten mixed or "
        "understated feeling into a simpler emotion. Do not drift from the "
        "original's actual meaning to something that merely sounds natural in the "
        "target language. Return ONLY the translation."
    )
    if glossary_clause:
        base += f" {glossary_clause}"
    return base


def _suggestions_v2(**_ignored) -> str:
    return (
        "You are a developmental editor giving direct, specific manuscript "
        "feedback — not a cheerleader. Analyse the excerpt and identify the "
        "2-4 most significant WEAKNESSES a working novelist would actually want "
        "to fix. Do not lead with praise; only mention a strength if it's "
        "necessary to explain why a weakness matters in context. Each item must "
        "separate what you OBSERVED (the specific issue, quoting or pointing at "
        "the actual text) from what you RECOMMEND (a concrete, actionable "
        "change) — these are different things, do not merge them into one "
        "vague sentence. Avoid generic craft-book language ('show don't tell') "
        "unless you also say exactly where and how it applies to THIS excerpt.\n\n"
        "CATEGORY: write a short, specific category name (2-4 words) that names "
        "THIS weakness precisely, in your own words — not a fixed label from a "
        "list. Do not reuse the same category for two different items in one "
        "response unless they are genuinely the same kind of problem.\n\n"
        "NARRATIVE RISK: also consider whether anything here risks losing the "
        "reader — an unclear stake, a scene that could be cut without loss, a "
        "promise made to the reader that this excerpt doesn't seem to be paying "
        "off. If so, that is a legitimate weakness category on its own "
        "('Narrative Risk'), not something to fold into another category.\n\n"
        "EXPOSITION: if a passage is pure exposition/backstory with no scene, "
        "action, or character presence, the weakness is the STRUCTURE itself "
        "(info-dump), not a missing detail within it — do not recommend adding "
        "MORE backstory detail to an info-dump; recommend converting it into "
        "scene, or cutting/deferring it.\n\n"
        "PRIORITY: rate each item's priority — 'high' (actively undermines the "
        "excerpt), 'medium' (worth fixing but not urgent), or 'low' (polish-level). "
        "Not every weakness is equally urgent; say so.\n\n"
        "Return ONLY a JSON array of 2-4 objects: {id: int, category: string, "
        "observation: string, recommendation: string, priority: 'high'|'medium'|'low'}."
    )


# ══════════════════════════════════════════════════════════════════════════
# Continuity check prompt (task 5.14). Registered from v2 onwards: before
# Stage 5 the continuity prompt was not versioned, so there is no v1 entry
# and check_continuity resolves with "v2" as its fallback. Builders return
# (system, instructions); the caller assembles the data blocks around them.
# ══════════════════════════════════════════════════════════════════════════

_CONTINUITY_SYSTEM_V2 = (
    "You are a continuity editor reviewing a manuscript for internal contradictions. "
    "Be specific: quote the conflicting facts and cite chapter numbers. Reason about "
    "CAUSE AND EFFECT, not just surface facts — a character acting against an "
    "established motivation, or a setup (promise, threat, planted object, stated goal) "
    "that is contradicted rather than paid off, is as real a continuity problem as a "
    "changed eye color or an impossible travel time."
)

_CONTINUITY_INSTRUCTIONS_V2 = (
    "Identify contradictions in: character appearance, character locations, "
    "world rules, timeline, character motivation/arc consistency, and relationship "
    "consistency. Return a JSON array of objects with keys:\n"
    '  "type": one of character_appearance | character_location | world_rule | timeline '
    '| motivation | relationship\n'
    '  "description": specific description of the contradiction\n'
    '  "chapter_refs": array of chapter numbers involved\n'
    '  "severity": high | medium | low\n'
    '  "resolution_hint": a concrete, specific suggestion naming exactly what to change '
    "and where — never a generic line like 'add more detail' or 'clarify this'\n"
    "If no contradictions found, return an empty array []. "
    "Return ONLY the JSON array."
)


def _continuity_v2(**_ignored) -> tuple[str, str]:
    return _CONTINUITY_SYSTEM_V2, _CONTINUITY_INSTRUCTIONS_V2


def _continuity_v3(signals_block: str = "", **_ignored) -> tuple[str, str]:
    """v3 adds the deterministic timeline / narrative-structure signals
    (services/timeline_signals.py, services/narrative_signals.py) as
    candidates the model must verify. With no signals it is identical to v2."""
    if not signals_block:
        return _CONTINUITY_SYSTEM_V2, _CONTINUITY_INSTRUCTIONS_V2
    system = _CONTINUITY_SYSTEM_V2 + (
        " You are also given machine-detected candidate problems. They are hints, "
        "not findings: confirm each one against the chapter data before reporting it, "
        "and silently drop any you cannot confirm. A flashback, a time skip, a dream or "
        "a deliberate unreliable narrator is not a contradiction."
    )
    instructions = signals_block + "\n\n" + _CONTINUITY_INSTRUCTIONS_V2 + (
        " A setup that is never paid off, or a character who vanishes without explanation, "
        "is reported with type \"motivation\" only if you can confirm it from the chapter data."
    )
    return system, instructions


# ══════════════════════════════════════════════════════════════════════════
# v3 — Stage 5 live-review fix D4 (style "Thriller" came back unchanged).
# Only style changes; every other transform reuses its v2 builder, so
# switching to v3 never moves another transform back to v1.
# ══════════════════════════════════════════════════════════════════════════

# The style picker (frontend/lib/transforms.ts STYLES) offers genre/mode
# targets, not authors (author-inspired rewriting is its own transform).
# v2 framed every target as "the literary style of X" and forbade genre
# markers and new imagery, which pushes a GENRE target towards a no-op.
# v3 names the craft levers for each known mode instead.
_STYLE_LEVERS_V3 = {
    "thriller": "short, punchy sentences and paragraphs; urgency and forward momentum; "
                "tension from withheld information and a sense of threat or a ticking clock; "
                "active verbs; cut reflective asides that slow the pace",
    "noir": "hard-boiled, clipped narration; a cynical, world-weary sensibility; "
            "terse, concrete description with occasional sharp simile; moral ambiguity",
    "gothic": "brooding atmosphere and dread; ornate, darker diction; decay, shadow and "
              "confinement in the description of setting; heightened interior unease",
    "pulp": "fast, vivid, visceral prose; strong verbs; high energy; action foregrounded",
    "minimalist": "spare, precise sentences; cut adjectives, adverbs and explanation; "
                  "let concrete action and subtext carry the feeling",
    "lyrical": "musical rhythm and cadence; sound patterning; richer imagery drawn from "
               "what is already in the passage; longer flowing sentences where it serves the moment",
    "literary": "layered, introspective narration; precise, resonant diction; attention to "
                "interiority and subtext",
    "contemporary": "modern, accessible, plain-spoken prose; current idiom; clear, direct sentences",
}


def _style_v3(style: str, genre_context: str,
              preservation_clause: str = "", strength_clause: str = "", **_ignored) -> str:
    levers = _STYLE_LEVERS_V3.get((style or "").strip().lower())
    if levers is None:
        # Unknown / free-text target: the v2 wording, unchanged.
        return _style_v2(style, genre_context, preservation_clause=preservation_clause,
                         strength_clause=strength_clause)
    base = (
        f"Rewrite this passage so it clearly reads as {style} prose. Use these craft "
        f"levers: {levers}. The change must be noticeable to a reader — restructuring "
        "sentences and changing rhythm and diction is expected, not just swapping a few "
        "words. Keep every event, character, fact and line of dialogue content the "
        "same; do not add plot. Dialogue may be tightened only if the preservation "
        "rules allow it, and a character's own voice must stay recognisable. Return "
        "ONLY the rewritten passage."
    )
    if preservation_clause:
        base += f" {preservation_clause}"
    if strength_clause:
        base += f" {strength_clause}"
    return _with_genre(base, genre_context)


# ── Cast extraction (Stage 12 A10) ───────────────────────────────────────────
# v2 is the cast prompt exactly as it was before Stage 12 (frozen). v3 adds
# PRESENCE — on-page vs referenced vs historical — separately from life status,
# so a dead ancestor or an absent ruler is listed and labelled, never silently
# dropped and never passed off as an ordinary on-page character.
_CAST_V2_TEXT = (
    'You are a literary analyst building a character bible from a manuscript.\n'
    'Extract every named character and every significant recurring person from the '
    'story text below, with as much grounded detail as the text supports.\n\n'
    'Return ONLY a valid JSON array. Each element must be an object with these exact keys:\n'
    '  "name": canonical full name (string)\n'
    '  "role": one of "protagonist", "antagonist", "supporting", "minor"\n'
    '  "status": one of "active", "deceased", "unknown"\n'
    '  "aliases": other names/nicknames/titles this character is called by (array of strings; [] if none)\n'
    '  "description": 1-2 sentence summary of who this character is (string)\n'
    '  "age": age or life-stage if stated or strongly implied, else "" (string, e.g. "early 30s", "teenager")\n'
    '  "appearance": physical description grounded in the text, else "" (string)\n'
    '  "personality": personality/temperament grounded in behaviour and dialogue, else "" (string)\n'
    '  "goals": what the character is actively trying to achieve, else "" (string)\n'
    '  "motivations": why they pursue those goals — their drives/fears, else "" (string)\n'
    '  "backstory": established history/origin revealed in the text, else "" (string)\n'
    '  "arc_notes": how the character changes or what unfolds across chapters, else "" (string)\n'
    '  "traits": 3-8 personality adjectives drawn from the text (array of strings; [] if unclear)\n'
    '  "first_appearance": chapter where the character first appears (e.g. "Chapter 1")\n'
    '  "evidence_snippet": short quote or close paraphrase confirming this character (max 80 words)\n'
    '  "confidence": "high" if clearly named and present; "uncertain" if inferred or ambiguous\n\n'
    'Rules:\n'
    '- Include named individuals AND named groups/collectives that act as characters.\n'
    '- Include unnamed but significant recurring characters by their role (e.g. "Ravi\'s Mother").\n'
    '- Extract ALL evidence available — fill appearance/personality/goals/motivations/backstory '
    'whenever the text supports them. Do not leave a field empty if the text gives evidence for it.\n'
    '- Do NOT invent facts. If a field is genuinely not established in the text, use "" (or [] for arrays).\n'
    '- Do NOT invent characters absent from the text.\n'
    '- Return [] if no characters are found.\n'
    '- Output ONLY the JSON array — no preamble, no markdown fences, no trailing prose.'
)


def _cast_v2(**_ignored) -> str:
    return _CAST_V2_TEXT


_CAST_V3_TEXT = _CAST_V2_TEXT.replace(
    '  "status": one of "active", "deceased", "unknown"\n',
    '  "status": one of "active", "deceased", "unknown" (alive or dead — this is NOT presence)\n'
    '  "presence": where the character exists in THIS text, one of:\n'
    '      "on_page": physically present in at least one scene — they act, speak or are seen in\n'
    '      the moment. This includes characters who were believed dead or who are hiding, if they\n'
    '      appear in any scene. When in doubt, use "on_page".\n'
    '      "referenced": alive or of unknown fate, but never present in any scene — only talked about.\n'
    '      "historical": died or was gone before the events of the text and never appears in any\n'
    '      scene — known only from memories, records or other characters\' accounts.\n',
).replace(
    '- Include unnamed but significant recurring characters by their role (e.g. "Ravi\'s Mother").\n',
    # The v2 example name is replaced by a placeholder: with off-page people now
    # requested, Qwen-7B listed the example ("Ravi's Mother") as a character in
    # 4 of 5 live runs — the same phantom-from-example defect as Stage 4.16.
    '- Include unnamed but significant recurring characters by their role, using the words the\n'
    '  text itself uses for them (e.g. "<the narrator\'s mother>"; never copy this placeholder).\n'
    '- A person known only by a title or role (e.g. "<the Archivist>") is a character too.\n'
    '- ALSO list people who never appear in a scene but matter to the plot — for example someone\n'
    '  whose death the characters investigate, or a ruler whose orders drive events — with presence\n'
    '  "historical" or "referenced". Do not list passers-by who are mentioned once and do nothing.\n'
    '- A character believed dead who later appears in a scene is "on_page" (status may be "active").\n'
    '- "status" is only ever "active", "deceased" or "unknown".\n',
    # Tried and reverted (measured, Stage 12): an explicit "people who share a
    # first name are different characters" rule RAISED single-window conflation
    # of the two Tomases from 2/5 to 4/5 runs. Conflation is flagged in code
    # instead (_merge_cast: _possible_combined_with).
)


def _cast_v3(**_ignored) -> str:
    return _CAST_V3_TEXT


def register_version(version: str, builders: dict[str, Callable]) -> None:
    """Add a new, additive version to the registry. Never call this to
    overwrite an existing version — that would defeat the whole point of
    having frozen baselines to revert to and measure against."""
    if version in PROMPT_REGISTRY:
        raise RuntimeError(
            f"prompt_registry: version {version!r} is already registered — "
            "add a new version instead of overwriting an existing one."
        )
    PROMPT_REGISTRY[version] = builders


def resolve_prompt_version(transform_type: str, version: str, fallback: str) -> tuple[Callable, str]:
    """
    Look up the prompt builder for (transform_type, version). Returns
    (builder, resolved_version) — resolved_version is what actually ran,
    for logging, and differs from `version` only when a fallback occurred.

    Fails safe: an unknown version or transform_type never falls through to
    arbitrary/partial prompt content. It logs the problem and uses
    `fallback` instead — and if `fallback` itself is missing that
    transform_type, that is a genuine configuration bug and raises, rather
    than silently degrading further.
    """
    entry = PROMPT_REGISTRY.get(version)
    if entry is not None and transform_type in entry:
        return entry[transform_type], version

    logger.error(
        "[prompt_registry] unresolvable (transform_type=%r, version=%r) — falling back to %r",
        transform_type, version, fallback,
    )
    fallback_entry = PROMPT_REGISTRY.get(fallback)
    if fallback_entry is None or transform_type not in fallback_entry:
        raise RuntimeError(
            f"prompt_registry: fallback version {fallback!r} does not define "
            f"transform_type {transform_type!r} either — this is a configuration "
            "bug (a real prompt version must exist for every transform type), "
            "not a condition to silently paper over."
        )
    return fallback_entry[transform_type], fallback


# Registered here, after register_version/resolve_prompt_version are defined,
# not next to the v2 builder functions above — a plain module-level call to a
# not-yet-defined function would NameError at import time.
register_version("v2", {
    "tone": _tone_v2,
    "emotion": _emotion_v2,
    "age_adapt": _age_adapt_v2,
    "style": _style_v2,
    "translate": _translate_v2,
    "suggestions": _suggestions_v2,
    "author_style": _author_style_v1,  # unchanged — see _author_style_v1's own docstring
    "continuity": _continuity_v2,  # the exact prompt check_continuity used before registration
    "cast": _cast_v2,              # Stage 12: the pre-Stage-12 cast prompt, frozen
})

# v3 (Stage 5, D4 + 5.14): every v2 transform is carried over; only style and
# continuity get new builders. The config default is "v3" with fallback "v2".
register_version("v3", {
    **PROMPT_REGISTRY["v2"],
    "style": _style_v3,
    "continuity": _continuity_v3,
    "cast": _cast_v3,              # Stage 12 A10: + presence (on_page / referenced / historical)
})


# ══════════════════════════════════════════════════════════════════════════
# v4 (Stage 12 Tranche 2b — A15). Builders now receive `strength`.
#   style      — v3 told the model "restructuring sentences … is expected" at
#                EVERY strength, contradicting the Light clause appended after
#                it. v4 asks for restructuring only at moderate/strong; at
#                light the style comes through word choice and punctuation.
#                Measured (tests/fixtures/strength_t2b_*.json): Light now keeps
#                a median 0.71 of the author's words against Strong's 0.58
#                (v3: 0.60 vs 0.59 — no difference).
# Measured and NOT adopted (no change in what Light keeps):
#   * age_adapt — a light-only "swap hard words, keep every sentence"
#     instruction: Light median 0.50 of the author's words vs Strong 0.455
#     (v3: 0.524 vs 0.455);
#   * age_adapt — a gentler children's guide ("keep difficult events, tell them
#     gently"): it changed what happened MORE often (A14 — adventure-3
#     "nobody survived" → "everyone got hurt" in 7/10 runs vs 1/10 on v2).
# A light-only tone instruction was also measured and NOT adopted: no change
# in what Light keeps (median 0.568 vs Strong 0.583).
# Every other transform is carried over from v3 unchanged.
# ══════════════════════════════════════════════════════════════════════════

_LIGHT_STYLE_V4 = (
    "At this strength keep the author's sentences, their order and their boundaries; "
    "express the style only through word choice, connectives and punctuation."
)


def _style_v4(style: str, genre_context: str, preservation_clause: str = "",
              strength_clause: str = "", strength: str = "light", **_ignored) -> str:
    if strength != "light":
        return _style_v3(style, genre_context, preservation_clause=preservation_clause,
                         strength_clause=strength_clause)
    # No craft-lever list at light: several levers are structural ("short,
    # punchy sentences") and would reintroduce the contradiction.
    base = (
        f"Edit this passage so it leans toward {style} prose. {_LIGHT_STYLE_V4} "
        "Keep every event, character, fact and line of dialogue content the same; do not "
        "add plot, details or imagery. A character's own voice must stay recognisable. "
        "Return ONLY the edited passage."
    )
    if preservation_clause:
        base += f" {preservation_clause}"
    if strength_clause:
        base += f" {strength_clause}"
    return _with_genre(base, genre_context)


register_version("v4", {
    **PROMPT_REGISTRY["v3"],
    "style": _style_v4,
})
