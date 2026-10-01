// Task 11.7 — the copyright-risk score and disclaimer render correctly in
// Analyze → Copyright Risk. Mocked API; no model. The response mirrors what the
// backend now guarantees: the headline is never below the worst finding, the
// model's note is passed through, and the disclaimer is always present.
import { test, expect, type Route } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { mockApi, signIn, workspaceUrl, STORY_ID } from './mockApi'

const json = (r: Route, b: unknown, status = 200) =>
  r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) }).then(() => true)

const DISCLAIMER =
  'This is automated copyright/plagiarism RISK guidance to help you make your writing more original — ' +
  'not legal advice, and not a guarantee. It cannot detect every similarity and may flag generic tropes. ' +
  'Consult a qualified professional for legal questions.'

test.beforeEach(async ({ page }) => { await signIn(page) })

test('11.7: overall risk, findings (worst first), note and disclaimer render for a whole-story check', async ({ page }) => {
  let calls = 0
  await mockApi(page, [
    (r, m, p) => m === 'POST' && p === `/api/stories/${STORY_ID}/copyright-risk`
      ? (calls++, json(r, {
          story_id: STORY_ID, scope: 'project', units_analyzed: 3, overall_risk: 'high', findings_count: 2,
          findings: [
            { finding_id: 1, risk_type: 'trope_overuse', risk_score: 'low', description: 'A chosen-one setup.',
              problematic_excerpt: '', is_generic_trope: true, rewrite_suggestion: 'Complicate the prophecy.' },
            { finding_id: 2, risk_type: 'character', risk_score: 'high', description: 'Resembles a well-known boy wizard.',
              problematic_excerpt: 'the boy with the scar', is_generic_trope: false, rewrite_suggestion: 'Change the distinctive marks.' },
          ],
          note: 'One notable similarity.', disclaimer: DISCLAIMER,
        }))
      : false,
  ])
  await page.goto(workspaceUrl('analyze'))
  await page.getByRole('button', { name: /Copyright Risk/ }).first().click()
  await page.getByRole('button', { name: /Check Whole Story/ }).click()

  await expect(page.getByText('Overall risk')).toBeVisible()
  // The headline (a paragraph) — the finding badge also says HIGH.
  await expect(page.getByRole('paragraph').filter({ hasText: /^HIGH$/ })).toBeVisible()
  await expect(page.getByText('3 chapter(s) · 2 finding(s)')).toBeVisible()
  // Findings are ordered worst first.
  const first = page.getByText('Resembles a well-known boy wizard.')
  const second = page.getByText('A chosen-one setup.')
  await expect(first).toBeVisible()
  await expect(second).toBeVisible()
  const [y1, y2] = [(await first.boundingBox())!.y, (await second.boundingBox())!.y]
  expect(y1).toBeLessThan(y2)
  await expect(page.getByText('One notable similarity.')).toBeVisible()
  await expect(page.getByText(DISCLAIMER)).toBeVisible()
  expect(calls).toBe(1)

  const a11y = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  expect(a11y.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical').map((v) => v.id)).toEqual([])
})

test('11.7: a failed analysis tells the author to try again and shows no stale result', async ({ page }) => {
  await mockApi(page, [
    (r, m, p) => m === 'POST' && p === `/api/stories/${STORY_ID}/copyright-risk`
      ? json(r, { detail: 'Copyright risk analysis could not be completed. Please try again.' }, 503)
      : false,
  ])
  await page.goto(workspaceUrl('analyze'))
  await page.getByRole('button', { name: /Copyright Risk/ }).first().click()
  await page.getByRole('button', { name: /Check Whole Story/ }).click()
  await expect(page.getByText('Copyright risk analysis could not be completed. Please try again.')).toBeVisible()
  await expect(page.getByText('Overall risk')).toHaveCount(0)
})
