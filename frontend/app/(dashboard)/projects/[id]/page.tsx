'use client'

// Story entry point — restores the author's last workspace (Workspace Memory) and
// redirects there. Defaults to Write for a fresh story. Replaces the old monolithic
// 3-column editor page, whose editor now lives in the Write workspace.

import { useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useStudioStore } from '@/lib/studioStore'
import { workspacePath } from '@/lib/registries/workspaces'

export default function StoryIndex() {
  // Next.js 15 (Stage 12 A5): route params come from useParams(); the page prop
  // is a Promise in Next 15, and a client component cannot await it.
  const params = useParams<{ id: string }>()
  const router = useRouter()
  useEffect(() => {
    const last = useStudioStore.getState().getStory(params.id).lastWorkspace || 'write'
    router.replace(workspacePath(params.id, last))
  }, [params.id, router])

  return (
    <div className="h-full flex items-center justify-center text-[#8e94bd] text-sm">
      Opening studio…
    </div>
  )
}
