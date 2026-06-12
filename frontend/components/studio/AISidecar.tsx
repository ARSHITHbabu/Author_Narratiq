'use client'

// AI Sidecar — the contextual, collapsible, resizable AI dock for the Write
// workspace. Reuses the existing AIToolsSidebar (refine/tone/emotion/adapt/continue,
// all selection-aware) instead of a crowded tab. Default closed so the editor leads.

import dynamic from 'next/dynamic'
import { X, Mic } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { useStoryContext } from './StoryContextEngine'
import { useStudioStore } from '@/lib/studioStore'
import { workspacePath } from '@/lib/registries/workspaces'

const AIToolsSidebar = dynamic(() => import('@/components/ai-tools/AIToolsSidebar'), { ssr: false })

export default function AISidecar() {
  const router = useRouter()
  const store = useStudioStore()
  const { storyId, activeChapterId, editor } = useStoryContext()

  return (
    <div className="h-full flex flex-col bg-[#0f1220] border-l border-[#1f2440]">
      <div className="h-10 flex items-center justify-between px-3 border-b border-[#1f2440] flex-shrink-0">
        <span className="text-xs font-medium text-[#e8eaf6]">AI Assistant</span>
        <div className="flex items-center gap-1">
          <button onClick={() => router.push(workspacePath(storyId, 'assistant'))}
            className="p-1 rounded text-[#9da3c8] hover:text-white hover:bg-[#1f2440]" title="Voice agent">
            <Mic className="w-3.5 h-3.5" />
          </button>
          <button onClick={() => store.toggleSidecar(false)}
            className="p-1 rounded text-[#9da3c8] hover:text-white hover:bg-[#1f2440]" title="Close (⌘\\)">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
      <div className="flex-1 overflow-hidden">
        {activeChapterId && (
          <AIToolsSidebar
            storyId={storyId}
            chapterId={activeChapterId}
            getSelectedText={() => editor?.getSelectedText() || ''}
            getFullText={() => editor?.getFullText() || ''}
            insertText={(text: string) => editor?.insertText(text)}
          />
        )}
      </div>
    </div>
  )
}
