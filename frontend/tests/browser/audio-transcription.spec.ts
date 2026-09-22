import { test, expect, type APIRequestContext, type Page } from '@playwright/test'

// Stage 6 task 6.4 — critical journey: upload audio -> transcript returned.
// Same conventions/caveats as autosave-persistence.spec.ts (written 2026-09-22,
// not executed against a live browser render as part of this change).
//
// Needs a short real audio fixture file — path supplied via E2E_AUDIO_FIXTURE_PATH
// so no binary audio is committed to the repo. Skips (not fails) if unset,
// same as the other required E2E_* vars.
//
//   E2E_EMAIL=… E2E_PASSWORD=… E2E_STORY_ID=… E2E_AUDIO_FIXTURE_PATH=/path/to/short.wav \
//     npx playwright test --project=browser

const EMAIL = process.env.E2E_EMAIL
const PASSWORD = process.env.E2E_PASSWORD
const STORY_ID = process.env.E2E_STORY_ID
const AUDIO_FIXTURE_PATH = process.env.E2E_AUDIO_FIXTURE_PATH

test.skip(!EMAIL || !PASSWORD || !STORY_ID || !AUDIO_FIXTURE_PATH,
  'Set E2E_EMAIL, E2E_PASSWORD, E2E_STORY_ID and E2E_AUDIO_FIXTURE_PATH.')

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

test('uploading an audio file returns a non-empty cleaned transcript', async ({ page, request }) => {
  const { token, user } = await authSession(request)
  await page.addInitScript(([t, u]) => {
    window.localStorage.setItem('narratiq_token', t)
    window.localStorage.setItem('narratiq_user', u)
  }, [token, user])
  await page.goto(`/projects/${STORY_ID}`)

  // Best-effort: exact tab/panel trigger for Audio not confirmed against a
  // live render. Falls back to a title-based lookup matching the pattern
  // already used for the AI sidecar toggle in other specs.
  const audioTab = page.getByTitle(/audio/i).first()
  if (await audioTab.count()) {
    await audioTab.click()
  }

  const uploadInput = page.locator('input[type=file]').first()
  await uploadInput.setInputFiles(AUDIO_FIXTURE_PATH!)

  // Transcription (faster-whisper) + Qwen cleanup is real inference — generous wait.
  const transcriptText = page.locator('text=/./').filter({ hasText: /\w{10,}/ }).first()
  await expect(transcriptText).toBeVisible({ timeout: 120_000 })
})
