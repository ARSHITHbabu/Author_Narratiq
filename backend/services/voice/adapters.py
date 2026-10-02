"""
Feature Adapter Layer.

Adapters are the ONLY place the agent invokes a feature. A server_sync adapter
calls a feature's existing SERVICE functions (which own their models) and returns
a result the agent formats; it never contains prompt or embedding code itself.

Server_sync is used only for light read/Q&A capabilities (story_qa, character_qa,
character_relationship). Everything else (transforms, writes, heavy/async
analyses) is executed client-side against the real router endpoints via api.ts.

Model ownership stays intact:
  story_qa             → retrieve_chunks_from_store (BGE-M3) + answer_story_question (Qwen)
  character_qa         → retrieve_character_context (BGE-M3) + answer_story_question (Qwen)
  character_relationship → relationship graph (DB) + character RAG + answer_story_question (Qwen)
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# ── D-1 for voice (Stage 12) ────────────────────────────────────────────────
# Voice Q&A used to search the whole manuscript even while the author worked in
# an early chapter. It now follows the Plot Assistant's spoiler boundary: the
# open chapter is the limit; the whole manuscript only on an EXPLICIT request.
# Deliberately conservative: a broad question ("what is this story about?")
# is not a request for later chapters.
_WHOLE_BOOK = re.compile(
    r"\b(?:"
    r"(?:in|across|throughout|from|over|through)\s+(?:the\s+)?(?:whole|entire|full)\s+(?:book|manuscript|novel|story)"
    r"|(?:the\s+)?(?:whole|entire|full)\s+(?:book|manuscript|novel)"
    r"|(?:all|every)\s+(?:of\s+the\s+)?(?:the\s+)?chapters"
    r"|every\s+chapter"
    r")\b",
    re.IGNORECASE,
)
NO_CHAPTER_MESSAGE = ("Open a chapter first so I only use what you have written up to there — "
                      "or ask about \u201cthe whole book\u201d if you want every chapter searched.")


def wants_whole_book(question: str) -> bool:
    return bool(question and _WHOLE_BOOK.search(question))


def voice_scope(question: str, bundle, db) -> tuple[bool, int | None]:
    """(allowed, max_chapter_number) for a voice question. max None = whole
    manuscript, only when explicitly asked. Not allowed = no chapter is open and
    the whole book was not asked for — never a silent unlimited search."""
    if wants_whole_book(question):
        return True, None
    num = getattr(bundle, "chapter_number", None)
    if num is None and getattr(bundle, "chapter_id", None) and getattr(bundle, "story_id", None):
        from models import Chapter
        row = db.query(Chapter).filter(Chapter.chapter_id == bundle.chapter_id,
                                       Chapter.story_id == bundle.story_id).first()
        num = row.chapter_number if row else None
    if isinstance(num, int) and num >= 1:
        return True, num
    return False, None


def _refused() -> dict:
    return {"answer": NO_CHAPTER_MESSAGE, "context_used": "none — no chapter open"}


def _scope_note(cap):
    return "whole manuscript (asked for)" if cap is None else f"chapters 1–{cap}"


def _genre_dict(story_id, db):
    from models import GenreProfile
    gp = db.query(GenreProfile).filter(GenreProfile.story_id == story_id).first()
    if not gp:
        return None
    return {"genre": gp.genre, "sub_genre": gp.sub_genre, "tone": gp.tone,
            "audience": gp.target_audience}


def _pseudo_chunks_from_chapter(bundle) -> list[dict]:
    """Fallback context when RAG is unavailable — use the current chapter text.
    Must match the chunk shape answer_story_question expects: chapter/text/word_count/score."""
    if bundle.chapter_text:
        text = bundle.chapter_text[:6000]
        return [{"text": text, "chapter": bundle.chapter_number or 0,
                 "word_count": len(text.split()), "score": 1.0}]
    return []


async def _adapt_story_qa(question, bundle, db, user) -> dict:
    from services.ai_service import (retrieve_chunks_from_store, retrieve_note_context,
                                     answer_story_question)
    story_id = bundle.story_id
    allowed, cap = voice_scope(question, bundle, db)
    if not allowed:
        return _refused()
    chunks = await retrieve_chunks_from_store(question, story_id, db, top_k=8,
                                              max_chapter_number=cap) if story_id else []
    used = ["story passages (RAG)"] if chunks else []
    if not chunks:
        chunks = _pseudo_chunks_from_chapter(bundle)
        if chunks:
            used = ["current chapter text"]
    if not chunks:
        return {"answer": "I don't have any indexed story content for that yet — "
                          "add or index a chapter first and I'll be able to answer.",
                "context_used": "none"}
    notes = await retrieve_note_context(story_id, question, db) if story_id else []
    intel = None
    if story_id:
        try:   # same scope rules as the Plot Assistant (provenance upper bound)
            from services.story_intel_service import build_integration_context
            intel = await build_integration_context(db, story_id, query=question, top_k=8,
                                                    max_chapter_number=cap)
        except Exception as exc:
            logger.warning("[voice] story intelligence unavailable (%s) — continuing without it", type(exc).__name__)
    answer = await answer_story_question(
        question, chunks, genre_profile=_genre_dict(story_id, db),
        current_chapter=bundle.chapter_text or "", note_context=notes or None,
        scope_limited=cap is not None, intel_context=intel)
    return {"answer": answer,
            "context_used": ", ".join(used + (["story notes"] if notes else [])) + f" [{_scope_note(cap)}]"}


async def _adapt_character_qa(question, bundle, db, user) -> dict:
    from services.ai_service import (retrieve_character_context, retrieve_chunks_from_store,
                                     answer_story_question)
    story_id = bundle.story_id
    allowed, cap = voice_scope(question, bundle, db)
    if not allowed:
        return _refused()
    char_ctx = await retrieve_character_context(story_id, question, db,
                                                max_chapter_number=cap) if story_id else []
    chunks = await retrieve_chunks_from_store(question, story_id, db, top_k=4,
                                              max_chapter_number=cap) if story_id else []
    if not chunks:
        chunks = _pseudo_chunks_from_chapter(bundle)
    if not char_ctx and not chunks:
        return {"answer": "I couldn't find that character in this story yet.",
                "context_used": "none"}
    answer = await answer_story_question(
        question, chunks, current_chapter=bundle.chapter_text or "",
        character_context=char_ctx or None, scope_limited=cap is not None)
    return {"answer": answer, "context_used": "character profiles (RAG)" +
            (" + story passages" if chunks and chunks[0].get("score", 0) != 1.0 else "") +
            f" [{_scope_note(cap)}]"}


async def _adapt_character_relationship(question, bundle, db, user) -> dict:
    from services.ai_service import retrieve_character_context, answer_story_question
    from models import Character, CharacterRelationship
    story_id = bundle.story_id
    allowed, cap = voice_scope(question, bundle, db)
    if not allowed:
        return _refused()
    # Recorded relationships carry no chapter provenance (author-entered, may
    # describe later events) — like untagged memory entries they are used only
    # when the whole manuscript was asked for. Capped character evidence still
    # answers within the chapter limit.
    rels = db.query(CharacterRelationship).filter(
        CharacterRelationship.story_id == story_id).all() if story_id and cap is None else []
    names = {c.character_id: c.name for c in
             (db.query(Character).filter(Character.story_id == story_id).all() if story_id else [])}
    rel_lines = [
        f"{names.get(r.from_character_id, '?')} — {r.relationship_type} "
        f"({r.strength}) → {names.get(r.to_character_id, '?')}"
        f"{': ' + r.description if r.description else ''}"
        for r in rels
    ]
    char_ctx = await retrieve_character_context(story_id, question, db,
                                                max_chapter_number=cap) if story_id else []
    note_ctx = (["Recorded relationships:\n" + "\n".join(rel_lines)] if rel_lines else None)
    if not char_ctx and not rel_lines:
        return {"answer": "I don't have relationship information for those characters yet.",
                "context_used": "none"}
    answer = await answer_story_question(
        question, _pseudo_chunks_from_chapter(bundle),
        character_context=char_ctx or None, note_context=note_ctx, scope_limited=cap is not None)
    return {"answer": answer,
            "context_used": ("relationship graph + " if rel_lines else "") + f"character profiles [{_scope_note(cap)}]"}


# (capability, action) → server_sync adapter
SERVER_ADAPTERS = {
    ("story_qa", "ask"):              _adapt_story_qa,
    ("character_qa", "ask"):          _adapt_character_qa,
    ("character_relationship", "ask"): _adapt_character_relationship,
}


async def run_server_adapter(node, bundle, db, user) -> dict | None:
    """Dispatch a server_sync capability to its feature adapter. Returns the
    feature result (with an 'answer' + 'context_used'), or None if unmapped."""
    fn = SERVER_ADAPTERS.get((node.capability, node.action))
    if fn is None:
        return None
    question = node.params.get("question") or node.params.get("query") or ""
    return await fn(question, bundle, db, user)
