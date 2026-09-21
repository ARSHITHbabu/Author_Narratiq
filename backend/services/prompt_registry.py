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
})
