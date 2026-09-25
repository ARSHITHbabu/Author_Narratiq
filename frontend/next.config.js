/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  // The mocked-API `studio` Playwright suite builds into its own directory so it
  // can never overwrite the real `.next` build that start-narratiq.sh serves.
  distDir: process.env.NEXT_DIST_DIR || '.next',

  // Always defined, so the build folds `=== 'true'` to a constant and drops the
  // test-only mock tool from normal builds (an undefined NEXT_PUBLIC_ variable
  // is left as a runtime lookup and its branch would be bundled).
  env: {
    NEXT_PUBLIC_E2E_MOCK_TOOL: process.env.NEXT_PUBLIC_E2E_MOCK_TOOL === 'true' ? 'true' : 'false',
  },

  // ── Cache strategy — prevents stale HTML → ChunkLoadError ──────────────
  // The bug: after a rebuild, the browser (or a CDN/proxy like the RunPod
  // proxy) served an OLD cached HTML document that referenced JS chunk hashes
  // from the previous build (e.g. layout-323501d1edf67dc6.js). Those chunks no
  // longer exist on disk, so the browser got a 404 → webpack threw
  // "ChunkLoadError: Loading chunk 185 failed".
  //
  // Fix: HTML documents must NEVER be cached, so every navigation re-fetches
  // fresh HTML that points at the CURRENT build's chunk hashes. The hashed
  // assets under /_next/static/ ARE content-addressed (the hash changes when
  // the content changes), so they are safe — and beneficial — to cache forever.
  async headers() {
    return [
      {
        // Content-hashed immutable build assets — cache aggressively.
        source: '/_next/static/:path*',
        headers: [
          { key: 'Cache-Control', value: 'public, max-age=31536000, immutable' },
        ],
      },
      {
        // Everything else (HTML documents, RSC payloads, API rewrites) — never
        // cache. The negative lookahead excludes the static assets above so we
        // don't accidentally mark immutable chunks as no-store.
        source: '/((?!_next/static/).*)',
        headers: [
          { key: 'Cache-Control', value: 'no-store, no-cache, must-revalidate, proxy-revalidate' },
          { key: 'Pragma', value: 'no-cache' },
          { key: 'Expires', value: '0' },
        ],
      },
    ]
  },
}

module.exports = nextConfig
