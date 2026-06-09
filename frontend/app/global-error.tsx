'use client'

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  return (
    <html lang="en">
      <body style={{ background: '#0d0f1a', color: '#e8eaf6', fontFamily: 'Inter, system-ui, sans-serif', padding: '40px', minHeight: '100vh' }}>
        <div style={{ maxWidth: '720px', margin: '0 auto' }}>
          <h1 style={{ color: '#f59e0b', fontSize: '1.5rem', marginBottom: '8px' }}>NarratIQ — Application Error</h1>
          <p style={{ color: '#9da3c8', marginBottom: '24px' }}>A client-side exception occurred. Copy the details below and report them.</p>

          <div style={{ background: '#13162a', border: '1px solid #2e3454', borderRadius: '8px', padding: '20px', marginBottom: '16px' }}>
            <p style={{ color: '#f59e0b', fontWeight: 600, marginBottom: '8px' }}>Error: {error?.message || '(no message)'}</p>
            {error?.digest && (
              <p style={{ color: '#5c6391', fontSize: '0.875rem', marginBottom: '8px' }}>Digest: {error.digest}</p>
            )}
            {error?.stack && (
              <pre style={{ color: '#9da3c8', fontSize: '0.75rem', overflow: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
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
      </body>
    </html>
  )
}
