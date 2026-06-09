#!/usr/bin/env node
// ═══════════════════════════════════════════════════════════════
//  NarratIQ — Proxy/Cloudflare chunk verification (Playwright)
//
//  Loads the REAL RunPod proxy URL in a headless browser and reports,
//  per URL, whether the browser hits a ChunkLoadError / deleted chunk.
//
//  Usage:
//    node scripts/smoke_test_proxy.js <fullUrl> [label]
// ═══════════════════════════════════════════════════════════════
const FRONTEND_ROOT = require('path').resolve(__dirname, '../frontend')
const { chromium } = require(require.resolve('@playwright/test', { paths: [FRONTEND_ROOT] }))

const URL = process.argv[2]
const LABEL = process.argv[3] || URL
const DEAD_CHUNK = 'layout-323501d1edf67dc6.js' // the deleted chunk from the error report

function isChunkError(t) {
  return /ChunkLoadError/i.test(t) || /Loading chunk [\d]+ failed/i.test(t) ||
         /Loading CSS chunk/i.test(t) || /Failed to fetch dynamically imported module/i.test(t)
}

;(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] })
  const ctx = await browser.newContext()           // fresh — no browser cache from prior runs
  const page = await ctx.newPage()

  const chunkErrors = []
  const static404s = []
  const consoleErrors = []
  let docCacheStatus = '(none)'
  let docCacheControl = '(none)'

  page.on('console', m => { if (m.type() === 'error') { const t = m.text(); if (isChunkError(t)) chunkErrors.push(t); else if (!/401|favicon/.test(t)) consoleErrors.push(t) } })
  page.on('pageerror', e => { if (isChunkError(e.message)) chunkErrors.push(e.message) })
  page.on('response', r => {
    if (r.url().includes('/_next/static/') && r.status() >= 400) static404s.push(`${r.status()} ${r.url()}`)
    if (r.url().split('?')[0] === URL.split('?')[0]) {
      const h = r.headers()
      docCacheStatus = h['cf-cache-status'] || '(none)'
      docCacheControl = h['cache-control'] || '(none)'
    }
  })
  page.on('requestfailed', r => { if (r.url().includes('/_next/static/')) static404s.push(`FAILED ${r.url()}`) })

  console.log(`\n─── Testing: ${LABEL}`)
  console.log(`    URL: ${URL}`)
  let html = ''
  try {
    await page.goto(URL, { waitUntil: 'networkidle', timeout: 30000 })
    html = await page.content()
    await page.waitForTimeout(1500)
    // reload twice
    for (let i = 1; i <= 2; i++) { await page.reload({ waitUntil: 'networkidle', timeout: 30000 }).catch(() => {}); await page.waitForTimeout(800) }
  } catch (e) {
    console.log(`    goto error: ${e.message}`)
  }

  const refsDead = html.includes(DEAD_CHUNK)
  const layoutRefs = [...new Set((html.match(/layout-[a-f0-9]+\.js/g) || []))]
  const bodyText = await page.evaluate(() => document.body?.innerText || '').catch(() => '')
  const appError = /application error|client-side exception/i.test(bodyText)

  console.log(`    cf-cache-status : ${docCacheStatus}`)
  console.log(`    cache-control   : ${docCacheControl}`)
  console.log(`    layout chunk in HTML : ${layoutRefs.join(', ') || '(none)'}`)
  console.log(`    references DELETED chunk (${DEAD_CHUNK}) : ${refsDead ? 'YES ✗' : 'no ✓'}`)
  console.log(`    ChunkLoadError(s)    : ${chunkErrors.length ? 'YES ✗ — ' + chunkErrors[0].slice(0,120) : 'none ✓'}`)
  console.log(`    /_next/static 404(s) : ${static404s.length ? 'YES ✗ — ' + static404s[0].slice(0,120) : 'none ✓'}`)
  console.log(`    "Application error" visible : ${appError ? 'YES ✗' : 'no ✓'}`)
  console.log(`    console.error(s)     : ${consoleErrors.length ? consoleErrors.length + ' — ' + consoleErrors[0].slice(0,100) : 'none ✓'}`)

  const PASS = !refsDead && chunkErrors.length === 0 && static404s.length === 0 && !appError
  console.log(`    RESULT: ${PASS ? '✓ PASS — no chunk error' : '✗ FAIL — stale chunk / ChunkLoadError present'}`)

  await browser.close()
  process.exit(PASS ? 0 : 1)
})()
