'use client'

import { useEffect } from 'react'
import { reportClientError } from '@/lib/errorReporting'

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    console.error('[NarratIQ Error]', error)

    // If this boundary caught a stale-build chunk failure, force a one-time
    // reload to pull fresh HTML pointing at the current build's chunks. Guarded
    // by sessionStorage so a permanently-missing chunk can't loop forever.
    const msg = `${error?.name || ''} ${error?.message || ''}`
    const isChunkError =
      error?.name === 'ChunkLoadError' ||
      /Loading chunk [\d]+ failed/i.test(msg) ||
      /Failed to fetch dynamically imported module/i.test(msg)
    // Stage 10 (10.2): record it in NarratIQ's own error tracking. A stale-build
    // chunk failure is expected after a redeploy and self-heals by reloading.
    if (!isChunkError) reportClientError(error, 'page')
    if (isChunkError) {
      try {
        const KEY = 'narratiq_chunk_reload_ts'
        const last = Number(sessionStorage.getItem(KEY) || '0')
        if (Date.now() - last > 10_000) {
          sessionStorage.setItem(KEY, String(Date.now()))
          window.location.reload()
        }
      } catch {
        window.location.reload()
      }
    }
  }, [error])

  return (
    <div style={{ minHeight: '100vh', background: '#0d0f1a', color: '#e8eaf6', fontFamily: 'Inter, system-ui, sans-serif', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '40px' }}>
      <div style={{ maxWidth: '560px', width: '100%' }}>
        <h1 style={{ color: '#f59e0b', fontSize: '1.5rem', marginBottom: '8px' }}>Something went wrong on this page</h1>
        <p style={{ color: '#9da3c8', marginBottom: '8px' }}>
          Everything you had already saved is safe; only unsaved changes on this screen may be lost.
        </p>
        <p style={{ color: '#9da3c8', marginBottom: '24px' }}>
          The problem has been recorded for the NarratIQ team. Try again, or go back to your manuscripts.
        </p>
        {error?.digest && <p style={{ color: '#8a90ba', fontSize: '0.8rem', marginBottom: '16px' }}>Reference: {error.digest}</p>}
        <button
          onClick={reset}
          style={{ background: '#f59e0b', color: '#000', border: 'none', borderRadius: '8px', padding: '10px 24px', fontWeight: 600, cursor: 'pointer' }}
        >
          Try again
        </button>
      </div>
    </div>
  )
}
