"""
Transcript normalization — lightweight, deterministic, fast.

Used to prepare a command string for intent/reference resolution. The
authoritative human-facing cleanup of long dictation still goes through
services.audio_service.clean_transcript (Qwen). This module only does cheap
deterministic fixes that help classification:

  - trims fillers
  - maps spoken number words → digits ("chapter three" → "chapter 3")
  - collapses whitespace

It never changes meaning and is safe to run on every turn.
"""
from __future__ import annotations

import re

_FILLERS = (
    "um", "uh", "erm", "you know", "i mean", "kind of", "sort of",
    "basically", "literally",
)

_NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
}


def normalize_command(text: str) -> str:
    """Return a normalized command string suitable for classification."""
    if not text:
        return ""
    t = text.strip()

    # number words → digits (word-boundary, case-insensitive)
    def _sub_num(m: re.Match) -> str:
        return str(_NUMBER_WORDS[m.group(0).lower()])

    if _NUMBER_WORDS:
        pattern = r"\b(" + "|".join(re.escape(w) for w in _NUMBER_WORDS) + r")\b"
        t = re.sub(pattern, _sub_num, t, flags=re.IGNORECASE)

    # strip standalone fillers
    for f in _FILLERS:
        t = re.sub(rf"\b{re.escape(f)}\b[,]?\s*", "", t, flags=re.IGNORECASE)

    t = re.sub(r"\s+", " ", t).strip()
    return t


# spoken ordinal extraction helper used by reference resolution ("second option")
_ORDINALS = {
    "first": 0, "1st": 0, "1": 0,
    "second": 1, "2nd": 1, "2": 1,
    "third": 2, "3rd": 2, "3": 2,
    "fourth": 3, "4th": 3, "4": 3,
    "fifth": 4, "5th": 4, "5": 4,
    "last": -1,
}


def extract_ordinal(text: str) -> int | None:
    """Return a 0-based index referenced by an ordinal in `text`, or None."""
    low = (text or "").lower()
    for word, idx in _ORDINALS.items():
        if re.search(rf"\b{re.escape(word)}\b", low):
            return idx
    return None
