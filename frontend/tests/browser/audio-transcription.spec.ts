import path from 'path'
import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
import { seedBrowserSession, sessionToken } from './_session'

// Stage 6 task 6.4 — critical journey: upload audio -> transcript -> note.
// Stage 12 Tranche 3 (A21): automated with a committed speech fixture.
//
// The fixture (fixtures/audio/dictation-fixture.wav) is synthetic speech made
// offline with espeak-ng; fixtures/audio/README.md holds the exact spoken text
// and the command that regenerates it. faster-whisper's silence filter turns a
// silent or tone file into an empty transcript, so only real speech can pass.
//
// The test checks CONTENT, not "some text appeared":
//   1. Assistant workspace -> "Saved dictation → note" toggle (AudioPanel is
//      mounted only when it is open) -> upload the fixture;
//   2. the upload reaches `completed` and its raw transcript contains at least
//      KEYWORD_MIN of the fixture's distinctive words (API, so a weak UI match
//      can never stand in for transcription);
//   3. the transcript card shows that text;
//   4. "Append to Note" into the fixture note; the note's stored content now
//      holds the transcript;
//   5. after a reload the upload is still shown as appended, and the note in the
//      World workspace shows the transcript.
//
//   E2E_EMAIL=… E2E_PASSWORD=… E2E_STORY_ID=… E2E_NOTE_ID=… \
//     npx playwright test tests/browser/audio-transcription.spec.ts --project=browser
// (seed with backend/scripts/seed_browser_fixtures.py: the "audio-transcription"
// block. E2E_AUDIO_FIXTURE_PATH overrides the committed fixture.)

const EMAIL = process.env.E2E_EMAIL
const PASSWORD = process.env.E2E_PASSWORD
const STORY_ID = process.env.E2E_STORY_ID
const NOTE_ID = process.env.E2E_NOTE_ID
const AUDIO_FIXTURE_PATH = process.env.E2E_AUDIO_FIXTURE_PATH
  ?? path.join(__dirname, 'fixtures', 'audio', 'dictation-fixture.wav')

// Must match fixtures/audio/README.md.
const NOTE_TITLE = 'Dictation inbox'
const KEYWORDS = ['lighthouse', 'keeper', 'marigold', 'lantern', 'midnight', 'logbook', 'fishing', 'boats', 'storm']
const KEYWORD_MIN = 6

test.skip(!EMAIL || !PASSWORD || !STORY_ID || !NOTE_ID,
  'Set E2E_EMAIL, E2E_PASSWORD, E2E_STORY_ID and E2E_NOTE_ID.')

const API_URL = process.env.E2E_API_URL ?? 'http://localhost:8000'
let cachedToken: string | null = null

async function authSession(request: APIRequestContext) {
  if (!cachedToken) {
    const res = await request.post(`${API_URL}/api/auth/login`, { data: { email: EMAIL, password: PASSWORD } })
    expect(res.ok(), `login failed: ${res.status()}`).toBe(true)
    cachedToken = sessionToken(res)
  }
  return cachedToken!
}

function keywordsIn(text: string): string[] {
  const low = text.toLowerCase()
  return KEYWORDS.filter((k) => low.includes(k))
}

async function openDictation(page: Page) {
  await page.goto(`/projects/${STORY_ID}/assistant`)
  await page.getByRole('button', { name: /Saved dictation/ }).click()
  await expect(page.getByText('Audio Notes')).toBeVisible({ timeout: 15_000 })
}

test('audio upload: real transcript, appended to a note, still there after a reload', async ({ page, request }) => {
  test.setTimeout(300_000)
  const token = await authSession(request)
  const auth = { Authorization: `Bearer ${token}` }
  await seedBrowserSession(page, token)
  await page.setViewportSize({ width: 1366, height: 768 })

  const before = await request.get(`${API_URL}/api/stories/${STORY_ID}/audio`, { headers: auth })
  expect(before.ok()).toBe(true)
  const known = new Set((await before.json()).map((u: { audio_id: string }) => u.audio_id))

  // 1. Upload through the UI.
  await openDictation(page)
  await page.locator('input[type=file][accept*=".wav"]').setInputFiles(AUDIO_FIXTURE_PATH)
  await expect(page.getByText('Upload started — transcription in progress')).toBeVisible({ timeout: 30_000 })

  // 2. The new upload completes with the fixture's words (CPU Whisper + Qwen cleanup).
  let upload: any = null
  await expect.poll(async () => {
    const res = await request.get(`${API_URL}/api/stories/${STORY_ID}/audio`, { headers: auth })
    upload = (await res.json()).find((u: { audio_id: string }) => !known.has(u.audio_id)) ?? null
    return upload?.status ?? 'missing'
  }, { timeout: 240_000, intervals: [3_000] }).toBe('completed')
  const raw: string = upload.raw_transcript ?? ''
  const found = keywordsIn(raw)
  expect(found.length, `raw transcript ${JSON.stringify(raw)} matched only ${found}`).toBeGreaterThanOrEqual(KEYWORD_MIN)

  // 3. The card in the panel shows the transcript (the panel polls every 5 s).
  const card = page.locator('div.rounded-xl', { has: page.getByText('completed', { exact: true }) })
    .filter({ hasText: /lighthouse/i }).first()
  await expect(card).toBeVisible({ timeout: 30_000 })

  // 4. Append it to the fixture note.
  await card.getByPlaceholder('Note ID to append to').fill(NOTE_ID!)
  await card.getByRole('button', { name: 'Append to Note' }).click()
  await expect(page.getByText('Transcript appended to note')).toBeVisible({ timeout: 15_000 })
  const notes = await request.get(`${API_URL}/api/ocr/${STORY_ID}/notes`, { headers: auth })
  const note = (await notes.json()).find((n: { note_id: string }) => n.note_id === NOTE_ID)
  expect(note, 'fixture note missing').toBeTruthy()
  expect(keywordsIn(note.content).length, `note content ${JSON.stringify(note.content)}`)
    .toBeGreaterThanOrEqual(KEYWORD_MIN)

  // 5. Persistence after a reload: the upload stays appended, the note shows the text.
  await page.reload()
  await openDictation(page)
  const after = await request.get(`${API_URL}/api/stories/${STORY_ID}/audio/${upload.audio_id}`, { headers: auth })
  expect((await after.json()).confirmed).toBe(true)
  await expect(page.getByText('Appended to note').first()).toBeVisible({ timeout: 15_000 })

  await page.goto(`/projects/${STORY_ID}/world?section=notes`)
  await page.getByRole('tab', { name: /^Notes$/ }).click()
  await page.getByRole('button', { name: new RegExp(NOTE_TITLE) }).click()
  await expect(page.locator('textarea').first()).toHaveValue(/lighthouse/i, { timeout: 15_000 })
})
