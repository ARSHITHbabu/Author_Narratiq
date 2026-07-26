import { test, expect, type APIRequestContext, type Page } from '@playwright/test'

// Phase 2 QA Issue 9 — a character appearing as both recognised and unrecognised.
// Checklist task 3.12, frontend half: the banner and the cast list must agree
// immediately after a mutation, with no page reload and no fixed delay.
//
//   E2E_EMAIL=… E2E_PASSWORD=… E2E_STORY_ID=… E2E_HINT_NAME=… E2E_HINT_KEEP=… \
//     npx playwright test --project=browser tests/browser/character-hint-sync.spec.ts
//
// E2E_HINT_NAME must be a live hint that this test will resolve by creating the
// character. E2E_HINT_KEEP must be a live hint with a SIMILAR BUT DISTINCT name
// that must survive. Both are seeded by the task's verification script.

const EMAIL = process.env.E2E_EMAIL
const PASSWORD = process.env.E2E_PASSWORD
const STORY_ID = process.env.E2E_STORY_ID
const HINT_NAME = process.env.E2E_HINT_NAME
const HINT_KEEP = process.env.E2E_HINT_KEEP

test.skip(!EMAIL || !PASSWORD || !STORY_ID || !HINT_NAME || !HINT_KEEP,
  'Set E2E_EMAIL, E2E_PASSWORD, E2E_STORY_ID, E2E_HINT_NAME and E2E_HINT_KEEP.')

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

// Scoped to the banner: a name in the CAST list is not a hint, and the whole point
// of Issue 9 is that the same name can legitimately appear in one and not the other.
const banner = (page: Page) => page.getByTestId('hints-banner')
const bannerCount = (page: Page) => page.getByText(/unrecognised name/)
const hintChip = (page: Page, name: string) => banner(page).getByText(name, { exact: true })

async function openCharacters(page: Page) {
  await page.goto(`/projects/${STORY_ID}/characters`)
  await expect(page.getByRole('button', { name: 'New' })).toBeVisible({ timeout: 30_000 })
}

test.beforeEach(async ({ page, request }) => {
  await signIn(page, request)
  await page.setViewportSize({ width: 1366, height: 768 })
})

// NOTE: this spec CONSUMES the hint it resolves, so the two hints must be reseeded
// before each run (see task 3.12's verification script). A missing hint fails loudly
// rather than skipping — a silent skip would look like a pass.
test('registering a character removes its name from the unrecognised list without a reload', async ({ page }) => {
  await openCharacters(page)
  await expect(banner(page), 'no live hints — reseed the fixture before running this spec').toBeVisible()
  await expect(hintChip(page, HINT_NAME!),
    `hint "${HINT_NAME}" is not live — reseed the fixture before running this spec`).toBeVisible()

  const before = (await bannerCount(page).innerText()).match(/^(\d+)/)?.[1]
  expect(before, 'could not read the banner count').toBeTruthy()

  // Watch for a navigation — there must not be one.
  let navigated = false
  page.on('framenavigated', (f) => { if (f === page.mainFrame()) navigated = true })

  await page.getByRole('button', { name: 'New' }).click()
  await page.getByPlaceholder('e.g. Elara Voss').fill(HINT_NAME!)
  await page.getByRole('button', { name: 'Create Character' }).click()

  // The chip disappears and the count drops, from a refetch — not a page reload.
  await expect(hintChip(page, HINT_NAME!)).toHaveCount(0, { timeout: 20_000 })
  await expect
    .poll(async () => (await bannerCount(page).count()) ? (await bannerCount(page).innerText()).match(/^(\d+)/)?.[1] : '0',
      { timeout: 20_000 })
    .not.toBe(before)
  expect(navigated, 'the page reloaded instead of refetching').toBe(false)
})

test('a similar but distinct unrecognised name is left alone', async ({ page }) => {
  await openCharacters(page)
  await expect(hintChip(page, HINT_KEEP!)).toBeVisible()
})

test('background mention indexing is shown as in progress, not as finished', async ({ page }) => {
  await openCharacters(page)
  await page.getByRole('button', { name: 'New' }).click()
  await page.getByPlaceholder('e.g. Elara Voss').fill(`E2E Pending ${Date.now()}`)
  await page.getByRole('button', { name: 'Create Character' }).click()

  const pending = page.getByTestId('mentions-pending')
  await expect(pending).toBeVisible({ timeout: 20_000 })
  await expect(pending).toContainText('still being indexed')
  await expect(pending).toContainText('The cast is saved')
})
