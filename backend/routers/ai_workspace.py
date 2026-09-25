"""
Phase 3 — AI workspace router (spec §17.1), registered at prefix /api/stories.

Pins (P3-01, P3-06 lineage, P3-09 promotion, P3-11 similarity) and per-story
AI preferences (P3-05 / P3-10). Every route:

  * requires a JWT (get_current_user);
  * resolves the story, chapter, pin and card ids through services.ownership,
    so a foreign id and a non-existent id are indistinguishable (same 404,
    same body; batch ids produce the same generic warning);
  * returns 404 — never 403 — for anything not owned;
  * logs ids, sizes and durations only — NEVER generation or manuscript text.

Pin content is read/written only through services.pin_store (§46 item 10).
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import text as sql
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from exceptions import ApiError
from middleware.rate_limit import limiter, get_user_id
from models import AiGenerationPin, NoteCard, StoryDNA, StoryPreservationSettings
from routers.auth import get_current_user, User
from schemas import (
    AiPreferencesOut, AiPreferencesUpdate, IDEA_CARD_TYPES, NoteCardOut, PinCreate, PinCreateOut,
    PinDetailOut, PinLimits, PinListOut, PinOut, PinPromoteOut, PinPromoteRequest, PinUpdate,
    SimilarityOut, SimilarityRequest,
)
from services import plans
from services.ownership import (
    owned_chapter_or_none, owned_pin, owned_story, resolve_owned_cards, resolve_owned_pins,
    unavailable_pins_warning,
)
from services.pin_store import get_pin_store, sha256_text

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ai-workspace"])

PREVIEW_CHARS = 180


# ── helpers ───────────────────────────────────────────────────────────────────

def _live_user_pins(db: Session, user_id: str):
    return db.query(AiGenerationPin).filter(
        AiGenerationPin.user_id == user_id, AiGenerationPin.expires_at > datetime.utcnow())


def _limits(db: Session, user) -> PinLimits:
    return PinLimits(used=_live_user_pins(db, user.user_id).count(),
                     max=plans.get_limits(user).max_pins, plan=plans.plan_name(user))


def _pin_out(pin: AiGenerationPin, *, detail: bool = False):
    content = get_pin_store().get(pin)
    preview = content[:PREVIEW_CHARS] + ("…" if len(content) > PREVIEW_CHARS else "")
    data = dict(
        pin_id=pin.pin_id, story_id=pin.story_id, chapter_id=pin.chapter_id, tool=pin.tool,
        scope=pin.scope or "selection", tool_params=pin.tool_params or {}, preview=preview,
        source_excerpt=pin.source_excerpt or "", source_sha256=pin.source_sha256 or "",
        source_from=pin.source_from, source_to=pin.source_to, content_sha256=pin.content_sha256,
        word_count=pin.word_count or 0, label=pin.label or "", is_favourite=bool(pin.is_favourite),
        parent_pin_id=pin.parent_pin_id, root_pin_id=pin.root_pin_id, lineage_depth=pin.lineage_depth or 0,
        derived_from_pin_ids=pin.derived_from_pin_ids or [], derivation=pin.derivation or "",
        has_embedding=pin.embedding is not None, applied_at=pin.applied_at,
        promoted_card_id=pin.promoted_card_id, expires_at=pin.expires_at, created_at=pin.created_at,
    )
    if detail:
        return PinDetailOut(content=content, **data)
    return PinOut(**data)


async def _embed_pin(pin_id: str) -> None:
    """Background BGE-M3 embedding for similarity stage 2 (P3-11). Failure
    leaves embedding NULL — similarity then simply stays lexical."""
    from database import SessionLocal
    from middleware.concurrency import embedding_semaphore
    from services.ai_service import embed_text
    db = SessionLocal()
    try:
        pin = db.query(AiGenerationPin).filter(AiGenerationPin.pin_id == pin_id).first()
        if pin is None:
            return
        content = get_pin_store().get(pin)
        async with embedding_semaphore():
            emb = await embed_text(content[:8000])
        pin.embedding = emb
        db.commit()
        logger.debug("[pins] embedded pin %s", pin_id[:8])
    except Exception as exc:
        logger.warning("[pins] embedding failed for pin %s (%s)", pin_id[:8], type(exc).__name__)
    finally:
        db.close()


# ── Pins ──────────────────────────────────────────────────────────────────────

@router.post("/{story_id}/ai/pins", response_model=PinCreateOut, status_code=201)
@limiter.limit(settings.rate_limit_pin_write, key_func=get_user_id)
async def create_pin(request: Request, story_id: str, data: PinCreate, response: Response,
                     current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    story = owned_story(story_id, current_user.user_id, db)
    chapter = owned_chapter_or_none(data.chapter_id, story.story_id, current_user.user_id, db)
    content = data.content
    if not content.strip():
        raise ApiError(400, "An empty result cannot be pinned.", code="empty_content")
    plans.enforce_pin_size(current_user, content)
    limits = plans.get_limits(current_user)
    content_sha = sha256_text(content)

    parent = owned_pin(data.parent_pin_id, story.story_id, current_user.user_id, db) if data.parent_pin_id else None
    derived, _missing = resolve_owned_pins(data.derived_from_pin_ids, story.story_id, current_user.user_id, db)

    # Count-and-insert under a per-user transaction-scoped advisory lock, so two
    # devices pinning at the cap cannot both pass the count (spec E16).
    db.execute(sql("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"pins:{current_user.user_id}"})

    existing = _live_user_pins(db, current_user.user_id).filter(
        AiGenerationPin.story_id == story.story_id, AiGenerationPin.content_sha256 == content_sha).first()
    if existing is not None:
        db.commit()   # releases the advisory lock
        response.status_code = 200
        return PinCreateOut(pin=_pin_out(existing), already_pinned=True, limits=_limits(db, current_user))

    live = _live_user_pins(db, current_user.user_id)
    used = live.count()
    if used >= limits.max_pins:
        oldest = live.order_by(AiGenerationPin.created_at.asc()).first()
        if not data.replace_oldest or oldest is None:
            db.rollback()
            raise ApiError(409, f"Pin limit reached for the {plans.plan_name(current_user)} plan "
                                f"({used} of {limits.max_pins}).",
                           code="pin_limit_reached",
                           limits={"used": used, "max": limits.max_pins, "plan": plans.plan_name(current_user)},
                           oldest_pin={"pin_id": oldest.pin_id, "label": oldest.label or "",
                                       "story_id": oldest.story_id,
                                       "created_at": oldest.created_at.isoformat() if oldest.created_at else None,
                                       "expires_at": oldest.expires_at.isoformat()} if oldest else None)
        # Explicit author choice from the cap dialog — never automatic eviction.
        get_pin_store().delete_many([oldest])
        db.delete(oldest)
        db.flush()

    now = datetime.utcnow()
    expires_at = now + timedelta(days=limits.pin_ttl_days)
    if expires_at <= now:   # E17 — a plan misconfiguration, never a silently-expired pin
        db.rollback()
        raise ApiError(500, "Pins are misconfigured on this server. Please contact support.", code="pin_ttl_invalid")

    pin = AiGenerationPin(
        user_id=current_user.user_id, story_id=story.story_id,
        chapter_id=chapter.chapter_id if chapter else None,
        tool=data.tool, scope=data.scope, tool_params=data.tool_params,
        source_from=data.source_from, source_to=data.source_to,
        source_excerpt=(data.source_excerpt or "")[: settings.pin_source_excerpt_chars],
        source_sha256=data.source_text_sha256 or "",
        label=data.label or "", derivation=data.derivation or "",
        derived_from_pin_ids=[p.pin_id for p in derived] + ([parent.pin_id] if parent and parent.pin_id not in [p.pin_id for p in derived] else []),
        expires_at=expires_at, created_at=now,
    )
    get_pin_store().put(pin, content)
    db.add(pin)
    db.flush()   # assigns pin_id

    if parent is not None and (parent.lineage_depth or 0) + 1 <= settings.max_lineage_depth:
        pin.parent_pin_id = parent.pin_id
        pin.root_pin_id = parent.root_pin_id or parent.pin_id
        pin.lineage_depth = (parent.lineage_depth or 0) + 1
    else:
        # A root, or beyond the depth cap: becomes its own root; provenance
        # is still recorded in derived_from_pin_ids.
        pin.root_pin_id = pin.pin_id
        pin.lineage_depth = 0
    db.commit()
    db.refresh(pin)
    logger.info("[pins] created pin %s story=%s tool=%s bytes=%d depth=%d",
                pin.pin_id[:8], story.story_id[:8], pin.tool, pin.content_bytes or 0, pin.lineage_depth or 0)
    if settings.pin_store_embedding:
        asyncio.create_task(_embed_pin(pin.pin_id))
    return PinCreateOut(pin=_pin_out(pin), already_pinned=False, limits=_limits(db, current_user))


@router.get("/{story_id}/ai/pins", response_model=PinListOut)
def list_pins(story_id: str, chapter_id: Optional[str] = None, tool: Optional[str] = None,
              scope: Optional[str] = None, root_pin_id: Optional[str] = None, q: Optional[str] = None,
              limit: int = 50, offset: int = 0,
              current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    story = owned_story(story_id, current_user.user_id, db)
    query = _live_user_pins(db, current_user.user_id).filter(AiGenerationPin.story_id == story.story_id)
    if chapter_id:
        query = query.filter(AiGenerationPin.chapter_id == chapter_id)
    if tool:
        query = query.filter(AiGenerationPin.tool == tool)
    if scope:
        query = query.filter(AiGenerationPin.scope == scope)
    if root_pin_id:
        query = query.filter(AiGenerationPin.root_pin_id == root_pin_id)
    if q and q.strip():
        # Label and excerpt only — pin CONTENT is never queried in SQL outside
        # PinContentStore (§46 item 10).
        like = f"%{q.strip()[:100]}%"
        query = query.filter((AiGenerationPin.label.ilike(like)) | (AiGenerationPin.source_excerpt.ilike(like)))
    total = query.count()
    rows = (query.order_by(AiGenerationPin.is_favourite.desc(), AiGenerationPin.created_at.desc())
            .offset(max(0, offset)).limit(max(1, min(limit, 200))).all())
    return PinListOut(pins=[_pin_out(p) for p in rows], total=total, limits=_limits(db, current_user))


@router.get("/{story_id}/ai/pins/{pin_id}", response_model=PinDetailOut)
def get_pin(story_id: str, pin_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    story = owned_story(story_id, current_user.user_id, db)
    pin = owned_pin(pin_id, story.story_id, current_user.user_id, db)
    out = _pin_out(pin, detail=True)
    # IDOR guard on lineage (spec §30): only expose ancestors the caller still owns.
    if out.parent_pin_id:
        still_owned, _ = resolve_owned_pins([out.parent_pin_id], story.story_id, current_user.user_id, db)
        if not still_owned:
            out.parent_pin_id = None
    return out


@router.patch("/{story_id}/ai/pins/{pin_id}", response_model=PinOut)
@limiter.limit(settings.rate_limit_pin_write, key_func=get_user_id)
def update_pin(request: Request, story_id: str, pin_id: str, data: PinUpdate,
               current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    story = owned_story(story_id, current_user.user_id, db)
    pin = owned_pin(pin_id, story.story_id, current_user.user_id, db)
    if data.label is not None:
        pin.label = data.label.strip()
    if data.is_favourite is not None:
        pin.is_favourite = data.is_favourite   # a sort key, never a lifetime (spec §19.2)
    if data.extend_ttl:
        limits = plans.get_limits(current_user)
        if not limits.can_extend_ttl:
            raise ApiError(422, f"Extending pins is not included in the {plans.plan_name(current_user)} plan. "
                                "Send it to the Idea Shelf to keep it permanently.", code="extend_not_in_plan")
        ceiling = (pin.created_at or datetime.utcnow()) + timedelta(days=settings.max_total_pin_age_days)
        new_expiry = min(datetime.utcnow() + timedelta(days=limits.pin_ttl_days), ceiling)
        if new_expiry <= pin.expires_at:
            raise ApiError(422, "This version has been kept for the maximum time. Send it to the Idea Shelf "
                                "to keep it permanently.", code="extension_limit_reached")
        pin.expires_at = new_expiry
    db.commit()
    db.refresh(pin)
    return _pin_out(pin)


@router.delete("/{story_id}/ai/pins/{pin_id}", status_code=204)
@limiter.limit(settings.rate_limit_pin_write, key_func=get_user_id)
def delete_pin(request: Request, story_id: str, pin_id: str,
               current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    story = owned_story(story_id, current_user.user_id, db)
    pin = owned_pin(pin_id, story.story_id, current_user.user_id, db)
    get_pin_store().delete_many([pin])
    db.delete(pin)
    db.commit()
    return Response(status_code=204)


@router.post("/{story_id}/ai/pins/{pin_id}/applied", response_model=PinOut)
def mark_pin_applied(story_id: str, pin_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Records that the author applied this version to the manuscript. Does
    NOT extend the pin: applied text lives in the manuscript (R3)."""
    story = owned_story(story_id, current_user.user_id, db)
    pin = owned_pin(pin_id, story.story_id, current_user.user_id, db)
    pin.applied_at = datetime.utcnow()
    db.commit()
    db.refresh(pin)
    return _pin_out(pin)


@router.post("/{story_id}/ai/pins/{pin_id}/promote", response_model=PinPromoteOut, status_code=201)
@limiter.limit(settings.rate_limit_pin_write, key_func=get_user_id)
async def promote_pin(request: Request, story_id: str, pin_id: str, data: PinPromoteRequest,
                      current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Pin → permanent Idea Shelf card (P3-09). The one sanctioned content
    copy in Phase 3: a deliberate temporary→permanent promotion."""
    story = owned_story(story_id, current_user.user_id, db)
    pin = owned_pin(pin_id, story.story_id, current_user.user_id, db)
    target = owned_chapter_or_none(data.target_chapter_id, story.story_id, current_user.user_id, db)
    if data.card_type == "style_sample":
        count = db.query(NoteCard).filter(NoteCard.story_id == story.story_id, NoteCard.user_id == current_user.user_id,
                                          NoteCard.card_type == "style_sample").count()
        plans.enforce_style_sample_create(current_user, count)
    else:
        count = db.query(NoteCard).filter(NoteCard.user_id == current_user.user_id,
                                          NoteCard.card_type.in_(IDEA_CARD_TYPES - {"style_sample"})).count()
        plans.enforce_idea_card_create(current_user, count)
    content = get_pin_store().get(pin)
    title = data.title.strip() or pin.label or " ".join(content.split()[:8])
    card = NoteCard(story_id=story.story_id, user_id=current_user.user_id, title=title[:200], content=content,
                    card_type=data.card_type, tags=data.tags or [], status="open",
                    target_chapter_id=target.chapter_id if target else None, source_pin_id=pin.pin_id)
    db.add(card)
    db.flush()
    released = False
    if data.release_pin:
        get_pin_store().delete_many([pin])
        db.delete(pin)
        released = True
    else:
        pin.promoted_card_id = card.card_id
    db.commit()
    db.refresh(card)
    from routers.ocr import _embed_note_card   # existing embedding pipeline → note RAG, unchanged
    asyncio.create_task(_embed_note_card(card.card_id))
    logger.info("[pins] promoted pin %s → card %s (released=%s)", pin_id[:8], card.card_id[:8], released)
    return PinPromoteOut(card=NoteCardOut.model_validate(card), pin_released=released)


# ── Similarity (P3-11) ────────────────────────────────────────────────────────

@router.post("/{story_id}/ai/similarity", response_model=SimilarityOut)
@limiter.limit(settings.rate_limit_realtime_ai, key_func=get_user_id)
async def similarity(request: Request, story_id: str, data: SimilarityRequest,
                     current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Idempotent; stores and logs nothing about the candidate text."""
    from services.similarity import compare_against
    story = owned_story(story_id, current_user.user_id, db)
    warnings = []
    if data.against_pin_ids:
        pins, missing = resolve_owned_pins(data.against_pin_ids, story.story_id, current_user.user_id, db)
        w = unavailable_pins_warning(missing)
        if w:
            warnings.append({"kind": "pins_unavailable", "severity": "info", "message": w})
    elif not data.against_texts:
        q = _live_user_pins(db, current_user.user_id).filter(AiGenerationPin.story_id == story.story_id)
        if data.tool:
            q = q.filter(AiGenerationPin.tool == data.tool)
        pins = q.order_by(AiGenerationPin.created_at.desc()).limit(settings.similarity_candidate_limit).all()
    else:
        pins = []
    matches, embedded = await compare_against(
        data.text, pins=pins, texts=data.against_texts, story_id=story.story_id,
        user_id=current_user.user_id, db=db, allow_semantic=data.mode == "auto")
    return SimilarityOut(matches=[m.as_dict() for m in matches], checked=len(matches),
                         embedded=embedded, warnings=warnings)


# ── Preferences (P3-05 project defaults, P3-10 style, pin prefs) ─────────────

def _prefs_out(story_id: str, row, user, db: Session) -> AiPreferencesOut:
    from services.generation_context import resolve_pin_prefs, resolve_style_prefs
    from services.transform_preservation import resolve_preserve_rules
    return AiPreferencesOut(
        story_id=story_id,
        preserve_character_names=bool(getattr(row, "preserve_character_names", True)),
        preserve_tone=bool(getattr(row, "preserve_tone", True)),
        author_notes=getattr(row, "author_notes", "") or "",
        preserve_rules=resolve_preserve_rules(story_id, db),
        style_prefs=resolve_style_prefs(row),
        pin_prefs=resolve_pin_prefs(row),
        story_dna_available=db.query(StoryDNA.dna_id).filter(StoryDNA.story_id == story_id).first() is not None,
        strict_consistency_allowed=plans.get_limits(user).strict_consistency,
    )


@router.get("/{story_id}/ai/preferences", response_model=AiPreferencesOut)
def get_preferences(story_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from services.transform_preservation import get_or_default_preservation_settings
    story = owned_story(story_id, current_user.user_id, db)
    return _prefs_out(story.story_id, get_or_default_preservation_settings(story.story_id, db), current_user, db)


@router.patch("/{story_id}/ai/preferences", response_model=AiPreferencesOut)
def update_preferences(story_id: str, data: AiPreferencesUpdate,
                       current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    story = owned_story(story_id, current_user.user_id, db)
    row = db.query(StoryPreservationSettings).filter(StoryPreservationSettings.story_id == story.story_id).first()
    if row is None:   # created lazily on first write (absent row = all defaults)
        row = StoryPreservationSettings(story_id=story.story_id)
        db.add(row)
    if data.preserve_character_names is not None:
        row.preserve_character_names = data.preserve_character_names
    if data.preserve_tone is not None:
        row.preserve_tone = data.preserve_tone
    if data.author_notes is not None:
        row.author_notes = data.author_notes.strip()
    if data.preserve_rules is not None:
        merged = dict(row.preserve_rules or {})
        for k, v in data.preserve_rules.model_dump().items():
            if k in ("character_names", "tone") or v is None:
                continue   # names/tone live in their own boolean columns
            merged[k] = v
        row.preserve_rules = merged
    if data.style_prefs is not None:
        merged = dict(row.style_prefs or {})
        for k, v in data.style_prefs.model_dump(exclude_none=True).items():
            if k == "exemplar_card_ids":
                cards, _ = resolve_owned_cards(v, story.story_id, current_user.user_id, db)
                v = [c.card_id for c in cards if c.card_type == "style_sample"]
            merged[k] = v
        row.style_prefs = merged
    if data.pin_prefs is not None:
        merged = dict(row.pin_prefs or {})
        merged.update(data.pin_prefs.model_dump(exclude_none=True))
        row.pin_prefs = merged
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return _prefs_out(story.story_id, row, current_user, db)
