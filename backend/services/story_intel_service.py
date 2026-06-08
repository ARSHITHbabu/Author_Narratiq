"""
Story Intelligence Service — 29 analysis passes (P1–P29)

All Qwen calls go through _complete() in ai_service.py.
All embeddings use get_bge() / embed_text() in ai_service.py.
No paid APIs. All inference is local.

Pass registry:
  P01  genre_hierarchy      — genre, sub-genre, blend rationale
  P02  story_dna            — premise, prose fingerprint
  P03  audience_profile     — primary audience, age range, content warnings
  P04  themes               — primary/secondary themes, motifs, symbols
  P05  conflicts            — conflict types and mapping
  P06  world_profile        — setting, world rules, consistency
  P07  narrative_structure  — act breakdown, narrative promises
  P08  chapter_emotion      — per-chapter emotional tone (batched)
  P09  chapter_pacing       — per-chapter pacing (batched)
  P10  chapter_themes       — per-chapter themes (batched)
  P11  chapter_foreshadow   — per-chapter foreshadowing (batched)
  P12  chapter_continuity   — per-chapter continuity check (batched)
  P13  emotional_arc_synth  — cross-chapter emotional arc synthesis
  P14  pacing_synth         — cross-chapter pacing synthesis
  P15  conflict_evolution   — cross-chapter conflict evolution
  P16  world_synth          — world-building synthesis
  P17  structure_synth      — narrative structure synthesis
  P18  strength_indicators  — craft score cards
  P19  risk_register        — plot holes, unresolved threads
  P20  market_analysis      — (writes into audience_profile)
  P21  series_potential     — (writes into narrative_structure)
  P22  overall_synthesis    — updates story_dna summary fields
  P23  character_intel      — per-character psychographics (batched)
  P24  relationship_intel   — per-relationship dynamics (batched)
  P25  memory_consolidation — write story_memory_entries from all intel
  P26  timeline_extraction  — per-chapter events → story_timeline
  P27  timeline_contradictions — cross-event contradiction detection
  P28  graph_population     — build story_graph_nodes + edges
  P29  integration_context  — build context blob for AI assistance features
"""

import hashlib
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from models import (
    Chapter, Character, CharacterIntelligence, CharacterRelationship,
    RelationshipIntelligence, Story, StoryAudienceProfile, StoryConflicts,
    StoryContinuityRisks, StoryDNA, StoryEmotionalArc,
    StoryForeshadowingRegistry, StoryGenreHierarchy, StoryGraphEdge,
    StoryGraphNode, StoryMemoryEntry, StoryNarrativeStructure, StoryPacingMap,
    StoryRiskRegister, StoryStrengthIndicators, StoryThemes, StoryTimeline,
    StoryTimelineEvent, StoryWorldProfile, gen_uuid,
)
from services.ai_service import (
    _complete, embed_text, embed_text_sync, get_bge,
    vector_distance, vector_similarity,
)

logger = logging.getLogger(__name__)

# ── Utilities ──────────────────────────────────────────────────────────────────

def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]


def _chapters_text(chapters: List[Chapter], max_chars: int = 60000) -> str:
    parts = []
    total = 0
    for ch in sorted(chapters, key=lambda c: c.chapter_number):
        snippet = (ch.content or "")[:3000]
        part = f"[Chapter {ch.chapter_number}: {ch.title or ''}]\n{snippet}"
        if total + len(part) > max_chars:
            break
        parts.append(part)
        total += len(part)
    return "\n\n".join(parts)


def _extract_json_safe(raw: str, fallback: Any = None) -> Any:
    """Extract JSON from LLM output, return fallback on failure."""
    import re
    if raw is None:
        return fallback
    # Try direct parse
    try:
        return json.loads(raw.strip())
    except Exception:
        pass
    # Try extracting JSON block
    m = re.search(r"```(?:json)?\s*([\s\S]+?)```", raw)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except Exception:
            pass
    # Try finding first { ... } or [ ... ]
    for pattern in (r"\{[\s\S]+\}", r"\[[\s\S]+\]"):
        m = re.search(pattern, raw)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return fallback


def _upsert_memory(
    db: Session,
    story_id: str,
    memory_type: str,
    memory_key: str,
    content: str,
    entity_type: str = "",
    entity_id: str = "",
    importance: float = 0.5,
    chapter_number: Optional[int] = None,
) -> None:
    """Upsert a story_memory_entry and compute its BGE-M3 embedding."""
    existing = (
        db.query(StoryMemoryEntry)
        .filter_by(story_id=story_id, memory_key=memory_key)
        .first()
    )
    emb = None
    try:
        # Sync helper — embed_text is async and cannot be awaited here.
        emb = embed_text_sync(content[:512])
    except Exception as exc:
        print(f"[story_intel] memory embedding failed for key={memory_key!r}: {exc!r}")

    if existing:
        existing.content = content
        existing.importance = importance
        existing.entity_type = entity_type
        existing.entity_id = entity_id
        existing.embedding = emb
        if chapter_number is not None:
            existing.chapter_last_updated = chapter_number
        existing.updated_at = datetime.utcnow()
    else:
        entry = StoryMemoryEntry(
            entry_id=gen_uuid(),
            story_id=story_id,
            memory_type=memory_type,
            memory_key=memory_key,
            entity_type=entity_type,
            entity_id=entity_id,
            content=content,
            chapter_first_established=chapter_number,
            chapter_last_updated=chapter_number,
            importance=importance,
            embedding=emb,
            is_ai_generated=True,
        )
        db.add(entry)


# ── P01: Genre Hierarchy ───────────────────────────────────────────────────────

async def run_p01_genre_hierarchy(db: Session, story: Story) -> StoryGenreHierarchy:
    chapters_text = _chapters_text(story.chapters, max_chars=8000)
    description = story.description or ""
    prompt = f"""You are a professional literary analyst. Analyze this story and produce a JSON genre analysis.

Story description: {description[:500]}

Chapter excerpts:
{chapters_text[:6000]}

Return ONLY valid JSON in this exact format:
{{
  "primary_genre": "string",
  "primary_genre_confidence": 0.0-1.0,
  "secondary_genres": [{{"genre": "string", "confidence": 0.0, "rationale": "string"}}],
  "genre_blend_rationale": "string",
  "marketing_category": "string",
  "comparable_titles": ["title1", "title2"],
  "tone_markers": ["tone1", "tone2"]
}}"""

    raw = await _complete(prompt, max_tokens=600, temperature=0.2)
    data = _extract_json_safe(raw, {})

    input_hash = _hash_text(description + chapters_text[:2000])
    obj = db.query(StoryGenreHierarchy).filter_by(story_id=story.story_id).first()
    if not obj:
        obj = StoryGenreHierarchy(genre_id=gen_uuid(), story_id=story.story_id)
        db.add(obj)

    obj.primary_genre = data.get("primary_genre", "")
    obj.primary_genre_confidence = float(data.get("primary_genre_confidence", 0.0))
    obj.secondary_genres = data.get("secondary_genres", [])
    obj.genre_blend_rationale = data.get("genre_blend_rationale", "")
    obj.marketing_category = data.get("marketing_category", "")
    obj.comparable_titles = data.get("comparable_titles", [])
    obj.tone_markers = data.get("tone_markers", [])
    obj.is_stale = False
    obj.input_hash = input_hash
    obj.generated_at = datetime.utcnow()
    db.flush()
    return obj


# ── P02: Story DNA ─────────────────────────────────────────────────────────────

async def run_p02_story_dna(db: Session, story: Story) -> StoryDNA:
    chapters_text = _chapters_text(story.chapters, max_chars=10000)
    prompt = f"""Analyze this story's DNA — its core identity and prose fingerprint. Return ONLY valid JSON.

Story description: {(story.description or '')[:500]}

Chapters:
{chapters_text[:8000]}

Return this JSON:
{{
  "premise": "one sentence",
  "central_question": "the question the story asks",
  "thematic_core": "the core theme",
  "narrative_engine": "what drives the story forward",
  "story_promise": "what the story promises to deliver",
  "resolution_type": "open/closed/ambiguous/cyclical",
  "pov_style": "first/third-limited/third-omniscient/second/mixed",
  "tense": "past/present/mixed",
  "sentence_rhythm": "short/long/varied/fragmented",
  "vocabulary_tier": "literary/accessible/genre/elevated",
  "prose_style": "lyrical/sparse/cinematic/immersive/expository",
  "structural_complexity": "simple/moderate/complex/experimental",
  "confidence": 0.0-1.0
}}"""

    raw = await _complete(prompt, max_tokens=700, temperature=0.2)
    data = _extract_json_safe(raw, {})

    input_hash = _hash_text(chapters_text[:3000])
    obj = db.query(StoryDNA).filter_by(story_id=story.story_id).first()
    if not obj:
        obj = StoryDNA(dna_id=gen_uuid(), story_id=story.story_id)
        db.add(obj)

    obj.premise = data.get("premise", "")
    obj.central_question = data.get("central_question", "")
    obj.thematic_core = data.get("thematic_core", "")
    obj.narrative_engine = data.get("narrative_engine", "")
    obj.story_promise = data.get("story_promise", "")
    obj.resolution_type = data.get("resolution_type", "")
    obj.pov_style = data.get("pov_style", "")
    obj.tense = data.get("tense", "")
    obj.sentence_rhythm = data.get("sentence_rhythm", "")
    obj.vocabulary_tier = data.get("vocabulary_tier", "")
    obj.prose_style = data.get("prose_style", "")
    obj.structural_complexity = data.get("structural_complexity", "")
    obj.confidence = float(data.get("confidence", 0.0))
    obj.is_stale = False
    obj.input_hash = input_hash
    obj.generated_at = datetime.utcnow()
    db.flush()
    return obj


# ── P03: Audience Profile ──────────────────────────────────────────────────────

async def run_p03_audience_profile(db: Session, story: Story) -> StoryAudienceProfile:
    chapters_text = _chapters_text(story.chapters, max_chars=6000)
    prompt = f"""Identify the target audience for this story. Return ONLY valid JSON.

Description: {(story.description or '')[:400]}
Chapters: {chapters_text[:4000]}

JSON format:
{{
  "primary_audience": "string",
  "age_range": "e.g. 18-35",
  "reading_level": "literary/general/YA/middle-grade/genre",
  "content_warnings": ["violence", "strong language", ...],
  "appeal_factors": ["fast-paced plot", "complex characters", ...],
  "comparable_readership": ["fans of X", "readers who enjoyed Y"],
  "marketing_hooks": ["hook1", "hook2"]
}}"""

    raw = await _complete(prompt, max_tokens=500, temperature=0.2)
    data = _extract_json_safe(raw, {})

    obj = db.query(StoryAudienceProfile).filter_by(story_id=story.story_id).first()
    if not obj:
        obj = StoryAudienceProfile(audience_id=gen_uuid(), story_id=story.story_id)
        db.add(obj)

    obj.primary_audience = data.get("primary_audience", "")
    obj.age_range = data.get("age_range", "")
    obj.reading_level = data.get("reading_level", "")
    obj.content_warnings = data.get("content_warnings", [])
    obj.appeal_factors = data.get("appeal_factors", [])
    obj.comparable_readership = data.get("comparable_readership", [])
    obj.marketing_hooks = data.get("marketing_hooks", [])
    obj.is_stale = False
    obj.input_hash = _hash_text(chapters_text[:2000])
    obj.generated_at = datetime.utcnow()
    db.flush()
    return obj


# ── P04: Themes ────────────────────────────────────────────────────────────────

async def run_p04_themes(db: Session, story: Story) -> StoryThemes:
    chapters_text = _chapters_text(story.chapters, max_chars=10000)
    prompt = f"""Extract themes, motifs, and symbols from this story. Return ONLY valid JSON.

Description: {(story.description or '')[:400]}
Chapters: {chapters_text[:8000]}

JSON format:
{{
  "primary_theme": "string",
  "theme_statement": "one complete sentence expressing the theme",
  "secondary_themes": ["theme2", "theme3"],
  "motifs": [{{"name": "string", "occurrences": ["ch1 desc", "ch3 desc"]}}],
  "symbols": [{{"symbol": "string", "meaning": "string"}}],
  "thematic_arc": "how the theme develops across the story"
}}"""

    raw = await _complete(prompt, max_tokens=700, temperature=0.25)
    data = _extract_json_safe(raw, {})

    obj = db.query(StoryThemes).filter_by(story_id=story.story_id).first()
    if not obj:
        obj = StoryThemes(theme_id=gen_uuid(), story_id=story.story_id)
        db.add(obj)

    obj.primary_theme = data.get("primary_theme", "")
    obj.theme_statement = data.get("theme_statement", "")
    obj.secondary_themes = data.get("secondary_themes", [])
    obj.motifs = data.get("motifs", [])
    obj.symbols = data.get("symbols", [])
    obj.thematic_arc = data.get("thematic_arc", "")
    obj.is_stale = False
    obj.input_hash = _hash_text(chapters_text[:2000])
    obj.generated_at = datetime.utcnow()
    db.flush()
    return obj


# ── P05: Conflicts ─────────────────────────────────────────────────────────────

async def run_p05_conflicts(db: Session, story: Story) -> StoryConflicts:
    chapters_text = _chapters_text(story.chapters, max_chars=10000)
    prompt = f"""Map all conflicts in this story. Return ONLY valid JSON.

Chapters: {chapters_text[:8000]}

JSON format:
{{
  "primary_conflict": "description",
  "conflict_type": "man-vs-man/man-vs-self/man-vs-nature/man-vs-society/man-vs-fate/man-vs-technology",
  "secondary_conflicts": [{{"description": "string", "type": "string", "characters": []}}],
  "unresolved_conflicts": ["conflict1", "conflict2"],
  "conflict_resolution_path": "how the primary conflict is resolved or heading"
}}"""

    raw = await _complete(prompt, max_tokens=600, temperature=0.2)
    data = _extract_json_safe(raw, {})

    obj = db.query(StoryConflicts).filter_by(story_id=story.story_id).first()
    if not obj:
        obj = StoryConflicts(conflict_id=gen_uuid(), story_id=story.story_id)
        db.add(obj)

    obj.primary_conflict = data.get("primary_conflict", "")
    obj.conflict_type = data.get("conflict_type", "")
    obj.secondary_conflicts = data.get("secondary_conflicts", [])
    obj.unresolved_conflicts = data.get("unresolved_conflicts", [])
    obj.conflict_resolution_path = data.get("conflict_resolution_path", "")
    obj.is_stale = False
    obj.input_hash = _hash_text(chapters_text[:2000])
    obj.generated_at = datetime.utcnow()
    db.flush()
    return obj


# ── P06: World Profile ─────────────────────────────────────────────────────────

async def run_p06_world_profile(db: Session, story: Story) -> StoryWorldProfile:
    chapters_text = _chapters_text(story.chapters, max_chars=10000)
    prompt = f"""Analyze the story world and setting. Return ONLY valid JSON.

Chapters: {chapters_text[:8000]}

JSON format:
{{
  "setting_type": "contemporary/historical/fantasy/sci-fi/dystopian/rural/urban/other",
  "primary_settings": [{{"name": "string", "description": "string", "chapters": []}}],
  "world_rules": ["rule1", "rule2"],
  "time_period": "string",
  "social_structure": "string",
  "technology_level": "string",
  "magic_system": {{}},
  "cultural_elements": ["element1"],
  "consistency_issues": [{{"issue": "string", "chapter": 0}}]
}}"""

    raw = await _complete(prompt, max_tokens=700, temperature=0.2)
    data = _extract_json_safe(raw, {})

    obj = db.query(StoryWorldProfile).filter_by(story_id=story.story_id).first()
    if not obj:
        obj = StoryWorldProfile(world_id=gen_uuid(), story_id=story.story_id)
        db.add(obj)

    obj.setting_type = data.get("setting_type", "")
    obj.primary_settings = data.get("primary_settings", [])
    obj.world_rules = data.get("world_rules", [])
    obj.time_period = data.get("time_period", "")
    obj.social_structure = data.get("social_structure", "")
    obj.technology_level = data.get("technology_level", "")
    obj.magic_system = data.get("magic_system", {})
    obj.cultural_elements = data.get("cultural_elements", [])
    obj.consistency_issues = data.get("consistency_issues", [])
    obj.is_stale = False
    obj.input_hash = _hash_text(chapters_text[:2000])
    obj.generated_at = datetime.utcnow()
    db.flush()
    return obj


# ── P07: Narrative Structure ───────────────────────────────────────────────────

async def run_p07_narrative_structure(db: Session, story: Story) -> StoryNarrativeStructure:
    chapters = sorted(story.chapters, key=lambda c: c.chapter_number)
    n = len(chapters)
    chapters_text = _chapters_text(chapters, max_chars=10000)
    prompt = f"""Analyze the narrative structure of this {n}-chapter story. Return ONLY valid JSON.

Chapters: {chapters_text[:8000]}

JSON format:
{{
  "structure_type": "three-act/hero's-journey/five-act/freytag-pyramid/kishōtenketsu/non-linear/other",
  "act_breakdown": {{"act1": [1,2,3], "act2": [4,5,6,7,8], "act3": [9,10]}},
  "inciting_incident_chapter": 0,
  "midpoint_chapter": 0,
  "climax_chapter": 0,
  "resolution_chapter": 0,
  "narrative_promises": ["promise1", "promise2"],
  "promises_kept": ["promise1"],
  "promises_broken": [],
  "structural_issues": [{{"issue": "string", "chapter": 0}}]
}}"""

    raw = await _complete(prompt, max_tokens=600, temperature=0.2)
    data = _extract_json_safe(raw, {})

    def _safe_int(val):
        try:
            return int(val) if val is not None else None
        except Exception:
            return None

    obj = db.query(StoryNarrativeStructure).filter_by(story_id=story.story_id).first()
    if not obj:
        obj = StoryNarrativeStructure(structure_id=gen_uuid(), story_id=story.story_id)
        db.add(obj)

    obj.structure_type = data.get("structure_type", "")
    obj.act_breakdown = data.get("act_breakdown", {})
    obj.inciting_incident_chapter = _safe_int(data.get("inciting_incident_chapter"))
    obj.midpoint_chapter = _safe_int(data.get("midpoint_chapter"))
    obj.climax_chapter = _safe_int(data.get("climax_chapter"))
    obj.resolution_chapter = _safe_int(data.get("resolution_chapter"))
    obj.narrative_promises = data.get("narrative_promises", [])
    obj.promises_kept = data.get("promises_kept", [])
    obj.promises_broken = data.get("promises_broken", [])
    obj.structural_issues = data.get("structural_issues", [])
    obj.is_stale = False
    obj.input_hash = _hash_text(chapters_text[:2000])
    obj.generated_at = datetime.utcnow()
    db.flush()
    return obj


# ── P08–P12: Per-Chapter Passes ────────────────────────────────────────────────
# These return data dicts consumed by synthesis passes P13-P17.
# Chapter-level data is stored in the synthesis objects (chapter_emotions,
# chapter_pacing, chapter_theme_map, foreshadowing_registry, continuity_risks).

async def _analyze_chapter_batch(
    chapter: Chapter,
) -> Dict[str, Any]:
    """Run all per-chapter analysis passes (P08-P12) in one LLM call to save tokens."""
    content_snippet = (chapter.content or "")[:2500]
    prompt = f"""Analyze Chapter {chapter.chapter_number}: "{chapter.title or ''}" and return ONLY valid JSON.

Chapter content:
{content_snippet}

Return this JSON:
{{
  "chapter_number": {chapter.chapter_number},
  "emotional_tone": "string (dominant emotion)",
  "emotional_intensity": 0.0-1.0,
  "pacing": "slow/moderate/fast/variable",
  "tension_level": 0.0-1.0,
  "themes": ["theme1"],
  "foreshadowings": [{{"hint": "string", "what_it_may_hint": "string"}}],
  "resolved_foreshadowings": [{{"hint": "string", "payoff": "string"}}],
  "continuity_issues": [{{"issue": "string", "severity": "low/medium/high"}}],
  "key_events": ["event1", "event2"],
  "characters_present": ["name1"]
}}"""

    raw = await _complete(prompt, max_tokens=600, temperature=0.2)
    data = _extract_json_safe(raw, {})
    data["chapter_number"] = chapter.chapter_number
    return data


# ── P13: Emotional Arc Synthesis ───────────────────────────────────────────────

async def run_p13_emotional_arc(
    db: Session,
    story: Story,
    chapter_data: List[Dict[str, Any]],
) -> StoryEmotionalArc:
    emotions = [
        {"chapter": d.get("chapter_number"), "tone": d.get("emotional_tone", ""),
         "intensity": d.get("emotional_intensity", 0.0)}
        for d in chapter_data
    ]
    prompt = f"""Given these per-chapter emotional tones, synthesize the story's emotional arc. Return ONLY valid JSON.

Chapter emotions: {json.dumps(emotions)}

JSON format:
{{
  "overall_arc_shape": "rise-fall-rise / tragedy / comedy / flat / erratic",
  "opening_emotion": "string",
  "midpoint_emotion": "string",
  "climax_emotion": "string",
  "resolution_emotion": "string",
  "emotional_contrast_score": 0.0-1.0,
  "dominant_emotions": ["emotion1", "emotion2"],
  "emotional_gaps": [1, 5]
}}"""

    raw = await _complete(prompt, max_tokens=400, temperature=0.2)
    data = _extract_json_safe(raw, {})

    obj = db.query(StoryEmotionalArc).filter_by(story_id=story.story_id).first()
    if not obj:
        obj = StoryEmotionalArc(arc_id=gen_uuid(), story_id=story.story_id)
        db.add(obj)

    obj.overall_arc_shape = data.get("overall_arc_shape", "")
    obj.opening_emotion = data.get("opening_emotion", "")
    obj.midpoint_emotion = data.get("midpoint_emotion", "")
    obj.climax_emotion = data.get("climax_emotion", "")
    obj.resolution_emotion = data.get("resolution_emotion", "")
    obj.emotional_contrast_score = float(data.get("emotional_contrast_score", 0.0))
    obj.chapter_emotions = emotions
    obj.dominant_emotions = data.get("dominant_emotions", [])
    obj.emotional_gaps = data.get("emotional_gaps", [])
    obj.is_stale = False
    obj.input_hash = _hash_text(str(emotions))
    obj.generated_at = datetime.utcnow()
    db.flush()
    return obj


# ── P14: Pacing Synthesis ──────────────────────────────────────────────────────

async def run_p14_pacing(
    db: Session,
    story: Story,
    chapter_data: List[Dict[str, Any]],
) -> StoryPacingMap:
    pacing_list = [
        {"chapter": d.get("chapter_number"), "pacing": d.get("pacing", ""),
         "tension": d.get("tension_level", 0.0)}
        for d in chapter_data
    ]
    prompt = f"""Synthesize pacing analysis across all chapters. Return ONLY valid JSON.

Chapter pacing data: {json.dumps(pacing_list)}

JSON format:
{{
  "overall_pacing": "slow/balanced/fast/erratic",
  "slow_zones": [1, 4],
  "tension_peaks": [7, 12],
  "pacing_score": 0.0-1.0,
  "pacing_issues": [{{"chapter": 0, "issue": "string"}}]
}}"""

    raw = await _complete(prompt, max_tokens=400, temperature=0.2)
    data = _extract_json_safe(raw, {})

    obj = db.query(StoryPacingMap).filter_by(story_id=story.story_id).first()
    if not obj:
        obj = StoryPacingMap(pacing_id=gen_uuid(), story_id=story.story_id)
        db.add(obj)

    obj.overall_pacing = data.get("overall_pacing", "")
    obj.chapter_pacing = pacing_list
    obj.slow_zones = data.get("slow_zones", [])
    obj.tension_peaks = data.get("tension_peaks", [])
    obj.pacing_score = float(data.get("pacing_score", 0.0))
    obj.pacing_issues = data.get("pacing_issues", [])
    obj.is_stale = False
    obj.input_hash = _hash_text(str(pacing_list))
    obj.generated_at = datetime.utcnow()
    db.flush()
    return obj


# ── P15: Conflict Evolution ────────────────────────────────────────────────────

async def run_p15_conflict_evolution(
    db: Session,
    story: Story,
    chapter_data: List[Dict[str, Any]],
) -> StoryConflicts:
    """Updates existing StoryConflicts record with chapter-level evolution data."""
    events_summary = [
        {"chapter": d.get("chapter_number"), "key_events": d.get("key_events", [])}
        for d in chapter_data
    ]
    prompt = f"""Track how conflicts evolve across these chapter events. Return ONLY valid JSON.

Chapter events: {json.dumps(events_summary)}

JSON format:
{{
  "conflict_evolution": [
    {{"chapter": 1, "conflict_status": "string", "escalation": 0.0-1.0}}
  ],
  "chapter_conflict_map": {{"1": ["conflict1"], "2": ["conflict2"]}}
}}"""

    raw = await _complete(prompt, max_tokens=500, temperature=0.2)
    data = _extract_json_safe(raw, {})

    obj = db.query(StoryConflicts).filter_by(story_id=story.story_id).first()
    if obj:
        obj.conflict_evolution = data.get("conflict_evolution", [])
        obj.chapter_conflict_map = data.get("chapter_conflict_map", {})
        db.flush()
    return obj


# ── P16: World Synthesis (consistency check) ──────────────────────────────────

async def run_p16_world_synth(
    db: Session,
    story: Story,
    chapter_data: List[Dict[str, Any]],
) -> StoryWorldProfile:
    """Updates world profile with cross-chapter consistency issues."""
    obj = db.query(StoryWorldProfile).filter_by(story_id=story.story_id).first()
    if not obj:
        return obj
    continuity_issues = []
    for d in chapter_data:
        for issue in d.get("continuity_issues", []):
            if issue.get("severity") in ("medium", "high"):
                continuity_issues.append({
                    "chapter": d.get("chapter_number"),
                    **issue,
                })
    obj.consistency_issues = (obj.consistency_issues or []) + continuity_issues
    db.flush()
    return obj


# ── P17: Structure Synthesis ───────────────────────────────────────────────────

async def run_p17_structure_synth(
    db: Session,
    story: Story,
    chapter_data: List[Dict[str, Any]],
) -> StoryNarrativeStructure:
    """Updates foreshadowing and promise tracking from chapter data."""
    # Aggregate foreshadowing across all chapters
    all_foreshadow = []
    all_resolved = []
    all_payoffs_without_setup = []
    for d in chapter_data:
        for f in d.get("foreshadowings", []):
            all_foreshadow.append({"chapter": d.get("chapter_number"), **f})
        for r in d.get("resolved_foreshadowings", []):
            all_resolved.append({"chapter": d.get("chapter_number"), **r})

    # Write to foreshadowing registry
    freg = db.query(StoryForeshadowingRegistry).filter_by(story_id=story.story_id).first()
    if not freg:
        freg = StoryForeshadowingRegistry(foreshadow_id=gen_uuid(), story_id=story.story_id)
        db.add(freg)
    freg.active_foreshadowings = all_foreshadow
    freg.resolved_foreshadowings = all_resolved
    freg.orphaned_hints = [f for f in all_foreshadow if f not in all_resolved]
    freg.is_stale = False
    freg.input_hash = _hash_text(str(all_foreshadow))
    freg.generated_at = datetime.utcnow()

    # Write continuity risks
    all_cont_issues = []
    for d in chapter_data:
        for issue in d.get("continuity_issues", []):
            all_cont_issues.append({"chapter": d.get("chapter_number"), **issue})

    crisk = db.query(StoryContinuityRisks).filter_by(story_id=story.story_id).first()
    if not crisk:
        crisk = StoryContinuityRisks(continuity_id=gen_uuid(), story_id=story.story_id)
        db.add(crisk)
    # Separate by category (heuristic: look for keywords)
    crisk.character_continuity_issues = [i for i in all_cont_issues if "character" in str(i).lower()]
    crisk.world_continuity_issues = [i for i in all_cont_issues if "world" in str(i).lower() or "setting" in str(i).lower()]
    crisk.timeline_continuity_issues = [i for i in all_cont_issues if "time" in str(i).lower() or "date" in str(i).lower()]
    crisk.object_continuity_issues = [i for i in all_cont_issues if "object" in str(i).lower() or "item" in str(i).lower()]
    crisk.chapter_continuity_map = {str(d.get("chapter_number")): d.get("continuity_issues", []) for d in chapter_data}
    high_count = sum(1 for i in all_cont_issues if i.get("severity") == "high")
    crisk.risk_score = min(1.0, high_count / max(len(all_cont_issues), 1))
    crisk.is_stale = False
    crisk.input_hash = _hash_text(str(all_cont_issues))
    crisk.generated_at = datetime.utcnow()

    db.flush()
    return db.query(StoryNarrativeStructure).filter_by(story_id=story.story_id).first()


# ── P18: Strength Indicators ───────────────────────────────────────────────────

async def run_p18_strength_indicators(db: Session, story: Story) -> StoryStrengthIndicators:
    chapters_text = _chapters_text(story.chapters, max_chars=8000)
    prompt = f"""Score this story across craft dimensions from 0.0 to 1.0. Return ONLY valid JSON.

Description: {(story.description or '')[:400]}
Chapters: {chapters_text[:6000]}

JSON format:
{{
  "overall_score": 0.0,
  "voice_score": 0.0,
  "originality_score": 0.0,
  "character_depth_score": 0.0,
  "plot_coherence_score": 0.0,
  "pacing_score": 0.0,
  "world_building_score": 0.0,
  "dialogue_quality_score": 0.0,
  "strengths": ["strength1", "strength2"],
  "score_rationale": {{"voice": "string", "originality": "string"}}
}}"""

    raw = await _complete(prompt, max_tokens=600, temperature=0.2)
    data = _extract_json_safe(raw, {})

    obj = db.query(StoryStrengthIndicators).filter_by(story_id=story.story_id).first()
    if not obj:
        obj = StoryStrengthIndicators(strength_id=gen_uuid(), story_id=story.story_id)
        db.add(obj)

    for field in ["overall_score", "voice_score", "originality_score",
                  "character_depth_score", "plot_coherence_score", "pacing_score",
                  "world_building_score", "dialogue_quality_score"]:
        setattr(obj, field, float(data.get(field, 0.0)))
    obj.strengths = data.get("strengths", [])
    obj.score_rationale = data.get("score_rationale", {})
    obj.is_stale = False
    obj.input_hash = _hash_text(chapters_text[:2000])
    obj.generated_at = datetime.utcnow()
    db.flush()
    return obj


# ── P19: Risk Register ─────────────────────────────────────────────────────────

async def run_p19_risk_register(
    db: Session,
    story: Story,
    chapter_data: List[Dict[str, Any]],
) -> StoryRiskRegister:
    all_issues = []
    for d in chapter_data:
        for issue in d.get("continuity_issues", []):
            all_issues.append({"chapter": d.get("chapter_number"), **issue})

    chapters_text = _chapters_text(story.chapters, max_chars=8000)
    prompt = f"""Identify risks that could undermine this story. Return ONLY valid JSON.

Chapters: {chapters_text[:6000]}
Known issues: {json.dumps(all_issues[:20])}

JSON format:
{{
  "plot_holes": [{{"description": "string", "chapter": 0, "severity": "low/medium/high"}}],
  "continuity_risks": [{{"description": "string", "severity": "string"}}],
  "character_inconsistencies": [{{"character": "string", "issue": "string"}}],
  "pacing_risks": [{{"description": "string", "chapters": []}}],
  "tonal_shifts": [{{"from_chapter": 0, "to_chapter": 0, "shift": "string"}}],
  "unresolved_threads": ["thread1"],
  "risk_score": 0.0-1.0,
  "critical_issues": ["issue1"]
}}"""

    raw = await _complete(prompt, max_tokens=700, temperature=0.2)
    data = _extract_json_safe(raw, {})

    obj = db.query(StoryRiskRegister).filter_by(story_id=story.story_id).first()
    if not obj:
        obj = StoryRiskRegister(risk_id=gen_uuid(), story_id=story.story_id)
        db.add(obj)

    obj.plot_holes = data.get("plot_holes", [])
    obj.continuity_risks = data.get("continuity_risks", [])
    obj.character_inconsistencies = data.get("character_inconsistencies", [])
    obj.pacing_risks = data.get("pacing_risks", [])
    obj.tonal_shifts = data.get("tonal_shifts", [])
    obj.unresolved_threads = data.get("unresolved_threads", [])
    obj.risk_score = float(data.get("risk_score", 0.0))
    obj.critical_issues = data.get("critical_issues", [])
    obj.is_stale = False
    obj.input_hash = _hash_text(chapters_text[:2000])
    obj.generated_at = datetime.utcnow()
    db.flush()
    return obj


# ── P20: Market Analysis (updates audience_profile) ───────────────────────────

async def run_p20_market_analysis(db: Session, story: Story) -> StoryAudienceProfile:
    """Enriches audience_profile with market positioning data."""
    genre_obj = db.query(StoryGenreHierarchy).filter_by(story_id=story.story_id).first()
    genre_str = genre_obj.primary_genre if genre_obj else "unknown"
    audience_obj = db.query(StoryAudienceProfile).filter_by(story_id=story.story_id).first()
    if not audience_obj:
        return None

    prompt = f"""Generate market positioning analysis for this story. Return ONLY valid JSON.

Genre: {genre_str}
Primary audience: {audience_obj.primary_audience}
Marketing hooks: {json.dumps(audience_obj.marketing_hooks)}

JSON format:
{{
  "market_positioning": "string",
  "shelf_category": "string",
  "series_potential": "standalone/duology/trilogy/open-series",
  "additional_marketing_hooks": ["hook1"]
}}"""

    raw = await _complete(prompt, max_tokens=400, temperature=0.25)
    data = _extract_json_safe(raw, {})

    extra_hooks = data.get("additional_marketing_hooks", [])
    audience_obj.marketing_hooks = list(set((audience_obj.marketing_hooks or []) + extra_hooks))
    db.flush()
    return audience_obj


# ── P21: Series Potential (updates narrative_structure) ───────────────────────

async def run_p21_series_potential(db: Session, story: Story) -> StoryNarrativeStructure:
    """Updates narrative structure with series potential flags."""
    struct_obj = db.query(StoryNarrativeStructure).filter_by(story_id=story.story_id).first()
    if not struct_obj:
        return None
    unresolved = struct_obj.promises_broken or []
    prompt = f"""Assess series potential based on unresolved story threads. Return ONLY valid JSON.

Unresolved threads/promises: {json.dumps(unresolved[:10])}
Story structure type: {struct_obj.structure_type}

JSON format:
{{
  "series_potential": "standalone/duology/trilogy/open-series/anthology",
  "series_hooks": ["hook1"],
  "open_questions": ["question1"]
}}"""

    raw = await _complete(prompt, max_tokens=300, temperature=0.25)
    data = _extract_json_safe(raw, {})

    # Append series data to structural issues field as metadata
    series_meta = {
        "series_potential": data.get("series_potential", ""),
        "series_hooks": data.get("series_hooks", []),
        "open_questions": data.get("open_questions", []),
    }
    existing_issues = struct_obj.structural_issues or []
    struct_obj.structural_issues = existing_issues + [{"type": "series_meta", **series_meta}]
    db.flush()
    return struct_obj


# ── P22: Overall Synthesis ─────────────────────────────────────────────────────

async def run_p22_overall_synthesis(db: Session, story: Story) -> StoryDNA:
    """Final synthesis pass — updates story_dna with cross-analysis insights."""
    dna = db.query(StoryDNA).filter_by(story_id=story.story_id).first()
    risk = db.query(StoryRiskRegister).filter_by(story_id=story.story_id).first()
    strength = db.query(StoryStrengthIndicators).filter_by(story_id=story.story_id).first()

    if not dna:
        return None

    overall = strength.overall_score if strength else 0.0
    critical = (risk.critical_issues or []) if risk else []

    synthesis_summary = f"Overall craft score: {overall:.2f}. Critical issues: {len(critical)}."
    # Store synthesis note in chapter_dna as a synthetic chapter 0 entry
    existing_chapter_dna = dna.chapter_dna or []
    dna.chapter_dna = existing_chapter_dna + [{"chapter": 0, "synthesis_note": synthesis_summary}]
    dna.confidence = min(1.0, (dna.confidence or 0.0) * 0.9 + overall * 0.1)
    db.flush()
    return dna


# ── P23: Character Intelligence ────────────────────────────────────────────────

async def run_p23_character_intel(
    db: Session,
    story: Story,
    character: Character,
) -> CharacterIntelligence:
    """Psychographic analysis for a single character."""
    # Gather chapter mentions
    mentions_text = ""
    if character.mentions:
        snippets = [m.passage_text[:300] for m in character.mentions[:10]]
        mentions_text = "\n---\n".join(snippets)

    profile = character.profile
    profile_text = ""
    if profile:
        parts = [
            profile.personality, profile.motivations, profile.goals,
            profile.backstory, profile.arc_notes, profile.raw_notes,
        ]
        profile_text = " | ".join(p for p in parts if p)

    prompt = f"""Conduct deep psychographic analysis of character "{character.name}" ({character.role}). Return ONLY valid JSON.

Author-defined profile:
{profile_text[:800]}

Mentions in story:
{mentions_text[:2000]}

JSON format:
{{
  "goals": [{{"goal": "string", "type": "external/internal", "chapter_established": 0}}],
  "motivations": "string",
  "internal_wounds": "string",
  "external_objectives": ["objective1"],
  "secrets": [{{"secret": "string", "impact": "string"}}],
  "fears": [{{"fear": "string", "source": "string"}}],
  "contradictions": [{{"behavior": "string", "contradicts": "string"}}],
  "arc_stage": "ordinary-world/call/refusal/acceptance/ordeal/reward/road-back/resurrection/return/static",
  "arc_stage_rationale": "string",
  "voice_distinction_score": 0.0-1.0,
  "voice_markers": ["marker1"],
  "plot_influence_score": 0.0-1.0,
  "consistency_score": 0.0-1.0,
  "consistency_issues": [{{"issue": "string", "chapter": 0}}],
  "confidence": 0.0-1.0
}}"""

    raw = await _complete(prompt, max_tokens=800, temperature=0.25)
    data = _extract_json_safe(raw, {})

    input_hash = _hash_text(profile_text + mentions_text[:500])

    obj = db.query(CharacterIntelligence).filter_by(character_id=character.character_id).first()
    if not obj:
        obj = CharacterIntelligence(
            intel_id=gen_uuid(),
            character_id=character.character_id,
            story_id=story.story_id,
        )
        db.add(obj)

    obj.goals = data.get("goals", [])
    obj.motivations = data.get("motivations", "")
    obj.internal_wounds = data.get("internal_wounds", "")
    obj.external_objectives = data.get("external_objectives", [])
    obj.secrets = data.get("secrets", [])
    obj.fears = data.get("fears", [])
    obj.contradictions = data.get("contradictions", [])
    obj.arc_stage = data.get("arc_stage", "")
    obj.arc_stage_rationale = data.get("arc_stage_rationale", "")
    obj.voice_distinction_score = float(data.get("voice_distinction_score", 0.0))
    obj.voice_markers = data.get("voice_markers", [])
    obj.plot_influence_score = float(data.get("plot_influence_score", 0.0))
    obj.consistency_score = float(data.get("consistency_score", 0.0))
    obj.consistency_issues = data.get("consistency_issues", [])
    obj.confidence = float(data.get("confidence", 0.0))
    obj.is_stale = False
    obj.input_hash = input_hash
    obj.generated_at = datetime.utcnow()
    db.flush()
    return obj


# ── P24: Relationship Intelligence ────────────────────────────────────────────

async def run_p24_relationship_intel(
    db: Session,
    story: Story,
    relationship: CharacterRelationship,
) -> RelationshipIntelligence:
    """Dynamics analysis for a single character relationship."""
    from_char = relationship.from_character
    to_char = relationship.to_character

    # Gather co-mention passages
    from models import CharacterMention
    co_mentions = (
        db.query(CharacterMention)
        .filter(
            CharacterMention.story_id == story.story_id,
            CharacterMention.character_id == relationship.from_character_id,
        )
        .order_by(CharacterMention.chapter_number)
        .limit(8)
        .all()
    )
    co_text = "\n---\n".join(m.passage_text[:300] for m in co_mentions)

    prompt = f"""Analyze the relationship between "{from_char.name}" and "{to_char.name}" in this story.
Relationship type: {relationship.relationship_type}, Strength: {relationship.strength}
Description: {relationship.description or ''}

Co-occurrence passages:
{co_text[:2000]}

Return ONLY valid JSON:
{{
  "evolution_trajectory": "string (how the relationship changes arc-wide)",
  "turning_points": [{{"chapter": 0, "event": "string", "impact": "string"}}],
  "tension_score": 0.0-1.0,
  "trust_score": 0.0-1.0,
  "conflict_score": 0.0-1.0,
  "dependency_score": 0.0-1.0,
  "is_hidden": true/false,
  "hidden_reason": "string or empty",
  "impact_on_plot": "string",
  "history": [{{"chapter": 0, "event": "string"}}],
  "confidence": 0.0-1.0
}}"""

    raw = await _complete(prompt, max_tokens=700, temperature=0.25)
    data = _extract_json_safe(raw, {})

    input_hash = _hash_text(co_text[:500] + relationship.relationship_id)

    obj = db.query(RelationshipIntelligence).filter_by(
        relationship_id=relationship.relationship_id
    ).first()
    if not obj:
        obj = RelationshipIntelligence(
            intel_id=gen_uuid(),
            relationship_id=relationship.relationship_id,
            story_id=story.story_id,
            from_character_id=relationship.from_character_id,
            to_character_id=relationship.to_character_id,
        )
        db.add(obj)

    obj.evolution_trajectory = data.get("evolution_trajectory", "")
    obj.turning_points = data.get("turning_points", [])
    obj.tension_score = float(data.get("tension_score", 0.0))
    obj.trust_score = float(data.get("trust_score", 0.0))
    obj.conflict_score = float(data.get("conflict_score", 0.0))
    obj.dependency_score = float(data.get("dependency_score", 0.0))
    obj.is_hidden = bool(data.get("is_hidden", False))
    obj.hidden_reason = data.get("hidden_reason", "")
    obj.impact_on_plot = data.get("impact_on_plot", "")
    obj.history = data.get("history", [])
    obj.confidence = float(data.get("confidence", 0.0))
    obj.is_stale = False
    obj.input_hash = input_hash
    obj.generated_at = datetime.utcnow()
    db.flush()
    return obj


# ── P25: Memory Consolidation ─────────────────────────────────────────────────

async def run_p25_memory_consolidation(db: Session, story: Story) -> int:
    """
    Write all intelligence findings into story_memory_entries with BGE-M3 embeddings.
    Returns the number of memory entries written.
    """
    written = 0

    # Story DNA
    dna = db.query(StoryDNA).filter_by(story_id=story.story_id).first()
    if dna and dna.premise:
        _upsert_memory(db, story.story_id, "plot", "story.premise", dna.premise, importance=0.9)
        written += 1
    if dna and dna.central_question:
        _upsert_memory(db, story.story_id, "plot", "story.central_question", dna.central_question, importance=0.8)
        written += 1

    # Genre
    genre = db.query(StoryGenreHierarchy).filter_by(story_id=story.story_id).first()
    if genre and genre.primary_genre:
        content = f"Genre: {genre.primary_genre}. Rationale: {genre.genre_blend_rationale}"
        _upsert_memory(db, story.story_id, "plot", "story.genre", content, importance=0.7)
        written += 1

    # Themes
    themes = db.query(StoryThemes).filter_by(story_id=story.story_id).first()
    if themes and themes.primary_theme:
        _upsert_memory(db, story.story_id, "theme", "story.primary_theme", themes.primary_theme, importance=0.8)
        written += 1
        if themes.theme_statement:
            _upsert_memory(db, story.story_id, "theme", "story.theme_statement", themes.theme_statement, importance=0.7)
            written += 1

    # Conflicts
    conflicts = db.query(StoryConflicts).filter_by(story_id=story.story_id).first()
    if conflicts and conflicts.primary_conflict:
        _upsert_memory(db, story.story_id, "conflict", "story.primary_conflict",
                       f"{conflicts.conflict_type}: {conflicts.primary_conflict}", importance=0.85)
        written += 1

    # Per-character intelligence
    char_intels = db.query(CharacterIntelligence).filter_by(story_id=story.story_id).all()
    for ci in char_intels:
        char = db.query(Character).filter_by(character_id=ci.character_id).first()
        name = char.name if char else ci.character_id

        if ci.motivations:
            _upsert_memory(db, story.story_id, "character",
                           f"character.{name.lower()}.motivations", ci.motivations,
                           entity_type="character", entity_id=ci.character_id, importance=0.8)
            written += 1

        if ci.internal_wounds:
            _upsert_memory(db, story.story_id, "character",
                           f"character.{name.lower()}.wounds", ci.internal_wounds,
                           entity_type="character", entity_id=ci.character_id, importance=0.75)
            written += 1

        if ci.arc_stage:
            content = f"Arc stage: {ci.arc_stage}. {ci.arc_stage_rationale}"
            _upsert_memory(db, story.story_id, "character",
                           f"character.{name.lower()}.arc_stage", content,
                           entity_type="character", entity_id=ci.character_id, importance=0.7)
            written += 1

        for secret in (ci.secrets or [])[:3]:
            secret_text = secret if isinstance(secret, str) else json.dumps(secret)
            key = f"character.{name.lower()}.secret.{_hash_text(secret_text)}"
            _upsert_memory(db, story.story_id, "character", key, secret_text,
                           entity_type="character", entity_id=ci.character_id, importance=0.9)
            written += 1

    # Per-relationship intelligence
    rel_intels = db.query(RelationshipIntelligence).filter_by(story_id=story.story_id).all()
    for ri in rel_intels:
        from_char = db.query(Character).filter_by(character_id=ri.from_character_id).first()
        to_char = db.query(Character).filter_by(character_id=ri.to_character_id).first()
        from_name = from_char.name.lower() if from_char else ri.from_character_id
        to_name = to_char.name.lower() if to_char else ri.to_character_id

        if ri.evolution_trajectory:
            key = f"relationship.{from_name}.{to_name}.evolution"
            content = f"{from_name} → {to_name}: {ri.evolution_trajectory}"
            _upsert_memory(db, story.story_id, "relationship", key, content,
                           entity_type="relationship", entity_id=ri.relationship_id,
                           importance=0.75)
            written += 1

        if ri.is_hidden and ri.hidden_reason:
            key = f"relationship.{from_name}.{to_name}.hidden"
            _upsert_memory(db, story.story_id, "relationship", key, ri.hidden_reason,
                           entity_type="relationship", entity_id=ri.relationship_id,
                           importance=0.95)
            written += 1

    # Risk register
    risk = db.query(StoryRiskRegister).filter_by(story_id=story.story_id).first()
    if risk:
        for i, hole in enumerate((risk.plot_holes or [])[:5]):
            hole_text = hole if isinstance(hole, str) else json.dumps(hole)
            _upsert_memory(db, story.story_id, "plot",
                           f"story.plot_hole.{i}", hole_text, importance=0.9)
            written += 1

    db.flush()
    return written


# ── P26: Timeline Extraction ───────────────────────────────────────────────────

async def run_p26_timeline(db: Session, story: Story) -> StoryTimeline:
    """Extract temporal events from all chapters and build timeline summary."""
    chapters = sorted(story.chapters, key=lambda c: c.chapter_number)

    # Delete stale events
    db.query(StoryTimelineEvent).filter_by(story_id=story.story_id).delete()

    all_events: List[Dict[str, Any]] = []
    for chapter in chapters:
        content_snippet = (chapter.content or "")[:2000]
        prompt = f"""Extract all temporal events from Chapter {chapter.chapter_number}: "{chapter.title or ''}". Return ONLY valid JSON.

Content:
{content_snippet}

JSON format (array):
[{{
  "event_type": "action/dialogue/flashback/flashforward/reference/backstory",
  "story_date": "approximate story date/time if mentioned",
  "temporal_marker": "exact phrase like 'three days later'",
  "characters_involved": ["name1"],
  "location": "string",
  "event_description": "string",
  "is_flashback": false,
  "is_flashforward": false,
  "flash_origin_chapter": null
}}]"""

        raw = await _complete(prompt, max_tokens=500, temperature=0.2)
        events = _extract_json_safe(raw, [])
        if not isinstance(events, list):
            events = []

        for ev in events:
            event = StoryTimelineEvent(
                event_id=gen_uuid(),
                story_id=story.story_id,
                chapter_id=chapter.chapter_id,
                chapter_number=chapter.chapter_number,
                event_type=ev.get("event_type", "action"),
                story_date=ev.get("story_date", ""),
                temporal_marker=ev.get("temporal_marker", ""),
                characters_involved=ev.get("characters_involved", []),
                location=ev.get("location", ""),
                event_description=ev.get("event_description", ""),
                is_flashback=bool(ev.get("is_flashback", False)),
                is_flashforward=bool(ev.get("is_flashforward", False)),
                flash_origin_chapter=ev.get("flash_origin_chapter"),
                generated_at=datetime.utcnow(),
            )
            db.add(event)
            all_events.append(ev)

    # Timeline summary
    flashbacks = sum(1 for e in all_events if e.get("is_flashback"))
    flashforwards = sum(1 for e in all_events if e.get("is_flashforward"))
    timeline_type = "non-linear" if (flashbacks + flashforwards) > 2 else "linear"

    prompt2 = f"""Synthesize the timeline of this story from its events. Return ONLY valid JSON.

Total events: {len(all_events)}, Flashbacks: {flashbacks}, Flash-forwards: {flashforwards}
Event samples: {json.dumps(all_events[:8])}

JSON format:
{{
  "timeline_type": "linear/non-linear/circular/multi-threaded",
  "estimated_story_duration": "string e.g. '3 weeks'",
  "start_period": "string",
  "end_period": "string",
  "seasons_mentioned": ["summer", "winter"],
  "significant_time_gaps": [{{"between_chapters": [0, 0], "gap": "string"}}],
  "character_age_map": {{"character_name": "age_info"}},
  "confidence": 0.0-1.0
}}"""

    raw2 = await _complete(prompt2, max_tokens=400, temperature=0.2)
    tl_data = _extract_json_safe(raw2, {})

    tl = db.query(StoryTimeline).filter_by(story_id=story.story_id).first()
    if not tl:
        tl = StoryTimeline(timeline_id=gen_uuid(), story_id=story.story_id)
        db.add(tl)
        db.flush()  # get timeline_id before assigning to events

    # Assign timeline_id to events
    for ev_obj in db.query(StoryTimelineEvent).filter_by(story_id=story.story_id).all():
        ev_obj.timeline_id = tl.timeline_id

    tl.timeline_type = tl_data.get("timeline_type", timeline_type)
    tl.estimated_story_duration = tl_data.get("estimated_story_duration", "")
    tl.start_period = tl_data.get("start_period", "")
    tl.end_period = tl_data.get("end_period", "")
    tl.seasons_mentioned = tl_data.get("seasons_mentioned", [])
    tl.significant_time_gaps = tl_data.get("significant_time_gaps", [])
    tl.character_age_map = tl_data.get("character_age_map", {})
    tl.confidence = float(tl_data.get("confidence", 0.0))
    tl.is_stale = False
    tl.input_hash = _hash_text(str(all_events[:10]))
    tl.generated_at = datetime.utcnow()
    db.flush()
    return tl


# ── P27: Timeline Contradiction Detection ─────────────────────────────────────

async def run_p27_timeline_contradictions(db: Session, story: Story) -> StoryTimeline:
    """Detect temporal contradictions across extracted events."""
    tl = db.query(StoryTimeline).filter_by(story_id=story.story_id).first()
    if not tl:
        return None

    events = (
        db.query(StoryTimelineEvent)
        .filter_by(story_id=story.story_id, is_stale=False)
        .order_by(StoryTimelineEvent.chapter_number)
        .all()
    )
    if not events:
        return tl

    event_list = [
        {"chapter": e.chapter_number, "date": e.story_date,
         "marker": e.temporal_marker, "desc": e.event_description[:100]}
        for e in events[:30]
    ]

    prompt = f"""Check these story timeline events for temporal contradictions. Return ONLY valid JSON.

Events: {json.dumps(event_list)}

JSON format:
{{
  "contradictions": [
    {{
      "event_a_chapter": 0,
      "event_b_chapter": 0,
      "description": "string",
      "severity": "low/medium/high"
    }}
  ]
}}"""

    raw = await _complete(prompt, max_tokens=400, temperature=0.2)
    data = _extract_json_safe(raw, {})

    contradictions = data.get("contradictions", [])
    tl.contradictions = contradictions
    tl.contradictions_detected = len(contradictions)
    db.flush()

    # Also write to memory
    if contradictions:
        _upsert_memory(
            db, story.story_id, "timeline",
            "story.timeline.contradictions",
            f"{len(contradictions)} temporal contradiction(s) detected.",
            importance=0.85,
        )

    return tl


# ── P28: Graph Population ─────────────────────────────────────────────────────

async def run_p28_graph_population(db: Session, story: Story) -> Tuple[int, int]:
    """Build story_graph_nodes and story_graph_edges. Returns (node_count, edge_count)."""
    # Clear existing graph
    db.query(StoryGraphEdge).filter_by(story_id=story.story_id).delete()
    db.query(StoryGraphNode).filter_by(story_id=story.story_id).delete()

    node_map: Dict[str, str] = {}  # entity_key → node_id

    def _ensure_node(node_type: str, label: str, entity_id: str = "",
                     properties: Dict = None, chapter: Optional[int] = None) -> str:
        key = f"{node_type}:{entity_id or label}"
        if key in node_map:
            return node_map[key]
        emb = None
        try:
            # Sync helper — embed_text is async and cannot be awaited here.
            emb = embed_text_sync(f"{node_type} {label}"[:256])
        except Exception as exc:
            print(f"[story_intel] graph-node embedding failed for {node_type}:{label!r}: {exc!r}")
        node = StoryGraphNode(
            node_id=gen_uuid(),
            story_id=story.story_id,
            node_type=node_type,
            label=label,
            entity_id=entity_id,
            properties=properties or {},
            embedding=emb,
            chapter_introduced=chapter,
        )
        db.add(node)
        node_map[key] = node.node_id
        return node.node_id

    def _add_edge(from_id: str, to_id: str, edge_type: str, weight: float = 1.0,
                  label: str = "", chapter: Optional[int] = None, props: Dict = None) -> None:
        edge = StoryGraphEdge(
            edge_id=gen_uuid(),
            story_id=story.story_id,
            from_node_id=from_id,
            to_node_id=to_id,
            edge_type=edge_type,
            weight=weight,
            label=label,
            chapter_established=chapter,
            properties=props or {},
        )
        db.add(edge)

    # Story root node
    story_nid = _ensure_node("story", story.title, entity_id=story.story_id)

    # Chapter nodes
    for ch in sorted(story.chapters, key=lambda c: c.chapter_number):
        ch_nid = _ensure_node("chapter", f"Ch.{ch.chapter_number}: {ch.title or ''}",
                              entity_id=ch.chapter_id, chapter=ch.chapter_number)
        _add_edge(story_nid, ch_nid, "contains_chapter", chapter=ch.chapter_number)

    # Character nodes
    for char in story.characters:
        char_nid = _ensure_node("character", char.name, entity_id=char.character_id)
        _add_edge(story_nid, char_nid, "has_character")

        # Character ↔ chapters via mentions
        mentioned_chapters = set()
        for mention in char.mentions:
            mentioned_chapters.add(mention.chapter_number)
        for chnum in mentioned_chapters:
            ch_key = f"chapter:{next((c.chapter_id for c in story.chapters if c.chapter_number == chnum), '')}"
            if ch_key in node_map:
                _add_edge(char_nid, node_map[ch_key], "appears_in_chapter",
                          weight=0.8, chapter=chnum)

    # Character relationship edges
    for rel in story.character_relationships:
        from_key = f"character:{rel.from_character_id}"
        to_key = f"character:{rel.to_character_id}"
        if from_key in node_map and to_key in node_map:
            ri = rel.intelligence
            weight = 0.5
            if ri:
                weight = max(ri.tension_score, ri.trust_score, ri.conflict_score)
            _add_edge(node_map[from_key], node_map[to_key],
                      f"relationship_{rel.relationship_type}",
                      weight=weight, label=rel.relationship_type)

    # Theme nodes
    themes = db.query(StoryThemes).filter_by(story_id=story.story_id).first()
    if themes and themes.primary_theme:
        th_nid = _ensure_node("theme", themes.primary_theme)
        _add_edge(story_nid, th_nid, "has_theme", weight=0.9)

    # Conflict nodes
    conflicts = db.query(StoryConflicts).filter_by(story_id=story.story_id).first()
    if conflicts and conflicts.primary_conflict:
        conf_nid = _ensure_node("conflict", conflicts.primary_conflict[:80])
        _add_edge(story_nid, conf_nid, "has_conflict", weight=0.85)

    db.flush()

    node_count = db.query(StoryGraphNode).filter_by(story_id=story.story_id).count()
    edge_count = db.query(StoryGraphEdge).filter_by(story_id=story.story_id).count()
    return node_count, edge_count


# ── P29: Integration Context Builder ──────────────────────────────────────────

async def build_integration_context(
    db: Session,
    story_id: str,
    query: Optional[str] = None,
    top_k: int = 12,
) -> Dict[str, Any]:
    """
    Build a rich context blob for AI assistance features (Plot Assistant, enrichment, etc).
    Reads from story_memory_entries via BGE-M3 semantic search when a query is given,
    otherwise returns a structured summary of all intelligence tables.
    """
    context: Dict[str, Any] = {}

    story = db.query(Story).filter_by(story_id=story_id).first()
    if not story:
        return context

    # 1. Semantic memory retrieval
    if query:
        try:
            query_emb = await embed_text(query[:512])   # returns list[float]
            from sqlalchemy import text as sql_text
            results = db.execute(
                sql_text(
                    "SELECT entry_id, memory_type, memory_key, content, importance, "
                    "entity_type, entity_id, "
                    f"{vector_similarity('embedding', 'qemb')} AS score "
                    "FROM story_memory_entries "
                    "WHERE story_id = :sid AND is_active = true AND embedding IS NOT NULL "
                    f"ORDER BY {vector_distance('embedding', 'qemb')} "
                    "LIMIT :k"
                ),
                {"qemb": str(query_emb), "sid": story_id, "k": top_k},
            ).fetchall()
            context["memory_hits"] = [
                {
                    "key": r.memory_key,
                    "type": r.memory_type,
                    "content": r.content,
                    "importance": r.importance,
                    "score": float(r.score),
                }
                for r in results
            ]
        except Exception as e:
            logger.warning(f"[P29] memory search failed: {e}")
            context["memory_hits"] = []

    # 2. Structured intelligence summary
    dna = db.query(StoryDNA).filter_by(story_id=story_id).first()
    if dna:
        context["story_premise"] = dna.premise
        context["central_question"] = dna.central_question
        context["pov_style"] = dna.pov_style
        context["tense"] = dna.tense

    genre = db.query(StoryGenreHierarchy).filter_by(story_id=story_id).first()
    if genre:
        context["genre"] = genre.primary_genre
        context["tone_markers"] = genre.tone_markers or []

    themes = db.query(StoryThemes).filter_by(story_id=story_id).first()
    if themes:
        context["primary_theme"] = themes.primary_theme
        context["theme_statement"] = themes.theme_statement

    conflicts = db.query(StoryConflicts).filter_by(story_id=story_id).first()
    if conflicts:
        context["primary_conflict"] = conflicts.primary_conflict

    # Character summaries
    char_intels = db.query(CharacterIntelligence).filter_by(story_id=story_id).all()
    chars_ctx = []
    for ci in char_intels:
        char = db.query(Character).filter_by(character_id=ci.character_id).first()
        if char:
            chars_ctx.append({
                "name": char.name,
                "role": char.role,
                "arc_stage": ci.arc_stage,
                "motivations": ci.motivations[:200] if ci.motivations else "",
                "secrets_count": len(ci.secrets or []),
            })
    context["characters"] = chars_ctx

    # Risks
    risk = db.query(StoryRiskRegister).filter_by(story_id=story_id).first()
    if risk:
        context["critical_issues"] = risk.critical_issues or []
        context["unresolved_threads"] = (risk.unresolved_threads or [])[:5]

    return context
