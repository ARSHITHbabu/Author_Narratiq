import { test, expect, type APIRequestContext, type Page } from '@playwright/test'

// Phase 2 QA Issue 7 — "notes load inconsistently". Checklist task 3.11.
//
//   E2E_EMAIL=… E2E_PASSWORD=… E2E_STORY_ID=… E2E_EMPTY_STORY_ID=… \
//     npx playwright test --project=browser tests/browser/notes-reliability.spec.ts
//
// E2E_STORY_ID must have at least one story note; E2E_EMPTY_STORY_ID must have none
// (it backs the loaded-and-empty case). Both workspace entry points are covered.

const EMAIL = process.env.E2E_EMAIL
const PASSWORD = process.env.E2E_PASSWORD
const STORY_ID = process.env.E2E_STORY_ID
const EMPTY_STORY_ID = process.env.E2E_EMPTY_STORY_ID

test.skip(!EMAIL || !PASSWORD || !STORY_ID || !EMPTY_STORY_ID,
  'Set E2E_EMAIL, E2E_PASSWORD, E2E_STORY_ID and E2E_EMPTY_STORY_ID.')

const API_URL = process.env.E2E_API_URL ?? 'http://localhost:8000'
let cached: { token: string; user: string } | null = null

async function signIn(page: Page, request: APIRequestContext) {
  if (!cached) {
    const res = await request.post(`${API_URL}/api/auth/login`, { data: { email: EMAIL, password: PASSWORD } })
    expect(res.ok(), `login failed: ${res.status()}`).toBe(true)
    const body = await res.json()
    cached = { token: body.access_token, user: JSON.stringify(body.user) }
  }
  await page.addInitScript(([t, u]) => {
    window.localStorage.setItem('narratiq_token', t)
    window.localStorage.setItem('narratiq_user', u)
  }, [cached.token, cached.user])
}

const WORKSPACES = ['world', 'plan'] as const
const notesTab = (page: Page) => page.getByRole('button', { name: 'Story Notes', exact: false }).first()
const cardsTab = (page: Page) => page.getByRole('button', { name: 'Note Cards', exact: false }).first()

async function openNotes(page: Page, workspace: string, storyId = STORY_ID!) {
  await page.goto(`/projects/${storyId}/${workspace}`)
  await page.getByRole('button', { name: /^Notes$/ }).click()
}

test.beforeEach(async ({ page, request }) => {
  await signIn(page, request)
  await page.setViewportSize({ width: 1366, height: 768 })
})

// ── Repeated navigation, both entry points ──────────────────────────────────

for (const ws of WORKSPACES) {
  test(`notes load on every visit to the ${ws} workspace (10 cycles)`, async ({ page }) => {
    for (let i = 0; i < 10; i++) {
      await openNotes(page, ws)
      await expect(page.getByText('Tide chart margins'), `cycle ${i}`).toBeVisible({ timeout: 15_000 })
      await expect(page.getByTestId('notes-error')).toHaveCount(0)
    }
  })
}

test('the API returns the same notes under repeated calls', async ({ request }) => {
  const token = cached!.token
  const seen = new Set<string>()
  for (let i = 0; i < 8; i++) {
    const res = await request.get(`${API_URL}/api/ocr/${STORY_ID}/notes`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(res.status()).toBe(200)
    seen.add(JSON.stringify((await res.json()).map((n: { note_id: string }) => n.note_id).sort()))
  }
  expect(seen.size, 'repeated reads disagreed').toBe(1)
})

// ── Partial failure: one section down, the other intact ─────────────────────

test('note cards fail, story notes still render (the reported symptom class)', async ({ page }) => {
  await page.route('**/api/ocr/*/note-cards', (r) => r.abort())
  await openNotes(page, 'world')

  await expect(page.getByText('Tide chart margins')).toBeVisible()   // preserved
  await expect(page.getByTestId('notes-empty')).toHaveCount(0)        // never "you have none"
  await expect(page.getByTestId('cards-tab-error')).toBeVisible()     // failure is visible

  await cardsTab(page).click()
  await expect(page.getByTestId('cards-error')).toBeVisible()
  await expect(page.getByTestId('cards-empty')).toHaveCount(0)
})

test('story notes fail, note cards still render', async ({ page }) => {
  await page.route('**/api/ocr/*/notes', (r) => r.abort())
  await openNotes(page, 'world')

  await expect(page.getByTestId('notes-error')).toBeVisible()
  await expect(page.getByTestId('notes-empty')).toHaveCount(0)

  await cardsTab(page).click()
  await expect(page.getByTestId('cards-error')).toHaveCount(0)
  await expect(page.getByTestId('notes-tab-error')).toBeVisible()
})

test('both fail: two honest errors, no empty state anywhere', async ({ page }) => {
  await page.route('**/api/ocr/*/notes', (r) => r.abort())
  await page.route('**/api/ocr/*/note-cards', (r) => r.abort())
  await openNotes(page, 'world')

  await expect(page.getByTestId('notes-error')).toBeVisible()
  await expect(page.getByTestId('notes-empty')).toHaveCount(0)
  await cardsTab(page).click()
  await expect(page.getByTestId('cards-error')).toBeVisible()
  await expect(page.getByTestId('cards-empty')).toHaveCount(0)
})

// ── Loaded and genuinely empty ──────────────────────────────────────────────

test('a story with no notes shows the empty state, not an error', async ({ page }) => {
  await openNotes(page, 'world', EMPTY_STORY_ID!)
  await expect(page.getByTestId('notes-empty')).toBeVisible()
  await expect(page.getByTestId('notes-error')).toHaveCount(0)
  await expect(page.getByTestId('notes-tab-error')).toHaveCount(0)
})

// ── Retry ───────────────────────────────────────────────────────────────────

test('the Retry action recovers a failed section without reloading the page', async ({ page }) => {
  let failNext = true
  await page.route('**/api/ocr/*/notes', (r) => (failNext ? r.abort() : r.continue()))
  await openNotes(page, 'world')
  await expect(page.getByTestId('notes-error')).toBeVisible()

  failNext = false
  await page.getByRole('button', { name: 'Try again' }).click()
  await expect(page.getByText('Tide chart margins')).toBeVisible({ timeout: 15_000 })
  await expect(page.getByTestId('notes-error')).toHaveCount(0)
  await expect(page.getByTestId('notes-tab-error')).toHaveCount(0)
})

test('there is no automatic retry — a failed section stays failed until asked', async ({ page }) => {
  let calls = 0
  await page.route('**/api/ocr/*/notes', (r) => { calls++; r.abort() })
  await openNotes(page, 'world')
  await expect(page.getByTestId('notes-error')).toBeVisible()
  await page.waitForTimeout(4000)
  expect(calls, 'the panel retried on its own').toBe(1)
})

// ── Cancellation and overlapping requests ───────────────────────────────────

test('navigating away mid-flight is a cancellation, not a failure', async ({ page }) => {
  await page.route('**/api/ocr/*/notes', async (r) => {
    await new Promise((res) => setTimeout(res, 4000))
    await r.continue()
  })
  await openNotes(page, 'world')
  await page.getByRole('button', { name: /Story Bible/ }).click()   // leave while loading
  await page.waitForTimeout(4500)
  await expect(page.getByTestId('notes-error')).toHaveCount(0)
  await expect(page.getByText(/could not be loaded/)).toHaveCount(0)
})

test('rapid tab flipping never leaves a stale or empty list', async ({ page }) => {
  await openNotes(page, 'world')
  for (let i = 0; i < 8; i++) {
    await page.getByRole('button', { name: /Story Bible/ }).click()
    await page.waitForTimeout(50)
    await page.getByRole('button', { name: /^Notes$/ }).click()
    await page.waitForTimeout(50)
  }
  await expect(page.getByText('Tide chart margins')).toBeVisible({ timeout: 15_000 })
  await expect(page.getByTestId('notes-error')).toHaveCount(0)
})

test('a slow earlier load cannot overwrite a newer one', async ({ page }) => {
  let n = 0
  await page.route('**/api/ocr/*/notes', async (r) => {
    n++
    if (n === 1) {
      // Slow, and would answer "you have no notes" — the stale result that must
      // never win. Fulfilling an aborted request throws; that is the point.
      await new Promise((res) => setTimeout(res, 3000))
      try { await r.fulfill({ status: 200, body: '[]', contentType: 'application/json' }) } catch { /* aborted */ }
      return
    }
    try { await r.continue() } catch { /* aborted */ }
  })

  await openNotes(page, 'world')                                  // load 1 — slow
  await page.waitForTimeout(300)                                  // let it be in flight
  await page.getByRole('button', { name: /Story Bible/ }).click()  // abandons load 1
  await page.waitForTimeout(200)
  await page.getByRole('button', { name: /^Notes$/ }).click()      // load 2 — real data

  await expect(page.getByText('Tide chart margins')).toBeVisible({ timeout: 20_000 })
  await page.waitForTimeout(3500)   // the stale empty answer would land around here
  await expect(page.getByText('Tide chart margins')).toBeVisible()
  await expect(page.getByTestId('notes-empty')).toHaveCount(0)
  await expect(page.getByTestId('notes-error')).toHaveCount(0)
})

// ── Mutations still behave ──────────────────────────────────────────────────

test('creating a note still appears immediately and survives a revisit', async ({ page }) => {
  const title = `E2E note ${Date.now()}`
  await openNotes(page, 'world')
  await page.getByRole('button', { name: 'New Note' }).click()
  await page.getByPlaceholder(/title/i).fill(title)
  await page.getByPlaceholder(/content|note/i).first().fill('created by the 3.11 browser suite')
  await page.getByRole('button', { name: /^(Create|Save|Add)/ }).first().click()
  await expect(page.getByText(title)).toBeVisible({ timeout: 15_000 })

  await openNotes(page, 'plan')
  await expect(page.getByText(title)).toBeVisible({ timeout: 15_000 })
})
