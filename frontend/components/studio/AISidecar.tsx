'use client'

// AI Sidecar — the contextual, collapsible, resizable AI dock for the Write
// workspace. Reuses the existing AIToolsSidebar (refine/tone/emotion/adapt/continue,
// all selection-aware) instead of a crowded tab. Default closed so the editor leads.
//
// While this dock is on screen it OWNS the text selection (PRE-2 / QA Issue 11) and
// the floating toolbar stands down. Two consequences are handled here: the workspace
// passes the live selection in, so the scope this panel reports is never stale; and
// the dock is marked selection-safe, so clicking inside it does not read as the
// author abandoning their selection.

import dynamic from 'next/dynamic'
import { X, Maximize2, Minimize2 } from 'lucide-react'
import { useStoryContext } from './StoryContextEngine'
import { useStudioStore } from '@/lib/studioStore'
import { selectionSafeProps, type OwnedSelection } from '@/lib/selectionOwnership'

const AIToolsSidebar = dynamic(() => import('@/components/ai-tools/AIToolsSidebar'), { ssr: false })

export default function AISidecar({ selection = null }: { selection?: OwnedSelection | null }) {
  const store = useStudioStore()
  const { storyId, activeChapterId, editor, genreProfile } = useStoryContext()

  return (
    <aside aria-labelledby="ai-sidecar-title" className="h-full flex flex-col bg-[#0f1220] border-l border-[#1f2440]" {...selectionSafeProps()}>
      <div className="h-10 flex items-center justify-between px-3 border-b border-[#1f2440] flex-shrink-0">
        <h2 id="ai-sidecar-title" className="text-xs font-medium text-[#e8eaf6]" tabIndex={-1}>AI Assistant</h2>
        <div className="flex items-center gap-1">
          {/* The voice agent has one entry point: the mic in the context bar. */}
          <button onClick={() => store.setSidecarExpanded(!store.sidecarExpanded)}
            aria-label={store.sidecarExpanded ? 'Restore AI assistant width' : 'Expand AI assistant'}
            aria-pressed={store.sidecarExpanded}
            className="p-1 rounded text-[#9da3c8] hover:text-white hover:bg-[#1f2440] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/70"
            title={store.sidecarExpanded ? 'Restore width' : 'Expand for detailed work'}>
            {store.sidecarExpanded ? <Minimize2 className="w-3.5 h-3.5" aria-hidden="true" /> : <Maximize2 className="w-3.5 h-3.5" aria-hidden="true" />}
          </button>
          <button onClick={() => store.toggleSidecar(false)} aria-label="Close AI assistant"
            className="p-1 rounded text-[#9da3c8] hover:text-white hover:bg-[#1f2440] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/70" title="Close (⌘\\)">
            <X className="w-3.5 h-3.5" aria-hidden="true" />
          </button>
        </div>
      </div>
      <div className="flex-1 overflow-hidden">
        {activeChapterId && (
          <AIToolsSidebar
            storyId={storyId}
            chapterId={activeChapterId}
            liveSelection={selection}
            getSelectedText={() => editor?.getSelectedText() || ''}
            getFullText={() => editor?.getFullText() || ''}
            insertText={(text: string) => editor?.insertText(text)}
            genreProfile={genreProfile}
          />
        )}
      </div>
    </aside>
  )
}
