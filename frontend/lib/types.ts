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
  character_id: string
  story_id:     string
  name:         string
  aliases:      string[]
  role:         CharacterRole
  status:       CharacterStatus
  created_at:   string
  updated_at:   string
  profile:      CharacterProfile | null
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
