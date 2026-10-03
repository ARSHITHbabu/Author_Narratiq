// Stage 12.1 (PA-C1, task 4.1 / D-1): the Plot Assistant's search scope is
// spoiler-safe "This chapter" by default, the author can switch to the full
// manuscript, the request carries the chosen scope, and the answer's badge says
// which scope was searched. Mocked API; no model.
import { test, expect, type Route } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { mockApi, signIn, workspaceUrl } from './mockApi'

const json = (r: Route, b: unknown) =>
  r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) }).then(() => true)

test.beforeEach(async ({ page }) => { await signIn(page) })

test('PA-C1: scope defaults to this chapter, can switch to the full manuscript, and is sent and shown', async ({ page }) => {
  const sent: Array<{ scope: string; current_chapter_number: number | null }> = []
  await mockApi(page, [
    (r, m, p) => {
      if (m !== 'POST' || p !== '/api/plot-assistant/') return false
      const body = r.request().postDataJSON()
      sent.push({ scope: body.scope, current_chapter_number: body.current_chapter_number })
      return json(r, {
        session_id: `s${sent.length}`, mode: 'qa', answer: `Answer ${sent.length}.`, suggestions: [],
        context_used: '', tokens_used: 10, scope_used: body.scope,
        retrieval: { chunks_retrieved: 1, chapters_covered: [1], scope_limited: body.scope === 'chapter' },
      })
    },
  ])
  await page.goto(workspaceUrl('plan', 'section=plot'))
  const scope = page.getByRole('group', { name: 'Search scope' })
  const chapterBtn = scope.getByRole('button', { name: 'This chapter' })
  const fullBtn = scope.getByRole('button', { name: 'Full manuscript' })
  await expect(chapterBtn).toHaveAttribute('aria-pressed', 'true')
  await expect(fullBtn).toHaveAttribute('aria-pressed', 'false')

  const box = page.getByPlaceholder(/Ask a story question/)
  await box.fill('Who is the keeper of the lighthouse?')
  await page.getByRole('button', { name: 'Ask the plot assistant' }).click()
  await expect(page.getByText('Answer 1.')).toBeVisible()
  await expect(page.getByText('this chapter', { exact: true })).toBeVisible()

  await fullBtn.click()
  await expect(fullBtn).toHaveAttribute('aria-pressed', 'true')
  await expect(chapterBtn).toHaveAttribute('aria-pressed', 'false')
  await box.fill('How does the story end?')
  await page.getByRole('button', { name: 'Ask the plot assistant' }).click()
  await expect(page.getByText('Answer 2.')).toBeVisible()
  await expect(page.getByText('full manuscript', { exact: true })).toBeVisible()
  await expect(page.getByText('Based on 1 passage(s) from chapter(s) 1')).toBeVisible()

  expect(sent.map((s) => s.scope)).toEqual(['chapter', 'full'])
  const a11y = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  expect(a11y.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical').map((v) => v.id)).toEqual([])
})

test('PA-C1 / task 4.4: creative ideas name the chapter summaries they were based on', async ({ page }) => {
  await mockApi(page, [
    (r, m, p) => m === 'POST' && p === '/api/plot-assistant/' ? json(r, {
      session_id: 's1', mode: 'creative', answer: null, context_used: '', tokens_used: 10, scope_used: 'full',
      suggestions: [{ id: 1, text: 'Let the keeper lie about the storm.', rationale: 'Raises the stakes.' }],
      retrieval: { chunks_retrieved: 0, chapters_covered: [], scope_limited: false, summary_chapters: [1, 2, 3] },
    }) : false,
  ])
  await page.goto(workspaceUrl('plan', 'section=plot'))
  await page.getByRole('group', { name: 'Search scope' }).getByRole('button', { name: 'Full manuscript' }).click()
  await page.getByPlaceholder(/Ask a story question/).fill('Suggest a twist.')
  await page.getByRole('button', { name: 'Ask the plot assistant' }).click()
  await expect(page.getByText('Let the keeper lie about the storm.')).toBeVisible()
  await expect(page.getByText('Ideas based on the summaries of chapter(s) 1, 2, 3')).toBeVisible()
})
