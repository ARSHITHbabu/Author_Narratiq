// Stage 12.3 — Phase 3 P3-02 acceptance (checklist 7.3): "⌘Z undoes an applied
// AI result in one step". The apply path is the single-transaction
// replaceRange; this proves it in a real browser with the real editor
// (mocked API: the behaviour under test is entirely in the editor, and a
// deterministic AI response makes the before/after text exact).
import { test, expect, type Route } from '@playwright/test'
import { mockApi, signIn, workspaceUrl } from './mockApi'
import { waitForChapterContent, focusEditorSettled } from './helpers'

const json = (r: Route, b: unknown, status = 200) =>
  r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) }).then(() => true)

const REWRITE = 'A rewritten paragraph that the AI returned, clearly different from the original text.'

test.beforeEach(async ({ page }) => { await signIn(page) })

test('7.3 / P3-02: one ⌘Z (Ctrl+Z) undoes an applied AI result completely', async ({ page }) => {
  await mockApi(page, [
    (r, m, p) => m === 'POST' && p === '/api/ai/tone'
      ? json(r, { original: '', transformed: REWRITE, mode: 'tone', tokens_used: 12, no_change: false,
          reason: null, strength_violation: false, preservation_violations: [], failed: false, warnings: [] })
      : false,
  ])
  await page.goto(workspaceUrl('write'))
  await waitForChapterContent(page)
  const first = page.locator('.ProseMirror p').first()
  const original = (await first.textContent()) ?? ''
  expect(original.length).toBeGreaterThan(0)

  await page.getByRole('button', { name: 'AI assistant', exact: true }).click()
  await page.getByRole('combobox', { name: 'Rewrite tool' }).selectOption('tone')
  await focusEditorSettled(page)
  await first.click({ clickCount: 3 })
  await page.locator('#ai-tool-panel').getByRole('button', { name: /Apply|Change|Transform|Rewrite/ }).last().click()
  await page.getByRole('button', { name: /Replace Selection/ }).first().click()
  await expect(first).toHaveText(REWRITE)

  await page.locator('.ProseMirror').focus()
  await page.keyboard.press('ControlOrMeta+z')                 // exactly one undo
  await expect(first).toHaveText(original)
  await expect(page.locator('.ProseMirror')).not.toContainText(REWRITE)
})
