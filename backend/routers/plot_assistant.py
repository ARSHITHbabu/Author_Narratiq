import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from openai import APIConnectionError, APIStatusError

from database import get_db
from models import Story, PlotAssistantSession, GenreProfile, ChapterSummary
from schemas import PlotAssistantRequest, PlotAssistantResponse, PlotSuggestion
from routers.auth import get_current_user, User
from services.ai_service import (
    detect_query_intent,
    answer_story_question,
    generate_plot_suggestions,
    retrieve_relevant_chunks,       # chapter-level  — for plot suggestions
    retrieve_chunks_from_store,     # paragraph-level — for QA
)

router = APIRouter(tags=["plot-assistant"])


@router.post("/", response_model=PlotAssistantResponse)
async def plot_assistant(
    data: PlotAssistantRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    story = db.query(Story).filter(
        Story.story_id == data.story_id,
        Story.user_id == current_user.user_id,
    ).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    print(
        f"\n[plot_assistant] ── New request ──────────────────────────────\n"
        f"  story_id : {data.story_id[:8]}...\n"
        f"  question : {data.question!r}\n"
        f"  cur_chapter_len : {len(data.current_chapter_text or '')}"
    )

    # ── Load genre profile ────────────────────────────────────────────────────
    genre_profile = db.query(GenreProfile).filter(
        GenreProfile.story_id == data.story_id
    ).first()

    genre_dict = None
    if genre_profile:
        genre_dict = {
            "genre":     genre_profile.genre,
            "sub_genre": genre_profile.sub_genre,
            "tone":      genre_profile.tone,
            "audience":  genre_profile.target_audience,
        }
        print(f"[plot_assistant] Genre: {genre_profile.genre} / {genre_profile.sub_genre}")
    else:
        print("[plot_assistant] No genre profile.")

    # ── Fallback summary list (used if no embeddings available) ───────────────
    summaries = (
        db.query(ChapterSummary)
        .filter(ChapterSummary.story_id == data.story_id)
        .order_by(ChapterSummary.chapter_number.desc())
        .limit(5)
        .all()
    )
    summary_list = [
        {"chapter": s.chapter_number, "events": s.key_events, "characters": s.characters_present}
        for s in summaries
    ]
    print(f"[plot_assistant] ChapterSummary rows in DB: {len(summaries)}")

    # ── Step 1: intent detection + BGE-M3 retrieval in parallel ──────────────
    # Both are independent — run concurrently to reduce latency.
    try:
        intent, retrieved_chunks = await asyncio.gather(
            detect_query_intent(data.question),
            retrieve_relevant_chunks(data.question, data.story_id, db, top_k=4),
        )
    except (APIConnectionError, APIStatusError) as exc:
        print(f"[plot_assistant] vLLM unavailable during intent/retrieval: {exc}")
        raise HTTPException(
            status_code=503,
            detail=(
                "The AI model (Qwen/vLLM) is currently unavailable. "
                "Please wait a moment and try again. "
                f"({type(exc).__name__})"
            ),
        )

    print(
        f"[plot_assistant] intent={intent!r} | "
        f"chapter_summaries_retrieved={len(retrieved_chunks)}"
    )

    cur_chapter = data.current_chapter_text or ""

    # ── Step 2: fine-grained chunk retrieval for QA/mixed ────────────────────
    # For QA we search paragraph-level chunks (not chapter summaries).
    # This scales to any story size: 60 chapters × 10 chunks = 600 vectors,
    # all searched in < 100 ms. Only the top-k most relevant passages are
    # passed to Qwen — the context window stays well within 8192 tokens.
    text_chunks: list[dict] = []
    if intent in ("qa", "mixed"):
        text_chunks = await retrieve_chunks_from_store(
            data.question, data.story_id, db, top_k=8
        )
        print(
            f"[plot_assistant] chunk-level retrieval: "
            f"{len(text_chunks)} passage(s) across "
            f"{len({c['chapter'] for c in text_chunks})} chapter(s)"
        )

    answer: str | None = None
    suggestions: list[PlotSuggestion] = []

    # ── Step 3: branch by intent ──────────────────────────────────────────────
    try:
        if intent == "qa":
            answer = await answer_story_question(
                question=data.question,
                text_chunks=text_chunks,
                genre_profile=genre_dict,
                current_chapter=cur_chapter,
            )
            print(f"[plot_assistant] QA answer → {len(answer)} chars")

        elif intent == "creative":
            raw = await generate_plot_suggestions(
                question=data.question,
                current_chapter=cur_chapter,
                summaries=summary_list,
                genre_profile=genre_dict,
                retrieved_chunks=retrieved_chunks,
            )
            suggestions = [
                PlotSuggestion(id=s["id"], text=s["text"], rationale=s["rationale"])
                for s in raw
            ]

        else:  # mixed — answer + suggestions in parallel
            answer_coro = answer_story_question(
                question=data.question,
                text_chunks=text_chunks,
                genre_profile=genre_dict,
                current_chapter=cur_chapter,
            )
            suggestions_coro = generate_plot_suggestions(
                question=data.question,
                current_chapter=cur_chapter,
                summaries=summary_list,
                genre_profile=genre_dict,
                retrieved_chunks=retrieved_chunks,
            )
            answer, raw = await asyncio.gather(answer_coro, suggestions_coro)
            suggestions = [
                PlotSuggestion(id=s["id"], text=s["text"], rationale=s["rationale"])
                for s in raw
            ]
            print(f"[plot_assistant] mixed: answer={len(answer)} chars, {len(suggestions)} suggestions")

    except (APIConnectionError, APIStatusError) as exc:
        print(f"[plot_assistant] vLLM unavailable: {exc}")
        raise HTTPException(
            status_code=503,
            detail=(
                "The AI model (Qwen/vLLM) is currently unavailable. "
                "Please wait a moment and try again. "
                f"({type(exc).__name__})"
            ),
        )

    # ── Persist session ───────────────────────────────────────────────────────
    stored_chunks = [
        {
            "chapter":    c["chapter"],
            "chunk_index": c.get("chunk_index", 0),
            "score":      c["score"],
            "words":      c.get("word_count", 0),
        }
        for c in text_chunks
    ]
    session = PlotAssistantSession(
        story_id=data.story_id,
        user_id=current_user.user_id,
        question=data.question,
        retrieved_chunks=stored_chunks,
        suggestions_returned=[s.model_dump() for s in suggestions],
        tokens_used=len(data.question.split()) * 4,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    # ── Build context description ─────────────────────────────────────────────
    if retrieved_chunks:
        chapters_used = sorted({c["chapter"] for c in retrieved_chunks})
        ch_list = ", ".join(f"Ch{n}" for n in chapters_used)
        context_desc = f"story context ({ch_list} retrieved via BGE-M3)"
        if genre_profile:
            context_desc = f"{genre_profile.genre} + {context_desc}"
    elif summaries:
        context_desc = f"{len(summaries)} chapter summary/summaries (no embeddings yet)"
        if genre_profile:
            context_desc = f"{genre_profile.genre} genre + {context_desc}"
    else:
        context_desc = "no prior context — write and save chapters first"
        if genre_profile:
            context_desc = f"{genre_profile.genre} genre profile + {context_desc}"

    print(f"[plot_assistant] mode={intent!r} | context_used={context_desc!r}")
    print("[plot_assistant] ── Done ─────────────────────────────────────────")

    return PlotAssistantResponse(
        session_id=session.session_id,
        mode=intent,
        answer=answer,
        suggestions=suggestions,
        context_used=context_desc,
        tokens_used=session.tokens_used,
    )


@router.patch("/{session_id}/use")
def mark_suggestion_used(session_id: str, suggestion_index: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = db.query(PlotAssistantSession).filter(PlotAssistantSession.session_id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.suggestion_used = suggestion_index
    db.commit()
    return {"updated": True}
