// Stage 12.3 — owner decision OD-09: Writing Suggestions (task 5.13) had no way
// in from the studio since the June 2026 workspace redesign (commit 34dc303).
// Restored as a tool in the Write sidecar's Generate group. Mocked API; no model.
import { test, expect, type Page, type Route } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { mockApi, signIn, workspaceUrl } from './mockApi'
import { waitForChapterContent } from './helpers'

const json = (r: Route, b: unknown, status = 200) =>
  r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) }).then(() => true)

const SUGGESTIONS = {
  tokens_used: 512,
  suggestions: [
    { id: 1, category: 'Unclear stakes', text: 'x', reason: 'x', priority: 'high',
      observation: 'The second paragraph never says what Mira loses if the tide gate fails.',
      recommendation: 'Name the cost in one concrete line before she reaches the gate.' },
    { id: 2, category: 'Over-explained beat', text: 'y', reason: 'y', priority: 'low',
      observation: 'Her fear is stated after the reader has already seen her hands shake.',
      recommendation: 'Cut "she was afraid" and let the shaking hands carry it.' },
  ],
}

async function openSuggestions(page: Page) {
  await page.goto(workspaceUrl('write'))
  await waitForChapterContent(page)
  await page.getByRole('button', { name: 'AI assistant', exact: true }).click()
  const sidecar = page.getByRole('complementary', { name: 'AI Assistant' })
  await expect(sidecar).toBeVisible()
  await sidecar.getByRole('tab', { name: 'Generate' }).click()
  await sidecar.getByRole('radio', { name: 'Suggestions' }).click()
  return sidecar
}

test.beforeEach(async ({ page }) => { await signIn(page) })

test('OD-09: Suggestions is reachable from Write → AI assistant → Generate and shows observation, fix and priority', async ({ page }) => {
  const bodies: any[] = []
  const log = await mockApi(page, [
    (r, m, p) => {
      if (m === 'POST' && p === '/api/ai/suggestions') { bodies.push(r.request().postDataJSON()); return json(r, SUGGESTIONS) }
      return false
    },
  ])
  const sidecar = await openSuggestions(page)
  await sidecar.getByRole('button', { name: 'Get Suggestions' }).click()
  const list = sidecar.getByRole('list', { name: 'Writing suggestions' })
  await expect(list.getByRole('listitem')).toHaveCount(2)
  await expect(list.getByText('Unclear stakes')).toBeVisible()
  await expect(list.getByText('high priority')).toBeVisible()
  await expect(list.getByText(/never says what Mira loses/)).toBeVisible()
  await expect(list.getByText(/Name the cost in one concrete line/)).toBeVisible()
  await expect(sidecar.getByTestId('suggestions-scope')).toHaveText('Feedback on the start of this chapter (no selection).')
  expect(bodies).toHaveLength(1)
  expect(bodies[0].text.length).toBeGreaterThan(0)
  expect(bodies[0].chapter_id).toBeTruthy()
  // The Write workspace's own background reads (story bible, note cards) are not mocked here;
  // what matters is that no AI call went unmocked.
  expect(log.unmatched.filter((c) => c.includes('/api/ai/'))).toEqual([])
  const axe = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  expect(axe.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical').map((v) => v.id)).toEqual([])
})

test('OD-09: a failed request shows the honest error and no stale list', async ({ page }) => {
  await mockApi(page, [
    (r, m, p) => m === 'POST' && p === '/api/ai/suggestions'
      ? json(r, { detail: 'Writing suggestions could not be generated. Please try again.' }, 422) : false,
  ])
  const sidecar = await openSuggestions(page)
  await sidecar.getByRole('button', { name: 'Get Suggestions' }).click()
  await expect(page.getByText('Writing suggestions could not be generated. Please try again.')).toBeVisible()
  await expect(sidecar.getByRole('list', { name: 'Writing suggestions' }).getByRole('listitem')).toHaveCount(0)
})
