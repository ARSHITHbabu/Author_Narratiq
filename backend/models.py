import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Text, Integer, Boolean, Float,
    ForeignKey, DateTime, JSON, UniqueConstraint
)
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from database import Base


def gen_uuid():
    return str(uuid.uuid4())


def _current_model_version() -> str:
    """Return the configured vLLM model name as the model_version default."""
    from config import settings
    return settings.vllm_model_name


class User(Base):
    __tablename__ = "users"
    user_id = Column(String, primary_key=True, default=gen_uuid)
    email = Column(String, unique=True, nullable=False, index=True)
    username = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    stories = relationship("Story", back_populates="user")


class Story(Base):
    __tablename__ = "stories"
    story_id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.user_id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, default="")
    word_count = Column(Integer, default=0)
    status = Column(String, default="draft")  # draft, active, archived
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="stories")
    chapters = relationship("Chapter", back_populates="story", cascade="all, delete-orphan")
    genre_profile = relationship("GenreProfile", back_populates="story", uselist=False, cascade="all, delete-orphan")
    story_intake = relationship("StoryIntake", back_populates="story", uselist=False, cascade="all, delete-orphan")
    plot_sessions = relationship("PlotAssistantSession", back_populates="story", cascade="all, delete-orphan")
    ocr_uploads = relationship("OcrUpload", back_populates="story", cascade="all, delete-orphan")
    chapter_summaries = relationship("ChapterSummary", back_populates="story", cascade="all, delete-orphan")
    characters = relationship("Character", back_populates="story", cascade="all, delete-orphan")
    character_profiles = relationship("CharacterProfile", back_populates="story", cascade="all, delete-orphan")
    character_relationships = relationship("CharacterRelationship", back_populates="story", cascade="all, delete-orphan")
    story_notes = relationship("StoryNote", back_populates="story", cascade="all, delete-orphan")
    note_cards = relationship("NoteCard", back_populates="story", cascade="all, delete-orphan")
    character_mentions       = relationship("CharacterMention",     back_populates="story", cascade="all, delete-orphan")
    character_hints          = relationship("CharacterHint",         back_populates="story", cascade="all, delete-orphan")
    character_arc_snapshots  = relationship("CharacterArcSnapshot",  back_populates="story", cascade="all, delete-orphan")
    manuscript_jobs          = relationship("ManuscriptJob",          back_populates="story", cascade="all, delete-orphan")
    # Intelligence system relationships
    intel_jobs               = relationship("StoryIntelJob",             back_populates="story", cascade="all, delete-orphan")
    genre_hierarchy          = relationship("StoryGenreHierarchy",       back_populates="story", uselist=False, cascade="all, delete-orphan")
    story_dna                = relationship("StoryDNA",                  back_populates="story", uselist=False, cascade="all, delete-orphan")
    audience_profile         = relationship("StoryAudienceProfile",      back_populates="story", uselist=False, cascade="all, delete-orphan")
    story_themes             = relationship("StoryThemes",               back_populates="story", uselist=False, cascade="all, delete-orphan")
    story_conflicts          = relationship("StoryConflicts",            back_populates="story", uselist=False, cascade="all, delete-orphan")
    world_profile            = relationship("StoryWorldProfile",         back_populates="story", uselist=False, cascade="all, delete-orphan")
    narrative_structure      = relationship("StoryNarrativeStructure",   back_populates="story", uselist=False, cascade="all, delete-orphan")
    emotional_arc            = relationship("StoryEmotionalArc",         back_populates="story", uselist=False, cascade="all, delete-orphan")
    pacing_map               = relationship("StoryPacingMap",            back_populates="story", uselist=False, cascade="all, delete-orphan")
    strength_indicators      = relationship("StoryStrengthIndicators",   back_populates="story", uselist=False, cascade="all, delete-orphan")
    risk_register            = relationship("StoryRiskRegister",         back_populates="story", uselist=False, cascade="all, delete-orphan")
    foreshadowing_registry   = relationship("StoryForeshadowingRegistry",back_populates="story", uselist=False, cascade="all, delete-orphan")
    continuity_risks         = relationship("StoryContinuityRisks",      back_populates="story", uselist=False, cascade="all, delete-orphan")
    intel_versions           = relationship("StoryIntelVersion",         back_populates="story", cascade="all, delete-orphan")
    character_intelligence   = relationship("CharacterIntelligence",     back_populates="story", cascade="all, delete-orphan")
    relationship_intelligence= relationship("RelationshipIntelligence",  back_populates="story", cascade="all, delete-orphan")
    memory_entries           = relationship("StoryMemoryEntry",          back_populates="story", cascade="all, delete-orphan")
    timeline                 = relationship("StoryTimeline",             back_populates="story", uselist=False, cascade="all, delete-orphan")
    timeline_events          = relationship("StoryTimelineEvent",        back_populates="story", cascade="all, delete-orphan")
    graph_nodes              = relationship("StoryGraphNode",            back_populates="story", cascade="all, delete-orphan")
    graph_edges              = relationship("StoryGraphEdge",            back_populates="story", cascade="all, delete-orphan")
    # Phase 2 relationships
    story_bibles             = relationship("StoryBible",                back_populates="story", cascade="all, delete-orphan")
    narrative_threads        = relationship("NarrativeThread",           back_populates="story", cascade="all, delete-orphan")
    pacing_goal              = relationship("PacingGoal",                back_populates="story", uselist=False, cascade="all, delete-orphan")
    audio_uploads            = relationship("AudioUpload",               back_populates="story", cascade="all, delete-orphan")


class Chapter(Base):
    __tablename__ = "chapters"
    chapter_id = Column(String, primary_key=True, default=gen_uuid)
    story_id = Column(String, ForeignKey("stories.story_id"), nullable=False)
    chapter_number = Column(Integer, nullable=False)
    title = Column(String, default="")
    content = Column(Text, default="")  # ProseMirror JSON stored as text
    word_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    story = relationship("Story", back_populates="chapters")
    summary = relationship("ChapterSummary", back_populates="chapter", uselist=False)
    versions = relationship("StoryVersion", back_populates="chapter", cascade="all, delete-orphan")
    chunks = relationship("ChapterChunk", backref="chapter", cascade="all, delete-orphan")


class StoryVersion(Base):
    __tablename__ = "story_versions"
    version_id = Column(String, primary_key=True, default=gen_uuid)
    chapter_id = Column(String, ForeignKey("chapters.chapter_id"), nullable=False)
    content = Column(Text, nullable=False)
    version_number = Column(Integer, nullable=False)
    label = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    chapter = relationship("Chapter", back_populates="versions")


class StoryIntake(Base):
    __tablename__ = "story_intakes"
    intake_id = Column(String, primary_key=True, default=gen_uuid)
    story_id = Column(String, ForeignKey("stories.story_id"), nullable=False, unique=True)
    raw_description = Column(Text, nullable=False)
    detected_genre = Column(String)
    detected_sub_genre = Column(String)
    detected_tone = Column(JSON, default=list)
    detected_audience = Column(String)
    detected_structure = Column(Text)
    detected_conflict = Column(Text)
    theme_hints = Column(JSON, default=list)
    author_confirmed = Column(Boolean, default=False)
    author_overrides = Column(JSON, default=dict)
    model_version = Column(String, default=_current_model_version)
    created_at = Column(DateTime, default=datetime.utcnow)

    story = relationship("Story", back_populates="story_intake")


class GenreProfile(Base):
    __tablename__ = "genre_profiles"
    profile_id = Column(String, primary_key=True, default=gen_uuid)
    story_id = Column(String, ForeignKey("stories.story_id"), nullable=False, unique=True)
    genre = Column(String)
    sub_genre = Column(String)
    tone = Column(JSON, default=list)
    target_audience = Column(String)
    writing_direction = Column(Text)
    injected_into_prompts = Column(Boolean, default=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    story = relationship("Story", back_populates="genre_profile")


class PlotAssistantSession(Base):
    __tablename__ = "plot_assistant_sessions"
    session_id = Column(String, primary_key=True, default=gen_uuid)
    story_id = Column(String, ForeignKey("stories.story_id"), nullable=False)
    user_id = Column(String, ForeignKey("users.user_id"), nullable=False)
    question = Column(Text, nullable=False)
    retrieved_chunks = Column(JSON, default=list)
    suggestions_returned = Column(JSON, default=list)
    suggestion_used = Column(Integer)
    tokens_used = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    story = relationship("Story", back_populates="plot_sessions")


class OcrUpload(Base):
    __tablename__ = "ocr_uploads"
    upload_id = Column(String, primary_key=True, default=gen_uuid)
    story_id = Column(String, ForeignKey("stories.story_id"), nullable=False)
    user_id = Column(String, ForeignKey("users.user_id"), nullable=False)
    image_path = Column(String)
    ocr_engine = Column(String)
    raw_ocr_text = Column(Text)
    cleaned_text = Column(Text)
    note_type = Column(String)
    confidence = Column(Float)
    author_edited_text = Column(Text)
    destination = Column(String)
    confirmed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    story = relationship("Story", back_populates="ocr_uploads")


class ChapterSummary(Base):
    __tablename__ = "chapter_summaries"
    summary_id = Column(String, primary_key=True, default=gen_uuid)
    chapter_id = Column(String, ForeignKey("chapters.chapter_id"), nullable=False, unique=True)
    story_id = Column(String, ForeignKey("stories.story_id"), nullable=False)
    chapter_number = Column(Integer, nullable=False)
    key_events = Column(JSON, default=list)
    characters_present = Column(JSON, default=list)
    locations = Column(JSON, default=list)
    timeline_markers = Column(JSON, default=list)
    emotional_tone = Column(String)
    chapter_purpose = Column(Text)
    raw_summary = Column(Text)
    embedding = Column(Vector(1024), nullable=True)   # BGE-M3 dense vector (1024-dim)
    model_version = Column(String, default=_current_model_version)
    generated_at = Column(DateTime, default=datetime.utcnow)
    is_stale = Column(Boolean, default=False)
    character_ids = Column(JSON, default=list)   # list of character UUIDs in this chapter

    chapter = relationship("Chapter", back_populates="summary")
    story = relationship("Story", back_populates="chapter_summaries")


class ChapterChunk(Base):
    """
    Sub-chapter text segment used for fine-grained semantic search (QA retrieval).

    Each chapter is split into overlapping ~350-word chunks at paragraph boundaries.
    Every chunk has a BGE-M3 embedding. At query time only the top-k most relevant
    chunks are retrieved and passed to Qwen — this keeps context well within the
    LLM window regardless of how many chapters or words the story contains.

    A 200k-word novel → ~580 chunks → searched via pgvector HNSW index in <10 ms.
    """
    __tablename__ = "chapter_chunks"
    chunk_id       = Column(String,  primary_key=True, default=gen_uuid)
    chapter_id     = Column(String,  ForeignKey("chapters.chapter_id"), nullable=False)
    story_id       = Column(String,  ForeignKey("stories.story_id"),    nullable=False)
    chapter_number = Column(Integer, nullable=False)
    chunk_index    = Column(Integer, nullable=False)   # 0-based within chapter
    text           = Column(Text,    nullable=False)   # plain text, ~350 words
    word_count     = Column(Integer, default=0)
    embedding      = Column(Vector(1024), nullable=True)  # BGE-M3 dense vector (1024-dim)
    character_ids  = Column(JSON,    default=list)    # list of character UUIDs in this chunk
    created_at     = Column(DateTime, default=datetime.utcnow)


# ── Character Management ───────────────────────────────────────────────────────

class Character(Base):
    """
    Core character entity — the canonical record for a named person in a story.

    Serves three roles:
      1. Source of truth for character names / aliases (used by OCR entity-safety system)
      2. Parent of CharacterProfile (structured character data + BGE-M3 embedding)
      3. Future: anchor for character relationship graph and arc tracking

    Deliberately lightweight — detailed data lives in CharacterProfile.
    """
    __tablename__ = "characters"
    character_id = Column(String,   primary_key=True, default=gen_uuid)
    story_id     = Column(String,   ForeignKey("stories.story_id"), nullable=False)
    user_id      = Column(String,   ForeignKey("users.user_id"),    nullable=False)
    name         = Column(String,   nullable=False, index=True)
    aliases      = Column(JSON,     default=list)     # alternate names OCR may detect
    role         = Column(String,   default="supporting")  # protagonist|antagonist|supporting|minor
    status       = Column(String,   default="active")      # active|deceased|unknown
    created_at   = Column(DateTime, default=datetime.utcnow)
    updated_at   = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    story         = relationship("Story",              back_populates="characters")
    profile       = relationship("CharacterProfile",   back_populates="character",
                                 uselist=False, cascade="all, delete-orphan")
    mentions      = relationship("CharacterMention",   back_populates="character", cascade="all, delete-orphan")
    arc_snapshots = relationship("CharacterArcSnapshot", back_populates="character", cascade="all, delete-orphan")
    intelligence  = relationship("CharacterIntelligence", back_populates="character",
                                 uselist=False, cascade="all, delete-orphan")


class CharacterProfile(Base):
    """
    Structured character profile — 1:1 with Character.

    Structured fields are populated via the Character Management UI (Task 3).
    raw_notes is the immediate target for OCR injection — the writer's handwritten
    notes land here verbatim and can later be organised into structured fields.

    embedding (BGE-M3 1024-dim) enables Character RAG: the Plot Assistant can
    retrieve relevant character profiles by semantic similarity at query time.
    Computed in the background after each profile update.

    story_id is denormalized here to allow O(1) story-scoped queries without
    a JOIN through the characters table.
    """
    __tablename__ = "character_profiles"
    profile_id   = Column(String,   primary_key=True, default=gen_uuid)
    character_id = Column(String,   ForeignKey("characters.character_id"),
                          nullable=False, unique=True)
    story_id     = Column(String,   ForeignKey("stories.story_id"), nullable=False)

    # Structured fields — populated by user via Character Management UI
    age          = Column(String,   default="")
    appearance   = Column(Text,     default="")
    personality  = Column(Text,     default="")
    motivations  = Column(Text,     default="")
    goals        = Column(Text,     default="")   # what the character is working toward
    backstory    = Column(Text,     default="")
    arc_notes    = Column(Text,     default="")
    traits       = Column(JSON,     default=list)  # personality adjectives e.g. ["stubborn","loyal"]

    # Free-form notes — primary landing zone for OCR-injected text.
    # Multiple OCR confirmations append here with a separator.
    raw_notes    = Column(Text,     default="")

    # BGE-M3 embedding of combined profile text (for Character RAG — Task 3).
    # NULL until first embedding background task completes.
    embedding         = Column(Vector(1024), nullable=True)

    # BGE-M3 embedding of character's story mention passages (story-grounded retrieval).
    # NULL until first mention indexing + embedding task completes.
    mention_embedding = Column(Vector(1024), nullable=True)

    # Traceability: stores upload_id of the OCR image that last wrote raw_notes.
    # Plain string — no FK cascade (upload lifecycle is governed by Story, not Profile).
    ocr_upload_id = Column(String,  nullable=True)

    created_at   = Column(DateTime, default=datetime.utcnow)
    updated_at   = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    character = relationship("Character", back_populates="profile")
    story     = relationship("Story",     back_populates="character_profiles")


class CharacterRelationship(Base):
    """
    Directed relationship edge between two characters within the same story.

    Directed model: from_character_id → to_character_id with a typed label.
    A single pair may have multiple edges (one per relationship_type), e.g.
    Elara is both "family" and "ally" with Kira.

    is_mutual is a rendering hint for the graph UI — it does NOT imply a
    reciprocal DB record.  Bidirectional rendering is triggered by the
    presence of both A→B and B→A records with compatible types, or by
    is_mutual=True on a single directed edge.

    strength classifies intensity for visual edge weight and RAG prioritisation:
      weak | moderate | strong | critical
    """
    __tablename__ = "character_relationships"

    relationship_id   = Column(String,  primary_key=True, default=gen_uuid)
    story_id          = Column(String,  ForeignKey("stories.story_id"),       nullable=False)
    from_character_id = Column(String,  ForeignKey("characters.character_id"), nullable=False)
    to_character_id   = Column(String,  ForeignKey("characters.character_id"), nullable=False)
    relationship_type = Column(String,  nullable=False)
    # ally | rival | family | romantic | mentor | enemy | neutral
    strength          = Column(String,  default="moderate")
    # weak | moderate | strong | critical
    description       = Column(Text,    default="")
    is_mutual         = Column(Boolean, default=False)
    created_at        = Column(DateTime, default=datetime.utcnow)
    updated_at        = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "story_id", "from_character_id", "to_character_id", "relationship_type",
            name="uq_relationship_typed",
        ),
    )

    story          = relationship("Story",     back_populates="character_relationships")
    from_character = relationship("Character", foreign_keys=[from_character_id])
    to_character   = relationship("Character", foreign_keys=[to_character_id])
    intelligence   = relationship("RelationshipIntelligence", back_populates="char_relationship",
                                  uselist=False, cascade="all, delete-orphan")


# ── Character Mentions ─────────────────────────────────────────────────────────

class CharacterMention(Base):
    """
    Records every chunk in which a character is mentioned by name or alias.

    Populated by index_character_mentions() after each chapter is indexed.
    Idempotent: old rows for a chapter are deleted before re-indexing.
    Used for:
      - mention_embedding computation (story-grounded BGE-M3 vectors)
      - character enrichment (evidence extraction for profile suggestions)
      - co-occurrence graph (co_character_ids)
    """
    __tablename__ = "character_mentions"
    mention_id       = Column(String,   primary_key=True, default=gen_uuid)
    character_id     = Column(String,   ForeignKey("characters.character_id"), nullable=False)
    story_id         = Column(String,   ForeignKey("stories.story_id"),        nullable=False)
    chapter_id       = Column(String,   ForeignKey("chapters.chapter_id"),     nullable=False)
    chunk_id         = Column(String,   nullable=True)   # optional ref to chapter_chunks
    chapter_number   = Column(Integer,  nullable=False)
    passage_text     = Column(Text,     nullable=False)  # the chunk text where character is mentioned
    mention_type     = Column(String,   default="reference")  # dialogue|action|description|reference
    co_character_ids = Column(JSON,     default=list)    # other character UUIDs present in same chunk
    created_at       = Column(DateTime, default=datetime.utcnow)

    character = relationship("Character", back_populates="mentions")
    story     = relationship("Story",     back_populates="character_mentions")


# ── Character Hints ────────────────────────────────────────────────────────────

class CharacterHint(Base):
    """
    Suggested new character detected from chapter summaries but not yet in the
    characters table.  Author can promote to Character or dismiss.
    """
    __tablename__ = "character_hints"
    hint_id         = Column(String,   primary_key=True, default=gen_uuid)
    story_id        = Column(String,   ForeignKey("stories.story_id"),    nullable=False)
    chapter_id      = Column(String,   ForeignKey("chapters.chapter_id"), nullable=False)
    chapter_number  = Column(Integer,  nullable=False)
    suggested_name  = Column(String,   nullable=False)
    context_snippet = Column(Text,     default="")
    is_dismissed    = Column(Boolean,  default=False)
    created_at      = Column(DateTime, default=datetime.utcnow)

    story = relationship("Story", back_populates="character_hints")


# ── Character Arc Snapshots ────────────────────────────────────────────────────

class CharacterArcSnapshot(Base):
    """
    Per-chapter character state snapshot — Qwen-derived from CharacterMention
    passages and ChapterSummary context for that chapter.

    One row per (character, chapter) pair, enforced by the unique constraint.
    This constraint is the DB primitive that enables future partial rebuilds:
    DELETE WHERE character_id=X AND chapter_id=Y, then INSERT fresh, without
    touching snapshots for other chapters.

    is_stale: set True by future code (e.g. when index_character_mentions()
    re-runs for a chapter) to flag this snapshot for regeneration.  Full
    rebuilds always write is_stale=False on every freshly created row.

    mention_count: number of CharacterMention rows consumed at generation time.
    Future staleness detection: if current count(character_id, chapter_id) !=
    mention_count, the snapshot is outdated without needing to re-analyse it.
    """
    __tablename__ = "character_arc_snapshots"
    arc_snapshot_id  = Column(String,   primary_key=True, default=gen_uuid)
    character_id     = Column(String,   ForeignKey("characters.character_id"), nullable=False)
    story_id         = Column(String,   ForeignKey("stories.story_id"),        nullable=False)
    chapter_id       = Column(String,   ForeignKey("chapters.chapter_id"),     nullable=False)
    chapter_number   = Column(Integer,  nullable=False)
    role_in_chapter  = Column(String,   default="observer")
    # major_player | observer | turning_point | brief_mention
    emotional_state  = Column(Text,     default="")
    key_action       = Column(Text,     default="")
    development_note = Column(Text,     default="")
    status_change    = Column(String,   nullable=True)
    mention_count    = Column(Integer,  default=0)   # CharacterMention rows used at generation
    is_stale         = Column(Boolean,  default=False)
    generated_at     = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "character_id", "chapter_id",
            name="uq_arc_snapshot_char_chapter",
        ),
    )

    character = relationship("Character", back_populates="arc_snapshots")
    story     = relationship("Story",     back_populates="character_arc_snapshots")


# ── Story Notes ────────────────────────────────────────────────────────────────

class StoryNote(Base):
    """
    Long-form story-level note — world-building, research, plot planning.

    Distinct from NoteCard: story notes are prose research and planning documents.
    Note cards are structured short-form index cards typed by purpose (scene, location,
    theme, etc.).  They have different retrieval roles in future RAG pipelines and
    will develop different schema fields as the product evolves.

    ocr_upload_id is a traceability string, not an enforced FK, so upload deletion
    does not cascade to notes.
    """
    __tablename__ = "story_notes"
    note_id       = Column(String,   primary_key=True, default=gen_uuid)
    story_id      = Column(String,   ForeignKey("stories.story_id"), nullable=False)
    user_id       = Column(String,   ForeignKey("users.user_id"),    nullable=False)
    title         = Column(String,   default="")
    content       = Column(Text,     nullable=False)
    ocr_upload_id = Column(String,   nullable=True)
    embedding     = Column(Vector(1024), nullable=True)  # BGE-M3 1024-dim — NULL until first embed
    created_at    = Column(DateTime, default=datetime.utcnow)
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    story = relationship("Story", back_populates="story_notes")


# ── Note Cards ─────────────────────────────────────────────────────────────────

class NoteCard(Base):
    """
    Structured index card — short-form, typed reference item.

    card_type classifies the card's purpose so future retrieval systems can
    filter by type: scene cards feed scene-structure context, location cards
    feed setting context, character cards feed character context.

    Deliberately separate from StoryNote: these have a typed classification
    system, are shorter and more structured, and will develop different
    embedding strategies (type-specific retrievers vs general story-note retrieval).
    """
    __tablename__ = "note_cards"
    card_id       = Column(String,   primary_key=True, default=gen_uuid)
    story_id      = Column(String,   ForeignKey("stories.story_id"), nullable=False)
    user_id       = Column(String,   ForeignKey("users.user_id"),    nullable=False)
    title         = Column(String,   default="")
    content       = Column(Text,     nullable=False)
    card_type     = Column(String,   default="general")
    ocr_upload_id = Column(String,   nullable=True)
    embedding     = Column(Vector(1024), nullable=True)  # BGE-M3 1024-dim — NULL until first embed
    created_at    = Column(DateTime, default=datetime.utcnow)
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    story = relationship("Story", back_populates="note_cards")


# ── Manuscript Upload Jobs ─────────────────────────────────────────────────────

class ManuscriptJob(Base):
    """
    Persistent job record for manuscript upload ingestion pipeline.

    Replaces the in-memory _jobs dict in manuscript.py so job state survives
    backend restarts, pod restarts, and multiple workers.

    status lifecycle: pending → processing → complete | error
    percent: 0-100 progress indicator updated by _ingest_pipeline at each chapter.
    chapter_count: total chapters detected at parse time (set once, never updated).
    user_id is stored for ownership enforcement on the job_status endpoint.
    """
    __tablename__ = "manuscript_jobs"
    job_id        = Column(String,   primary_key=True, default=gen_uuid)
    story_id      = Column(String,   ForeignKey("stories.story_id"), nullable=False)
    user_id       = Column(String,   ForeignKey("users.user_id"),    nullable=False)
    status        = Column(String,   default="pending")    # pending|processing|complete|error
    stage         = Column(String,   default="")
    percent       = Column(Integer,  default=0)
    message       = Column(Text,     default="")
    chapter_count = Column(Integer,  default=0)
    created_at    = Column(DateTime, default=datetime.utcnow)
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    story = relationship("Story", back_populates="manuscript_jobs")


# ═══════════════════════════════════════════════════════════════════════════════
# Story Intelligence System — V1 + V2 Tables
# ═══════════════════════════════════════════════════════════════════════════════

class StoryIntelJob(Base):
    """Tracks a full-story intelligence analysis run (P1–P29)."""
    __tablename__ = "story_intel_jobs"
    job_id             = Column(String,   primary_key=True, default=gen_uuid)
    story_id           = Column(String,   ForeignKey("stories.story_id"), nullable=False)
    user_id            = Column(String,   ForeignKey("users.user_id"),    nullable=False)
    status             = Column(String,   default="pending")   # pending|running|complete|error
    triggered_by       = Column(String,   default="manual")    # intake|chapter_save|manual|auto
    passes_requested   = Column(JSON,     default=list)
    passes_completed   = Column(JSON,     default=list)
    passes_failed      = Column(JSON,     default=list)
    current_pass       = Column(String,   default="")
    percent            = Column(Integer,  default=0)
    error_message      = Column(Text,     default="")
    created_at         = Column(DateTime, default=datetime.utcnow)
    updated_at         = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    story = relationship("Story", back_populates="intel_jobs")


class StoryGenreHierarchy(Base):
    """Hierarchical genre analysis (Pass P1)."""
    __tablename__ = "story_genre_hierarchy"
    genre_id                  = Column(String,   primary_key=True, default=gen_uuid)
    story_id                  = Column(String,   ForeignKey("stories.story_id"), nullable=False, unique=True)
    primary_genre             = Column(String,   default="")
    primary_genre_confidence  = Column(Float,    default=0.0)
    secondary_genres          = Column(JSON,     default=list)
    genre_blend_rationale     = Column(Text,     default="")
    marketing_category        = Column(String,   default="")
    comparable_titles         = Column(JSON,     default=list)
    tone_markers              = Column(JSON,     default=list)
    author_overrides          = Column(JSON,     default=dict)
    is_stale                  = Column(Boolean,  default=False)
    input_hash                = Column(String,   default="")
    generated_at              = Column(DateTime, default=datetime.utcnow)

    story = relationship("Story", back_populates="genre_hierarchy")


class StoryDNA(Base):
    """Core story identity and prose fingerprint (Pass P2)."""
    __tablename__ = "story_dna"
    dna_id                = Column(String,   primary_key=True, default=gen_uuid)
    story_id              = Column(String,   ForeignKey("stories.story_id"), nullable=False, unique=True)
    premise               = Column(Text,     default="")
    central_question      = Column(Text,     default="")
    thematic_core         = Column(Text,     default="")
    narrative_engine      = Column(Text,     default="")
    story_promise         = Column(Text,     default="")
    resolution_type       = Column(Text,     default="")
    pov_style             = Column(String,   default="")
    tense                 = Column(String,   default="")
    sentence_rhythm       = Column(String,   default="")
    vocabulary_tier       = Column(String,   default="")
    prose_style           = Column(Text,     default="")
    structural_complexity = Column(String,   default="")
    chapter_dna           = Column(JSON,     default=list)
    confidence            = Column(Float,    default=0.0)
    author_overrides      = Column(JSON,     default=dict)
    is_stale              = Column(Boolean,  default=False)
    input_hash            = Column(String,   default="")
    generated_at          = Column(DateTime, default=datetime.utcnow)

    story = relationship("Story", back_populates="story_dna")


class StoryAudienceProfile(Base):
    """Audience and market positioning analysis (Pass P3)."""
    __tablename__ = "story_audience_profile"
    audience_id          = Column(String,   primary_key=True, default=gen_uuid)
    story_id             = Column(String,   ForeignKey("stories.story_id"), nullable=False, unique=True)
    primary_audience     = Column(String,   default="")
    age_range            = Column(String,   default="")
    reading_level        = Column(String,   default="")
    content_warnings     = Column(JSON,     default=list)
    appeal_factors       = Column(JSON,     default=list)
    comparable_readership= Column(JSON,     default=list)
    marketing_hooks      = Column(JSON,     default=list)
    author_overrides     = Column(JSON,     default=dict)
    is_stale             = Column(Boolean,  default=False)
    input_hash           = Column(String,   default="")
    generated_at         = Column(DateTime, default=datetime.utcnow)

    story = relationship("Story", back_populates="audience_profile")


class StoryThemes(Base):
    """Theme and motif extraction (Pass P4)."""
    __tablename__ = "story_themes"
    theme_id          = Column(String,   primary_key=True, default=gen_uuid)
    story_id          = Column(String,   ForeignKey("stories.story_id"), nullable=False, unique=True)
    primary_theme     = Column(Text,     default="")
    theme_statement   = Column(Text,     default="")
    secondary_themes  = Column(JSON,     default=list)
    motifs            = Column(JSON,     default=list)
    symbols           = Column(JSON,     default=list)
    thematic_arc      = Column(Text,     default="")
    chapter_theme_map = Column(JSON,     default=dict)
    author_overrides  = Column(JSON,     default=dict)
    is_stale          = Column(Boolean,  default=False)
    input_hash        = Column(String,   default="")
    generated_at      = Column(DateTime, default=datetime.utcnow)

    story = relationship("Story", back_populates="story_themes")


class StoryConflicts(Base):
    """Conflict mapping and evolution (Passes P5, P15)."""
    __tablename__ = "story_conflicts"
    conflict_id            = Column(String,   primary_key=True, default=gen_uuid)
    story_id               = Column(String,   ForeignKey("stories.story_id"), nullable=False, unique=True)
    primary_conflict       = Column(Text,     default="")
    conflict_type          = Column(String,   default="")
    secondary_conflicts    = Column(JSON,     default=list)
    conflict_evolution     = Column(JSON,     default=list)
    unresolved_conflicts   = Column(JSON,     default=list)
    conflict_resolution_path= Column(Text,   default="")
    chapter_conflict_map   = Column(JSON,     default=dict)
    author_overrides       = Column(JSON,     default=dict)
    is_stale               = Column(Boolean,  default=False)
    input_hash             = Column(String,   default="")
    generated_at           = Column(DateTime, default=datetime.utcnow)

    story = relationship("Story", back_populates="story_conflicts")


class StoryWorldProfile(Base):
    """World-building and setting analysis (Passes P6, P16)."""
    __tablename__ = "story_world_profile"
    world_id            = Column(String,   primary_key=True, default=gen_uuid)
    story_id            = Column(String,   ForeignKey("stories.story_id"), nullable=False, unique=True)
    setting_type        = Column(String,   default="")
    primary_settings    = Column(JSON,     default=list)
    world_rules         = Column(JSON,     default=list)
    time_period         = Column(String,   default="")
    social_structure    = Column(Text,     default="")
    technology_level    = Column(String,   default="")
    magic_system        = Column(JSON,     default=dict)
    cultural_elements   = Column(JSON,     default=list)
    consistency_issues  = Column(JSON,     default=list)
    author_overrides    = Column(JSON,     default=dict)
    is_stale            = Column(Boolean,  default=False)
    input_hash          = Column(String,   default="")
    generated_at        = Column(DateTime, default=datetime.utcnow)

    story = relationship("Story", back_populates="world_profile")


class StoryNarrativeStructure(Base):
    """Narrative structure and promise analysis (Passes P7, P17)."""
    __tablename__ = "story_narrative_structure"
    structure_id            = Column(String,   primary_key=True, default=gen_uuid)
    story_id                = Column(String,   ForeignKey("stories.story_id"), nullable=False, unique=True)
    structure_type          = Column(String,   default="")
    act_breakdown           = Column(JSON,     default=dict)
    inciting_incident_chapter= Column(Integer, nullable=True)
    midpoint_chapter        = Column(Integer,  nullable=True)
    climax_chapter          = Column(Integer,  nullable=True)
    resolution_chapter      = Column(Integer,  nullable=True)
    narrative_promises      = Column(JSON,     default=list)
    promises_kept           = Column(JSON,     default=list)
    promises_broken         = Column(JSON,     default=list)
    structural_issues       = Column(JSON,     default=list)
    author_overrides        = Column(JSON,     default=dict)
    is_stale                = Column(Boolean,  default=False)
    input_hash              = Column(String,   default="")
    generated_at            = Column(DateTime, default=datetime.utcnow)

    story = relationship("Story", back_populates="narrative_structure")


class StoryEmotionalArc(Base):
    """Story-level emotional arc synthesis (Pass P13)."""
    __tablename__ = "story_emotional_arc"
    arc_id                   = Column(String,   primary_key=True, default=gen_uuid)
    story_id                 = Column(String,   ForeignKey("stories.story_id"), nullable=False, unique=True)
    overall_arc_shape        = Column(String,   default="")
    opening_emotion          = Column(String,   default="")
    midpoint_emotion         = Column(String,   default="")
    climax_emotion           = Column(String,   default="")
    resolution_emotion       = Column(String,   default="")
    emotional_contrast_score = Column(Float,    default=0.0)
    chapter_emotions         = Column(JSON,     default=list)
    dominant_emotions        = Column(JSON,     default=list)
    emotional_gaps           = Column(JSON,     default=list)
    author_overrides         = Column(JSON,     default=dict)
    is_stale                 = Column(Boolean,  default=False)
    input_hash               = Column(String,   default="")
    generated_at             = Column(DateTime, default=datetime.utcnow)

    story = relationship("Story", back_populates="emotional_arc")


class StoryPacingMap(Base):
    """Pacing analysis across all chapters (Pass P14)."""
    __tablename__ = "story_pacing_map"
    pacing_id      = Column(String,   primary_key=True, default=gen_uuid)
    story_id       = Column(String,   ForeignKey("stories.story_id"), nullable=False, unique=True)
    overall_pacing = Column(String,   default="")
    act_structure  = Column(JSON,     default=dict)
    chapter_pacing = Column(JSON,     default=list)
    slow_zones     = Column(JSON,     default=list)
    tension_peaks  = Column(JSON,     default=list)
    pacing_score   = Column(Float,    default=0.0)
    pacing_issues  = Column(JSON,     default=list)
    author_overrides= Column(JSON,    default=dict)
    is_stale       = Column(Boolean,  default=False)
    input_hash     = Column(String,   default="")
    generated_at   = Column(DateTime, default=datetime.utcnow)

    story = relationship("Story", back_populates="pacing_map")


class StoryStrengthIndicators(Base):
    """Quantified strength scores across craft dimensions (Pass P18)."""
    __tablename__ = "story_strength_indicators"
    strength_id           = Column(String,   primary_key=True, default=gen_uuid)
    story_id              = Column(String,   ForeignKey("stories.story_id"), nullable=False, unique=True)
    overall_score         = Column(Float,    default=0.0)
    voice_score           = Column(Float,    default=0.0)
    originality_score     = Column(Float,    default=0.0)
    character_depth_score = Column(Float,    default=0.0)
    plot_coherence_score  = Column(Float,    default=0.0)
    pacing_score          = Column(Float,    default=0.0)
    world_building_score  = Column(Float,    default=0.0)
    dialogue_quality_score= Column(Float,    default=0.0)
    strengths             = Column(JSON,     default=list)
    score_rationale       = Column(JSON,     default=dict)
    author_overrides      = Column(JSON,     default=dict)
    is_stale              = Column(Boolean,  default=False)
    input_hash            = Column(String,   default="")
    generated_at          = Column(DateTime, default=datetime.utcnow)

    story = relationship("Story", back_populates="strength_indicators")


class StoryRiskRegister(Base):
    """Identified risks, plot holes, and continuity issues (Pass P19)."""
    __tablename__ = "story_risk_register"
    risk_id                    = Column(String,   primary_key=True, default=gen_uuid)
    story_id                   = Column(String,   ForeignKey("stories.story_id"), nullable=False, unique=True)
    plot_holes                 = Column(JSON,     default=list)
    continuity_risks           = Column(JSON,     default=list)
    character_inconsistencies  = Column(JSON,     default=list)
    pacing_risks               = Column(JSON,     default=list)
    tonal_shifts               = Column(JSON,     default=list)
    unresolved_threads         = Column(JSON,     default=list)
    risk_score                 = Column(Float,    default=0.0)
    critical_issues            = Column(JSON,     default=list)
    author_overrides           = Column(JSON,     default=dict)
    is_stale                   = Column(Boolean,  default=False)
    input_hash                 = Column(String,   default="")
    generated_at               = Column(DateTime, default=datetime.utcnow)

    story = relationship("Story", back_populates="risk_register")


class StoryForeshadowingRegistry(Base):
    """Foreshadowing hints and their payoffs across all chapters (P11 aggregate)."""
    __tablename__ = "story_foreshadowing_registry"
    foreshadow_id           = Column(String,   primary_key=True, default=gen_uuid)
    story_id                = Column(String,   ForeignKey("stories.story_id"), nullable=False, unique=True)
    active_foreshadowings   = Column(JSON,     default=list)
    resolved_foreshadowings = Column(JSON,     default=list)
    orphaned_hints          = Column(JSON,     default=list)
    payoffs_without_setup   = Column(JSON,     default=list)
    is_stale                = Column(Boolean,  default=False)
    input_hash              = Column(String,   default="")
    generated_at            = Column(DateTime, default=datetime.utcnow)

    story = relationship("Story", back_populates="foreshadowing_registry")


class StoryContinuityRisks(Base):
    """Cross-chapter continuity issue aggregation (P12 aggregate)."""
    __tablename__ = "story_continuity_risks"
    continuity_id               = Column(String,   primary_key=True, default=gen_uuid)
    story_id                    = Column(String,   ForeignKey("stories.story_id"), nullable=False, unique=True)
    character_continuity_issues = Column(JSON,     default=list)
    world_continuity_issues     = Column(JSON,     default=list)
    timeline_continuity_issues  = Column(JSON,     default=list)
    object_continuity_issues    = Column(JSON,     default=list)
    chapter_continuity_map      = Column(JSON,     default=dict)
    risk_score                  = Column(Float,    default=0.0)
    is_stale                    = Column(Boolean,  default=False)
    input_hash                  = Column(String,   default="")
    generated_at                = Column(DateTime, default=datetime.utcnow)

    story = relationship("Story", back_populates="continuity_risks")


class StoryIntelVersion(Base):
    """Snapshots of intelligence state for audit and rollback."""
    __tablename__ = "story_intel_versions"
    version_id     = Column(String,   primary_key=True, default=gen_uuid)
    story_id       = Column(String,   ForeignKey("stories.story_id"), nullable=False)
    version_number = Column(Integer,  nullable=False)
    snapshot       = Column(JSON,     default=dict)
    trigger        = Column(String,   default="manual")
    created_at     = Column(DateTime, default=datetime.utcnow)

    story = relationship("Story", back_populates="intel_versions")


# ── V2: Character Intelligence ─────────────────────────────────────────────────

class CharacterIntelligence(Base):
    """Deep per-character psychographic and arc analysis (Pass P23)."""
    __tablename__ = "character_intelligence"
    intel_id               = Column(String,   primary_key=True, default=gen_uuid)
    character_id           = Column(String,   ForeignKey("characters.character_id"), nullable=False, unique=True)
    story_id               = Column(String,   ForeignKey("stories.story_id"),        nullable=False)
    goals                  = Column(JSON,     default=list)
    motivations            = Column(Text,     default="")
    internal_wounds        = Column(Text,     default="")
    external_objectives    = Column(JSON,     default=list)
    secrets                = Column(JSON,     default=list)
    fears                  = Column(JSON,     default=list)
    contradictions         = Column(JSON,     default=list)
    arc_stage              = Column(String,   default="")
    arc_stage_rationale    = Column(Text,     default="")
    voice_distinction_score= Column(Float,    default=0.0)
    voice_markers          = Column(JSON,     default=list)
    plot_influence_score   = Column(Float,    default=0.0)
    consistency_score      = Column(Float,    default=0.0)
    consistency_issues     = Column(JSON,     default=list)
    memory_timeline        = Column(JSON,     default=list)
    confidence             = Column(Float,    default=0.0)
    author_overrides       = Column(JSON,     default=dict)
    is_stale               = Column(Boolean,  default=False)
    input_hash             = Column(String,   default="")
    generated_at           = Column(DateTime, default=datetime.utcnow)

    character = relationship("Character", back_populates="intelligence")
    story     = relationship("Story",     back_populates="character_intelligence")


# ── V2: Relationship Intelligence ──────────────────────────────────────────────

class RelationshipIntelligence(Base):
    """Deep per-relationship evolution and dynamics analysis (Pass P24)."""
    __tablename__ = "relationship_intelligence"
    intel_id             = Column(String,   primary_key=True, default=gen_uuid)
    relationship_id      = Column(String,   ForeignKey("character_relationships.relationship_id"), nullable=False, unique=True)
    story_id             = Column(String,   ForeignKey("stories.story_id"),         nullable=False)
    from_character_id    = Column(String,   ForeignKey("characters.character_id"),  nullable=False)
    to_character_id      = Column(String,   ForeignKey("characters.character_id"),  nullable=False)
    evolution_trajectory = Column(Text,     default="")
    turning_points       = Column(JSON,     default=list)
    tension_score        = Column(Float,    default=0.0)
    trust_score          = Column(Float,    default=0.0)
    conflict_score       = Column(Float,    default=0.0)
    dependency_score     = Column(Float,    default=0.0)
    is_hidden            = Column(Boolean,  default=False)
    hidden_reason        = Column(Text,     default="")
    impact_on_plot       = Column(Text,     default="")
    history              = Column(JSON,     default=list)
    confidence           = Column(Float,    default=0.0)
    author_overrides     = Column(JSON,     default=dict)
    is_stale             = Column(Boolean,  default=False)
    input_hash           = Column(String,   default="")
    generated_at         = Column(DateTime, default=datetime.utcnow)

    char_relationship = relationship("CharacterRelationship", back_populates="intelligence")
    story             = relationship("Story",     back_populates="relationship_intelligence")
    from_character    = relationship("Character", foreign_keys=[from_character_id])
    to_character      = relationship("Character", foreign_keys=[to_character_id])


# ── V2: Story Memory System ────────────────────────────────────────────────────

class StoryMemoryEntry(Base):
    """
    Universal knowledge bus — every intelligence pass writes here; every AI
    assistance feature (Plot Assistant, enrichment, transforms) reads via
    BGE-M3 semantic search.

    memory_key is UNIQUE per story to allow upsert semantics:
      INSERT … ON CONFLICT (story_id, memory_key) DO UPDATE SET …
    """
    __tablename__ = "story_memory_entries"
    entry_id                = Column(String,   primary_key=True, default=gen_uuid)
    story_id                = Column(String,   ForeignKey("stories.story_id"), nullable=False)
    memory_type             = Column(String,   nullable=False)
    # character|relationship|plot|world|theme|conflict|timeline
    memory_key              = Column(String,   nullable=False)
    entity_type             = Column(String,   default="")
    entity_id               = Column(String,   default="")
    content                 = Column(Text,     nullable=False)
    chapter_first_established= Column(Integer, nullable=True)
    chapter_last_updated    = Column(Integer,  nullable=True)
    importance              = Column(Float,    default=0.5)
    is_active               = Column(Boolean,  default=True)
    embedding               = Column(Vector(1024), nullable=True)
    is_ai_generated         = Column(Boolean,  default=True)
    is_author_added         = Column(Boolean,  default=False)
    created_at              = Column(DateTime, default=datetime.utcnow)
    updated_at              = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("story_id", "memory_key", name="uq_story_memory_key"),
    )

    story = relationship("Story", back_populates="memory_entries")


# ── V2: Timeline Intelligence ──────────────────────────────────────────────────

class StoryTimeline(Base):
    """Story-level temporal structure summary (Pass P26)."""
    __tablename__ = "story_timeline"
    timeline_id              = Column(String,   primary_key=True, default=gen_uuid)
    story_id                 = Column(String,   ForeignKey("stories.story_id"), nullable=False, unique=True)
    timeline_type            = Column(String,   default="linear")
    estimated_story_duration = Column(String,   default="")
    start_period             = Column(String,   default="")
    end_period               = Column(String,   default="")
    seasons_mentioned        = Column(JSON,     default=list)
    significant_time_gaps    = Column(JSON,     default=list)
    character_age_map        = Column(JSON,     default=dict)
    contradictions           = Column(JSON,     default=list)
    contradictions_detected  = Column(Integer,  default=0)
    confidence               = Column(Float,    default=0.0)
    is_stale                 = Column(Boolean,  default=False)
    input_hash               = Column(String,   default="")
    generated_at             = Column(DateTime, default=datetime.utcnow)

    story  = relationship("Story",  back_populates="timeline")
    events = relationship("StoryTimelineEvent", back_populates="timeline", cascade="all, delete-orphan")


class StoryTimelineEvent(Base):
    """Individual temporal event extracted from a chapter (Pass P26)."""
    __tablename__ = "story_timeline_events"
    event_id              = Column(String,   primary_key=True, default=gen_uuid)
    story_id              = Column(String,   ForeignKey("stories.story_id"), nullable=False)
    timeline_id           = Column(String,   ForeignKey("story_timeline.timeline_id"), nullable=True)
    chapter_id            = Column(String,   ForeignKey("chapters.chapter_id"), nullable=True)
    chapter_number        = Column(Integer,  nullable=False)
    event_type            = Column(String,   default="action")
    story_date            = Column(String,   default="")
    temporal_marker       = Column(String,   default="")
    characters_involved   = Column(JSON,     default=list)
    location              = Column(String,   default="")
    event_description     = Column(Text,     default="")
    is_flashback          = Column(Boolean,  default=False)
    is_flashforward       = Column(Boolean,  default=False)
    flash_origin_chapter  = Column(Integer,  nullable=True)
    is_stale              = Column(Boolean,  default=False)
    generated_at          = Column(DateTime, default=datetime.utcnow)

    story    = relationship("Story",         back_populates="timeline_events")
    timeline = relationship("StoryTimeline", back_populates="events")


# ── V2: Story Graph ────────────────────────────────────────────────────────────

class StoryGraphNode(Base):
    """PostgreSQL adjacency-list node — entity in the story knowledge graph (P28)."""
    __tablename__ = "story_graph_nodes"
    node_id            = Column(String,   primary_key=True, default=gen_uuid)
    story_id           = Column(String,   ForeignKey("stories.story_id"), nullable=False)
    node_type          = Column(String,   nullable=False)
    # story|chapter|character|location|object|event|theme|conflict|promise
    label              = Column(String,   nullable=False)
    entity_id          = Column(String,   default="")
    properties         = Column(JSON,     default=dict)
    embedding          = Column(Vector(1024), nullable=True)
    chapter_introduced = Column(Integer,  nullable=True)
    is_active          = Column(Boolean,  default=True)
    created_at         = Column(DateTime, default=datetime.utcnow)

    story         = relationship("Story", back_populates="graph_nodes")
    outgoing_edges= relationship("StoryGraphEdge", foreign_keys="StoryGraphEdge.from_node_id",
                                 back_populates="from_node", cascade="all, delete-orphan")
    incoming_edges= relationship("StoryGraphEdge", foreign_keys="StoryGraphEdge.to_node_id",
                                 back_populates="to_node")


class StoryGraphEdge(Base):
    """Directed edge in the story knowledge graph (P28)."""
    __tablename__ = "story_graph_edges"
    edge_id             = Column(String,   primary_key=True, default=gen_uuid)
    story_id            = Column(String,   ForeignKey("stories.story_id"),       nullable=False)
    from_node_id        = Column(String,   ForeignKey("story_graph_nodes.node_id"), nullable=False)
    to_node_id          = Column(String,   ForeignKey("story_graph_nodes.node_id"), nullable=False)
    edge_type           = Column(String,   nullable=False)
    weight              = Column(Float,    default=1.0)
    label               = Column(String,   default="")
    chapter_established = Column(Integer,  nullable=True)
    properties          = Column(JSON,     default=dict)
    is_active           = Column(Boolean,  default=True)
    created_at          = Column(DateTime, default=datetime.utcnow)

    story     = relationship("Story",          back_populates="graph_edges")
    from_node = relationship("StoryGraphNode", foreign_keys=[from_node_id], back_populates="outgoing_edges")
    to_node   = relationship("StoryGraphNode", foreign_keys=[to_node_id],   back_populates="incoming_edges")


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 2 Tables
# ═══════════════════════════════════════════════════════════════════════════════

class StoryBible(Base):
    """Generated story bible — structured reference document for the manuscript."""
    __tablename__ = "story_bibles"
    bible_id     = Column(String,   primary_key=True, default=gen_uuid)
    story_id     = Column(String,   ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=False)
    user_id      = Column(String,   ForeignKey("users.user_id"),    nullable=False)
    title        = Column(String,   default="Story Bible")
    content_json = Column(Text,     nullable=False, default="{}")
    version      = Column(Integer,  default=1)
    created_at   = Column(DateTime, default=datetime.utcnow)
    updated_at   = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    story = relationship("Story", back_populates="story_bibles")


class NarrativeThread(Base):
    """Tracks a named narrative thread (subplot, arc, mystery) across chapters."""
    __tablename__ = "narrative_threads"
    thread_id           = Column(String,   primary_key=True, default=gen_uuid)
    story_id            = Column(String,   ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=False)
    user_id             = Column(String,   ForeignKey("users.user_id"),    nullable=False)
    name                = Column(String,   nullable=False)
    description         = Column(Text,     default="")
    introduced_chapter  = Column(Integer,  nullable=True)
    resolved_chapter    = Column(Integer,  nullable=True)
    last_seen_chapter   = Column(Integer,  nullable=True)
    status              = Column(String,   default="open")  # open|resolved|dead_end
    created_at          = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    story = relationship("Story", back_populates="narrative_threads")


class PacingGoal(Base):
    """Per-story word count and chapter pacing targets — one row per story."""
    __tablename__ = "pacing_goals"
    goal_id                  = Column(String,   primary_key=True, default=gen_uuid)
    story_id                 = Column(String,   ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=False, unique=True)
    user_id                  = Column(String,   ForeignKey("users.user_id"),    nullable=False)
    target_word_count        = Column(Integer,  default=0)
    target_chapter_count     = Column(Integer,  default=0)
    target_words_per_chapter = Column(Integer,  default=0)
    current_streak_days      = Column(Integer,  default=0)
    created_at               = Column(DateTime, default=datetime.utcnow)
    updated_at               = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    story = relationship("Story", back_populates="pacing_goal")


class AudioUpload(Base):
    """Audio recording + Whisper transcription result for the Notes audio workflow."""
    __tablename__ = "audio_uploads"
    audio_id          = Column(String,    primary_key=True, default=gen_uuid)
    story_id          = Column(String,    ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=False)
    user_id           = Column(String,    ForeignKey("users.user_id"),    nullable=False)
    note_id           = Column(String,    ForeignKey("story_notes.note_id", ondelete="SET NULL"), nullable=True)
    audio_path        = Column(Text,      nullable=True)
    raw_transcript    = Column(Text,      default="")
    cleaned_text      = Column(Text,      default="")
    language_detected = Column(String(10), default="")
    duration_seconds  = Column(Float,     default=0.0)
    confidence        = Column(Float,     default=0.0)
    word_count        = Column(Integer,   default=0)
    status            = Column(String,    default="processing")  # processing|completed|failed
    confirmed         = Column(Boolean,   default=False)
    created_at        = Column(DateTime,  default=datetime.utcnow)
    updated_at        = Column(DateTime,  default=datetime.utcnow, onupdate=datetime.utcnow)

    story = relationship("Story", back_populates="audio_uploads")
