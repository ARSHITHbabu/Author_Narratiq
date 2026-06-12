"""
Context Resolver — fill node parameters from (1) planner-extracted params,
(2) the client context snapshot, (3) resolved conversational references, and
(4) RAG/DB entity resolution (character name → id, "chapter 3" → chapter_id).

Reports any still-missing REQUIRED parameter so the agent can ask a targeted
clarification rather than guessing. Reuses the existing character search and
BGE-M3 retrieval rather than rebuilding entity lookup.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from .capabilities import get_action

logger = logging.getLogger(__name__)


# ── Context bundle (priority-ordered authoring context for a capability) ───────

@dataclass
class ContextBundle:
    story_id: str | None = None
    chapter_id: str | None = None
    chapter_number: int | None = None
    selected_text: str | None = None
    chapter_text: str | None = None        # current visible OR saved DB content
    used: list[str] = field(default_factory=list)   # human labels of sources used

    @property
    def used_label(self) -> str:
        return ", ".join(self.used) if self.used else "story context"


def _strip_html(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


def build_bundle(context, memory, db) -> ContextBundle:
    """
    Assemble authoring context in strict priority order:
      1. selected_text  2. current visible chapter text  3. saved DB chapter
    RAG (chunks/character/notes) is fetched by the feature adapters themselves.
    IDs are resolved from context → session memory (never asked of the author).
    """
    b = ContextBundle()
    b.story_id = getattr(context, "story_id", None) or memory.get("last_story_id")
    b.chapter_id = getattr(context, "chapter_id", None) or memory.get("last_chapter_id")
    b.chapter_number = getattr(context, "chapter_number", None)

    sel = getattr(context, "selected_text", None)
    if sel and getattr(context, "has_selection", False):
        b.selected_text = sel
        b.used.append("selected text")

    # current visible editor text (priority 2), else saved DB chapter (priority 3)
    visible = getattr(context, "full_chapter_text", None)
    if visible:
        b.chapter_text = visible
        b.used.append(f"chapter {b.chapter_number}" if b.chapter_number else "current chapter")
    elif b.chapter_id:
        from models import Chapter
        ch = db.query(Chapter).filter(Chapter.chapter_id == b.chapter_id).first()
        if ch and ch.content:
            b.chapter_text = _strip_html(ch.content)
            b.used.append(f"chapter {ch.chapter_number} (saved)")
    return b


# ── Entity resolution ─────────────────────────────────────────────────────────

def resolve_chapter(ref: Any, story_id: str, db) -> str | None:
    """Resolve a chapter reference (number, 'chapter 3', or id) → chapter_id."""
    from models import Chapter
    if not ref or not story_id:
        return None
    ref_s = str(ref).strip()
    # already an id?
    row = db.query(Chapter).filter(Chapter.chapter_id == ref_s,
                                   Chapter.story_id == story_id).first()
    if row:
        return row.chapter_id
    m = re.search(r"(\d+)", ref_s)
    if m:
        num = int(m.group(1))
        row = db.query(Chapter).filter(Chapter.story_id == story_id,
                                       Chapter.chapter_number == num).first()
        if row:
            return row.chapter_id
    return None


def resolve_character(ref: Any, story_id: str, db) -> tuple[str | None, str | None]:
    """Resolve a character reference (name/alias/id) → (character_id, name).
    Falls back to fuzzy + phonetic matching so a misheard name still resolves."""
    from models import Character
    if not ref or not story_id:
        return None, None
    ref_s = str(ref).strip()
    row = db.query(Character).filter(Character.character_id == ref_s,
                                     Character.story_id == story_id).first()
    if row:
        return row.character_id, row.name

    rows = db.query(Character).filter(Character.story_id == story_id).all()
    low = ref_s.lower().strip(".,'\"").rstrip("'s")
    # exact / substring on name or alias
    for c in rows:
        for n in [c.name or ""] + list(c.aliases or []):
            if n and n.lower() == low:
                return c.character_id, c.name
    for c in rows:
        for n in [c.name or ""] + list(c.aliases or []):
            nl = (n or "").lower()
            if nl and (low in nl or nl in low):
                return c.character_id, c.name

    # fuzzy + phonetic fallback (generic, no hardcoded names)
    try:
        from rapidfuzz import fuzz
        import jellyfish
        ref_ph = jellyfish.metaphone(low) or ""
        best, best_score = None, 0.0
        for c in rows:
            for n in [c.name or ""] + list(c.aliases or []):
                if not n:
                    continue
                nl = n.lower()
                score = fuzz.ratio(low, nl)
                if ref_ph and jellyfish.metaphone(nl) == ref_ph:
                    score = max(score, 90.0)
                if score > best_score:
                    best, best_score = c, score
        if best and best_score >= 82:
            return best.character_id, best.name
    except Exception:
        pass
    return None, None


# ── Context brief (for LLM prompts) ───────────────────────────────────────────

def summarize_context(context, memory) -> str:
    bits = []
    if getattr(context, "story_id", None):
        bits.append(f"story_id={context.story_id}")
    if getattr(context, "chapter_number", None) is not None:
        bits.append(f"current_chapter={context.chapter_number}")
    if getattr(context, "has_selection", False):
        sel = (context.selected_text or "")[:80]
        bits.append(f"has_selection=true selection≈{sel!r}")
    if getattr(context, "active_panel", None):
        bits.append(f"panel={context.active_panel}")
    if memory.get("last_capability"):
        bits.append(f"last_action={memory.get('last_intent')}")
    if memory.get("last_result_kind"):
        bits.append(f"last_result={memory.get('last_result_kind')}")
    return "; ".join(bits)


# ── Node parameter resolution ─────────────────────────────────────────────────

def resolve_node_params(node, context, refs, memory, db) -> list[str]:
    """
    Mutates node.params in place; returns the list of still-missing REQUIRED
    parameter names. Order of precedence: explicit planner params → references →
    client context → session memory → DB entity resolution.
    """
    spec = get_action(node.capability, node.action)
    if spec is None:
        return []
    p = node.params

    story_id = p.get("story_id") or getattr(context, "story_id", None) or memory.get("last_story_id")
    if story_id:
        p["story_id"] = story_id

    # text — for text transforms this is the CURRENT live selection ONLY. No RAG,
    # no chapter content, no summaries, and no stale memory/last-selection (even
    # via a pronoun like "this"). If there is no current selection the field stays
    # unfilled → the agent clarifies ("select the text first").
    if "text" in spec.required and not p.get("text"):
        if node.capability == "text_transform":
            text = (getattr(context, "selected_text", None)
                    if getattr(context, "has_selection", False) else None)
        else:
            text = (refs.selected_text or getattr(context, "selected_text", None)
                    or memory.get("last_selected_text"))
        if text:
            p["text"] = text

    # chapter_id — resolve a number/phrase to an id, else use a known id directly
    if ("chapter_id" in spec.required or "chapter_id" in spec.optional) and not p.get("chapter_id"):
        cid = refs.chapter_id
        if not cid:
            chap_ref = p.get("chapter_number") or p.get("chapter")
            if chap_ref and story_id:
                cid = resolve_chapter(chap_ref, story_id, db)
        if not cid:
            cid = getattr(context, "chapter_id", None) or memory.get("last_chapter_id")
        if cid:
            p["chapter_id"] = cid

    # character_id
    if ("character_id" in spec.required or "character_id" in spec.optional) and not p.get("character_id"):
        char_ref = refs.character_id or p.get("character_name") or p.get("character")
        cid, cname = (refs.character_id, refs.character_name)
        if not cid and char_ref and story_id:
            cid, cname = resolve_character(char_ref, story_id, db)
        if not cid:
            cid = getattr(context, "active_character_id", None) or memory.get("last_character_id")
        if cid:
            p["character_id"] = cid
            if cname:
                p["character_name"] = cname

    # content for apply/edit/voice_note: prefer planner content, else option/selection
    if "content" in spec.required and not p.get("content"):
        content = (p.get("content") or refs.option_text or refs.selected_text
                   or getattr(context, "selected_text", None))
        if content:
            p["content"] = content

    # compute missing required (story_id implicitly required for most)
    missing = [r for r in spec.required if not p.get(r)]
    return missing
