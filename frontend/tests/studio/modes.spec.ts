// Stage 8.3 / 8.4 / 8.5 — writing-first modes and progressive disclosure:
// Edit (default) vs Draft, Reading mode (read-only, no autosave), Focus/Zen, the
// measured control reduction, and the Stage 7 toolbar-Escape carry-forward (M2).
import { test, expect, type Page } from '@playwright/test'
import { mockApi, signIn, workspaceUrl } from './mockApi'
import { countVisibleControls } from './helpers'

const toolbar = (page: Page) => page.getByRole('toolbar', { name: 'AI actions for the selected text' })
const firstPara = (page: Page) => page.locator('.ProseMirror p').first()
const aiToggle = (page: Page) => page.getByRole('button', { name: 'AI assistant', exact: true })
const rail = (page: Page) => page.getByRole('navigation', { name: 'Workspaces' })
async function openWrite(page: Page) {
  await page.goto(workspaceUrl('write'))
  await page.locator('.ProseMirror').first().waitFor()
}
async function view(page: Page, item: string) {
  await page.getByRole('button', { name: 'View options' }).click()
  await page.getByRole('menuitemcheckbox', { name: item }).click()
}

test.beforeEach(async ({ page }) => { await signIn(page) })

test('Edit is the default mode: selection toolbar and AI assistant are available', async ({ page }) => {
  await mockApi(page); await openWrite(page)
  await expect(page.getByRole('radio', { name: 'Edit' })).toHaveAttribute('aria-checked', 'true')
  await expect(aiToggle(page)).toBeVisible()
  await firstPara(page).click({ clickCount: 3 })
  await expect(toolbar(page)).toBeVisible()
})

test('Draft hides every AI surface, is remembered per story, and Edit brings them back', async ({ page }) => {
  await mockApi(page); await openWrite(page)
  await aiToggle(page).click()
  await expect(page.getByRole('complementary', { name: 'AI Assistant' })).toBeVisible()
  await page.getByRole('radio', { name: 'Draft' }).click()
  await expect(page.getByRole('complementary', { name: 'AI Assistant' })).toHaveCount(0)
  await expect(aiToggle(page)).toHaveCount(0)
  await firstPara(page).click({ clickCount: 3 })
  await expect(toolbar(page)).toHaveCount(0)
  await page.keyboard.press('Control+\\')
  await expect(page.getByRole('complementary', { name: 'AI Assistant' })).toHaveCount(0)

  await page.reload(); await page.locator('.ProseMirror').first().waitFor()
  await expect(page.getByRole('radio', { name: 'Draft' })).toHaveAttribute('aria-checked', 'true')

  await page.getByRole('radio', { name: 'Edit' }).click()
  await expect(page.getByRole('complementary', { name: 'AI Assistant' })).toBeVisible()   // preference kept
})

test('Reading mode is read-only, hides the chrome, and sends no chapter save', async ({ page }) => {
  const log = await mockApi(page); await openWrite(page)
  await view(page, 'Reading mode')
  await expect(page.locator('.ProseMirror')).toHaveAttribute('contenteditable', 'false')
  await expect(page.getByRole('toolbar', { name: 'Formatting' })).toHaveCount(0)
  await expect(rail(page)).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Add chapter' })).toHaveCount(0)
  await firstPara(page).click()
  await page.keyboard.type('xyz')
  await expect(firstPara(page)).not.toContainText('xyz')
  await page.keyboard.press('Escape')
  await expect(page.locator('.ProseMirror')).toHaveAttribute('contenteditable', 'true')
  await expect(rail(page)).toBeVisible()
  await page.waitForTimeout(2200)               // longer than the 1.5 s autosave debounce
  expect(log.saves).toEqual([])
})

test('Focus hides rail, binder and sidecar; Zen hides all chrome and Esc exits', async ({ page }) => {
  await mockApi(page); await openWrite(page)
  await aiToggle(page).click()
  await view(page, 'Focus mode')
  await expect(rail(page)).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Add chapter' })).toHaveCount(0)
  await expect(page.getByRole('complementary', { name: 'AI Assistant' })).toHaveCount(0)
  await page.keyboard.press('Control+.')
  await expect(rail(page)).toBeVisible()
  await view(page, 'Zen mode')
  await expect(page.locator('header')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'View options' })).toHaveCount(0)
  await page.keyboard.press('Escape')
  await expect(page.locator('header')).toBeVisible()
})

test('M2: Escape hides the toolbar, and re-selecting the same words always brings it back', async ({ page }) => {
  await mockApi(page); await openWrite(page)
  // Same gesture as live selection-toolbar test 9: click, Home, Shift+End —
  // the identical range every round. Before the fix, whether the toolbar came
  // back depended on React rendering the momentary collapsed selection.
  for (let i = 0; i < 10; i++) {
    await firstPara(page).click()
    await page.keyboard.press('Home')
    await page.keyboard.press('Shift+End')
    await expect(toolbar(page), `round ${i}: shown`).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(toolbar(page), `round ${i}: dismissed`).toHaveCount(0)
  }
})

// 8.4 — measured reduction in simultaneously visible controls at 1366×768.
// Baseline on main (06850cf + startup fix), same fixture and metric:
//   Write, sidecar closed = 36, sidecar open = 53.
const BASELINE = { closed: 36, open: 53 }
test('progressive disclosure: at least 30% fewer visible controls with the sidecar open', async ({ page }) => {
  await mockApi(page); await openWrite(page)
  const closed = await countVisibleControls(page)
  await aiToggle(page).click()
  await expect(page.getByRole('complementary', { name: 'AI Assistant' })).toBeVisible()
  await page.waitForTimeout(300)
  const open = await countVisibleControls(page)
  test.info().annotations.push({ type: 'controls', description: `closed ${closed.count} (baseline ${BASELINE.closed}); open ${open.count} (baseline ${BASELINE.open})` })
  console.log(`CONTROLS closed=${closed.count} open=${open.count}\n  closed: ${closed.names.join(' | ')}\n  open: ${open.names.join(' | ')}`)
  expect(open.count).toBeLessThanOrEqual(Math.floor(BASELINE.open * 0.7))
  expect(closed.count).toBeLessThan(BASELINE.closed)
})
