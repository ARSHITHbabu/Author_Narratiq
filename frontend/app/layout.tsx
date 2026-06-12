import type { Metadata } from 'next'
import './globals.css'
import { AuthProvider } from '@/lib/auth'
import { Toaster } from 'sonner'
import ChunkErrorRecovery from '@/components/chunk-error-recovery'
import QueryProvider from '@/components/providers/QueryProvider'

// ── Disable static prerendering of HTML shells ───────────────────────────────
// By default Next.js prerenders these client shells as STATIC and serves them
// with `Cache-Control: s-maxage=31536000, stale-while-revalidate`. That header
// lets a shared cache hold a stale HTML document after a redeploy, and the stale
// HTML references JS chunk hashes from the OLD build → 404 → ChunkLoadError.
// Rendering on demand makes Next emit `Cache-Control: no-store` instead, so every
// document load references the CURRENT build's chunks. These shells are all
// 'use client' with no server data-fetching, so on-demand rendering costs ~nothing.
export const dynamic = 'force-dynamic'
export const fetchCache = 'force-no-store'

export const metadata: Metadata = {
  title: 'NarratIQ AI — AI-Powered Long-Form Storytelling',
  description: 'The AI writing studio for serious novelists. Story memory, genre intelligence, plot assistance, and literary transformation.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
      </head>
      <body>
        <ChunkErrorRecovery />
        <QueryProvider>
        <AuthProvider>
          {children}
          <Toaster
            position="bottom-right"
            theme="dark"
            toastOptions={{
              style: {
                background: '#1a1e36',
                border: '1px solid #2e3454',
                color: '#e8eaf6',
              },
            }}
          />
        </AuthProvider>
        </QueryProvider>
      </body>
    </html>
  )
}
