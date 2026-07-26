import { test, expect, type APIRequestContext, type Page } from '@playwright/test'

// Phase 2 QA Issue 6 — "the OCR section appears empty". Checklist task 3.10.
//
//   E2E_EMAIL=… E2E_PASSWORD=… E2E_STORY_ID=… E2E_NO_CHAPTER_STORY_ID=… \
//     npx playwright test --project=browser tests/browser/ocr-panel.spec.ts
//
// The second story id must be a story with NO chapters — the exact condition under
// which the panel used to render nothing at all.

const EMAIL = process.env.E2E_EMAIL
const PASSWORD = process.env.E2E_PASSWORD
const STORY_ID = process.env.E2E_STORY_ID
const NO_CHAPTER_STORY_ID = process.env.E2E_NO_CHAPTER_STORY_ID

test.skip(!EMAIL || !PASSWORD || !STORY_ID || !NO_CHAPTER_STORY_ID,
  'Set E2E_EMAIL, E2E_PASSWORD, E2E_STORY_ID and E2E_NO_CHAPTER_STORY_ID.')

const API_URL = process.env.E2E_API_URL ?? 'http://localhost:8000'
let cached: { token: string; user: string } | null = null

async function signIn(page: Page, request: APIRequestContext) {
  if (!cached) {
    const res = await request.post(`${API_URL}/api/auth/login`, { data: { email: EMAIL, password: PASSWORD } })
    expect(res.ok(), `login failed: ${res.status()}`).toBe(true)
    const body = await res.json()
    cached = { token: body.access_token, user: JSON.stringify(body.user) }
  }
  await page.addInitScript(([t, u]) => {
    window.localStorage.setItem('narratiq_token', t)
    window.localStorage.setItem('narratiq_user', u)
  }, [cached.token, cached.user])
}

const uploadControl = (page: Page) => page.locator('input[type=file]')
const destination = (page: Page, label: string) => page.getByRole('button', { name: label, exact: true })

async function openOcr(page: Page, storyId: string) {
  await page.goto(`/projects/${storyId}/world`)
  await page.getByRole('button', { name: /Scan \(OCR\)/ }).click()
}

test.beforeEach(async ({ page, request }) => {
  await signIn(page, request)
  await page.setViewportSize({ width: 1366, height: 768 })
})

test('the OCR panel renders an upload control on a story with chapters', async ({ page }) => {
  await openOcr(page, STORY_ID!)
  await expect(page.getByText('Upload handwritten note photo')).toBeVisible()
  await expect(uploadControl(page)).toHaveCount(1)
  for (const d of ['Story Notes', 'Current Chapter Draft', 'Note Card', 'Character Profile']) {
    await expect(destination(page, d)).toBeHidden()   // destinations appear after extraction
  }
})

test('the OCR panel renders an upload control on a story with NO chapters (QA Issue 6)', async ({ page }) => {
  await openOcr(page, NO_CHAPTER_STORY_ID!)
  await expect(page.getByText('Upload handwritten note photo')).toBeVisible()
  await expect(uploadControl(page)).toHaveCount(1)
  await expect(page.getByTestId('ocr-chapter-hint')).toContainText('no chapters yet')
})

test('the chapter hint explains what is unavailable without hiding the feature', async ({ page }) => {
  await openOcr(page, NO_CHAPTER_STORY_ID!)
  const hint = page.getByTestId('ocr-chapter-hint')
  await expect(hint).toBeVisible()
  await expect(hint).toContainText('notes, note cards and character profiles')
  // The scan workflow itself is fully present.
  await expect(page.getByText('JPEG, PNG, WebP, HEIC — drag & drop or click')).toBeVisible()
})

test('a story with chapters shows no chapter hint', async ({ page }) => {
  await openOcr(page, STORY_ID!)
  await expect(page.getByText('Upload handwritten note photo')).toBeVisible()
  await expect(page.getByTestId('ocr-chapter-hint')).toHaveCount(0)
})

test('the OCR tab renders without a page error in either story', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  await openOcr(page, NO_CHAPTER_STORY_ID!)
  await expect(page.getByText('Upload handwritten note photo')).toBeVisible()
  await openOcr(page, STORY_ID!)
  await expect(page.getByText('Upload handwritten note photo')).toBeVisible()
  expect(errors, `page errors: ${errors.join(' | ')}`).toHaveLength(0)
})
