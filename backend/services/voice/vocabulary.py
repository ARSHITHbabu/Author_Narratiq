"""
Story-aware transcript correction (B) + entity pre-resolution.

Whisper mishears proper nouns it has never seen (character names, invented
places, made-up terms). This module builds a GENERIC per-story vocabulary from
the author's own data — character names + aliases, chapter titles, note / note-card
titles, story title — and uses fuzzy (rapidfuzz) + phonetic (metaphone) matching
to repair likely-misheard spans BEFORE intent routing.

Nothing here is hardcoded to any name, story, or phrase: the vocabulary is read
live from the DB for whatever story the author is in. A repaired span that maps
to a known entity also yields that entity's id, so the resolver never has to ask
the author for an internal id.

correct_transcript() returns (corrected_text, corrections) where each correction
is {from, to, kind, ref_id} — kind ∈ character|chapter|note|story.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field

from rapidfuzz import fuzz
import jellyfish

logger = logging.getLogger(__name__)

_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "at", "for",
    "with", "this", "that", "it", "is", "are", "was", "were", "he", "she", "they",
    "my", "your", "his", "her", "story", "chapter", "note", "scene", "where",
    "what", "who", "make", "find", "show", "more", "all",
}

# Honorifics/titles that aren't the distinctive part of a person's name. Generic
# list (not story-specific) so "Mr. Dinesh" also matches a spoken "Dinesh".
_TITLES = {
    "mr", "mrs", "ms", "miss", "dr", "doctor", "sir", "lord", "lady", "madam",
    "master", "mister", "captain", "professor", "prof", "saint", "st", "uncle",
    "aunt", "aunty", "king", "queen", "prince", "princess", "father", "mother",
    "brother", "sister", "general", "colonel", "sergeant", "officer", "detective",
}

_WORD = re.compile(r"[A-Za-z']+")


def _norm(w: str) -> str:
    return w.lower().strip(".,!?;:'\"").rstrip("'s") if w else ""


def _phonetic(s: str) -> str:
    try:
        return jellyfish.metaphone(s) or ""
    except Exception:
        return ""


@dataclass
class VocabTerm:
    text: str                  # canonical surface form
    kind: str                  # character | chapter | note | story
    ref_id: str | None
    tokens: list[str] = field(default_factory=list)   # normalized tokens
    phonetic: str = ""

    @property
    def n(self) -> int:
        return len(self.tokens)

    @property
    def distinctive(self) -> bool:
        # A term worth correcting toward: not purely stopwords, has real length.
        joined = "".join(self.tokens)
        return len(joined) >= 3 and any(t not in _STOPWORDS and len(t) >= 3 for t in self.tokens)


# ── per-story vocabulary cache (live data; short TTL) ─────────────────────────
_cache: dict[str, tuple[float, list[VocabTerm]]] = {}
_TTL = 120.0


def _make_term(text: str, kind: str, ref_id: str | None) -> VocabTerm | None:
    toks = [_norm(w) for w in _WORD.findall(text or "")]
    toks = [t for t in toks if t]
    if not toks:
        return None
    return VocabTerm(text=text.strip(), kind=kind, ref_id=ref_id, tokens=toks,
                     phonetic=_phonetic("".join(toks)))


def build_story_vocabulary(story_id: str, db, *, use_cache: bool = True) -> list[VocabTerm]:
    """Collect the author's story-specific vocabulary. Generic — no hardcoding."""
    if use_cache:
        hit = _cache.get(story_id)
        if hit and (time.monotonic() - hit[0]) < _TTL:
            return hit[1]

    from models import Character, Chapter, StoryNote, NoteCard, Story
    terms: list[VocabTerm] = []

    def add(text, kind, ref_id):
        t = _make_term(text, kind, ref_id)
        if t and t.distinctive:
            terms.append(t)
        # For multi-word person names, also index the distinctive single tokens
        # (authors often say just "Dinesh", not "Mr. Dinesh"). Generic — uses the
        # token's own length/title-ness, never a specific name.
        if t and kind == "character" and t.n > 1:
            for tok in t.tokens:
                if tok in _TITLES or tok in _STOPWORDS or len(tok) < 4:
                    continue
                terms.append(VocabTerm(text=tok.capitalize(), kind=kind, ref_id=ref_id,
                                       tokens=[tok], phonetic=_phonetic(tok)))

    try:
        for c in db.query(Character).filter(Character.story_id == story_id).all():
            add(c.name, "character", c.character_id)
            for alias in (c.aliases or []):
                add(alias, "character", c.character_id)
        for ch in db.query(Chapter).filter(Chapter.story_id == story_id).all():
            if ch.title:
                add(ch.title, "chapter", ch.chapter_id)
        for n in db.query(StoryNote).filter(StoryNote.story_id == story_id).all():
            if n.title:
                add(n.title, "note", n.note_id)
        for nc in db.query(NoteCard).filter(NoteCard.story_id == story_id).all():
            if nc.title:
                add(nc.title, "note", nc.card_id)
        st = db.query(Story).filter(Story.story_id == story_id).first()
        if st and st.title:
            add(st.title, "story", st.story_id)
    except Exception as exc:                       # noqa: BLE001
        logger.warning("[voice.vocab] build failed for %s: %s", story_id, exc)

    # de-dup by (text, ref_id)
    seen, uniq = set(), []
    for t in terms:
        key = (t.text.lower(), t.ref_id)
        if key not in seen:
            seen.add(key)
            uniq.append(t)
    _cache[story_id] = (time.monotonic(), uniq)
    return uniq


def invalidate(story_id: str) -> None:
    _cache.pop(story_id, None)


def _span_score(window_tokens: list[str], term: VocabTerm) -> float:
    """0-100 similarity of a transcript window to a vocab term (fuzzy ∪ phonetic)."""
    w = " ".join(window_tokens)
    t = " ".join(term.tokens)
    if not w:
        return 0.0
    fuzzy = fuzz.ratio(w, t)
    # Phonetic equality is a strong signal for misheard proper nouns.
    if term.phonetic and _phonetic("".join(window_tokens)) == term.phonetic:
        return max(fuzzy, 92.0)
    return float(fuzzy)


def correct_transcript(transcript: str, vocab: list[VocabTerm], *, min_score: int = 84):
    """
    Repair likely-misheard story terms. Returns (corrected_text, corrections).
    Generic sliding-window fuzzy+phonetic match; longer terms matched first so
    multi-word names win over single tokens.
    """
    if not transcript or not vocab:
        return transcript, []

    words = transcript.split()
    norm = [_norm(w) for w in words]
    used = [False] * len(words)
    corrections = []

    for term in sorted(vocab, key=lambda t: -t.n):
        n = term.n
        if n == 0 or n > len(words):
            continue
        for i in range(len(words) - n + 1):
            if any(used[i:i + n]):
                continue
            window = norm[i:i + n]
            if window == term.tokens:
                used[i:i + n] = [True] * n          # already correct — lock it
                continue
            # Skip windows that are just stopwords (avoid rewriting "the end").
            if all(t in _STOPWORDS for t in window):
                continue
            score = _span_score(window, term)
            if score >= min_score:
                original = " ".join(words[i:i + n])
                words[i:i + n] = term.text.split()
                # pad `used`/`norm` if term has different word count
                used[i:i + n] = [True] * len(term.text.split())
                norm = [_norm(w) for w in words]
                used = (used + [False] * (len(words) - len(used)))[:len(words)]
                corrections.append({"from": original, "to": term.text,
                                    "kind": term.kind, "ref_id": term.ref_id,
                                    "score": round(score, 1)})
                break

    corrected = " ".join(words)
    if corrections:
        logger.info("[voice.vocab] corrected %d term(s): %s", len(corrections),
                    [f"{c['from']}→{c['to']}" for c in corrections])
    return corrected, corrections
