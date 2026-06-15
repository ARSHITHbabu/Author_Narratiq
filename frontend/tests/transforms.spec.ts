import { test, expect } from '@playwright/test'
import {
  REFINE_MODES, TONES, EMOTIONS, AUDIENCES, STYLES, LANGUAGES, INTENSITIES,
  AUTHOR_STYLES, TRANSFORM_GROUPS, buildTransformCall,
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
