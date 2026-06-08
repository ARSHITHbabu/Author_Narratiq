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
    retrieve_character_context,     # character profiles — for both modes
    retrieve_note_context,          # story notes + note cards — for both modes
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
        Story.user_id  == current_user.user_id,
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
    _fallback_q = db.query(ChapterSummary).filter(
        ChapterSummary.story_id == data.story_id
    )
    if data.current_chapter_number is not None:
        _fallback_q = _fallback_q.filter(
            ChapterSummary.chapter_number <= data.current_chapter_number
        )
    summaries = (
        _fallback_q
        .order_by(ChapterSummary.chapter_number.desc())
        .limit(5)
        .all()
    )
    summary_list = [
        {"chapter": s.chapter_number, "events": s.key_events, "characters": s.characters_present}
        for s in summaries
    ]
    print(f"[plot_assistant] ChapterSummary rows in DB: {len(summaries)}")

    cur_chapter = data.current_chapter_text or ""

    # ── Step 1: intent detection + chapter retrieval in parallel ──────────────
    try:
        intent, retrieved_chunks = await asyncio.gather(
            detect_query_intent(data.question),
            retrieve_relevant_chunks(
                data.question, data.story_id, db, top_k=4,
                max_chapter_number=data.current_chapter_number,
            ),
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

    # ── Step 2: fine-grained chunk retrieval + character context ─────────────
    # For QA: paragraph chunks are the primary retrieval signal.
    #   - Character context is only injected when the question explicitly names
    #     a character (name-mention boost triggers inclusion).  When character
    #     context is injected, chunks are capped at top_k=5 (not 8) to stay
    #     within the Qwen context window (input budget ~3196 tokens).
    # For creative/mixed: character context is always retrieved.  Chapter
    #   summaries are the primary retrieval, so chunks are not fetched.

    text_chunks:       list[dict] = []
    character_context: list[str]  = []

    if intent in ("qa", "mixed"):
        # Detect name mentions before running BGE-M3 so we know the chunk cap
        question_lower = data.question.lower()
        from models import Character as _Char
        story_chars = (
            db.query(_Char)
            .filter(_Char.story_id == data.story_id)
            .all()
        )
        has_name_mention = any(
            c.name.lower() in question_lower or
            any(a.strip().lower() in question_lower for a in (c.aliases or []))
            for c in story_chars
        )

        # Reduce chunk count to top_k=5 when character context will be injected
        qa_top_k = 5 if has_name_mention else 8
        text_chunks = await retrieve_chunks_from_store(
            data.question, data.story_id, db, top_k=qa_top_k,
            max_chapter_number=data.current_chapter_number,
        )
        print(
            f"[plot_assistant] chunk-level retrieval: "
            f"{len(text_chunks)} passage(s) across "
            f"{len({c['chapter'] for c in text_chunks})} chapter(s) "
            f"(top_k={qa_top_k}, name_mention={has_name_mention})"
        )

        # Character context for QA — only when a character is explicitly named
        if has_name_mention:
            character_context = await retrieve_character_context(
                data.story_id, data.question, db, top_k=3, token_budget=600,
            )

    if intent in ("creative", "mixed"):
        # Character context for creative — always retrieve, full budget
        if not character_context:  # avoid double retrieval in mixed mode
            character_context = await retrieve_character_context(
                data.story_id, data.question, db, top_k=3, token_budget=800,
            )

    # ── Note context — retrieved for all intents ──────────────────────────────
    # Token budget is tightened when character context is already injected to
    # avoid overflowing the Qwen context window.
    note_token_budget = 350 if character_context else 500
    note_context: list[str] = await retrieve_note_context(
        data.story_id, data.question, db, top_k=3, token_budget=note_token_budget,
    )

    # ── Intelligence context (P29) — semantic memory + story knowledge ────────
    intel_context: dict | None = None
    try:
        from services.story_intel_service import build_integration_context
        intel_context = await build_integration_context(
            db, data.story_id, query=data.question, top_k=8
        )
    except Exception as exc:
        # Never block the plot assistant if intelligence isn't ready yet, but do
        # log it — silent failures here previously masked missing analysis.
        print(
            f"[plot_assistant] integration context unavailable for "
            f"story={data.story_id[:8]}... ({type(exc).__name__}: {exc}) — "
            f"continuing without it"
        )

    answer:      str | None        = None
    suggestions: list[PlotSuggestion] = []

    # ── Step 3: branch by intent ──────────────────────────────────────────────
    try:
        if intent == "qa":
            answer = await answer_story_question(
                question          = data.question,
                text_chunks       = text_chunks,
                genre_profile     = genre_dict,
                current_chapter   = cur_chapter,
                character_context = character_context or None,
                note_context      = note_context or None,
            )
            print(f"[plot_assistant] QA answer → {len(answer)} chars")

        elif intent == "creative":
            raw = await generate_plot_suggestions(
                question           = data.question,
                current_chapter    = cur_chapter,
                summaries          = summary_list,
                genre_profile      = genre_dict,
                retrieved_chunks   = retrieved_chunks,
                character_profiles = character_context or None,
                note_context       = note_context or None,
                intel_context      = intel_context,
            )
            suggestions = [
                PlotSuggestion(id=s["id"], text=s["text"], rationale=s["rationale"])
                for s in raw
            ]

        else:  # mixed — answer + suggestions in parallel
            answer_coro = answer_story_question(
                question          = data.question,
                text_chunks       = text_chunks,
                genre_profile     = genre_dict,
                current_chapter   = cur_chapter,
                character_context = character_context or None,
                note_context      = note_context or None,
            )
            suggestions_coro = generate_plot_suggestions(
                question           = data.question,
                current_chapter    = cur_chapter,
                summaries          = summary_list,
                genre_profile      = genre_dict,
                retrieved_chunks   = retrieved_chunks,
                character_profiles = character_context or None,
                note_context       = note_context or None,
                intel_context      = intel_context,
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
    except ValueError as exc:
        print(f"[plot_assistant] Invalid model output: {exc}")
        raise HTTPException(status_code=503, detail=str(exc))

    # ── Persist session ───────────────────────────────────────────────────────
    stored_chunks = [
        {
            "chapter":     c["chapter"],
            "chunk_index": c.get("chunk_index", 0),
            "score":       c["score"],
            "words":       c.get("word_count", 0),
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
        if character_context:
            context_desc += f" + {len(character_context)} character profile(s)"
        if note_context:
            context_desc += f" + {len(note_context)} note(s)"
        if genre_profile:
            context_desc = f"{genre_profile.genre} + {context_desc}"
    elif summaries:
        context_desc = f"{len(summaries)} chapter summary/summaries (no embeddings yet)"
        if note_context:
            context_desc += f" + {len(note_context)} note(s)"
        if genre_profile:
            context_desc = f"{genre_profile.genre} genre + {context_desc}"
    else:
        context_desc = "no prior context — write and save chapters first"
        if note_context:
            context_desc = f"{len(note_context)} note(s) + {context_desc}"
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
def mark_suggestion_used(
    session_id:       str,
    suggestion_index: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = db.query(PlotAssistantSession).filter(
        PlotAssistantSession.session_id == session_id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.suggestion_used = suggestion_index
    db.commit()
    return {"updated": True}
