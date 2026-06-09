// Diagnostic script: open the frontend and capture all JS errors
const { chromium } = require('@playwright/test')

;(async () => {
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
  })
  const context = await browser.newContext()
  const page = await context.newPage()

  const consoleErrors = []
  const pageErrors = []

  page.on('console', msg => {
    if (msg.type() === 'error') {
      consoleErrors.push({ text: msg.text(), location: msg.location() })
    }
  })
  page.on('pageerror', err => {
    pageErrors.push({ message: err.message, stack: err.stack })
  })

  console.log('=== Navigating to http://localhost:3000 ===')
  try {
    await page.goto('http://localhost:3000', { waitUntil: 'networkidle', timeout: 30000 })
  } catch (e) {
    console.log('Navigation error:', e.message)
  }

  // Wait a bit for any async errors
  await page.waitForTimeout(3000)

  const title = await page.title()
  const bodyText = await page.evaluate(() => document.body?.innerText?.slice(0, 500) || '')
  const url = page.url()

  console.log('Page URL:', url)
  console.log('Page title:', title)
  console.log('Body text (first 500):', bodyText)
  console.log()

  console.log('=== Console Errors ===')
  if (consoleErrors.length === 0) {
    console.log('  (none)')
  } else {
    consoleErrors.forEach((e, i) => {
      console.log(`  [${i + 1}] ${e.text}`)
      if (e.location?.url) console.log(`       at ${e.location.url}:${e.location.lineNumber}`)
    })
  }

  console.log()
  console.log('=== Page Errors (uncaught exceptions) ===')
  if (pageErrors.length === 0) {
    console.log('  (none)')
  } else {
    pageErrors.forEach((e, i) => {
      console.log(`  [${i + 1}] ${e.message}`)
      if (e.stack) console.log(e.stack.split('\n').slice(0, 8).map(l => '       ' + l).join('\n'))
    })
  }

  // Check for "Application error" text
  const hasAppError = bodyText.includes('Application error') || title.includes('Application error')
  console.log()
  console.log('=== Result ===')
  console.log('  Application error visible:', hasAppError)
  console.log('  Console errors:', consoleErrors.length)
  console.log('  Page errors:', pageErrors.length)

  await browser.close()
  process.exit(hasAppError || pageErrors.length > 0 ? 1 : 0)
})()
