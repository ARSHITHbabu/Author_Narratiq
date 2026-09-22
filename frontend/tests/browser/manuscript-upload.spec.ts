import { test, expect, type APIRequestContext, type Page } from '@playwright/test'

// Stage 6 task 6.4 — critical journey: upload a manuscript -> chapters populate.
// Same conventions/caveats as autosave-persistence.spec.ts (written 2026-09-22,
// not executed against a live browser render as part of this change).
//
//   E2E_EMAIL=… E2E_PASSWORD=… E2E_STORY_ID=… (a story with an UPLOAD panel
//   reachable and EMPTY of chapters, so the count assertion is meaningful)
//   npx playwright test --project=browser

const EMAIL = process.env.E2E_EMAIL
const PASSWORD = process.env.E2E_PASSWORD
const STORY_ID = process.env.E2E_STORY_ID

test.skip(!EMAIL || !PASSWORD || !STORY_ID, 'Set E2E_EMAIL, E2E_PASSWORD and E2E_STORY_ID.')

const API_URL = process.env.E2E_API_URL ?? 'http://localhost:8000'
let cachedToken: string | null = null
let cachedUser: string | null = null

async function authSession(request: APIRequestContext) {
  if (!cachedToken || !cachedUser) {
    const res = await request.post(`${API_URL}/api/auth/login`, { data: { email: EMAIL, password: PASSWORD } })
    expect(res.ok(), `login failed: ${res.status()}`).toBe(true)
    const body = await res.json()
    cachedToken = body.access_token
    cachedUser = JSON.stringify(body.user)
  }
  return { token: cachedToken!, user: cachedUser! }
}

async function openProject(page: Page, request: APIRequestContext) {
  const { token, user } = await authSession(request)
  await page.addInitScript(([t, u]) => {
    window.localStorage.setItem('narratiq_token', t)
    window.localStorage.setItem('narratiq_user', u)
  }, [token, user])
  await page.goto(`/projects/${STORY_ID}`)
}

test('uploading a manuscript populates chapters in the sidebar', async ({ page, request }) => {
  await openProject(page, request)

  const chapterListBefore = page.getByRole('list', { name: /chapters/i })
  const beforeCount = await chapterListBefore.locator('li').count().catch(() => 0)

  // Best-effort selector: the manuscript-upload control's exact trigger
  // (button/tab) was not confirmed against a live render — the file input
  // itself follows the same `input[type=file]` convention already proven
  // in ocr-panel.spec.ts.
  const uploadInput = page.locator('input[type=file]').first()
  await uploadInput.setInputFiles({
    name: 'e2e-manuscript.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from(
      'Chapter One\n\nOnce there was a debt that could not be named, and Devika ' +
      'Rao carried it the way she carried everything else — quietly, and alone.\n',
    ),
  })

  await page.waitForTimeout(5000) // upload + parse is async; no explicit completion signal exposed to the test

  const chapterListAfter = page.getByRole('list', { name: /chapters/i })
  const afterCount = await chapterListAfter.locator('li').count()
  expect(afterCount).toBeGreaterThan(beforeCount)
})
