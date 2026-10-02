// Stage 12 remediation (Tranches 1 and 2b), mocked API — no backend, no model.
//   A8: Import manuscript from the Write binder (success, partial, refusal, bad file).
//   A7: Possible duplicate characters — detect → suggest → author-confirmed merge.
import { test, expect, type Route } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { mockApi, signIn, workspaceUrl, STORY_ID } from './mockApi'

const json = (r: Route, b: unknown, status = 200) =>
  r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) }).then(() => true)

async function seriousA11y(page: import('@playwright/test').Page) {
  const r = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  return r.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical').map((v) => v.id)
}

test.beforeEach(async ({ page }) => { await signIn(page) })

// ── A8: manuscript import ────────────────────────────────────────────────────

const TXT = { name: 'book.txt', mimeType: 'text/plain', buffer: Buffer.from('Chapter 1\nThe rain.\nChapter 2\nThe key.') }

async function openImport(page: import('@playwright/test').Page) {
  await page.goto(workspaceUrl('write'))
  await page.getByTestId('import-manuscript').click()
  await expect(page.getByTestId('manuscript-import-dialog')).toBeVisible()
}

test('A8: import saves chapters, shows progress, then success; the binder reloads', async ({ page }) => {
  let uploads = 0, polls = 0, chapterListCalls = 0
  await mockApi(page, [
    (r, m, p) => {
      if (m === 'GET' && p === `/api/stories/${STORY_ID}/chapters`) chapterListCalls++
      return false
    },
    (r, m, p) => m === 'POST' && p === `/api/manuscript/upload/${STORY_ID}`
      ? (uploads++, json(r, { job_id: 'job-1', story_id: STORY_ID, chapter_count: 2, estimated_minutes: 1, status: 'processing' }))
      : false,
    (r, m, p) => m === 'GET' && p === '/api/manuscript/job/job-1'
      ? (polls++, json(r, polls < 2
          ? { job_id: 'job-1', status: 'processing', stage: 'Preparing chapter 1 of 2 for AI tools', percent: 40, message: '' }
          : { job_id: 'job-1', status: 'complete', stage: 'Story imported and ready', percent: 100, message: '2 chapters imported.' }))
      : false,
  ])
  await openImport(page)
  await expect(page.getByText(/added after your existing 3 chapters/)).toBeVisible()
  const listBefore = chapterListCalls
  await page.getByTestId('manuscript-file-input').setInputFiles(TXT)
  await page.getByTestId('manuscript-import-start').click()
  await expect(page.getByTestId('manuscript-import-preparing')).toContainText('2 chapters saved to your story.')
  await expect(page.getByTestId('manuscript-import-done')).toContainText('2 chapters imported.', { timeout: 15000 })
  expect(uploads).toBe(1)
  expect(chapterListCalls).toBeGreaterThan(listBefore)          // binder refreshed
  expect(await seriousA11y(page)).toEqual([])
})

test('A8: indexing that stops is reported as partial — the text is saved', async ({ page }) => {
  await mockApi(page, [
    (r, m, p) => m === 'POST' && p === `/api/manuscript/upload/${STORY_ID}`
      ? json(r, { job_id: 'job-2', story_id: STORY_ID, chapter_count: 3, estimated_minutes: 1, status: 'processing' }) : false,
    (r, m, p) => m === 'GET' && p === '/api/manuscript/job/job-2'
      ? json(r, { job_id: 'job-2', status: 'partial', stage: 'Imported — AI preparation incomplete', percent: 100,
          message: 'All 3 chapters were imported and saved. AI tools could not finish preparing 2 of them because the AI service was temporarily unavailable; those chapters are prepared again the next time you save them.' })
      : false,
  ])
  await openImport(page)
  await page.getByTestId('manuscript-file-input').setInputFiles(TXT)
  await page.getByTestId('manuscript-import-start').click()
  const partial = page.getByTestId('manuscript-import-partial')
  await expect(partial).toContainText('3 chapters saved to your story.', { timeout: 15000 })
  await expect(partial).toContainText('could not finish preparing 2 of them')
})

test('A8: a refused upload explains itself and says nothing was imported', async ({ page }) => {
  await mockApi(page, [
    (r, m, p) => m === 'POST' && p === `/api/manuscript/upload/${STORY_ID}`
      ? json(r, { detail: 'A manuscript import is already running for this story. Wait for it to finish, then try again.' }, 409) : false,
  ])
  await openImport(page)
  await page.getByTestId('manuscript-file-input').setInputFiles(TXT)
  await page.getByTestId('manuscript-import-start').click()
  await expect(page.getByTestId('manuscript-import-error')).toContainText('already running')
})

test('A8: a server failure never shows raw error text', async ({ page }) => {
  await mockApi(page, [
    (r, m, p) => m === 'POST' && p === `/api/manuscript/upload/${STORY_ID}`
      ? r.fulfill({ status: 502, contentType: 'text/html', body: '<html>Traceback (most recent call last)</html>' }).then(() => true) : false,
  ])
  await openImport(page)
  await page.getByTestId('manuscript-file-input').setInputFiles(TXT)
  await page.getByTestId('manuscript-import-start').click()
  const err = page.getByTestId('manuscript-import-error')
  await expect(err).toContainText('Nothing was imported')
  await expect(err).not.toContainText('Traceback')
})

test('A8: unsupported and empty files are rejected before upload', async ({ page }) => {
  let uploads = 0
  await mockApi(page, [
    (r, m, p) => m === 'POST' && p === `/api/manuscript/upload/${STORY_ID}` ? (uploads++, json(r, {})) : false,
  ])
  await openImport(page)
  await page.getByTestId('manuscript-file-input').setInputFiles({ name: 'book.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF') })
  await expect(page.getByRole('alert')).toContainText('Choose a .txt or .docx file')
  await expect(page.getByTestId('manuscript-import-start')).toBeDisabled()
  await page.getByTestId('manuscript-file-input').setInputFiles({ name: 'empty.txt', mimeType: 'text/plain', buffer: Buffer.from('') })
  await expect(page.getByRole('alert')).toContainText('This file is empty.')
  expect(uploads).toBe(0)
})

// ── A7: possible duplicate characters ────────────────────────────────────────

const CHARS = [
  { character_id: 'c-elara', story_id: STORY_ID, name: 'Elara', aliases: [], role: 'protagonist', status: 'active', description: '' },
  { character_id: 'c-elara-voss', story_id: STORY_ID, name: 'Elara Voss', aliases: [], role: 'supporting', status: 'active', description: '' },
  { character_id: 'c-marek', story_id: STORY_ID, name: 'Marek', aliases: [], role: 'supporting', status: 'active', description: '' },
  { character_id: 'c-marekk', story_id: STORY_ID, name: 'Marekk', aliases: [], role: 'minor', status: 'active', description: '' },
]
const ref = (c: typeof CHARS[number]) => ({ character_id: c.character_id, name: c.name, aliases: c.aliases, role: c.role, status: c.status })
const PAIRS = [
  { character_a: ref(CHARS[0]), character_b: ref(CHARS[1]), score: 0.9, profile_similarity: null,
    reasons: [{ kind: 'name_part', text: '“Elara” and “Elara Voss” could be the same person\'s shorter and longer name.' }] },
  { character_a: ref(CHARS[2]), character_b: ref(CHARS[3]), score: 0.8, profile_similarity: null,
    reasons: [{ kind: 'similar_spelling', text: '“Marek” and “Marekk” are spelled almost the same.' }] },
]

function castHandlers(state: { merges: { survivor: string; duplicate: string }[] }) {
  return [
    (r: Route, m: string, p: string) => {
      if (m === 'GET' && p === `/api/stories/${STORY_ID}/characters`) {
        const gone = new Set(state.merges.map((x) => x.duplicate))
        return json(r, CHARS.filter((c) => !gone.has(c.character_id)))
      }
      if (m === 'GET' && p === `/api/stories/${STORY_ID}/characters/hints`) return json(r, [])
      if (m === 'GET' && p === `/api/stories/${STORY_ID}/characters/duplicate-candidates`) {
        const gone = new Set(state.merges.map((x) => x.duplicate))
        return json(r, PAIRS.filter((x) => !gone.has(x.character_a.character_id) && !gone.has(x.character_b.character_id)))
      }
      const mm = p.match(new RegExp(`^/api/stories/${STORY_ID}/characters/([^/]+)/merge$`))
      if (m === 'POST' && mm) {
        const dup = (r.request().postDataJSON() ?? {}).duplicate_id
        state.merges.push({ survivor: mm[1], duplicate: dup })
        const s = CHARS.find((c) => c.character_id === mm[1])!
        const d = CHARS.find((c) => c.character_id === dup)!
        return json(r, { survivor: { ...s, aliases: [d.name] }, summary: {} })
      }
      return false
    },
  ]
}

test('A7: possible duplicates are listed with reasons and nothing merges without confirmation', async ({ page }) => {
  const state = { merges: [] as { survivor: string; duplicate: string }[] }
  await mockApi(page, castHandlers(state))
  await page.goto(workspaceUrl('characters'))
  const panel = page.getByTestId('duplicates-panel')
  await expect(panel).toContainText('2 possible duplicates')
  await panel.getByRole('button', { name: /possible duplicates/ }).click()
  await expect(page.getByTestId('duplicate-pair')).toHaveCount(2)
  await expect(panel).toContainText('could be the same person')

  const first = page.getByTestId('duplicate-pair').first()
  await expect(first.getByTestId('duplicate-merge')).toBeDisabled()      // must choose who to keep
  await first.getByLabel('Keep “Elara”').check()
  await first.getByTestId('duplicate-merge').click()
  await expect(first.getByTestId('duplicate-confirm')).toContainText('“Elara Voss” will be merged into “Elara”')
  expect(state.merges).toEqual([])                                        // still nothing merged
  expect(await seriousA11y(page)).toEqual([])

  await first.getByTestId('duplicate-confirm-merge').click()
  await expect.poll(() => state.merges).toEqual([{ survivor: 'c-elara', duplicate: 'c-elara-voss' }])
  await expect(page.getByTestId('duplicate-pair')).toHaveCount(1)
})

test('A7: cancel and "Not the same person" never call merge; dismissal persists in this browser', async ({ page }) => {
  const state = { merges: [] as { survivor: string; duplicate: string }[] }
  await mockApi(page, castHandlers(state))
  await page.goto(workspaceUrl('characters'))
  await page.getByTestId('duplicates-panel').getByRole('button', { name: /possible duplicates/ }).click()
  const marek = page.getByTestId('duplicate-pair').filter({ hasText: 'Marekk' })
  await marek.getByLabel('Keep “Marek”').check()
  await marek.getByTestId('duplicate-merge').click()
  await marek.getByRole('button', { name: 'Cancel' }).click()
  await marek.getByTestId('duplicate-dismiss').click()
  await expect(page.getByTestId('duplicate-pair')).toHaveCount(1)
  await page.reload()
  await expect(page.getByTestId('duplicates-panel')).toContainText('1 possible duplicate')
  expect(state.merges).toEqual([])
})

test('A7: a failed merge says both characters are unchanged', async ({ page }) => {
  const state = { merges: [] as { survivor: string; duplicate: string }[] }
  await mockApi(page, [
    (r, m, p) => m === 'POST' && p.endsWith('/merge') ? json(r, { detail: 'boom' }, 500) : false,
    ...castHandlers(state),
  ])
  await page.goto(workspaceUrl('characters'))
  await page.getByTestId('duplicates-panel').getByRole('button', { name: /possible duplicates/ }).click()
  const first = page.getByTestId('duplicate-pair').first()
  await first.getByLabel('Keep “Elara”').check()
  await first.getByTestId('duplicate-merge').click()
  await first.getByTestId('duplicate-confirm-merge').click()
  await expect(first.getByRole('alert')).toContainText('both characters are unchanged')
})

test('A7: cast generation marks a possible duplicate and does not pre-select it', async ({ page }) => {
  const sugg = (name: string, extra: object = {}) => ({
    name, role: 'supporting', status: 'active', description: '', aliases: [], first_appearance: '',
    evidence_snippet: '', confidence: 'high', age: '', appearance: '', personality: '', goals: '',
    motivations: '', backstory: '', arc_notes: '', traits: [], already_exists: false,
    existing_character_id: null, possible_duplicate_of: null, possible_duplicate_name: null, ...extra,
  })
  const state = { merges: [] as { survivor: string; duplicate: string }[] }
  await mockApi(page, [
    (r, m, p) => m === 'POST' && p === `/api/stories/${STORY_ID}/characters/generate-cast`
      ? json(r, { story_id: STORY_ID, chapters_scanned: 3, new_count: 2, existing_count: 0, suggestions: [
          sugg('Captain Elara', { possible_duplicate_of: 'c-elara', possible_duplicate_name: 'Elara' }),
          sugg('Tomas Reyne'),
        ] })
      : false,
    ...castHandlers(state),
  ])
  await page.goto(workspaceUrl('characters'))
  await page.getByTitle('Generate cast from story').click()
  await expect(page.getByTestId('cast-possible-duplicate')).toContainText('May be the same person as “Elara”')
  await expect(page.getByRole('button', { name: 'Add 1 Character' })).toBeVisible()
})

// ── Tranche 2a: A10 presence, A11 flags, A12 order ──────────────────────────

test('A10–A12: off-page figures and possible duplicates are shown, labelled and not pre-selected', async ({ page }) => {
  const sugg = (name: string, extra: object = {}) => ({
    name, role: 'supporting', status: 'active', description: '', aliases: [], first_appearance: '',
    evidence_snippet: '', confidence: 'high', age: '', appearance: '', personality: '', goals: '',
    motivations: '', backstory: '', arc_notes: '', traits: [], already_exists: false,
    existing_character_id: null, possible_duplicate_of: null, possible_duplicate_name: null,
    presence: 'on_page', possible_duplicate_in_suggestions: null, possible_combined_with: null,
    mention_count: 0, ...extra,
  })
  const state = { merges: [] as { survivor: string; duplicate: string }[] }
  let confirmed: any[] = []
  await mockApi(page, [
    (r, m, p) => m === 'POST' && p === `/api/stories/${STORY_ID}/characters/generate-cast`
      ? json(r, { story_id: STORY_ID, chapters_scanned: 6, new_count: 5, existing_count: 0, suggestions: [
          sugg('Mira Okoye', { role: 'protagonist', mention_count: 14 }),
          sugg('Tomas Reyne', { mention_count: 3 }),
          sugg('Tomas', { possible_duplicate_in_suggestions: 'Tomas Reyne', mention_count: 2 }),
          sugg('Hessa Lin', { possible_combined_with: 'Hessa Marr', mention_count: 5 }),
          sugg('The Cartographer', { presence: 'historical', status: 'deceased', mention_count: 6 }),
        ] })
      : false,
    (r, m, p) => {
      if (m === 'POST' && p === `/api/stories/${STORY_ID}/characters/confirm-cast`) {
        confirmed = (r.request().postDataJSON() ?? {}).suggestions ?? []
        return json(r, { created: [], skipped_existing: 0 }, 201)
      }
      return false
    },
    ...castHandlers(state),
  ])
  await page.goto(workspaceUrl('characters'))
  await page.getByTitle('Generate cast from story').click()
  await expect(page.getByTestId('cast-presence')).toHaveText('In the past')
  await expect(page.getByTestId('cast-batch-duplicate')).toContainText('“Tomas Reyne”')
  await expect(page.getByTestId('cast-combined')).toContainText('“Hessa Marr”')
  await expect(page.getByText('14 mentions')).toBeVisible()
  // Only Mira and Tomas Reyne are pre-selected.
  await expect(page.getByRole('button', { name: 'Add 2 Characters' })).toBeVisible()
  await expect(page.getByRole('checkbox', { name: 'Add The Cartographer to the cast' })).toHaveAttribute('aria-checked', 'false')
  await expect(page.getByRole('checkbox', { name: 'Add Mira Okoye to the cast' })).toHaveAttribute('aria-checked', 'true')
  expect(await seriousA11y(page)).toEqual([])
  await page.getByRole('button', { name: 'Add 2 Characters' }).click()
  await expect.poll(() => confirmed.map((c) => c.name).sort()).toEqual(['Mira Okoye', 'Tomas Reyne'])
  expect(confirmed.every((c) => c.presence === 'on_page')).toBe(true)
})

test('A12: the saved cast stays A–Z unless the author chooses importance', async ({ page }) => {
  const calls: string[] = []
  const state = { merges: [] as { survivor: string; duplicate: string }[] }
  await mockApi(page, [
    (r, m, p) => {
      if (m === 'GET' && p === `/api/stories/${STORY_ID}/characters`) calls.push(new URL(r.request().url()).search)
      return false
    },
    ...castHandlers(state),
  ])
  await page.goto(workspaceUrl('characters'))
  await expect(page.getByTestId('char-sort-name')).toHaveAttribute('aria-pressed', 'true')
  await expect.poll(() => calls.length).toBeGreaterThan(0)
  expect(calls.every((q) => !q.includes('importance'))).toBe(true)
  await page.getByTestId('char-sort-importance').click()
  await expect.poll(() => calls.some((q) => q.includes('order=importance'))).toBe(true)
})

// ── Tranche 2b, A16: an invented name is a soft note, never a block ─────────

test('A16: a name the rewrite introduced is shown as a soft note and the result can still be applied', async ({ page }) => {
  const { waitForChapterContent, focusEditorSettled } = await import('./helpers')
  await mockApi(page, [
    (r, m, p) => (m === 'POST' && p === '/api/ai/tone') ? json(r, {
      original: 'Placeholder paragraph 1 for layout tests.',
      transformed: 'A calmer placeholder paragraph for layout tests, with Odalys.',
      mode: 'tone', tokens_used: 10, no_change: false,
      warnings: [{ kind: 'new_entity', severity: 'soft',
        message: 'The rewrite adds name(s) not found in your text or story: “Odalys”. Check this is intended.',
        entity: { type: 'name', names: ['Odalys'] } }],
      strength_detail: { measured: true, kept_share: 0.8, new_share: 0.2, strength: 'light' },
    }) : false,
  ])
  await page.goto(workspaceUrl('write'))
  await waitForChapterContent(page)
  await page.getByRole('button', { name: 'AI assistant', exact: true }).click()
  await page.getByRole('combobox', { name: 'Rewrite tool' }).selectOption('tone')
  await focusEditorSettled(page)
  await page.locator('.ProseMirror p').first().click({ clickCount: 3 })
  await page.locator('#ai-tool-panel').getByRole('button', { name: /Apply|Change|Transform|Rewrite/ }).last().click()
  const note = page.locator('[data-kind="new_entity"]')
  await expect(note).toContainText('Odalys')
  await expect(note).toHaveClass(/amber/)                        // soft, not the red "hard" style
  await expect(page.getByRole('button', { name: /Apply to selection|Replace|Insert/ }).first()).toBeEnabled()
  expect(await seriousA11y(page)).toEqual([])
})
