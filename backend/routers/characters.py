import asyncio
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from database import get_db
from models import Character, CharacterProfile, CharacterRelationship, Story
from schemas import (
    CastConfirmRequest, CastConfirmResult, CastGenerationResult, CastSuggestion,
    CharacterCreate, CharacterGraphResponse, CharacterMentionOut, CharacterHintOut,
    CharacterOut, CharacterProfileUpdate, CharacterUpdate,
    EnrichResult, EnrichSuggestion,
    RelationshipCreate, RelationshipOut, RelationshipUpdate,
)
from routers.auth import get_current_user, User

router = APIRouter(tags=["characters"])

_VALID_ROLES     = {"protagonist", "antagonist", "supporting", "minor"}
_VALID_STATUSES  = {"active", "deceased", "unknown"}
_VALID_REL_TYPES = {"ally", "rival", "family", "romantic", "mentor", "enemy", "neutral"}
_VALID_STRENGTHS = {"weak", "moderate", "strong", "critical"}

_NAME_PARTICLES = frozenset({
    'de', 'van', 'von', 'of', 'the', 'la', 'le', 'du', 'des',
    'el', 'al', 'bin', 'binti', 'di', 'da',
})


def _normalize_character_name(name: str) -> str:
    """
    Title-case an LLM-extracted character name robustly.
    - all-lowercase / all-caps → title case
    - Already-correct mixed-case (e.g. "MacGregor") → returned unchanged
    - Mid-name particles (de, van, von …) stay lowercase
    - Handles apostrophe names (O'Brien) and hyphenated names (Jean-Luc)
    """
    name = name.strip()
    if not name:
        return name

    # If already properly title-cased, return as-is to preserve author intent
    if name != name.lower() and name != name.upper():
        words = name.split()
        if all(
            (w[0].isupper() if w else True) or w.lower() in _NAME_PARTICLES
            for w in words
        ):
            return name

    def _cap(word: str, is_first: bool) -> str:
        if not word:
            return word
        if not is_first and word.lower() in _NAME_PARTICLES:
            return word.lower()
        if "'" in word:
            return "'".join(part.capitalize() for part in word.split("'"))
        if '-' in word:
            return '-'.join(part.capitalize() for part in word.split('-') if part)
        return word.capitalize()

    return ' '.join(_cap(w, i == 0) for i, w in enumerate(name.split()))


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

        # Always include name + role so sparse profiles still have a meaningful vector
        char = db.query(Character).filter(
            Character.character_id == profile.character_id
        ).first()
        name_anchor = f"{char.name} {char.role}" if char else ""

        parts = [
            name_anchor,
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


async def _run_mention_index(chapter_id: str, story_id: str, chapter_number: int) -> None:
    from database import SessionLocal
    from services.ai_service import index_character_mentions, update_mention_embedding
    db = SessionLocal()
    try:
        counts = await index_character_mentions(chapter_id, story_id, chapter_number, db)
        for char_id in counts:
            await update_mention_embedding(char_id, story_id, db)
    except Exception as exc:
        print(f"[mention_index bg] Failed for chapter {chapter_id[:8]}...: {exc}")
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


@router.post("/{story_id}/characters/generate-cast", response_model=CastGenerationResult)
async def generate_cast(
    story_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Scan all indexed chapter chunks and extract character suggestions using the LLM.
    Returns suggestions with already_exists flags; does NOT write to the DB.
    Author must call confirm-cast to save confirmed suggestions.
    """
    _check_story_access(story_id, current_user.user_id, db)

    from models import ChapterChunk
    chunks = (
        db.query(ChapterChunk)
        .filter(ChapterChunk.story_id == story_id)
        .order_by(ChapterChunk.chapter_number, ChapterChunk.chunk_index)
        .all()
    )

    if not chunks:
        raise HTTPException(
            status_code=422,
            detail="No indexed chapter content found. Save and open your chapters first so they can be indexed.",
        )

    # Group by chapter number and join chunk texts
    chapter_map: dict[int, list[str]] = {}
    for c in chunks:
        chapter_map.setdefault(c.chapter_number, []).append(c.text)
    per_chapter = [" ".join(texts) for _, texts in sorted(chapter_map.items())]

    from services.ai_service import extract_cast
    raw_suggestions = await extract_cast(per_chapter)

    # Build existing character index (name + aliases → character)
    existing = db.query(Character).filter(Character.story_id == story_id).all()
    existing_index: dict[str, Character] = {}
    for c in existing:
        existing_index[c.name.strip().lower()] = c
        for alias in (c.aliases or []):
            if alias.strip():
                existing_index.setdefault(alias.strip().lower(), c)

    suggestions = []
    for raw in raw_suggestions:
        name = str(raw.get("name", "")).strip()
        if not name:
            continue
        # Deduplicate within this result set
        if any(s.name.lower() == name.lower() for s in suggestions):
            continue

        aliases = raw.get("aliases", []) if isinstance(raw.get("aliases"), list) else []
        role = raw.get("role", "supporting")
        if role not in _VALID_ROLES:
            role = "supporting"
        status = raw.get("status", "active")
        if status not in _VALID_STATUSES:
            status = "active"
        confidence = raw.get("confidence", "high")
        if confidence not in ("high", "uncertain"):
            confidence = "high"

        # Check existing via name and aliases from suggestion
        existing_char = existing_index.get(name.lower())
        if not existing_char:
            for alias in aliases:
                existing_char = existing_index.get(alias.strip().lower())
                if existing_char:
                    break

        suggestions.append(CastSuggestion(
            name=name,
            role=role,
            status=status,
            description=str(raw.get("description", "")),
            aliases=aliases,
            first_appearance=str(raw.get("first_appearance", "")),
            evidence_snippet=str(raw.get("evidence_snippet", "")),
            confidence=confidence,
            already_exists=existing_char is not None,
            existing_character_id=existing_char.character_id if existing_char else None,
        ))

    new_count = sum(1 for s in suggestions if not s.already_exists)
    existing_count = sum(1 for s in suggestions if s.already_exists)

    return CastGenerationResult(
        story_id=story_id,
        suggestions=suggestions,
        chapters_scanned=len(chapter_map),
        new_count=new_count,
        existing_count=existing_count,
    )


@router.post("/{story_id}/characters/confirm-cast", response_model=CastConfirmResult, status_code=201)
async def confirm_cast(
    story_id: str,
    data: CastConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create characters from confirmed cast suggestions.
    Only creates characters that do not already exist (normalized name match).
    """
    _check_story_access(story_id, current_user.user_id, db)

    if not data.suggestions:
        return CastConfirmResult(created=[], skipped_existing=0)

    # Build existing name index for fast duplicate check
    existing = db.query(Character).filter(Character.story_id == story_id).all()
    taken_names: set[str] = set()
    for c in existing:
        taken_names.add(c.name.strip().lower())
        for alias in (c.aliases or []):
            if alias.strip():
                taken_names.add(alias.strip().lower())

    created_entries: list[tuple[str, str]] = []  # (character_id, profile_id)
    skipped_existing = 0

    for s in data.suggestions:
        raw_name = s.name.strip()
        if not raw_name:
            continue
        name = _normalize_character_name(raw_name)
        if name.lower() in taken_names:
            skipped_existing += 1
            continue

        # Normalize aliases the same way
        aliases = [_normalize_character_name(a) for a in (s.aliases or []) if a.strip()]

        character = Character(
            story_id=story_id,
            user_id=current_user.user_id,
            name=name,
            aliases=aliases,
            role=s.role if s.role in _VALID_ROLES else "supporting",
            status=s.status if s.status in _VALID_STATUSES else "active",
        )
        db.add(character)
        db.flush()

        profile_notes = s.description or ""
        if s.evidence_snippet:
            profile_notes = (profile_notes + "\n\nStory evidence: " + s.evidence_snippet).strip()

        profile = CharacterProfile(
            character_id=character.character_id,
            story_id=story_id,
            raw_notes=profile_notes,
            backstory=s.description or "",
        )
        db.add(profile)
        db.flush()
        created_entries.append((character.character_id, profile.profile_id))

        # Prevent duplicates within this batch
        taken_names.add(name.lower())
        for alias in aliases:
            taken_names.add(alias.lower())

    db.commit()

    # Re-query created characters and schedule profile embeddings
    created_chars = []
    for char_id, profile_id in created_entries:
        c = db.query(Character).filter(Character.character_id == char_id).first()
        if c:
            created_chars.append(c)
            asyncio.create_task(_embed_profile(profile_id))

    # Auto-trigger mention re-indexing for every indexed chapter so the new
    # characters are immediately discoverable via Story Mentions and RAG.
    if created_entries:
        from models import Chapter as ChapterModel, ChapterChunk as ChunkModel
        story_chapters = db.query(ChapterModel).filter(
            ChapterModel.story_id == story_id
        ).all()
        queued = 0
        for ch in story_chapters:
            has_chunks = db.query(ChunkModel).filter(
                ChunkModel.chapter_id == ch.chapter_id
            ).first() is not None
            if has_chunks:
                asyncio.create_task(_run_mention_index(
                    chapter_id=ch.chapter_id,
                    story_id=story_id,
                    chapter_number=ch.chapter_number,
                ))
                queued += 1
        if queued:
            print(
                f"[confirm_cast] {len(created_entries)} character(s) created — "
                f"triggered mention re-indexing for {queued} chapter(s)"
            )

    return CastConfirmResult(
        created=created_chars,
        skipped_existing=skipped_existing,
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


@router.get("/{story_id}/characters/hints", response_model=list[CharacterHintOut])
def list_character_hints(
    story_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_story_access(story_id, current_user.user_id, db)
    from models import CharacterHint
    return (
        db.query(CharacterHint)
        .filter(
            CharacterHint.story_id == story_id,
            CharacterHint.is_dismissed == False,  # noqa: E712
        )
        .order_by(CharacterHint.chapter_number, CharacterHint.created_at)
        .all()
    )


@router.post("/{story_id}/characters/hints/{hint_id}/dismiss")
def dismiss_hint(
    story_id: str,
    hint_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_story_access(story_id, current_user.user_id, db)
    from models import CharacterHint
    hint = db.query(CharacterHint).filter(
        CharacterHint.hint_id == hint_id,
        CharacterHint.story_id == story_id,
    ).first()
    if not hint:
        raise HTTPException(status_code=404, detail="Hint not found")
    hint.is_dismissed = True
    db.commit()
    return {"dismissed": hint_id}


@router.post("/{story_id}/characters/hints/{hint_id}/promote", response_model=CharacterOut)
async def promote_hint(
    story_id: str,
    hint_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Promote a character hint directly to the character table."""
    _check_story_access(story_id, current_user.user_id, db)
    from models import CharacterHint
    hint = db.query(CharacterHint).filter(
        CharacterHint.hint_id == hint_id,
        CharacterHint.story_id == story_id,
    ).first()
    if not hint:
        raise HTTPException(status_code=404, detail="Hint not found")

    # Check for collision
    existing = db.query(Character).filter(
        Character.story_id == story_id,
        Character.name.ilike(hint.suggested_name.strip()),
    ).first()
    if existing:
        hint.is_dismissed = True
        db.commit()
        raise HTTPException(status_code=409, detail=f"A character named '{hint.suggested_name}' already exists")

    character = Character(
        story_id=story_id,
        user_id=current_user.user_id,
        name=hint.suggested_name.strip(),
        aliases=[],
        role="supporting",
        status="active",
    )
    db.add(character)
    db.flush()
    profile = CharacterProfile(
        character_id=character.character_id,
        story_id=story_id,
    )
    db.add(profile)
    hint.is_dismissed = True
    db.commit()
    db.refresh(character)
    asyncio.create_task(_embed_profile(character.profile.profile_id))
    return character


@router.post("/{story_id}/characters/sync-mentions")
async def sync_character_mentions(
    story_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Backfill character mention indexing for all indexed chapters in a story.
    Run this after adding characters or after sync-summaries completes.
    """
    _check_story_access(story_id, current_user.user_id, db)

    from models import ChapterChunk, Chapter
    chapters_with_chunks = (
        db.query(Chapter)
        .filter(Chapter.story_id == story_id)
        .all()
    )

    queued = 0
    for ch in chapters_with_chunks:
        has_chunks = db.query(ChapterChunk).filter(
            ChapterChunk.chapter_id == ch.chapter_id
        ).count() > 0
        if not has_chunks:
            continue
        asyncio.create_task(_run_mention_index(
            chapter_id=ch.chapter_id,
            story_id=story_id,
            chapter_number=ch.chapter_number,
        ))
        queued += 1

    return {
        "story_id": story_id,
        "chapters_queued": queued,
        "message": (
            f"Indexing character mentions for {queued} chapter(s) in the background. "
            "Check back in ~5-10 seconds."
        ) if queued else "No indexed chapters found. Run sync-summaries first.",
    }


@router.get("/{story_id}/characters/{character_id}/mentions",
            response_model=list[CharacterMentionOut])
def list_character_mentions(
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
    from models import CharacterMention
    return (
        db.query(CharacterMention)
        .filter(
            CharacterMention.character_id == character_id,
            CharacterMention.story_id     == story_id,
        )
        .order_by(CharacterMention.chapter_number, CharacterMention.mention_id)
        .all()
    )


@router.post("/{story_id}/characters/{character_id}/enrich",
             response_model=EnrichResult)
async def enrich_character(
    story_id:     str,
    character_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Extract profile suggestions for this character from their story mentions.
    Returns suggestions for author review — nothing is auto-applied.
    """
    _check_story_access(story_id, current_user.user_id, db)
    character = db.query(Character).filter(
        Character.character_id == character_id,
        Character.story_id     == story_id,
    ).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    from models import CharacterMention
    mentions = db.query(CharacterMention).filter(
        CharacterMention.character_id == character_id,
        CharacterMention.story_id     == story_id,
    ).all()

    if not mentions:
        raise HTTPException(
            status_code=422,
            detail="No story mentions found for this character. "
                   "Sync mentions first (POST /characters/sync-mentions).",
        )

    from services.ai_service import enrich_character_from_story
    suggestions_raw = await enrich_character_from_story(character_id, story_id, db)

    chapters_covered = sorted({m.chapter_number for m in mentions})

    suggestions = []
    valid_fields = {"appearance", "personality", "goals", "motivations", "backstory", "arc_notes", "traits"}
    for s in suggestions_raw:
        field = str(s.get("field", "")).strip()
        value = str(s.get("value", "")).strip()
        evidence = str(s.get("evidence", "")).strip()
        chapter_raw = s.get("chapter", 0)
        try:
            chapter = int(chapter_raw)
        except (TypeError, ValueError):
            chapter = 0
        try:
            confidence = float(s.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        if field in valid_fields and value:
            suggestions.append(EnrichSuggestion(
                field=field,
                value=value,
                evidence=evidence,
                chapter=chapter,
                confidence=round(min(1.0, max(0.0, confidence)), 2),
            ))

    return EnrichResult(
        character_id=character_id,
        suggestions=suggestions,
        mentions_analyzed=len(mentions),
        chapters_covered=chapters_covered,
    )


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
