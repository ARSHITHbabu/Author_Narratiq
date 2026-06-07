import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Text, Integer, Boolean, Float,
    ForeignKey, DateTime, JSON, UniqueConstraint
)
from sqlalchemy.orm import relationship
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
    embedding = Column(JSON, default=None)   # BGE-M3 dense vector (1024-dim list[float])
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

    A 200k-word novel → ~580 chunks → all searched in <100 ms by numpy cosine.
    """
    __tablename__ = "chapter_chunks"
    chunk_id       = Column(String,  primary_key=True, default=gen_uuid)
    chapter_id     = Column(String,  ForeignKey("chapters.chapter_id"), nullable=False)
    story_id       = Column(String,  ForeignKey("stories.story_id"),    nullable=False)
    chapter_number = Column(Integer, nullable=False)
    chunk_index    = Column(Integer, nullable=False)   # 0-based within chapter
    text           = Column(Text,    nullable=False)   # plain text, ~350 words
    word_count     = Column(Integer, default=0)
    embedding      = Column(JSON,    default=None)     # BGE-M3 dense vector (1024-dim)
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
    embedding         = Column(JSON, default=None)

    # BGE-M3 embedding of character's story mention passages (story-grounded retrieval).
    # NULL until first mention indexing + embedding task completes.
    mention_embedding = Column(JSON, default=None)

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
    embedding     = Column(JSON,     default=None)   # BGE-M3 1024-dim — NULL until first embed
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
    embedding     = Column(JSON,     default=None)   # BGE-M3 1024-dim — NULL until first embed
    created_at    = Column(DateTime, default=datetime.utcnow)
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    story = relationship("Story", back_populates="note_cards")
