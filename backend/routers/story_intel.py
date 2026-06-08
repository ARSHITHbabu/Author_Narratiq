"""
Story Intelligence Router — /api/intelligence/{story_id}/...

All routes require JWT auth. Ownership is enforced via _get_owned_story().
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import (
    Character, CharacterIntelligence, CharacterRelationship,
    RelationshipIntelligence, Story, StoryAudienceProfile, StoryConflicts,
    StoryContinuityRisks, StoryDNA, StoryEmotionalArc, StoryForeshadowingRegistry,
    StoryGenreHierarchy, StoryGraphEdge, StoryGraphNode, StoryIntelJob,
    StoryMemoryEntry, StoryNarrativeStructure, StoryPacingMap, StoryRiskRegister,
    StoryStrengthIndicators, StoryThemes, StoryTimeline, StoryTimelineEvent,
    StoryWorldProfile, gen_uuid,
)
from routers.auth import get_current_user
from schemas import (
    AuthorMemoryAddRequest,
    AuthorOverrideRequest,
    CharacterIntelligenceOut,
    CharacterIntelligenceOverrideRequest,
    IntelJobOut,
    IntelJobTriggerRequest,
    RelationshipIntelligenceOut,
    StoryAudienceProfileOut,
    StoryConflictsOut,
    StoryContinuityRisksOut,
    StoryDNAOut,
    StoryEmotionalArcOut,
    StoryForeshadowingRegistryOut,
    StoryGenreHierarchyOut,
    StoryGraphResponse,
    StoryIntelligenceDashboard,
    StoryMemoryEntryOut,
    StoryMemorySearchRequest,
    StoryMemorySearchResult,
    StoryNarrativeStructureOut,
    StoryPacingMapOut,
    StoryRiskRegisterOut,
    StoryStrengthIndicatorsOut,
    StoryThemesOut,
    StoryTimelineOut,
    StoryWorldProfileOut,
)

router = APIRouter(tags=["story-intelligence"])


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_owned_story(story_id: str, user: dict, db: Session) -> Story:
    story = db.query(Story).filter_by(story_id=story_id, user_id=user["user_id"]).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return story


# ── Job Control ────────────────────────────────────────────────────────────────

@router.post("/{story_id}/intelligence/analyze", response_model=IntelJobOut)
async def trigger_analysis(
    story_id: str,
    req: IntelJobTriggerRequest,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Launch a full story intelligence analysis run in the background."""
    story = _get_owned_story(story_id, user, db)

    from services.story_intel_orchestrator import run_analysis_background
    job_id = await run_analysis_background(
        story_id=story_id,
        user_id=user["user_id"],
        triggered_by="manual",
        passes=req.passes,
        force_refresh=req.force_refresh or False,
    )

    job = db.query(StoryIntelJob).filter_by(job_id=job_id).first()
    if not job:
        raise HTTPException(status_code=500, detail="Job creation failed")
    return job


@router.get("/{story_id}/intelligence/jobs", response_model=List[IntelJobOut])
def list_jobs(
    story_id: str,
    limit: int = 10,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_owned_story(story_id, user, db)
    return (
        db.query(StoryIntelJob)
        .filter_by(story_id=story_id)
        .order_by(StoryIntelJob.created_at.desc())
        .limit(limit)
        .all()
    )


@router.get("/{story_id}/intelligence/jobs/{job_id}", response_model=IntelJobOut)
def get_job(
    story_id: str,
    job_id: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_owned_story(story_id, user, db)
    job = db.query(StoryIntelJob).filter_by(job_id=job_id, story_id=story_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


# ── Dashboard ──────────────────────────────────────────────────────────────────

@router.get("/{story_id}/intelligence", response_model=StoryIntelligenceDashboard)
def get_dashboard(
    story_id: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the full intelligence dashboard for a story."""
    story = _get_owned_story(story_id, user, db)

    latest_job = (
        db.query(StoryIntelJob)
        .filter_by(story_id=story_id)
        .order_by(StoryIntelJob.created_at.desc())
        .first()
    )

    return StoryIntelligenceDashboard(
        story_id=story_id,
        latest_job=latest_job,
        genre_hierarchy=db.query(StoryGenreHierarchy).filter_by(story_id=story_id).first(),
        story_dna=db.query(StoryDNA).filter_by(story_id=story_id).first(),
        audience_profile=db.query(StoryAudienceProfile).filter_by(story_id=story_id).first(),
        themes=db.query(StoryThemes).filter_by(story_id=story_id).first(),
        conflicts=db.query(StoryConflicts).filter_by(story_id=story_id).first(),
        world_profile=db.query(StoryWorldProfile).filter_by(story_id=story_id).first(),
        narrative_structure=db.query(StoryNarrativeStructure).filter_by(story_id=story_id).first(),
        emotional_arc=db.query(StoryEmotionalArc).filter_by(story_id=story_id).first(),
        pacing_map=db.query(StoryPacingMap).filter_by(story_id=story_id).first(),
        strength_indicators=db.query(StoryStrengthIndicators).filter_by(story_id=story_id).first(),
        risk_register=db.query(StoryRiskRegister).filter_by(story_id=story_id).first(),
        foreshadowing_registry=db.query(StoryForeshadowingRegistry).filter_by(story_id=story_id).first(),
        continuity_risks=db.query(StoryContinuityRisks).filter_by(story_id=story_id).first(),
        timeline=db.query(StoryTimeline).filter_by(story_id=story_id).first(),
        character_intel_count=db.query(CharacterIntelligence).filter_by(story_id=story_id).count(),
        relationship_intel_count=db.query(RelationshipIntelligence).filter_by(story_id=story_id).count(),
        memory_entry_count=db.query(StoryMemoryEntry).filter_by(story_id=story_id).count(),
        graph_node_count=db.query(StoryGraphNode).filter_by(story_id=story_id).count(),
        graph_edge_count=db.query(StoryGraphEdge).filter_by(story_id=story_id).count(),
    )


# ── V1 Intelligence Getters + Override Setters ────────────────────────────────

@router.get("/{story_id}/intelligence/genre", response_model=StoryGenreHierarchyOut)
def get_genre(story_id: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    _get_owned_story(story_id, user, db)
    obj = db.query(StoryGenreHierarchy).filter_by(story_id=story_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Not yet analyzed")
    return obj


@router.patch("/{story_id}/intelligence/genre/override")
def override_genre(
    story_id: str, req: AuthorOverrideRequest,
    user=Depends(get_current_user), db: Session = Depends(get_db),
):
    _get_owned_story(story_id, user, db)
    obj = db.query(StoryGenreHierarchy).filter_by(story_id=story_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Not yet analyzed")
    obj.author_overrides = req.author_overrides
    db.commit()
    return {"ok": True}


@router.get("/{story_id}/intelligence/dna", response_model=StoryDNAOut)
def get_dna(story_id: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    _get_owned_story(story_id, user, db)
    obj = db.query(StoryDNA).filter_by(story_id=story_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Not yet analyzed")
    return obj


@router.get("/{story_id}/intelligence/audience", response_model=StoryAudienceProfileOut)
def get_audience(story_id: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    _get_owned_story(story_id, user, db)
    obj = db.query(StoryAudienceProfile).filter_by(story_id=story_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Not yet analyzed")
    return obj


@router.get("/{story_id}/intelligence/themes", response_model=StoryThemesOut)
def get_themes(story_id: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    _get_owned_story(story_id, user, db)
    obj = db.query(StoryThemes).filter_by(story_id=story_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Not yet analyzed")
    return obj


@router.get("/{story_id}/intelligence/conflicts", response_model=StoryConflictsOut)
def get_conflicts(story_id: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    _get_owned_story(story_id, user, db)
    obj = db.query(StoryConflicts).filter_by(story_id=story_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Not yet analyzed")
    return obj


@router.get("/{story_id}/intelligence/world", response_model=StoryWorldProfileOut)
def get_world(story_id: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    _get_owned_story(story_id, user, db)
    obj = db.query(StoryWorldProfile).filter_by(story_id=story_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Not yet analyzed")
    return obj


@router.get("/{story_id}/intelligence/structure", response_model=StoryNarrativeStructureOut)
def get_structure(story_id: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    _get_owned_story(story_id, user, db)
    obj = db.query(StoryNarrativeStructure).filter_by(story_id=story_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Not yet analyzed")
    return obj


@router.get("/{story_id}/intelligence/emotional-arc", response_model=StoryEmotionalArcOut)
def get_emotional_arc(story_id: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    _get_owned_story(story_id, user, db)
    obj = db.query(StoryEmotionalArc).filter_by(story_id=story_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Not yet analyzed")
    return obj


@router.get("/{story_id}/intelligence/pacing", response_model=StoryPacingMapOut)
def get_pacing(story_id: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    _get_owned_story(story_id, user, db)
    obj = db.query(StoryPacingMap).filter_by(story_id=story_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Not yet analyzed")
    return obj


@router.get("/{story_id}/intelligence/strengths", response_model=StoryStrengthIndicatorsOut)
def get_strengths(story_id: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    _get_owned_story(story_id, user, db)
    obj = db.query(StoryStrengthIndicators).filter_by(story_id=story_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Not yet analyzed")
    return obj


@router.get("/{story_id}/intelligence/risks", response_model=StoryRiskRegisterOut)
def get_risks(story_id: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    _get_owned_story(story_id, user, db)
    obj = db.query(StoryRiskRegister).filter_by(story_id=story_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Not yet analyzed")
    return obj


@router.get("/{story_id}/intelligence/foreshadowing", response_model=StoryForeshadowingRegistryOut)
def get_foreshadowing(story_id: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    _get_owned_story(story_id, user, db)
    obj = db.query(StoryForeshadowingRegistry).filter_by(story_id=story_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Not yet analyzed")
    return obj


@router.get("/{story_id}/intelligence/continuity", response_model=StoryContinuityRisksOut)
def get_continuity(story_id: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    _get_owned_story(story_id, user, db)
    obj = db.query(StoryContinuityRisks).filter_by(story_id=story_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Not yet analyzed")
    return obj


# ── V2: Character Intelligence ────────────────────────────────────────────────

@router.get("/{story_id}/intelligence/characters", response_model=List[CharacterIntelligenceOut])
def list_character_intelligence(
    story_id: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_owned_story(story_id, user, db)
    return db.query(CharacterIntelligence).filter_by(story_id=story_id).all()


@router.get("/{story_id}/intelligence/characters/{character_id}", response_model=CharacterIntelligenceOut)
def get_character_intelligence(
    story_id: str,
    character_id: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_owned_story(story_id, user, db)
    obj = db.query(CharacterIntelligence).filter_by(
        character_id=character_id, story_id=story_id
    ).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Character intelligence not yet analyzed")
    return obj


@router.patch("/{story_id}/intelligence/characters/{character_id}/override")
def override_character_intelligence(
    story_id: str,
    character_id: str,
    req: CharacterIntelligenceOverrideRequest,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_owned_story(story_id, user, db)
    obj = db.query(CharacterIntelligence).filter_by(
        character_id=character_id, story_id=story_id
    ).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    obj.author_overrides = req.author_overrides
    db.commit()
    return {"ok": True}


# ── V2: Relationship Intelligence ─────────────────────────────────────────────

@router.get("/{story_id}/intelligence/relationships", response_model=List[RelationshipIntelligenceOut])
def list_relationship_intelligence(
    story_id: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_owned_story(story_id, user, db)
    return db.query(RelationshipIntelligence).filter_by(story_id=story_id).all()


@router.get("/{story_id}/intelligence/relationships/{relationship_id}", response_model=RelationshipIntelligenceOut)
def get_relationship_intelligence(
    story_id: str,
    relationship_id: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_owned_story(story_id, user, db)
    obj = db.query(RelationshipIntelligence).filter_by(
        relationship_id=relationship_id, story_id=story_id
    ).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Not yet analyzed")
    return obj


# ── V2: Story Memory ──────────────────────────────────────────────────────────

@router.get("/{story_id}/intelligence/memory", response_model=List[StoryMemoryEntryOut])
def list_memory(
    story_id: str,
    memory_type: Optional[str] = None,
    limit: int = 50,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_owned_story(story_id, user, db)
    q = db.query(StoryMemoryEntry).filter_by(story_id=story_id, is_active=True)
    if memory_type:
        q = q.filter_by(memory_type=memory_type)
    return q.order_by(StoryMemoryEntry.importance.desc()).limit(limit).all()


@router.post("/{story_id}/intelligence/memory/search", response_model=List[StoryMemorySearchResult])
async def search_memory(
    story_id: str,
    req: StoryMemorySearchRequest,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_owned_story(story_id, user, db)

    from services.ai_service import embed_text, vector_distance, vector_similarity
    from sqlalchemy import text as sql_text

    try:
        query_emb = await embed_text(req.query[:512])   # returns list[float]
        sql = (
            "SELECT entry_id, memory_type, memory_key, content, importance, "
            "entity_type, entity_id, is_active, is_ai_generated, is_author_added, "
            "chapter_first_established, chapter_last_updated, created_at, updated_at, "
            f"{vector_similarity('embedding', 'qemb')} AS score "
            "FROM story_memory_entries "
            "WHERE story_id = :sid AND is_active = true AND embedding IS NOT NULL "
        )
        params = {"qemb": str(query_emb), "sid": story_id, "k": req.top_k or 10}
        if req.memory_type:
            sql += "AND memory_type = :mtype "
            params["mtype"] = req.memory_type
        if req.entity_type:
            sql += "AND entity_type = :etype "
            params["etype"] = req.entity_type
        sql += f"ORDER BY {vector_distance('embedding', 'qemb')} LIMIT :k"

        rows = db.execute(sql_text(sql), params).fetchall()
        results = []
        for r in rows:
            entry = StoryMemoryEntryOut(
                entry_id=r.entry_id,
                story_id=story_id,
                memory_type=r.memory_type,
                memory_key=r.memory_key,
                content=r.content,
                entity_type=r.entity_type,
                entity_id=r.entity_id,
                importance=r.importance,
                is_active=r.is_active,
                is_ai_generated=r.is_ai_generated,
                is_author_added=r.is_author_added,
                chapter_first_established=r.chapter_first_established,
                chapter_last_updated=r.chapter_last_updated,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
            results.append(StoryMemorySearchResult(entry=entry, score=float(r.score)))
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Memory search failed: {str(e)}")


@router.post("/{story_id}/intelligence/memory/add", response_model=StoryMemoryEntryOut)
def add_author_memory(
    story_id: str,
    req: AuthorMemoryAddRequest,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Author can manually add a memory entry (e.g., a secret or world rule)."""
    _get_owned_story(story_id, user, db)

    from services.ai_service import embed_text_sync
    emb = None
    try:
        # Sync endpoint — embed_text is async and cannot be awaited here.
        emb = embed_text_sync(req.content[:512])
    except Exception as exc:
        print(f"[story_intel] author-memory embedding failed for key={req.memory_key!r}: {exc!r}")

    existing = db.query(StoryMemoryEntry).filter_by(
        story_id=story_id, memory_key=req.memory_key
    ).first()

    if existing:
        existing.content = req.content
        existing.importance = req.importance or 0.5
        existing.is_author_added = True
        existing.embedding = emb
        from datetime import datetime
        existing.updated_at = datetime.utcnow()
        db.commit()
        return existing
    else:
        entry = StoryMemoryEntry(
            entry_id=gen_uuid(),
            story_id=story_id,
            memory_type=req.memory_type,
            memory_key=req.memory_key,
            entity_type=req.entity_type or "",
            entity_id=req.entity_id or "",
            content=req.content,
            importance=req.importance or 0.5,
            is_ai_generated=False,
            is_author_added=True,
            embedding=emb,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry


# ── V2: Timeline ──────────────────────────────────────────────────────────────

@router.get("/{story_id}/intelligence/timeline", response_model=StoryTimelineOut)
def get_timeline(story_id: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    _get_owned_story(story_id, user, db)
    obj = db.query(StoryTimeline).filter_by(story_id=story_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Not yet analyzed")
    return obj


@router.get("/{story_id}/intelligence/timeline/events")
def list_timeline_events(
    story_id: str,
    chapter_number: Optional[int] = None,
    flashbacks_only: bool = False,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_owned_story(story_id, user, db)
    q = db.query(StoryTimelineEvent).filter_by(story_id=story_id, is_stale=False)
    if chapter_number is not None:
        q = q.filter_by(chapter_number=chapter_number)
    if flashbacks_only:
        q = q.filter_by(is_flashback=True)
    return q.order_by(StoryTimelineEvent.chapter_number).all()


# ── V2: Story Graph ───────────────────────────────────────────────────────────

@router.get("/{story_id}/intelligence/graph", response_model=StoryGraphResponse)
def get_graph(
    story_id: str,
    node_type: Optional[str] = None,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_owned_story(story_id, user, db)
    node_q = db.query(StoryGraphNode).filter_by(story_id=story_id, is_active=True)
    if node_type:
        node_q = node_q.filter_by(node_type=node_type)
    nodes = node_q.all()

    node_ids = {n.node_id for n in nodes}
    edges = (
        db.query(StoryGraphEdge)
        .filter_by(story_id=story_id, is_active=True)
        .filter(
            StoryGraphEdge.from_node_id.in_(node_ids),
            StoryGraphEdge.to_node_id.in_(node_ids),
        )
        .all()
    )
    return StoryGraphResponse(
        nodes=nodes, edges=edges,
        node_count=len(nodes), edge_count=len(edges),
    )


# ── Integration context (for AI assistance) ───────────────────────────────────

@router.get("/{story_id}/intelligence/context")
async def get_integration_context(
    story_id: str,
    query: Optional[str] = None,
    top_k: int = 12,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return the P29 integration context — used by Plot Assistant and enrichment.
    """
    _get_owned_story(story_id, user, db)
    from services.story_intel_service import build_integration_context
    return await build_integration_context(db, story_id, query=query, top_k=top_k)
