import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Text, Integer, Boolean, Float,
    ForeignKey, DateTime, JSON
)
from sqlalchemy.orm import relationship
from database import Base


def gen_uuid():
    return str(uuid.uuid4())


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
    model_version = Column(String, default="placeholder-v1")
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
    model_version = Column(String, default="placeholder-v1")
    generated_at = Column(DateTime, default=datetime.utcnow)
    is_stale = Column(Boolean, default=False)

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
    created_at     = Column(DateTime, default=datetime.utcnow)
