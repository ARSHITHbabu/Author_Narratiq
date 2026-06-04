import io
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database import get_db
from models import Story, Chapter
from schemas import ExportRequest
from routers.auth import get_current_user, User

router = APIRouter(tags=["export"])


@router.post("/")
async def export_manuscript(
    data: ExportRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    story = db.query(Story).filter(Story.story_id == data.story_id, Story.user_id == current_user.user_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    chapters = db.query(Chapter).filter(Chapter.story_id == data.story_id).order_by(Chapter.chapter_number).all()

    if data.format == "docx":
        return _export_docx(story, chapters, data)
    elif data.format == "pdf":
        return _export_txt_as_pdf_placeholder(story, chapters)
    else:
        raise HTTPException(status_code=400, detail="Format must be 'docx' or 'pdf'")


def _export_docx(story, chapters, data):
    """
    # MODEL_PLACEHOLDER: python-docx
    # In production: use python-docx with manuscript template
    # For MVP-lite: return plain text as .txt (docx library not required to be installed)
    """
    lines = [f"{story.title}\n", "=" * len(story.title) + "\n\n"]
    if story.description:
        lines.append(f"{story.description}\n\n")
    for ch in chapters:
        if data.include_chapter_numbers:
            lines.append(f"\nChapter {ch.chapter_number}: {ch.title}\n")
            lines.append("-" * 40 + "\n\n")
        else:
            lines.append(f"\n{ch.title}\n\n")
        lines.append((ch.content or "") + "\n\n")

    content = "".join(lines).encode("utf-8")
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{story.title}.docx"'},
    )


def _export_txt_as_pdf_placeholder(story, chapters):
    """
    # MODEL_PLACEHOLDER: ReportLab Platypus for production PDF
    """
    lines = [f"{story.title}\n\n"]
    for ch in chapters:
        lines.append(f"Chapter {ch.chapter_number}: {ch.title}\n\n")
        lines.append((ch.content or "") + "\n\n")

    content = "".join(lines).encode("utf-8")
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{story.title}.pdf"'},
    )
