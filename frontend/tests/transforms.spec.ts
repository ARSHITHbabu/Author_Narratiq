import { test, expect } from '@playwright/test'
import {
  REFINE_MODES, TONES, EMOTIONS, AUDIENCES, STYLES, LANGUAGES, INTENSITIES,
  AUTHOR_STYLES, TRANSFORM_GROUPS, buildTransformCall, splitSentences, LOCKABLE_GROUPS, STRENGTH_LEVELS,
  noChangeMessage, NEAR_NOOP_REASON_PREFIX,
} from '../lib/transforms'

// ── Complete Phase 1/Phase 2 option inventory is present ──────────────────────
test('shared config exposes the full real transform option set', () => {
  expect(REFINE_MODES.map((o) => o.id)).toEqual(['standard', 'literary', 'grammar', 'dialogue'])
  expect(TONES.length).toBe(9)
  expect(EMOTIONS.map((o) => o.id.toLowerCase()))
    .toEqual(['joy', 'sadness', 'fear', 'anger', 'surprise', 'disgust', 'anticipation'])
  expect(INTENSITIES).toEqual(['low', 'medium', 'high'])
  expect(AUDIENCES.map((o) => o.id)).toEqual(['children', 'ya', 'adult'])
  expect(STYLES.length).toBe(8)
  expect(LANGUAGES.length).toBe(14)
})

// ── Toolbar + Sidecar share ONE config (groups derived from it) ───────────────
test('all transform groups are exposed and map to shared options', () => {
  const ids = TRANSFORM_GROUPS.map((g) => g.id)
  expect(ids).toEqual(['refine', 'tone', 'emotion', 'age_adapt', 'style', 'author_style', 'translate'])
  expect(TRANSFORM_GROUPS.find((g) => g.id === 'tone')!.options).toBe(TONES)
  expect(TRANSFORM_GROUPS.find((g) => g.id === 'style')!.options).toBe(STYLES)
  expect(TRANSFORM_GROUPS.find((g) => g.id === 'author_style')!.options).toBe(AUTHOR_STYLES)
})

// ── Author-style catalog: public-domain named authors + generic styles only ───
test('author styles separate public-domain authors from generic styles, no living-author imitation', () => {
  const publicDomain = AUTHOR_STYLES.filter((a) => a.group === 'public_domain').map((a) => a.id)
  const generic = AUTHOR_STYLES.filter((a) => a.group === 'generic').map((a) => a.id)
  expect(publicDomain).toContain('shakespeare')
  expect(generic.length).toBeGreaterThan(0)
  // Living / in-copyright authors are NOT offered as named imitation targets.
  const ids = AUTHOR_STYLES.map((a) => a.id)
  expect(ids).not.toContain('hemingway')
  expect(ids).not.toContain('woolf')
  expect(ids).not.toContain('christie')
  // Every named author option must be flagged public-domain.
  for (const a of AUTHOR_STYLES.filter((o) => o.group === 'public_domain')) {
    expect(a.publicDomain).toBe(true)
  }
})

// ── Each option routes to the CORRECT ai_transform endpoint (never RAG/plot) ──
const SEL = 'He stood at the window, saying nothing.'   // the selected text only

test('refine routes to /api/ai/refine with the selected text + mode', () => {
  const c = buildTransformCall('refine', 'literary', SEL, { storyId: 's1', chapterId: 'c1' })
  expect(c.path).toBe('/api/ai/refine')
  expect(c.body).toMatchObject({ text: SEL, mode: 'literary', story_id: 's1', chapter_id: 'c1' })
})

test('tone routes to /api/ai/tone (value lowercased)', () => {
  const c = buildTransformCall('tone', 'Dark', SEL, { storyId: 's1' })
  expect(c.path).toBe('/api/ai/tone')
  expect(c.body).toMatchObject({ text: SEL, tone: 'dark', story_id: 's1' })
})

test('emotion routes to /api/ai/emotion with intensity', () => {
  const c = buildTransformCall('emotion', 'Fear', SEL, { intensity: 'high' })
  expect(c.path).toBe('/api/ai/emotion')
  expect(c.body).toMatchObject({ text: SEL, emotion: 'fear', intensity: 'high' })
})

test('audience routes to /api/ai/age-adapt', () => {
  const c = buildTransformCall('age_adapt', 'ya', SEL, { storyId: 's1' })
  expect(c.path).toBe('/api/ai/age-adapt')
  expect(c.body).toMatchObject({ text: SEL, target_age: 'ya' })
})

test('style routes to /api/ai/style (value lowercased)', () => {
  const c = buildTransformCall('style', 'Gothic', SEL)
  expect(c.path).toBe('/api/ai/style')
  expect(c.body).toMatchObject({ text: SEL, style: 'gothic' })
})

test('author style routes to /api/ai/author-style with the author key', () => {
  const c = buildTransformCall('author_style', 'shakespeare', SEL, { storyId: 's1', chapterId: 'c1' })
  expect(c.path).toBe('/api/ai/author-style')
  expect(c.body).toMatchObject({ text: SEL, author: 'shakespeare', story_id: 's1', chapter_id: 'c1' })
})

test('translate routes to /api/ai/translate with the language', () => {
  const c = buildTransformCall('translate', 'French', SEL, { storyId: 's1' })
  expect(c.path).toBe('/api/ai/translate')
  expect(c.body).toMatchObject({ text: SEL, target_language: 'French' })
})

// ── Task 5.4/5.6 — strength + locked_ranges are wired for the right groups ────

test('LOCKABLE_GROUPS is exactly tone/age_adapt/style — matching schemas.StrengthMixin', () => {
  expect(LOCKABLE_GROUPS.sort()).toEqual(['age_adapt', 'style', 'tone'])
  expect(STRENGTH_LEVELS).toEqual(['light', 'moderate', 'strong'])
})

test('tone sends strength + locked_ranges when provided', () => {
  const c = buildTransformCall('tone', 'Dark', SEL, {
    storyId: 's1', strength: 'moderate', lockedRanges: [{ start: 0, end: 8 }],
  })
  expect(c.body).toMatchObject({ strength: 'moderate', locked_ranges: [{ start: 0, end: 8 }] })
})

test('age_adapt and style also send strength + locked_ranges', () => {
  const a = buildTransformCall('age_adapt', 'ya', SEL, { strength: 'strong', lockedRanges: [{ start: 2, end: 5 }] })
  expect(a.body).toMatchObject({ strength: 'strong', locked_ranges: [{ start: 2, end: 5 }] })
  const s = buildTransformCall('style', 'Gothic', SEL, { strength: 'light' })
  expect(s.body).toMatchObject({ strength: 'light' })
})

test('non-lockable groups never send strength or locked_ranges, even if passed', () => {
  for (const group of ['refine', 'emotion', 'author_style', 'translate'] as const) {
    const c = buildTransformCall(group, group === 'translate' ? 'French' : 'standard', SEL, {
      strength: 'strong', lockedRanges: [{ start: 0, end: 3 }],
    })
    expect(c.body).not.toHaveProperty('strength')
    expect(c.body).not.toHaveProperty('locked_ranges')
  }
})

// ── Task 5.4 — sentence splitting for the lock picker ──────────────────────────

test('splitSentences finds exact character offsets for each sentence', () => {
  const text = 'The letter had said everything and nothing. Devika read it twice, then folded it back.'
  const spans = splitSentences(text)
  expect(spans.length).toBe(2)
  expect(text.slice(spans[0].start, spans[0].end)).toBe('The letter had said everything and nothing.')
  expect(text.slice(spans[1].start, spans[1].end)).toBe('Devika read it twice, then folded it back.')
})

test('splitSentences handles a single sentence with no trailing period', () => {
  const text = 'He stood at the window, saying nothing'
  const spans = splitSentences(text)
  expect(spans.length).toBe(1)
  expect(spans[0]).toEqual({ text, start: 0, end: text.length })
})

test('splitSentences offsets are usable as locked_ranges — round-trips through buildTransformCall', () => {
  const text = 'Aanya was not going to get a fifth chance. She knew it.'
  const spans = splitSentences(text)
  const lockedRanges = [spans[0]].map((s) => ({ start: s.start, end: s.end }))
  const c = buildTransformCall('tone', 'Dark', text, { lockedRanges })
  const body = c.body as { locked_ranges: { start: number; end: number }[] }
  expect(body.locked_ranges).toEqual([{ start: 0, end: text.indexOf('.') + 1 }])
  expect(text.slice(body.locked_ranges[0].start, body.locked_ranges[0].end)).toBe('Aanya was not going to get a fifth chance.')
})

// ── Selected text only — no RAG / story passages / chapter summary anywhere ───
test('every transform sends ONLY the selected text (no story-wide context)', () => {
  const groups = ['refine', 'tone', 'emotion', 'age_adapt', 'style', 'author_style', 'translate'] as const
  for (const g of groups) {
    const c = buildTransformCall(g, g === 'translate' ? 'French' : 'standard', SEL, { storyId: 's1' })
    expect(c.body.text).toBe(SEL)                 // exact selection
    expect(c.path.startsWith('/api/ai/')).toBe(true)   // ai_transform feature only
    expect(c.path).not.toContain('plot')
    expect(c.path).not.toContain('intelligence')
    expect(c.path).not.toContain('voice')
  }
})

// ── Stage 5 (D4): an unchanged Style result is never shown as a rewrite ─────
test('no-change message distinguishes "already suitable" from "no meaningful change"', () => {
  const guard = 'The AI could not find a meaningful change to make — try a stronger setting or a different passage.'
  expect(guard.startsWith(NEAR_NOOP_REASON_PREFIX)).toBe(true)
  expect(noChangeMessage(guard)).toBe(guard)
  expect(noChangeMessage('It is already formal.')).toBe('Already reads that way — It is already formal.')
  expect(noChangeMessage(null)).toBe('This already reads that way — no change made.')
})
