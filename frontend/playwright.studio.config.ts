import { defineConfig, devices } from '@playwright/test'

// `studio` suite — Stage 8 navigation, layout, modes, accessibility and viewport
// checks in a real browser with NO backend. Every API request goes to the
// build-time origin http://mock-api.test and is fulfilled by tests/studio/mockApi.ts.
//
//   npm run test:studio            (builds into .next-studio, then serves it)
//
// The build lands in .next-studio (NEXT_DIST_DIR), never in the real .next that
// start-narratiq.sh serves. PW_CHROMIUM_PATH optionally points at a preinstalled
// Chromium (e.g. /opt/pw-browsers/chromium) instead of `playwright install`.
// STUDIO_SKIP_BUILD=1 reuses an existing .next-studio build.
const PORT = Number(process.env.STUDIO_PORT ?? 3100)
const env = {
  NEXT_PUBLIC_API_URL: 'http://mock-api.test',
  NEXT_DIST_DIR: '.next-studio',
  NEXT_TELEMETRY_DISABLED: '1',
}

export default defineConfig({
  testDir: './tests/studio',
  outputDir: './.studio-results',
  fullyParallel: true,
  workers: process.env.CI ? 2 : 4,
  reporter: 'list',
  use: {
    ...devices['Desktop Chrome'],
    baseURL: `http://localhost:${PORT}`,
    viewport: { width: 1366, height: 768 },
    launchOptions: process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {},
  },
  webServer: {
    command: process.env.STUDIO_SKIP_BUILD
      ? `npx next start -p ${PORT}`
      : `npx next build && npx next start -p ${PORT}`,
    url: `http://localhost:${PORT}/login`,
    env,
    timeout: 600_000,
    reuseExistingServer: false,
  },
})
