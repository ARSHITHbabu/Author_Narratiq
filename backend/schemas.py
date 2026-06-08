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
    # Richer Story Intelligence quick-analysis fields (optional, backwards-compatible)
    secondary_genres:   List[str] = []
    comparable_titles:  List[str] = []
    marketing_category: Optional[str] = None
    emotional_arc:      Optional[str] = None
    narrative_pov:      Optional[str] = None
    pacing:             Optional[str] = None
    content_warnings:   List[str] = []
    intelligence_notes: Optional[str] = None


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
    # Rich profile fields extracted from chapter evidence (may be "" / [] if not established)
    age:                   str = ""
    appearance:            str = ""
    personality:           str = ""
    goals:                 str = ""
    motivations:           str = ""
    backstory:             str = ""
    arc_notes:             str = ""
    traits:                List[str] = []
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
    # Rich profile fields carried through from the suggestion so the saved
    # CharacterProfile is populated, not empty. All optional / default-empty.
    age:              str = ""
    appearance:       str = ""
    personality:      str = ""
    goals:            str = ""
    motivations:      str = ""
    backstory:        str = ""
    arc_notes:        str = ""
    traits:           List[str] = []


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


# ── Character Arc Timeline ────────────────────────────────────────────────────

class CharacterArcSnapshotOut(BaseModel):
    arc_snapshot_id:  str
    chapter_id:       str
    chapter_number:   int
    role_in_chapter:  str   # major_player | observer | turning_point | brief_mention
    emotional_state:  str
    key_action:       str
    development_note: str
    status_change:    Optional[str]
    mention_count:    int
    is_stale:         bool
    generated_at:     datetime
    model_config = {"from_attributes": True}


class CharacterArcTimelineResponse(BaseModel):
    character_id:           str
    character_name:         str
    total_chapters:         int
    chapters_with_presence: int
    snapshots:              List[CharacterArcSnapshotOut]
    analysis_note:          str


# ── Export ────────────────────────────────────────────────────────────────────

class ExportRequest(BaseModel):
    story_id: str
    format: str  # docx | pdf
    include_chapter_numbers: Optional[bool] = True
    font_size: Optional[int] = 12


# ═══════════════════════════════════════════════════════════════════════════════
# Story Intelligence System Schemas
# ═══════════════════════════════════════════════════════════════════════════════

# ── Job control ───────────────────────────────────────────────────────────────

class IntelJobTriggerRequest(BaseModel):
    passes: Optional[List[str]] = None  # None = all passes
    force_refresh: Optional[bool] = False


class IntelJobOut(BaseModel):
    model_config = {"from_attributes": True}
    job_id:           str
    story_id:         str
    status:           str
    triggered_by:     str
    passes_requested: Optional[List[Any]] = []
    passes_completed: Optional[List[Any]] = []
    passes_failed:    Optional[List[Any]] = []
    current_pass:     Optional[str] = ""
    percent:          Optional[int] = 0
    error_message:    Optional[str] = ""
    created_at:       Optional[datetime] = None
    updated_at:       Optional[datetime] = None


# ── Genre Hierarchy ───────────────────────────────────────────────────────────

class StoryGenreHierarchyOut(BaseModel):
    model_config = {"from_attributes": True}
    genre_id:                 str
    story_id:                 str
    primary_genre:            Optional[str] = ""
    primary_genre_confidence: Optional[float] = 0.0
    secondary_genres:         Optional[List[Any]] = []
    genre_blend_rationale:    Optional[str] = ""
    marketing_category:       Optional[str] = ""
    comparable_titles:        Optional[List[Any]] = []
    tone_markers:             Optional[List[Any]] = []
    author_overrides:         Optional[Any] = {}
    is_stale:                 Optional[bool] = False
    generated_at:             Optional[datetime] = None


# ── Story DNA ─────────────────────────────────────────────────────────────────

class StoryDNAOut(BaseModel):
    model_config = {"from_attributes": True}
    dna_id:                str
    story_id:              str
    premise:               Optional[str] = ""
    central_question:      Optional[str] = ""
    thematic_core:         Optional[str] = ""
    narrative_engine:      Optional[str] = ""
    story_promise:         Optional[str] = ""
    resolution_type:       Optional[str] = ""
    pov_style:             Optional[str] = ""
    tense:                 Optional[str] = ""
    sentence_rhythm:       Optional[str] = ""
    vocabulary_tier:       Optional[str] = ""
    prose_style:           Optional[str] = ""
    structural_complexity: Optional[str] = ""
    chapter_dna:           Optional[List[Any]] = []
    confidence:            Optional[float] = 0.0
    author_overrides:      Optional[Any] = {}
    is_stale:              Optional[bool] = False
    generated_at:          Optional[datetime] = None


# ── Audience Profile ──────────────────────────────────────────────────────────

class StoryAudienceProfileOut(BaseModel):
    model_config = {"from_attributes": True}
    audience_id:           str
    story_id:              str
    primary_audience:      Optional[str] = ""
    age_range:             Optional[str] = ""
    reading_level:         Optional[str] = ""
    content_warnings:      Optional[List[Any]] = []
    appeal_factors:        Optional[List[Any]] = []
    comparable_readership: Optional[List[Any]] = []
    marketing_hooks:       Optional[List[Any]] = []
    author_overrides:      Optional[Any] = {}
    is_stale:              Optional[bool] = False
    generated_at:          Optional[datetime] = None


# ── Themes ────────────────────────────────────────────────────────────────────

class StoryThemesOut(BaseModel):
    model_config = {"from_attributes": True}
    theme_id:          str
    story_id:          str
    primary_theme:     Optional[str] = ""
    theme_statement:   Optional[str] = ""
    secondary_themes:  Optional[List[Any]] = []
    motifs:            Optional[List[Any]] = []
    symbols:           Optional[List[Any]] = []
    thematic_arc:      Optional[str] = ""
    chapter_theme_map: Optional[Any] = {}
    author_overrides:  Optional[Any] = {}
    is_stale:          Optional[bool] = False
    generated_at:      Optional[datetime] = None


# ── Conflicts ─────────────────────────────────────────────────────────────────

class StoryConflictsOut(BaseModel):
    model_config = {"from_attributes": True}
    conflict_id:              str
    story_id:                 str
    primary_conflict:         Optional[str] = ""
    conflict_type:            Optional[str] = ""
    secondary_conflicts:      Optional[List[Any]] = []
    conflict_evolution:       Optional[List[Any]] = []
    unresolved_conflicts:     Optional[List[Any]] = []
    conflict_resolution_path: Optional[str] = ""
    chapter_conflict_map:     Optional[Any] = {}
    author_overrides:         Optional[Any] = {}
    is_stale:                 Optional[bool] = False
    generated_at:             Optional[datetime] = None


# ── World Profile ─────────────────────────────────────────────────────────────

class StoryWorldProfileOut(BaseModel):
    model_config = {"from_attributes": True}
    world_id:           str
    story_id:           str
    setting_type:       Optional[str] = ""
    primary_settings:   Optional[List[Any]] = []
    world_rules:        Optional[List[Any]] = []
    time_period:        Optional[str] = ""
    social_structure:   Optional[str] = ""
    technology_level:   Optional[str] = ""
    magic_system:       Optional[Any] = {}
    cultural_elements:  Optional[List[Any]] = []
    consistency_issues: Optional[List[Any]] = []
    author_overrides:   Optional[Any] = {}
    is_stale:           Optional[bool] = False
    generated_at:       Optional[datetime] = None


# ── Narrative Structure ───────────────────────────────────────────────────────

class StoryNarrativeStructureOut(BaseModel):
    model_config = {"from_attributes": True}
    structure_id:             str
    story_id:                 str
    structure_type:           Optional[str] = ""
    act_breakdown:            Optional[Any] = {}
    inciting_incident_chapter:Optional[int] = None
    midpoint_chapter:         Optional[int] = None
    climax_chapter:           Optional[int] = None
    resolution_chapter:       Optional[int] = None
    narrative_promises:       Optional[List[Any]] = []
    promises_kept:            Optional[List[Any]] = []
    promises_broken:          Optional[List[Any]] = []
    structural_issues:        Optional[List[Any]] = []
    author_overrides:         Optional[Any] = {}
    is_stale:                 Optional[bool] = False
    generated_at:             Optional[datetime] = None


# ── Emotional Arc ─────────────────────────────────────────────────────────────

class StoryEmotionalArcOut(BaseModel):
    model_config = {"from_attributes": True}
    arc_id:                    str
    story_id:                  str
    overall_arc_shape:         Optional[str] = ""
    opening_emotion:           Optional[str] = ""
    midpoint_emotion:          Optional[str] = ""
    climax_emotion:            Optional[str] = ""
    resolution_emotion:        Optional[str] = ""
    emotional_contrast_score:  Optional[float] = 0.0
    chapter_emotions:          Optional[List[Any]] = []
    dominant_emotions:         Optional[List[Any]] = []
    emotional_gaps:            Optional[List[Any]] = []
    author_overrides:          Optional[Any] = {}
    is_stale:                  Optional[bool] = False
    generated_at:              Optional[datetime] = None


# ── Pacing Map ────────────────────────────────────────────────────────────────

class StoryPacingMapOut(BaseModel):
    model_config = {"from_attributes": True}
    pacing_id:       str
    story_id:        str
    overall_pacing:  Optional[str] = ""
    act_structure:   Optional[Any] = {}
    chapter_pacing:  Optional[List[Any]] = []
    slow_zones:      Optional[List[Any]] = []
    tension_peaks:   Optional[List[Any]] = []
    pacing_score:    Optional[float] = 0.0
    pacing_issues:   Optional[List[Any]] = []
    author_overrides:Optional[Any] = {}
    is_stale:        Optional[bool] = False
    generated_at:    Optional[datetime] = None


# ── Strength Indicators ───────────────────────────────────────────────────────

class StoryStrengthIndicatorsOut(BaseModel):
    model_config = {"from_attributes": True}
    strength_id:            str
    story_id:               str
    overall_score:          Optional[float] = 0.0
    voice_score:            Optional[float] = 0.0
    originality_score:      Optional[float] = 0.0
    character_depth_score:  Optional[float] = 0.0
    plot_coherence_score:   Optional[float] = 0.0
    pacing_score:           Optional[float] = 0.0
    world_building_score:   Optional[float] = 0.0
    dialogue_quality_score: Optional[float] = 0.0
    strengths:              Optional[List[Any]] = []
    score_rationale:        Optional[Any] = {}
    author_overrides:       Optional[Any] = {}
    is_stale:               Optional[bool] = False
    generated_at:           Optional[datetime] = None


# ── Risk Register ─────────────────────────────────────────────────────────────

class StoryRiskRegisterOut(BaseModel):
    model_config = {"from_attributes": True}
    risk_id:                   str
    story_id:                  str
    plot_holes:                Optional[List[Any]] = []
    continuity_risks:          Optional[List[Any]] = []
    character_inconsistencies: Optional[List[Any]] = []
    pacing_risks:              Optional[List[Any]] = []
    tonal_shifts:              Optional[List[Any]] = []
    unresolved_threads:        Optional[List[Any]] = []
    risk_score:                Optional[float] = 0.0
    critical_issues:           Optional[List[Any]] = []
    author_overrides:          Optional[Any] = {}
    is_stale:                  Optional[bool] = False
    generated_at:              Optional[datetime] = None


# ── Foreshadowing Registry ────────────────────────────────────────────────────

class StoryForeshadowingRegistryOut(BaseModel):
    model_config = {"from_attributes": True}
    foreshadow_id:           str
    story_id:                str
    active_foreshadowings:   Optional[List[Any]] = []
    resolved_foreshadowings: Optional[List[Any]] = []
    orphaned_hints:          Optional[List[Any]] = []
    payoffs_without_setup:   Optional[List[Any]] = []
    is_stale:                Optional[bool] = False
    generated_at:            Optional[datetime] = None


# ── Continuity Risks ──────────────────────────────────────────────────────────

class StoryContinuityRisksOut(BaseModel):
    model_config = {"from_attributes": True}
    continuity_id:                str
    story_id:                     str
    character_continuity_issues:  Optional[List[Any]] = []
    world_continuity_issues:      Optional[List[Any]] = []
    timeline_continuity_issues:   Optional[List[Any]] = []
    object_continuity_issues:     Optional[List[Any]] = []
    chapter_continuity_map:       Optional[Any] = {}
    risk_score:                   Optional[float] = 0.0
    is_stale:                     Optional[bool] = False
    generated_at:                 Optional[datetime] = None


# ── Character Intelligence ────────────────────────────────────────────────────

class CharacterIntelligenceOut(BaseModel):
    model_config = {"from_attributes": True}
    intel_id:                str
    character_id:            str
    story_id:                str
    goals:                   Optional[List[Any]] = []
    motivations:             Optional[str] = ""
    internal_wounds:         Optional[str] = ""
    external_objectives:     Optional[List[Any]] = []
    secrets:                 Optional[List[Any]] = []
    fears:                   Optional[List[Any]] = []
    contradictions:          Optional[List[Any]] = []
    arc_stage:               Optional[str] = ""
    arc_stage_rationale:     Optional[str] = ""
    voice_distinction_score: Optional[float] = 0.0
    voice_markers:           Optional[List[Any]] = []
    plot_influence_score:    Optional[float] = 0.0
    consistency_score:       Optional[float] = 0.0
    consistency_issues:      Optional[List[Any]] = []
    memory_timeline:         Optional[List[Any]] = []
    confidence:              Optional[float] = 0.0
    author_overrides:        Optional[Any] = {}
    is_stale:                Optional[bool] = False
    generated_at:            Optional[datetime] = None


class CharacterIntelligenceOverrideRequest(BaseModel):
    author_overrides: Any


# ── Relationship Intelligence ─────────────────────────────────────────────────

class RelationshipIntelligenceOut(BaseModel):
    model_config = {"from_attributes": True}
    intel_id:             str
    relationship_id:      str
    story_id:             str
    from_character_id:    str
    to_character_id:      str
    evolution_trajectory: Optional[str] = ""
    turning_points:       Optional[List[Any]] = []
    tension_score:        Optional[float] = 0.0
    trust_score:          Optional[float] = 0.0
    conflict_score:       Optional[float] = 0.0
    dependency_score:     Optional[float] = 0.0
    is_hidden:            Optional[bool] = False
    hidden_reason:        Optional[str] = ""
    impact_on_plot:       Optional[str] = ""
    history:              Optional[List[Any]] = []
    confidence:           Optional[float] = 0.0
    author_overrides:     Optional[Any] = {}
    is_stale:             Optional[bool] = False
    generated_at:         Optional[datetime] = None


# ── Story Memory ──────────────────────────────────────────────────────────────

class StoryMemoryEntryOut(BaseModel):
    model_config = {"from_attributes": True}
    entry_id:                  str
    story_id:                  str
    memory_type:               str
    memory_key:                str
    entity_type:               Optional[str] = ""
    entity_id:                 Optional[str] = ""
    content:                   str
    chapter_first_established: Optional[int] = None
    chapter_last_updated:      Optional[int] = None
    importance:                Optional[float] = 0.5
    is_active:                 Optional[bool] = True
    is_ai_generated:           Optional[bool] = True
    is_author_added:           Optional[bool] = False
    created_at:                Optional[datetime] = None
    updated_at:                Optional[datetime] = None


class StoryMemorySearchRequest(BaseModel):
    query: str
    top_k: Optional[int] = 10
    memory_type: Optional[str] = None
    entity_type: Optional[str] = None


class StoryMemorySearchResult(BaseModel):
    entry: StoryMemoryEntryOut
    score: float


class AuthorMemoryAddRequest(BaseModel):
    memory_type: str
    memory_key:  str
    content:     str
    entity_type: Optional[str] = ""
    entity_id:   Optional[str] = ""
    importance:  Optional[float] = 0.5


# ── Timeline ──────────────────────────────────────────────────────────────────

class StoryTimelineOut(BaseModel):
    model_config = {"from_attributes": True}
    timeline_id:              str
    story_id:                 str
    timeline_type:            Optional[str] = "linear"
    estimated_story_duration: Optional[str] = ""
    start_period:             Optional[str] = ""
    end_period:               Optional[str] = ""
    seasons_mentioned:        Optional[List[Any]] = []
    significant_time_gaps:    Optional[List[Any]] = []
    character_age_map:        Optional[Any] = {}
    contradictions:           Optional[List[Any]] = []
    contradictions_detected:  Optional[int] = 0
    confidence:               Optional[float] = 0.0
    is_stale:                 Optional[bool] = False
    generated_at:             Optional[datetime] = None


class StoryTimelineEventOut(BaseModel):
    model_config = {"from_attributes": True}
    event_id:             str
    story_id:             str
    chapter_number:       int
    event_type:           Optional[str] = "action"
    story_date:           Optional[str] = ""
    temporal_marker:      Optional[str] = ""
    characters_involved:  Optional[List[Any]] = []
    location:             Optional[str] = ""
    event_description:    Optional[str] = ""
    is_flashback:         Optional[bool] = False
    is_flashforward:      Optional[bool] = False
    flash_origin_chapter: Optional[int] = None
    generated_at:         Optional[datetime] = None


# ── Story Graph ───────────────────────────────────────────────────────────────

class StoryGraphNodeOut(BaseModel):
    model_config = {"from_attributes": True}
    node_id:            str
    story_id:           str
    node_type:          str
    label:              str
    entity_id:          Optional[str] = ""
    properties:         Optional[Any] = {}
    chapter_introduced: Optional[int] = None
    is_active:          Optional[bool] = True
    created_at:         Optional[datetime] = None


class StoryGraphEdgeOut(BaseModel):
    model_config = {"from_attributes": True}
    edge_id:             str
    story_id:            str
    from_node_id:        str
    to_node_id:          str
    edge_type:           str
    weight:              Optional[float] = 1.0
    label:               Optional[str] = ""
    chapter_established: Optional[int] = None
    properties:          Optional[Any] = {}
    is_active:           Optional[bool] = True
    created_at:          Optional[datetime] = None


class StoryGraphResponse(BaseModel):
    nodes: List[StoryGraphNodeOut]
    edges: List[StoryGraphEdgeOut]
    node_count: int
    edge_count: int


# ── Intelligence Dashboard ────────────────────────────────────────────────────

class StoryIntelligenceDashboard(BaseModel):
    story_id:              str
    latest_job:            Optional[IntelJobOut] = None
    genre_hierarchy:       Optional[StoryGenreHierarchyOut] = None
    story_dna:             Optional[StoryDNAOut] = None
    audience_profile:      Optional[StoryAudienceProfileOut] = None
    themes:                Optional[StoryThemesOut] = None
    conflicts:             Optional[StoryConflictsOut] = None
    world_profile:         Optional[StoryWorldProfileOut] = None
    narrative_structure:   Optional[StoryNarrativeStructureOut] = None
    emotional_arc:         Optional[StoryEmotionalArcOut] = None
    pacing_map:            Optional[StoryPacingMapOut] = None
    strength_indicators:   Optional[StoryStrengthIndicatorsOut] = None
    risk_register:         Optional[StoryRiskRegisterOut] = None
    foreshadowing_registry:Optional[StoryForeshadowingRegistryOut] = None
    continuity_risks:      Optional[StoryContinuityRisksOut] = None
    timeline:              Optional[StoryTimelineOut] = None
    character_intel_count: int = 0
    relationship_intel_count: int = 0
    memory_entry_count:    int = 0
    graph_node_count:      int = 0
    graph_edge_count:      int = 0


# ── Author Overrides ──────────────────────────────────────────────────────────

class AuthorOverrideRequest(BaseModel):
    author_overrides: Any


class IntelVersionOut(BaseModel):
    model_config = {"from_attributes": True}
    version_id:     str
    story_id:       str
    version_number: int
    trigger:        Optional[str] = "manual"
    created_at:     Optional[datetime] = None
