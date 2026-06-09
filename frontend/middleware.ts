import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

// ── Force HTML documents to be uncacheable ───────────────────────────────────
// next.config.js `headers()` sets Cache-Control, but for statically-prerendered
// pages Next.js OVERRIDES it with `s-maxage=31536000, stale-while-revalidate`.
// That lets a shared cache (e.g. the RunPod proxy) keep serving an OLD HTML
// document after a redeploy — and that stale HTML references JS chunk hashes
// from the previous build, which no longer exist on disk → 404 → ChunkLoadError.
//
// Middleware runs on every request under `next start` and its response headers
// take precedence, so this reliably stamps no-store on every HTML/RSC response.
// The matcher below excludes the content-hashed immutable assets under
// /_next/static and the image optimizer, which SHOULD stay cacheable.
export function middleware(request: NextRequest) {
  const res = NextResponse.next()
  res.headers.set('Cache-Control', 'no-store, no-cache, must-revalidate, proxy-revalidate')
  res.headers.set('Pragma', 'no-cache')
  res.headers.set('Expires', '0')
  return res
}

export const config = {
  // Apply to everything EXCEPT immutable build assets, the image optimizer,
  // and favicon — those are safe (and desirable) to cache.
  matcher: ['/((?!_next/static/|_next/image|favicon.ico).*)'],
}
