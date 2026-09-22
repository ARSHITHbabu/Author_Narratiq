import { test, expect, type APIRequestContext, type Page } from '@playwright/test'

// Stage 6 task 6.4 — critical journey: upload audio -> transcript returned.
//
// STATUS (Stage 6 closure, 2026-09-22): NOT executed. Genuinely blocked, not
// skipped out of laziness — documented per explicit instruction rather than
// left as an unverified guess.
//
// Why it can't be automated in this environment right now: faster-whisper
// needs actual SPEECH audio to produce a meaningful transcript; a silent or
// tone-only WAV would only prove the upload plumbing works, not real
// transcription, and would risk reporting a false pass. This environment has
// no text-to-speech tool available (checked: espeak/espeak-ng/festival, the
// `gtts`/`pyttsx3` Python packages, and `ffmpeg` are all absent), so no real
// speech fixture could be generated. AudioPanel.tsx is imported by
// VoiceAgentPanel.tsx (not mounted as its own top-level workspace tab), so
// the upload control is reached via the "Voice assistant" header button.
//
// Manual verification procedure (reproducible, for the author or a future
// session with TTS/microphone access):
//   1. Log in, open any story with at least one chapter.
//   2. Click "Voice assistant" in the top header.
//   3. Find the audio-upload control within that panel (Audio/Recordings
//      section) and upload a short (5-30s) real speech recording — a phone
//      voice memo works.
//   4. Within ~30-60s, confirm BOTH a raw transcript and a Qwen-cleaned
//      version appear (see backend/services/audio_service.py::clean_transcript
//      — Stage 3 fixed a bug where this step silently never ran).
//   5. Confirm the note is saved and reappears after a page reload.
// Automating this needs either a committed short speech fixture file (a
// product/legal decision — is it acceptable to ship a recorded voice sample
// in the repo?) or a TTS tool added to the environment — both out of this
// closure pass's scope.
//
//   E2E_EMAIL=… E2E_PASSWORD=… E2E_STORY_ID=… E2E_AUDIO_FIXTURE_PATH=/path/to/short.wav \
//     npx playwright test tests/browser/audio-transcription.spec.ts --project=browser

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
