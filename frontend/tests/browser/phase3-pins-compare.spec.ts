import { test, expect, type APIRequestContext, type Page } from '@playwright/test'

// Stage 7 (Phase 3) — real-browser verification of the author loop:
// generate → pin → Versions → compare → per-block merge → insert, plus the
// invert-locks control and Send to Idea Shelf. Real frontend + backend + vLLM.
//
//   npx playwright install chromium
//   E2E_EMAIL=… E2E_PASSWORD=… E2E_STORY_ID=… npx playwright test --project=browser tests/browser/phase3-pins-compare.spec.ts
//
// Runs against a disposable fixture story (never real manuscript content)
// whose chapter one is a plain two-sentence paragraph (see lock-and-strength
// .spec.ts for why the fixture is plain rather than moody).

const EMAIL = process.env.E2E_EMAIL
const PASSWORD = process.env.E2E_PASSWORD
const STORY_ID = process.env.E2E_STORY_ID
test.skip(!EMAIL || !PASSWORD || !STORY_ID, 'Set E2E_EMAIL, E2E_PASSWORD and E2E_STORY_ID.')

const AI_TIMEOUT = 150_000
const API_URL = process.env.E2E_API_URL ?? 'http://localhost:8000'
test.describe.configure({ mode: 'serial' })

let token = ''
let userJson = ''

async function signIn(page: Page, request: APIRequestContext) {
  if (!token) {
    const res = await request.post(`${API_URL}/api/auth/login`, { data: { email: EMAIL, password: PASSWORD } })
    expect(res.ok()).toBe(true)
    const body = await res.json()
    token = body.access_token
    userJson = JSON.stringify(body.user)
  }
  await page.addInitScript(([t, u]) => {
    window.localStorage.setItem('narratiq_token', t)
    window.localStorage.setItem('narratiq_user', u)
  }, [token, userJson])
}

const toolbar = (page: Page) => page.getByRole('toolbar', { name: 'AI actions for the selected text' })
const firstParagraph = (page: Page) => page.locator('.ProseMirror p').first()

async function openWrite(page: Page) {
  await page.goto(`/projects/${STORY_ID}/write`)
  await expect(page.locator('.ProseMirror')).toBeVisible({ timeout: 30_000 })
  await expect(firstParagraph(page)).not.toBeEmpty()
}

async function generate(page: Page, tone: string) {
  await firstParagraph(page).click({ clickCount: 3 })
  await toolbar(page).getByRole('button', { name: /Tone/i }).first().click()
  await page.getByRole('menuitem', { name: new RegExp(tone) }).click()
  await expect(page.getByRole('button', { name: /Apply to selection|Insert at cursor instead/ })).toBeVisible({ timeout: AI_TIMEOUT })
}

test.beforeAll(async ({ request }) => {
  // Start from zero pins for this fixture story so counts are deterministic.
  const res = await request.post(`${API_URL}/api/auth/login`, { data: { email: EMAIL, password: PASSWORD } })
  const t = (await res.json()).access_token
  const pins = await (await request.get(`${API_URL}/api/stories/${STORY_ID}/ai/pins`, { headers: { Authorization: `Bearer ${t}` } })).json()
  for (const p of pins.pins) await request.delete(`${API_URL}/api/stories/${STORY_ID}/ai/pins/${p.pin_id}`, { headers: { Authorization: `Bearer ${t}` } })
})

test.beforeEach(async ({ page, request }) => {
  await signIn(page, request)
  await openWrite(page)
})

test('invert locks swaps locked and unlocked sentences', async ({ page }) => {
  await firstParagraph(page).click({ clickCount: 3 })
  await toolbar(page).getByRole('button', { name: /Tone/i }).first().click()
  const menu = page.getByRole('menu')
  const sentences = menu.locator('button[aria-pressed]')
  await expect(sentences).toHaveCount(2)
  await sentences.first().click()
  await expect(sentences.first()).toHaveAttribute('aria-pressed', 'true')
  await menu.getByTestId('invert-locks').click()
  await expect(sentences.first()).toHaveAttribute('aria-pressed', 'false')
  await expect(sentences.nth(1)).toHaveAttribute('aria-pressed', 'true')
})

test('P3-01: a result can be pinned from the toolbar and shows its expiry', async ({ page }) => {
  await generate(page, 'Dark')
  const pin = page.getByTestId('pin-button')
  await pin.click()
  await expect(pin).toContainText(/Pinned · expires in \d+ days/, { timeout: 15_000 })
})

test('P3-01/P3-04: Versions lists pins; two versions compare and merge block by block', async ({ page }) => {
  // A second, different version to compare against.
  await generate(page, 'Hopeful')
  await page.getByTestId('pin-button').click()
  await expect(page.getByTestId('pin-button')).toContainText('Pinned', { timeout: 15_000 })
  await page.keyboard.press('Escape')

  await page.getByRole('button', { name: 'AI assistant', exact: true }).click()
  await page.getByRole('tab', { name: 'Versions' }).click()
  const cards = page.getByTestId('pin-card')
  await expect(cards).toHaveCount(2, { timeout: 15_000 })
  await expect(page.getByTestId('versions-panel')).toContainText(/2 of 20 pins · free plan · kept 7 days/)

  await cards.nth(0).locator('button[aria-expanded]').click()
  await cards.nth(0).getByRole('button', { name: 'Compare with another version' }).click()
  await cards.nth(1).locator('button[aria-expanded]').click()
  await cards.nth(1).getByRole('button', { name: 'Compare with this' }).click()

  const dialog = page.getByRole('dialog')
  await expect(dialog.getByText('Compare versions')).toBeVisible()
  await dialog.getByRole('tab', { name: 'Unified' }).click()
  await dialog.getByRole('tab', { name: 'Changes only' }).click()
  const merge = dialog.getByTestId('merge-section')
  if (await merge.count()) {
    const choices = merge.locator('li button[aria-pressed]')
    // Choose the right-hand side of the first changed passage and check the
    // merged text now contains exactly that passage.
    const right = choices.nth(1)
    const chosenText = (await right.innerText()).split('\n').slice(1).join(' ').trim().slice(0, 25)
    await right.click()
    await expect(right).toHaveAttribute('aria-pressed', 'true')
    if (chosenText && !chosenText.startsWith('(leave out)')) await expect(merge.getByTestId('merged-text')).toContainText(chosenText)
  }
  await dialog.getByRole('button', { name: 'Close comparison' }).click()
  await expect(dialog).toBeHidden()
})

test('P3-09: a result can be sent to the Idea Shelf and appears under Notes → Ideas', async ({ page }) => {
  await generate(page, 'Epic')
  await page.getByRole('button', { name: 'Send to Idea Shelf' }).click()
  await page.getByRole('button', { name: 'Save idea' }).click()
  await expect(page.getByText(/Saved to the Idea Shelf/)).toBeVisible({ timeout: 15_000 })
  // Stage 8.8: the Idea Shelf's one home is World › Notes › Ideas (D10).
  await page.goto(`/projects/${STORY_ID}/world?section=notes&tab=ideas`)
  await expect(page.getByRole('tab', { name: 'Ideas', selected: true })).toBeVisible()
  await expect(page.getByTestId('idea-card').first()).toBeVisible({ timeout: 15_000 })
})
