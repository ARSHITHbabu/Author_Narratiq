// Stage 11 (Phase 2 rule R4): the browser must not contact any third party.
// Inter is bundled from @fontsource/inter and served from this origin.
import { test, expect } from '@playwright/test'
import { mockApi, signIn, workspaceUrl } from './mockApi'

test('no request leaves for Google Fonts, and Inter still renders', async ({ page }) => {
  const external: string[] = []
  page.on('request', (r) => {
    if (/fonts\.(googleapis|gstatic)\.com/.test(r.url())) external.push(r.url())
  })
  await signIn(page)
  await mockApi(page)
  await page.goto(workspaceUrl('write'))
  await page.waitForLoadState('networkidle')
  expect(external).toEqual([])
  const interLoaded = await page.evaluate(async () => {
    await document.fonts.ready
    return document.fonts.check('500 16px Inter')
  })
  expect(interLoaded).toBe(true)
  const family = await page.evaluate(() => getComputedStyle(document.body).fontFamily)
  expect(family).toContain('Inter')
})
