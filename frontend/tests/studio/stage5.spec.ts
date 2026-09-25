// Stage 5 behaviour merged from main (PR #2) inside the Stage 8 studio:
// Narrative Threads scan outcome (D1), the saved Manuscript Report (D2) and the
// near-no-op result in the grouped AI sidecar (D4). Mocked API; no model.
import { test, expect, type Page, type Route } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { mockApi, signIn, workspaceUrl, STORY_ID } from './mockApi'
import { waitForChapterContent } from './helpers'

const json = (r: Route, b: unknown, status = 200) =>
  r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) }).then(() => true)

// Same threshold as a11y.spec.ts: zero serious or critical WCAG 2.1 AA findings.
async function noBlockingA11y(page: Page) {
  const r = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  expect(r.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical').map((v) => `${v.id}: ${v.nodes.map((n) => n.html.slice(0, 160)).join(' | ')}`)).toEqual([])
}

test.beforeEach(async ({ page }) => { await signIn(page) })

test('D1: a finished scan with no threads says so in Analyze → Narrative Threads', async ({ page }) => {
  await mockApi(page, [
    (r, m, p) => m === 'GET' && p === `/api/stories/${STORY_ID}/narrative-threads/scan-status`
      ? json(r, { scan_id: 's1', status: 'completed_empty', threads_written: 0, chapters_scanned: 3,
          batches_degraded: 0, error_code: null, started_at: '2026-09-25T00:00:00Z', finished_at: '2026-09-25T00:01:00Z' })
      : false,
  ])
  await page.goto(workspaceUrl('analyze'))
  await page.getByRole('button', { name: /Narrative Threads/ }).click()
  await expect(page.getByText('The scan read 3 chapter(s) and found no narrative threads.')).toBeVisible()
  await noBlockingA11y(page)
})

test('D2: the saved Manuscript Report reloads with its stale notice and a Regenerate button', async ({ page }) => {
  await mockApi(page, [
    (r, m, p) => m === 'GET' && p === `/api/stories/${STORY_ID}/manuscript-report`
      ? json(r, {
          story_id: STORY_ID, chapters_analyzed: 3, word_count_total: 1200, character_arcs: [],
          pacing: { slow_chapters: [], intense_chapters: [], assessment: 'Even pacing.' },
          unresolved_threads: [], strengths: [], improvements: [], analysis_note: '',
          relationship_arcs: [], narrative_signals: [], generated_at: '2026-09-24T10:00:00Z', is_stale: true, degraded: false,
        })
      : false,
  ])
  await page.goto(workspaceUrl('analyze'))
  await page.getByRole('button', { name: /Manuscript Report/ }).click()
  await expect(page.getByText('Your chapters have changed since this report was generated.', { exact: false })).toBeVisible()
  await expect(page.getByRole('button', { name: /Regenerate Report/ })).toBeVisible()
  await noBlockingA11y(page)
})

test('D4: a near-no-op rewrite in the grouped sidecar is shown as unchanged, with no Replace button', async ({ page }) => {
  const reason = 'The AI could not find a meaningful change in this passage.'
  await mockApi(page, [
    (r, m, p) => m === 'POST' && p === '/api/ai/tone'
      ? json(r, { original: 'Placeholder paragraph 1 for layout tests.', transformed: 'Placeholder paragraph 1 for layout tests.',
          mode: 'tone', tokens_used: 5, no_change: true, reason, warnings: [] })
      : false,
  ])
  await page.goto(workspaceUrl('write'))
  await waitForChapterContent(page)
  await page.getByRole('button', { name: 'AI assistant', exact: true }).click()
  await page.getByRole('combobox', { name: 'Rewrite tool' }).selectOption('tone')
  await page.locator('.ProseMirror p').first().click({ clickCount: 3 })
  await page.locator('#ai-tool-panel').getByRole('button', { name: /Apply|Change|Transform|Rewrite/ }).last().click()
  await expect(page.getByTestId('sidebar-no-change')).toHaveText(reason)
  await expect(page.getByRole('button', { name: /Replace Selection|Insert at Cursor/ })).toHaveCount(0)
  await noBlockingA11y(page)
})
