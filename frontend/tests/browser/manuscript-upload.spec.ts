import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
import { seedBrowserSession, sessionToken } from './_session'

// Stage 6 task 6.4 critical journey — upload a manuscript → chapters populate.
//
// Until Stage 12 (remediation A8) there was no upload control anywhere in the
// UI and this spec was written to fail until one existed. The control now lives
// in the Write binder ("Import manuscript…"). This is the real end-to-end flow
// against a live stack: choose a .txt file in the browser, the backend saves
// every chapter (numbered AFTER the story's existing chapters) and then prepares
// them for AI tools in the background, and the binder shows them.
//
// Needs the "manuscript-upload" story from backend/scripts/seed_browser_fixtures.py
// (two chapters already present):
//   E2E_EMAIL=… E2E_PASSWORD=… E2E_STORY_ID=… [E2E_API_URL=… E2E_BASE_URL=…]
//   npx playwright test tests/browser/manuscript-upload.spec.ts --project=browser

const EMAIL = process.env.E2E_EMAIL
const PASSWORD = process.env.E2E_PASSWORD
const STORY_ID = process.env.E2E_STORY_ID

test.skip(!EMAIL || !PASSWORD || !STORY_ID, 'Set E2E_EMAIL, E2E_PASSWORD and E2E_STORY_ID.')

const API_URL = process.env.E2E_API_URL ?? 'http://localhost:8000'
let cachedToken: string | null = null

async function token(request: APIRequestContext) {
  if (!cachedToken) {
    const res = await request.post(`${API_URL}/api/auth/login`, { data: { email: EMAIL, password: PASSWORD } })
    expect(res.ok(), `login failed: ${res.status()}`).toBe(true)
    cachedToken = sessionToken(res)
  }
  return cachedToken
}

async function chapters(request: APIRequestContext) {
  const res = await request.get(`${API_URL}/api/stories/${STORY_ID}/chapters`, {
    headers: { Authorization: `Bearer ${await token(request)}` },
  })
  expect(res.ok()).toBe(true)
  return (await res.json()) as { chapter_number: number; title: string }[]
}

async function openWrite(page: Page, request: APIRequestContext) {
  await seedBrowserSession(page, await token(request))
  await page.goto(`/projects/${STORY_ID}/write`)
  await page.getByTestId('import-manuscript').waitFor({ state: 'visible' })
}

const MANUSCRIPT = [
  'Chapter 1: The Causeway Road',
  'The tide had not yet turned when Wren reached the causeway.',
  '',
  'She counted the posts as she walked.',
  'Chapter 2: The Keeper',
  'The keeper had left his log open at an unfinished page.',
].join('\n')

test('import a .txt manuscript from the Write binder: chapters appended, numbered after the existing ones', async ({ page, request }) => {
  test.setTimeout(10 * 60_000)        // AI preparation of the new chapters runs on the live model
  const before = await chapters(request)
  const highest = Math.max(0, ...before.map((c) => c.chapter_number))

  await openWrite(page, request)
  await page.getByTestId('import-manuscript').click()
  const dialog = page.getByTestId('manuscript-import-dialog')
  await expect(dialog).toContainText(`added after your existing ${before.length} chapter`)
  await page.getByTestId('manuscript-file-input').setInputFiles({
    name: 'causeway.txt', mimeType: 'text/plain', buffer: Buffer.from(MANUSCRIPT),
  })
  await page.getByTestId('manuscript-import-start').click()
  await expect(page.getByTestId('manuscript-import-preparing')).toContainText('2 chapters saved to your story.')

  // Saved before preparation finishes: the database already has them, numbered after the existing ones.
  const after = await chapters(request)
  const added = after.filter((c) => !before.some((b) => b.chapter_number === c.chapter_number))
  expect(added.map((c) => c.chapter_number)).toEqual([highest + 1, highest + 2])
  expect(added.map((c) => c.title)).toEqual(['The Causeway Road', 'The Keeper'])
  expect(new Set(after.map((c) => c.chapter_number)).size).toBe(after.length)

  // The binder shows them without a page reload.
  await expect(page.getByText('The Causeway Road')).toBeVisible()

  // Preparation for AI tools ends honestly: complete, or a partial notice that keeps the text.
  await expect(page.getByTestId('manuscript-import-done').or(page.getByTestId('manuscript-import-partial')))
    .toBeVisible({ timeout: 9 * 60_000 })
})

test('an unsupported file is refused in the browser and nothing is uploaded', async ({ page, request }) => {
  const before = await chapters(request)
  await openWrite(page, request)
  await page.getByTestId('import-manuscript').click()
  await page.getByTestId('manuscript-file-input').setInputFiles({
    name: 'novel.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4'),
  })
  await expect(page.getByRole('alert')).toContainText('Choose a .txt or .docx file')
  await expect(page.getByTestId('manuscript-import-start')).toBeDisabled()
  expect((await chapters(request)).length).toBe(before.length)
})
