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
