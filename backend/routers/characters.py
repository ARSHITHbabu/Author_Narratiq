import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Character, CharacterProfile, Story
from schemas import (
    CharacterCreate, CharacterOut, CharacterProfileUpdate, CharacterUpdate,
)
from routers.auth import get_current_user, User

router = APIRouter(tags=["characters"])


def _check_story_access(story_id: str, user_id: str, db: Session) -> Story:
    story = db.query(Story).filter(
        Story.story_id == story_id, Story.user_id == user_id
    ).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return story


async def _embed_profile(profile_id: str) -> None:
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
            profile.raw_notes, profile.appearance, profile.personality,
            profile.motivations, profile.backstory, profile.arc_notes,
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
        print(f"[character_embed] failed for {profile_id[:8]}...: {exc}")
    finally:
        db.close()


@router.get("/{story_id}/characters", response_model=list[CharacterOut])
def list_characters(
    story_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_story_access(story_id, current_user.user_id, db)
    return (
        db.query(Character)
        .filter(Character.story_id == story_id)
        .order_by(Character.name)
        .all()
    )


@router.post("/{story_id}/characters", response_model=CharacterOut)
def create_character(
    story_id: str,
    data: CharacterCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_story_access(story_id, current_user.user_id, db)

    existing = (
        db.query(Character)
        .filter(Character.story_id == story_id, Character.name.ilike(data.name.strip()))
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"A character named '{data.name}' already exists in this story",
        )

    character = Character(
        story_id=story_id,
        user_id=current_user.user_id,
        name=data.name.strip(),
        aliases=data.aliases or [],
        role=data.role or "supporting",
        status=data.status or "active",
    )
    db.add(character)
    db.commit()
    db.refresh(character)
    return character


@router.get("/{story_id}/characters/{character_id}", response_model=CharacterOut)
def get_character(
    story_id: str,
    character_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_story_access(story_id, current_user.user_id, db)
    character = db.query(Character).filter(
        Character.character_id == character_id,
        Character.story_id == story_id,
    ).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    return character


@router.patch("/{story_id}/characters/{character_id}", response_model=CharacterOut)
def update_character(
    story_id: str,
    character_id: str,
    data: CharacterUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_story_access(story_id, current_user.user_id, db)
    character = db.query(Character).filter(
        Character.character_id == character_id,
        Character.story_id == story_id,
    ).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    if data.name is not None:
        character.name = data.name.strip()
    if data.aliases is not None:
        character.aliases = data.aliases
    if data.role is not None:
        character.role = data.role
    if data.status is not None:
        character.status = data.status

    character.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(character)
    return character


@router.delete("/{story_id}/characters/{character_id}")
def delete_character(
    story_id: str,
    character_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_story_access(story_id, current_user.user_id, db)
    character = db.query(Character).filter(
        Character.character_id == character_id,
        Character.story_id == story_id,
    ).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    db.delete(character)
    db.commit()
    return {"deleted": character_id}


@router.patch("/{story_id}/characters/{character_id}/profile", response_model=CharacterOut)
async def update_character_profile(
    story_id: str,
    character_id: str,
    data: CharacterProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_story_access(story_id, current_user.user_id, db)
    character = db.query(Character).filter(
        Character.character_id == character_id,
        Character.story_id == story_id,
    ).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    profile = character.profile
    if not profile:
        profile = CharacterProfile(
            character_id=character_id,
            story_id=story_id,
        )
        db.add(profile)

    for field in ("age", "appearance", "personality", "motivations",
                  "backstory", "arc_notes", "raw_notes"):
        val = getattr(data, field)
        if val is not None:
            setattr(profile, field, val)

    profile.updated_at = datetime.utcnow()
    character.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(character)

    # Background: recompute BGE-M3 embedding for Character RAG
    asyncio.create_task(_embed_profile(profile.profile_id))

    return character
