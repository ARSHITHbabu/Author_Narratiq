import { test, expect, type APIRequestContext, type Page } from '@playwright/test'

// Stage 5 tasks 5.4 (sentence locking) and 5.6 (strength control) — full
// browser verification, not just backend helpers: frontend selection →
// SelectionToolbar's lock/strength UI → the real /api/ai/tone endpoint →
// the real backend/vLLM → the reconstructed result → Apply into the editor.
//
//   npx playwright install chromium
//   E2E_EMAIL=… E2E_PASSWORD=… E2E_STORY_ID=… npx playwright test --project=browser tests/browser/lock-and-strength.spec.ts
//
// Runs against a running frontend + backend, and a disposable fixture story
// (never real manuscript content) whose chapter one is:
//   "The sensor reported normal readings for the third day in a row. Priya
//    logged the data and closed her laptop for the night."
// — two plain, deliberately non-suspenseful sentences (so the no-change
// layer, task 5.5, does not judge them "already suspenseful" and skip the
// rewrite this test needs to observe — a flatly descriptive/moody passage
// like a lighthouse-at-night scene was tried first and DID get judged
// already-suitable, which is why this fixture is plain/technical instead).

const EMAIL = process.env.E2E_EMAIL
const PASSWORD = process.env.E2E_PASSWORD
const STORY_ID = process.env.E2E_STORY_ID

test.skip(!EMAIL || !PASSWORD || !STORY_ID, 'Set E2E_EMAIL, E2E_PASSWORD and E2E_STORY_ID.')

const AI_TIMEOUT = 120_000
const API_URL = process.env.E2E_API_URL ?? 'http://localhost:8000'

const toolbar = (page: Page) => page.getByRole('toolbar', { name: 'AI actions for the selected text' })
const previewCard = (page: Page) => page.getByRole('button', { name: 'Apply to selection' })
const editorArea = (page: Page) => page.locator('.ProseMirror')
const firstParagraph = (page: Page) => page.locator('.ProseMirror p').first()

let cachedToken: string | null = null
let cachedUser: string | null = null

async function authSession(request: APIRequestContext): Promise<{ token: string; user: string }> {
  if (!cachedToken || !cachedUser) {
    const res = await request.post(`${API_URL}/api/auth/login`, { data: { email: EMAIL, password: PASSWORD } })
    expect(res.ok(), `login failed: ${res.status()}`).toBe(true)
    const body = await res.json()
    cachedToken = body.access_token
    cachedUser = JSON.stringify(body.user)
  }
  return { token: cachedToken!, user: cachedUser! }
}

async function signIn(page: Page, request: APIRequestContext) {
  const { token, user } = await authSession(request)
  await page.addInitScript(([t, u]) => {
    window.localStorage.setItem('narratiq_token', t)
    window.localStorage.setItem('narratiq_user', u)
  }, [token, user])
}

async function openWrite(page: Page) {
  await page.goto(`/projects/${STORY_ID}/write`)
  await expect(editorArea(page)).toBeVisible({ timeout: 30_000 })
  await expect(firstParagraph(page)).not.toBeEmpty()
}

/** Select the ENTIRE first paragraph of chapter one (both fixture sentences) —
 * triple-click selects the whole paragraph block regardless of how many
 * visual lines it wraps onto, unlike Home/Shift+End which only covers one
 * visual line at narrower viewport widths. */
async function selectLine(page: Page) {
  await firstParagraph(page).click({ clickCount: 3 })
}

test.beforeEach(async ({ page, request }) => {
  await signIn(page, request)
  await openWrite(page)
})

test('5.6: strength selector is offered for Tone and defaults to light', async ({ page }) => {
  await selectLine(page)
  await toolbar(page).getByRole('button', { name: /Tone/i }).first().click()
  const menu = page.getByRole('menu')
  await expect(menu.getByText('Strength')).toBeVisible()
  const lightBtn = menu.getByRole('button', { name: 'light', exact: true })
  await expect(lightBtn).toBeVisible()
  // Default strength is "light" — verified via its distinct highlighted style class.
  await expect(lightBtn).toHaveClass(/bg-amber-500\/20/)
})

test('5.6: strength selector is NOT offered for Emotion (excluded by design)', async ({ page }) => {
  await selectLine(page)
  await toolbar(page).getByRole('button', { name: /Emotion/i }).first().click()
  const menu = page.getByRole('menu')
  await expect(menu.getByText('Intensity')).toBeVisible()   // emotion keeps its own control
  await expect(menu.getByText('Strength')).toHaveCount(0)   // but never strength
})

test('5.4: lock picker lists both fixture sentences and toggles', async ({ page }) => {
  await selectLine(page)
  await toolbar(page).getByRole('button', { name: /Tone/i }).first().click()
  const menu = page.getByRole('menu')
  await expect(menu.getByText(/Lock sentences/)).toBeVisible()
  const first = menu.getByRole('button', { name: /sensor reported normal/ })
  const second = menu.getByRole('button', { name: /Priya logged/ })
  await expect(first).toBeVisible()
  await expect(second).toBeVisible()

  await expect(first).toHaveAttribute('aria-pressed', 'false')
  await first.click()
  await expect(first).toHaveAttribute('aria-pressed', 'true')
  await expect(menu.getByText('Lock sentences to keep unchanged (1)')).toBeVisible()
})

test('5.4+5.6 end-to-end: a locked sentence survives a real /api/ai/tone call byte-identical, and Apply writes the reconstructed result into the editor', async ({ page }) => {
  await selectLine(page)
  const originalText = await firstParagraph(page).innerText()
  const lockedSentence = 'The sensor reported normal readings for the third day in a row.'
  expect(originalText).toContain(lockedSentence)

  await toolbar(page).getByRole('button', { name: /Tone/i }).first().click()
  const menu = page.getByRole('menu')

  // Set strength to "strong" — the highest-intervention level, specifically
  // to make it likely the model actually rewrites the UNLOCKED sentence, so
  // this test can tell "locked text preserved" apart from "model changed
  // nothing at all".
  await menu.getByRole('button', { name: 'strong', exact: true }).click()

  // Lock only the first sentence.
  await menu.getByRole('button', { name: /sensor reported normal/ }).click()

  // Run the transform — a real call through /api/ai/tone to the real backend/vLLM.
  await menu.getByRole('menuitem', { name: /Suspenseful/i }).click()

  await expect(previewCard(page)).toBeVisible({ timeout: AI_TIMEOUT })
  // The toolbar's own preview header reports the lock count — frontend→API
  // round-trip confirmation, not just that SOME preview appeared.
  await expect(page.getByText('1 sentence locked')).toBeVisible()

  const previewText = await page.locator('p.font-serif').innerText()
  // The deterministic guarantee under test: the locked sentence is BYTE-IDENTICAL
  // in the model's response — reconstructed from the original captured text,
  // never trusted from the model's own echo.
  expect(previewText).toContain(lockedSentence)

  // Apply into the real ProseMirror editor and confirm the locked sentence
  // survived all the way into the actual document, not just the preview pane.
  await previewCard(page).click();
  await expect(page.getByText('Applied to your selected text')).toBeVisible()
  await expect(firstParagraph(page)).toContainText(lockedSentence)
  // And the paragraph actually changed overall (the unlocked half was
  // genuinely rewritten, not a silent no-op).
  await expect(firstParagraph(page)).not.toHaveText(originalText)
})
