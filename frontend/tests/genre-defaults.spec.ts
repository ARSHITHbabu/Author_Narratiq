import { test, expect } from '@playwright/test'
import { deriveToolDefaults, NEUTRAL_DEFAULTS, hasGenreProfile } from '../lib/genreDefaults'

// ── No genre profile → TRULY NEUTRAL defaults (never Horror/Gothic) ───────────
test('no profile yields neutral defaults, not genre-specific ones', () => {
  const d = deriveToolDefaults(null)
  expect(d).toEqual(NEUTRAL_DEFAULTS)
  expect(d.tone).toBe('Balanced')
  expect(d.emotion).toBe('Neutral')
  expect(d.style).toBe('Clean')
  // must NOT be the old misleading Horror defaults
  expect([d.tone, d.emotion, d.style]).not.toContain('Dark')
  expect([d.tone, d.emotion, d.style]).not.toContain('Fear')
  expect([d.tone, d.emotion, d.style]).not.toContain('Gothic')
})

test('hasGenreProfile is false for null/empty and true with genre or tone', () => {
  expect(hasGenreProfile(null)).toBe(false)
  expect(hasGenreProfile({})).toBe(false)
  expect(hasGenreProfile({ genre: 'Horror' })).toBe(true)
  expect(hasGenreProfile({ tone: ['Dark'] })).toBe(true)
})

// ── Genre → recommended defaults from the real option sets ────────────────────
test('horror maps to Dark / Fear / Gothic', () => {
  const d = deriveToolDefaults({ genre: 'Horror', sub_genre: 'Supernatural horror' })
  expect(d.tone).toBe('Dark')
  expect(d.emotion).toBe('Fear')
  expect(d.style).toBe('Gothic')
})

test('comedy maps to Humorous / Joy', () => {
  const d = deriveToolDefaults({ genre: 'Comedy' })
  expect(d.tone).toBe('Humorous')
  expect(d.emotion).toBe('Joy')
})

test('romance maps to Romantic / Joy', () => {
  const d = deriveToolDefaults({ genre: 'Romance' })
  expect(d.tone).toBe('Romantic')
  expect(d.emotion).toBe('Joy')
})

test('a detected tone that matches a known option is preferred', () => {
  const d = deriveToolDefaults({ genre: 'Drama', tone: ['Hopeful'] })
  expect(d.tone).toBe('Hopeful')
})

test('unrecognised genre falls back to neutral (not Horror)', () => {
  const d = deriveToolDefaults({ genre: 'Cookbook' })
  expect(d.tone).toBe(NEUTRAL_DEFAULTS.tone)
  expect(d.style).toBe(NEUTRAL_DEFAULTS.style)
})

test('audience maps to age bucket', () => {
  expect(deriveToolDefaults({ genre: 'Fantasy', audience: 'Young Adult' }).age).toBe('ya')
  expect(deriveToolDefaults({ genre: 'Fantasy', audience: 'Children' }).age).toBe('children')
  expect(deriveToolDefaults({ genre: 'Fantasy', audience: 'Adult' }).age).toBe('adult')
})
