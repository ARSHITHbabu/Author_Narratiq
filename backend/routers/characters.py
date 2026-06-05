import asyncio
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from database import get_db
from models import Character, CharacterProfile, CharacterRelationship, Story
from schemas import (
    CharacterCreate, CharacterGraphResponse, CharacterOut,
    CharacterProfileUpdate, CharacterUpdate,
    RelationshipCreate, RelationshipOut, RelationshipUpdate,
)
from routers.auth import get_current_user, User

router = APIRouter(tags=["characters"])

_VALID_ROLES     = {"protagonist", "antagonist", "supporting", "minor"}
_VALID_STATUSES  = {"active", "deceased", "unknown"}
_VALID_REL_TYPES = {"ally", "rival", "family", "romantic", "mentor", "enemy", "neutral"}
_VALID_STRENGTHS = {"weak", "moderate", "strong", "critical"}


# ── Authorization helper ───────────────────────────────────────────────────────

def _check_story_access(story_id: str, user_id: str, db: Session) -> Story:
    story = db.query(Story).filter(
        Story.story_id == story_id, Story.user_id == user_id
    ).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return story


# ── Background embedding ───────────────────────────────────────────────────────

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
            profile.raw_notes,
            profile.appearance,
            profile.personality,
            profile.goals,
            profile.motivations,
            profile.backstory,
            profile.arc_notes,
            " ".join(profile.traits or []),
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


# ── Character routes ───────────────────────────────────────────────────────────
# IMPORTANT: /search and /graph must be registered BEFORE /{character_id}
# so FastAPI does not interpret "search" or "graph" as a character_id value.

@router.get("/{story_id}/characters/search", response_model=list[CharacterOut])
def search_characters(
    story_id:  str,
    q:         Optional[str] = Query(None, description="Name substring filter"),
    role:      Optional[str] = Query(None, description="protagonist|antagonist|supporting|minor"),
    status:    Optional[str] = Query(None, description="active|deceased|unknown"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_story_access(story_id, current_user.user_id, db)
    query = db.query(Character).filter(Character.story_id == story_id)
    if q:
        query = query.filter(Character.name.ilike(f"%{q.strip()}%"))
    if role:
        query = query.filter(Character.role == role)
    if status:
        query = query.filter(Character.status == status)
    return query.order_by(Character.name).all()


@router.get("/{story_id}/characters/graph", response_model=CharacterGraphResponse)
def get_character_graph(
    story_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_story_access(story_id, current_user.user_id, db)
    nodes = (
        db.query(Character)
        .filter(Character.story_id == story_id)
        .order_by(Character.name)
        .all()
    )
    edges = (
        db.query(CharacterRelationship)
        .filter(CharacterRelationship.story_id == story_id)
        .all()
    )
    return CharacterGraphResponse(nodes=nodes, edges=edges)


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

    if data.role and data.role not in _VALID_ROLES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid role '{data.role}'. Must be one of: {', '.join(sorted(_VALID_ROLES))}",
        )
    if data.status and data.status not in _VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status '{data.status}'. Must be one of: {', '.join(sorted(_VALID_STATUSES))}",
        )

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
    story_id:     str,
    character_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_story_access(story_id, current_user.user_id, db)
    character = db.query(Character).filter(
        Character.character_id == character_id,
        Character.story_id     == story_id,
    ).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    return character


@router.patch("/{story_id}/characters/{character_id}", response_model=CharacterOut)
async def update_character(
    story_id:     str,
    character_id: str,
    data: CharacterUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_story_access(story_id, current_user.user_id, db)
    character = db.query(Character).filter(
        Character.character_id == character_id,
        Character.story_id     == story_id,
    ).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    if data.role is not None and data.role not in _VALID_ROLES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid role '{data.role}'. Must be one of: {', '.join(sorted(_VALID_ROLES))}",
        )
    if data.status is not None and data.status not in _VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status '{data.status}'. Must be one of: {', '.join(sorted(_VALID_STATUSES))}",
        )

    name_changed = False
    if data.name is not None:
        new_name = data.name.strip()
        if new_name != character.name:
            # Check for name collision before renaming
            collision = (
                db.query(Character)
                .filter(
                    Character.story_id == story_id,
                    Character.character_id != character_id,
                    Character.name.ilike(new_name),
                )
                .first()
            )
            if collision:
                raise HTTPException(
                    status_code=409,
                    detail=f"A character named '{new_name}' already exists in this story",
                )
            character.name = new_name
            name_changed = True

    if data.aliases is not None:
        character.aliases = data.aliases
    if data.role is not None:
        character.role = data.role
    if data.status is not None:
        character.status = data.status

    character.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(character)

    # Re-embed profile when name changes — the name appears in the formatted
    # character context block that BGE-M3 encodes.
    if name_changed and character.profile:
        asyncio.create_task(_embed_profile(character.profile.profile_id))

    return character


@router.delete("/{story_id}/characters/{character_id}")
def delete_character(
    story_id:     str,
    character_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_story_access(story_id, current_user.user_id, db)
    character = db.query(Character).filter(
        Character.character_id == character_id,
        Character.story_id     == story_id,
    ).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    db.delete(character)
    db.commit()
    return {"deleted": character_id}


@router.patch("/{story_id}/characters/{character_id}/profile", response_model=CharacterOut)
async def update_character_profile(
    story_id:     str,
    character_id: str,
    data: CharacterProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_story_access(story_id, current_user.user_id, db)
    character = db.query(Character).filter(
        Character.character_id == character_id,
        Character.story_id     == story_id,
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
                  "goals", "backstory", "arc_notes", "raw_notes"):
        val = getattr(data, field)
        if val is not None:
            setattr(profile, field, val)

    # traits: None means "no change"; [] means "clear all traits"
    if data.traits is not None:
        profile.traits = data.traits

    profile.updated_at  = datetime.utcnow()
    character.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(character)

    asyncio.create_task(_embed_profile(profile.profile_id))

    return character


# ── Relationship routes ────────────────────────────────────────────────────────

@router.get("/{story_id}/characters/{character_id}/relationships",
            response_model=list[RelationshipOut])
def list_relationships(
    story_id:     str,
    character_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_story_access(story_id, current_user.user_id, db)
    character = db.query(Character).filter(
        Character.character_id == character_id,
        Character.story_id     == story_id,
    ).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    return (
        db.query(CharacterRelationship)
        .filter(
            CharacterRelationship.story_id == story_id,
            or_(
                CharacterRelationship.from_character_id == character_id,
                CharacterRelationship.to_character_id   == character_id,
            ),
        )
        .order_by(CharacterRelationship.created_at)
        .all()
    )


@router.post("/{story_id}/characters/{character_id}/relationships",
             response_model=RelationshipOut, status_code=201)
def create_relationship(
    story_id:     str,
    character_id: str,
    data: RelationshipCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_story_access(story_id, current_user.user_id, db)

    # Source character must exist in this story
    from_char = db.query(Character).filter(
        Character.character_id == character_id,
        Character.story_id     == story_id,
    ).first()
    if not from_char:
        raise HTTPException(status_code=404, detail="Character not found")

    # Target character must exist in the same story (prevents cross-story edges)
    to_char = db.query(Character).filter(
        Character.character_id == data.to_character_id,
        Character.story_id     == story_id,
    ).first()
    if not to_char:
        raise HTTPException(
            status_code=404,
            detail="Target character not found in this story",
        )

    if character_id == data.to_character_id:
        raise HTTPException(
            status_code=422, detail="A character cannot have a relationship with itself"
        )

    if data.relationship_type not in _VALID_REL_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid relationship_type '{data.relationship_type}'. "
                   f"Must be one of: {', '.join(sorted(_VALID_REL_TYPES))}",
        )

    strength = data.strength or "moderate"
    if strength not in _VALID_STRENGTHS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid strength '{strength}'. "
                   f"Must be one of: {', '.join(sorted(_VALID_STRENGTHS))}",
        )

    existing = db.query(CharacterRelationship).filter(
        CharacterRelationship.story_id          == story_id,
        CharacterRelationship.from_character_id == character_id,
        CharacterRelationship.to_character_id   == data.to_character_id,
        CharacterRelationship.relationship_type == data.relationship_type,
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=(
                f"A '{data.relationship_type}' relationship from this character "
                "to the target already exists"
            ),
        )

    rel = CharacterRelationship(
        story_id          = story_id,
        from_character_id = character_id,
        to_character_id   = data.to_character_id,
        relationship_type = data.relationship_type,
        strength          = strength,
        description       = data.description or "",
        is_mutual         = data.is_mutual or False,
    )
    db.add(rel)
    db.commit()
    db.refresh(rel)
    return rel


@router.patch("/{story_id}/characters/{character_id}/relationships/{relationship_id}",
              response_model=RelationshipOut)
def update_relationship(
    story_id:        str,
    character_id:    str,
    relationship_id: str,
    data: RelationshipUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_story_access(story_id, current_user.user_id, db)

    rel = db.query(CharacterRelationship).filter(
        CharacterRelationship.relationship_id   == relationship_id,
        CharacterRelationship.story_id          == story_id,
        CharacterRelationship.from_character_id == character_id,
    ).first()
    if not rel:
        raise HTTPException(status_code=404, detail="Relationship not found")

    if data.relationship_type is not None:
        if data.relationship_type not in _VALID_REL_TYPES:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid relationship_type '{data.relationship_type}'. "
                       f"Must be one of: {', '.join(sorted(_VALID_REL_TYPES))}",
            )
        rel.relationship_type = data.relationship_type

    if data.strength is not None:
        if data.strength not in _VALID_STRENGTHS:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid strength '{data.strength}'. "
                       f"Must be one of: {', '.join(sorted(_VALID_STRENGTHS))}",
            )
        rel.strength = data.strength

    if data.description is not None:
        rel.description = data.description
    if data.is_mutual is not None:
        rel.is_mutual = data.is_mutual

    rel.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(rel)
    return rel


@router.delete("/{story_id}/characters/{character_id}/relationships/{relationship_id}")
def delete_relationship(
    story_id:        str,
    character_id:    str,
    relationship_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_story_access(story_id, current_user.user_id, db)

    rel = db.query(CharacterRelationship).filter(
        CharacterRelationship.relationship_id   == relationship_id,
        CharacterRelationship.story_id          == story_id,
        CharacterRelationship.from_character_id == character_id,
    ).first()
    if not rel:
        raise HTTPException(status_code=404, detail="Relationship not found")

    db.delete(rel)
    db.commit()
    return {"deleted": relationship_id}
