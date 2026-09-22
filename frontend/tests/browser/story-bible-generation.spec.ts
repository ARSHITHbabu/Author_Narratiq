import { test, expect, type APIRequestContext, type Page } from '@playwright/test'

// Stage 6 task 6.4 — critical journey: generate story bible -> five sections
// render with provenance. Same conventions/caveats as autosave-persistence.spec.ts
// (written 2026-09-22, not executed against a live browser render as part of
// this change). Needs a story with at least a couple of chapters so
// generation has real content to work from.
//
//   E2E_EMAIL=… E2E_PASSWORD=… E2E_STORY_ID=… npx playwright test --project=browser

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

const SECTIONS = ['characters', 'locations', 'timeline', 'world', 'themes']

test('generating the story bible renders all five sections with citations', async ({ page, request }) => {
  const { token, user } = await authSession(request)
  await page.addInitScript(([t, u]) => {
    window.localStorage.setItem('narratiq_token', t)
    window.localStorage.setItem('narratiq_user', u)
  }, [token, user])
  await page.goto(`/projects/${STORY_ID}`)

  const storyBibleTab = page.getByTitle(/story bible/i).first()
  if (await storyBibleTab.count()) {
    await storyBibleTab.click()
  }

  const generateButton = page.getByRole('button', { name: /generate/i }).first()
  await generateButton.click()

  // Generation is 5 real sequential Qwen calls per Stage 2 — genuinely slow.
  for (const section of SECTIONS) {
    await expect(page.getByText(new RegExp(section, 'i')).first()).toBeVisible({ timeout: 180_000 })
  }

  // Provenance: the checklist requires citation evidence, not just prose —
  // matches the "[Ch N]" citation convention used elsewhere in the app
  // (continuity-check, manuscript-report).
  await expect(page.getByText(/\[Ch\s*\d+/i).first()).toBeVisible()
})
