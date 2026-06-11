'use client'

import { useEffect, useState, useRef, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import dynamic from 'next/dynamic'
import {
  Feather, ArrowLeft, BarChart3, Download, Brain, Camera,
  Wand2, Lightbulb, Loader2, Sparkles, Search, Users, StickyNote, AlertTriangle,
  BookOpen, Target, Mic,
} from 'lucide-react'
import { chaptersApi, projectsApi, exportApi, aiApi } from '@/lib/api'
import { Story, Chapter, AISuggestion } from '@/lib/types'
import ChapterSidebar from '@/components/editor/ChapterSidebar'
import StoryEditor from '@/components/editor/StoryEditor'
import { EditorSearchFunctions } from '@/components/editor/StoryEditor'
import { toast } from 'sonner'

// ── Lazy panel imports ────────────────────────────────────────────────────────
// All right-panel components are loaded only when the author first opens that
// tab. This keeps the initial JS payload to the editor + sidebar only (~70 kB
// page-specific vs 143 kB with static imports). Each panel becomes its own
// chunk and is cached after first load. ssr:false is correct — all panels are
// client-only and use browser APIs (localStorage, DOM).

function PanelSkeleton() {
  return (
    <div className="flex flex-col gap-3 p-4 h-full">
      <div className="h-3 bg-[#1f2440] rounded animate-pulse w-1/2" />
      <div className="h-3 bg-[#1f2440] rounded animate-pulse w-3/4" />
      <div className="h-3 bg-[#1f2440] rounded animate-pulse w-2/3" />
      <div className="h-20 bg-[#1a1e36] rounded-xl animate-pulse mt-2" />
      <div className="h-20 bg-[#1a1e36] rounded-xl animate-pulse" />
    </div>
  )
}

const AIToolsSidebar = dynamic(
  () => import('@/components/ai-tools/AIToolsSidebar'),
  { ssr: false, loading: () => <PanelSkeleton /> },
)
const PlotAssistantPanel = dynamic(
  () => import('@/components/plot-assistant/PlotAssistantPanel'),
  { ssr: false, loading: () => <PanelSkeleton /> },
)
const OCRPanel = dynamic(
  () => import('@/components/ocr/OCRPanel'),
  { ssr: false, loading: () => <PanelSkeleton /> },
)
const NotesPanel = dynamic(
  () => import('@/components/notes/NotesPanel'),
  { ssr: false, loading: () => <PanelSkeleton /> },
)
const CharacterList = dynamic(
  () => import('@/components/characters/CharacterList'),
  { ssr: false, loading: () => <PanelSkeleton /> },
)
const AuditPanel = dynamic(
  () => import('@/components/plot-holes/AuditPanel'),
  { ssr: false, loading: () => <PanelSkeleton /> },
)
const StoryBiblePanel = dynamic(
  () => import('@/components/story-bible/StoryBiblePanel'),
  { ssr: false, loading: () => <PanelSkeleton /> },
)
const PacingGoalPanel = dynamic(
  () => import('@/components/pacing/PacingGoalPanel'),
  { ssr: false, loading: () => <PanelSkeleton /> },
)
const AudioPanel = dynamic(
  () => import('@/components/audio/AudioPanel'),
  { ssr: false, loading: () => <PanelSkeleton /> },
)
const SearchPanel = dynamic(
  () => import('@/components/search/SearchPanel'),
  { ssr: false },
)

type RightPanel = 'ai' | 'plot' | 'ocr' | 'notes' | 'suggestions' | 'characters' | 'audit' | 'bible' | 'pacing' | 'audio'

export default function EditorPage({ params }: { params: { id: string } }) {
  const { id: storyId } = params
  const router = useRouter()

  const [story, setStory] = useState<Story | null>(null)
  const [chapters, setChapters] = useState<Chapter[]>([])
  const [activeChapter, setActiveChapter] = useState<Chapter | null>(null)
  const [loading, setLoading] = useState(true)
  const [wordCount, setWordCount] = useState(0)

  // Stable ref so handleWordCountChange never closes over a stale activeChapter
  const activeChapterIdRef = useRef<string | null>(null)
  const [rightPanel, setRightPanel] = useState<RightPanel>('ai')
  const [suggestions, setSuggestions] = useState<AISuggestion[]>([])
  const [loadingSuggestions, setLoadingSuggestions] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [leftCollapsed, setLeftCollapsed] = useState(false)
  const [rightCollapsed, setRightCollapsed] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [editorReloadKey, setEditorReloadKey] = useState(0)
  const [notesReloadKey, setNotesReloadKey] = useState(0)

  // We use a ref to hold editor methods from StoryEditor
  const editorMethodsRef = useRef<{
    getSelectedText: () => string
    getFullText: () => string
    insertText: (text: string) => void
  } | null>(null)

  // Search: ref to editor search functions + pending cross-chapter navigation
  const editorSearchRef = useRef<EditorSearchFunctions | null>(null)
  const pendingSearchRef = useRef<{
    query: string
    caseSensitive: boolean
    wholeWord: boolean
    targetIndex: number
  } | null>(null)
  // Tracks the live search state from SearchPanel so we can re-apply
  // highlights whenever the user switches chapters manually
  const activeSearchRef = useRef<{
    query: string
    caseSensitive: boolean
    wholeWord: boolean
  } | null>(null)

  // Keep ref in sync so handleWordCountChange can read the latest chapter id
  // without being recreated on every chapter switch (which would cause TipTap
  // to re-capture the callback on every render unnecessarily).
  useEffect(() => {
    activeChapterIdRef.current = activeChapter?.chapter_id ?? null
  }, [activeChapter])

  useEffect(() => {
    loadProject()
  }, [storyId])

  // Ctrl+F / Cmd+F keyboard shortcut
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
        e.preventDefault()
        setSearchOpen(true)
      }
      if (e.key === 'Escape' && searchOpen) {
        setSearchOpen(false)
        editorSearchRef.current?.clearSearch()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [searchOpen])

  // Called when user clicks a search result (possibly in a different chapter)
  const handleJumpToMatch = useCallback(
    (chapterId: string, localIndex: number, query: string, caseSensitive: boolean, wholeWord: boolean) => {
      pendingSearchRef.current = { query, caseSensitive, wholeWord, targetIndex: localIndex }
      if (activeChapter?.chapter_id === chapterId) {
        editorSearchRef.current?.applySearch(query, caseSensitive, wholeWord, localIndex)
        pendingSearchRef.current = null
      } else {
        const target = chapters.find(c => c.chapter_id === chapterId)
        if (target) setActiveChapter(target)
      }
    },
    [activeChapter, chapters],
  )

  // Called after chapter content is loaded in the editor.
  // Uses refs only → stable callback, always reads latest values.
  const handleContentLoaded = useCallback(() => {
    if (!editorSearchRef.current) return

    if (pendingSearchRef.current) {
      // User clicked a search result that jumped to a different chapter
      const { query, caseSensitive, wholeWord, targetIndex } = pendingSearchRef.current
      editorSearchRef.current.applySearch(query, caseSensitive, wholeWord, targetIndex)
      pendingSearchRef.current = null
    } else if (activeSearchRef.current?.query.trim()) {
      // Search panel is open with an active query — re-apply to the new chapter
      // so the author sees which matches exist here (all inactive/yellow; no scroll)
      const { query, caseSensitive, wholeWord } = activeSearchRef.current
      editorSearchRef.current.applySearch(query, caseSensitive, wholeWord, -1)
    }
  }, [])

  // Updates the status-bar word count AND the sidebar's ch.word_count for the
  // active chapter so both reflect the live editor count without a page refresh.
  // Uses a ref for the active chapter id so this callback stays stable across
  // chapter switches — TipTap picks up the latest version each render.
  const handleWordCountChange = useCallback((count: number) => {
    setWordCount(count)
    const chId = activeChapterIdRef.current
    if (chId) {
      setChapters(prev =>
        prev.map(ch => ch.chapter_id === chId ? { ...ch, word_count: count } : ch)
      )
    }
  }, [])

  const loadProject = async () => {
    try {
      const [storyRes, chapRes] = await Promise.all([
        projectsApi.get(storyId),
        chaptersApi.list(storyId),
      ])
      setStory(storyRes.data)
      const chs: Chapter[] = chapRes.data
      setChapters(chs)
      if (chs.length > 0) setActiveChapter(chs[0])
    } catch {
      toast.error('Failed to load project')
      router.replace('/dashboard')
    } finally {
      setLoading(false)
    }
  }

  const exportManuscript = async (format: 'docx' | 'pdf') => {
    setExporting(true)
    try {
      const res = await exportApi.export(storyId, format)
      const url = window.URL.createObjectURL(new Blob([res.data]))
      const a = document.createElement('a')
      a.href = url
      a.download = `${story?.title || 'manuscript'}.${format}`
      a.click()
      window.URL.revokeObjectURL(url)
      toast.success(`Exported as ${format.toUpperCase()}`)
    } catch {
      toast.error('Export failed')
    } finally {
      setExporting(false)
    }
  }

  const loadSuggestions = async () => {
    if (!activeChapter) return
    setLoadingSuggestions(true)
    setSuggestions([])
    try {
      const text = editorMethodsRef.current?.getFullText() || ''
      if (!text.trim()) return toast.error('Write some text first to get suggestions')
      const res = await aiApi.suggestions(storyId, activeChapter.chapter_id, text)
      setSuggestions(res.data.suggestions)
      setRightPanel('suggestions')
    } catch {
      toast.error('Failed to load suggestions')
    } finally {
      setLoadingSuggestions(false)
    }
  }

  // Expose editor methods to parent
  const setEditorMethods = useCallback((methods: {
    getSelectedText: () => string
    getFullText: () => string
    insertText: (text: string) => void
  }) => {
    editorMethodsRef.current = methods
  }, [])

  if (loading) {
    return (
      <div className="h-screen bg-[#0d0f1a] flex items-center justify-center">
        <div className="flex items-center gap-3 text-[#5c6391]">
          <Loader2 className="w-5 h-5 animate-spin" />
          <span>Loading manuscript...</span>
        </div>
      </div>
    )
  }

  if (!story || !activeChapter) return null

  return (
    <div className="h-screen bg-[#0d0f1a] flex flex-col overflow-hidden">
      {/* Top Bar */}
      <div className="flex items-center justify-between px-4 h-12 border-b border-[#1f2440] flex-shrink-0">
        <div className="flex items-center gap-3">
          <Link href="/dashboard" className="text-[#5c6391] hover:text-amber-400 transition-colors">
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <div className="w-px h-4 bg-[#2e3454]" />
          <Feather className="w-4 h-4 text-amber-500 flex-shrink-0" />
          <span className="text-sm font-medium text-[#e8eaf6] truncate max-w-[200px]">{story.title}</span>
        </div>

        <div className="flex items-center gap-2">
          {/* Search */}
          <button
            onClick={() => setSearchOpen(v => !v)}
            title="Search manuscript (Ctrl+F)"
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition-all border ${
              searchOpen
                ? 'text-amber-400 bg-amber-500/10 border-amber-500/20'
                : 'text-[#9da3c8] hover:text-amber-400 hover:bg-[#1f2440] border-transparent hover:border-[#2e3454]'
            }`}
          >
            <Search className="w-3.5 h-3.5" />
            Search
          </button>

          {/* Suggestions */}
          <button
            onClick={loadSuggestions}
            disabled={loadingSuggestions}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-[#9da3c8] hover:text-amber-400 hover:bg-[#1f2440] transition-all border border-transparent hover:border-[#2e3454]"
          >
            {loadingSuggestions ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Lightbulb className="w-3.5 h-3.5" />}
            AI Suggestions
          </button>

          <Link
            href={`/projects/${storyId}/analytics`}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-[#9da3c8] hover:text-amber-400 hover:bg-[#1f2440] transition-all border border-transparent hover:border-[#2e3454]"
          >
            <BarChart3 className="w-3.5 h-3.5" />
            Analytics
          </Link>

          {/* Export */}
          <div className="relative group">
            <button
              disabled={exporting}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-[#9da3c8] hover:text-amber-400 hover:bg-[#1f2440] transition-all border border-transparent hover:border-[#2e3454]"
            >
              {exporting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
              Export
            </button>
            <div className="absolute right-0 top-8 bg-[#1a1e36] border border-[#2e3454] rounded-lg py-1 w-32 z-20 hidden group-hover:block shadow-xl">
              <button onClick={() => exportManuscript('docx')} className="w-full text-left px-3 py-2 text-xs text-[#9da3c8] hover:bg-[#252a45] hover:text-[#e8eaf6]">
                Export DOCX
              </button>
              <button onClick={() => exportManuscript('pdf')} className="w-full text-left px-3 py-2 text-xs text-[#9da3c8] hover:bg-[#252a45] hover:text-[#e8eaf6]">
                Export PDF
              </button>
            </div>
          </div>

          <Link
            href={`/projects/${storyId}/intake`}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs bg-amber-500/10 text-amber-400 border border-amber-500/20 hover:bg-amber-500/20 transition-all"
          >
            <Sparkles className="w-3.5 h-3.5" />
            Genre Profile
          </Link>
        </div>
      </div>

      {/* Main 3-column layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: Chapter Sidebar */}
        <div className={`${leftCollapsed ? 'w-0' : 'w-56'} flex-shrink-0 border-r border-[#1f2440] bg-[#0f1220] overflow-hidden transition-all duration-200`}>
          {!leftCollapsed && (
            <ChapterSidebar
              storyId={storyId}
              chapters={chapters}
              activeChapterId={activeChapter?.chapter_id || null}
              onSelect={setActiveChapter}
              onChaptersChange={setChapters}
            />
          )}
        </div>

        {/* Toggle left sidebar */}
        <button
          onClick={() => setLeftCollapsed(!leftCollapsed)}
          className="w-3 flex-shrink-0 border-r border-[#1f2440] bg-[#0f1220] hover:bg-[#1f2440] transition-colors flex items-center justify-center text-[#3d4466] hover:text-amber-500"
          title={leftCollapsed ? 'Show chapters' : 'Hide chapters'}
        >
          <div className="text-xs">{leftCollapsed ? '›' : '‹'}</div>
        </button>

        {/* Center: Editor */}
        <div className="flex-1 min-w-0 flex flex-col bg-[#0d0f1a] overflow-hidden">
          <EditorWithMethods
            storyId={storyId}
            chapter={activeChapter}
            onWordCountChange={handleWordCountChange}
            onMethodsReady={setEditorMethods}
            onSearchReady={(fns) => { editorSearchRef.current = fns }}
            onContentLoaded={handleContentLoaded}
            reloadTrigger={editorReloadKey}
          />
        </div>

        {/* Toggle right sidebar */}
        <button
          onClick={() => setRightCollapsed(!rightCollapsed)}
          className="w-3 flex-shrink-0 border-l border-[#1f2440] bg-[#0f1220] hover:bg-[#1f2440] transition-colors flex items-center justify-center text-[#3d4466] hover:text-amber-500"
          title={rightCollapsed ? 'Show AI tools' : 'Hide AI tools'}
        >
          <div className="text-xs">{rightCollapsed ? '‹' : '›'}</div>
        </button>

        {/* Right: AI Tools */}
        <div className={`${rightCollapsed ? 'w-0' : 'w-72'} flex-shrink-0 border-l border-[#1f2440] bg-[#0f1220] overflow-hidden transition-all duration-200 flex flex-col`}>
          {!rightCollapsed && (
            <>
              {/* Right panel tabs */}
              <div className="flex flex-wrap border-b border-[#1f2440] flex-shrink-0">
                {[
                  { id: 'ai'          as RightPanel, icon: Wand2,        label: 'AI'     },
                  { id: 'plot'        as RightPanel, icon: Brain,        label: 'Plot'   },
                  { id: 'ocr'         as RightPanel, icon: Camera,       label: 'OCR'    },
                  { id: 'notes'       as RightPanel, icon: StickyNote,   label: 'Notes'  },
                  { id: 'suggestions' as RightPanel, icon: Lightbulb,    label: 'Tips'   },
                  { id: 'characters'  as RightPanel, icon: Users,        label: 'Cast'   },
                  { id: 'audit'       as RightPanel, icon: AlertTriangle,label: 'Audit'  },
                  { id: 'bible'       as RightPanel, icon: BookOpen,     label: 'Bible'  },
                  { id: 'pacing'      as RightPanel, icon: Target,       label: 'Pacing' },
                  { id: 'audio'       as RightPanel, icon: Mic,          label: 'Audio'  },
                ].map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setRightPanel(tab.id)}
                    className={`flex-1 py-2 text-[10px] flex flex-col items-center gap-0.5 min-w-[30px] transition-colors ${
                      rightPanel === tab.id
                        ? 'border-b-2 border-amber-500 text-amber-400'
                        : 'text-[#5c6391] hover:text-[#9da3c8]'
                    }`}
                  >
                    <tab.icon className="w-3 h-3" />
                    {tab.label}
                  </button>
                ))}
              </div>

              <div className="flex-1 overflow-hidden">
                {rightPanel === 'ai' && (
                  <AIToolsSidebar
                    storyId={storyId}
                    chapterId={activeChapter.chapter_id}
                    getSelectedText={() => editorMethodsRef.current?.getSelectedText() || ''}
                    getFullText={() => editorMethodsRef.current?.getFullText() || ''}
                    insertText={(text) => editorMethodsRef.current?.insertText(text)}
                  />
                )}
                {rightPanel === 'plot' && (
                  <PlotAssistantPanel
                    storyId={storyId}
                    getEditorText={() => editorMethodsRef.current?.getFullText() || ''}
                    chapterNumber={activeChapter.chapter_number}
                  />
                )}
                {rightPanel === 'ocr' && (
                  <OCRPanel
                    storyId={storyId}
                    chapterId={activeChapter.chapter_id}
                    onInjectComplete={() => setEditorReloadKey(k => k + 1)}
                    onNotesInjectComplete={() => setNotesReloadKey(k => k + 1)}
                  />
                )}
                {rightPanel === 'notes' && (
                  <NotesPanel storyId={storyId} reloadKey={notesReloadKey} />
                )}
                {rightPanel === 'suggestions' && (
                  <SuggestionsPanel suggestions={suggestions} loading={loadingSuggestions} />
                )}
                {rightPanel === 'characters' && (
                  <CharacterList storyId={storyId} />
                )}
                {rightPanel === 'audit' && (
                  <AuditPanel storyId={storyId} />
                )}
                {rightPanel === 'bible' && (
                  <StoryBiblePanel storyId={storyId} />
                )}
                {rightPanel === 'pacing' && (
                  <PacingGoalPanel storyId={storyId} />
                )}
                {rightPanel === 'audio' && (
                  <AudioPanel storyId={storyId} />
                )}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Floating Search Panel — loaded lazily (only when user opens search) */}
      {searchOpen && (
        <SearchPanel
          storyId={storyId}
          activeChapterId={activeChapter.chapter_id}
          onClose={() => {
            setSearchOpen(false)
            editorSearchRef.current?.clearSearch()
            activeSearchRef.current = null
          }}
          onJumpToMatch={handleJumpToMatch}
          onReplaceComplete={(affectedIds) => {
            if (affectedIds.includes(activeChapter.chapter_id)) {
              setEditorReloadKey(k => k + 1)
            }
          }}
          onSearchStateChange={(state) => { activeSearchRef.current = state }}
        />
      )}

      {/* Status bar */}
      <div className="flex items-center gap-4 px-4 h-8 border-t border-[#1f2440] text-xs text-[#5c6391] flex-shrink-0 bg-[#0f1220]">
        <span>Chapter {activeChapter.chapter_number}: <span className="text-[#9da3c8]">{activeChapter.title}</span></span>
        <div className="w-px h-3 bg-[#2e3454]" />
        <span>Words: <span className="text-[#9da3c8]">{wordCount.toLocaleString()}</span></span>
        <div className="w-px h-3 bg-[#2e3454]" />
        <span>Story total: <span className="text-[#9da3c8]">{(story.word_count || 0).toLocaleString()}</span></span>
        <div className="flex-1" />
        <span className="text-amber-500/60">NarratIQ AI v3.0</span>
      </div>
    </div>
  )
}

function EditorWithMethods({
  storyId,
  chapter,
  onWordCountChange,
  onMethodsReady,
  onSearchReady,
  onContentLoaded,
  reloadTrigger,
}: {
  storyId: string
  chapter: Chapter
  onWordCountChange: (n: number) => void
  onMethodsReady: (m: {
    getSelectedText: () => string
    getFullText: () => string
    insertText: (text: string) => void
  }) => void
  onSearchReady?: (fns: EditorSearchFunctions) => void
  onContentLoaded?: () => void
  reloadTrigger?: number
}) {
  const editorRef = useRef<any>(null)

  useEffect(() => {
    onMethodsReady({
      getSelectedText: () => {
        const ed = editorRef.current
        if (!ed) return ''
        const { from, to } = ed.state.selection
        if (from === to) return ''
        return ed.state.doc.textBetween(from, to, ' ')
      },
      getFullText: () => {
        const ed = editorRef.current
        if (!ed) return ''
        return ed.getText()
      },
      insertText: (text: string) => {
        const ed = editorRef.current
        if (!ed) return
        ed.chain().focus().insertContent(text).run()
      },
    })
  }, [onMethodsReady])

  return (
    <StoryEditor
      storyId={storyId}
      chapter={chapter}
      onWordCountChange={onWordCountChange}
      onContentLoaded={onContentLoaded}
      reloadTrigger={reloadTrigger}
      onEditorReady={(ed, searchFns) => {
        editorRef.current = ed
        onSearchReady?.(searchFns)
      }}
    />
  )
}

function SuggestionsPanel({ suggestions, loading }: { suggestions: AISuggestion[]; loading: boolean }) {
  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="w-5 h-5 animate-spin text-amber-500" />
      </div>
    )
  }

  if (suggestions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 p-6 text-center">
        <Lightbulb className="w-10 h-10 text-[#2e3454]" />
        <p className="text-sm text-[#5c6391]">Click "AI Suggestions" in the toolbar to get craft feedback on your current chapter</p>
      </div>
    )
  }

  return (
    <div className="p-4 flex flex-col gap-3 overflow-y-auto h-full">
      <div className="text-xs font-medium text-amber-400 mb-1">{suggestions.length} Writing Suggestions</div>
      {suggestions.map((s) => (
        <div key={s.id} className="bg-[#0d0f1a] border border-[#1f2440] rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs font-medium text-amber-400">{s.category}</span>
          </div>
          <p className="text-sm text-[#e8eaf6] leading-relaxed mb-2">{s.text}</p>
          <p className="text-xs text-[#5c6391] italic">{s.reason}</p>
        </div>
      ))}
    </div>
  )
}
