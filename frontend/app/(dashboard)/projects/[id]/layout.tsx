'use client'

// Story layout — the assembly point for the Author Studio:
//   QueryClient (global) → StudioStoreGate (per-user layout) → StoryContextEngine → CollaborationBoundary → StudioShell → workspace
// Every workspace route under /projects/[id]/* renders inside this shell and shares
// one Story Context Engine (single source of truth) and one persistent chrome.

import { useParams } from 'next/navigation'
import StoryContextEngine from '@/components/studio/StoryContextEngine'
import CollaborationBoundary from '@/components/studio/CollaborationBoundary'
import StudioShell from '@/components/studio/StudioShell'
import StudioStoreGate from '@/components/studio/StudioStoreGate'

export default function StoryLayout({ children }: { children: React.ReactNode }) {
  // Next.js 15 (Stage 12 A5): route params come from useParams(); the page prop
  // is a Promise in Next 15, and a client component cannot await it.
  const params = useParams<{ id: string }>()
  return (
    <StudioStoreGate>
      <StoryContextEngine storyId={params.id}>
        <CollaborationBoundary>
          <StudioShell>{children}</StudioShell>
        </CollaborationBoundary>
      </StoryContextEngine>
    </StudioStoreGate>
  )
}
