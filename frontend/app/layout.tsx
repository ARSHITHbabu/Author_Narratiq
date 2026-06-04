import type { Metadata } from 'next'
import './globals.css'
import { AuthProvider } from '@/lib/auth'
import { Toaster } from 'sonner'

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
      </body>
    </html>
  )
}
