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

logger = logging.getLogger(__name__)


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
    chunks = await retrieve_chunks_from_store(question, story_id, db, top_k=8) if story_id else []
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
    answer = await answer_story_question(
        question, chunks, genre_profile=_genre_dict(story_id, db),
        current_chapter=bundle.chapter_text or "", note_context=notes or None)
    return {"answer": answer, "context_used": ", ".join(used + (["story notes"] if notes else []))}


async def _adapt_character_qa(question, bundle, db, user) -> dict:
    from services.ai_service import (retrieve_character_context, retrieve_chunks_from_store,
                                     answer_story_question)
    story_id = bundle.story_id
    char_ctx = await retrieve_character_context(story_id, question, db) if story_id else []
    chunks = await retrieve_chunks_from_store(question, story_id, db, top_k=4) if story_id else []
    if not chunks:
        chunks = _pseudo_chunks_from_chapter(bundle)
    if not char_ctx and not chunks:
        return {"answer": "I couldn't find that character in this story yet.",
                "context_used": "none"}
    answer = await answer_story_question(
        question, chunks, current_chapter=bundle.chapter_text or "",
        character_context=char_ctx or None)
    return {"answer": answer, "context_used": "character profiles (RAG)" +
            (" + story passages" if chunks and chunks[0].get("score", 0) != 1.0 else "")}


async def _adapt_character_relationship(question, bundle, db, user) -> dict:
    from services.ai_service import retrieve_character_context, answer_story_question
    from models import Character, CharacterRelationship
    story_id = bundle.story_id
    rels = db.query(CharacterRelationship).filter(
        CharacterRelationship.story_id == story_id).all() if story_id else []
    names = {c.character_id: c.name for c in
             (db.query(Character).filter(Character.story_id == story_id).all() if story_id else [])}
    rel_lines = [
        f"{names.get(r.from_character_id, '?')} — {r.relationship_type} "
        f"({r.strength}) → {names.get(r.to_character_id, '?')}"
        f"{': ' + r.description if r.description else ''}"
        for r in rels
    ]
    char_ctx = await retrieve_character_context(story_id, question, db) if story_id else []
    note_ctx = (["Recorded relationships:\n" + "\n".join(rel_lines)] if rel_lines else None)
    if not char_ctx and not rel_lines:
        return {"answer": "I don't have relationship information for those characters yet.",
                "context_used": "none"}
    answer = await answer_story_question(
        question, _pseudo_chunks_from_chapter(bundle),
        character_context=char_ctx or None, note_context=note_ctx)
    return {"answer": answer,
            "context_used": "relationship graph + character profiles"}


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
