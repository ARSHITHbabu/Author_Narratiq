import { test, expect, type APIRequestContext, type Page } from '@playwright/test'

// Phase 2 QA Issue 3 — the Writing Analytics page was unreachable below the fold.
// Checklist task 3.9.
//
//   E2E_EMAIL=… E2E_PASSWORD=… E2E_STORY_ID=… npx playwright test --project=browser
//
// The reachability assertions deliberately target "the LAST section" rather than a
// fixed pixel height, so they keep holding as analytics sections are added.

const EMAIL = process.env.E2E_EMAIL
const PASSWORD = process.env.E2E_PASSWORD
const STORY_ID = process.env.E2E_STORY_ID

test.skip(!EMAIL || !PASSWORD || !STORY_ID, 'Set E2E_EMAIL, E2E_PASSWORD and E2E_STORY_ID.')

const API_URL = process.env.E2E_API_URL ?? 'http://localhost:8000'
let cached: { token: string; user: string } | null = null

async function signIn(page: Page, request: APIRequestContext) {
  if (!cached) {
    const res = await request.post(`${API_URL}/api/auth/login`, { data: { email: EMAIL, password: PASSWORD } })
    expect(res.ok(), `login failed: ${res.status()}`).toBe(true)
    const body = await res.json()
    cached = { token: body.access_token, user: JSON.stringify(body.user) }
  }
  await page.addInitScript(([t, u]) => {
    window.localStorage.setItem('narratiq_token', t)
    window.localStorage.setItem('narratiq_user', u)
  }, [cached.token, cached.user])
}

const lastSection = (page: Page) => page.getByTestId('analytics-last-section')
const header = (page: Page) => page.getByText('/ Analytics')

async function openAnalytics(page: Page) {
  await page.goto(`/projects/${STORY_ID}/analytics`)
  await expect(page.getByRole('heading', { name: 'Writing Statistics' })).toBeVisible({ timeout: 30_000 })
}

/** The page's single scroll container, found by capability rather than by class. */
async function scrollers(page: Page) {
  return page.evaluate(() =>
    Array.from(document.querySelectorAll('*'))
      .filter((el) => {
        const s = getComputedStyle(el)
        const scrollable = /(auto|scroll)/.test(s.overflowY)
        return scrollable && el.scrollHeight > el.clientHeight + 1
      })
      .map((el) => ({ className: (el as HTMLElement).className, height: el.clientHeight })),
  )
}

test.beforeEach(async ({ page, request }) => {
  await signIn(page, request)
})

const VIEWPORTS = [
  { name: '1366x768', width: 1366, height: 768 },
  { name: '1180x720', width: 1180, height: 720 },
  { name: '1024x640', width: 1024, height: 640 },
  { name: '1024x560 (short)', width: 1024, height: 560 },
]

for (const vp of VIEWPORTS) {
  test(`the last analytics section can be scrolled into view at ${vp.name}`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width: vp.width, height: vp.height })
    await openAnalytics(page)

    await lastSection(page).scrollIntoViewIfNeeded()
    await expect(lastSection(page)).toBeInViewport()
    await expect(page.getByRole('heading', { name: /Phase 2 Analytics/ })).toBeVisible()

    await testInfo.attach(`analytics-${vp.width}x${vp.height}.png`, {
      body: await page.screenshot(), contentType: 'image/png',
    })
  })
}

test('there is exactly one vertical scroll container — no nested or competing scrollbars', async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 640 })
  await openAnalytics(page)
  const found = await scrollers(page)
  expect(found, `expected one scroller, got ${JSON.stringify(found)}`).toHaveLength(1)
})

test('the window itself never scrolls — the studio shell owns the viewport', async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 640 })
  await openAnalytics(page)
  const windowScrolls = await page.evaluate(() =>
    document.documentElement.scrollHeight > document.documentElement.clientHeight + 1)
  expect(windowScrolls).toBe(false)
})

test('the header never covers content — it is in flow, not overlaying', async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 768 })
  await openAnalytics(page)

  const headerBox = (await header(page).boundingBox())!
  const firstHeading = (await page.getByRole('heading', { name: 'Writing Statistics' }).boundingBox())!
  expect(firstHeading.y).toBeGreaterThanOrEqual(headerBox.y + headerBox.height)

  // And structurally, for every scroll position: the scroll region starts below the
  // header, so content is clipped at its top edge rather than painted underneath.
  await lastSection(page).scrollIntoViewIfNeeded()
  const region = await page.evaluate(() => {
    const el = Array.from(document.querySelectorAll('*')).find((e) => {
      const s = getComputedStyle(e)
      return /(auto|scroll)/.test(s.overflowY) && e.scrollHeight > e.clientHeight + 1
    })
    const r = el!.getBoundingClientRect()
    return { y: r.y, height: r.height }
  })
  expect(region.y).toBeGreaterThanOrEqual(headerBox.y + headerBox.height - 1)
})

test('scrolling works by wheel and by keyboard, and returns to the top', async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 640 })
  await openAnalytics(page)

  const offset = async () => (await scrollers(page)).length &&
    page.evaluate(() => {
      const el = Array.from(document.querySelectorAll('*')).find((e) => {
        const s = getComputedStyle(e)
        return /(auto|scroll)/.test(s.overflowY) && e.scrollHeight > e.clientHeight + 1
      })
      return el ? el.scrollTop : -1
    })

  expect(await offset()).toBe(0)
  await page.mouse.move(500, 400)
  await page.mouse.wheel(0, 600)
  await expect.poll(offset).toBeGreaterThan(0)

  await lastSection(page).scrollIntoViewIfNeeded()
  const atBottom = await offset()
  expect(atBottom).toBeGreaterThan(0)

  await page.getByRole('heading', { name: 'Writing Statistics' }).scrollIntoViewIfNeeded()
  await expect.poll(offset).toBeLessThan(atBottom as number)
})

test('returning from analytics to the story keeps the app navigable', async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 768 })
  await openAnalytics(page)
  await lastSection(page).scrollIntoViewIfNeeded()

  await page.goBack()
  await page.goForward()
  await expect(page.getByRole('heading', { name: 'Writing Statistics' })).toBeVisible({ timeout: 30_000 })
  await lastSection(page).scrollIntoViewIfNeeded()
  await expect(lastSection(page)).toBeInViewport()
})
