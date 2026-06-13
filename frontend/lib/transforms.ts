// Shared AI text-transform configuration — the SINGLE source of truth for every
// selection-based transform option in the app. Powers the Selection Toolbar AND the
// AI Sidecar (AIToolsSidebar) so options are never duplicated. Values mirror the
// real Phase 1/Phase 2 ai_transform endpoints (refine/tone/emotion/age-adapt/style/
// translate). Selection transforms go ONLY through these endpoints — never RAG,
// plot assistant, story Q&A, or chapter summaries.

import { Wand2, Palette, Heart, Users, Type, Globe, type LucideIcon } from 'lucide-react'
import api from './api'

export interface Opt { id: string; label: string; emoji?: string; desc?: string; age?: string }

// Refine modes (TransformRequest.mode) — value sent verbatim.
export const REFINE_MODES: Opt[] = [
  { id: 'standard', label: 'Standard', desc: 'Grammar + clarity' },
  { id: 'literary', label: 'Literary', desc: 'Elevated prose' },
  { id: 'grammar',  label: 'Grammar',  desc: 'Errors only' },
  { id: 'dialogue', label: 'Dialogue', desc: 'Speech patterns' },
]

// Tones (ToneRequest.tone) — id is the display label; sent lowercased.
export const TONES: Opt[] = [
  { id: 'Dark', label: 'Dark', emoji: '🌑' },
  { id: 'Suspenseful', label: 'Suspenseful', emoji: '⚡' },
  { id: 'Romantic', label: 'Romantic', emoji: '🌹' },
  { id: 'Humorous', label: 'Humorous', emoji: '😄' },
  { id: 'Epic', label: 'Epic', emoji: '⚔️' },
  { id: 'Melancholic', label: 'Melancholic', emoji: '🌧️' },
  { id: 'Hopeful', label: 'Hopeful', emoji: '🌤️' },
  { id: 'Tense', label: 'Tense', emoji: '🔥' },
  { id: 'Lyrical', label: 'Lyrical', emoji: '🎵' },
]

// Emotions (EmotionRequest.emotion) — backend supports all 7; sent lowercased.
export const EMOTIONS: Opt[] = [
  { id: 'Joy', label: 'Joy', emoji: '✨' },
  { id: 'Sadness', label: 'Sadness', emoji: '💧' },
  { id: 'Fear', label: 'Fear', emoji: '😰' },
  { id: 'Anger', label: 'Anger', emoji: '💢' },
  { id: 'Surprise', label: 'Surprise', emoji: '⚡' },
  { id: 'Disgust', label: 'Disgust', emoji: '🤢' },
  { id: 'Anticipation', label: 'Anticipation', emoji: '🎯' },
]
export const INTENSITIES = ['low', 'medium', 'high'] as const

// Audience / age (AgeAdaptRequest.target_age) — value sent verbatim.
export const AUDIENCES: Opt[] = [
  { id: 'children', label: 'Children', age: '5–10', desc: 'Simple words, short sentences' },
  { id: 'ya',       label: 'Young Adult', age: '10–18', desc: 'Age-appropriate complexity' },
  { id: 'adult',    label: 'Adult', age: '18+', desc: 'Full literary complexity' },
]

// Styles (StyleRequest.style) — sent lowercased.
export const STYLES: Opt[] = [
  { id: 'Gothic', label: 'Gothic', desc: 'Dark, ornate, brooding' },
  { id: 'Noir', label: 'Noir', desc: 'Hard-boiled, cynical' },
  { id: 'Contemporary', label: 'Contemporary', desc: 'Modern, accessible' },
  { id: 'Minimalist', label: 'Minimalist', desc: 'Spare, precise' },
  { id: 'Lyrical', label: 'Lyrical', desc: 'Musical, poetic' },
  { id: 'Pulp', label: 'Pulp', desc: 'Fast, visceral' },
  { id: 'Literary', label: 'Literary', desc: 'Layered, introspective' },
  { id: 'Thriller', label: 'Thriller', desc: 'Taut, relentless' },
]

// Languages (TranslationRequest.target_language) — value sent verbatim.
export const LANGUAGES: string[] = [
  'French', 'Spanish', 'German', 'Italian', 'Portuguese', 'Japanese', 'Korean',
  'Chinese (Simplified)', 'Russian', 'Arabic', 'Hindi', 'Tamil', 'Dutch', 'Polish',
]

export type GroupId = 'refine' | 'tone' | 'emotion' | 'age_adapt' | 'style' | 'translate'

export interface TransformGroup { id: GroupId; label: string; icon: LucideIcon; options: Opt[] }

// The groups the compact Selection Toolbar exposes (each a dropdown).
export const TRANSFORM_GROUPS: TransformGroup[] = [
  { id: 'refine', label: 'Refine', icon: Wand2, options: REFINE_MODES },
  { id: 'tone', label: 'Tone', icon: Palette, options: TONES },
  { id: 'emotion', label: 'Emotion', icon: Heart, options: EMOTIONS },
  { id: 'age_adapt', label: 'Audience', icon: Users, options: AUDIENCES },
  { id: 'style', label: 'Style', icon: Type, options: STYLES },
  { id: 'translate', label: 'Translate', icon: Globe, options: LANGUAGES.map((l) => ({ id: l, label: l })) },
]

export interface TransformOpts { storyId?: string; chapterId?: string; intensity?: string }

// Pure descriptor of the HTTP call for a transform — used by runTransform AND by
// tests to assert correct routing + that the SELECTED TEXT is what gets sent.
export function buildTransformCall(group: GroupId, value: string, text: string, opts: TransformOpts = {}) {
  const { storyId, chapterId, intensity = 'medium' } = opts
  switch (group) {
    case 'refine':    return { path: '/api/ai/refine', body: { text, mode: value, story_id: storyId, chapter_id: chapterId } }
    case 'tone':      return { path: '/api/ai/tone', body: { text, tone: value.toLowerCase(), story_id: storyId } }
    case 'emotion':   return { path: '/api/ai/emotion', body: { text, emotion: value.toLowerCase(), intensity, story_id: storyId } }
    case 'age_adapt': return { path: '/api/ai/age-adapt', body: { text, target_age: value, story_id: storyId } }
    case 'style':     return { path: '/api/ai/style', body: { text, style: value.toLowerCase(), story_id: storyId } }
    case 'translate': return { path: '/api/ai/translate', body: { text, target_language: value, story_id: storyId } }
  }
}

// Run a transform on EXACTLY the given (selected) text → returns the rewritten prose.
export async function runTransform(group: GroupId, value: string, text: string, opts: TransformOpts = {}): Promise<string> {
  const call = buildTransformCall(group, value, text, opts)
  const res = await api.post(call.path, call.body)
  return res.data.transformed as string
}
