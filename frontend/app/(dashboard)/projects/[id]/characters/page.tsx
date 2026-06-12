'use client'

// Characters Workspace — the cast home. Reuses CharacterList (which already has
// list / profile / relationship-graph views) at full width.

import dynamic from 'next/dynamic'
import { useStoryContext } from '@/components/studio/StoryContextEngine'

const CharacterList = dynamic(() => import('@/components/characters/CharacterList'), { ssr: false })

export default function CharactersWorkspace() {
  const { storyId } = useStoryContext()
  return (
    <div className="h-full overflow-hidden bg-[#0d0f1a]">
      <CharacterList storyId={storyId} />
    </div>
  )
}
