import { createHash } from 'node:crypto'
import { test, expect, type APIRequestContext, type Page, type TestInfo } from '@playwright/test'
import { seedBrowserSession, sessionToken } from './_session'

// Stage 7 (Phase 3) — real-browser verification of the author loop:
// generate → pin → Versions → compare → per-block merge → insert, plus the
// invert-locks control and Send to Idea Shelf. Real frontend + backend + vLLM.
//
//   npx playwright install chromium
//   E2E_EMAIL=… E2E_PASSWORD=… E2E_STORY_ID=… npx playwright test --project=browser tests/browser/phase3-pins-compare.spec.ts
//
// Runs against a disposable fixture story (never real manuscript content)
// whose chapter one is a plain two-sentence paragraph (see lock-and-strength
// .spec.ts for why the fixture is plain rather than moody).
//
// Stage 12 (phase3-pins investigation):
//  * Tone runs a model pre-check that can legitimately answer "this already
//    reads that way". That is a correct product result, not a pin-workflow
//    failure, so generate() takes a fixed list of tones: a no-change notice is
//    recorded and the next tone is tried. The pin workflow itself is still
//    asserted in full — the second pin must be a NEW pin (already_pinned=false)
//    with different content from the first.
//  * Every test attaches a JSON trace (pin create/list/delete and tone
//    responses with status, pin id, content hash, already_pinned, no_change;
//    toasts; the server's pin list afterwards; the ids beforeAll deleted; the
//    repeat/retry index) so a count mismatch can be explained, not guessed.

const EMAIL = process.env.E2E_EMAIL
const PASSWORD = process.env.E2E_PASSWORD
const STORY_ID = process.env.E2E_STORY_ID
test.skip(!EMAIL || !PASSWORD || !STORY_ID, 'Set E2E_EMAIL, E2E_PASSWORD and E2E_STORY_ID.')

const AI_TIMEOUT = 150_000
const API_URL = process.env.E2E_API_URL ?? 'http://localhost:8000'
test.describe.configure({ mode: 'serial' })

let token = ''
let deletedInBeforeAll: string[] = []
let trace: Record<string, unknown>[] = []

const sha = (s: string) => createHash('sha256').update(s).digest('hex').slice(0, 12)
const now = () => new Date().toISOString()

async function signIn(page: Page, request: APIRequestContext) {
  if (!token) {
    const res = await request.post(`${API_URL}/api/auth/login`, { data: { email: EMAIL, password: PASSWORD } })
    expect(res.ok()).toBe(true)
    token = sessionToken(res)
  }
  await seedBrowserSession(page, token)
}

const auth = () => ({ Authorization: `Bearer ${token}` })
const toolbar = (page: Page) => page.getByRole('toolbar', { name: 'AI actions for the selected text' })
const firstParagraph = (page: Page) => page.locator('.ProseMirror p').first()
const NO_CHANGE = /already reads that way|could not find a meaningful change/i

async function openWrite(page: Page) {
  await page.goto(`/projects/${STORY_ID}/write`)
  await expect(page.locator('.ProseMirror')).toBeVisible({ timeout: 30_000 })
  await expect(firstParagraph(page)).not.toBeEmpty()
}

function instrument(page: Page) {
  page.on('response', async (res) => {
    const url = res.url()
    const m = res.request().method()
    if (!/\/ai\/pins|\/api\/ai\/tone/.test(url)) return
    const rec: Record<string, unknown> = { t: now(), method: m, path: new URL(url).pathname, status: res.status() }
    try {
      if (m === 'POST' && /\/ai\/pins$/.test(url)) {
        const body = JSON.parse(res.request().postData() || '{}')
        rec.sent_content_sha = sha(String(body.content ?? ''))
        const j = await res.json()
        Object.assign(rec, { pin_id: j.pin?.pin_id, already_pinned: j.already_pinned, used: j.limits?.used })
      } else if (m === 'GET' && /\/ai\/pins(\?|$)/.test(url)) {
        const j = await res.json()
        rec.pin_ids = (j.pins ?? []).map((p: { pin_id: string }) => p.pin_id)
      } else if (/\/api\/ai\/tone/.test(url)) {
        const j = await res.json()
        Object.assign(rec, { no_change: j.no_change, transformed_sha: sha(String(j.transformed ?? '')) })
      }
    } catch { /* body not JSON (e.g. 204) */ }
    trace.push(rec)
  })
}

/** Generate a tone preview, trying `tones` in order. A "no change" notice is
 *  a legitimate model answer: it is recorded and the next tone is tried. */
async function generate(page: Page, tones: string[]): Promise<string> {
  for (const tone of tones) {
    await firstParagraph(page).click({ clickCount: 3 })
    await toolbar(page).getByRole('button', { name: /Tone/i }).first().click()
    await page.getByRole('menuitem', { name: new RegExp(tone) }).click()
    const preview = page.getByRole('button', { name: /Apply to selection|Insert at cursor instead/ })
    const notice = page.getByText(NO_CHANGE).first()
    await expect(preview.or(notice)).toBeVisible({ timeout: AI_TIMEOUT })
    if (await preview.isVisible()) {
      trace.push({ t: now(), generated: tone })
      return tone
    }
    trace.push({ t: now(), tone, outcome: 'no_change (legitimate model result) — trying next tone' })
    test.info().annotations.push({ type: 'no-change', description: tone })
    await page.keyboard.press('Escape')
    await expect(notice).toBeHidden({ timeout: 15_000 })
  }
  test.skip(true, `precondition not met: every tone in [${tones.join(', ')}] returned "already reads that way"`)
  return ''
}

async function pinAndRecord(page: Page) {
  const created = page.waitForResponse((r) => r.request().method() === 'POST' && /\/ai\/pins$/.test(r.url()))
  await page.getByTestId('pin-button').click()
  const res = await created
  await expect(page.getByTestId('pin-button')).toContainText('Pinned', { timeout: 15_000 })
  const toasts = await page.locator('[data-sonner-toast]').allInnerTexts().catch(() => [])
  trace.push({ t: now(), toasts })
  return res.json() as Promise<{ already_pinned: boolean; pin: { pin_id: string } }>
}

async function attachTrace(request: APIRequestContext, info: TestInfo) {
  const list = await (await request.get(`${API_URL}/api/stories/${STORY_ID}/ai/pins`, { headers: auth() })).json()
  await info.attach('pin-trace.json', {
    contentType: 'application/json',
    body: JSON.stringify({
      test: info.title, repeatEachIndex: info.repeatEachIndex, retry: info.retry, workerIndex: info.workerIndex,
      deletedInBeforeAll, events: trace,
      serverPinsAfter: (list.pins ?? []).map((p: { pin_id: string; tool: string; created_at: string }) =>
        ({ pin_id: p.pin_id, tool: p.tool, created_at: p.created_at })),
      usage: list.limits ?? list.usage ?? null,
    }, null, 2),
  })
}

test.beforeAll(async ({ request }) => {
  // Start from zero pins for this fixture story so counts are deterministic.
  const res = await request.post(`${API_URL}/api/auth/login`, { data: { email: EMAIL, password: PASSWORD } })
  const t = sessionToken(res)
  const pins = await (await request.get(`${API_URL}/api/stories/${STORY_ID}/ai/pins`, { headers: { Authorization: `Bearer ${t}` } })).json()
  deletedInBeforeAll = pins.pins.map((p: { pin_id: string }) => p.pin_id)
  for (const id of deletedInBeforeAll) await request.delete(`${API_URL}/api/stories/${STORY_ID}/ai/pins/${id}`, { headers: { Authorization: `Bearer ${t}` } })
})

test.beforeEach(async ({ page, request }) => {
  trace = [{ t: now(), start: test.info().title }]
  await signIn(page, request)
  instrument(page)
  await openWrite(page)
})

test.afterEach(async ({ request }, info) => {
  await attachTrace(request, info)
})

test('invert locks swaps locked and unlocked sentences', async ({ page }) => {
  await firstParagraph(page).click({ clickCount: 3 })
  await toolbar(page).getByRole('button', { name: /Tone/i }).first().click()
  const menu = page.getByRole('menu')
  const sentences = menu.locator('button[aria-pressed]')
  await expect(sentences).toHaveCount(2)
  await sentences.first().click()
  await expect(sentences.first()).toHaveAttribute('aria-pressed', 'true')
  await menu.getByTestId('invert-locks').click()
  await expect(sentences.first()).toHaveAttribute('aria-pressed', 'false')
  await expect(sentences.nth(1)).toHaveAttribute('aria-pressed', 'true')
})

let firstPinId = ''

test('P3-01: a result can be pinned from the toolbar and shows its expiry', async ({ page }) => {
  await generate(page, ['Dark', 'Tense', 'Melancholic'])
  const pin = page.getByTestId('pin-button')
  const created = await pinAndRecord(page)
  expect(created.already_pinned).toBe(false)
  firstPinId = created.pin.pin_id
  await expect(pin).toContainText(/Pinned · expires in \d+ days/, { timeout: 15_000 })
})

test('P3-01/P3-04: Versions lists pins; two versions compare and merge block by block', async ({ page }) => {
  // A second, DIFFERENT version to compare against: a new pin, not the
  // server's "already pinned" answer for identical content.
  let created: { already_pinned: boolean; pin: { pin_id: string } } | null = null
  for (const tones of [['Hopeful', 'Humorous'], ['Epic', 'Romantic'], ['Lyrical']]) {
    await generate(page, tones)
    created = await pinAndRecord(page)
    if (!created.already_pinned) break
    trace.push({ t: now(), outcome: 'already_pinned: identical content to an existing pin — trying another tone' })
    await page.keyboard.press('Escape')
  }
  expect(created?.already_pinned, 'the second version must be a new pin').toBe(false)
  expect(created?.pin.pin_id).not.toBe(firstPinId)
  await page.keyboard.press('Escape')

  await page.getByRole('button', { name: 'AI assistant', exact: true }).click()
  await page.getByRole('tab', { name: 'Versions' }).click()
  const cards = page.getByTestId('pin-card')
  await expect(cards).toHaveCount(2, { timeout: 15_000 })
  await expect(page.getByTestId('versions-panel')).toContainText(/2 of 20 pins · free plan · kept 7 days/)

  await cards.nth(0).locator('button[aria-expanded]').click()
  await cards.nth(0).getByRole('button', { name: 'Compare with another version' }).click()
  await cards.nth(1).locator('button[aria-expanded]').click()
  await cards.nth(1).getByRole('button', { name: 'Compare with this' }).click()

  const dialog = page.getByRole('dialog')
  await expect(dialog.getByText('Compare versions')).toBeVisible()
  await dialog.getByRole('tab', { name: 'Unified' }).click()
  await dialog.getByRole('tab', { name: 'Changes only' }).click()
  const merge = dialog.getByTestId('merge-section')
  if (await merge.count()) {
    const choices = merge.locator('li button[aria-pressed]')
    // Choose the right-hand side of the first changed passage and check the
    // merged text now contains exactly that passage.
    const right = choices.nth(1)
    const chosenText = (await right.innerText()).split('\n').slice(1).join(' ').trim().slice(0, 25)
    await right.click()
    await expect(right).toHaveAttribute('aria-pressed', 'true')
    if (chosenText && !chosenText.startsWith('(leave out)')) await expect(merge.getByTestId('merged-text')).toContainText(chosenText)
  }
  await dialog.getByRole('button', { name: 'Close comparison' }).click()
  await expect(dialog).toBeHidden()
})

const cardIds = async (request: APIRequestContext): Promise<string[]> =>
  ((await (await request.get(`${API_URL}/api/ocr/${STORY_ID}/note-cards`, { headers: auth() })).json()) as { card_id: string }[])
    .map((c) => c.card_id)

test('P3-09: a result can be sent to the Idea Shelf and appears under Notes → Ideas', async ({ page, request }) => {
  // Stage 12: the idea this test saves is deleted afterwards. Before, every run
  // left one behind, and after 50 runs the free plan's idea limit (correctly)
  // refused the 51st — a test-data failure, not a product one.
  const before = new Set(await cardIds(request))
  try {
    await generate(page, ['Epic', 'Suspenseful', 'Romantic'])
    await page.getByRole('button', { name: 'Send to Idea Shelf' }).click()
    await page.getByRole('button', { name: 'Save idea' }).click()
    await expect(page.getByText(/Saved to the Idea Shelf/)).toBeVisible({ timeout: 15_000 })
    // Stage 8.8: the Idea Shelf's one home is World › Notes › Ideas (D10).
    await page.goto(`/projects/${STORY_ID}/world?section=notes&tab=ideas`)
    await expect(page.getByRole('tab', { name: 'Ideas', selected: true })).toBeVisible()
    await expect(page.getByTestId('idea-card').first()).toBeVisible({ timeout: 15_000 })
  } finally {
    for (const id of await cardIds(request)) {
      if (!before.has(id)) await request.delete(`${API_URL}/api/ocr/note-cards/${id}`, { headers: auth() })
    }
  }
})
