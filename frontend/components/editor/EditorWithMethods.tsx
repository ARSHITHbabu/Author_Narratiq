'use client'

// Reusable wrapper around StoryEditor that exposes the editor-method bridge
// (selection/replace/insert) and search functions. The Write workspace registers
// these into the Story Context Engine so the AI Sidecar, Selection Toolbar, Command
// Palette and Voice Agent all read the live selection from one place.

import { useEffect, useRef } from 'react'
import StoryEditor, { type EditorSearchFunctions } from './StoryEditor'
import type { Chapter } from '@/lib/types'
import type { OwnedSelection } from '@/lib/selectionOwnership'

export interface EditorMethods {
  getSelectedText: () => string
  getFullText: () => string
  insertText: (text: string) => void
  getSelectionRange: () => { from: number; to: number } | null
  replaceRange: (from: number, to: number, text: string) => void
  /** The text currently occupying a range, or '' if the range no longer exists.
   *  Lets a caller prove a captured range still holds the words it captured
   *  before writing over it. */
  getTextInRange: (from: number, to: number) => string
}

// A live selection always carries the chapter it belongs to: `from`/`to` are
// document offsets and mean nothing outside their own chapter. Everything
// downstream (the toolbar's preview, Apply) checks that chapter before touching
// the manuscript. Same shape as OwnedSelection — one definition, not two.
export type LiveSelection = OwnedSelection

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

  // `onEditorReady` fires once per TipTap instance, and that instance survives
  // chapter switches (content is swapped, the editor is not rebuilt). A closure
  // over `chapter` would therefore stamp every later selection with the FIRST
  // chapter's id. A ref keeps the stamp truthful.
  const chapterIdRef = useRef(chapter.chapter_id)
  useEffect(() => { chapterIdRef.current = chapter.chapter_id }, [chapter.chapter_id])

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
      getTextInRange: (from: number, to: number) => {
        const ed = editorRef.current
        if (!ed) return ''
        const size = ed.state.doc.content.size
        if (from < 0 || to > size || from >= to) return ''
        return ed.state.doc.textBetween(from, to, ' ')
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
            onSelectionChange(
              from === to
                ? null
                : { text: editor.state.doc.textBetween(from, to, ' '), from, to, chapterId: chapterIdRef.current },
            )
          })
        }
      }}
    />
  )
}
