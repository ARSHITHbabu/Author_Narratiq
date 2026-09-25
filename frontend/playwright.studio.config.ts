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
// STUDIO_SKIP_BUILD=1 reuses an existing build.
//
// Build variants (STUDIO_VARIANT), each in its own directory:
//   default    — the product as shipped
//   mock-tool  — NEXT_PUBLIC_E2E_MOCK_TOOL=true: one extra test-only tool (8.7)
//   p3-off     — NEXT_PUBLIC_P3_ENABLED=false: the Phase 3 rollback build (L5)
// Specs that need a variant skip themselves in the others.
const PORT = Number(process.env.STUDIO_PORT ?? 3100)
const VARIANT = process.env.STUDIO_VARIANT ?? 'default'
const VARIANT_ENV: Record<string, Record<string, string>> = {
  default: {},
  'mock-tool': { NEXT_PUBLIC_E2E_MOCK_TOOL: 'true' },
  'p3-off': { NEXT_PUBLIC_P3_ENABLED: 'false' },
}
const env = {
  NEXT_PUBLIC_API_URL: 'http://mock-api.test',
  NEXT_DIST_DIR: VARIANT === 'default' ? '.next-studio' : `.next-studio-${VARIANT}`,
  NEXT_TELEMETRY_DISABLED: '1',
  ...VARIANT_ENV[VARIANT],
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
