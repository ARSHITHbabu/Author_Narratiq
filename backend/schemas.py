from pydantic import BaseModel, EmailStr, computed_field, field_validator
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
    current_chapter_number: Optional[int] = None
    template: Optional[str] = None


class PlotAssistantResponse(BaseModel):
    session_id: str
    mode: str = "creative"   # "qa" | "creative" | "mixed"
    answer: Optional[str] = None   # present for "qa" and "mixed" modes
    suggestions: List[PlotSuggestion] = []   # present for "suggestions" and "mixed"
    context_used: str
    tokens_used: int


# ── Plot Hole Detection ────────────────────────────────────────────────────────

class PlotHoleIssue(BaseModel):
    issue_id:    int
    type:        str          # character_inconsistency | location_inconsistency |
                              # timeline_inconsistency | unresolved_thread |
                              # continuity_break | character_disappearance
    severity:    str          # "high" | "medium" | "low"
    chapters:    List[int]    # chapter numbers where the evidence appears
    description: str
    suggestion:  str          # author-actionable resolution hint


class PlotHoleResponse(BaseModel):
    story_id:          str
    chapters_analyzed: int
    issues_found:      int
    issues:            List[PlotHoleIssue]
    analysis_note:     str    # e.g. "No issues detected." or cap/stale warning


# ── Manuscript Report ──────────────────────────────────────────────────────────

class CharacterArcEntry(BaseModel):
    name:         str
    appears_in:   List[int]   # chapter numbers, ascending — first=appears_in[0], last=appears_in[-1]
    arc_summary:  str
    completeness: str         # "complete" | "partial" | "unresolved"


class PacingAnalysis(BaseModel):
    slow_chapters:    List[int]   # low-event, low-tension chapters
    intense_chapters: List[int]   # high-event, high-tension chapters
    assessment:       str


class UnresolvedThread(BaseModel):
    description:   str
    introduced_in: int          # chapter where thread is first established
    chapters:      List[int]    # all chapters where thread appears (ascending)


class StrengthEntry(BaseModel):
    text:     str
    chapters: List[int]         # chapters that exhibit this strength


class ImprovementEntry(BaseModel):
    text:     str
    chapters: List[int]         # chapters that motivated this recommendation


class ManuscriptReport(BaseModel):
    story_id:           str
    chapters_analyzed:  int
    word_count_total:   int
    character_arcs:     List[CharacterArcEntry]
    pacing:             PacingAnalysis
    unresolved_threads: List[UnresolvedThread]
    strengths:          List[StrengthEntry]
    improvements:       List[ImprovementEntry]
    analysis_note:      str


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

class OcrSuggestion(BaseModel):
    original:   str    # token as OCR extracted it
    suggested:  str    # closest matching story term
    reason:     str    # human-readable explanation shown in UI
    confidence: float  # SequenceMatcher similarity ratio (0.0–1.0)


class OcrExtractResponse(BaseModel):
    upload_id: str
    raw_text: str
    cleaned_text: str
    note_type: str
    confidence: float   # word-validity quality score from GOT-OCR2.0 (0.0–1.0)
    ocr_engine: str
    lines_detected: int = 0          # always 0 for GOT-OCR2.0 (end-to-end model)
    suggestions: List[OcrSuggestion] = []  # optional story-context correction hints


class OcrConfirm(BaseModel):
    upload_id:      str
    final_text:     str
    destination:    str            # story_notes | chapter_draft | character_profile | note_card
    chapter_id:     Optional[str] = None   # required when destination == "chapter_draft"
    character_name: Optional[str] = None   # required when destination == "character_profile"


class OcrConfirmResponse(BaseModel):
    confirmed:   bool
    destination: str
    injected:    bool
    target_id:   Optional[str] = None   # ID of the created / updated entity


# ── Story Notes ───────────────────────────────────────────────────────────────

class StoryNoteCreate(BaseModel):
    title:   Optional[str] = ""
    content: str


class StoryNoteUpdate(BaseModel):
    title:   Optional[str] = None
    content: Optional[str] = None


class StoryNoteOut(BaseModel):
    note_id:       str
    story_id:      str
    title:         str
    content:       str
    ocr_upload_id: Optional[str] = None
    created_at:    datetime
    updated_at:    datetime
    model_config = {"from_attributes": True}


# ── Note Cards ────────────────────────────────────────────────────────────────

_VALID_CARD_TYPES = {"scene", "location", "theme", "character", "general"}


class NoteCardCreate(BaseModel):
    title:     Optional[str] = ""
    content:   str
    card_type: Optional[str] = "general"

    @field_validator("card_type")
    @classmethod
    def _validate_card_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _VALID_CARD_TYPES:
            raise ValueError(
                f"card_type must be one of: {', '.join(sorted(_VALID_CARD_TYPES))}"
            )
        return v


class NoteCardUpdate(BaseModel):
    title:     Optional[str] = None
    content:   Optional[str] = None
    card_type: Optional[str] = None

    @field_validator("card_type")
    @classmethod
    def _validate_card_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _VALID_CARD_TYPES:
            raise ValueError(
                f"card_type must be one of: {', '.join(sorted(_VALID_CARD_TYPES))}"
            )
        return v


class NoteCardOut(BaseModel):
    card_id:       str
    story_id:      str
    title:         str
    content:       str
    card_type:     str
    ocr_upload_id: Optional[str] = None
    created_at:    datetime
    updated_at:    datetime
    model_config = {"from_attributes": True}


# ── Characters ────────────────────────────────────────────────────────────────

class CharacterCreate(BaseModel):
    name:    str
    aliases: Optional[List[str]] = []
    role:    Optional[str] = "supporting"   # protagonist | antagonist | supporting | minor
    status:  Optional[str] = "active"       # active | deceased | unknown


class CharacterUpdate(BaseModel):
    name:    Optional[str] = None
    aliases: Optional[List[str]] = None
    role:    Optional[str] = None
    status:  Optional[str] = None


class CharacterProfileUpdate(BaseModel):
    age:         Optional[str]       = None
    appearance:  Optional[str]       = None
    personality: Optional[str]       = None
    motivations: Optional[str]       = None
    goals:       Optional[str]       = None   # None = no change; "" = clear
    backstory:   Optional[str]       = None
    arc_notes:   Optional[str]       = None
    raw_notes:   Optional[str]       = None
    traits:      Optional[List[str]] = None   # None = no change; [] = clear all


class CharacterProfileOut(BaseModel):
    profile_id:    str
    age:           str
    appearance:    str
    personality:   str
    motivations:   str
    goals:         str
    backstory:     str
    arc_notes:     str
    traits:        List[str]
    raw_notes:     str
    ocr_upload_id: Optional[str] = None
    created_at:    datetime
    updated_at:    datetime
    model_config = {"from_attributes": True}


class CharacterOut(BaseModel):
    character_id: str
    story_id:     str
    name:         str
    aliases:      List[str]
    role:         str
    status:       str
    created_at:   datetime
    updated_at:   datetime
    profile:      Optional[CharacterProfileOut] = None
    model_config = {"from_attributes": True}

    @computed_field
    @property
    def completeness_score(self) -> int:
        if not self.profile:
            return 0
        fields = [
            self.profile.age, self.profile.appearance, self.profile.personality,
            self.profile.goals, self.profile.motivations, self.profile.backstory,
            self.profile.arc_notes,
        ]
        return round(sum(1 for f in fields if f and str(f).strip()) / 7 * 100)


# ── Character Relationships ───────────────────────────────────────────────────

class RelationshipCreate(BaseModel):
    to_character_id:   str
    relationship_type: str   # ally|rival|family|romantic|mentor|enemy|neutral
    strength:          Optional[str]  = "moderate"  # weak|moderate|strong|critical
    description:       Optional[str]  = ""
    is_mutual:         Optional[bool] = False


class RelationshipUpdate(BaseModel):
    relationship_type: Optional[str]  = None
    strength:          Optional[str]  = None
    description:       Optional[str]  = None
    is_mutual:         Optional[bool] = None


class RelationshipOut(BaseModel):
    relationship_id:   str
    story_id:          str
    from_character_id: str
    to_character_id:   str
    relationship_type: str
    strength:          str
    description:       str
    is_mutual:         bool
    created_at:        datetime
    updated_at:        datetime
    model_config = {"from_attributes": True}


class CharacterGraphResponse(BaseModel):
    nodes: List[CharacterOut]
    edges: List[RelationshipOut]


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


# ── Search & Replace ──────────────────────────────────────────────────────────

class SearchMatchContext(BaseModel):
    context_before: str
    match_text: str
    context_after: str


class ChapterSearchResult(BaseModel):
    chapter_id: str
    chapter_number: int
    chapter_title: str
    match_count: int
    matches: List[SearchMatchContext]


class ExactSearchRequest(BaseModel):
    query: str
    case_sensitive: bool = False
    whole_word: bool = False
    chapter_ids: Optional[List[str]] = None


class ExactSearchResponse(BaseModel):
    query: str
    total_matches: int
    chapters_hit: int
    results: List[ChapterSearchResult]


class SemanticSearchRequest(BaseModel):
    query: str
    top_k: int = 8


class SemanticResult(BaseModel):
    chapter_id: str
    chapter_number: int
    chapter_title: str
    chunk_text: str
    score: float


class SemanticSearchResponse(BaseModel):
    query: str
    results: List[SemanticResult]


class ReplacePreviewItem(BaseModel):
    chapter_id: str
    chapter_number: int
    chapter_title: str
    match_count: int


class ReplaceRequest(BaseModel):
    query: str
    replacement: str
    case_sensitive: bool = False
    whole_word: bool = False
    chapter_ids: Optional[List[str]] = None   # None = all chapters
    occurrence_index: Optional[int] = None    # None = all, N = Nth only (Replace One)
    dry_run: bool = False


class ReplaceResponse(BaseModel):
    dry_run: bool
    replaced_count: int
    chapters_affected: int
    preview: List[ReplacePreviewItem]


# ── Cast Generation ───────────────────────────────────────────────────────────

class CastSuggestion(BaseModel):
    name:                  str
    role:                  str
    status:                str
    description:           str
    aliases:               List[str]
    first_appearance:      str
    evidence_snippet:      str
    confidence:            str          # "high" | "uncertain"
    already_exists:        bool = False
    existing_character_id: Optional[str] = None


class CastGenerationResult(BaseModel):
    story_id:         str
    suggestions:      List[CastSuggestion]
    chapters_scanned: int
    new_count:        int
    existing_count:   int


class CastConfirmItem(BaseModel):
    name:             str
    role:             str
    status:           str
    description:      str
    aliases:          List[str]
    evidence_snippet: str


class CastConfirmRequest(BaseModel):
    suggestions: List[CastConfirmItem]


class CastConfirmResult(BaseModel):
    created:          List[CharacterOut]
    skipped_existing: int


# ── Character Mentions ────────────────────────────────────────────────────────

class CharacterMentionOut(BaseModel):
    mention_id:       str
    character_id:     str
    chapter_id:       str
    chapter_number:   int
    passage_text:     str
    mention_type:     str
    co_character_ids: List[str]
    created_at:       datetime
    model_config = {"from_attributes": True}


# ── Character Hints ───────────────────────────────────────────────────────────

class CharacterHintOut(BaseModel):
    hint_id:         str
    story_id:        str
    chapter_id:      str
    chapter_number:  int
    suggested_name:  str
    context_snippet: str
    is_dismissed:    bool
    created_at:      datetime
    model_config = {"from_attributes": True}


# ── Character Enrichment ──────────────────────────────────────────────────────

class EnrichSuggestion(BaseModel):
    field:      str   # profile field name: appearance|personality|goals|motivations|backstory|arc_notes|traits
    value:      str   # suggested value
    evidence:   str   # story excerpt that supports this suggestion
    chapter:    int   # chapter number where evidence was found
    confidence: float # 0.0-1.0


class EnrichResult(BaseModel):
    character_id:      str
    suggestions:       List[EnrichSuggestion]
    mentions_analyzed: int
    chapters_covered:  List[int]


# ── Export ────────────────────────────────────────────────────────────────────

class ExportRequest(BaseModel):
    story_id: str
    format: str  # docx | pdf
    include_chapter_numbers: Optional[bool] = True
    font_size: Optional[int] = 12
