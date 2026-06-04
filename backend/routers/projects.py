from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Story, Chapter
from schemas import StoryCreate, StoryUpdate, StoryOut
from routers.auth import get_current_user, User

router = APIRouter(tags=["projects"])


@router.get("/", response_model=list[StoryOut])
def list_projects(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Story).filter(Story.user_id == current_user.user_id).order_by(Story.updated_at.desc()).all()


@router.post("/", response_model=StoryOut)
def create_project(data: StoryCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    story = Story(user_id=current_user.user_id, title=data.title, description=data.description or "")
    db.add(story)
    db.commit()
    # Create first chapter automatically
    chapter = Chapter(story_id=story.story_id, chapter_number=1, title="Chapter 1", content="")
    db.add(chapter)
    db.commit()
    db.refresh(story)
    return story


@router.get("/{story_id}", response_model=StoryOut)
def get_project(story_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    story = db.query(Story).filter(Story.story_id == story_id, Story.user_id == current_user.user_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Project not found")
    return story


@router.patch("/{story_id}", response_model=StoryOut)
def update_project(story_id: str, data: StoryUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    story = db.query(Story).filter(Story.story_id == story_id, Story.user_id == current_user.user_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Project not found")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(story, field, value)
    story.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(story)
    return story


@router.delete("/{story_id}")
def delete_project(story_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    story = db.query(Story).filter(Story.story_id == story_id, Story.user_id == current_user.user_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Project not found")
    db.delete(story)
    db.commit()
    return {"deleted": story_id}
