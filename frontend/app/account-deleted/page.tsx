import Link from 'next/link'
import { Feather } from 'lucide-react'

// Shown after a successful account deletion (Stage 10, 10.6). Public: the
// session no longer exists, so this page must not require one.
export default function AccountDeletedPage() {
  return (
    <main className="min-h-screen bg-[#0d0f1a] flex items-center justify-center px-4">
      <div className="w-full max-w-md bg-[#13162a] border border-[#1f2440] rounded-2xl p-8 text-center">
        <Feather className="w-6 h-6 text-amber-500 mx-auto mb-4" aria-hidden />
        <h1 className="text-xl font-bold mb-2">Your account has been deleted</h1>
        <p className="text-sm text-[#9da3c8] mb-2">
          Your account, manuscripts and uploads have been permanently removed, and you have been signed out on every device.
        </p>
        <p className="text-sm text-[#9da3c8] mb-6">
          Copies in NarratIQ&apos;s backups expire automatically, as described in the{' '}
          <Link href="/data-policy" className="text-amber-400 underline underline-offset-2">data policy</Link>.
        </p>
        <Link href="/" className="inline-block bg-amber-500 hover:bg-amber-600 text-black font-semibold px-5 py-2.5 rounded-xl text-sm transition-colors">
          Return to the home page
        </Link>
      </div>
    </main>
  )
}
