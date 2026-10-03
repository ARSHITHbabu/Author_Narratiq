import { test, expect, type APIRequestContext, type Response } from '@playwright/test'
import { seedBrowserSession, sessionToken } from './_session'

// Stage 12.1 (task 4.1 manual check, PA-C1): ask a whole-story question while
// Chapter 1 is open, live, through the real UI and backend.
//   * "This chapter" (the default) must stay spoiler-safe: the evidence comes
//     only from Chapter 1, and the badge says "this chapter".
//   * "Full manuscript" must reach later chapters, and the badge says so.
// The assertions are on what the backend reports it searched (scope_used, the
// passage chapters and, for creative/mixed intent, the summary chapters) and
// what the panel shows, not on answer wording. The model picks the intent, so
// the evidence check covers both kinds. (First live run, Stage 12.1: a
// "creative" classification exposed that the metadata omitted summaries.)
//
//   E2E_EMAIL=… E2E_PASSWORD=… E2E_STORY_ID=… (the seed_fixture.py story, 3 chapters)
//   npx playwright test tests/browser/plot-assistant-scope.spec.ts --project=browser

const EMAIL = process.env.E2E_EMAIL
const PASSWORD = process.env.E2E_PASSWORD
const STORY_ID = process.env.E2E_STORY_ID

test.skip(!EMAIL || !PASSWORD || !STORY_ID, 'Set E2E_EMAIL, E2E_PASSWORD and E2E_STORY_ID.')

const API_URL = process.env.E2E_API_URL ?? 'http://localhost:8000'
const QUESTION = 'What happens across the whole story, and how does it end?'

async function login(request: APIRequestContext) {
  const res = await request.post(`${API_URL}/api/auth/login`, { data: { email: EMAIL, password: PASSWORD } })
  expect(res.ok(), `login failed: ${res.status()}`).toBe(true)
  return sessionToken(res)
}

test('a whole-story question from Chapter 1: chapter scope stays in Chapter 1, full scope reaches later chapters', async ({ page, request }) => {
  test.setTimeout(4 * 60 * 1000)
  await seedBrowserSession(page, await login(request))
  await page.goto(`/projects/${STORY_ID}/plan?section=plot`)
  const scope = page.getByRole('group', { name: 'Search scope' })
  await expect(scope.getByRole('button', { name: 'This chapter' })).toHaveAttribute('aria-pressed', 'true', { timeout: 30_000 })

  const ask = async () => {
    await page.getByPlaceholder(/Ask a story question/).fill(QUESTION)
    const [res] = await Promise.all([
      page.waitForResponse((r: Response) => r.url().includes('/api/plot-assistant') && r.request().method() === 'POST', { timeout: 150_000 }),
      page.getByRole('button', { name: 'Ask the plot assistant' }).click(),
    ])
    expect(res.status()).toBe(200)
    return { sent: res.request().postDataJSON(), body: await res.json() }
  }
  const evidence = (body: any): number[] =>
    [...body.retrieval.chapters_covered, ...(body.retrieval.summary_chapters ?? [])]

  const chapter = await ask()
  expect(chapter.sent.current_chapter_number).toBe(1)
  expect(chapter.sent.scope).toBe('chapter')
  expect(chapter.body.scope_used).toBe('chapter')
  expect(evidence(chapter.body).length).toBeGreaterThan(0)
  expect(evidence(chapter.body).every((n) => n <= 1)).toBe(true)
  await expect(page.getByText('this chapter', { exact: true })).toBeVisible()
  console.log('chapter scope', chapter.body.mode, JSON.stringify(chapter.body.retrieval))

  await scope.getByRole('button', { name: 'Full manuscript' }).click()
  const full = await ask()
  expect(full.sent.scope).toBe('full')
  expect(full.body.scope_used).toBe('full')
  expect(evidence(full.body).some((n) => n > 1)).toBe(true)
  await expect(page.getByText('full manuscript', { exact: true })).toBeVisible()
  await expect(page.getByText(/(Based on \d+ passage\(s\)|Ideas based on the summaries) .*chapter\(s\)/).first()).toBeVisible()
  console.log('full scope', full.body.mode, JSON.stringify(full.body.retrieval))
})
