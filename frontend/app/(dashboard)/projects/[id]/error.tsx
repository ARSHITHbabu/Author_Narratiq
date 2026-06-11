'use client'

import { useEffect } from 'react'
import Link from 'next/link'
import { AlertTriangle, RotateCcw, ArrowLeft } from 'lucide-react'

export default function EditorError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    console.error('[EditorError]', error)
  }, [error])

  return (
    <div className="h-screen bg-[#0d0f1a] flex items-center justify-center p-6">
      <div className="max-w-md w-full bg-[#1a1e36] border border-red-500/20 rounded-2xl p-8 text-center">
        <div className="flex justify-center mb-4">
          <div className="w-14 h-14 rounded-full bg-red-500/10 flex items-center justify-center">
            <AlertTriangle className="w-7 h-7 text-red-400" />
          </div>
        </div>

        <h1 className="text-lg font-semibold text-[#e8eaf6] mb-2">Editor encountered an error</h1>
        <p className="text-sm text-[#5c6391] mb-1">
          Something went wrong while loading this manuscript.
        </p>
        {error.digest && (
          <p className="text-xs text-[#3d4466] font-mono mb-6">ref: {error.digest}</p>
        )}

        <div className="flex flex-col gap-3 mt-6">
          <button
            onClick={reset}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400 hover:bg-amber-500/20 transition-colors text-sm font-medium"
          >
            <RotateCcw className="w-4 h-4" />
            Try again
          </button>
          <Link
            href="/dashboard"
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-[#252a45] border border-[#2e3454] text-[#9da3c8] hover:text-[#e8eaf6] transition-colors text-sm"
          >
            <ArrowLeft className="w-4 h-4" />
            Return to dashboard
          </Link>
        </div>
      </div>
    </div>
  )
}
