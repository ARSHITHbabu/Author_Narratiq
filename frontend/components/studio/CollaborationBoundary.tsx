'use client'

// Collaboration Boundary — architecture seam for future multi-user features.
// Today it is a pass-through. It exists so Story Members / Roles / Permissions /
// Comments / Review Sessions / Presence / Shared Workspaces can be layered in later
// WITHOUT touching the workspaces below it. Permission gating already flows through
// the Story Context Engine's `can(action)` (currently always true for the owner).

import type { ReactNode } from 'react'

export default function CollaborationBoundary({ children }: { children: ReactNode }) {
  // Future: subscribe to presence, inject comment threads, enforce role gates.
  // For now: render children unchanged (single-owner mode).
  return <>{children}</>
}
