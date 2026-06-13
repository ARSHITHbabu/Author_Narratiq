'use client'

// Story Context Engine — the single source of truth for everything a workspace,
// the AI Sidecar, the Command Palette, the Voice Agent, and future AI agents need.
//
//   Studio Shell → StoryContextEngine → CollaborationBoundary(future) → Workspaces
//
// Server data (story, chapters, characters) is owned by React Query (one fetch,
// shared, deduped). UI/memory state comes from the Zustand studio store. The editor
// publishes its live selection here via a ref bridge. Nothing prop-drills; everyone
// consumes useStoryContext().

import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { projectsApi, chaptersApi, charactersApi, activityApi, intakeApi } from '@/lib/api'
import { useStudioStore } from '@/lib/studioStore'
import type { Story, Chapter, Character, GenreProfile } from '@/lib/types'
import { useAuth } from '@/lib/auth'

export interface EditorBridge {
  getSelectedText: () => string
  getFullText: () => string
  insertText: (text: string) => void
  getSelectionRange: () => { from: number; to: number } | null
  replaceRange: (from: number, to: number, text: string) => void
}

export interface Selection { text: string; from: number; to: number }

export interface StoryContextValue {
  storyId: string
  // server state (React Query)
  story: Story | undefined
  chapters: Chapter[]
  characters: Character[]
  // Genre profile (from Story Intake) — makes every AI tool genre-aware.
  // null while loading or if the author never completed/skipped intake.
  genreProfile: Partial<GenreProfile> | null
  loading: boolean
  reloadChapters: () => void
  reloadCharacters: () => void
  reloadStory: () => void
  reloadGenreProfile: () => void
  // Live, optimistic word-count update for a chapter — keeps the binder sidebar
  // and the story total in sync with the editor as the user types, without
  // waiting for a save round-trip or page refresh.
  updateChapterWordCount: (chapterId: string, wordCount: number) => void

  // active selections (memory-backed)
  activeChapterId: string | null
  activeChapter: Chapter | undefined
  setActiveChapter: (id: string | null) => void
  activeCharacterId: string | null
  setActiveCharacter: (id: string | null) => void
  activeAnalysis: string | null
  setActiveAnalysis: (id: string | null) => void
  activeNoteId: string | null
  setActiveNote: (id: string | null) => void

  // editor + live selection (ref bridge — set by the Write workspace)
  registerEditor: (b: EditorBridge | null) => void
  editor: EditorBridge | null
  selection: Selection | null
  captureSelection: () => Selection | null

  // AI / voice session ids (ephemeral)
  aiSessionId: string | null
  setAiSession: (id: string | null) => void
  voiceSessionId: string | null
  setVoiceSession: (id: string | null) => void

  // collaboration-ready (stubbed single-owner today)
  members: { user_id: string; username: string; role: string }[]
  role: 'owner' | 'editor' | 'viewer'
  can: (action: string) => boolean

  // activity timeline
  logActivity: (e: { category: 'ai' | 'analysis' | 'project' | 'voice' | 'export'; type: string; title?: string; summary?: string; ref_type?: string; ref_id?: string; metadata?: Record<string, unknown> }) => void
}

const Ctx = createContext<StoryContextValue | null>(null)

export function useStoryContext(): StoryContextValue {
  const v = useContext(Ctx)
  if (!v) throw new Error('useStoryContext must be used inside <StoryContextEngine>')
  return v
}

export default function StoryContextEngine({ storyId, children }: { storyId: string; children: ReactNode }) {
  const qc = useQueryClient()
  const { user } = useAuth()
  const store = useStudioStore()
  const mem = store.getStory(storyId)

  // ── Server state (shared cache) ───────────────────────────────────────────
  const storyQ = useQuery({ queryKey: ['story', storyId], queryFn: async () => (await projectsApi.get(storyId)).data as Story })
  const chaptersQ = useQuery({ queryKey: ['chapters', storyId], queryFn: async () => (await chaptersApi.list(storyId)).data as Chapter[] })
  const charactersQ = useQuery({ queryKey: ['characters', storyId], queryFn: async () => (await charactersApi.list(storyId)).data as Character[] })

  // Genre profile — the GET endpoint returns a subset (genre, sub_genre, tone,
  // target_audience, writing_direction) or null. Normalise `target_audience` →
  // `audience` so consumers (genre-aware tool defaults) read one shape.
  const genreQ = useQuery({
    queryKey: ['genre-profile', storyId],
    queryFn: async (): Promise<Partial<GenreProfile> | null> => {
      const { data } = await intakeApi.getGenreProfile(storyId)
      if (!data) return null
      return {
        genre: data.genre ?? '',
        sub_genre: data.sub_genre ?? '',
        tone: Array.isArray(data.tone) ? data.tone : (data.tone ? [data.tone] : []),
        audience: data.target_audience ?? '',
        writing_direction: data.writing_direction ?? undefined,
      }
    },
    staleTime: 60_000,
  })

  const chapters = chaptersQ.data ?? []
  const characters = charactersQ.data ?? []

  // ── Optimistic chapter word-count sync (binder + story total) ─────────────
  const updateChapterWordCount = useCallback((chapterId: string, wordCount: number) => {
    qc.setQueryData<Chapter[]>(['chapters', storyId], (old) => {
      if (!old) return old
      let changed = false
      const next = old.map((c) => {
        if (c.chapter_id === chapterId && c.word_count !== wordCount) {
          changed = true
          return { ...c, word_count: wordCount }
        }
        return c
      })
      if (!changed) return old
      // Keep the story-level total live too (sum of chapter counts).
      qc.setQueryData<Story>(['story', storyId], (s) =>
        s ? { ...s, word_count: next.reduce((sum, c) => sum + (c.word_count || 0), 0) } : s,
      )
      return next
    })
  }, [qc, storyId])

  // ── Active selections (persisted via Workspace Memory) ────────────────────
  const activeChapterId = mem.lastChapterId && chapters.some((c) => c.chapter_id === mem.lastChapterId)
    ? mem.lastChapterId
    : (chapters[0]?.chapter_id ?? null)
  const activeChapter = chapters.find((c) => c.chapter_id === activeChapterId)

  const setActiveChapter = useCallback((id: string | null) => store.setChapter(storyId, id), [storyId, store])
  const setActiveCharacter = useCallback((id: string | null) => store.setCharacter(storyId, id), [storyId, store])
  const setActiveAnalysis = useCallback((id: string | null) => store.setAnalysis(storyId, id), [storyId, store])
  const setActiveNote = useCallback((id: string | null) => store.setNote(storyId, id), [storyId, store])

  // ── Editor bridge + live selection ────────────────────────────────────────
  const editorRef = useRef<EditorBridge | null>(null)
  const [selection, setSelection] = useState<Selection | null>(null)
  const registerEditor = useCallback((b: EditorBridge | null) => { editorRef.current = b }, [])
  const captureSelection = useCallback((): Selection | null => {
    const b = editorRef.current
    if (!b) return null
    const text = b.getSelectedText()
    const range = b.getSelectionRange()
    const sel = text && range ? { text, from: range.from, to: range.to } : null
    setSelection(sel)
    return sel
  }, [])

  // ── Ephemeral AI/voice sessions ───────────────────────────────────────────
  const [aiSessionId, setAiSession] = useState<string | null>(null)
  const [voiceSessionId, setVoiceSession] = useState<string | null>(null)

  // ── Activity timeline ─────────────────────────────────────────────────────
  const logActivity = useCallback<StoryContextValue['logActivity']>((e) => {
    activityApi.record(storyId, e).then(() => {
      qc.invalidateQueries({ queryKey: ['activity', storyId] })
    }).catch(() => { /* non-blocking */ })
  }, [storyId, qc])

  // ── Collaboration stub (single owner) ─────────────────────────────────────
  const members = useMemo(() => (user ? [{ user_id: user.user_id, username: user.username, role: 'owner' }] : []), [user])
  const can = useCallback(() => true, [])   // future: real permission gate

  const value: StoryContextValue = {
    storyId,
    story: storyQ.data,
    chapters,
    characters,
    genreProfile: genreQ.data ?? null,
    loading: storyQ.isLoading || chaptersQ.isLoading,
    reloadChapters: () => qc.invalidateQueries({ queryKey: ['chapters', storyId] }),
    reloadCharacters: () => qc.invalidateQueries({ queryKey: ['characters', storyId] }),
    reloadStory: () => qc.invalidateQueries({ queryKey: ['story', storyId] }),
    reloadGenreProfile: () => qc.invalidateQueries({ queryKey: ['genre-profile', storyId] }),
    updateChapterWordCount,
    activeChapterId, activeChapter, setActiveChapter,
    activeCharacterId: mem.lastCharacterId, setActiveCharacter,
    activeAnalysis: mem.lastAnalysis, setActiveAnalysis,
    activeNoteId: mem.lastNoteId, setActiveNote,
    registerEditor, editor: editorRef.current, selection, captureSelection,
    aiSessionId, setAiSession, voiceSessionId, setVoiceSession,
    members, role: 'owner', can,
    logActivity,
  }

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
