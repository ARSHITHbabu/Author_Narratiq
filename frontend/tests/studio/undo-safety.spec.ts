// Stage 12.3 agent review (HR-15 / HR-17) — opening a chapter was an undoable step.
// Live, typing one sentence into chapter 40 and pressing Ctrl+Z three times emptied the
// whole chapter, and autosave saved the empty document over it (data loss). Loading a
// chapter must never be undone: undo stops at the text as it was opened. Mocked API.
import { test, expect } from '@playwright/test'
import { mockApi, signIn, workspaceUrl } from './mockApi'
import { waitForChapterContent } from './helpers'

test.beforeEach(async ({ page }) => { await signIn(page) })

async function recordSaves(page: import('@playwright/test').Page) {
  const bodies: { path: string; content: string }[] = []
  const log = await mockApi(page, [
    (r, m, p) => {
      if ((m === 'PUT' || m === 'PATCH') && /\/chapters\//.test(p)) {
        const b = r.request().postDataJSON() ?? {}
        if (typeof b.content === 'string') bodies.push({ path: p, content: b.content })
      }
      return false
    },
  ])
  return { log, bodies }
}

test('undo after typing stops at the chapter as it was opened; nothing empty is saved', async ({ page }) => {
  const { bodies } = await recordSaves(page)
  await page.goto(workspaceUrl('write'))
  await waitForChapterContent(page)
  const editor = page.locator('.ProseMirror')
  const original = await editor.innerText()
  await editor.click(); await page.keyboard.press('Control+End')
  await page.keyboard.type(' The tide turned at noon.')
  for (let i = 0; i < 6; i++) { await page.keyboard.press('Control+z'); await page.waitForTimeout(100) }
  await expect(editor).toHaveText(original)
  await page.waitForTimeout(2200)                                   // past the 1.5 s autosave
  for (const b of bodies) expect(b.content).toContain('Placeholder paragraph')
})

test('undo after switching chapters never brings back the previous chapter or empties this one', async ({ page }) => {
  const { bodies } = await recordSaves(page)
  await page.goto(workspaceUrl('write'))
  await waitForChapterContent(page)
  const editor = page.locator('.ProseMirror')
  await editor.click(); await page.keyboard.press('Control+End')
  await page.keyboard.type(' Typed in chapter one.')
  await page.getByRole('button', { name: /Chapter 2\s/ }).first().click()
  await expect(editor).toContainText('Placeholder paragraph 2')
  const chapter2 = await editor.innerText()
  await editor.click()
  for (let i = 0; i < 6; i++) { await page.keyboard.press('Control+z'); await page.waitForTimeout(100) }
  await expect(editor).toHaveText(chapter2)
  await page.waitForTimeout(2200)
  const ch2Saves = bodies.filter((b) => b.content.includes('Placeholder paragraph 2') || !b.content.includes('Placeholder paragraph 1'))
  for (const b of ch2Saves) expect(b.content).toContain('Placeholder paragraph 2')
})
