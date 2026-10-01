// Stage 11 (Phase 2 §19 P2-06): the Story Bible tells the author when the
// chapters changed after it was generated. Mocked API; no model.
import { test, expect, type Route } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { mockApi, signIn, workspaceUrl, STORY_ID } from './mockApi'

const json = (r: Route, b: unknown, status = 200) =>
  r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) }).then(() => true)

const bible = (is_stale: boolean | null) => ({
  bible_id: 'b1', story_id: STORY_ID, title: 'Story Bible', version: 2, status: 'completed',
  failed_sections: [], created_at: '2026-10-01T10:00:00Z', updated_at: '2026-10-01T10:05:00Z',
  content_json: JSON.stringify({ characters: 'Devika — keeper of the lighthouse.', locations: 'The lighthouse.',
    timeline: 'Chapter 1: the storm.', world_rules: 'None recorded.', themes: 'Trust.' }),
  is_stale,
})

const NOTICE = 'Your chapters have changed since this Story Bible was generated.'

test.beforeEach(async ({ page }) => { await signIn(page) })

test('P2-06: a stale bible shows the notice, keeps its content and offers Regenerate', async ({ page }) => {
  await mockApi(page, [
    (r, m, p) => m === 'GET' && p === `/api/stories/${STORY_ID}/story-bible` ? json(r, bible(true)) : false,
  ])
  await page.goto(workspaceUrl('world', 'section=bible'))
  await expect(page.getByText(NOTICE)).toBeVisible()
  await expect(page.getByText('Devika — keeper of the lighthouse.')).toBeVisible()   // still readable
  await expect(page.getByRole('button', { name: 'Regenerate', exact: true })).toBeVisible()
  const a11y = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  expect(a11y.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical').map((v) => v.id)).toEqual([])
})

for (const value of [false, null]) {
  test(`P2-06: no notice when is_stale is ${value}`, async ({ page }) => {
    await mockApi(page, [
      (r, m, p) => m === 'GET' && p === `/api/stories/${STORY_ID}/story-bible` ? json(r, bible(value)) : false,
    ])
    await page.goto(workspaceUrl('world', 'section=bible'))
    await expect(page.getByText('Devika — keeper of the lighthouse.')).toBeVisible()
    await expect(page.getByText(NOTICE)).toHaveCount(0)
  })
}
