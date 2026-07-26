import { test, expect, type APIRequestContext, type Locator, type Page } from '@playwright/test'

// PRE-2 browser verification (Phase 2 QA Issues 1 and 11) — checklist task 3.8.
//
//   npx playwright install chromium
//   E2E_EMAIL=… E2E_PASSWORD=… E2E_STORY_ID=… npx playwright test --project=browser
//
// Runs against a running frontend + backend. The fixture story must have two
// chapters; chapter one must begin with the word "The" followed by a space (the
// whitespace-selection case selects that exact space). No manuscript content from
// any real author is used, referenced or captured here.
//
// Without the environment variables these tests SKIP — they never pass by default,
// because a verification checkbox may only be ticked on a real run.

const EMAIL = process.env.E2E_EMAIL
const PASSWORD = process.env.E2E_PASSWORD
const STORY_ID = process.env.E2E_STORY_ID

test.skip(!EMAIL || !PASSWORD || !STORY_ID, 'Set E2E_EMAIL, E2E_PASSWORD and E2E_STORY_ID.')

// AI transforms go to a real model; give them room without hiding a hang.
const AI_TIMEOUT = 120_000

const toolbar = (page: Page) => page.getByRole('toolbar', { name: 'AI actions for the selected text' })
const sidecarPanel = (page: Page) => page.getByText('AI Assistant', { exact: true })
const sidecarToggle = (page: Page) => page.getByTitle(/AI sidecar/)
const previewCard = (page: Page) => page.getByRole('button', { name: 'Apply to selection' })
const editorArea = (page: Page) => page.locator('.ProseMirror')
const firstParagraph = (page: Page) => page.locator('.ProseMirror p').first()

// Auth endpoints are rate-limited to 5/minute per IP, so the suite signs in ONCE
// through the API and seeds the same JWT the app itself stores. The login form is
// not what these tests are about.
const API_URL = process.env.E2E_API_URL ?? 'http://localhost:8000'
let cachedToken: string | null = null

let cachedUser: string | null = null

async function authSession(request: APIRequestContext): Promise<{ token: string; user: string }> {
  if (!cachedToken || !cachedUser) {
    const res = await request.post(`${API_URL}/api/auth/login`, {
      data: { email: EMAIL, password: PASSWORD },
    })
    expect(res.ok(), `login failed: ${res.status()}`).toBe(true)
    const body = await res.json()
    cachedToken = body.access_token
    cachedUser = JSON.stringify(body.user)
  }
  return { token: cachedToken!, user: cachedUser! }
}

async function signIn(page: Page, request: APIRequestContext) {
  const { token, user } = await authSession(request)
  // The same two keys the app writes on a real sign-in.
  await page.addInitScript(([t, u]) => {
    window.localStorage.setItem('narratiq_token', t)
    window.localStorage.setItem('narratiq_user', u)
  }, [token, user])
}

async function openWrite(page: Page) {
  await page.goto(`/projects/${STORY_ID}/write`)
  await expect(editorArea(page)).toBeVisible({ timeout: 30_000 })
  await expect(firstParagraph(page)).not.toBeEmpty()
}

/** Select the first visual line of chapter one. */
async function selectLine(page: Page) {
  await firstParagraph(page).click()
  await page.keyboard.press('Home')
  await page.keyboard.press('Shift+End')
}

/** Collapse the selection without leaving the editor. */
async function deselect(page: Page) {
  await firstParagraph(page).click()
  await page.keyboard.press('End')
}

/** Select exactly the space after the leading word "The". */
async function selectOnlyWhitespace(page: Page) {
  await firstParagraph(page).click()
  await page.keyboard.press('ControlOrMeta+Home')                        // start of the document
  for (let i = 0; i < 3; i++) await page.keyboard.press('ArrowRight')   // past "The"
  await page.keyboard.press('Shift+ArrowRight')                          // the space
  const selected = await page.evaluate(() => window.getSelection()?.toString() ?? '')
  expect(selected, 'fixture must start with "The "').toBe(' ')
}

/** Switch chapters in the binder and wait for the editor to actually hold that
 *  chapter's prose — the heading updates before the content is loaded. */
async function openChapter(page: Page, n: number) {
  await page.getByText(`Chapter ${n}`, { exact: true }).click()
  await expect(page.getByRole('heading', { name: new RegExp(`Chapter ${n} —`) })).toBeVisible()
  await expect(editorArea(page)).toContainText(n === 1 ? 'The lighthouse' : 'A second chapter')
}

/** Run a transform from the toolbar and wait for its preview. */
async function runTransform(page: Page, group: string, option: string) {
  await toolbar(page).getByRole('button', { name: new RegExp(group, 'i') }).first().click()
  await page.getByRole('menuitem', { name: new RegExp(option, 'i') }).first().click()
}

async function boxOf(locator: Locator) {
  const box = await locator.boundingBox()
  expect(box).not.toBeNull()
  return box!
}

const overlaps = (a: { x: number; y: number; width: number; height: number },
                  b: { x: number; y: number; width: number; height: number }) =>
  a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height

test.beforeEach(async ({ page, request }) => {
  await signIn(page, request)
  await openWrite(page)
})

// ── 1, 2, 10: appearance and dismissal ──────────────────────────────────────

test('1+2: select shows the toolbar, deselect hides it', async ({ page }) => {
  await expect(toolbar(page)).toHaveCount(0)
  await selectLine(page)
  await expect(toolbar(page)).toBeVisible()
  await deselect(page)
  await expect(toolbar(page)).toHaveCount(0)
})

test('10: a whitespace-only selection does not open the toolbar', async ({ page }) => {
  await selectOnlyWhitespace(page)
  await expect(toolbar(page)).toHaveCount(0)
})

// ── 3, 4, 5: sidebar deference ──────────────────────────────────────────────

test('3+4: opening the sidebar suppresses the toolbar, closing it gives the selection back', async ({ page }) => {
  await selectLine(page)
  await expect(toolbar(page)).toBeVisible()

  await sidecarToggle(page).click()
  await expect(sidecarPanel(page)).toBeVisible()
  await expect(toolbar(page)).toHaveCount(0)
  // The selection survived the handover — the sidebar knows about it.
  await expect(page.getByText(/words selected — AI will work on this/)).toBeVisible()

  await page.getByTitle(/^Close/).click()
  await expect(sidecarPanel(page)).toHaveCount(0)
  await expect(toolbar(page)).toBeVisible()
})

test('3: with the sidebar already open, a new selection never raises the toolbar', async ({ page }) => {
  await sidecarToggle(page).click()
  await expect(sidecarPanel(page)).toBeVisible()
  await selectLine(page)
  await expect(page.getByText(/words selected — AI will work on this/)).toBeVisible()
  await expect(toolbar(page)).toHaveCount(0)
})

test('5: the sidebar scope updates when the selection changes', async ({ page }) => {
  await sidecarToggle(page).click()
  await expect(page.getByText('No selection — using full chapter')).toBeVisible()

  await selectLine(page)
  const firstScope = await page.getByText(/words selected/).innerText()

  await editorArea(page).click()
  await page.keyboard.press('ControlOrMeta+a')
  await expect
    .poll(async () => page.getByText(/words selected/).innerText(), { timeout: 10_000 })
    .not.toBe(firstScope)
})

// ── 6, 7, 8: preview lifecycle and manuscript safety ────────────────────────

test('6: a pending preview stays reviewable when the sidebar opens', async ({ page }) => {
  await selectLine(page)
  await runTransform(page, 'Refine', 'Grammar')
  await expect(previewCard(page)).toBeVisible({ timeout: AI_TIMEOUT })

  await sidecarToggle(page).click()
  await expect(sidecarPanel(page)).toBeVisible()
  await expect(previewCard(page)).toBeVisible()      // AI output survives the panel
  await expect(toolbar(page)).toHaveCount(0)          // but the duplicate controls do not
})

test('7: changing chapter invalidates a pending preview', async ({ page }) => {
  await selectLine(page)
  await runTransform(page, 'Refine', 'Grammar')
  await expect(previewCard(page)).toBeVisible({ timeout: AI_TIMEOUT })

  await openChapter(page, 2)
  await expect(previewCard(page)).toHaveCount(0)
})

test('8: a generation finishing after a chapter switch cannot apply anywhere', async ({ page }) => {
  await openChapter(page, 2)
  const chapterTwoBefore = await editorArea(page).innerText()
  await openChapter(page, 1)

  // Hold the transform response open so the chapter switch is guaranteed to land
  // while the generation is still in flight — the case being verified.
  await page.route('**/api/ai/**', async (route) => {
    await new Promise((r) => setTimeout(r, 6000))
    await route.continue()
  })

  await selectLine(page)
  await runTransform(page, 'Refine', 'Grammar')
  await page.getByText('Chapter 2', { exact: true }).click()   // leave while it generates
  await expect(page.getByRole('heading', { name: /Chapter 2 —/ })).toBeVisible()

  await expect(page.getByText('You moved to another chapter, so that suggestion was discarded.'))
    .toBeVisible({ timeout: AI_TIMEOUT })
  await expect(previewCard(page)).toHaveCount(0)
  expect(await editorArea(page).innerText()).toBe(chapterTwoBefore)
})

// ── 9: Escape order ─────────────────────────────────────────────────────────

test('9: Escape closes the menu, then the toolbar; and discards a preview', async ({ page }) => {
  await selectLine(page)
  await toolbar(page).getByRole('button', { name: /Tone/i }).first().click()
  await expect(page.getByRole('menu')).toBeVisible()

  await page.keyboard.press('Escape')
  await expect(page.getByRole('menu')).toHaveCount(0)
  await expect(toolbar(page)).toBeVisible()            // menu only — toolbar stays

  await page.keyboard.press('Escape')
  await expect(toolbar(page)).toHaveCount(0)           // now the toolbar

  await selectLine(page)                                // a new selection brings it back
  await expect(toolbar(page)).toBeVisible()
  await runTransform(page, 'Refine', 'Grammar')
  await expect(previewCard(page)).toBeVisible({ timeout: AI_TIMEOUT })
  await page.keyboard.press('Escape')
  await expect(previewCard(page)).toHaveCount(0)
})

// ── 11: Focus and Zen preserve the ownership rule ───────────────────────────

test('11: Focus mode hides the sidebar, so the toolbar takes the selection back', async ({ page }) => {
  await selectLine(page)
  await sidecarToggle(page).click()
  await expect(toolbar(page)).toHaveCount(0)

  await page.keyboard.press('ControlOrMeta+.')          // Focus mode, keyboard only
  await expect(sidecarPanel(page)).toHaveCount(0)
  await expect(toolbar(page)).toBeVisible()

  await page.keyboard.press('ControlOrMeta+.')          // back out
  await expect(sidecarPanel(page)).toBeVisible()
  await expect(toolbar(page)).toHaveCount(0)
})

test('11: in Zen mode the toolbar still owns a selection', async ({ page }) => {
  await page.getByTitle('Zen mode').click()
  await expect(page.getByText('Exit Zen (Esc)')).toBeVisible()
  // Entering a mode re-lays out the panel group and the editor reloads its content.
  // That reload can land just after a selection and collapse it — a pre-existing
  // behaviour, not something the ownership rule controls. An author would simply
  // select again, so the test does too, and asserts that selecting in Zen mode
  // raises the toolbar.
  await expect(editorArea(page)).toContainText('The lighthouse')
  await expect.poll(async () => {
    await selectLine(page)
    return toolbar(page).count()
  }, { timeout: 15_000 }).toBeGreaterThan(0)
})

// ── 12, 13, 14: geometry, dragging, menu direction ──────────────────────────

test('12: resizing keeps the toolbar inside the editor column', async ({ page }) => {
  await selectLine(page)
  await expect(toolbar(page)).toBeVisible()

  for (const size of [{ width: 1280, height: 720 }, { width: 1024, height: 700 }, { width: 900, height: 620 }]) {
    await page.setViewportSize(size)
    await page.waitForTimeout(300)
    const bar = await boxOf(toolbar(page))
    const column = await boxOf(page.locator('.ProseMirror').locator('xpath=ancestor::div[contains(@class,"relative")][1]'))
    expect(bar.x).toBeGreaterThanOrEqual(column.x - 1)
    expect(bar.x + bar.width).toBeLessThanOrEqual(column.x + column.width + 1)
    expect(bar.y + bar.height).toBeLessThanOrEqual(size.height + 1)
  }
})

test('13+14: dragging keeps the selection and flips the menu direction', async ({ page }) => {
  await selectLine(page)
  const handle = page.getByTestId('toolbar-drag-handle').first()
  const before = await boxOf(toolbar(page))

  // Default rest is low in the column, so menus open upward.
  await toolbar(page).getByRole('button', { name: /Tone/i }).first().click()
  const buttonBox = await boxOf(toolbar(page).getByRole('button', { name: /Tone/i }).first())
  const menuUp = await boxOf(page.getByRole('menu'))
  expect(menuUp.y).toBeLessThan(buttonBox.y)
  await page.keyboard.press('Escape')

  const h = await boxOf(handle)
  await page.mouse.move(h.x + h.width / 2, h.y + h.height / 2)
  await page.mouse.down()
  await page.mouse.move(h.x + h.width / 2, 120, { steps: 12 })
  await page.mouse.up()

  // 13: the drag did not clear the editor selection — the toolbar is still up.
  await expect(toolbar(page)).toBeVisible()
  const after = await boxOf(toolbar(page))
  expect(after.y).toBeLessThan(before.y)

  // 14: high in the column, menus now open downward.
  await toolbar(page).getByRole('button', { name: /Tone/i }).first().click()
  const buttonBox2 = await boxOf(toolbar(page).getByRole('button', { name: /Tone/i }).first())
  const menuDown = await boxOf(page.getByRole('menu'))
  expect(menuDown.y).toBeGreaterThan(buttonBox2.y)

  // Double-clicking the handle returns it to the default rest.
  await page.keyboard.press('Escape')
  await handle.dblclick()
  const reset = await boxOf(toolbar(page))
  expect(Math.abs(reset.y - before.y)).toBeLessThan(4)
})

// ── Visual verification: the toolbar never covers editor controls ───────────

const VIEWPORTS = [
  { name: '1366x768 (reported QA resolution)', width: 1366, height: 768 },
  { name: '1180x720 (narrower desktop)', width: 1180, height: 720 },
  { name: '1024x640 (minimum supported)', width: 1024, height: 640 },
]

for (const vp of VIEWPORTS) {
  test(`visual: no overlap with editor controls at ${vp.name}`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width: vp.width, height: vp.height })
    await selectLine(page)
    await expect(toolbar(page)).toBeVisible()

    const bar = await boxOf(toolbar(page))
    for (const control of ['Bold', 'Italic', 'Underline', 'Save']) {
      const box = await boxOf(page.getByRole('button', { name: control }).first())
      expect(overlaps(bar, box), `toolbar overlaps ${control} at ${vp.name}`).toBe(false)
    }
    const savedStatus = page.getByText(/^Saved /)
    if (await savedStatus.count()) {
      expect(overlaps(bar, await boxOf(savedStatus.first()))).toBe(false)
    }
    await testInfo.attach(`toolbar-${vp.width}x${vp.height}.png`, {
      body: await page.screenshot(), contentType: 'image/png',
    })
  })
}

test('visual: the sidebar keeps its own controls clear because the toolbar stands down', async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 768 })
  await selectLine(page)
  await sidecarToggle(page).click()
  await expect(sidecarPanel(page)).toBeVisible()
  await expect(toolbar(page)).toHaveCount(0)
})
