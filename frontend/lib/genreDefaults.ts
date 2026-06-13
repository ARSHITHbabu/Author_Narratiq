// Genre-aware tool defaults — the single source of truth that maps a story's
// detected genre profile to sensible starting values for the AI rewrite tools
// (tone / emotion / style / audience). Reusable across the AI Sidecar and the
// Selection Toolbar. Genre-matched values are drawn from the real option sets in
// lib/transforms so a derived default is always selectable.
//
// The user can always override; these are only the *initial* / *recommended*
// selections so the tools feel genre-appropriate instead of random (e.g. Horror
// → Fear/Dark/Gothic, Comedy → Joy/Humorous, Romance → Romantic warmth).
//
// When there is NO genre profile (intake skipped), we fall back to TRULY NEUTRAL
// values — never genre-specific ones like Dark/Fear/Gothic — so a profile-less
// project does not behave like a Horror story.

import { TONES } from './transforms'
import type { GenreProfile } from './types'

export interface ToolDefaults {
  tone: string
  emotion: string
  style: string
  age: string
}

// Truly neutral, genre-agnostic defaults for projects with no genre profile.
// These intentionally do NOT match any flavored chip, so nothing is pre-
// highlighted — signalling "no genre recommendation, pick what you like".
export const NEUTRAL_DEFAULTS: ToolDefaults = {
  tone: 'Balanced',
  emotion: 'Neutral',
  style: 'Clean',
  age: 'adult',
}

// Ordered rules: first regex that matches the genre text wins. Tone/emotion/style
// ids match entries in TONES / EMOTIONS / STYLES (lib/transforms).
const GENRE_RULES: { match: RegExp; tone: string; emotion: string; style: string }[] = [
  { match: /horror|gothic|dread|supernatural|ghost/, tone: 'Dark',        emotion: 'Fear',         style: 'Gothic' },
  { match: /thriller|suspense|crime|mystery|detective|noir/, tone: 'Suspenseful', emotion: 'Fear',  style: 'Thriller' },
  { match: /romance|romantic|love/,                  tone: 'Romantic',    emotion: 'Joy',          style: 'Lyrical' },
  { match: /comedy|humou?r|satire|comic|farce/,      tone: 'Humorous',    emotion: 'Joy',          style: 'Contemporary' },
  { match: /epic|high fantasy|fantasy|myth|saga/,    tone: 'Epic',        emotion: 'Anticipation', style: 'Literary' },
  { match: /sci-?fi|science fiction|dystop|cyberpunk|space/, tone: 'Tense', emotion: 'Anticipation', style: 'Minimalist' },
  { match: /tragedy|grief|literary|drama/,           tone: 'Melancholic', emotion: 'Sadness',      style: 'Literary' },
  { match: /adventure|action|quest/,                 tone: 'Epic',        emotion: 'Anticipation', style: 'Pulp' },
  { match: /hope|inspir|uplift|feel-?good/,          tone: 'Hopeful',     emotion: 'Joy',          style: 'Contemporary' },
]

function mapAudienceToAge(audience?: string): string {
  const a = (audience ?? '').toLowerCase()
  if (/child|kid|middle.?grade|\bmg\b|picture book/.test(a)) return 'children'
  if (/\bya\b|young.?adult|teen/.test(a)) return 'ya'
  return 'adult'
}

// True when the story has a usable genre profile (genre or detected tones).
export function hasGenreProfile(profile?: Partial<GenreProfile> | null): boolean {
  if (!profile) return false
  return Boolean((profile.genre && profile.genre.trim()) || (profile.tone && profile.tone.length))
}

export function deriveToolDefaults(profile?: Partial<GenreProfile> | null): ToolDefaults {
  // No genre profile → neutral, NOT Horror/Gothic.
  if (!hasGenreProfile(profile)) return NEUTRAL_DEFAULTS

  const hay = [
    profile!.genre,
    profile!.sub_genre,
    ...(profile!.secondary_genres ?? []),
  ].filter(Boolean).join(' ').toLowerCase()

  const rule = GENRE_RULES.find((r) => r.match.test(hay))

  // Prefer a tone the analysis actually detected, if it matches a known option.
  const profileTones = (profile!.tone ?? []).map((t) => t.toLowerCase())
  const matchedTone = TONES.find((t) => profileTones.includes(t.id.toLowerCase()))?.id

  // A profile with an unrecognised genre still shouldn't assume Horror — fall
  // back to neutral for any field the rules don't cover.
  return {
    tone:    matchedTone ?? rule?.tone ?? NEUTRAL_DEFAULTS.tone,
    emotion: rule?.emotion ?? NEUTRAL_DEFAULTS.emotion,
    style:   rule?.style ?? NEUTRAL_DEFAULTS.style,
    age:     mapAudienceToAge(profile!.audience),
  }
}
