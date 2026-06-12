"""
Global Activity Timeline router.

  POST /api/stories/{story_id}/activity   — record a meaningful action
  GET  /api/stories/{story_id}/activity   — list (filter by category, search)

Additive and self-contained — no existing routers/services are modified. The
frontend records events after successful actions (transforms, analyses, exports,
CRUD, voice edits); this is an extensible, queryable log, not a version-history
system. Owner-scoped today; `user_id` + metadata are captured so collaboration/
audit can build on it later.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from database import get_db
from models import Story, ActivityEvent, User
from schemas import ActivityEventCreate, ActivityEventOut
from routers.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["activity"])

_CATEGORIES = {"ai", "analysis", "project", "voice", "export"}


def _owned_story(story_id: str, user_id: str, db: Session) -> Story:
    story = db.query(Story).filter(Story.story_id == story_id,
                                   Story.user_id == user_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return story


@router.post("/{story_id}/activity", response_model=ActivityEventOut)
def record_activity(
    story_id: str,
    body: ActivityEventCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _owned_story(story_id, current_user.user_id, db)
    category = body.category if body.category in _CATEGORIES else "project"
    ev = ActivityEvent(
        story_id=story_id,
        user_id=current_user.user_id,
        category=category,
        type=body.type[:60],
        title=(body.title or "")[:300],
        summary=(body.summary or "")[:2000],
        ref_type=(body.ref_type or "")[:40],
        ref_id=(body.ref_id or "")[:64],
        metadata_json=body.metadata or {},
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


@router.get("/{story_id}/activity", response_model=list[ActivityEventOut])
def list_activity(
    story_id: str,
    category: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _owned_story(story_id, current_user.user_id, db)
    query = db.query(ActivityEvent).filter(ActivityEvent.story_id == story_id)
    if category and category in _CATEGORIES:
        query = query.filter(ActivityEvent.category == category)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(ActivityEvent.title.ilike(like),
                                 ActivityEvent.summary.ilike(like),
                                 ActivityEvent.type.ilike(like)))
    return (query.order_by(ActivityEvent.created_at.desc())
            .limit(max(1, min(limit, 500))).all())
