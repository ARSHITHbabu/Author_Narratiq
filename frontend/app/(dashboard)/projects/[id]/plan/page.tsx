'use client'

// Plan Workspace — structuring & ideation. Reuses Plot Assistant, Pacing, Narrative
// Threads, and Notes as sections of one workspace (secondary nav within the canvas).

import dynamic from 'next/dynamic'
import { useState } from 'react'
import { MessageSquare, Target, Activity, StickyNote } from 'lucide-react'
import { useStoryContext } from '@/components/studio/StoryContextEngine'

const PlotAssistantPanel = dynamic(() => import('@/components/plot-assistant/PlotAssistantPanel'), { ssr: false })
const PacingGoalPanel = dynamic(() => import('@/components/pacing/PacingGoalPanel'), { ssr: false })
const NarrativeThreadsPanel = dynamic(() => import('@/components/analysis/NarrativeThreadsPanel'), { ssr: false })
const NotesPanel = dynamic(() => import('@/components/notes/NotesPanel'), { ssr: false })

const SECTIONS = [
  { id: 'plot', label: 'Plot Assistant', icon: MessageSquare },
  { id: 'pacing', label: 'Pacing', icon: Target },
  { id: 'threads', label: 'Threads', icon: Activity },
  { id: 'notes', label: 'Notes', icon: StickyNote },
] as const

export default function PlanWorkspace() {
  const { storyId, activeChapter, editor } = useStoryContext()
  const [section, setSection] = useState<typeof SECTIONS[number]['id']>('plot')

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
        {section === 'plot' && (
          <PlotAssistantPanel storyId={storyId} getEditorText={() => editor?.getFullText() || ''} chapterNumber={activeChapter?.chapter_number} />
        )}
        {section === 'pacing' && <PacingGoalPanel storyId={storyId} />}
        {section === 'threads' && <NarrativeThreadsPanel storyId={storyId} />}
        {section === 'notes' && <NotesPanel storyId={storyId} />}
      </div>
    </div>
  )
}
