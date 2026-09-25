// Every workspace renders against the mocked API with no uncaught page error.
import { test, expect } from '@playwright/test'
import { mockApi, signIn, workspaceUrl } from './mockApi'

const ROUTES = ['write', 'plan', 'characters', 'world', 'analyze', 'assistant', 'publish', 'intake', 'analytics']

for (const ws of ROUTES) {
  test(`${ws} renders without page errors`, async ({ page }) => {
    const errors: string[] = []
    page.on('pageerror', (e) => errors.push(e.message))
    await signIn(page)
    await mockApi(page)
    await page.goto(workspaceUrl(ws))
    await expect(page.getByRole('navigation', { name: 'Workspaces' })).toBeVisible()
    await page.waitForLoadState('networkidle')
    expect(errors).toEqual([])
  })
}
