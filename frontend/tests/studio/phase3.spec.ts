// Stage 8.6 — every Phase 3 surface is reachable and usable in its home (Write's
// AI sidecar, with room to work when expanded): transform → pin, Versions,
// compare, sentence locks, preservation rules. Mocked API; no model involved.
import { test, expect, type Page, type Route } from '@playwright/test'
import { mockApi, signIn, workspaceUrl, STORY_ID, CHAPTER_IDS } from './mockApi'

const now = '2026-09-25T00:00:00Z'
const pin = (id: string, label: string) => ({
  pin_id: id, story_id: STORY_ID, chapter_id: CHAPTER_IDS[0], tool: 'tone', scope: 'selection', tool_params: {},
  preview: `${label} preview`, source_excerpt: 'Placeholder', source_sha256: 'x', source_from: 1, source_to: 10,
  content_sha256: 'y', word_count: 3, label, is_favourite: false, parent_pin_id: null, root_pin_id: id,
  lineage_depth: 0, derived_from_pin_ids: [], derivation: 'variation', has_embedding: false, applied_at: null,
  promoted_card_id: null, expires_at: '2026-10-02T00:00:00Z', created_at: now,
})
const PINS = [pin('p1', 'Version one'), pin('p2', 'Version two')]
const json = (r: Route, b: unknown) => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })

async function phase3Api(page: Page) {
  const created: string[] = []
  const log = await mockApi(page, [
    (r, m, p) => (m === 'GET' && p === `/api/stories/${STORY_ID}/ai/pins`) ? json(r, { pins: PINS, total: 2 }).then(() => true) : false,
    (r, m, p) => {
      const g = p.match(new RegExp(`^/api/stories/${STORY_ID}/ai/pins/(p[12])$`))
      return m === 'GET' && g ? json(r, { ...PINS.find((x) => x.pin_id === g[1]), content: `Full text of ${g[1]}.` }).then(() => true) : false
    },
    (r, m, p) => {
      if (!(m === 'POST' && p === `/api/stories/${STORY_ID}/ai/pins`)) return false
      created.push(p)
      return json(r, pin('p3', 'New pin')).then(() => true)
    },
    (r, m, p) => (m === 'GET' && p === '/api/ai/limits') ? json(r, {
      plan: 'free', limits: { max_pins: 20, pin_ttl_days: 7, max_pin_chars: 20000, max_context_pins: 3, max_idea_cards: 50,
        max_style_samples: 0, can_extend_ttl: false, strict_consistency: false },
      usage: { pins: 2, idea_cards: 0 }, session_history_max: 20, avoid_max_items: 5,
    }).then(() => true) : false,
    (r, m, p) => (m === 'GET' && p === `/api/stories/${STORY_ID}/ai/preferences`) ? json(r, {
      story_id: STORY_ID, preserve_character_names: true, preserve_tone: true, author_notes: '',
      preserve_rules: { character_names: true, tone: 'warn', tense: 'warn', pov: 'warn', dialogue_meaning: 'warn', timeline: 'warn', story_facts: 'warn' },
      style_prefs: { match_level: 'light', exemplar_card_ids: [], use_story_dna: false },
      pin_prefs: { duplicate_auto_retry: false, strict_consistency: false },
      story_dna_available: false, strict_consistency_allowed: false,
    }).then(() => true) : false,
    (r, m, p) => (m === 'POST' && p === '/api/ai/tone') ? json(r, {
      original: 'Placeholder paragraph 1 for layout tests.', transformed: 'A calmer placeholder paragraph for layout tests.',
      mode: 'tone', tokens_used: 10, no_change: false, warnings: [],
    }).then(() => true) : false,
  ])
  return { log, created }
}

async function openWrite(page: Page) {
  await page.goto(workspaceUrl('write'))
  await page.locator('.ProseMirror').first().waitFor()
  await page.getByRole('button', { name: 'AI assistant', exact: true }).click()
}

test.beforeEach(async ({ page }) => { await signIn(page) })

test('transform → pin: a result can be pinned from the sidecar', async ({ page }) => {
  const { created } = await phase3Api(page)
  await openWrite(page)
  await page.getByRole('combobox', { name: 'Rewrite tool' }).selectOption('tone')
  await page.locator('.ProseMirror p').first().click({ clickCount: 3 })
  await page.locator('#ai-tool-panel').getByRole('button', { name: /Apply|Change|Transform|Rewrite/ }).last().click()
  await expect(page.getByTestId('pin-button')).toBeVisible()
  await page.getByTestId('pin-button').click()
  await expect.poll(() => created.length).toBe(1)
})

test('sentence locks and preservation rules are reachable on a lockable tool', async ({ page }) => {
  await phase3Api(page)
  await openWrite(page)
  await page.getByRole('combobox', { name: 'Rewrite tool' }).selectOption('tone')
  await expect(page.getByTestId('sidebar-lock-strength')).toBeVisible()
  await page.locator('.ProseMirror p').first().click({ clickCount: 3 })
  await expect(page.getByTestId('sidebar-lock-strength').getByRole('button', { name: /Placeholder paragraph 1/ })).toBeVisible()
  await page.getByRole('button', { name: /What the AI must keep/ }).click()
  await expect(page.getByRole('radiogroup', { name: 'Voice matching' })).toBeVisible()
})

test('Versions and compare have room in the expanded sidecar', async ({ page }) => {
  await phase3Api(page)
  await openWrite(page)
  await page.getByRole('button', { name: 'Expand AI assistant' }).click()
  await page.getByRole('tab', { name: 'Versions' }).click()
  const cards = page.getByTestId('pin-card')
  await expect(cards).toHaveCount(2)
  await cards.nth(0).getByRole('button', { expanded: false }).click()
  await cards.nth(0).getByRole('button', { name: 'Compare with another version' }).click()
  await cards.nth(1).getByRole('button', { expanded: false }).click()
  await cards.nth(1).getByRole('button', { name: 'Compare with this' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: 'Close comparison' }).click()
  await expect(dialog).toHaveCount(0)
})

test('the AI groups and Rewrite chooser work from the keyboard alone', async ({ page }) => {
  await phase3Api(page)
  await openWrite(page)
  const rewrite = page.getByRole('tab', { name: 'Rewrite' })
  await rewrite.focus()
  await page.keyboard.press('ArrowRight')
  await expect(page.getByRole('tab', { name: 'Generate' })).toBeFocused()
  await expect(page.getByRole('radio', { name: 'Continue' })).toBeVisible()
  await page.keyboard.press('ArrowRight')
  await expect(page.getByRole('tab', { name: 'Versions' })).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByTestId('versions-panel')).toBeVisible()
  await page.keyboard.press('ArrowRight')                       // wraps to Rewrite
  await expect(rewrite).toHaveAttribute('aria-selected', 'true')
  const chooser = page.getByRole('combobox', { name: 'Rewrite tool' })
  await chooser.focus()
  await chooser.selectOption('style')
  await expect(chooser).toHaveValue('style')
})
