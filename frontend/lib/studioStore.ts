'use client'

// Workspace Memory — persisted studio UI state (Zustand + persist → localStorage).
// Single source of truth for: which workspace/chapter/character/analysis the author
// last used per story, and the panel/layout/sidecar state. The Story Context Engine
// reads/writes this; on return, the studio restores the author's environment.
//
// Per user (Stage 8.2): the state is stored under `narratiq_studio:<user_id>`, so
// two accounts in one browser never share a layout or each other's story memory.
// The store does not hydrate on its own (skipHydration); `bindStudioStoreToUser`
// points it at the signed-in user's key and rehydrates, and is called by the story
// layout gate on sign-in and by logout. Cross-device sync is out of scope (it would
// need a server table) — a documented Stage 8 scope decision.

import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { WorkspaceId } from './registries/workspaces'

export interface PerStoryMemory {
  lastWorkspace: WorkspaceId
  lastChapterId: string | null
  lastCharacterId: string | null
  lastAnalysis: string | null
  lastNoteId: string | null
  /** last open section per multi-section workspace (Plan, World) */
  lastSections?: Partial<Record<WorkspaceId, string>>
}

export const LEGACY_STUDIO_KEY = 'narratiq_studio'
export const studioKeyFor = (userId: string | null) => `${LEGACY_STUDIO_KEY}:${userId ?? 'anon'}`

interface LayoutState {
  railCollapsed: boolean
  binderCollapsed: boolean
  sidecarOpen: boolean
  binderSize: number      // % of the horizontal split
  sidecarSize: number
  sidecarExpanded: boolean // sidecar widened for detailed AI work (binder hidden)
  focusMode: boolean      // hides rail/binder/sidecar
  zenMode: boolean        // hides everything (paragraph focus)
  typewriter: boolean
  searchOpen: boolean     // manuscript search & replace (session-only)
}

interface StudioState extends LayoutState {
  /** storage key the store is currently bound to; null until the first bind */
  boundKey: string | null
  lastStoryId: string | null
  byStory: Record<string, PerStoryMemory>

  // memory writers
  setLastStory: (storyId: string) => void
  setWorkspace: (storyId: string, ws: WorkspaceId) => void
  setChapter: (storyId: string, chapterId: string | null) => void
  setCharacter: (storyId: string, characterId: string | null) => void
  setAnalysis: (storyId: string, analysis: string | null) => void
  setNote: (storyId: string, noteId: string | null) => void
  setSection: (storyId: string, ws: WorkspaceId, section: string) => void
  getStory: (storyId: string) => PerStoryMemory

  // layout writers
  toggleRail: () => void
  toggleBinder: () => void
  toggleSidecar: (open?: boolean) => void
  setSidecarExpanded: (on: boolean) => void
  setBinderSize: (n: number) => void
  setSidecarSize: (n: number) => void
  setFocusMode: (on: boolean) => void
  setZenMode: (on: boolean) => void
  toggleTypewriter: () => void
  setSearchOpen: (open: boolean) => void
}

const DEFAULT_PER_STORY: PerStoryMemory = {
  lastWorkspace: 'write',
  lastChapterId: null,
  lastCharacterId: null,
  lastAnalysis: null,
  lastNoteId: null,
}

/** Everything a user's layout/memory resets to (also what a new account sees). */
const DEFAULT_DATA = {
  lastStoryId: null as string | null,
  byStory: {} as Record<string, PerStoryMemory>,
  railCollapsed: false,
  binderCollapsed: false,
  sidecarOpen: false,        // AI Sidecar default CLOSED — editor breathes
  binderSize: 20,
  sidecarSize: 26,
  sidecarExpanded: false,
  focusMode: false,
  zenMode: false,
  typewriter: false,
  searchOpen: false,
}

export const useStudioStore = create<StudioState>()(
  persist(
    (set, get) => ({
      ...DEFAULT_DATA,
      boundKey: null,

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

      setSection: (storyId, ws, section) =>
        set((s) => {
          const prev = { ...DEFAULT_PER_STORY, ...s.byStory[storyId] }
          if (prev.lastSections?.[ws] === section) return s
          return { byStory: { ...s.byStory, [storyId]: { ...prev, lastSections: { ...prev.lastSections, [ws]: section } } } }
        }),

      toggleRail: () => set((s) => ({ railCollapsed: !s.railCollapsed })),
      toggleBinder: () => set((s) => ({ binderCollapsed: !s.binderCollapsed })),
      toggleSidecar: (open) => set((s) => ({ sidecarOpen: open ?? !s.sidecarOpen })),
      setSidecarExpanded: (on) => set({ sidecarExpanded: on }),
      setBinderSize: (n) => set({ binderSize: n }),
      setSidecarSize: (n) => set({ sidecarSize: n }),
      setFocusMode: (on) => set({ focusMode: on, zenMode: on ? false : get().zenMode }),
      setZenMode: (on) => set({ zenMode: on, focusMode: on ? false : get().focusMode }),
      toggleTypewriter: () => set((s) => ({ typewriter: !s.typewriter })),
      setSearchOpen: (open) => set({ searchOpen: open }),
    }),
    {
      name: studioKeyFor(null),
      skipHydration: true,
      // Hydration starts from defaults, never from the previously bound user's
      // in-memory state: a user with no saved layout gets a clean one.
      merge: (persisted, current) => ({ ...current, ...DEFAULT_DATA, ...((persisted ?? {}) as Partial<StudioState>) }),
      partialize: (s) => ({
        lastStoryId: s.lastStoryId,
        byStory: s.byStory,
        railCollapsed: s.railCollapsed,
        binderCollapsed: s.binderCollapsed,
        sidecarOpen: s.sidecarOpen,
        binderSize: s.binderSize,
        sidecarSize: s.sidecarSize,
        sidecarExpanded: s.sidecarExpanded,
        typewriter: s.typewriter,
        // focus/zen are session-only — not persisted
      }),
    },
  ),
)

/** Layout fields copied from the pre-Stage-8 global key — sizes only. The legacy
 *  per-story memory is NOT migrated: it may hold another account's story ids. */
const MIGRATED_FIELDS = ['binderSize', 'sidecarSize', 'railCollapsed'] as const

function migrateLegacyLayout(targetKey: string) {
  try {
    const raw = localStorage.getItem(LEGACY_STUDIO_KEY)
    if (raw === null) return
    if (localStorage.getItem(targetKey) === null) {
      const legacy = (JSON.parse(raw)?.state ?? {}) as Record<string, unknown>
      const state: Record<string, unknown> = {}
      for (const f of MIGRATED_FIELDS) if (legacy[f] !== undefined) state[f] = legacy[f]
      localStorage.setItem(targetKey, JSON.stringify({ state, version: 0 }))
    }
    localStorage.removeItem(LEGACY_STUDIO_KEY)
  } catch {
    try { localStorage.removeItem(LEGACY_STUDIO_KEY) } catch { /* storage unavailable */ }
  }
}

/**
 * Point the studio store at `userId`'s storage key and load that user's layout.
 * Called with the signed-in user's id before any studio UI renders, and with
 * null on logout. Always starts from defaults, so nothing from the previous
 * account survives a switch, even when the new account has no saved layout.
 */
export async function bindStudioStoreToUser(userId: string | null): Promise<void> {
  const key = studioKeyFor(userId)
  if (useStudioStore.getState().boundKey === key) return
  // No setState before the rename: persist writes on every set, and writing
  // here would overwrite the previous user's saved layout with defaults.
  if (userId && typeof window !== 'undefined') migrateLegacyLayout(key)
  useStudioStore.persist.setOptions({ name: key })
  await useStudioStore.persist.rehydrate()
  useStudioStore.setState({ boundKey: key, focusMode: false, zenMode: false, searchOpen: false })
}
