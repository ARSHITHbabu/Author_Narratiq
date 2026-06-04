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
  mode: 'qa' | 'suggestions' | 'mixed'
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

export interface OcrResult {
  upload_id: string
  raw_text: string
  cleaned_text: string
  note_type: string
  confidence: number
  ocr_engine: string
}

export type ToneType =
  | 'dark' | 'suspenseful' | 'romantic' | 'humorous'
  | 'epic' | 'melancholic' | 'hopeful' | 'tense' | 'lyrical'

export type EmotionType =
  | 'joy' | 'sadness' | 'fear' | 'anger' | 'surprise' | 'anticipation'

export type AgeGroup = 'children' | 'ya' | 'adult'
