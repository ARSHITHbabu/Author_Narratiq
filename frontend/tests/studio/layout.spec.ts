// Stage 8.2 — resizable, expandable panels whose layout persists per user.
import { test, expect, type Page } from '@playwright/test'
import { mockApi, signIn, workspaceUrl, USER_A, USER_B } from './mockApi'
import { waitForChapterContent } from './helpers'

const sidecar = (page: Page) => page.getByRole('complementary', { name: 'AI Assistant' })
const openSidecar = async (page: Page) => {
  await page.getByRole('button', { name: 'AI assistant', exact: true }).click()
  await expect(sidecar(page)).toBeVisible()
}
const widthPct = async (page: Page) => {
  const box = (await sidecar(page).boundingBox())!
  return (box.width / page.viewportSize()!.width) * 100
}
const editorReady = (page: Page) => waitForChapterContent(page)

async function logout(page: Page) {
  await page.getByRole('button', { name: 'User menu' }).click()
  await page.getByRole('menuitem', { name: 'Log out' }).click()
  await page.waitForURL(/\/login/)
}
async function login(page: Page, email: string) {
  await page.goto('/login')
  await page.getByPlaceholder('you@example.com').fill(email)
  await page.locator('input[type="password"]').fill('irrelevant-mock')
  await page.locator('button[type="submit"]').click()
  await page.waitForURL(/\/dashboard/)
}

test('dragging the sidecar resizes it and the width survives a reload', async ({ page }) => {
  await signIn(page); await mockApi(page)
  await page.goto(workspaceUrl('write')); await editorReady(page)
  await openSidecar(page)
  const before = await widthPct(page)
  const handle = page.locator('[data-panel-resize-handle-id]').last()
  const hb = (await handle.boundingBox())!
  await page.mouse.move(hb.x + hb.width / 2, hb.y + hb.height / 2)
  await page.mouse.down()
  await page.mouse.move(hb.x - 120, hb.y + hb.height / 2, { steps: 8 })
  await page.mouse.up()
  const resized = await widthPct(page)
  expect(resized).toBeGreaterThan(before + 5)
  await page.reload(); await editorReady(page)
  await expect(sidecar(page)).toBeVisible()
  expect(Math.abs((await widthPct(page)) - resized)).toBeLessThan(1)
})

test('Expand widens the sidecar for detailed work, hides the binder, and persists', async ({ page }) => {
  await signIn(page); await mockApi(page)
  await page.goto(workspaceUrl('write')); await editorReady(page)
  await openSidecar(page)
  const normal = await widthPct(page)
  await page.getByRole('button', { name: 'Expand AI assistant' }).click()
  await expect.poll(() => widthPct(page)).toBeGreaterThan(55)
  await expect(page.getByRole('button', { name: 'Add chapter' })).toHaveCount(0)
  await page.reload(); await editorReady(page)
  await expect.poll(() => widthPct(page)).toBeGreaterThan(55)
  await page.getByRole('button', { name: 'Restore AI assistant width' }).click()
  await expect.poll(async () => Math.abs((await widthPct(page)) - normal)).toBeLessThan(1)
  await expect(page.getByRole('button', { name: 'Add chapter' })).toBeVisible()
})

test('layouts are per user: A resizes, B sees defaults, A gets A\'s layout back', async ({ page }) => {
  await mockApi(page)
  await login(page, USER_A.email)
  await page.goto(workspaceUrl('write')); await editorReady(page)
  await openSidecar(page)
  await page.getByRole('button', { name: 'Expand AI assistant' }).click()
  await expect.poll(() => widthPct(page)).toBeGreaterThan(55)

  await logout(page)
  await login(page, USER_B.email)
  await page.goto(workspaceUrl('write')); await editorReady(page)
  await expect(sidecar(page)).toHaveCount(0)                      // B: default (closed)
  await openSidecar(page)
  expect(await widthPct(page)).toBeLessThan(40)                   // B: default width

  await logout(page)
  await login(page, USER_A.email)
  await page.goto(workspaceUrl('write')); await editorReady(page)
  await expect(sidecar(page)).toBeVisible()                        // A: own layout back
  await expect.poll(() => widthPct(page)).toBeGreaterThan(55)

  const keys = await page.evaluate(() => Object.keys(localStorage).filter((k) => k.startsWith('narratiq_studio')))
  expect(keys.sort()).toEqual(expect.arrayContaining([`narratiq_studio:${USER_A.user_id}`, `narratiq_studio:${USER_B.user_id}`]))
})

test('legacy global layout: sizes migrate once, story memory does not, key is deleted', async ({ page }) => {
  await page.addInitScript(() => {
    if (sessionStorage.getItem('legacy-seeded')) return
    sessionStorage.setItem('legacy-seeded', '1')
    localStorage.setItem('narratiq_studio', JSON.stringify({ version: 0, state: {
      binderSize: 27, sidecarSize: 33, railCollapsed: false, sidecarOpen: true,
      byStory: { 'someone-elses-story': { lastWorkspace: 'analyze' } }, lastStoryId: 'someone-elses-story',
    } }))
  })
  await signIn(page); await mockApi(page)
  await page.goto(workspaceUrl('write')); await editorReady(page)
  const stored = await page.evaluate((id) => ({
    legacy: localStorage.getItem('narratiq_studio'),
    mine: JSON.parse(localStorage.getItem(`narratiq_studio:${id}`) ?? '{}').state,
  }), USER_A.user_id)
  expect(stored.legacy).toBeNull()
  expect(stored.mine.binderSize).toBe(27)
  expect(stored.mine.sidecarSize).toBe(33)
  expect(stored.mine.sidecarOpen).toBe(false)                     // not a size — not migrated
  expect(Object.keys(stored.mine.byStory ?? {})).not.toContain('someone-elses-story')
  expect(stored.mine.lastStoryId).not.toBe('someone-elses-story')
})
