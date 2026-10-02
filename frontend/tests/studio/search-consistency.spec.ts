// Stage 12 remediation A9 — the editor half of the search equivalence check.
//
// Every case in backend/tests/fixtures/search_match_cases.json is loaded into the
// REAL editor as chapter content (TipTap parses the same HTML the backend
// searches), searched through the real Search panel, and the distinct
// highlighted matches are counted. The backend test asserts the same `count`
// for the same HTML, so backend count == editor highlights.
//
// Also: pending typing is saved before a replace request leaves the browser,
// so a reload after the replace cannot discard or overwrite it.
import { test, expect, type Page, type Route } from '@playwright/test'
import { readFileSync } from 'fs'
import { join } from 'path'
import { mockApi, signIn, workspaceUrl, STORY_ID, CHAPTER_IDS } from './mockApi'
import { waitForChapterContent, focusEditorSettled } from './helpers'

const CASES: Array<{ id: string; html: string; query: string; whole_word: boolean; case_sensitive: boolean; count: number }> =
  JSON.parse(readFileSync(join(__dirname, '../../../backend/tests/fixtures/search_match_cases.json'), 'utf8')).cases

const json = (r: Route, b: unknown, status = 200) =>
  r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) }).then(() => true)

const CH1 = CHAPTER_IDS[0]
const chapterBody = (content: string) => ({
  chapter_id: CH1, story_id: STORY_ID, chapter_number: 1, title: 'Chapter 1', word_count: 10,
  created_at: '2026-10-02T00:00:00Z', updated_at: '2026-10-02T00:00:00Z', content,
})

async function distinctHits(page: Page): Promise<number> {
  return page.evaluate(() => new Set(
    Array.from(document.querySelectorAll('[data-search-match]')).map((e) => e.getAttribute('data-search-match')),
  ).size)
}

async function openSearch(page: Page) {
  await page.keyboard.press('Control+f')
  const input = page.getByPlaceholder(/Search across manuscript/i)
  await expect(input).toBeVisible()
  return input
}

test.beforeEach(async ({ page }) => { await signIn(page) })

for (const c of CASES) {
  test(`A9 equivalence: ${c.id} → ${c.count} match(es) in the editor`, async ({ page }) => {
    await mockApi(page, [
      (r, m, p) => m === 'GET' && p === `/api/stories/${STORY_ID}/chapters/${CH1}` ? json(r, chapterBody(c.html)) : false,
      (r, m, p) => m === 'POST' && p === `/api/search/exact/${STORY_ID}`
        ? json(r, { query: c.query, total_matches: c.count, chapters_hit: c.count ? 1 : 0,
            results: c.count ? [{ chapter_id: CH1, chapter_number: 1, chapter_title: 'Chapter 1', match_count: c.count,
              matches: Array.from({ length: c.count }, () => ({ context_before: '', match_text: c.query, context_after: '' })) }] : [] })
        : false,
    ])
    await page.goto(workspaceUrl('write'))
    await waitForChapterContent(page)
    const input = await openSearch(page)
    if (c.case_sensitive) await page.getByRole('button', { name: 'Match case' }).click()
    if (c.whole_word) await page.getByRole('button', { name: 'Whole word' }).click()
    await input.fill(c.query)
    await input.press('Enter')
    if (c.count > 0) await expect.poll(() => distinctHits(page)).toBe(c.count)
    else {
      await expect(page.getByText('No matches', { exact: true })).toBeVisible()
      expect(await distinctHits(page)).toBe(0)
    }
  })
}

test('A9: the whole-word and case options are labelled and off by default', async ({ page }) => {
  await mockApi(page)
  await page.goto(workspaceUrl('write'))
  await waitForChapterContent(page)
  await openSearch(page)
  for (const name of ['Whole word', 'Match case']) {
    const b = page.getByRole('button', { name })
    await expect(b).toHaveAttribute('aria-pressed', 'false')
    await expect(b).toHaveAttribute('title', /.+/)
  }
})

test('A9: unsaved typing is saved before a replace is sent, and never lost to the reload', async ({ page }) => {
  let stored = '<p>The harbour was quiet.</p>'
  const order: string[] = []
  await mockApi(page, [
    (r, m, p) => {
      if (p !== `/api/stories/${STORY_ID}/chapters/${CH1}`) return false
      if (m === 'GET') return json(r, chapterBody(stored))
      if (m === 'PUT' || m === 'PATCH') {
        stored = (r.request().postDataJSON() ?? {}).content ?? stored
        order.push('save')
        return json(r, chapterBody(stored))
      }
      return false
    },
    (r, m, p) => m === 'POST' && p === `/api/search/exact/${STORY_ID}`
      ? (order.push('search'), json(r, { query: 'harbour', total_matches: 1, chapters_hit: 1,
          results: [{ chapter_id: CH1, chapter_number: 1, chapter_title: 'Chapter 1', match_count: 1,
            matches: [{ context_before: 'The ', match_text: 'harbour', context_after: ' was quiet.' }] }] }))
      : false,
    (r, m, p) => {
      if (!(m === 'POST' && p === `/api/search/replace/${STORY_ID}`)) return false
      order.push('replace')
      // The server sees the saved text — including what was just typed.
      expect(stored).toContain('Wren arrived.')
      stored = stored.replace('harbour', 'port')
      return json(r, { dry_run: false, replaced_count: 1, chapters_affected: 1,
        preview: [{ chapter_id: CH1, chapter_number: 1, chapter_title: 'Chapter 1', match_count: 1 }] })
    },
  ])
  await page.goto(workspaceUrl('write'))
  await waitForChapterContent(page)
  await focusEditorSettled(page)
  await page.locator('.ProseMirror p').first().click()
  await page.keyboard.press('End')
  await page.keyboard.type(' Wren arrived.')
  // Search and replace immediately — inside the 1.5 s autosave window.
  const input = await openSearch(page)
  await input.fill('harbour')
  await input.press('Enter')
  await expect(page.getByText('1 match across 1 chapter')).toBeVisible()
  await page.getByRole('button', { name: 'Replace', exact: true }).click()
  await page.getByPlaceholder('Replace with…').fill('port')
  await page.getByRole('button', { name: 'Replace one' }).click()
  await expect.poll(() => order.includes('replace')).toBe(true)
  expect(order.indexOf('save')).toBeGreaterThan(-1)
  expect(order.indexOf('save')).toBeLessThan(order.indexOf('replace'))
  await expect(page.locator('.ProseMirror')).toContainText('Wren arrived.')
  await expect(page.locator('.ProseMirror')).toContainText('The port was quiet.')
})
