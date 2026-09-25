// Stage 8.1 / 8.8 — workspace navigation: every rail item routes, every tool opens
// in its one home, sub-routes belong to their parent, Notes/Threads not duplicated.
import { test, expect } from '@playwright/test'
import { mockApi, signIn, workspaceUrl, STORY_ID } from './mockApi'

const RAIL = [
  ['write', 'Write'], ['plan', 'Plan'], ['characters', 'Characters'], ['world', 'World'],
  ['analyze', 'Analyze'], ['assistant', 'Assistant'], ['publish', 'Publish'],
] as const

test.beforeEach(async ({ page }) => { await signIn(page); await mockApi(page) })

const rail = (page: import('@playwright/test').Page) => page.getByRole('navigation', { name: 'Workspaces' })

test('every rail item routes to its workspace and is marked current', async ({ page }) => {
  await page.goto(workspaceUrl('write'))
  for (const [id, label] of RAIL) {
    await rail(page).getByRole('button', { name: label, exact: true }).click()
    await expect(page).toHaveURL(new RegExp(`/projects/${STORY_ID}/${id}(\\?|$)`))
    await expect(rail(page).getByRole('button', { name: label, exact: true })).toHaveAttribute('aria-current', 'page')
    await expect(rail(page).locator('[aria-current="page"]')).toHaveCount(1)
  }
})

test('keyboard shortcuts Ctrl+1..7 switch workspaces', async ({ page }) => {
  await page.goto(workspaceUrl('write'))
  await page.locator('.ProseMirror').first().waitFor()
  for (let i = RAIL.length - 1; i >= 0; i--) {
    await page.keyboard.press(`Control+${i + 1}`)
    await expect(page).toHaveURL(new RegExp(`/${RAIL[i][0]}(\\?|$)`))
  }
})

for (const sub of ['intake', 'analytics']) {
  test(`/${sub} belongs to Analyze in the rail and breadcrumb`, async ({ page }) => {
    await page.goto(workspaceUrl(sub))
    await expect(rail(page).getByRole('button', { name: 'Analyze', exact: true })).toHaveAttribute('aria-current', 'page')
    await expect(page.locator('header')).toContainText('Analyze')
  })
}

test('Plan offers Plot Assistant and Pacing only, and points to World for notes', async ({ page }) => {
  await page.goto(workspaceUrl('plan'))
  const tabs = page.getByRole('tablist', { name: 'Plan sections' }).getByRole('tab')
  await expect(tabs).toHaveText([/Plot Assistant/, /Pacing/])
  await page.getByRole('link', { name: /Notes and ideas live in World/ }).click()
  await expect(page).toHaveURL(/\/world\?section=notes/)
  await expect(page.getByRole('tab', { name: 'Notes', exact: true })).toHaveAttribute('aria-selected', 'true')
})

test('Notes and the Idea Shelf have one home: World', async ({ page }) => {
  await page.goto(workspaceUrl('world'))
  const tabs = page.getByRole('tablist', { name: 'World sections' }).getByRole('tab')
  await expect(tabs).toHaveText([/Story Bible/, /Notes/, /Scan \(OCR\)/])
  if (process.env.STUDIO_VARIANT === 'p3-off') return      // no Idea Shelf in the rollback build
  await page.goto(workspaceUrl('world', 'section=notes&tab=ideas'))
  await expect(page.getByRole('tab', { name: 'Ideas' })).toHaveAttribute('aria-selected', 'true')
})

test('Narrative Threads has one home: Analyze', async ({ page }) => {
  await page.goto(workspaceUrl('analyze'))
  await page.getByRole('button', { name: /Narrative Threads/ }).click()
  await expect(page.getByText('Narrative Threads').first()).toBeVisible()
  for (const ws of ['plan', 'world']) {
    await page.goto(workspaceUrl(ws))
    await expect(page.getByRole('tab', { name: /Threads/ })).toHaveCount(0)
  }
})

test('section tabs follow the WAI-ARIA tab pattern and are remembered per story', async ({ page }) => {
  await page.goto(workspaceUrl('world'))
  await page.getByRole('tab', { name: 'Story Bible' }).focus()
  await page.keyboard.press('ArrowRight')
  await expect(page.getByRole('tab', { name: 'Notes', exact: true })).toBeFocused()
  await expect(page.getByRole('tab', { name: 'Notes', exact: true })).toHaveAttribute('aria-selected', 'true')
  await page.goto(workspaceUrl('write'))
  await page.goto(workspaceUrl('world'))
  await expect(page.getByRole('tab', { name: 'Notes', exact: true })).toHaveAttribute('aria-selected', 'true')
})

test('Search & replace opens in Write with Ctrl+F and from the palette', async ({ page }) => {
  await page.goto(workspaceUrl('write'))
  await page.locator('.ProseMirror').first().waitFor()
  await page.keyboard.press('Control+f')
  await expect(page.getByPlaceholder(/search/i).first()).toBeVisible()
  await page.keyboard.press('Escape')
  await page.goto(workspaceUrl('plan'))
  await page.keyboard.press('Control+k')
  await page.getByPlaceholder(/Search workspaces/).fill('search & replace')
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/\/write/)
  await expect(page.getByPlaceholder(/search/i).first()).toBeVisible()
})

test('palette deep links open a tool in its home', async ({ page }) => {
  await page.goto(workspaceUrl('write'))
  await page.locator('.ProseMirror').first().waitFor()
  for (const [query, url, tab] of [
    ['Go to Notes', /world\?section=notes/, 'Notes'],
    ['Go to Pacing', /plan\?section=pacing/, 'Pacing'],
    ['Go to Story Bible', /world\?section=bible/, 'Story Bible'],
  ] as const) {
    await page.keyboard.press('Control+k')
    await page.getByPlaceholder(/Search workspaces/).fill(query)
    await page.keyboard.press('Enter')
    await expect(page).toHaveURL(url)
    await expect(page.getByRole('tab', { name: tab, exact: true })).toHaveAttribute('aria-selected', 'true')
  }
})
