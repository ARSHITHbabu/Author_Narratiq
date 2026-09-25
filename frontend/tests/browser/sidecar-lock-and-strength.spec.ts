import { test, expect, type APIRequestContext, type Page } from '@playwright/test'

// Stage 5 tasks 5.4 / 5.6 via the AI SIDECAR path (AIToolsSidebar) — the
// companion of lock-and-strength.spec.ts, which covers the floating toolbar.
// While the sidecar is open it owns the selection and the floating toolbar is
// hidden, so the sidecar's Tone/Audience/Style tabs must carry the controls too.
//
//   E2E_EMAIL=… E2E_PASSWORD=… E2E_STORY_ID=… npx playwright test --project=browser tests/browser/sidecar-lock-and-strength.spec.ts
//
// Fixture: a disposable story with a chapter titled "Fixture" whose content is
//   "The sensor reported normal readings for the third day in a row. Priya
//    logged the data and closed her laptop for the night."

const EMAIL = process.env.E2E_EMAIL
const PASSWORD = process.env.E2E_PASSWORD
const STORY_ID = process.env.E2E_STORY_ID

test.skip(!EMAIL || !PASSWORD || !STORY_ID, 'Set E2E_EMAIL, E2E_PASSWORD and E2E_STORY_ID.')

const AI_TIMEOUT = 120_000
const API_URL = process.env.E2E_API_URL ?? 'http://localhost:8000'
const LOCKED = 'The sensor reported normal readings for the third day in a row.'

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

const sidecar = (page: Page) => page.getByTestId('sidebar-lock-strength')
const firstParagraph = (page: Page) => page.locator('.ProseMirror p').first()

async function openWithSidecar(page: Page) {
  await page.goto(`/projects/${STORY_ID}/write`)
  await expect(page.locator('.ProseMirror')).toBeVisible({ timeout: 30_000 })
  await page.getByText('Fixture', { exact: true }).first().click()
  await expect(firstParagraph(page)).toContainText('sensor reported')
  await page.getByRole('button', { name: 'AI assistant', exact: true }).click()
  // Stage 8.4: sidebar tools are grouped; Tone is chosen from the Rewrite chooser.
  await page.getByRole('combobox', { name: 'Rewrite tool' }).selectOption('tone')
}

test.beforeEach(async ({ page, request }) => {
  await signIn(page, request)
  await openWithSidecar(page)
})

test('sidecar Tone tab shows strength selector (default light) and, with a selection, the lock picker', async ({ page }) => {
  await expect(sidecar(page).getByText('Strength')).toBeVisible()
  await expect(sidecar(page).getByRole('button', { name: 'light', exact: true })).toHaveAttribute('aria-pressed', 'true')

  await firstParagraph(page).click({ clickCount: 3 })
  await expect(page.getByText(/words? selected — AI will work on this/)).toBeVisible()
  // The floating toolbar is (by design) hidden while the sidecar owns the selection.
  await expect(page.getByRole('toolbar', { name: 'AI actions for the selected text' })).toHaveCount(0)

  const first = sidecar(page).getByRole('button', { name: /sensor reported normal/ })
  await expect(first).toBeVisible()
  await expect(sidecar(page).getByRole('button', { name: /Priya logged/ })).toBeVisible()
  await first.click()
  await expect(first).toHaveAttribute('aria-pressed', 'true')
  await expect(sidecar(page).getByText('Lock sentences to keep unchanged (1)')).toBeVisible()
})

test('sidecar Emotion tab does NOT offer strength/locks', async ({ page }) => {
  await page.getByRole('combobox', { name: 'Rewrite tool' }).selectOption('emotion')
  await expect(sidecar(page)).toHaveCount(0)
})

test('sidecar end-to-end: strength + lock are sent to /api/ai/tone and the locked sentence survives byte-identical', async ({ page }) => {
  await firstParagraph(page).click({ clickCount: 3 })
  await sidecar(page).getByRole('button', { name: 'strong', exact: true }).click()
  await sidecar(page).getByRole('button', { name: /sensor reported normal/ }).click()

  const reqPromise = page.waitForRequest((r) => r.url().includes('/api/ai/tone') && r.method() === 'POST')
  const resPromise = page.waitForResponse((r) => r.url().includes('/api/ai/tone'), { timeout: AI_TIMEOUT })
  await page.getByRole('button', { name: /^Apply .* Tone$/ }).click()

  const body = (await reqPromise).postDataJSON()
  expect(body.strength).toBe('strong')
  expect(body.locked_ranges).toHaveLength(1)
  expect(body.text.slice(body.locked_ranges[0].start, body.locked_ranges[0].end)).toBe(LOCKED)

  const res = await resPromise
  expect(res.ok(), `tone failed: ${res.status()}`).toBe(true)
  const out = await res.json()
  expect(out.transformed).toContain(LOCKED)
  await expect(page.getByText('AI Result')).toBeVisible()
})
