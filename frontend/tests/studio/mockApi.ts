// Mocked NarratIQ API for the `studio` Playwright project.
//
// The studio specs exercise navigation, layout, modes and accessibility — the
// frontend's own behaviour — so they run with NO backend: every request to the
// build-time API origin (NEXT_PUBLIC_API_URL=http://mock-api.test) is fulfilled
// here from synthetic fixtures. Nothing reaches a real service, and no manuscript
// text is involved: the fixture chapters are placeholder sentences.

import type { Page, Route } from '@playwright/test'

export const API_ORIGIN = 'http://mock-api.test'
export const STORY_ID = '11111111-1111-4111-8111-111111111111'
export const CHAPTER_IDS = [
  '22222222-2222-4222-8222-222222222201',
  '22222222-2222-4222-8222-222222222202',
  '22222222-2222-4222-8222-222222222203',
]

export interface MockUser { user_id: string; email: string; username: string }
export const USER_A: MockUser = { user_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', email: 'a@example.test', username: 'author-a' }
export const USER_B: MockUser = { user_id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', email: 'b@example.test', username: 'author-b' }

const now = '2026-09-25T00:00:00Z'
const story = {
  story_id: STORY_ID, user_id: USER_A.user_id, title: 'Fixture Story', description: '',
  word_count: 36, status: 'draft', created_at: now, updated_at: now,
}
const chapters = CHAPTER_IDS.map((id, i) => ({
  chapter_id: id, story_id: STORY_ID, chapter_number: i + 1, title: `Chapter ${i + 1}`,
  word_count: 12, created_at: now, updated_at: now,
  content: `<p>Placeholder paragraph ${i + 1} for layout tests. It has a few plain words.</p>`,
}))

export interface ApiLog {
  /** every request as "METHOD /path" */
  calls: string[]
  /** requests no fixture matched (served a generic empty body) */
  unmatched: string[]
  /** chapter save requests (PUT/PATCH of a chapter) — Reading mode must send none */
  saves: string[]
}

type Handler = (route: Route, method: string, path: string) => Promise<boolean> | boolean

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
}

/** Install the mocked API on a page. Extra handlers run first, so a spec can override. */
export async function mockApi(page: Page, extra: Handler[] = []): Promise<ApiLog> {
  const log: ApiLog = { calls: [], unmatched: [], saves: [] }
  await page.route(`${API_ORIGIN}/**`, async (route) => {
    const req = route.request()
    const method = req.method()
    const path = new URL(req.url()).pathname
    log.calls.push(`${method} ${path}`)
    if (method === 'OPTIONS') return route.fulfill({ status: 204 })
    for (const h of extra) if (await h(route, method, path)) return

    // ── auth: the email picks the fixture user ──────────────────────────────
    if (method === 'POST' && path === '/api/auth/login') {
      const email = (req.postDataJSON() ?? {}).email
      const u = [USER_A, USER_B].find((x) => x.email === email) ?? USER_A
      return json(route, { access_token: `mock-token-${u.username}`, token_type: 'bearer', user: { ...u, created_at: now } })
    }

    // ── core story context ──────────────────────────────────────────────────
    if (method === 'GET' && /^\/api\/projects\/?$/.test(path)) return json(route, [story])
    if (method === 'GET' && path === `/api/projects/${STORY_ID}`) return json(route, story)
    if (method === 'GET' && path === `/api/stories/${STORY_ID}/chapters`) return json(route, chapters.map(({ content, ...c }) => c))
    const ch = path.match(/^\/api\/stories\/[^/]+\/chapters\/([^/]+)$/)
    if (ch) {
      const found = chapters.find((c) => c.chapter_id === ch[1])
      if (found && method === 'GET') {
        // STUDIO_CHAPTER_DELAY_MS slows the chapter body so readiness bugs in
        // specs show up every time instead of only under heavy load (review F1).
        const delay = Number(process.env.STUDIO_CHAPTER_DELAY_MS || 0)
        if (delay > 0) await new Promise((r) => setTimeout(r, delay))
        return json(route, found)
      }
      if (found && (method === 'PUT' || method === 'PATCH')) { log.saves.push(`${method} ${path}`); return json(route, found) }
    }
    if (method === 'GET' && path === `/api/stories/${STORY_ID}/characters`) return json(route, [])
    if (method === 'GET' && path.endsWith('/genre-profile')) return json(route, null)

    // ── Stage 5 (merged from main): scan status and the saved report ────────
    if (method === 'GET' && path === `/api/stories/${STORY_ID}/narrative-threads/scan-status`) {
      return json(route, { scan_id: null, status: 'none', threads_written: 0, chapters_scanned: 0,
        batches_degraded: 0, error_code: null, started_at: null, finished_at: null })
    }
    if (method === 'GET' && path === `/api/stories/${STORY_ID}/manuscript-report`) {
      return json(route, { detail: 'No saved report for this story yet.' }, 404)
    }

    // Generic fallback: an empty but well-formed body. GETs of collections get [],
    // everything else {}. Recorded so a spec can assert nothing unexpected fired.
    log.unmatched.push(`${method} ${path}`)
    if (method === 'GET') return json(route, /s$|list$|history$|notes$|cards$|pins$/.test(path) ? [] : {})
    return json(route, {})
  })
  return log
}

/** Sign a mocked user in by seeding the same localStorage keys the app's login
 *  writes. Only on the first document of the test (sessionStorage marker), so a
 *  later logout in the same test is not undone by the next navigation. */
export async function signIn(page: Page, user: MockUser = USER_A) {
  // STUDIO_LATE_SELECTIONCHANGE_MS delivers the editor's selectionchange events
  // late, so ProseMirror's 20 ms post-focus selection sync lands in the window
  // a fast test gesture can hit. Used to prove the F1 second-cause fix.
  const late = Number(process.env.STUDIO_LATE_SELECTIONCHANGE_MS || 0)
  if (late > 0) {
    await page.addInitScript((ms) => {
      const add = Document.prototype.addEventListener
      Document.prototype.addEventListener = function (this: Document, type: string, fn: any, opts?: any) {
        if (type === 'selectionchange' && typeof fn === 'function') {
          const self = this
          return add.call(self, type, (e: Event) => { setTimeout(() => fn.call(self, e), ms) }, opts)
        }
        return add.call(this, type, fn, opts)
      } as typeof Document.prototype.addEventListener
    }, late)
  }
  await page.addInitScript((u) => {
    if (!sessionStorage.getItem('mock-signed-in')) {
      sessionStorage.setItem('mock-signed-in', '1')
      localStorage.setItem('narratiq_token', 'mock-token')
      localStorage.setItem('narratiq_user', JSON.stringify({ ...u, created_at: '2026-09-25T00:00:00Z' }))
    }
  }, user)
}

export function workspaceUrl(ws: string, query = '') {
  return `/projects/${STORY_ID}/${ws}${query ? `?${query}` : ''}`
}
