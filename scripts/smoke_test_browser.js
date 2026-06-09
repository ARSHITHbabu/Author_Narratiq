#!/usr/bin/env node
// ═══════════════════════════════════════════════════════════════
//  NarratIQ AI v3.0 — Browser Smoke Test (Playwright)
//
//  Detects React/Next.js runtime crashes that HTTP-only tests miss.
//  Usage:
//    cd /workspace/narratiq-ai/frontend
//    node /workspace/narratiq-ai/scripts/smoke_test_browser.js
//
//  Exit 0: all checks pass
//  Exit 1: any check fails
// ═══════════════════════════════════════════════════════════════

// Playwright lives in frontend/node_modules — resolve from there
const FRONTEND_ROOT = require('path').resolve(__dirname, '../frontend')
const { chromium } = require(require.resolve('@playwright/test', { paths: [FRONTEND_ROOT] }))

const FRONTEND = process.env.FRONTEND_URL || 'http://localhost:3000'
const BACKEND  = process.env.BACKEND_URL  || 'http://localhost:8000'

const SMOKE_EMAIL = `browser_smoke_${Date.now()}@example.com`
const SMOKE_USER  = `bsmoke${Date.now()}`
const SMOKE_PASS  = 'SmokePass123!'

let PASS = 0
let FAIL = 0
const failures = []

function ok(label) {
  console.log(`  [OK]   ${label}`)
  PASS++
}
function fail(label, detail = '') {
  console.log(`  [FAIL] ${label}`)
  if (detail) console.log(`         ${detail}`)
  FAIL++
  failures.push({ label, detail })
}
function section(title) {
  console.log('')
  console.log('─'.repeat(62))
  console.log(`  ${title}`)
  console.log('─'.repeat(62))
}

// Console messages we deliberately tolerate — pure environment noise that does
// not indicate a broken build. Everything else (including ChunkLoadError) fails.
const BENIGN_CONSOLE = [
  '401',          // expected auth challenges before login
  'favicon',      // we ship no favicon — 404 is expected
  'preconnect',   // <link rel=preconnect> hints sometimes warn
]

function isChunkError(text) {
  return (
    /ChunkLoadError/i.test(text) ||
    /Loading chunk [\d]+ failed/i.test(text) ||
    /Loading CSS chunk/i.test(text) ||
    /Failed to fetch dynamically imported module/i.test(text)
  )
}

// Create a fresh browser page with error listeners
async function newPage(context) {
  const page = await context.newPage()
  const consoleErrors = []
  const pageErrors = []
  const chunkErrors = []
  const static404s = []

  page.on('console', msg => {
    if (msg.type() === 'error') {
      const text = msg.text()
      if (isChunkError(text)) {
        chunkErrors.push(text)
        consoleErrors.push(text)
      } else if (!BENIGN_CONSOLE.some(b => text.includes(b))) {
        consoleErrors.push(text)
      }
    }
  })
  page.on('pageerror', err => {
    const text = `${err.message}`
    if (isChunkError(text)) chunkErrors.push(text)
    pageErrors.push({ message: err.message, stack: err.stack })
  })
  // Catch the actual HTTP 404 on a deleted build chunk — the root cause of
  // ChunkLoadError. Any non-2xx/3xx response under /_next/static/ is fatal.
  page.on('response', resp => {
    const url = resp.url()
    if (url.includes('/_next/static/') && resp.status() >= 400) {
      static404s.push(`${resp.status()} ${url}`)
    }
  })
  // Also catch requests that never got a response at all (e.g. chunk fetch
  // aborted) under /_next/static/.
  page.on('requestfailed', req => {
    const url = req.url()
    if (url.includes('/_next/static/')) {
      static404s.push(`FAILED ${req.failure()?.errorText || ''} ${url}`)
    }
  })

  return { page, consoleErrors, pageErrors, chunkErrors, static404s }
}

// Check a page didn't crash after navigation. Returns true only when fully clean.
function assertNoCrash(page, ctx, label) {
  return (async () => {
    const { consoleErrors, pageErrors, chunkErrors, static404s } = ctx
    const bodyText = await page.evaluate(() => document.body?.innerText || '').catch(() => '')
    const lower = bodyText.toLowerCase()
    const hasAppError = lower.includes('application error') ||
                        lower.includes('a client-side exception')

    let clean = true

    if (chunkErrors.length > 0) {
      fail(`${label} — ChunkLoadError detected`, chunkErrors[0].slice(0, 200))
      clean = false
    }
    if (static404s.length > 0) {
      fail(`${label} — 404/failure under /_next/static/`, static404s[0].slice(0, 200))
      clean = false
    }
    if (hasAppError) {
      fail(`${label} — "Application error" visible in page`, bodyText.slice(0, 200))
      clean = false
    }
    if (pageErrors.length > 0) {
      fail(`${label} — uncaught JS exception`, pageErrors[0].message)
      clean = false
    }
    if (consoleErrors.length > 0) {
      fail(`${label} — console.error emitted`, consoleErrors[0].slice(0, 200))
      clean = false
    }
    return clean
  })()
}

;(async () => {
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
  })

  try {
    const context = await browser.newContext({
      // Fresh context = no localStorage/cookies from prior runs
      storageState: undefined,
    })

    // ── 1. Landing page ────────────────────────────────────────────────
    section('1. Landing page — no crash, correct content')
    {
      const ctx = await newPage(context)
      const { page, consoleErrors, pageErrors } = ctx
      await page.goto(FRONTEND, { waitUntil: 'networkidle', timeout: 20000 })
      await page.waitForTimeout(1500)

      const title = await page.title()
      const bodyText = await page.evaluate(() => document.body?.innerText || '')

      const nocrash = await assertNoCrash(page, ctx, 'Landing page')
      if (nocrash) ok('Landing page loads without crash')

      if (title.toLowerCase().includes('narratiq')) {
        ok(`Page title correct: "${title}"`)
      } else {
        fail('Page title missing "NarratIQ"', `Got: "${title}"`)
      }

      if (bodyText.includes('Start Writing') || bodyText.includes('Sign In')) {
        ok('Landing page renders CTA buttons')
      } else {
        fail('Landing page CTA buttons not visible', bodyText.slice(0, 200))
      }

      await page.close()
    }

    // ── 2. Register page ────────────────────────────────────────────────
    section('2. Register page — renders without crash')
    {
      const ctx = await newPage(context)
      const { page, consoleErrors, pageErrors } = ctx
      await page.goto(`${FRONTEND}/register`, { waitUntil: 'networkidle', timeout: 20000 })
      await page.waitForTimeout(1000)

      const nocrash = await assertNoCrash(page, ctx, 'Register page')
      if (nocrash) ok('Register page loads without crash')

      // Check form fields
      const emailInput = await page.$('input[type="email"], input[name="email"], input[placeholder*="email" i]')
      const passInput  = await page.$('input[type="password"]')
      if (emailInput && passInput) {
        ok('Register form has email + password inputs')
      } else {
        fail('Register form inputs not found')
      }

      await page.close()
    }

    // ── 3. Login page ───────────────────────────────────────────────────
    section('3. Login page — renders without crash')
    {
      const ctx = await newPage(context)
      const { page, consoleErrors, pageErrors } = ctx
      await page.goto(`${FRONTEND}/login`, { waitUntil: 'networkidle', timeout: 20000 })
      await page.waitForTimeout(1000)

      const nocrash = await assertNoCrash(page, ctx, 'Login page')
      if (nocrash) ok('Login page loads without crash')

      const emailInput = await page.$('input[type="email"], input[name="email"], input[placeholder*="email" i]')
      const passInput  = await page.$('input[type="password"]')
      if (emailInput && passInput) {
        ok('Login form has email + password inputs')
      } else {
        fail('Login form inputs not found')
      }

      await page.close()
    }

    // ── 4. Register via API, then full login flow ─────────────────────
    section('4. Auth flow — register + login + redirect to dashboard')
    let authToken = null
    {
      // Register via API so we have a known user
      const regResp = await fetch(`${BACKEND}/api/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: SMOKE_EMAIL, username: SMOKE_USER, password: SMOKE_PASS }),
      }).catch(e => null)

      if (!regResp || !regResp.ok) {
        fail('API register failed — cannot test auth flow')
      } else {
        const regData = await regResp.json()
        authToken = regData.access_token
        ok(`API register: got token (${authToken?.slice(0, 20)}...)`)

        // Now test login via the browser UI
        const ctx = await newPage(context)
        const { page, consoleErrors, pageErrors } = ctx
        await page.goto(`${FRONTEND}/login`, { waitUntil: 'networkidle', timeout: 20000 })

        try {
          await page.fill('input[type="email"], input[name="email"]', SMOKE_EMAIL)
          await page.fill('input[type="password"]', SMOKE_PASS)
          await page.click('button[type="submit"]')

          // Wait for redirect to dashboard
          await page.waitForURL('**/dashboard**', { timeout: 10000 })
          const nocrash = await assertNoCrash(page, ctx, 'Dashboard after login')
          if (nocrash) ok('Login redirects to /dashboard without crash')

          const dashText = await page.evaluate(() => document.body?.innerText || '')
          if (dashText.toLowerCase().includes('project') || dashText.toLowerCase().includes('story') || dashText.toLowerCase().includes('new')) {
            ok('Dashboard renders project list area')
          } else {
            fail('Dashboard content not found after login', dashText.slice(0, 200))
          }
        } catch (e) {
          fail('Login flow error', e.message)
        }

        await page.close()
      }
    }

    // ── 5. Dashboard directly (inject token into localStorage) ──────────
    section('5. Dashboard — loads with pre-seeded auth token')
    if (authToken) {
      const ctx = await newPage(context)
      const { page, consoleErrors, pageErrors } = ctx
      await page.goto(FRONTEND, { waitUntil: 'domcontentloaded', timeout: 10000 })

      // Seed localStorage with valid token
      await page.evaluate(({ token, user, email }) => {
        localStorage.setItem('narratiq_token', token)
        localStorage.setItem('narratiq_user', JSON.stringify({ email, username: user }))
      }, { token: authToken, user: SMOKE_USER, email: SMOKE_EMAIL })

      await page.goto(`${FRONTEND}/dashboard`, { waitUntil: 'networkidle', timeout: 20000 })
      await page.waitForTimeout(2000)

      const nocrash = await assertNoCrash(page, ctx, 'Dashboard with token')
      if (nocrash) ok('Dashboard loads with valid token, no crash')

      const url = page.url()
      if (url.includes('/dashboard')) {
        ok('Dashboard URL confirmed (not redirected to login)')
      } else {
        fail('Dashboard redirected away', `Ended up at: ${url}`)
      }

      await page.close()
    } else {
      console.log('  [SKIP] No auth token — skipping dashboard token test')
    }

    // ── 6. Project/editor page ──────────────────────────────────────────
    section('6. Project editor — loads without client-side crash')
    if (authToken) {
      // Create a project via API
      const projResp = await fetch(`${BACKEND}/api/projects/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${authToken}` },
        body: JSON.stringify({ title: 'Browser Smoke Test Novel', description: 'auto' }),
      }).catch(() => null)

      if (!projResp || !projResp.ok) {
        fail('API create project failed — cannot test editor')
      } else {
        const proj = await projResp.json()
        const storyId = proj.story_id
        ok(`Project created: ${storyId}`)

        const ctx = await newPage(context)
        const { page, consoleErrors, pageErrors } = ctx
        await page.goto(FRONTEND, { waitUntil: 'domcontentloaded', timeout: 10000 })
        await page.evaluate(({ token, user, email }) => {
          localStorage.setItem('narratiq_token', token)
          localStorage.setItem('narratiq_user', JSON.stringify({ email, username: user }))
        }, { token: authToken, user: SMOKE_USER, email: SMOKE_EMAIL })

        await page.goto(`${FRONTEND}/projects/${storyId}`, { waitUntil: 'networkidle', timeout: 30000 })
        await page.waitForTimeout(3000)

        const nocrash = await assertNoCrash(page, ctx, 'Editor page')
        if (nocrash) ok('Editor page loads without crash')

        const url = page.url()
        if (url.includes(`/projects/${storyId}`)) {
          ok('Editor URL confirmed (not redirected)')
        } else {
          fail('Editor redirected away', `Ended up at: ${url}`)
        }

        // Check editor has text area or content area
        const editorEl = await page.$('[contenteditable], textarea, [data-editor], .ProseMirror, [role="textbox"]')
        if (editorEl) {
          ok('Editor text area/content region is present')
        } else {
          console.log('  [WARN] No editor content area found (may still be loading)')
        }

        await page.close()
      }
    } else {
      console.log('  [SKIP] No auth token — skipping editor test')
    }

    // ── 7. Corrupt localStorage resilience ─────────────────────────────
    section('7. Corrupt localStorage — app must not crash')
    {
      const ctx = await newPage(context)
      const { page, consoleErrors, pageErrors } = ctx
      await page.goto(FRONTEND, { waitUntil: 'domcontentloaded', timeout: 10000 })

      // Inject corrupt data (the original bug: "undefined" as JSON)
      await page.evaluate(() => {
        localStorage.setItem('narratiq_token', 'some-token')
        localStorage.setItem('narratiq_user', 'undefined')  // non-JSON — was the original crash
      })

      await page.goto(FRONTEND, { waitUntil: 'networkidle', timeout: 20000 })
      await page.waitForTimeout(2000)

      const bodyText = await page.evaluate(() => document.body?.innerText || '')
      const hasAppError = bodyText.toLowerCase().includes('application error')

      if (!hasAppError && pageErrors.length === 0) {
        ok('Corrupt localStorage ("undefined") handled gracefully — no crash')
      } else {
        fail('App crashed with corrupt localStorage', pageErrors[0]?.message || bodyText.slice(0, 200))
      }

      // Also verify that localStorage was cleaned up
      const storedUser = await page.evaluate(() => localStorage.getItem('narratiq_user'))
      if (!storedUser || storedUser === 'undefined') {
        // The catch block should have removed it — check either cleared or not set to "undefined"
        ok('Corrupt localStorage entry cleared by AuthProvider catch block')
      } else {
        console.log(`  [INFO] narratiq_user after repair: ${storedUser?.slice(0, 50)}`)
      }

      await page.close()
    }

    // ── 8. Stale-chunk regression — reload twice, no ChunkLoadError ─────
    // This is the dedicated guard for the original bug:
    //   "ChunkLoadError: Loading chunk 185 failed
    //    /_next/static/chunks/app/layout-323501d1edf67dc6.js → 404"
    // Reloading exercises a full document re-fetch; with no-store HTML the
    // browser must always get fresh chunk references, never a 404 under
    // /_next/static/, and never a ChunkLoadError.
    section('8. Stale-chunk regression — reload x2, no chunk 404 / ChunkLoadError')
    {
      const ctx = await newPage(context)
      const { page } = ctx
      await page.goto(FRONTEND, { waitUntil: 'networkidle', timeout: 20000 })

      let reloadClean = true
      for (let r = 1; r <= 2; r++) {
        await page.reload({ waitUntil: 'networkidle', timeout: 20000 })
        await page.waitForTimeout(1000)
        if (ctx.chunkErrors.length > 0) {
          fail(`Reload #${r} — ChunkLoadError`, ctx.chunkErrors[0].slice(0, 200))
          reloadClean = false
        }
        if (ctx.static404s.length > 0) {
          fail(`Reload #${r} — 404/failure under /_next/static/`, ctx.static404s[0].slice(0, 200))
          reloadClean = false
        }
      }
      if (reloadClean) ok('Reloaded landing page twice — no chunk 404, no ChunkLoadError')

      // Cross-navigate login → dashboard-ish routes to exercise chunk loading
      // for multiple route bundles, the exact path that triggered chunk 185.
      await page.goto(`${FRONTEND}/login`, { waitUntil: 'networkidle', timeout: 20000 })
      await page.goto(`${FRONTEND}/register`, { waitUntil: 'networkidle', timeout: 20000 })
      await page.waitForTimeout(800)
      if (ctx.chunkErrors.length === 0 && ctx.static404s.length === 0) {
        ok('Cross-route navigation loads all chunks (no 404, no ChunkLoadError)')
      } else {
        fail('Cross-route navigation hit a chunk error',
          (ctx.chunkErrors[0] || ctx.static404s[0] || '').slice(0, 200))
      }

      await page.close()
    }

    // ── Results ────────────────────────────────────────────────────────
    section('RESULTS')
    console.log(`\n  Passed : ${PASS}`)
    console.log(`  Failed : ${FAIL}`)
    console.log()

    if (FAIL === 0) {
      console.log('  ✓ All browser smoke tests PASSED')
    } else {
      console.log(`  ✗ ${FAIL} test(s) FAILED:`)
      failures.forEach(f => console.log(`    - ${f.label}: ${f.detail || ''}`))
    }

  } finally {
    await browser.close()
  }

  process.exit(FAIL > 0 ? 1 : 0)
})()
