'use client'

// Shared Story Bible status hook — single source of truth for generation state,
// used by both the Story Bible panel and the app-wide completion watcher so they
// share ONE React Query cache entry (no duplicate polling). Status comes from the
// backend (running | completed | failed), so the UI survives navigation/reloads.

import { useEffect, useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { storyBibleApi } from './api'
import type { StoryBibleOut } from './types'
import { toast } from 'sonner'

export const storyBibleKey = (storyId: string) => ['story-bible', storyId] as const

export function useStoryBible(storyId: string) {
  return useQuery({
    queryKey: storyBibleKey(storyId),
    queryFn: async (): Promise<StoryBibleOut | null> => {
      try {
        const res = await storyBibleApi.get(storyId)
        return res.data as StoryBibleOut
      } catch (e: any) {
        if (e?.response?.status === 404) return null   // never generated → idle
        throw e
      }
    },
    // Poll only while a generation is actually running.
    refetchInterval: (query) =>
      (query.state.data as StoryBibleOut | null)?.status === 'running' ? 4000 : false,
    refetchOnWindowFocus: true,
    staleTime: 0,
  })
}

// Fires a completion/failure toast on the running → completed/failed transition.
// Mounted app-wide (StudioShell) so the user is notified even after navigating
// away from the Story Bible panel.
export function StoryBibleWatcher({ storyId }: { storyId: string }) {
  const qc = useQueryClient()
  const { data } = useStoryBible(storyId)
  const prev = useRef<string | undefined>(undefined)

  useEffect(() => {
    const status = data?.status
    if (prev.current === 'running' && status === 'completed') {
      toast.success('Story Bible is ready.')
      qc.invalidateQueries({ queryKey: storyBibleKey(storyId) })
    } else if (prev.current === 'running' && status === 'failed') {
      toast.error('Story Bible generation failed. You can retry from the Story Bible panel.')
    }
    if (status !== undefined) prev.current = status
  }, [data?.status, storyId, qc])

  return null
}
