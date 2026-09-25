'use client'

// World Workspace — reference & worldbuilding: Story Bible, Notes (with Note Cards
// and the Idea Shelf tab, decision D10) and OCR (handwritten worldbuilding intake).
// This is the ONE home of Notes and the Idea Shelf (Stage 8.8, Phase 2 Issue 10).

import dynamic from 'next/dynamic'
import { useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { BookOpen, StickyNote, Camera } from 'lucide-react'
import { useStoryContext } from '@/components/studio/StoryContextEngine'
import { SectionTabs, SectionPanel, useWorkspaceSection } from '@/components/studio/SectionTabs'

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
  const [section, setSection] = useWorkspaceSection(storyId, 'world', SECTIONS)
  const [notesReload, setNotesReload] = useState(0)
  // ?tab=ideas opens Notes straight on the Idea Shelf (Command Palette deep link).
  const notesTab = useSearchParams().get('tab')

  return (
    <div className="h-full flex flex-col bg-[#0d0f1a]">
      <SectionTabs label="World sections" sections={SECTIONS} current={section} onSelect={setSection} />
      <SectionPanel id={section}>
        {section === 'bible' && <StoryBiblePanel storyId={storyId} />}
        {section === 'notes' && (
          <NotesPanel storyId={storyId} reloadKey={notesReload}
            initialTab={notesTab === 'ideas' || notesTab === 'cards' ? notesTab : undefined} />
        )}
        {/* Scanning does not depend on a chapter. Gating the whole panel on
            `activeChapterId` made this tab render EMPTY while chapters loaded and
            for any story with no chapters — QA Issue 6. The panel now always
            renders and disables only the one destination that needs a chapter. */}
        {section === 'ocr' && (
          <OCRPanel storyId={storyId} chapterId={activeChapterId} chaptersLoading={loading}
            onInjectComplete={() => reloadChapters()}
            onNotesInjectComplete={() => setNotesReload((k) => k + 1)} />
        )}
      </SectionPanel>
    </div>
  )
}
