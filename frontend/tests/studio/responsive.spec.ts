// Stage 8.10 — viewport matrix: no horizontal page scroll on any workspace,
// the editor keeps a usable width, and every rail item stays reachable.
import { test, expect } from '@playwright/test'
import { mockApi, signIn, workspaceUrl } from './mockApi'
import { hasHorizontalScroll, waitForChapterContent } from './helpers'

const VIEWPORTS = [
  [1920, 1080], [1536, 864], [1440, 900], [1366, 768], [1280, 720], [1024, 768], [768, 1024],
] as const
const ROUTES = ['write', 'plan', 'characters', 'world', 'analyze', 'assistant', 'publish', 'intake', 'analytics']

for (const [w, h] of VIEWPORTS) {
  test.describe(`${w}×${h}`, () => {
    test.use({ viewport: { width: w, height: h } })

    test('no horizontal page scroll on any workspace', async ({ page }) => {
      await signIn(page); await mockApi(page)
      for (const ws of ROUTES) {
        await page.goto(workspaceUrl(ws))
        await expect(page.getByRole('navigation', { name: 'Workspaces' })).toBeVisible()
        await page.waitForLoadState('networkidle')
        expect(await hasHorizontalScroll(page), `${ws} scrolls horizontally at ${w}px`).toBe(false)
      }
    })

    test('Write keeps a usable editor with the AI sidecar open, and the rail is reachable', async ({ page }) => {
      await signIn(page); await mockApi(page)
      await page.goto(workspaceUrl('write'))
      await waitForChapterContent(page)
      await page.getByRole('button', { name: 'AI assistant', exact: true }).click()
      await expect(page.getByRole('complementary', { name: 'AI Assistant' })).toBeVisible()
      const editor = (await page.locator('.ProseMirror').first().boundingBox())!
      expect(editor.width, `editor width at ${w}px`).toBeGreaterThanOrEqual(w >= 1024 ? 400 : 300)
      expect(await hasHorizontalScroll(page)).toBe(false)
      const rail = page.getByRole('navigation', { name: 'Workspaces' })
      for (const label of ['Write', 'Plan', 'Characters', 'World', 'Analyze', 'Assistant', 'Publish']) {
        const b = rail.getByRole('button', { name: label, exact: true })
        await b.scrollIntoViewIfNeeded()
        await expect(b, `${label} reachable at ${w}×${h}`).toBeInViewport()
      }
    })
  })
}
