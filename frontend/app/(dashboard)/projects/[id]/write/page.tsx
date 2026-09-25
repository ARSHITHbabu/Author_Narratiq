'use client'

// Write Workspace — the primary, editor-first experience. Binder (left, resizable/
// collapsible) · Editor (center) · AI Sidecar (right, resizable, default closed).
// Focus / Zen / Fullscreen / Typewriter modes. Selection toolbar for AI on the exact
// selection. Reuses ChapterSidebar + StoryEditor + AIToolsSidebar; the editor bridge
// is published into the Story Context Engine (single source of truth).

import { useCallback, useEffect, useRef, useState } from 'react'
import { Panel, PanelGroup, PanelResizeHandle, type ImperativePanelHandle } from 'react-resizable-panels'
import { PenLine, Sparkles, Focus, Maximize2, AlignVerticalSpaceAround, PanelRightOpen } from 'lucide-react'
import ChapterSidebar from '@/components/editor/ChapterSidebar'
import EditorWithMethods, { type EditorMethods, type LiveSelection } from '@/components/editor/EditorWithMethods'
import type { EditorSearchFunctions } from '@/components/editor/StoryEditor'
import AISidecar from '@/components/studio/AISidecar'
import SelectionToolbar from '@/components/studio/SelectionToolbar'
import dynamic from 'next/dynamic'
import { P3_ENABLED } from '@/lib/generationControls'
import { useGenerationStore } from '@/lib/generationStore'
import { useStoryContext } from '@/components/studio/StoryContextEngine'
import { useStudioStore } from '@/lib/studioStore'
import { isSelectionSafeTarget, selectionSafeProps } from '@/lib/selectionOwnership'

// Loaded on demand — the compare dialog (Radix Dialog + diff) is not needed
// until an author opens a comparison, so it stays out of the route's first load.
const VersionCompareView = dynamic(() => import('@/components/generation/VersionCompareView'), { ssr: false })
// Manuscript search & replace (its one home is Write — Stage 8.1). Floating panel,
// loaded only when opened (⌘F / Ctrl+F, or "Search & replace" in the palette).
const SearchPanel = dynamic(() => import('@/components/search/SearchPanel'), { ssr: false })

const EXPANDED_SIDECAR = 65

export default function WriteWorkspace() {
  const { storyId, story, chapters, activeChapter, activeChapterId, setActiveChapter, reloadChapters, registerEditor, updateChapterWordCount } = useStoryContext()
  const store = useStudioStore()
  const compareOpen = useGenerationStore((s) => s.compare !== null)
  const [wordCount, setWordCount] = useState(activeChapter?.word_count ?? 0)

  // Live word count: update both the status-bar number AND the binder/sidebar +
  // story total (via the shared chapters cache) on every keystroke, so counts
  // stay in sync without waiting for autosave or a page refresh.
  const handleWordCountChange = useCallback((count: number) => {
    setWordCount(count)
    if (activeChapterId) updateChapterWordCount(activeChapterId, count)
  }, [activeChapterId, updateChapterWordCount])
  const [selection, setSelection] = useState<LiveSelection | null>(null)
  const methodsRef = useRef<EditorMethods | null>(null)
  const editorAreaRef = useRef<HTMLDivElement | null>(null)

  // ── Search & replace wiring (restored from the pre-Studio editor) ──────────
  const searchFnsRef = useRef<EditorSearchFunctions | null>(null)
  const pendingSearchRef = useRef<{ query: string; caseSensitive: boolean; wholeWord: boolean; targetIndex: number } | null>(null)
  const activeSearchRef = useRef<{ query: string; caseSensitive: boolean; wholeWord: boolean } | null>(null)
  const [editorReloadKey, setEditorReloadKey] = useState(0)
  const closeSearch = useCallback(() => {
    store.setSearchOpen(false)
    searchFnsRef.current?.clearSearch()
    activeSearchRef.current = null
  }, [store])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f' && !e.shiftKey) {
        e.preventDefault()
        store.setSearchOpen(true)
      } else if ((e.ctrlKey || e.metaKey) && e.key === '\\') {
        // ⌘\ / Ctrl+\ — the sidecar shortcut its buttons have always advertised.
        e.preventDefault()
        store.toggleSidecar()
      } else if (e.key === 'Escape' && useStudioStore.getState().searchOpen) {
        closeSearch()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [store, closeSearch])

  // Leaving Write closes the panel so it does not reappear unexpectedly later.
  useEffect(() => () => { useStudioStore.getState().setSearchOpen(false) }, [])

  const handleJumpToMatch = useCallback(
    (chapterId: string, localIndex: number, query: string, caseSensitive: boolean, wholeWord: boolean) => {
      if (activeChapterId === chapterId) {
        searchFnsRef.current?.applySearch(query, caseSensitive, wholeWord, localIndex)
        pendingSearchRef.current = null
      } else {
        pendingSearchRef.current = { query, caseSensitive, wholeWord, targetIndex: localIndex }
        setActiveChapter(chapterId)
      }
    },
    [activeChapterId, setActiveChapter],
  )

  // After a chapter's content loads: land on a pending match, or re-apply the
  // open query so the author sees this chapter's matches too.
  const handleContentLoaded = useCallback(() => {
    const fns = searchFnsRef.current
    if (!fns) return
    if (pendingSearchRef.current) {
      const { query, caseSensitive, wholeWord, targetIndex } = pendingSearchRef.current
      fns.applySearch(query, caseSensitive, wholeWord, targetIndex)
      pendingSearchRef.current = null
    } else if (activeSearchRef.current?.query.trim()) {
      const { query, caseSensitive, wholeWord } = activeSearchRef.current
      fns.applySearch(query, caseSensitive, wholeWord, -1)
    }
  }, [])

  const onMethodsReady = useCallback((m: EditorMethods) => {
    methodsRef.current = m
    registerEditor(m)
  }, [registerEditor])

  // Selection lifecycle: this state is what every AI surface treats as the author's
  // current selection. EditorWithMethods clears it when the ProseMirror selection
  // collapses (in-editor clicks); here we also clear it when the author clicks away
  // and whenever the chapter changes — so no stale selection keeps the toolbar open.
  //
  // "Clicks away" excludes surfaces that consume the selection — the AI sidebar and
  // the toolbar itself, both marked with `data-selection-safe`. Clearing on those
  // would make the sidebar report "no selection" while still transforming the
  // selected words: the exact dishonesty PRE-2 exists to remove.
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      const target = e.target as Node
      if (editorAreaRef.current?.contains(target)) return
      if (isSelectionSafeTarget(target)) return
      setSelection(null)
    }
    document.addEventListener('mousedown', onDown, true)
    return () => document.removeEventListener('mousedown', onDown, true)
  }, [])

  useEffect(() => { setSelection(null) }, [activeChapterId])

  const showSidecar = store.sidecarOpen && !store.focusMode && !store.zenMode
  // Expanded sidecar (8.2 / 8.6): room for detailed AI work — the binder steps
  // aside and the sidecar takes most of the width. Its size is not saved as the
  // normal sidecar size, so collapsing returns to the author's own width.
  const expanded = showSidecar && store.sidecarExpanded
  const showBinder = !store.binderCollapsed && !store.focusMode && !store.zenMode && !expanded
  const sidecarRef = useRef<ImperativePanelHandle | null>(null)
  useEffect(() => {
    if (!showSidecar) return
    sidecarRef.current?.resize(expanded ? EXPANDED_SIDECAR : useStudioStore.getState().sidecarSize)
  }, [expanded, showSidecar])

  const toggleFullscreen = () => {
    if (document.fullscreenElement) document.exitFullscreen()
    else document.documentElement.requestFullscreen?.()
  }

  if (!chapters.length || !activeChapter) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-center text-[#5c6391] gap-3">
        <PenLine className="w-8 h-8" />
        <p className="text-sm">No chapters yet.</p>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col bg-[#0d0f1a]">
      <div className="flex-1 min-h-0">
        {/* Sizes persist through the per-user studio store only (Stage 8.2) — no
            second autoSaveId copy that could disagree with it. */}
        <PanelGroup direction="horizontal" className="h-full">
          {showBinder && (
            <>
              <Panel id="binder" order={1} defaultSize={store.binderSize} minSize={12} maxSize={32}
                onResize={(s) => store.setBinderSize(s)} className="min-w-0">
                <div className="h-full border-r border-[#1f2440] bg-[#0f1220]">
                  <ChapterSidebar
                    storyId={storyId}
                    chapters={chapters}
                    activeChapterId={activeChapterId}
                    onSelect={(ch) => setActiveChapter(ch.chapter_id)}
                    onChaptersChange={() => reloadChapters()}
                  />
                </div>
              </Panel>
              <PanelResizeHandle className="w-1 bg-transparent hover:bg-amber-500/30 transition-colors" />
            </>
          )}

          <Panel id="editor" order={2} className="min-w-0 relative">
            <div ref={editorAreaRef} className={`h-full overflow-y-auto relative ${store.typewriter ? 'pb-[40vh]' : ''}`}>
              <EditorWithMethods
                storyId={storyId}
                chapter={activeChapter}
                onWordCountChange={handleWordCountChange}
                onMethodsReady={onMethodsReady}
                onSelectionChange={setSelection}
                onSearchReady={(fns) => { searchFnsRef.current = fns }}
                onContentLoaded={handleContentLoaded}
                reloadTrigger={editorReloadKey}
              />
            </div>
            {/* Sibling of the scroll area, not a child of it: anchored to the column
                itself the toolbar cannot drift with scrolled content, and it has a
                stable box to be dragged and clamped inside. Placed after the editor
                in the DOM so a keyboard-only author reaches it with one Tab from the
                text they just selected. */}
            <SelectionToolbar selection={selection} sidebarVisible={showSidecar} />
          </Panel>

          {showSidecar && (
            <>
              <PanelResizeHandle className="w-1 bg-transparent hover:bg-amber-500/30 transition-colors" />
              <Panel id="sidecar" order={3} ref={sidecarRef}
                defaultSize={expanded ? EXPANDED_SIDECAR : store.sidecarSize} minSize={18} maxSize={expanded ? 75 : 40}
                onResize={(s) => { if (!useStudioStore.getState().sidecarExpanded) store.setSidecarSize(s) }} className="min-w-0">
                <AISidecar selection={selection} />
              </Panel>
            </>
          )}
        </PanelGroup>
      </div>

      {/* Status bar / mode controls */}
      {!store.zenMode && (
        <div className="h-8 flex-shrink-0 flex items-center px-3 gap-3 border-t border-[#1f2440] bg-[#0f1220] text-xs text-[#9da3c8]">
          <span>Ch {activeChapter.chapter_number}: <span className="text-[#cdd2f0]">{activeChapter.title || 'Untitled'}</span></span>
          <span className="text-[#5c6391]">·</span>
          <span>{wordCount.toLocaleString()} words</span>
          <span className="text-[#5c6391]">·</span>
          <span>Story {(story?.word_count ?? 0).toLocaleString()}</span>
          <div className="flex-1" />
          {/* Selection-safe: this button hands the selection to the sidebar, so
              pressing it is not the author walking away from their selection. */}
          <button onClick={() => store.toggleSidecar()} {...selectionSafeProps()}
            className={`p-1 rounded hover:bg-[#1f2440] ${store.sidecarOpen ? 'text-amber-400' : ''}`} title="AI assistant (⌘\\)" aria-label="AI assistant" aria-pressed={store.sidecarOpen}><PanelRightOpen className="w-3.5 h-3.5" aria-hidden="true" /></button>
          <button onClick={() => store.toggleTypewriter()} className={`p-1 rounded hover:bg-[#1f2440] ${store.typewriter ? 'text-amber-400' : ''}`} title="Typewriter"><AlignVerticalSpaceAround className="w-3.5 h-3.5" /></button>
          <button onClick={() => store.setFocusMode(!store.focusMode)} className={`p-1 rounded hover:bg-[#1f2440] ${store.focusMode ? 'text-amber-400' : ''}`} title="Focus (⌘.)"><Focus className="w-3.5 h-3.5" /></button>
          <button onClick={() => store.setZenMode(true)} className="p-1 rounded hover:bg-[#1f2440]" title="Zen mode"><Sparkles className="w-3.5 h-3.5" /></button>
          <button onClick={toggleFullscreen} className="p-1 rounded hover:bg-[#1f2440]" title="Fullscreen"><Maximize2 className="w-3.5 h-3.5" /></button>
        </div>
      )}
      {/* Phase 3 compare/merge dialog — mounted once for the workspace; opened
          from Versions or a similarity badge on either AI surface. */}
      {P3_ENABLED && compareOpen && <VersionCompareView />}
      {store.searchOpen && activeChapterId && (
        <SearchPanel
          storyId={storyId}
          activeChapterId={activeChapterId}
          onClose={closeSearch}
          onJumpToMatch={handleJumpToMatch}
          onReplaceComplete={(affected) => { if (affected.includes(activeChapterId)) setEditorReloadKey((k) => k + 1) }}
          onSearchStateChange={(state) => { activeSearchRef.current = state }}
        />
      )}
      {store.zenMode && (
        <button onClick={() => store.setZenMode(false)} className="fixed bottom-4 right-4 z-30 text-[11px] px-3 py-1.5 rounded-full border border-[#2e3454] bg-[#13162a] text-[#9da3c8] hover:text-white">Exit Zen (Esc)</button>
      )}
    </div>
  )
}
