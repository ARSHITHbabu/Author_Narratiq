'use client'

// Story layout — the assembly point for the Author Studio:
//   QueryClient (global) → StoryContextEngine → CollaborationBoundary → StudioShell → workspace
// Every workspace route under /projects/[id]/* renders inside this shell and shares
// one Story Context Engine (single source of truth) and one persistent chrome.

import StoryContextEngine from '@/components/studio/StoryContextEngine'
import CollaborationBoundary from '@/components/studio/CollaborationBoundary'
import StudioShell from '@/components/studio/StudioShell'

export default function StoryLayout({ children, params }: { children: React.ReactNode; params: { id: string } }) {
  return (
    <StoryContextEngine storyId={params.id}>
      <CollaborationBoundary>
        <StudioShell>{children}</StudioShell>
      </CollaborationBoundary>
    </StoryContextEngine>
  )
}
