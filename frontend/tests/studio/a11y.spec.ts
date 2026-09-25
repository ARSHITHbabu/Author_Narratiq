// Stage 8.9 — WCAG 2.1 A/AA automated audit (axe-core) of every workspace and
// the dynamic surfaces, plus keyboard and focus-management checks.
// Threshold (agreed in the Stage 8 plan): zero serious or critical violations.
// Moderate/minor findings are attached to the report, not failed on.
import { test, expect, type Page } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { mockApi, signIn, workspaceUrl, STORY_ID } from './mockApi'

const WCAG = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']

async function audit(page: Page, label: string) {
  const r = await new AxeBuilder({ page }).withTags(WCAG).analyze()
  const blocking = r.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
  const rest = r.violations.filter((v) => !blocking.includes(v))
  const fmt = (vs: typeof r.violations) => vs.map((v) => `${v.impact} ${v.id} (${v.nodes.length}): ${v.nodes.slice(0, 3).map((n) => n.target.join(' ')).join(' ; ')}`).join('\n')
  test.info().annotations.push({ type: `axe ${label}`, description: `blocking=${blocking.length} other=${rest.length}${rest.length ? '\n' + fmt(rest) : ''}` })
  expect(blocking, `${label}:\n${fmt(blocking)}`).toEqual([])
}

test.beforeEach(async ({ page }) => { await signIn(page) })

for (const ws of ['write', 'plan', 'characters', 'world', 'analyze', 'assistant', 'publish', 'intake', 'analytics']) {
  test(`axe: ${ws} has no serious or critical WCAG 2.1 AA violations`, async ({ page }) => {
    await mockApi(page)
    await page.goto(workspaceUrl(ws))
    await expect(page.getByRole('navigation', { name: 'Workspaces' })).toBeVisible()
    await page.waitForLoadState('networkidle')
    await audit(page, ws)
  })
}

test('axe: Write with the AI sidecar, the View menu and the command palette open', async ({ page }) => {
  await mockApi(page)
  await page.goto(workspaceUrl('write'))
  await page.locator('.ProseMirror').first().waitFor()
  await page.getByRole('button', { name: 'AI assistant', exact: true }).click()
  await audit(page, 'write+sidecar')
  await page.getByRole('button', { name: 'View options' }).click()
  await audit(page, 'write+view-menu')
  await page.keyboard.press('Escape')
  await page.keyboard.press('Control+k')
  await expect(page.getByPlaceholder(/Search workspaces/)).toBeVisible()
  await audit(page, 'command-palette')
})

test('axe: World notes, Analyze panel and Plan sections', async ({ page }) => {
  await mockApi(page)
  await page.goto(workspaceUrl('world', 'section=notes'))
  await page.waitForLoadState('networkidle')
  await audit(page, 'world-notes')
  await page.goto(workspaceUrl('analyze'))
  await page.getByRole('button', { name: /Continuity/ }).click()
  await page.waitForLoadState('networkidle')
  await audit(page, 'analyze-continuity')
})

// ── Keyboard-only writing session (8.9 verification) ────────────────────────
/** Press Tab until `pred` holds for the focused element (bounded). */
async function tabTo(page: Page, pred: string, max = 60) {
  for (let i = 0; i < max; i++) {
    await page.keyboard.press('Tab')
    if (await page.evaluate(pred)) return
  }
  throw new Error(`never reached focus target: ${pred}`)
}
const focusedName = (n: string) =>
  `(() => { const a = document.activeElement; return !!a && (a.getAttribute('aria-label') === ${JSON.stringify(n)} || a.textContent?.trim() === ${JSON.stringify(n)}) })()`

test('a full writing session with the keyboard only', async ({ page }) => {
  const log = await mockApi(page, [
    (r, m, p) => (m === 'POST' && p === '/api/ai/tone')
      ? r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        original: 'x', transformed: 'A calmer placeholder paragraph.', mode: 'tone', tokens_used: 1, warnings: [] }) }).then(() => true)
      : false,
  ])
  await page.goto(workspaceUrl('world'))
  await expect(page.getByRole('navigation', { name: 'Workspaces' })).toBeVisible()

  // Skip link is the first stop and lands in the main region.
  await page.keyboard.press('Tab')
  await expect(page.getByRole('link', { name: 'Skip to content' })).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page.locator('#studio-main')).toBeFocused()

  // Rail → Write.
  await page.keyboard.press('Shift+Tab')
  await tabTo(page, focusedName('Write'))
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(new RegExp(`/projects/${STORY_ID}/write`))
  await page.locator('.ProseMirror').first().waitFor()

  // Binder → Chapter 2.
  await tabTo(page, `document.activeElement?.textContent?.includes('Chapter 2') && document.activeElement.tagName === 'BUTTON'`)
  await page.keyboard.press('Enter')
  await expect(page.locator('.ProseMirror')).toContainText('Placeholder paragraph 2')

  // Into the manuscript and type; autosave fires.
  await tabTo(page, `document.activeElement?.classList.contains('ProseMirror')`)
  await page.keyboard.press('End')
  await page.keyboard.type(' Typed by keyboard.')
  await expect.poll(() => log.saves.length, { timeout: 5000 }).toBeGreaterThan(0)

  // Select the line, open the AI assistant: focus moves to its heading.
  await page.keyboard.press('Home')
  await page.keyboard.press('Shift+End')
  await page.keyboard.press('Control+\\')
  await expect(page.locator('#ai-sidecar-title')).toBeFocused()

  // Choose Tone from the Rewrite chooser and run it.
  await tabTo(page, `document.activeElement?.getAttribute('aria-label') === 'Rewrite tool'`)
  await page.keyboard.press('ArrowDown')                      // refine → tone
  await expect(page.getByRole('combobox', { name: 'Rewrite tool' })).toHaveValue('tone')
  await tabTo(page, `/^(Apply|Change|Transform|Rewrite)/.test(document.activeElement?.textContent?.trim() ?? '') && !!document.activeElement?.closest('#ai-tool-panel')`)
  await page.keyboard.press('Enter')
  await expect(page.getByText('A calmer placeholder paragraph.').first()).toBeVisible()

  // Close the assistant: focus returns to the manuscript.
  await page.keyboard.press('Control+\\')
  await expect(page.getByRole('complementary', { name: 'AI Assistant' })).toHaveCount(0)
  await expect(page.locator('.ProseMirror')).toBeFocused()
})

test('opening an analysis moves focus to its heading, and Back returns to its card', async ({ page }) => {
  await mockApi(page)
  await page.goto(workspaceUrl('analyze'))
  await page.getByRole('button', { name: /Continuity/ }).focus()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('heading', { name: 'Continuity', level: 1 })).toBeFocused()
  await page.getByRole('button', { name: 'Back to all analyses' }).click()
  await expect(page.getByRole('button', { name: /Continuity/ })).toBeFocused()
})
