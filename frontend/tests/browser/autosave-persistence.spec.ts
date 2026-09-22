import { test, expect, type APIRequestContext, type Page } from '@playwright/test'

// Stage 6 task 6.4 — critical journey: login -> project -> chapter -> autosave -> reload persistence.
//
//   npx playwright install chromium
//   E2E_EMAIL=… E2E_PASSWORD=… E2E_STORY_ID=… npx playwright test --project=browser
//
// Written 2026-09-22 following the exact conventions of the existing browser
// specs (selection-toolbar.spec.ts, lock-and-strength.spec.ts) — same
// env-gated skip-by-default, same auth-via-API-then-seed-localStorage
// pattern. NOT executed against a live browser render as part of this
// change (no browser binaries installed in this environment, and doing so
// would need a live full stack) — selectors below are best-effort from
// reading the actual component source, not verified live. Flagged
// explicitly in the Stage 6 report; verify on first real run.

const EMAIL = process.env.E2E_EMAIL
const PASSWORD = process.env.E2E_PASSWORD
const STORY_ID = process.env.E2E_STORY_ID

test.skip(!EMAIL || !PASSWORD || !STORY_ID, 'Set E2E_EMAIL, E2E_PASSWORD and E2E_STORY_ID.')

const API_URL = process.env.E2E_API_URL ?? 'http://localhost:8000'
let cachedToken: string | null = null
let cachedUser: string | null = null

async function authSession(request: APIRequestContext): Promise<{ token: string; user: string }> {
  if (!cachedToken || !cachedUser) {
    const res = await request.post(`${API_URL}/api/auth/login`, {
      data: { email: EMAIL, password: PASSWORD },
    })
    expect(res.ok(), `login failed: ${res.status()}`).toBe(true)
    const body = await res.json()
    cachedToken = body.access_token
    cachedUser = JSON.stringify(body.user)
  }
  return { token: cachedToken!, user: cachedUser! }
}

async function openEditor(page: Page, request: APIRequestContext) {
  const { token, user } = await authSession(request)
  await page.addInitScript(([t, u]) => {
    window.localStorage.setItem('narratiq_token', t)
    window.localStorage.setItem('narratiq_user', u)
  }, [token, user])
  await page.goto(`/projects/${STORY_ID}`)
  await page.locator('.ProseMirror').first().waitFor({ state: 'visible' })
}

const editor = (page: Page) => page.locator('.ProseMirror').first()

test('typed text survives a full reload after autosave', async ({ page, request }) => {
  await openEditor(page, request)

  const marker = `E2E-autosave-marker-${Date.now()}`
  await editor(page).click()
  await page.keyboard.press('End')
  await page.keyboard.type(` ${marker}`)

  // Autosave is debounced — the app does not expose an explicit "saved"
  // event to the test, so this waits generously rather than guessing an
  // exact debounce interval (matches how the existing specs treat
  // similarly un-instrumented async UI state).
  await page.waitForTimeout(3000)

  await page.reload()
  await editor(page).waitFor({ state: 'visible' })
  await expect(editor(page)).toContainText(marker)
})

test('bolding a word survives a full reload', async ({ page, request }) => {
  await openEditor(page, request)

  await editor(page).click()
  await page.keyboard.press('Control+A')
  await page.keyboard.press('Control+B')
  await page.waitForTimeout(3000)

  await page.reload()
  await editor(page).waitFor({ state: 'visible' })
  const boldCount = await editor(page).locator('strong, b').count()
  expect(boldCount).toBeGreaterThan(0)
})
