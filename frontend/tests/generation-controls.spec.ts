import { test, expect } from '@playwright/test'
import { buildControls, expiryLabel, CONTROLLABLE_GROUPS, DERIVATIONS, PRESERVE_RULES } from '../lib/generationControls'
import { buildTransformCall } from '../lib/transforms'

// Phase 3 controls (spec §17.2): payload shape and backward compatibility.

test('without controls every request body is exactly the pre-Phase-3 shape', () => {
  for (const g of ['tone', 'emotion', 'age_adapt', 'style', 'refine', 'translate', 'author_style'] as const) {
    const body = buildTransformCall(g, 'dark', 'Text.', { storyId: 's1', chapterId: 'c1' })!.body as Record<string, unknown>
    expect(body).not.toHaveProperty('controls')
    if (g !== 'refine' && g !== 'author_style') expect(body).not.toHaveProperty('chapter_id')
  }
})

test('controls travel only to the tools whose endpoint accepts them', () => {
  const controls = buildControls({ contextPinIds: ['p1'] })
  for (const g of CONTROLLABLE_GROUPS) {
    const body = buildTransformCall(g, 'x', 'Text.', { storyId: 's1', chapterId: 'c1', controls })!.body as Record<string, unknown>
    expect(body.controls).toEqual({ context_pin_ids: ['p1'] })
    expect(body.chapter_id).toBe('c1')
  }
  for (const g of ['refine', 'translate', 'author_style'] as const) {
    const body = buildTransformCall(g, 'x', 'Text.', { storyId: 's1', controls })!.body as Record<string, unknown>
    expect(body).not.toHaveProperty('controls')
  }
})

test('buildControls drops empties, dedupes and caps the avoid-set', () => {
  expect(buildControls({})).toEqual({})
  const c = buildControls({
    contextPinIds: ['a', 'a', 'b'], avoidTexts: Array.from({ length: 12 }, (_, i) => `idea ${i} `.repeat(60)),
    basePinId: 'p', derivationParam: '  calmer  ', instruction: '  ',
  })
  expect(c.context_pin_ids).toEqual(['a', 'b'])
  expect(c.avoid_texts!.length).toBe(8)
  expect(c.avoid_texts!.every((t) => t.length <= 240)).toBe(true)
  expect(c.derivation).toBe('variation')
  expect(c.derivation_param).toBe('calmer')
  expect(c).not.toHaveProperty('instruction')
})

test('local context is capped to ~120 words either side', () => {
  const c = buildControls({ localContext: { before: 'w '.repeat(500), after: 'x '.repeat(500) } })
  expect(c.local_context!.before.split(/\s+/).filter(Boolean).length).toBeLessThanOrEqual(120)
  expect(c.local_context!.after.split(/\s+/).filter(Boolean).length).toBeLessThanOrEqual(120)
})

test('expiry is stated plainly and warns inside 48 hours', () => {
  const now = new Date('2026-09-25T00:00:00Z')
  expect(expiryLabel('2026-10-02T00:00:00', now)).toEqual({ text: 'expires in 7 days', soon: false })
  expect(expiryLabel('2026-09-26T00:00:00', now).text).toBe('expires tomorrow')
  expect(expiryLabel('2026-09-25T05:00:00', now)).toEqual({ text: 'expires in 5 h', soon: true })
})

test('all eight derivation intents and seven preservation rules are offered', () => {
  expect(DERIVATIONS.map((d) => d.id)).toEqual([
    'variation', 'improve', 'continue', 'keep_structure_change_ending', 'keep_idea_change_tone', 'expand', 'condense', 'custom'])
  expect(PRESERVE_RULES.length).toBe(7)
})
