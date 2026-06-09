'use client'

import { useEffect } from 'react'

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
      <div style={{ maxWidth: '680px', width: '100%' }}>
        <h1 style={{ color: '#f59e0b', fontSize: '1.5rem', marginBottom: '8px' }}>NarratIQ — Something went wrong</h1>
        <p style={{ color: '#9da3c8', marginBottom: '24px' }}>A rendering error occurred. Details below.</p>
        <div style={{ background: '#13162a', border: '1px solid #2e3454', borderRadius: '8px', padding: '20px', marginBottom: '16px' }}>
          <p style={{ color: '#f59e0b', fontWeight: 600, marginBottom: '8px' }}>Error: {error?.message || '(no message)'}</p>
          {error?.digest && <p style={{ color: '#5c6391', fontSize: '0.875rem', marginBottom: '8px' }}>Digest: {error.digest}</p>}
          {error?.stack && (
            <pre style={{ color: '#9da3c8', fontSize: '0.75rem', overflow: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-word', marginTop: '8px' }}>
              {error.stack}
            </pre>
          )}
        </div>
        <button
          onClick={reset}
          style={{ background: '#f59e0b', color: '#000', border: 'none', borderRadius: '8px', padding: '10px 24px', fontWeight: 600, cursor: 'pointer' }}
        >
          Try Again
        </button>
      </div>
    </div>
  )
}
