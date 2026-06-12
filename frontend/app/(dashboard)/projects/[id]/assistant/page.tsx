'use client'

// Assistant Workspace — the agentic AI home. Reuses the full VoiceAgentPanel. It
// consumes the Story Context Engine's editor bridge (selection/replace) when the
// editor is mounted; story-wide voice actions work regardless.

import dynamic from 'next/dynamic'
import { useRouter } from 'next/navigation'
import { useStoryContext } from '@/components/studio/StoryContextEngine'
import { workspacePath } from '@/lib/registries/workspaces'

const VoiceAgentPanel = dynamic(() => import('@/components/voice/VoiceAgentPanel'), { ssr: false })

export default function AssistantWorkspace() {
  const router = useRouter()
  const { storyId, activeChapter, activeChapterId, editor, setActiveChapter } = useStoryContext()

  return (
    <div className="h-full overflow-hidden bg-[#0d0f1a] max-w-2xl mx-auto border-x border-[#1f2440]">
      <VoiceAgentPanel
        storyId={storyId}
        chapterId={activeChapterId}
        chapterNumber={activeChapter?.chapter_number ?? null}
        chapterTitle={activeChapter?.title}
        getSelectedText={() => editor?.getSelectedText() || ''}
        getFullText={() => editor?.getFullText() || ''}
        insertText={(t: string) => editor?.insertText(t)}
        getSelectionRange={() => editor?.getSelectionRange() || null}
        replaceRange={(from: number, to: number, t: string) => editor?.replaceRange(from, to, t)}
        onOpenChapter={(cid: string) => { setActiveChapter(cid); router.push(workspacePath(storyId, 'write')) }}
      />
    </div>
  )
}
