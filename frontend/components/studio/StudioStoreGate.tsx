'use client'

// Binds the studio store to the signed-in user before any studio UI renders, so
// the first frame already shows this user's own layout (no flash of another
// account's or the default layout) — Stage 8.2 per-user persistence.

import { useEffect, useState, type ReactNode } from 'react'
import { useAuth } from '@/lib/auth'
import { bindStudioStoreToUser, studioKeyFor, useStudioStore } from '@/lib/studioStore'

export default function StudioStoreGate({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const userId = user?.user_id ?? null
  const boundKey = useStudioStore((s) => s.boundKey)
  const [, force] = useState(0)

  useEffect(() => {
    let live = true
    bindStudioStoreToUser(userId).then(() => { if (live) force((n) => n + 1) })
    return () => { live = false }
  }, [userId])

  if (boundKey !== studioKeyFor(userId)) {
    return <div className="h-screen bg-[#0d0f1a]" aria-busy="true" />
  }
  return <>{children}</>
}
