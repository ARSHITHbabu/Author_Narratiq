"""
Exact search & replace over chapter HTML — one text model for count, preview,
Replace One and Replace All (Stage 12 remediation A9; SEARCH-4 / SEARCH-5).

Why this module exists. Search used to count matches in one model of the text
(every tag turned into a space, then entities decoded) and replace in another
(raw, still-escaped text between tags), while the editor highlighted in a third
(one formatted text run at a time). The three disagreed, and replace could
corrupt the manuscript: replacing "amp" turned `&amp;` into `&X;`, Replace One
across formatting changed the wrong occurrence, and the replacement was
inserted as raw HTML.

The text model — mirrored exactly by frontend/lib/searchMatch.ts:
  * The chapter is split into BLOCKS. A block ends at every block-level tag
    (p, h1–h6, li, blockquote, pre, div, …) and at every <br>. A match never
    crosses a block (owner decision: no matches across paragraphs or explicit
    line breaks).
  * Inline formatting tags (b, i, em, strong, u, s, mark, a, span, code, …) are
    removed with NO separator, so "Dev<b>ika</b>" reads "Devika".
  * HTML entities are decoded ("&amp;" is one "&").
  * Runs of ASCII whitespace collapse to one space, and whitespace at the start
    or end of a block is dropped — what ProseMirror does when it loads HTML.
    Inside <pre> whitespace is kept. A non-breaking space stays a distinct
    character.
  * The query is literal (escaped). Whole word means: not preceded or followed
    by a letter, combining mark, digit or underscore — Unicode-aware, so
    "café" and "हिंदी" work. Case-insensitive uses Unicode simple case folding.
  * Curly and straight quotes are NOT treated as equal (owner decision).

Replace works on the very same match list: each decoded character remembers
the raw HTML span it came from, so a match is mapped back onto the original
markup. The replacement is escaped as author text, entities outside the match
are untouched, and every tag is kept, so formatting stays balanced. A match
that spans formatting puts the replacement where the match begins and removes
the rest of the matched text from the following formatted runs.
"""
from __future__ import annotations

import html as _html
import re
from dataclasses import dataclass, field

import regex  # Unicode property classes for whole-word boundaries

CONTEXT_CHARS = 80
MAX_QUERY_CHARS = 500

_BLOCK_TAGS = frozenset({
    "p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "ul", "ol", "blockquote",
    "pre", "div", "section", "article", "header", "footer", "aside", "nav",
    "table", "thead", "tbody", "tfoot", "tr", "td", "th", "caption",
    "figure", "figcaption", "hr", "dl", "dt", "dd", "main", "address",
})
_BREAK_TAGS = frozenset({"br"})
_TAG = re.compile(r"<!--.*?-->|<[^>]*>", re.S)
_TAG_NAME = re.compile(r"<\s*(/?)\s*([A-Za-z][A-Za-z0-9]*)")
_ENTITY = re.compile(r"&(?:#[0-9]+|#[xX][0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]*);")
_COLLAPSIBLE = frozenset(" \t\n\r\f")
_WORD = r"[\p{L}\p{M}\p{N}_]"


@dataclass
class _Block:
    chars: list[str] = field(default_factory=list)
    spans: list[tuple[int, int]] = field(default_factory=list)   # raw [start, end) per char

    @property
    def text(self) -> str:
        return "".join(self.chars)


@dataclass
class Match:
    block: int
    start: int          # offset in the block's text
    end: int
    text: str
    context_before: str
    context_after: str


def blocks_of(html: str) -> list[_Block]:
    """Split chapter HTML into searchable blocks (see the module docstring)."""
    blocks: list[_Block] = []
    cur = _Block()
    pre_depth = 0

    def close():
        nonlocal cur
        while cur.chars and cur.chars[-1] == " " and not pre_depth:
            cur.chars.pop()
            cur.spans.pop()
        if cur.chars:
            blocks.append(cur)
        cur = _Block()

    def add_text(raw: str, base: int):
        i = 0
        while i < len(raw):
            m = _ENTITY.match(raw, i) if raw[i] == "&" else None
            if m:
                decoded = _html.unescape(m.group())
                span = (base + i, base + m.end())
                i = m.end()
            else:
                decoded = raw[i]
                span = (base + i, base + i + 1)
                i += 1
            for ch in decoded:
                if ch in _COLLAPSIBLE and not pre_depth:
                    # Collapse runs; drop at block start. Only literal ASCII
                    # whitespace collapses (an encoded &#32; is rare — same rule).
                    if not cur.chars or cur.chars[-1] == " ":
                        continue
                    ch = " "
                cur.chars.append(ch)
                cur.spans.append(span)

    pos = 0
    for m in _TAG.finditer(html):
        if m.start() > pos:
            add_text(html[pos:m.start()], pos)
        tag = m.group()
        nm = _TAG_NAME.match(tag)
        if nm:
            closing, name = nm.group(1) == "/", nm.group(2).lower()
            if name in _BLOCK_TAGS or name in _BREAK_TAGS:
                close()
                if name == "pre":
                    pre_depth = max(0, pre_depth + (-1 if closing else 1))
        pos = m.end()
    if pos < len(html):
        add_text(html[pos:], pos)
    close()
    return blocks


def compile_pattern(query: str, whole_word: bool, case_sensitive: bool) -> regex.Pattern:
    body = regex.escape(query, special_only=True, literal_spaces=True)
    if whole_word:
        body = rf"(?<!{_WORD}){body}(?!{_WORD})"
    flags = regex.V0 | (0 if case_sensitive else regex.IGNORECASE)
    return regex.compile(body, flags)


def find_matches(html: str, query: str, whole_word: bool = False, case_sensitive: bool = False) -> list[Match]:
    """Every match in document order. Empty queries match nothing."""
    if not html or not query or not query.strip():
        return []
    pat = compile_pattern(query, whole_word, case_sensitive)
    out: list[Match] = []
    for bi, b in enumerate(blocks_of(html)):
        text = b.text
        for m in pat.finditer(text):
            if m.end() == m.start():
                continue
            s, e = m.start(), m.end()
            out.append(Match(
                block=bi, start=s, end=e, text=m.group(),
                context_before=text[max(0, s - CONTEXT_CHARS):s].lstrip(),
                context_after=text[e:e + CONTEXT_CHARS].rstrip(),
            ))
    return out


def replace(html: str, query: str, replacement: str, *, whole_word: bool = False,
            case_sensitive: bool = False, occurrence_index: int | None = None) -> tuple[str, int]:
    """Replace matches of `query` in `html`.

    occurrence_index None replaces every match; N replaces exactly the Nth match
    as find_matches() enumerates it (the same index the author navigated to).
    Returns (new_html, replaced_count). The count always equals the number of
    matches actually rewritten.
    """
    matches = find_matches(html, query, whole_word, case_sensitive)
    if occurrence_index is not None:
        if occurrence_index < 0 or occurrence_index >= len(matches):
            return html, 0
        matches = [matches[occurrence_index]]
    if not matches:
        return html, 0

    blocks = blocks_of(html)
    safe = _html.escape(replacement, quote=False)
    edits: list[tuple[int, int, str]] = []          # raw [start, end) → text
    for m in matches:
        spans = blocks[m.block].spans[m.start:m.end]
        # Group the matched characters into contiguous raw runs; a new run
        # starts wherever a tag (or skipped whitespace) sits between two chars.
        runs: list[list[int]] = []
        for s, e in spans:
            if runs and s <= runs[-1][1]:
                runs[-1][1] = max(runs[-1][1], e)
            else:
                runs.append([s, e])
        edits.append((runs[0][0], runs[0][1], safe))
        for s, e in runs[1:]:
            edits.append((s, e, ""))

    out = html
    for s, e, text in sorted(edits, key=lambda x: x[0], reverse=True):
        out = out[:s] + text + out[e:]
    return out, len(matches)


def plain_word_count(html: str) -> int:
    return sum(len(b.text.split()) for b in blocks_of(html))
