'use client'

// Plan Workspace — structuring & ideation: Plot Assistant and Pacing.
// Notes / Idea Shelf live in World and Narrative Threads in Analyze (Stage 8.8 —
// one home per tool, Phase 2 Issue 10); a plain link points authors there.

import dynamic from 'next/dynamic'
import Link from 'next/link'
import { MessageSquare, Target } from 'lucide-react'
import { useStoryContext } from '@/components/studio/StoryContextEngine'
import { SectionTabs, SectionPanel, useWorkspaceSection } from '@/components/studio/SectionTabs'
import { workspacePathWith } from '@/lib/registries/workspaces'

const PlotAssistantPanel = dynamic(() => import('@/components/plot-assistant/PlotAssistantPanel'), { ssr: false })
const PacingGoalPanel = dynamic(() => import('@/components/pacing/PacingGoalPanel'), { ssr: false })

const SECTIONS = [
  { id: 'plot', label: 'Plot Assistant', icon: MessageSquare },
  { id: 'pacing', label: 'Pacing', icon: Target },
] as const

export default function PlanWorkspace() {
  const { storyId, activeChapter, editor } = useStoryContext()
  const [section, setSection] = useWorkspaceSection(storyId, 'plan', SECTIONS)

  return (
    <div className="h-full flex flex-col bg-[#0d0f1a]">
      <SectionTabs label="Plan sections" sections={SECTIONS} current={section} onSelect={setSection}
        trailing={
          <Link href={workspacePathWith(storyId, 'world', { section: 'notes' })}
            className="text-[11px] text-[#aeb3d6] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/70 rounded px-1">
            Notes and ideas live in World →
          </Link>
        } />
      <SectionPanel id={section}>
        {section === 'plot' && (
          <PlotAssistantPanel storyId={storyId} getEditorText={() => editor?.getFullText() || ''} chapterNumber={activeChapter?.chapter_number} />
        )}
        {section === 'pacing' && <PacingGoalPanel storyId={storyId} />}
      </SectionPanel>
    </div>
  )
}
