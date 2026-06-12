'use client'

// Reusable wrapper around StoryEditor that exposes the editor-method bridge
// (selection/replace/insert) and search functions. The Write workspace registers
// these into the Story Context Engine so the AI Sidecar, Selection Toolbar, Command
// Palette and Voice Agent all read the live selection from one place.

import { useEffect, useRef } from 'react'
import StoryEditor, { type EditorSearchFunctions } from './StoryEditor'
import type { Chapter } from '@/lib/types'

export interface EditorMethods {
  getSelectedText: () => string
  getFullText: () => string
  insertText: (text: string) => void
  getSelectionRange: () => { from: number; to: number } | null
  replaceRange: (from: number, to: number, text: string) => void
}

export interface LiveSelection { text: string; from: number; to: number }

interface Props {
  storyId: string
  chapter: Chapter
  onWordCountChange: (n: number) => void
  onMethodsReady: (m: EditorMethods) => void
  onSelectionChange?: (sel: LiveSelection | null) => void
  onSearchReady?: (fns: EditorSearchFunctions) => void
  onContentLoaded?: () => void
  reloadTrigger?: number
}

export default function EditorWithMethods({
  storyId, chapter, onWordCountChange, onMethodsReady, onSelectionChange, onSearchReady, onContentLoaded, reloadTrigger,
}: Props) {
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
      getFullText: () => editorRef.current?.getText() ?? '',
      insertText: (text: string) => editorRef.current?.chain().focus().insertContent(text).run(),
      getSelectionRange: () => {
        const ed = editorRef.current
        if (!ed) return null
        const { from, to } = ed.state.selection
        return from === to ? null : { from, to }
      },
      replaceRange: (from: number, to: number, text: string) => {
        editorRef.current?.chain().focus().insertContentAt({ from, to }, text).run()
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
        if (onSelectionChange) {
          ed.on('selectionUpdate', ({ editor }: any) => {
            const { from, to } = editor.state.selection
            onSelectionChange(from === to ? null : { text: editor.state.doc.textBetween(from, to, ' '), from, to })
          })
        }
      }}
    />
  )
}
