'use client'

// Write Workspace — the primary, editor-first experience. Binder (left, resizable/
// collapsible) · Editor (center) · AI Sidecar (right, resizable, default closed).
// Focus / Zen / Fullscreen / Typewriter modes. Selection toolbar for AI on the exact
// selection. Reuses ChapterSidebar + StoryEditor + AIToolsSidebar; the editor bridge
// is published into the Story Context Engine (single source of truth).

import { useCallback, useEffect, useRef, useState } from 'react'
import { Panel, PanelGroup, PanelResizeHandle } from 'react-resizable-panels'
import { PenLine, Sparkles, Focus, Maximize2, AlignVerticalSpaceAround, PanelRightOpen } from 'lucide-react'
import ChapterSidebar from '@/components/editor/ChapterSidebar'
import EditorWithMethods, { type EditorMethods, type LiveSelection } from '@/components/editor/EditorWithMethods'
import AISidecar from '@/components/studio/AISidecar'
import SelectionToolbar from '@/components/studio/SelectionToolbar'
import { useStoryContext } from '@/components/studio/StoryContextEngine'
import { useStudioStore } from '@/lib/studioStore'

export default function WriteWorkspace() {
  const { storyId, story, chapters, activeChapter, activeChapterId, setActiveChapter, reloadChapters, registerEditor } = useStoryContext()
  const store = useStudioStore()
  const [wordCount, setWordCount] = useState(activeChapter?.word_count ?? 0)
  const [selection, setSelection] = useState<LiveSelection | null>(null)
  const methodsRef = useRef<EditorMethods | null>(null)
  const editorAreaRef = useRef<HTMLDivElement | null>(null)

  const onMethodsReady = useCallback((m: EditorMethods) => {
    methodsRef.current = m
    registerEditor(m)
  }, [registerEditor])

  // Selection lifecycle: the toolbar must reflect the LIVE editor selection only.
  // EditorWithMethods clears `selection` when the ProseMirror selection collapses
  // (in-editor clicks). Here we also clear it on clicks OUTSIDE the editor area and
  // whenever the chapter changes — so no stale selection keeps the toolbar open.
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (editorAreaRef.current && !editorAreaRef.current.contains(e.target as Node)) {
        setSelection(null)
      }
    }
    document.addEventListener('mousedown', onDown, true)
    return () => document.removeEventListener('mousedown', onDown, true)
  }, [])

  useEffect(() => { setSelection(null) }, [activeChapterId])

  const showBinder = !store.binderCollapsed && !store.focusMode && !store.zenMode
  const showSidecar = store.sidecarOpen && !store.focusMode && !store.zenMode

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
        <PanelGroup direction="horizontal" autoSaveId="narratiq-write" className="h-full">
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
              <SelectionToolbar selection={selection} />
              <EditorWithMethods
                storyId={storyId}
                chapter={activeChapter}
                onWordCountChange={setWordCount}
                onMethodsReady={onMethodsReady}
                onSelectionChange={setSelection}
              />
            </div>
          </Panel>

          {showSidecar && (
            <>
              <PanelResizeHandle className="w-1 bg-transparent hover:bg-amber-500/30 transition-colors" />
              <Panel id="sidecar" order={3} defaultSize={store.sidecarSize} minSize={18} maxSize={40}
                onResize={(s) => store.setSidecarSize(s)} className="min-w-0">
                <AISidecar />
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
          <button onClick={() => store.toggleSidecar()} className={`p-1 rounded hover:bg-[#1f2440] ${store.sidecarOpen ? 'text-amber-400' : ''}`} title="AI sidecar (⌘\\)"><PanelRightOpen className="w-3.5 h-3.5" /></button>
          <button onClick={() => store.toggleTypewriter()} className={`p-1 rounded hover:bg-[#1f2440] ${store.typewriter ? 'text-amber-400' : ''}`} title="Typewriter"><AlignVerticalSpaceAround className="w-3.5 h-3.5" /></button>
          <button onClick={() => store.setFocusMode(!store.focusMode)} className={`p-1 rounded hover:bg-[#1f2440] ${store.focusMode ? 'text-amber-400' : ''}`} title="Focus (⌘.)"><Focus className="w-3.5 h-3.5" /></button>
          <button onClick={() => store.setZenMode(true)} className="p-1 rounded hover:bg-[#1f2440]" title="Zen mode"><Sparkles className="w-3.5 h-3.5" /></button>
          <button onClick={toggleFullscreen} className="p-1 rounded hover:bg-[#1f2440]" title="Fullscreen"><Maximize2 className="w-3.5 h-3.5" /></button>
        </div>
      )}
      {store.zenMode && (
        <button onClick={() => store.setZenMode(false)} className="fixed bottom-4 right-4 z-30 text-[11px] px-3 py-1.5 rounded-full border border-[#2e3454] bg-[#13162a] text-[#9da3c8] hover:text-white">Exit Zen (Esc)</button>
      )}
    </div>
  )
}
