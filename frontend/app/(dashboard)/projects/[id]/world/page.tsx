'use client'

// World Workspace — reference & worldbuilding. Reuses Story Bible, Notes, and OCR
// (handwritten worldbuilding intake) as sections of one workspace.

import dynamic from 'next/dynamic'
import { useState } from 'react'
import { BookOpen, StickyNote, Camera } from 'lucide-react'
import { useStoryContext } from '@/components/studio/StoryContextEngine'

const StoryBiblePanel = dynamic(() => import('@/components/story-bible/StoryBiblePanel'), { ssr: false })
const NotesPanel = dynamic(() => import('@/components/notes/NotesPanel'), { ssr: false })
const OCRPanel = dynamic(() => import('@/components/ocr/OCRPanel'), { ssr: false })

const SECTIONS = [
  { id: 'bible', label: 'Story Bible', icon: BookOpen },
  { id: 'notes', label: 'Notes', icon: StickyNote },
  { id: 'ocr', label: 'Scan (OCR)', icon: Camera },
] as const

export default function WorldWorkspace() {
  const { storyId, activeChapterId, loading, reloadChapters } = useStoryContext()
  const [section, setSection] = useState<typeof SECTIONS[number]['id']>('bible')
  const [notesReload, setNotesReload] = useState(0)

  return (
    <div className="h-full flex flex-col bg-[#0d0f1a]">
      <div className="h-10 flex items-center gap-1 px-3 border-b border-[#1f2440] flex-shrink-0">
        {SECTIONS.map((s) => (
          <button key={s.id} onClick={() => setSection(s.id)}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs ${section === s.id ? 'bg-amber-500/10 text-amber-400' : 'text-[#9da3c8] hover:text-white hover:bg-[#1f2440]'}`}>
            <s.icon className="w-3.5 h-3.5" /> {s.label}
          </button>
        ))}
      </div>
      <div className="flex-1 overflow-hidden">
        {section === 'bible' && <StoryBiblePanel storyId={storyId} />}
        {section === 'notes' && <NotesPanel storyId={storyId} reloadKey={notesReload} />}
        {/* Scanning does not depend on a chapter. Gating the whole panel on
            `activeChapterId` made this tab render EMPTY while chapters loaded and
            for any story with no chapters — QA Issue 6. The panel now always
            renders and disables only the one destination that needs a chapter. */}
        {section === 'ocr' && (
          <OCRPanel storyId={storyId} chapterId={activeChapterId} chaptersLoading={loading}
            onInjectComplete={() => reloadChapters()}
            onNotesInjectComplete={() => setNotesReload((k) => k + 1)} />
        )}
      </div>
    </div>
  )
}
