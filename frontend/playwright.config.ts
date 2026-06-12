import { defineConfig } from '@playwright/test'

// Minimal config. The transforms spec is pure-logic (no browser) — it validates the
// shared transform config + correct ai_transform endpoint routing.
export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  reporter: 'list',
})
