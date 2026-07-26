import { defineConfig, devices } from '@playwright/test'

// Two projects, deliberately separated.
//
//   unit    — pure logic, no browser, no running stack. This is the default run:
//               npx playwright test              (or --project=unit)
//   browser — real end-to-end checks against a running frontend + backend and a
//             story that has at least one chapter. Needs browser binaries
//             (`npx playwright install chromium`) and seeded data, so it is opt-in
//             and must never be reported as passing until it has actually run:
//               npx playwright test --project=browser
//
// Browser-project environment: E2E_BASE_URL, E2E_EMAIL, E2E_PASSWORD, E2E_STORY_ID.
export default defineConfig({
  fullyParallel: true,
  reporter: 'list',
  projects: [
    {
      name: 'unit',
      testDir: './tests',
      testIgnore: '**/browser/**',
    },
    {
      name: 'browser',
      testDir: './tests/browser',
      use: {
        ...devices['Desktop Chrome'],
        baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:3000',
        viewport: { width: 1366, height: 768 },   // the reported QA resolution
      },
    },
  ],
})
