// Build-variant checks. Each block runs only in its STUDIO_VARIANT build
// (see playwright.studio.config.ts); in other builds it is skipped.
import { test, expect } from '@playwright/test'
import { readdirSync, readFileSync, statSync, existsSync } from 'fs'
import { join } from 'path'
import { mockApi, signIn, workspaceUrl } from './mockApi'
import { hasHorizontalScroll, openPalette, waitForChapterContent } from './helpers'

const VARIANT = process.env.STUDIO_VARIANT ?? 'default'
const MARKER = 'narratiq-e2e-mock-tool-7f3a'

function buildContains(dir: string, needle: string): number {
  let hits = 0
  const walk = (d: string) => {
    for (const f of readdirSync(d)) {
      const p = join(d, f)
      if (statSync(p).isDirectory()) walk(p)
      else if (/\.(js|html|json)$/.test(f) && readFileSync(p, 'utf8').includes(needle)) hits++
    }
  }
  walk(dir)
  return hits
}

// ── 8.7 scalability: a new tool is one registry row, no layout change ───────
test.describe('mock-tool build', () => {
  test.skip(VARIANT !== 'mock-tool', 'runs in STUDIO_VARIANT=mock-tool')

  test('the mock tool appears in Analyze, opens full width, and nothing else moves', async ({ page }) => {
    await signIn(page); await mockApi(page)
    await page.goto(workspaceUrl('analyze'))
    const rail = page.getByRole('navigation', { name: 'Workspaces' })
    const railBox = (await rail.boundingBox())!
    const card = page.getByRole('button', { name: /Mock Tool/ })
    await expect(card).toBeVisible()
    expect(await hasHorizontalScroll(page)).toBe(false)
    await card.click()
    await expect(page.getByTestId('mock-tool-panel')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Mock Tool', level: 1 })).toBeFocused()
    expect(await hasHorizontalScroll(page)).toBe(false)
    const after = (await rail.boundingBox())!
    expect(after).toEqual(railBox)                                  // rail untouched
    await expect(rail.getByRole('button')).toHaveCount(8)            // 7 workspaces + library
  })

  test('the mock tool is compiled into this build (control for the hygiene check)', () => {
    expect(buildContains(join(__dirname, '..', '..', '.next-studio-mock-tool', 'static'), MARKER)).toBeGreaterThan(0)
  })
})

// ── L3: a normal build carries no trace of the mock tool ─────────────────────
test.describe('default build', () => {
  test.skip(VARIANT !== 'default', 'runs in the default build')

  test('the mock tool is absent from the normal build output', () => {
    const dir = join(__dirname, '..', '..', '.next-studio', 'static')
    test.skip(!existsSync(dir), 'no .next-studio build present')
    expect(buildContains(dir, MARKER)).toBe(0)
    expect(buildContains(dir, 'MockToolPanel')).toBe(0)
  })
})

// ── L5: the Phase 3 rollback build (NEXT_PUBLIC_P3_ENABLED=false) ────────────
test.describe('p3-off build', () => {
  test.skip(VARIANT !== 'p3-off', 'runs in STUDIO_VARIANT=p3-off')

  test('Phase 3 surfaces disappear cleanly and every other home still works', async ({ page }) => {
    await signIn(page); await mockApi(page)
    await page.goto(workspaceUrl('write'))
    await waitForChapterContent(page)
    await page.getByRole('button', { name: 'AI assistant', exact: true }).click()
    await expect(page.getByRole('tablist', { name: 'AI tool groups' }).getByRole('tab')).toHaveText(['Rewrite', 'Generate'])
    await expect(page.getByRole('button', { name: /What the AI must keep/ })).toHaveCount(0)
    await page.goto(workspaceUrl('world', 'section=notes&tab=ideas'))
    await expect(page.getByRole('tablist', { name: 'Notes views' }).getByRole('tab')).toHaveText(['Story Notes', 'Note Cards'])
    await expect(page.getByRole('tab', { name: 'Story Notes' })).toHaveAttribute('aria-selected', 'true')
    await (await openPalette(page)).fill('Idea Shelf')
    await expect(page.getByRole('option', { name: /Go to Idea Shelf/ })).toHaveCount(0)
  })
})
