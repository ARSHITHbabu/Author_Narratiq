'use client'

import { useEffect } from 'react'

// ── ChunkLoadError self-heal ────────────────────────────────────────────────
// Cache-Control headers fix FUTURE navigations, but a tab that is ALREADY open
// still holds stale HTML in memory. When the user clicks a link, that stale HTML
// asks webpack to load a chunk hash from the previous build — which 404s after a
// redeploy — and webpack throws "ChunkLoadError: Loading chunk N failed".
//
// This component listens for that specific failure and force-reloads the page
// ONCE so the browser pulls the fresh (no-store) HTML pointing at current chunks.
// A sessionStorage guard prevents an infinite reload loop if the chunk is
// genuinely, permanently missing (e.g. server actually down).
const RELOAD_GUARD_KEY = 'narratiq_chunk_reload_ts'
const RELOAD_DEBOUNCE_MS = 10_000

function isChunkLoadError(reason: unknown): boolean {
  if (!reason) return false
  const name = (reason as { name?: string }).name || ''
  const message = (reason as { message?: string }).message || String(reason)
  return (
    name === 'ChunkLoadError' ||
    /Loading chunk [\d]+ failed/i.test(message) ||
    /Loading CSS chunk/i.test(message) ||
    /Failed to fetch dynamically imported module/i.test(message)
  )
}

function reloadOnce() {
  try {
    const last = Number(sessionStorage.getItem(RELOAD_GUARD_KEY) || '0')
    const now = Date.now()
    // If we reloaded very recently, the fresh HTML still failed — stop looping
    // and let the error boundary show, rather than thrash the browser.
    if (now - last < RELOAD_DEBOUNCE_MS) return
    sessionStorage.setItem(RELOAD_GUARD_KEY, String(now))
  } catch {
    // sessionStorage unavailable (private mode quota etc.) — best-effort reload.
  }
  // Cache-busting reload to bypass any intermediary proxy cache of the HTML.
  window.location.reload()
}

export default function ChunkErrorRecovery() {
  useEffect(() => {
    const onError = (event: ErrorEvent) => {
      if (isChunkLoadError(event.error) || isChunkLoadError(event.message)) {
        reloadOnce()
      }
    }
    const onRejection = (event: PromiseRejectionEvent) => {
      if (isChunkLoadError(event.reason)) {
        reloadOnce()
      }
    }
    window.addEventListener('error', onError)
    window.addEventListener('unhandledrejection', onRejection)
    return () => {
      window.removeEventListener('error', onError)
      window.removeEventListener('unhandledrejection', onRejection)
    }
  }, [])

  return null
}
