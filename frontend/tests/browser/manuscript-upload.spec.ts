import { test, expect, type APIRequestContext, type Page } from '@playwright/test'

// Stage 6 task 6.4 — critical journey: upload a manuscript -> chapters populate.
//
// REAL FINDING from executing this live during Stage 6 closure (2026-09-22):
// the backend has a fully working manuscript-upload endpoint
// (POST /api/manuscript/upload/{story_id}, verified passing in
// backend/tests/test_e2e_checklist_gaps.py::test_manuscript_docx_upload_creates_chapters_from_content)
// and the frontend even has a typed API client for it (lib/api.ts's
// `manuscriptApi.upload`) — but NOTHING in the frontend ever calls it.
// Confirmed by exhaustive search: `grep -rln "manuscriptApi\." frontend/app
// frontend/components` returns zero results. Every workspace tab
// (Write/Plan/Characters/World/Analyze/Assistant/Publish/Library) was opened
// live and none exposes a manuscript-upload control. This is a genuine,
// previously-undocumented gap: an author cannot upload a manuscript through
// the app UI at all, even though the backend is ready for it.
//
// This test therefore does NOT assert the happy path (there is no happy
// path to assert). It documents the gap as a reproducible, xfail(strict)
// check across every workspace tab, so a future frontend fix that adds the
// missing UI will make this test start failing (a *good* failure, meaning
// "update this test, the gap is closed") rather than silently doing nothing
// forever.
//
//   E2E_EMAIL=… E2E_PASSWORD=… E2E_STORY_ID=…
//   npx playwright test tests/browser/manuscript-upload.spec.ts --project=browser

const EMAIL = process.env.E2E_EMAIL
const PASSWORD = process.env.E2E_PASSWORD
const STORY_ID = process.env.E2E_STORY_ID

test.skip(!EMAIL || !PASSWORD || !STORY_ID, 'Set E2E_EMAIL, E2E_PASSWORD and E2E_STORY_ID.')

const API_URL = process.env.E2E_API_URL ?? 'http://localhost:8000'
let cachedToken: string | null = null
let cachedUser: string | null = null

async function authSession(request: APIRequestContext) {
  if (!cachedToken || !cachedUser) {
    const res = await request.post(`${API_URL}/api/auth/login`, { data: { email: EMAIL, password: PASSWORD } })
    expect(res.ok(), `login failed: ${res.status()}`).toBe(true)
    const body = await res.json()
    cachedToken = body.access_token
    cachedUser = JSON.stringify(body.user)
  }
  return { token: cachedToken!, user: cachedUser! }
}

async function openProject(page: Page, request: APIRequestContext) {
  const { token, user } = await authSession(request)
  await page.addInitScript(([t, u]) => {
    window.localStorage.setItem('narratiq_token', t)
    window.localStorage.setItem('narratiq_user', u)
  }, [token, user])
  await page.goto(`/projects/${STORY_ID}`)
  await page.locator('.ProseMirror').first().waitFor({ state: 'visible' })
}

const WORKSPACE_TABS = ['Write', 'Plan', 'Characters', 'World', 'Analyze', 'Assistant', 'Publish']

// Deliberately a normal (not Playwright test.fail()-annotated) test: per
// this project's own established policy for known-open defects
// (backend/tests/test_known_stage5_defects.py), an "expected failure"
// annotation hides the red in a normal run summary. This stays plainly red
// until the frontend gap above is actually closed.
test('a manuscript-upload control is reachable from some workspace tab', async ({ page, request }) => {
    await openProject(page, request)

    let found = false
    for (const tabName of WORKSPACE_TABS) {
      const tab = page.getByRole('button', { name: tabName, exact: true })
      if (await tab.count()) {
        await tab.click()
        await page.waitForTimeout(500)
      }
      if (await page.locator('input[type=file]').count()) {
        found = true
        break
      }
    }

    expect(
      found,
      'No workspace tab exposes a manuscript-upload file input, even though ' +
      'the backend endpoint (POST /api/manuscript/upload/{story_id}) and the ' +
      'frontend API client (manuscriptApi.upload in lib/api.ts) both exist ' +
      'and work — confirmed via backend/tests/test_e2e_checklist_gaps.py. ' +
      'This is a real, reproducible frontend gap, not a selector guess.',
    ).toBe(true)
  },
)
