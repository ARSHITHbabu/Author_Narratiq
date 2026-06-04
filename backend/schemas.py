from pydantic import BaseModel, EmailStr
from typing import Optional, List, Any
from datetime import datetime


# ── Auth ──────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    email: EmailStr
    username: str
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    user_id: str
    email: str
    username: str
    created_at: datetime
    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserOut


# ── Stories ───────────────────────────────────────────────────────────────────

class StoryCreate(BaseModel):
    title: str
    description: Optional[str] = ""


class StoryUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


class StoryOut(BaseModel):
    story_id: str
    user_id: str
    title: str
    description: str
    word_count: int
    status: str
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


# ── Chapters ──────────────────────────────────────────────────────────────────

class ChapterCreate(BaseModel):
    title: str
    content: Optional[str] = ""


class ChapterUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None


class ChapterOut(BaseModel):
    chapter_id: str
    story_id: str
    chapter_number: int
    title: str
    word_count: int
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class ChapterWithContent(ChapterOut):
    content: str


# ── Versions ──────────────────────────────────────────────────────────────────

class VersionOut(BaseModel):
    version_id: str
    chapter_id: str
    version_number: int
    label: str
    created_at: datetime
    model_config = {"from_attributes": True}


class VersionWithContent(VersionOut):
    content: str


# ── Story Intake / Genre ───────────────────────────────────────────────────────

class IntakeRequest(BaseModel):
    description: str
    audience_hint: Optional[str] = None
    language: Optional[str] = "en"


class GenreProfile(BaseModel):
    genre: str
    sub_genre: str
    tone: List[str]
    audience: str
    structure: str
    conflict: str
    themes: List[str]
    writing_direction: Optional[str] = None
    confidence: float


class IntakeResponse(BaseModel):
    intake_id: str
    genre_profile: GenreProfile
    model: str


class IntakeConfirm(BaseModel):
    intake_id: str
    overrides: Optional[dict] = {}


# ── Plot Assistant ─────────────────────────────────────────────────────────────

class PlotSuggestion(BaseModel):
    id: int
    text: str
    rationale: str


class PlotAssistantRequest(BaseModel):
    story_id: str
    question: str
    current_chapter_text: Optional[str] = ""
    template: Optional[str] = None


class PlotAssistantResponse(BaseModel):
    session_id: str
    mode: str = "creative"   # "qa" | "creative" | "mixed"
    answer: Optional[str] = None   # present for "qa" and "mixed" modes
    suggestions: List[PlotSuggestion] = []   # present for "suggestions" and "mixed"
    context_used: str
    tokens_used: int


# ── AI Transform ──────────────────────────────────────────────────────────────

class TransformRequest(BaseModel):
    story_id: Optional[str] = None
    chapter_id: Optional[str] = None
    text: str
    mode: Optional[str] = "standard"


class ToneRequest(BaseModel):
    story_id: Optional[str] = None
    chapter_id: Optional[str] = None
    text: str
    tone: str  # dark, suspenseful, romantic, humorous, etc.


class EmotionRequest(BaseModel):
    text: str
    emotion: str  # joy, sadness, fear, anger, surprise, disgust, anticipation
    intensity: Optional[str] = "medium"  # low, medium, high


class AgeAdaptRequest(BaseModel):
    story_id: Optional[str] = None
    text: str
    target_age: str  # children (5-10), ya (10-18), adult


class StyleRequest(BaseModel):
    text: str
    style: str  # gothic, noir, contemporary, etc.


class TranslationRequest(BaseModel):
    story_id: Optional[str] = None
    text: str
    target_language: str
    source_language: Optional[str] = "en"


class TransformResponse(BaseModel):
    original: str
    transformed: str
    mode: str
    tokens_used: int


# ── OCR ───────────────────────────────────────────────────────────────────────

class OcrExtractResponse(BaseModel):
    upload_id: str
    raw_text: str
    cleaned_text: str
    note_type: str
    confidence: float
    ocr_engine: str


class OcrConfirm(BaseModel):
    upload_id: str
    final_text: str
    destination: str  # story_notes | chapter_draft | character_profile | note_card


# ── Manuscript ────────────────────────────────────────────────────────────────

class ManuscriptUploadResponse(BaseModel):
    job_id: str
    story_id: str
    chapter_count: int
    estimated_minutes: int
    status: str


class JobStatus(BaseModel):
    job_id: str
    status: str  # pending | processing | complete | error
    stage: str
    percent: int
    message: str


# ── AI Suggestions ─────────────────────────────────────────────────────────────

class SuggestionRequest(BaseModel):
    story_id: str
    chapter_id: str
    text: str


class Suggestion(BaseModel):
    id: int
    category: str
    text: str
    reason: str


class SuggestionsResponse(BaseModel):
    suggestions: List[Suggestion]
    tokens_used: int


# ── Export ────────────────────────────────────────────────────────────────────

class ExportRequest(BaseModel):
    story_id: str
    format: str  # docx | pdf
    include_chapter_numbers: Optional[bool] = True
    font_size: Optional[int] = 12
