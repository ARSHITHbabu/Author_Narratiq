import path from 'path'
import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
import { seedBrowserSession, sessionToken } from './_session'

// Stage 12.1 (Gate 2) — checklist task 3.10's end-to-end journey, automated:
// image upload → real GOT-OCR2.0 extraction → extracted text reviewed → "Current
// Chapter Draft" → the text is in the chapter in the Write editor, and still there
// after a reload. ocr-panel.spec.ts covers the panel itself (no extraction).
//
// The image (fixtures/ocr/printed-note.png, see its README) is PRINTED text: this
// checks the workflow, not handwriting quality. Needs the GPU (GOT-OCR loads on
// first use, so the first extraction can take a minute).
//
//   E2E_EMAIL=… E2E_PASSWORD=… E2E_STORY_ID=… \
//     npx playwright test tests/browser/ocr-to-editor.spec.ts --project=browser
// (seed with backend/scripts/seed_browser_fixtures.py: the "ocr-to-editor" block,
// a story with one chapter; re-seed before each run, the spec adds text to it.)

const EMAIL = process.env.E2E_EMAIL
const PASSWORD = process.env.E2E_PASSWORD
const STORY_ID = process.env.E2E_STORY_ID
const IMAGE = path.join(__dirname, 'fixtures', 'ocr', 'printed-note.png')

test.skip(!EMAIL || !PASSWORD || !STORY_ID, 'Set E2E_EMAIL, E2E_PASSWORD and E2E_STORY_ID.')

const API_URL = process.env.E2E_API_URL ?? 'http://localhost:8000'
let cachedToken: string | null = null

async function signIn(page: Page, request: APIRequestContext) {
  if (!cachedToken) {
    const res = await request.post(`${API_URL}/api/auth/login`, { data: { email: EMAIL, password: PASSWORD } })
    expect(res.ok(), `login failed: ${res.status()}`).toBe(true)
    cachedToken = sessionToken(res)
  }
  await seedBrowserSession(page, cachedToken)
  return cachedToken
}

test('OCR: upload → extraction → Current Chapter Draft → text in the editor, after a reload too', async ({ page, request }) => {
  test.setTimeout(300_000)
  const token = await signIn(page, request)
  await page.setViewportSize({ width: 1366, height: 768 })

  // 1. Upload and extract in World → Scan (OCR).
  await page.goto(`/projects/${STORY_ID}/world`)
  await page.getByRole('tab', { name: /Scan \(OCR\)/ }).click()
  await page.locator('input[type=file]').setInputFiles(IMAGE)
  await page.getByRole('button', { name: /Extract Text/ }).click()

  // 2. The extracted text is shown for review (real model; GOT-OCR may load first).
  const review = page.locator('textarea').first()
  await expect(review).toHaveValue(/harbour lamp holds/i, { timeout: 240_000 })
  await expect(review).toHaveValue(/keeps the keys/i)

  // 3. Send it to the current chapter draft.
  await page.getByRole('button', { name: 'Current Chapter Draft', exact: true }).click()
  await page.getByRole('button', { name: /Confirm & Save to Project/ }).click()
  await expect(page.getByText('Saved to Current Chapter Draft')).toBeVisible({ timeout: 30_000 })

  // 4. The stored chapter holds it (API), and the Write editor shows it.
  // The list omits chapter text; read the chapter itself.
  const auth = { headers: { Authorization: `Bearer ${token}` } }
  const [chapter] = await (await request.get(`${API_URL}/api/stories/${STORY_ID}/chapters`, auth)).json()
  const stored = await (await request.get(`${API_URL}/api/stories/${STORY_ID}/chapters/${chapter.chapter_id}`, auth)).json()
  expect(stored.content).toMatch(/harbour lamp holds/i)
  expect(stored.content).toContain('Wren climbed to the lamp room.')

  await page.goto(`/projects/${STORY_ID}/write`)
  const editor = page.locator('.ProseMirror')
  await expect(editor).toContainText(/harbour lamp holds/i, { timeout: 30_000 })
  await expect(editor).toContainText('Wren climbed to the lamp room.')   // the existing text is kept

  // 5. Persisted: still there after a reload.
  await page.reload()
  await expect(page.locator('.ProseMirror')).toContainText(/harbour lamp holds/i, { timeout: 30_000 })
})
