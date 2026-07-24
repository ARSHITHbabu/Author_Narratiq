export interface User {
  user_id: string
  email: string
  username: string
  created_at: string
}

export interface Story {
  story_id: string
  user_id: string
  title: string
  description: string
  word_count: number
  status: string
  created_at: string
  updated_at: string
}

export interface Chapter {
  chapter_id: string
  story_id: string
  chapter_number: number
  title: string
  word_count: number
  created_at: string
  updated_at: string
  content?: string
}

export interface Version {
  version_id: string
  chapter_id: string
  version_number: number
  label: string
  created_at: string
  content?: string
}

export interface GenreProfile {
  genre: string
  sub_genre: string
  tone: string[]
  audience: string
  structure: string
  conflict: string
  themes: string[]
  writing_direction?: string
  confidence: number
  // Richer Story Intelligence quick-analysis fields (optional)
  secondary_genres?:   string[]
  comparable_titles?:  string[]
  marketing_category?: string | null
  emotional_arc?:      string | null
  narrative_pov?:      string | null
  pacing?:             string | null
  content_warnings?:   string[]
  intelligence_notes?: string | null
}

export interface IntakeResponse {
  intake_id: string
  genre_profile: GenreProfile
  model: string
}

// Saved Story Intake / Genre Detection report (GET /api/intake/:id/report).
export interface IntakeReport {
  exists: boolean
  confirmed: boolean
  intake_id?: string | null
  raw_description?: string
  genre_profile: GenreProfile | null
}

export interface PlotSuggestion {
  id: number
  text: string
  rationale: string
}

export interface PlotAssistantResponse {
  session_id: string
  mode: 'qa' | 'creative' | 'mixed'
  answer?: string
  suggestions: PlotSuggestion[]
  context_used: string
  tokens_used: number
}

export interface PlotHoleIssue {
  issue_id:    number
  type:        string
  severity:    'high' | 'medium' | 'low'
  chapters:    number[]
  description: string
  suggestion:  string
}

export interface PlotHoleResponse {
  story_id:          string
  chapters_analyzed: number
  issues_found:      number
  issues:            PlotHoleIssue[]
  analysis_note:     string
}

// ── Manuscript Report ─────────────────────────────────────────────────────────

export interface CharacterArcEntry {
  name:         string
  appears_in:   number[]   // ascending chapter numbers
  arc_summary:  string
  completeness: 'complete' | 'partial' | 'unresolved'
}

export interface PacingAnalysis {
  slow_chapters:    number[]
  intense_chapters: number[]
  assessment:       string
}

export interface UnresolvedThread {
  description:   string
  introduced_in: number     // chapter where thread is first established
  chapters:      number[]   // all chapters where thread appears
}

export interface StrengthEntry {
  text:     string
  chapters: number[]        // chapters that exhibit this strength
}

export interface ImprovementEntry {
  text:     string
  chapters: number[]        // chapters that motivated this recommendation
}

export interface ManuscriptReport {
  story_id:           string
  chapters_analyzed:  number
  word_count_total:   number
  character_arcs:     CharacterArcEntry[]
  pacing:             PacingAnalysis
  unresolved_threads: UnresolvedThread[]
  strengths:          StrengthEntry[]
  improvements:       ImprovementEntry[]
  analysis_note:      string
}

export interface TransformResponse {
  original: string
  transformed: string
  mode: string
  tokens_used: number
}

// ── Copyright / Plagiarism Risk Detection ──────────────────────────────────────
export type RiskLevel = 'low' | 'medium' | 'high'

export interface CopyrightRiskFinding {
  finding_id:          number
  risk_type:           string   // direct_text | plot | character | world_building | scene | style_imitation | trope_overuse
  risk_score:          RiskLevel
  description:         string
  problematic_excerpt: string
  is_generic_trope:    boolean
  rewrite_suggestion:  string
}

export interface CopyrightRiskResponse {
  story_id:       string
  scope:          'selection' | 'chapter' | 'project'
  units_analyzed: number
  overall_risk:   RiskLevel
  findings_count: number
  findings:       CopyrightRiskFinding[]
  note:           string
  disclaimer:     string
}

export interface AISuggestion {
  id: number
  category: string
  text: string
  reason: string
}

export interface OcrSuggestion {
  original: string    // OCR-extracted term
  suggested: string   // closest story match
  reason: string      // displayed to author
  confidence: number  // 0.0–1.0 similarity score
}

export interface OcrResult {
  upload_id: string
  raw_text: string
  cleaned_text: string
  note_type: string
  confidence: number
  ocr_engine: string
  lines_detected: number
  suggestions: OcrSuggestion[]
}

// ── Search & Replace ──────────────────────────────────────────────────────────

export interface SearchMatchContext {
  context_before: string
  match_text: string
  context_after: string
}

export interface ChapterSearchResult {
  chapter_id: string
  chapter_number: number
  chapter_title: string
  match_count: number
  matches: SearchMatchContext[]
}

export interface ExactSearchResponse {
  query: string
  total_matches: number
  chapters_hit: number
  results: ChapterSearchResult[]
}

export interface SemanticResult {
  chapter_id: string
  chapter_number: number
  chapter_title: string
  chunk_text: string
  score: number
}

export interface SemanticSearchResponse {
  query: string
  results: SemanticResult[]
}

export interface ReplacePreviewItem {
  chapter_id: string
  chapter_number: number
  chapter_title: string
  match_count: number
}

export interface ReplaceResponse {
  dry_run: boolean
  replaced_count: number
  chapters_affected: number
  preview: ReplacePreviewItem[]
}

export type ToneType =
  | 'dark' | 'suspenseful' | 'romantic' | 'humorous'
  | 'epic' | 'melancholic' | 'hopeful' | 'tense' | 'lyrical'

export type EmotionType =
  | 'joy' | 'sadness' | 'fear' | 'anger' | 'surprise' | 'anticipation'

export type AgeGroup = 'children' | 'ya' | 'adult'

// ── Story Notes & Note Cards ──────────────────────────────────────────────────

export interface StoryNote {
  note_id:       string
  story_id:      string
  title:         string
  content:       string
  ocr_upload_id: string | null
  created_at:    string
  updated_at:    string
}

export type NoteCardType = 'scene' | 'location' | 'theme' | 'character' | 'general'

export interface NoteCard {
  card_id:       string
  story_id:      string
  title:         string
  content:       string
  card_type:     NoteCardType
  ocr_upload_id: string | null
  created_at:    string
  updated_at:    string
}

// ── Characters ────────────────────────────────────────────────────────────────

export type CharacterRole   = 'protagonist' | 'antagonist' | 'supporting' | 'minor'
export type CharacterStatus = 'active' | 'deceased' | 'unknown'
export type RelationshipType = 'ally' | 'rival' | 'family' | 'romantic' | 'mentor' | 'enemy' | 'neutral'
export type RelationshipStrength = 'weak' | 'moderate' | 'strong' | 'critical'

export interface CharacterProfile {
  profile_id:    string
  age:           string
  appearance:    string
  personality:   string
  motivations:   string
  goals:         string
  backstory:     string
  arc_notes:     string
  traits:        string[]
  raw_notes:     string
  ocr_upload_id: string | null
  created_at:    string
  updated_at:    string
}

export interface Character {
  character_id:      string
  story_id:          string
  name:              string
  aliases:           string[]
  role:              CharacterRole
  status:            CharacterStatus
  created_at:        string
  updated_at:        string
  profile:           CharacterProfile | null
  completeness_score: number
}

export interface CharacterRelationship {
  relationship_id:   string
  story_id:          string
  from_character_id: string
  to_character_id:   string
  relationship_type: RelationshipType
  strength:          RelationshipStrength
  description:       string
  is_mutual:         boolean
  created_at:        string
  updated_at:        string
}

export interface CharacterGraph {
  nodes: Character[]
  edges: CharacterRelationship[]
}

// ── Cast Generation ───────────────────────────────────────────────────────────

export interface CastSuggestion {
  name:                  string
  role:                  CharacterRole
  status:                CharacterStatus
  description:           string
  aliases:               string[]
  first_appearance:      string
  evidence_snippet:      string
  confidence:            'high' | 'uncertain'
  // Rich profile fields extracted from chapter evidence (may be "" / [])
  age:                   string
  appearance:            string
  personality:           string
  goals:                 string
  motivations:           string
  backstory:             string
  arc_notes:             string
  traits:                string[]
  already_exists:        boolean
  existing_character_id: string | null
}

export interface CastGenerationResult {
  story_id:         string
  suggestions:      CastSuggestion[]
  chapters_scanned: number
  new_count:        number
  existing_count:   number
}

export interface CastConfirmResult {
  created:          Character[]
  skipped_existing: number
}

// ── Character Mentions ────────────────────────────────────────────────────────

export interface CharacterMention {
  mention_id:       string
  character_id:     string
  chapter_id:       string
  chapter_number:   number
  passage_text:     string
  mention_type:     string
  co_character_ids: string[]
  created_at:       string
}

// ── Character Hints ───────────────────────────────────────────────────────────

export interface CharacterHint {
  hint_id:         string
  story_id:        string
  chapter_id:      string
  chapter_number:  number
  suggested_name:  string
  context_snippet: string
  is_dismissed:    boolean
  created_at:      string
}

// ── Character Enrichment ──────────────────────────────────────────────────────

export type EnrichField = 'appearance' | 'personality' | 'goals' | 'motivations' | 'backstory' | 'arc_notes' | 'traits'

export interface EnrichSuggestion {
  field:      EnrichField
  value:      string
  evidence:   string
  chapter:    number
  confidence: number
}

export interface EnrichResult {
  character_id:      string
  suggestions:       EnrichSuggestion[]
  mentions_analyzed: number
  chapters_covered:  number[]
}

// ── Character Arc Timeline ─────────────────────────────────────────────────────

export type ArcRole = 'major_player' | 'observer' | 'turning_point' | 'brief_mention'

export interface CharacterArcSnapshot {
  arc_snapshot_id:  string
  chapter_id:       string
  chapter_number:   number
  role_in_chapter:  ArcRole
  emotional_state:  string
  key_action:       string
  development_note: string
  status_change:    string | null
  mention_count:    number
  is_stale:         boolean
  generated_at:     string
}

export interface CharacterArcTimelineResponse {
  character_id:           string
  character_name:         string
  total_chapters:         number
  chapters_with_presence: number
  snapshots:              CharacterArcSnapshot[]
  analysis_note:          string
}

// ── Phase 2 Types ─────────────────────────────────────────────────────────────

// P2-01 Emotional Arc Map
export interface EmotionalArcEntry {
  chapter_number: number
  chapter_title:  string
  emotional_tone: string | null
}

export interface EmotionalArcResponse {
  story_id:     string
  chapter_count: number
  arc:          EmotionalArcEntry[]
  assessment:   string | null
}

// P2-02 Chapter Continuation
export interface ContinuationSuggestion {
  direction: string
  text:      string
  rationale: string
}

export interface ContinuationResponse {
  story_id:    string
  chapter_id:  string
  suggestions: ContinuationSuggestion[]
}

// P2-03 Voice Check
export interface VoiceInconsistentPair {
  passage_a:        string
  passage_b:        string
  chapter_a:        number
  chapter_b:        number
  similarity_score: number
  description:      string
}

export interface VoiceCheckResponse {
  character_id:       string
  character_name:     string
  status:             string
  dialogue_count:     number
  consistency_score:  number | null
  inconsistent_pairs: VoiceInconsistentPair[]
}

// P2-04 Chapter Outline
export interface OutlineBeat {
  scene_number:       number
  beat_description:   string
  characters_present: string[]
  location:           string
  pacing_note:        string
}

// Field names mirror backend schemas.py OutlineResponse exactly. It returns
// `outline` (not `beats`) and no story_id — an earlier mismatch here meant the
// UI read res.data.beats, got undefined, and silently rendered nothing while
// the backend was returning a correct beat sheet.
export interface OutlineResponse {
  chapter_id: string
  outline:    OutlineBeat[]
}

// P2-05 Continuity Check
export interface ContinuityIssue {
  type:            string
  description:     string
  chapter_refs:    number[]
  severity:        'low' | 'medium' | 'high'
  resolution_hint: string
}

export interface ContinuityCheckResponse {
  story_id:         string
  issues_found:     number
  issues:           ContinuityIssue[]
  chapters_scanned: number
  note:             string
}

// P2-06 Story Bible
export interface StoryBibleOut {
  bible_id:     string
  story_id:     string
  content_json: string   // JSON string: {characters, locations, timeline, world_rules, themes}
  version:      number
  status:       'running' | 'completed' | 'failed'
  created_at:   string
  updated_at:   string
}

export interface StoryBibleJobResponse {
  job_id:    string
  status:    string
  bible_id:  string | null
}

// P2-07 Narrative Threads
export interface NarrativeThreadOut {
  thread_id:          string
  story_id:           string
  name:               string
  description:        string
  introduced_chapter: number | null
  last_seen_chapter:  number | null
  resolved_chapter:   number | null
  status:             'open' | 'dead_end' | 'resolved'
  created_at:         string
  updated_at:         string
}

export interface NarrativeScanResponse {
  job_id: string
  status: string
}

// P2-08 Style Drift
export interface StyleDriftResponse {
  story_id:       string
  status:         string
  drift_score:    number | null
  early_chapters: number[]
  late_chapters:  number[]
  description:    string
  sample_early:   string | null
  sample_late:    string | null
}

// P2-09 Pacing
export interface ChapterWordCount {
  chapter_number: number
  chapter_title:  string
  word_count:     number
}

export interface PacingGoalResponse {
  story_id:                   string
  target_word_count:          number
  target_chapter_count:       number
  target_words_per_chapter:   number
  actual_word_count:          number
  actual_chapter_count:       number
  avg_words_per_chapter:      number
  progress_pct:               number
  estimated_chapters_remaining: number
  chapter_distribution:       ChapterWordCount[]
  current_streak_days:        number
}

// P2-10 Duplicate Scenes
export interface DuplicatePair {
  chapter_a:        number
  chapter_b:        number
  a_title:          string
  b_title:          string
  similarity_score: number
  a_snippet:        string
  b_snippet:        string
}

export interface DuplicateScenesResponse {
  story_id:    string
  threshold:   number
  pairs_found: number
  pairs:       DuplicatePair[]
}

// P2-11 Audio
export interface AudioUploadOut {
  audio_id:         string
  story_id:         string
  note_id:          string | null
  status:           string
  raw_transcript:   string | null
  cleaned_text:     string | null
  language_detected: string | null
  duration_seconds:  number | null
  confidence:        number | null
  word_count:        number | null
  confirmed:         boolean
  created_at:        string | null
  updated_at:        string | null
}

export interface AudioTranscribeResponse {
  audio_id:         string
  status:           string
  duration_seconds: number | null
}

// ── Real-Time Voice Agent ─────────────────────────────────────────────────────
export type VoiceActionType =
  | 'read' | 'write' | 'generate' | 'analyze' | 'destructive' | 'export'

export type VoiceStatus =
  | 'success' | 'needs_confirmation' | 'needs_clarification' | 'failed'

export interface VoiceExecution {
  client_call: string | null     // logical key dispatched by lib/voiceActions.ts
  args:        Record<string, unknown>
  navigate:    string | null
}

export interface WorkflowNode {
  node_key:    string
  capability:  string
  action:      string
  action_type: VoiceActionType
  depends_on:  string[]
  execution_locus: 'server' | 'client'
  requires_confirmation: boolean
  status:      string
  execution:   VoiceExecution | null
  result:      Record<string, unknown> | null
  user_message: string
}

export interface VoiceWorkflow {
  workflow_id: string
  node_count:  number
  status:      string
  nodes:       WorkflowNode[]
}

export interface VoiceClarification {
  question: string
  missing:  string[]
  // author-facing choices: {label} for names, or {capability,description} for features
  options?: Array<Record<string, unknown>> | null
}

export interface VoiceResolvedEntity { name: string; kind: string }

export interface VoiceAgentResponse {
  session_id:           string
  command_id:           string
  transcript:           string
  cleaned_transcript:   string
  corrected_transcript: string
  resolved_entities:    VoiceResolvedEntity[]
  context_used:         string
  resolved_references:  Record<string, unknown>
  detected_intent:      string
  capability:           string
  target_router:        string
  action_type:          VoiceActionType | ''
  is_multi_step:        boolean
  confidence:           number
  requires_confirmation: boolean
  status:               VoiceStatus
  workflow:             VoiceWorkflow | null
  result:               Record<string, unknown>
  user_message:         string
  clarification:        VoiceClarification | null
  error:                string | null
}

export interface VoiceContextSnapshot {
  story_id?:            string | null
  chapter_id?:          string | null
  chapter_number?:      number | null
  chapter_title?:       string | null
  selected_text?:       string | null
  selected_text_range?: number[] | null
  has_selection?:       boolean
  cursor_position?:     number | null
  full_chapter_text?:   string | null
  active_panel?:        string | null
  active_character_id?: string | null
  word_count?:          number | null
}
