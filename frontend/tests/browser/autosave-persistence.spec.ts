import { test, expect, type APIRequestContext, type Page } from '@playwright/test'

// Stage 6 task 6.4 — critical journey: login -> project -> chapter -> autosave -> reload persistence.
//
//   npx playwright install chromium
//   E2E_EMAIL=… E2E_PASSWORD=… E2E_STORY_ID=… npx playwright test --project=browser
//
// Written 2026-09-22 following the exact conventions of the existing browser
// specs (selection-toolbar.spec.ts, lock-and-strength.spec.ts) — same
// env-gated skip-by-default, same auth-via-API-then-seed-localStorage
// pattern. Executed live against a real stack during Stage 6 closure
// (2026-09-22) — both tests passing; see this file's own comment above
// openEditorInFreshStory for a real test-isolation bug found and fixed
// during that run.

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

// Found running this file live (2026-09-22): Playwright's default parallel
// workers ran both tests below concurrently against the SAME shared
// E2E_STORY_ID/chapter, and each test's typing/autosave raced the other's —
// the bold test's own reload showed the OTHER test's marker text appended,
// and the bold mark itself was lost, not because bolding is broken but
// because two autosaves overwrote each other mid-test. Fixed by giving each
// test its own disposable story via the API — a test-isolation bug, not a
// product bug.
async function openEditorInFreshStory(page: Page, request: APIRequestContext): Promise<string> {
  const { token, user } = await authSession(request)
  const created = await request.post(`${API_URL}/api/projects/`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { title: `E2E autosave isolation ${Date.now()}` },
  })
  expect(created.ok(), `story creation failed: ${created.status()}`).toBe(true)
  const story = await created.json()

  await page.addInitScript(([t, u]) => {
    window.localStorage.setItem('narratiq_token', t)
    window.localStorage.setItem('narratiq_user', u)
  }, [token, user])
  await page.goto(`/projects/${story.story_id}`)
  await page.locator('.ProseMirror').first().waitFor({ state: 'visible' })
  return story.story_id as string
}

const editor = (page: Page) => page.locator('.ProseMirror').first()

test('typed text survives a full reload after autosave', async ({ page, request }) => {
  await openEditorInFreshStory(page, request)

  const marker = `E2E-autosave-marker-${Date.now()}`
  await editor(page).click()
  // Found live (2026-09-22): typing immediately after click/End race the
  // editor's own focus handling — the first ~8 characters were silently
  // dropped (content came back as "save-marker-..." after reload, missing
  // "E2E-auto"). A brief settle after focus, before the first keystroke,
  // fixed it — a known contenteditable/synthetic-input timing issue, not an
  // autosave defect.
  await page.keyboard.press('End')
  await page.waitForTimeout(300)
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
  await openEditorInFreshStory(page, request)

  // Found live (2026-09-22): a fresh story's chapter starts with EMPTY
  // content — Control+A on an empty editor selects nothing, so the original
  // version of this test bolded nothing and the post-reload snapshot showed
  // only the editor's own placeholder text. Type real content first.
  await editor(page).click()
  await page.waitForTimeout(300)
  await page.keyboard.type('a word to make bold')
  await page.keyboard.press('Control+A')
  await page.keyboard.press('Control+B')
  await page.waitForTimeout(3000)

  await page.reload()
  await editor(page).waitFor({ state: 'visible' })
  // Found live (2026-09-22): the <strong> mark IS present in the DOM right
  // after reload (confirmed via the page snapshot), but a synchronous
  // .count() call right after the editor container becomes visible can
  // still race the ProseMirror content actually hydrating from the loaded
  // chapter. expect(...).toHaveCount() auto-retries; a bare .count() does not.
  await expect(editor(page).locator('strong, b')).not.toHaveCount(0)
})
