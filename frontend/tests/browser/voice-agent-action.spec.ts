import { test, expect, type APIRequestContext, type Page } from '@playwright/test'

// Stage 6 task 6.4 — critical journey: voice agent -> the correct tool
// actually executes (not just "a command was heard").
//
// Real audio input cannot be simulated through a real microphone in this
// environment. Checked live during Stage 6 closure (2026-09-22):
// components/voice/VoiceAgentPanel.tsx has NO text-command fallback input at
// all (confirmed by reading the component source — only a Mic button; the
// original spec's getByPlaceholder guess was wrong, there is nothing to find).
// So this test drives the same REST endpoint the real mic flow calls into
// once speech-to-text has produced a transcript (POST /api/voice/interpret —
// see routers/voice_agent.py), using the REAL logged-in browser page's own
// auth context (not a bare API test) — this validates intent routing and
// action execution end to end, which is what "the correct tool runs" is
// actually about; it does not validate microphone capture itself, and this
// test does not claim to.
//
//   E2E_EMAIL=… E2E_PASSWORD=… E2E_STORY_ID=… (a story with a chapter that
//   has content, so "summarize this chapter" has something to summarize)
//   npx playwright test tests/browser/voice-agent-action.spec.ts --project=browser

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
  await page.locator('.ProseMirror').first().waitFor({ state: 'visible' })
}

test('a "summarize this chapter" command routes to the correct tool and executes', async ({ page, request }) => {
  test.setTimeout(90_000)
  await openProject(page, request)

  const { token } = await authSession(request)
  const chaptersRes = await request.get(`${API_URL}/api/stories/${STORY_ID}/chapters`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  expect(chaptersRes.ok()).toBe(true)
  const chapters = await chaptersRes.json()
  expect(chapters.length, 'fixture story needs at least one chapter').toBeGreaterThan(0)
  const chapterId = chapters[0].chapter_id

  const interpretRes = await page.request.post(`${API_URL}/api/voice/interpret`, {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      transcript: 'Summarize this chapter',
      context: { story_id: STORY_ID, chapter_id: chapterId },
    },
  })
  expect(interpretRes.ok(), await interpretRes.text()).toBe(true)
  const result = await interpretRes.json()

  // Found live (2026-09-22): the real success value is "succeeded", not
  // "success" as VoiceAgentResponse's docstring default implied.
  expect(result.status, JSON.stringify(result)).toBe('succeeded')
  expect(result.target_router || result.capability, 'no tool was routed to').toBeTruthy()
  expect(result.user_message || Object.keys(result.result || {}).length > 0,
    'no user-facing result and no result payload — looks unexecuted').toBeTruthy()
})
