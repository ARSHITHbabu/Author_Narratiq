import asyncio
import html as _html
import os
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Response
from sqlalchemy.orm import Session

from database import get_db
from models import Chapter, Character, CharacterProfile, NoteCard, OcrUpload, Story, StoryNote, StoryVersion
from schemas import (
    OcrConfirm, OcrConfirmResponse, OcrExtractResponse, OcrSuggestion,
    StoryNoteOut, StoryNoteCreate, StoryNoteUpdate,
    NoteCardOut, NoteCardCreate, NoteCardUpdate,
)
from routers.auth import get_current_user, User
from services.ocr_service import process_ocr_image
from services.ai_service import generate_ocr_suggestions

router = APIRouter(tags=["ocr"])

UPLOAD_DIR = "uploads/ocr"
os.makedirs(UPLOAD_DIR, exist_ok=True)

_VALID_DESTINATIONS = {"story_notes", "chapter_draft", "character_profile", "note_card"}


# ── Authorization helper ───────────────────────────────────────────────────────

def _get_owned_story(story_id: str, user_id: str, db: Session) -> Story:
    """Return the story if it exists and belongs to user_id, else raise 404."""
    story = db.query(Story).filter(
        Story.story_id == story_id, Story.user_id == user_id
    ).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return story


# ── Helpers ───────────────────────────────────────────────────────────────────

def _auto_title(text: str, max_len: int = 72) -> str:
    """Derive a title from the first non-empty line of text."""
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    return first[:max_len] if first else "Untitled Note"


def _plain_to_tiptap_html(text: str) -> str:
    """
    Convert plain OCR text to TipTap-compatible HTML.

    Each non-empty line becomes a <p> element.  All content is HTML-escaped
    so that OCR artefacts containing < > & do not corrupt the editor document.
    A <hr /> separator visually marks the injection boundary.
    """
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    paras = "".join(f"<p>{_html.escape(ln)}</p>" for ln in lines)
    return f"<hr />{paras}"


# ── Background tasks ──────────────────────────────────────────────────────────

async def _regenerate_chapter_index(
    chapter_id: str, story_id: str, chapter_number: int, content: str
) -> None:
    """Re-summarise and re-embed a chapter after OCR content is appended."""
    from database import SessionLocal
    from services.ai_service import summarize_and_embed_chapter
    db = SessionLocal()
    try:
        await summarize_and_embed_chapter(chapter_id, story_id, chapter_number, content, db)
    except Exception as exc:
        print(f"[ocr→index bg] chapter {chapter_id[:8]}...: {exc}")
    finally:
        db.close()


async def _embed_character_profile(profile_id: str) -> None:
    """
    Compute and store a BGE-M3 embedding for a character profile.

    Combines all structured fields and raw_notes into one text block so the
    embedding captures the full character description for Character RAG retrieval.
    """
    from database import SessionLocal
    from services.ai_service import embed_text
    db = SessionLocal()
    try:
        profile = db.query(CharacterProfile).filter(
            CharacterProfile.profile_id == profile_id
        ).first()
        if not profile:
            return
        parts = [
            profile.raw_notes,
            profile.appearance,
            profile.personality,
            profile.motivations,
            profile.backstory,
            profile.arc_notes,
        ]
        combined = " ".join(p for p in parts if p and p.strip())
        if not combined.strip():
            return
        emb = await embed_text(combined)
        profile.embedding = emb
        profile.updated_at = datetime.utcnow()
        db.commit()
        print(f"[character_embed] profile {profile_id[:8]}... done ({len(emb)}-dim)")
    except Exception as exc:
        print(f"[character_embed] failed for profile {profile_id[:8]}...: {exc}")
    finally:
        db.close()


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/extract/{story_id}", response_model=OcrExtractResponse)
async def extract_ocr(
    story_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    allowed = {"image/jpeg", "image/png", "image/webp"}
    if file.content_type not in allowed:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, WebP images are accepted")

    # BUG-1: verify the authenticated user owns this story before creating any
    # upload record or touching the filesystem.
    _get_owned_story(story_id, current_user.user_id, db)

    file_id = str(uuid.uuid4())
    file_path = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    try:
        result = await process_ocr_image(file_path)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        print(f"[ocr endpoint] Unexpected pipeline error: {exc}")
        raise HTTPException(
            status_code=500,
            detail="OCR processing failed unexpectedly. Please try again.",
        )

    raw_suggestions = await generate_ocr_suggestions(result["raw_text"], story_id, db)
    suggestions = [OcrSuggestion(**s) for s in raw_suggestions]

    upload = OcrUpload(
        story_id=story_id,
        user_id=current_user.user_id,
        image_path=file_path,
        ocr_engine=result["ocr_engine"],
        raw_ocr_text=result["raw_text"],
        cleaned_text=result["cleaned_text"],
        note_type=result["note_type"],
        confidence=result["confidence"],
        confirmed=False,
    )
    db.add(upload)
    db.commit()
    db.refresh(upload)

    return OcrExtractResponse(
        upload_id=upload.upload_id,
        raw_text=result["raw_text"],
        cleaned_text=result["cleaned_text"],
        note_type=result["note_type"],
        confidence=result["confidence"],
        ocr_engine=result["ocr_engine"],
        lines_detected=result.get("lines_detected", 0),
        suggestions=suggestions,
    )


@router.post("/confirm", response_model=OcrConfirmResponse)
async def confirm_ocr(
    data: OcrConfirm,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # ── Validate destination ──────────────────────────────────────────────────
    if data.destination not in _VALID_DESTINATIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid destination '{data.destination}'. "
                   f"Must be one of: {', '.join(sorted(_VALID_DESTINATIONS))}",
        )

    # ── Fetch upload and authorise ────────────────────────────────────────────
    upload = db.query(OcrUpload).filter(OcrUpload.upload_id == data.upload_id).first()
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    if upload.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Not authorised to confirm this upload")

    # BUG-2: idempotency guard — each upload may only be confirmed once.
    # A second call with the same upload_id would otherwise produce duplicate
    # StoryNotes, NoteCards, chapter injections, or profile appends.
    if upload.confirmed:
        raise HTTPException(status_code=409, detail="Upload has already been confirmed")

    # ── Persist the author-edited text and mark as confirmed ──────────────────
    upload.author_edited_text = data.final_text
    upload.destination = data.destination
    upload.confirmed = True
    db.commit()

    # ── Route to destination ──────────────────────────────────────────────────
    target_id: str | None = None

    # ── chapter_draft ─────────────────────────────────────────────────────────
    if data.destination == "chapter_draft":
        if not data.chapter_id:
            raise HTTPException(
                status_code=400,
                detail="chapter_id is required when destination is 'chapter_draft'",
            )

        chapter = db.query(Chapter).filter(
            Chapter.chapter_id == data.chapter_id,
            Chapter.story_id == upload.story_id,
        ).first()
        if not chapter:
            raise HTTPException(status_code=404, detail="Chapter not found")

        story = db.query(Story).filter(
            Story.story_id == chapter.story_id,
            Story.user_id == current_user.user_id,
        ).first()
        if not story:
            raise HTTPException(status_code=403, detail="Not authorised to modify this chapter")

        # Save a version snapshot before appending
        last_ver = (
            db.query(StoryVersion)
            .filter(StoryVersion.chapter_id == chapter.chapter_id)
            .order_by(StoryVersion.version_number.desc())
            .first()
        )
        next_ver = (last_ver.version_number + 1) if last_ver else 1
        if chapter.content:
            db.add(StoryVersion(
                chapter_id=chapter.chapter_id,
                content=chapter.content,
                version_number=next_ver,
                label=f"Before OCR injection v{next_ver}",
            ))

        # Append OCR text as TipTap-compatible HTML
        ocr_html = _plain_to_tiptap_html(data.final_text)
        chapter.content = (chapter.content or "") + ocr_html
        chapter.updated_at = datetime.utcnow()

        # Recompute word count from stripped HTML
        from services.ai_service import _strip_html
        plain = _strip_html(chapter.content)
        chapter.word_count = len(plain.split()) if plain.strip() else 0

        # Update story total word count
        total = sum(c.word_count for c in story.chapters)
        story.word_count = total
        story.updated_at = datetime.utcnow()
        db.commit()

        # Background: re-summarise and re-embed the chapter
        asyncio.create_task(
            _regenerate_chapter_index(
                chapter_id=chapter.chapter_id,
                story_id=story.story_id,
                chapter_number=chapter.chapter_number,
                content=chapter.content,
            )
        )

        target_id = chapter.chapter_id
        print(
            f"[ocr_inject] chapter_draft → chapter {chapter.chapter_id[:8]}... "
            f"(ch{chapter.chapter_number}, story {story.story_id[:8]}...)"
        )

    # ── story_notes ───────────────────────────────────────────────────────────
    elif data.destination == "story_notes":
        note = StoryNote(
            story_id=upload.story_id,
            user_id=current_user.user_id,
            title=_auto_title(data.final_text),
            content=data.final_text,
            ocr_upload_id=upload.upload_id,
        )
        db.add(note)
        db.commit()
        db.refresh(note)
        target_id = note.note_id
        print(f"[ocr_inject] story_notes → note {note.note_id[:8]}...")

    # ── note_card ─────────────────────────────────────────────────────────────
    elif data.destination == "note_card":
        card = NoteCard(
            story_id=upload.story_id,
            user_id=current_user.user_id,
            title=_auto_title(data.final_text),
            content=data.final_text,
            ocr_upload_id=upload.upload_id,
        )
        db.add(card)
        db.commit()
        db.refresh(card)
        target_id = card.card_id
        print(f"[ocr_inject] note_card → card {card.card_id[:8]}...")

    # ── character_profile ─────────────────────────────────────────────────────
    elif data.destination == "character_profile":
        char_name = (data.character_name or "").strip()
        if not char_name:
            raise HTTPException(
                status_code=400,
                detail="character_name is required when destination is 'character_profile'",
            )

        # Find or create the character (case-insensitive match within this story)
        character = (
            db.query(Character)
            .filter(
                Character.story_id == upload.story_id,
                Character.name.ilike(char_name),
            )
            .first()
        )
        if not character:
            character = Character(
                story_id=upload.story_id,
                user_id=current_user.user_id,
                name=char_name,
            )
            db.add(character)
            db.flush()   # obtain character_id before creating profile
            print(f"[ocr_inject] created new character '{char_name}' ({character.character_id[:8]}...)")

        # Get or create the character profile
        profile = (
            db.query(CharacterProfile)
            .filter(CharacterProfile.character_id == character.character_id)
            .first()
        )
        if not profile:
            profile = CharacterProfile(
                character_id=character.character_id,
                story_id=upload.story_id,
                raw_notes=data.final_text,
                ocr_upload_id=upload.upload_id,
            )
            db.add(profile)
        else:
            # Append to existing raw_notes with a clear separator
            existing = (profile.raw_notes or "").strip()
            profile.raw_notes = f"{existing}\n\n---\n\n{data.final_text}" if existing else data.final_text
            profile.ocr_upload_id = upload.upload_id
            profile.updated_at = datetime.utcnow()

        character.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(profile)
        target_id = profile.profile_id

        # Background: compute BGE-M3 embedding for Character RAG
        asyncio.create_task(_embed_character_profile(profile.profile_id))
        print(f"[ocr_inject] character_profile → '{char_name}' profile {profile.profile_id[:8]}...")

    return OcrConfirmResponse(
        confirmed=True,
        destination=data.destination,
        injected=True,
        target_id=target_id,
    )


@router.get("/{story_id}/uploads")
def list_uploads(
    story_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # BUG-3: verify ownership before exposing upload records.
    _get_owned_story(story_id, current_user.user_id, db)
    uploads = (
        db.query(OcrUpload)
        .filter(OcrUpload.story_id == story_id, OcrUpload.confirmed == True)
        .all()
    )
    return [
        {
            "upload_id":         u.upload_id,
            "note_type":         u.note_type,
            "cleaned_text":      u.cleaned_text,
            "author_edited_text": u.author_edited_text,
            "destination":       u.destination,
            "confidence":        u.confidence,
            "created_at":        u.created_at,
        }
        for u in uploads
    ]


@router.get("/{story_id}/notes", response_model=list[StoryNoteOut])
def list_story_notes(
    story_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_owned_story(story_id, current_user.user_id, db)
    return (
        db.query(StoryNote)
        .filter(StoryNote.story_id == story_id)
        .order_by(StoryNote.created_at.desc())
        .all()
    )


@router.get("/{story_id}/note-cards", response_model=list[NoteCardOut])
def list_note_cards(
    story_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_owned_story(story_id, current_user.user_id, db)
    return (
        db.query(NoteCard)
        .filter(NoteCard.story_id == story_id)
        .order_by(NoteCard.created_at.desc())
        .all()
    )


# ── StoryNote CRUD ────────────────────────────────────────────────────────────

@router.post("/{story_id}/notes", response_model=StoryNoteOut, status_code=201)
def create_story_note(
    story_id: str,
    data: StoryNoteCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_owned_story(story_id, current_user.user_id, db)
    note = StoryNote(
        story_id=story_id,
        user_id=current_user.user_id,
        title=data.title or "",
        content=data.content,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


@router.patch("/notes/{note_id}", response_model=StoryNoteOut)
def update_story_note(
    note_id: str,
    data: StoryNoteUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = db.query(StoryNote).filter(StoryNote.note_id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    if note.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Not authorised to edit this note")
    if data.title is not None:
        note.title = data.title
    if data.content is not None:
        note.content = data.content
    note.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(note)
    return note


@router.delete("/notes/{note_id}", status_code=204)
def delete_story_note(
    note_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = db.query(StoryNote).filter(StoryNote.note_id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    if note.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Not authorised to delete this note")
    db.delete(note)
    db.commit()
    return Response(status_code=204)


# ── NoteCard CRUD ─────────────────────────────────────────────────────────────

@router.post("/{story_id}/note-cards", response_model=NoteCardOut, status_code=201)
def create_note_card(
    story_id: str,
    data: NoteCardCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_owned_story(story_id, current_user.user_id, db)
    card = NoteCard(
        story_id=story_id,
        user_id=current_user.user_id,
        title=data.title or "",
        content=data.content,
        card_type=data.card_type or "general",
    )
    db.add(card)
    db.commit()
    db.refresh(card)
    return card


@router.patch("/note-cards/{card_id}", response_model=NoteCardOut)
def update_note_card(
    card_id: str,
    data: NoteCardUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    card = db.query(NoteCard).filter(NoteCard.card_id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Note card not found")
    if card.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Not authorised to edit this note card")
    if data.title is not None:
        card.title = data.title
    if data.content is not None:
        card.content = data.content
    if data.card_type is not None:
        card.card_type = data.card_type
    card.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(card)
    return card


@router.delete("/note-cards/{card_id}", status_code=204)
def delete_note_card(
    card_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    card = db.query(NoteCard).filter(NoteCard.card_id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Note card not found")
    if card.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Not authorised to delete this note card")
    db.delete(card)
    db.commit()
    return Response(status_code=204)
