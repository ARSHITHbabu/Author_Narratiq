import os
import uuid
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import OcrUpload
from schemas import OcrExtractResponse, OcrConfirm
from routers.auth import get_current_user, User
from services.ocr_service import process_ocr_image

router = APIRouter(tags=["ocr"])

UPLOAD_DIR = "uploads/ocr"
os.makedirs(UPLOAD_DIR, exist_ok=True)


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

    file_id = str(uuid.uuid4())
    file_path = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    try:
        result = await process_ocr_image(file_path)
    except RuntimeError as exc:
        # Model not installed or pipeline crashed — surface as 500 with clear message
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        print(f"[ocr endpoint] Unexpected pipeline error: {exc}")
        raise HTTPException(
            status_code=500,
            detail="OCR processing failed unexpectedly. Please try again.",
        )

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
    )


@router.post("/confirm")
def confirm_ocr(data: OcrConfirm, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    upload = db.query(OcrUpload).filter(OcrUpload.upload_id == data.upload_id).first()
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    upload.author_edited_text = data.final_text
    upload.destination = data.destination
    upload.confirmed = True
    db.commit()
    return {"confirmed": True, "destination": data.destination}


@router.get("/{story_id}/uploads")
def list_uploads(story_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    uploads = db.query(OcrUpload).filter(OcrUpload.story_id == story_id, OcrUpload.confirmed == True).all()
    return [
        {
            "upload_id": u.upload_id,
            "note_type": u.note_type,
            "cleaned_text": u.cleaned_text,
            "author_edited_text": u.author_edited_text,
            "destination": u.destination,
            "confidence": u.confidence,
            "created_at": u.created_at,
        }
        for u in uploads
    ]
