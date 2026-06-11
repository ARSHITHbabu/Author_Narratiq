"""
Phase 2 — P2-11 Audio Notes Transcription
Upload an audio recording, transcribe via faster-whisper, optionally append to a story note.
Background task returns job_id immediately; client polls GET /{audio_id} for completion.
"""
import asyncio
import os
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from database import get_db
from models import Story, StoryNote, AudioUpload
from schemas import AudioTranscribeResponse, AudioUploadOut, AudioConfirmRequest, AudioConfirmResponse
from routers.auth import get_current_user, User

router = APIRouter(tags=["audio"])

_AUDIO_UPLOAD_DIR = "uploads/audio"
_ALLOWED_EXTENSIONS = {".mp3", ".mp4", ".m4a", ".wav", ".ogg", ".flac", ".webm", ".opus"}
_MAX_AUDIO_SIZE_MB  = 100


def _get_owned_story(story_id: str, user_id: str, db: Session) -> Story:
    story = db.query(Story).filter(
        Story.story_id == story_id,
        Story.user_id  == user_id,
    ).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return story


async def _run_transcription(audio_id: str, audio_path: str) -> None:
    """
    Background task: transcribe the audio file with faster-whisper,
    clean the transcript with Qwen, then persist results.
    """
    from database import SessionLocal
    from services.audio_service import transcribe_audio, clean_transcript

    db = SessionLocal()
    try:
        upload = db.query(AudioUpload).filter(AudioUpload.audio_id == audio_id).first()
        if not upload:
            return

        # ── Transcription ──────────────────────────────────────────────────────
        result = await transcribe_audio(audio_path)
        raw = result.get("raw_transcript", "")
        cleaned = await clean_transcript(raw)

        upload.raw_transcript    = raw
        upload.cleaned_text      = cleaned
        upload.language_detected = result.get("language_detected", "")
        upload.duration_seconds  = result.get("duration_seconds", 0.0)
        upload.confidence        = result.get("confidence", 0.0)
        upload.word_count        = result.get("word_count", 0)
        upload.status            = "completed"
        upload.updated_at        = datetime.utcnow()
        db.commit()
        print(f"[audio] transcription done for {audio_id[:8]}... — "
              f"{upload.word_count} words, lang={upload.language_detected}")

    except Exception as exc:
        print(f"[audio] transcription failed for {audio_id[:8]}... : {exc}")
        try:
            upload = db.query(AudioUpload).filter(AudioUpload.audio_id == audio_id).first()
            if upload:
                upload.status     = "failed"
                upload.updated_at = datetime.utcnow()
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


@router.post("/{story_id}/audio", response_model=AudioTranscribeResponse)
async def upload_audio(
    request: Request,
    story_id: str,
    file: UploadFile = File(...),
    note_id: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Upload an audio file for transcription.
    Accepted formats: mp3, mp4, m4a, wav, ogg, flac, webm, opus.
    Returns audio_id + status="processing". Poll GET /{audio_id} for the transcript.
    """
    # Reject oversized uploads before reading the body (saves memory on large abusive requests)
    cl = request.headers.get("content-length")
    if cl and int(cl) > _MAX_AUDIO_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"Audio file too large. Maximum is {_MAX_AUDIO_SIZE_MB} MB.",
        )

    _get_owned_story(story_id, current_user.user_id, db)

    # Validate note belongs to this story if provided
    if note_id:
        note = db.query(StoryNote).filter(
            StoryNote.note_id == note_id,
            StoryNote.story_id == story_id,
        ).first()
        if not note:
            raise HTTPException(status_code=404, detail="Story note not found")

    # ── File validation ────────────────────────────────────────────────────────
    filename = file.filename or "audio"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported audio format '{ext}'. "
                   f"Supported: {', '.join(sorted(_ALLOWED_EXTENSIONS))}",
        )

    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > _MAX_AUDIO_SIZE_MB:
        raise HTTPException(
            status_code=413,
            detail=f"Audio file too large ({size_mb:.1f} MB). Maximum is {_MAX_AUDIO_SIZE_MB} MB.",
        )

    # ── Persist to disk ────────────────────────────────────────────────────────
    os.makedirs(_AUDIO_UPLOAD_DIR, exist_ok=True)
    audio_id   = str(uuid.uuid4())
    audio_path = os.path.join(_AUDIO_UPLOAD_DIR, f"{audio_id}{ext}")
    with open(audio_path, "wb") as f:
        f.write(content)

    # ── Create DB record ───────────────────────────────────────────────────────
    upload = AudioUpload(
        audio_id=audio_id,
        story_id=story_id,
        user_id=current_user.user_id,
        note_id=note_id,
        audio_path=audio_path,
        status="processing",
    )
    db.add(upload)
    db.commit()

    # ── Kick off background transcription ─────────────────────────────────────
    asyncio.create_task(_run_transcription(audio_id, audio_path))

    return AudioTranscribeResponse(
        audio_id=audio_id,
        status="processing",
        duration_seconds=None,
    )


@router.get("/{story_id}/audio/{audio_id}", response_model=AudioUploadOut)
def get_audio_upload(
    story_id:  str,
    audio_id:  str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Poll transcription status. Returns the transcript when status='completed'."""
    _get_owned_story(story_id, current_user.user_id, db)

    upload = db.query(AudioUpload).filter(
        AudioUpload.audio_id == audio_id,
        AudioUpload.story_id == story_id,
    ).first()
    if not upload:
        raise HTTPException(status_code=404, detail="Audio upload not found")
    return upload


@router.get("/{story_id}/audio", response_model=list[AudioUploadOut])
def list_audio_uploads(
    story_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all audio uploads for a story."""
    _get_owned_story(story_id, current_user.user_id, db)
    return (
        db.query(AudioUpload)
        .filter(AudioUpload.story_id == story_id)
        .order_by(AudioUpload.created_at.desc())
        .all()
    )


@router.post("/{story_id}/audio/{audio_id}/confirm", response_model=AudioConfirmResponse)
def confirm_audio_transcript(
    story_id:  str,
    audio_id:  str,
    body: AudioConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Confirm a completed transcript and append it to the linked story note.
    Optionally provide an author-edited version via body.edited_text.
    Idempotent: re-confirming overwrites the note content with the current text.
    """
    _get_owned_story(story_id, current_user.user_id, db)

    upload = db.query(AudioUpload).filter(
        AudioUpload.audio_id == audio_id,
        AudioUpload.story_id == story_id,
    ).first()
    if not upload:
        raise HTTPException(status_code=404, detail="Audio upload not found")
    if upload.status != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Transcript not ready (status={upload.status}). Wait for completion.",
        )

    # Resolve target note
    note_id = body.note_id or upload.note_id
    if not note_id:
        raise HTTPException(
            status_code=422,
            detail="No note_id provided and no note was linked at upload time.",
        )

    note = db.query(StoryNote).filter(
        StoryNote.note_id  == note_id,
        StoryNote.story_id == story_id,
    ).first()
    if not note:
        raise HTTPException(status_code=404, detail="Story note not found")

    # Text to save — prefer author-edited version, else cleaned, else raw
    text_to_save = (
        body.edited_text.strip()
        if body.edited_text and body.edited_text.strip()
        else (upload.cleaned_text or upload.raw_transcript or "")
    )

    # Append with separator if note already has content
    if note.content:
        note.content = note.content.rstrip() + "\n\n---\n\n" + text_to_save
    else:
        note.content = text_to_save

    upload.note_id   = note_id
    upload.confirmed = True
    upload.updated_at = datetime.utcnow()
    db.commit()

    return AudioConfirmResponse(
        audio_id=audio_id,
        note_id=note_id,
        appended=True,
    )
