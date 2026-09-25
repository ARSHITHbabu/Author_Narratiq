// Phase 3 session store — DELIBERATELY NOT PERSISTED (spec §10.2, rule R1).
//
// Unpinned generations live only here, in memory: never localStorage, never
// the server. A refresh, logout or story switch clears them — that is the
// "only pinned versions are kept" contract the UI states to the author.
// Pins themselves are server state (react-query / pinsApi), not stored here.

import { create } from 'zustand'

export interface SessionGeneration {
  id: string
  text: string
  tool: string
  toolParams: Record<string, unknown>
  chapterId: string
  sourceText: string
  sourceFrom: number | null
  sourceTo: number | null
  createdAt: number
  basePinId?: string
  contextPinIds?: string[]
}

interface GenerationState {
  storyId: string | null
  historyMax: number
  history: Record<string, SessionGeneration[]>         // key: `${chapterId}:${tool}`
  contextPinIds: string[]                              // selected "use as context"
  avoidPinIds: string[]                                // selected "avoid ideas like"
  compare: { left: CompareSide; right: CompareSide } | null
  firstRunHintShown: boolean
  pinsVersion: number                                  // bump → Versions list refreshes
  setStory: (storyId: string) => void
  setHistoryMax: (n: number) => void
  record: (g: SessionGeneration) => void
  recentTexts: (chapterId: string, tool: string, excludeId?: string) => string[]
  toggleContextPin: (pinId: string, max: number) => boolean
  toggleAvoidPin: (pinId: string) => void
  clearSelections: () => void
  openCompare: (left: CompareSide, right: CompareSide) => void
  closeCompare: () => void
  markHintShown: () => void
  pinsChanged: () => void
}

export interface CompareSide { label: string; text: string; pinId?: string }

export const historyKey = (chapterId: string, tool: string) => `${chapterId}:${tool}`

export const useGenerationStore = create<GenerationState>((set, get) => ({
  storyId: null,
  historyMax: 10,
  history: {},
  contextPinIds: [],
  avoidPinIds: [],
  compare: null,
  firstRunHintShown: false,
  pinsVersion: 0,
  setStory: (storyId) => {
    if (get().storyId === storyId) return
    // A different story is a different working session: drop everything unpinned.
    set({ storyId, history: {}, contextPinIds: [], avoidPinIds: [], compare: null })
  },
  setHistoryMax: (n) => set({ historyMax: Math.max(1, n) }),
  record: (g) => set((s) => {
    const key = historyKey(g.chapterId, g.tool)
    const list = [...(s.history[key] ?? []), g].slice(-s.historyMax)
    return { history: { ...s.history, [key]: list } }
  }),
  recentTexts: (chapterId, tool, excludeId) =>
    (get().history[historyKey(chapterId, tool)] ?? []).filter((g) => g.id !== excludeId).map((g) => g.text),
  toggleContextPin: (pinId, max) => {
    const cur = get().contextPinIds
    if (cur.includes(pinId)) { set({ contextPinIds: cur.filter((p) => p !== pinId) }); return true }
    if (cur.length >= max) return false
    set({ contextPinIds: [...cur, pinId] })
    return true
  },
  toggleAvoidPin: (pinId) => set((s) => ({
    avoidPinIds: s.avoidPinIds.includes(pinId) ? s.avoidPinIds.filter((p) => p !== pinId) : [...s.avoidPinIds, pinId].slice(-8),
  })),
  clearSelections: () => set({ contextPinIds: [], avoidPinIds: [] }),
  openCompare: (left, right) => set({ compare: { left, right } }),
  closeCompare: () => set({ compare: null }),
  markHintShown: () => set({ firstRunHintShown: true }),
  pinsChanged: () => set((s) => ({ pinsVersion: s.pinsVersion + 1 })),
}))
