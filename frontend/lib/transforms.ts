// Shared AI text-transform configuration — the SINGLE source of truth for every
// selection-based transform option in the app. Powers the Selection Toolbar AND the
// AI Sidecar (AIToolsSidebar) so options are never duplicated. Values mirror the
// real Phase 1/Phase 2 ai_transform endpoints (refine/tone/emotion/age-adapt/style/
// translate). Selection transforms go ONLY through these endpoints — never RAG,
// plot assistant, story Q&A, or chapter summaries.

import { Wand2, Palette, Heart, Users, Type, Globe, BookOpen, type LucideIcon } from 'lucide-react'
import api from './api'

export interface Opt { id: string; label: string; emoji?: string; desc?: string; age?: string }

// Author/style influences. `group` separates public-domain named authors from
// always-safe generic styles. The backend (ai_service._AUTHOR_STYLES) is the
// safety authority — these ids must match its catalog keys. Living/in-copyright
// authors are intentionally NOT offered as named imitation targets.
export interface AuthorOpt extends Opt { publicDomain: boolean; group: 'public_domain' | 'generic' }
export const AUTHOR_STYLES: AuthorOpt[] = [
  { id: 'shakespeare', label: 'William Shakespeare', desc: 'Elizabethan, dramatic, poetic', publicDomain: true, group: 'public_domain' },
  { id: 'austen',      label: 'Jane Austen',         desc: 'Witty, ironic, social',         publicDomain: true, group: 'public_domain' },
  { id: 'dickens',     label: 'Charles Dickens',     desc: 'Vivid, characterful, warm',     publicDomain: true, group: 'public_domain' },
  { id: 'poe',         label: 'Edgar Allan Poe',     desc: 'Gothic, intense, ornate',       publicDomain: true, group: 'public_domain' },
  { id: 'bronte',      label: 'The Brontës',         desc: 'Passionate, moody, Romantic',   publicDomain: true, group: 'public_domain' },
  { id: 'twain',       label: 'Mark Twain',          desc: 'Vernacular, dry, colloquial',   publicDomain: true, group: 'public_domain' },
  { id: 'generic_poetic',     label: 'Poetic',         desc: 'Lyrical, musical, imagery',   publicDomain: true, group: 'generic' },
  { id: 'generic_cinematic',  label: 'Cinematic',      desc: 'Visual, vivid, momentum',     publicDomain: true, group: 'generic' },
  { id: 'generic_literary',   label: 'Literary',       desc: 'Layered, introspective',      publicDomain: true, group: 'generic' },
  { id: 'generic_minimalist', label: 'Minimalist',     desc: 'Spare, understated',          publicDomain: true, group: 'generic' },
  { id: 'generic_stream',     label: 'Stream of consciousness', desc: 'Fluid interior voice', publicDomain: true, group: 'generic' },
  { id: 'generic_mystery',    label: 'Classic mystery', desc: 'Suspenseful, deductive',     publicDomain: true, group: 'generic' },
]

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

export type GroupId = 'refine' | 'tone' | 'emotion' | 'age_adapt' | 'style' | 'translate' | 'author_style'

export interface TransformGroup { id: GroupId; label: string; icon: LucideIcon; options: Opt[] }

// The groups the compact Selection Toolbar exposes (each a dropdown).
export const TRANSFORM_GROUPS: TransformGroup[] = [
  { id: 'refine', label: 'Refine', icon: Wand2, options: REFINE_MODES },
  { id: 'tone', label: 'Tone', icon: Palette, options: TONES },
  { id: 'emotion', label: 'Emotion', icon: Heart, options: EMOTIONS },
  { id: 'age_adapt', label: 'Audience', icon: Users, options: AUDIENCES },
  { id: 'style', label: 'Style', icon: Type, options: STYLES },
  { id: 'author_style', label: 'Author', icon: BookOpen, options: AUTHOR_STYLES },
  { id: 'translate', label: 'Translate', icon: Globe, options: LANGUAGES.map((l) => ({ id: l, label: l })) },
]

// Task 5.4 — groups whose backend request schema accepts `strength` +
// `locked_ranges` (schemas.StrengthMixin). Emotion, refine, author_style and
// translate deliberately do NOT — see EmotionRequest's own docstring in
// schemas.py for why emotion is excluded, and translate_text()'s own
// glossary-based mechanism (task 5.11) for why translation isn't part of
// this shared orchestrator at all.
export const LOCKABLE_GROUPS: GroupId[] = ['tone', 'age_adapt', 'style']
export const STRENGTH_LEVELS = ['light', 'moderate', 'strong'] as const
export type StrengthLevel = (typeof STRENGTH_LEVELS)[number]

export interface LockedRange { start: number; end: number }

/** A sentence span within `text`, as exact character offsets — the same
 * contract `LockedRangeIn` expects server-side (offsets into THIS request's
 * own `text` field, the already-captured selection substring, not
 * document-absolute editor positions). */
export interface SentenceSpan { text: string; start: number; end: number }

export function splitSentences(text: string): SentenceSpan[] {
  const spans: SentenceSpan[] = []
  const re = /[^.!?]*[.!?]+(?:\s+|$)|[^.!?]+$/g
  let m: RegExpExecArray | null
  while ((m = re.exec(text))) {
    if (m[0].length === 0) { re.lastIndex++; continue }
    const start = m.index
    const trimmedEnd = start + m[0].replace(/\s+$/, '').length
    if (trimmedEnd > start) spans.push({ text: text.slice(start, trimmedEnd), start, end: trimmedEnd })
  }
  return spans
}

export interface TransformOpts {
  storyId?: string
  chapterId?: string
  intensity?: string
  strength?: StrengthLevel
  lockedRanges?: LockedRange[]
}

// Full Stage 5 response shape (schemas.TransformResponse) — additive fields
// an older client could ignore, but the toolbar surfaces them (task 5.3's
// remaining UI gap) so preservation/no-change/strength signals are actually
// visible to the author, not just returned by the API.
export interface TransformResult {
  transformed: string
  no_change: boolean
  reason: string | null
  strength_violation: boolean
  preservation_violations: string[]
}

// Pure descriptor of the HTTP call for a transform — used by runTransform AND by
// tests to assert correct routing + that the SELECTED TEXT is what gets sent.
export function buildTransformCall(group: GroupId, value: string, text: string, opts: TransformOpts = {}) {
  const { storyId, chapterId, intensity = 'medium', strength, lockedRanges } = opts
  const lockable = LOCKABLE_GROUPS.includes(group)
  // Only attached for groups whose backend schema actually accepts them —
  // sending these to /emotion, /refine, /author-style or /translate would be
  // silently ignored server-side (extra fields aren't rejected), but keeping
  // the client honest about what each endpoint supports is worth the branch.
  const lockFields = lockable ? { strength, locked_ranges: lockedRanges?.map((r) => ({ start: r.start, end: r.end })) } : {}
  switch (group) {
    case 'refine':    return { path: '/api/ai/refine', body: { text, mode: value, story_id: storyId, chapter_id: chapterId } }
    case 'tone':      return { path: '/api/ai/tone', body: { text, tone: value.toLowerCase(), story_id: storyId, ...lockFields } }
    case 'emotion':   return { path: '/api/ai/emotion', body: { text, emotion: value.toLowerCase(), intensity, story_id: storyId } }
    case 'age_adapt': return { path: '/api/ai/age-adapt', body: { text, target_age: value, story_id: storyId, ...lockFields } }
    case 'style':     return { path: '/api/ai/style', body: { text, style: value.toLowerCase(), story_id: storyId, ...lockFields } }
    case 'author_style': return { path: '/api/ai/author-style', body: { text, author: value, story_id: storyId, chapter_id: chapterId } }
    case 'translate': return { path: '/api/ai/translate', body: { text, target_language: value, story_id: storyId } }
  }
}

// Run a transform on EXACTLY the given (selected) text → returns the full
// Stage 5 result (not just the rewritten prose), so callers can surface
// no_change/reason/preservation/strength signals to the author.
export async function runTransform(group: GroupId, value: string, text: string, opts: TransformOpts = {}): Promise<TransformResult> {
  const call = buildTransformCall(group, value, text, opts)
  const res = await api.post(call.path, call.body)
  const d = res.data
  return {
    transformed: d.transformed as string,
    no_change: !!d.no_change,
    reason: d.reason ?? null,
    strength_violation: !!d.strength_violation,
    preservation_violations: Array.isArray(d.preservation_violations) ? d.preservation_violations : [],
  }
}
