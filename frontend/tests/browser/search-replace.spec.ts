import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
import { seedBrowserSession, sessionToken } from './_session'
import { focusEditorSettled, waitForChapterContent } from '../studio/helpers'

// Stage 12 remediation A9 — search & replace data integrity against a live stack.
// Needs the "search-replace" story from backend/scripts/seed_browser_fixtures.py
// (re-seed before each run: this spec replaces text). Serial: each test builds on
// the chapter as the previous one left it.
//
//   E2E_EMAIL=… E2E_PASSWORD=… E2E_STORY_ID=… [E2E_API_URL=… E2E_BASE_URL=…]
//   npx playwright test tests/browser/search-replace.spec.ts --project=browser

const EMAIL = process.env.E2E_EMAIL
const PASSWORD = process.env.E2E_PASSWORD
const STORY_ID = process.env.E2E_STORY_ID
test.skip(!EMAIL || !PASSWORD || !STORY_ID, 'Set E2E_EMAIL, E2E_PASSWORD and E2E_STORY_ID.')
test.describe.configure({ mode: 'serial' })

const API_URL = process.env.E2E_API_URL ?? 'http://localhost:8000'
let token: string | null = null

async function auth(request: APIRequestContext) {
  if (!token) {
    const res = await request.post(`${API_URL}/api/auth/login`, { data: { email: EMAIL, password: PASSWORD } })
    expect(res.ok()).toBe(true)
    token = sessionToken(res)
  }
  return token!
}

async function chapterHtml(request: APIRequestContext): Promise<string> {
  const h = { Authorization: `Bearer ${await auth(request)}` }
  const list = await (await request.get(`${API_URL}/api/stories/${STORY_ID}/chapters`, { headers: h })).json()
  const ch = await (await request.get(`${API_URL}/api/stories/${STORY_ID}/chapters/${list[0].chapter_id}`, { headers: h })).json()
  return ch.content as string
}

async function openWriteAndSearch(page: Page, request: APIRequestContext, query: string, wholeWord = false) {
  await seedBrowserSession(page, await auth(request))
  await page.goto(`/projects/${STORY_ID}/write`)
  await waitForChapterContent(page)
  await page.keyboard.press('Control+f')
  const input = page.getByPlaceholder(/Search across manuscript/i)
  if (wholeWord) await page.getByRole('button', { name: 'Whole word' }).click()
  await input.fill(query)
  await input.press('Enter')
  return input
}

const distinctHits = (page: Page) => page.evaluate(() => new Set(
  Array.from(document.querySelectorAll('[data-search-match]')).map((e) => e.getAttribute('data-search-match'))).size)

async function shownCount(page: Page): Promise<number> {
  const t = await page.getByText(/^\d+ match(es)? across \d+ chapter/).innerText()
  return Number(t.split(' ')[0])
}

test('count shown = highlights = Replace All preview, across bold and nested formatting', async ({ page, request }) => {
  for (const q of ['Devika', 'old castle']) {
    await openWriteAndSearch(page, request, q)
    await expect(page.getByText(/match(es)? across/)).toBeVisible()
    const shown = await shownCount(page)
    await expect.poll(() => distinctHits(page)).toBe(shown)
    expect(shown).toBe(2)
    await page.getByRole('button', { name: 'Replace', exact: true }).click()
    await page.getByPlaceholder('Replace with…').fill('X')
    await page.getByRole('button', { name: /Replace all \(\d+\)/ }).click()
    await expect(page.getByText(/Replace .* with/)).toBeVisible()             // confirmation step
    await expect(page.locator('body')).toContainText(`${shown} match`)
    await page.keyboard.press('Escape')
  }
})

test('Replace One across formatting changes the occurrence the author selected', async ({ page, request }) => {
  await openWriteAndSearch(page, request, 'old castle')
  await expect(page.getByText('2 matches across 1 chapter')).toBeVisible()
  await page.getByRole('button', { name: 'Replace', exact: true }).click()
  await page.getByPlaceholder('Replace with…').fill('ruin')
  await page.getByRole('button', { name: 'Replace one' }).click()          // the first, active match
  await expect.poll(async () => (await chapterHtml(request)).includes('ruin')).toBe(true)
  const html = await chapterHtml(request)
  expect(html).toContain('the <strong>ruin<em></em></strong>')               // first one, inside the marks
  expect(html).toContain('and the old castle')                              // second one untouched
})

test('replacing "amp" never corrupts &amp; and "<b>hello</b>" is stored as text', async ({ page, request }) => {
  await openWriteAndSearch(page, request, 'amp')
  await expect(page.getByText('1 match across 1 chapter')).toBeVisible()     // "ampersand" only
  await page.getByRole('button', { name: 'Replace', exact: true }).click()
  await page.getByPlaceholder('Replace with…').fill('<b>hello</b>')
  await page.getByRole('button', { name: 'Replace one' }).click()
  await expect.poll(async () => (await chapterHtml(request)).includes('hello')).toBe(true)
  const html = await chapterHtml(request)
  expect(html).toContain('Tom &amp; Jerry')
  expect(html).toContain('&lt;b&gt;hello&lt;/b&gt;ersand')
  expect(html).not.toContain('&X;')
  await expect(page.locator('.ProseMirror')).toContainText('<b>hello</b>ersand')   // shown as text
})

test('typing just before a replace is saved and survives the reload', async ({ page, request }) => {
  await seedBrowserSession(page, await auth(request))
  await page.goto(`/projects/${STORY_ID}/write`)
  await waitForChapterContent(page)
  await focusEditorSettled(page)
  await page.locator('.ProseMirror p').last().click()
  await page.keyboard.press('End')
  await page.keyboard.type(' Wren arrived late.')
  await page.keyboard.press('Control+f')                                     // inside the 1.5 s autosave window
  const input = page.getByPlaceholder(/Search across manuscript/i)
  await input.fill('Jerry')
  await input.press('Enter')
  await expect(page.getByText('1 match across 1 chapter')).toBeVisible()
  await page.getByRole('button', { name: 'Replace', exact: true }).click()
  await page.getByPlaceholder('Replace with…').fill('Spike')
  await page.getByRole('button', { name: 'Replace one' }).click()
  await expect.poll(async () => (await chapterHtml(request)).includes('Spike')).toBe(true)
  const html = await chapterHtml(request)
  expect(html).toContain('Wren arrived late.')
  await expect(page.locator('.ProseMirror')).toContainText('Wren arrived late.')
  await expect(page.locator('.ProseMirror')).toContainText('Tom & Spike')
})
