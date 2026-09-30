'use client'

import { useEffect } from 'react'
import { reportClientError } from '@/lib/errorReporting'

// Last-resort boundary (the root layout itself failed). Stage 10 (10.2): the
// error is reported to NarratIQ's own error tracking; the author sees what
// happened and what to do — never a raw message or stack trace.
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => { reportClientError(error, 'global') }, [error])
  return (
    <html lang="en">
      <body style={{ background: '#0d0f1a', color: '#e8eaf6', fontFamily: 'Inter, system-ui, sans-serif', padding: '40px', minHeight: '100vh' }}>
        <div style={{ maxWidth: '560px', margin: '0 auto' }}>
          <h1 style={{ color: '#f59e0b', fontSize: '1.5rem', marginBottom: '8px' }}>NarratIQ ran into a problem</h1>
          <p style={{ color: '#9da3c8', marginBottom: '8px' }}>
            This page stopped working. Everything you had already saved is safe; only unsaved changes on this screen may be lost.
          </p>
          <p style={{ color: '#9da3c8', marginBottom: '24px' }}>
            The problem has been recorded for the NarratIQ team. Try again, or reload the page.
          </p>
          {error?.digest && (
            <p style={{ color: '#8a90ba', fontSize: '0.8rem', marginBottom: '16px' }}>Reference: {error.digest}</p>
          )}
          <button
            onClick={reset}
            style={{ background: '#f59e0b', color: '#000', border: 'none', borderRadius: '8px', padding: '10px 24px', fontWeight: 600, cursor: 'pointer' }}
          >
            Try again
          </button>
        </div>
      </body>
    </html>
  )
}
