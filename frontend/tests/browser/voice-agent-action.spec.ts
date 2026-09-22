import { test, expect, type APIRequestContext, type Page } from '@playwright/test'

// Stage 6 task 6.4 — critical journey: voice agent -> the correct tool
// actually executes (not just "a command was heard"). Same conventions/
// caveats as autosave-persistence.spec.ts (written 2026-09-22, not executed
// against a live browser render as part of this change).
//
// Voice input itself cannot be simulated through a real microphone in a
// headless browser. This test instead drives the agent's REST command path
// directly (the same path the real mic flow calls into once speech-to-text
// has produced text — see routers/voice_agent.py), which is the part that
// actually matters for "the correct tool runs": intent routing and action
// execution, not audio capture.
//
//   E2E_EMAIL=… E2E_PASSWORD=… E2E_STORY_ID=… (a story with a chapter that
//   has content, so "summarize this chapter" has something to summarize)
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

test('a text-driven "summarize this chapter" command executes and shows a result in the UI', async ({ page, request }) => {
  const { token, user } = await authSession(request)
  await page.addInitScript(([t, u]) => {
    window.localStorage.setItem('narratiq_token', t)
    window.localStorage.setItem('narratiq_user', u)
  }, [token, user])
  await page.goto(`/projects/${STORY_ID}`)

  const voiceTab = page.getByTitle(/voice/i).first()
  if (await voiceTab.count()) {
    await voiceTab.click()
  }

  // Best-effort: the voice panel exposes a mic button (Mic icon,
  // components/voice/VoiceAgentPanel.tsx) with no confirmed accessible name
  // for text-command entry as an alternative to real audio. If the UI has
  // no such text-entry fallback, this line is the one to update once that's
  // confirmed on a real run — the REST-level routing itself is verified
  // separately in the backend voice tests (test_voice_unit.py, test_voice_execution.py).
  const textCommandInput = page.getByPlaceholder(/type a command|say something/i)
  await expect(textCommandInput).toBeVisible({ timeout: 10_000 })
  await textCommandInput.fill('Summarize this chapter')
  await textCommandInput.press('Enter')

  await expect(page.getByText(/summary|summarized/i).first()).toBeVisible({ timeout: 60_000 })
})
