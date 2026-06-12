'use client'

// Workspace Memory — persisted studio UI state (Zustand + persist → localStorage).
// Single source of truth for: which workspace/chapter/character/analysis the author
// last used per story, and the panel/layout/sidecar state. The Story Context Engine
// reads/writes this; on return, the studio restores the author's environment.

import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { WorkspaceId } from './registries/workspaces'

export interface PerStoryMemory {
  lastWorkspace: WorkspaceId
  lastChapterId: string | null
  lastCharacterId: string | null
  lastAnalysis: string | null
  lastNoteId: string | null
}

interface LayoutState {
  railCollapsed: boolean
  binderCollapsed: boolean
  sidecarOpen: boolean
  binderSize: number      // % of the horizontal split
  sidecarSize: number
  focusMode: boolean      // hides rail/binder/sidecar
  zenMode: boolean        // hides everything (paragraph focus)
  typewriter: boolean
}

interface StudioState extends LayoutState {
  lastStoryId: string | null
  byStory: Record<string, PerStoryMemory>

  // memory writers
  setLastStory: (storyId: string) => void
  setWorkspace: (storyId: string, ws: WorkspaceId) => void
  setChapter: (storyId: string, chapterId: string | null) => void
  setCharacter: (storyId: string, characterId: string | null) => void
  setAnalysis: (storyId: string, analysis: string | null) => void
  setNote: (storyId: string, noteId: string | null) => void
  getStory: (storyId: string) => PerStoryMemory

  // layout writers
  toggleRail: () => void
  toggleBinder: () => void
  toggleSidecar: (open?: boolean) => void
  setBinderSize: (n: number) => void
  setSidecarSize: (n: number) => void
  setFocusMode: (on: boolean) => void
  setZenMode: (on: boolean) => void
  toggleTypewriter: () => void
}

const DEFAULT_PER_STORY: PerStoryMemory = {
  lastWorkspace: 'write',
  lastChapterId: null,
  lastCharacterId: null,
  lastAnalysis: null,
  lastNoteId: null,
}

export const useStudioStore = create<StudioState>()(
  persist(
    (set, get) => ({
      lastStoryId: null,
      byStory: {},

      railCollapsed: false,
      binderCollapsed: false,
      sidecarOpen: false,        // AI Sidecar default CLOSED — editor breathes
      binderSize: 20,
      sidecarSize: 26,
      focusMode: false,
      zenMode: false,
      typewriter: false,

      getStory: (storyId) => get().byStory[storyId] ?? DEFAULT_PER_STORY,

      setLastStory: (storyId) => set({ lastStoryId: storyId }),

      setWorkspace: (storyId, ws) =>
        set((s) => ({
          lastStoryId: storyId,
          byStory: { ...s.byStory, [storyId]: { ...DEFAULT_PER_STORY, ...s.byStory[storyId], lastWorkspace: ws } },
        })),
      setChapter: (storyId, chapterId) =>
        set((s) => ({ byStory: { ...s.byStory, [storyId]: { ...DEFAULT_PER_STORY, ...s.byStory[storyId], lastChapterId: chapterId } } })),
      setCharacter: (storyId, characterId) =>
        set((s) => ({ byStory: { ...s.byStory, [storyId]: { ...DEFAULT_PER_STORY, ...s.byStory[storyId], lastCharacterId: characterId } } })),
      setAnalysis: (storyId, analysis) =>
        set((s) => ({ byStory: { ...s.byStory, [storyId]: { ...DEFAULT_PER_STORY, ...s.byStory[storyId], lastAnalysis: analysis } } })),
      setNote: (storyId, noteId) =>
        set((s) => ({ byStory: { ...s.byStory, [storyId]: { ...DEFAULT_PER_STORY, ...s.byStory[storyId], lastNoteId: noteId } } })),

      toggleRail: () => set((s) => ({ railCollapsed: !s.railCollapsed })),
      toggleBinder: () => set((s) => ({ binderCollapsed: !s.binderCollapsed })),
      toggleSidecar: (open) => set((s) => ({ sidecarOpen: open ?? !s.sidecarOpen })),
      setBinderSize: (n) => set({ binderSize: n }),
      setSidecarSize: (n) => set({ sidecarSize: n }),
      setFocusMode: (on) => set({ focusMode: on, zenMode: on ? false : get().zenMode }),
      setZenMode: (on) => set({ zenMode: on, focusMode: on ? false : get().focusMode }),
      toggleTypewriter: () => set((s) => ({ typewriter: !s.typewriter })),
    }),
    {
      name: 'narratiq_studio',
      partialize: (s) => ({
        lastStoryId: s.lastStoryId,
        byStory: s.byStory,
        railCollapsed: s.railCollapsed,
        binderCollapsed: s.binderCollapsed,
        sidecarOpen: s.sidecarOpen,
        binderSize: s.binderSize,
        sidecarSize: s.sidecarSize,
        typewriter: s.typewriter,
        // focus/zen are session-only — not persisted
      }),
    },
  ),
)
