'use client'

import { useEffect, useCallback, useRef, useState } from 'react'
import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Placeholder from '@tiptap/extension-placeholder'
import CharacterCount from '@tiptap/extension-character-count'
import Highlight from '@tiptap/extension-highlight'
import Typography from '@tiptap/extension-typography'
import Underline from '@tiptap/extension-underline'
import TextAlign from '@tiptap/extension-text-align'
import {
  Bold, Italic, UnderlineIcon, Strikethrough, Heading1, Heading2,
  Quote, List, ListOrdered, AlignLeft, AlignCenter, AlignRight,
  Highlighter, Undo, Redo, Save, Loader2, MoreHorizontal
} from 'lucide-react'
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { chaptersApi } from '@/lib/api'
import { Chapter } from '@/lib/types'
import { toast } from 'sonner'
import { SearchHighlightExtension, searchHighlightKey, findMatchPositions } from './SearchHighlightExtension'

export interface EditorSearchFunctions {
  applySearch: (query: string, caseSensitive: boolean, wholeWord: boolean, targetIndex: number) => number
  clearSearch: () => void
}

interface Props {
  storyId: string
  chapter: Chapter
  onWordCountChange: (count: number) => void
  onEditorReady?: (editor: any, searchFns: EditorSearchFunctions) => void
  onContentLoaded?: () => void
  reloadTrigger?: number
  /** Reading mode (Stage 8.3): no formatting chrome, and the text cannot be
   *  edited — so nothing is ever autosaved while reading. */
  readOnly?: boolean
}

const ToolbarBtn = ({ onClick, active, title, children }: any) => (
  <button
    type="button"
    onMouseDown={(e) => { e.preventDefault(); onClick() }}
    // Keyboard activation (Enter/Space) arrives as click, not mousedown.
    onClick={(e) => { if (e.detail === 0) onClick() }}
    title={title}
    aria-label={title}
    aria-pressed={active}
    className={`p-1.5 rounded transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/70 ${
      active
        ? 'bg-amber-500/20 text-amber-400'
        : 'text-[#9da3c8] hover:text-[#e8eaf6] hover:bg-[#1f2440]'
    }`}
  >
    {children}
  </button>
)

// Secondary formatting — one "More formatting" menu instead of eight always-on
// buttons (Stage 8.4 progressive disclosure). Nothing is removed.
const moreItemCls = 'w-full text-left px-3 py-1.5 text-xs text-[#cdd2f0] hover:bg-[#1f2440] focus:bg-[#1f2440] outline-none cursor-pointer flex items-center gap-2 data-[state=checked]:text-amber-400'

export default function StoryEditor({ storyId, chapter, onWordCountChange, onEditorReady, onContentLoaded, reloadTrigger, readOnly = false }: Props) {
  const [saving, setSaving] = useState(false)
  const [lastSaved, setLastSaved] = useState<Date | null>(null)
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: { levels: [1, 2, 3] },
      }),
      Placeholder.configure({
        placeholder: 'Begin your chapter here… Every great novel starts with a single sentence.',
      }),
      CharacterCount,
      Highlight.configure({ multicolor: false }),
      Typography,
      Underline,
      TextAlign.configure({ types: ['heading', 'paragraph'] }),
      SearchHighlightExtension,
    ],
    content: chapter.content || '',
    editable: !readOnly,
    editorProps: {
      attributes: { class: 'min-h-[calc(100vh-260px)] focus:outline-none' },
    },
    onCreate({ editor }) {
      const searchFns: EditorSearchFunctions = {
        applySearch(query, caseSensitive, wholeWord, targetIndex) {
          const matches = findMatchPositions(editor.state.doc, query, caseSensitive, wholeWord)
          editor.view.dispatch(
            editor.view.state.tr.setMeta(searchHighlightKey, { matches, activeIndex: targetIndex }),
          )
          if (matches[targetIndex]) {
            editor.commands.setTextSelection(matches[targetIndex])
            editor.commands.scrollIntoView()
          }
          return matches.length
        },
        clearSearch() {
          editor.view.dispatch(
            editor.view.state.tr.setMeta(searchHighlightKey, { matches: [], activeIndex: -1 }),
          )
        },
      }
      onEditorReady?.(editor, searchFns)
    },
    onUpdate({ editor }) {
      const text = editor.getText()
      const wc = text.trim() ? text.trim().split(/\s+/).length : 0
      onWordCountChange(wc)

      // Auto-save with 1.5s debounce
      if (saveTimer.current) clearTimeout(saveTimer.current)
      saveTimer.current = setTimeout(() => {
        saveContent(editor.getHTML())
      }, 1500)
    },
  })

  // Load chapter content when chapter changes OR when the TipTap editor first
  // becomes available.  TipTap's useEditor returns null on the first render and
  // becomes non-null in a subsequent render (it creates the editor in a
  // useEffect internally).  Without `editor` in the dep array the effect fires
  // once while editor is null (exits early) and never re-fires for the same
  // chapter.chapter_id — leaving Chapter 1 blank until the user navigates away
  // and back.  Adding `editor` here makes the effect re-run the moment the
  // editor instance is ready, loading the correct content on first visit.
  useEffect(() => {
    if (!editor) return
    const load = async () => {
      // Purge stale search decorations immediately — before the document is
      // replaced.  Without this, positions from the outgoing chapter survive
      // into the incoming chapter's document and land on arbitrary text.
      editor.view.dispatch(
        editor.view.state.tr.setMeta(searchHighlightKey, { matches: [], activeIndex: -1 }),
      )
      try {
        const res = await chaptersApi.get(storyId, chapter.chapter_id)
        editor.commands.setContent(res.data.content || '', false)
        const text = (res.data.content || '').replace(/<[^>]+>/g, ' ')
        const wc = text.trim() ? text.trim().split(/\s+/).length : 0
        onWordCountChange(wc)
      } catch {
        editor.commands.setContent(chapter.content || '', false)
      }
      onContentLoaded?.()
    }
    load()
    return () => { if (saveTimer.current) clearTimeout(saveTimer.current) }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editor, chapter.chapter_id, reloadTrigger])

  const saveContent = useCallback(async (html: string) => {
    setSaving(true)
    try {
      await chaptersApi.update(storyId, chapter.chapter_id, { content: html })
      setLastSaved(new Date())
    } catch {
      // Silent fail on auto-save
    } finally {
      setSaving(false)
    }
  }, [storyId, chapter.chapter_id])

  // Entering/leaving Reading mode must not emit an update: an update would
  // schedule an autosave of text the author never touched.
  useEffect(() => {
    if (editor && editor.isEditable === readOnly) editor.setEditable(!readOnly, false)
  }, [editor, readOnly])

  const manualSave = () => {
    if (!editor) return
    if (saveTimer.current) clearTimeout(saveTimer.current)
    saveContent(editor.getHTML())
    toast.success('Chapter saved')
  }

  if (!editor) return null

  return (
    <div className="flex flex-col h-full">
      {/* Formatting Toolbar — hidden while reading */}
      {!readOnly && (
      <div role="toolbar" aria-label="Formatting" className="flex items-center gap-0.5 px-4 py-2 border-b border-[#1f2440] flex-wrap">
        <ToolbarBtn onClick={() => editor.chain().focus().toggleBold().run()} active={editor.isActive('bold')} title="Bold"><Bold className="w-3.5 h-3.5" aria-hidden="true" /></ToolbarBtn>
        <ToolbarBtn onClick={() => editor.chain().focus().toggleItalic().run()} active={editor.isActive('italic')} title="Italic"><Italic className="w-3.5 h-3.5" aria-hidden="true" /></ToolbarBtn>
        <ToolbarBtn onClick={() => editor.chain().focus().toggleUnderline().run()} active={editor.isActive('underline')} title="Underline"><UnderlineIcon className="w-3.5 h-3.5" aria-hidden="true" /></ToolbarBtn>

        <div className="w-px h-5 bg-[#2e3454] mx-1" aria-hidden="true" />

        <ToolbarBtn onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()} active={editor.isActive('heading', { level: 1 })} title="Heading 1"><Heading1 className="w-3.5 h-3.5" aria-hidden="true" /></ToolbarBtn>
        <ToolbarBtn onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()} active={editor.isActive('heading', { level: 2 })} title="Heading 2"><Heading2 className="w-3.5 h-3.5" aria-hidden="true" /></ToolbarBtn>

        <DropdownMenu.Root modal={false}>
          <DropdownMenu.Trigger asChild>
            <button type="button" aria-label="More formatting" title="More formatting"
              className="p-1.5 rounded text-[#9da3c8] hover:text-[#e8eaf6] hover:bg-[#1f2440] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/70">
              <MoreHorizontal className="w-3.5 h-3.5" aria-hidden="true" />
            </button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content align="start" sideOffset={4} onCloseAutoFocus={(e) => { e.preventDefault(); editor.commands.focus() }}
              className="w-48 rounded-lg border border-[#2e3454] bg-[#13162a] shadow-xl py-1 z-50">
              {([
                ['Strikethrough', Strikethrough, () => editor.chain().focus().toggleStrike().run(), editor.isActive('strike')],
                ['Highlight', Highlighter, () => editor.chain().focus().toggleHighlight().run(), editor.isActive('highlight')],
                ['Blockquote', Quote, () => editor.chain().focus().toggleBlockquote().run(), editor.isActive('blockquote')],
                ['Bullet list', List, () => editor.chain().focus().toggleBulletList().run(), editor.isActive('bulletList')],
                ['Numbered list', ListOrdered, () => editor.chain().focus().toggleOrderedList().run(), editor.isActive('orderedList')],
                ['Align left', AlignLeft, () => editor.chain().focus().setTextAlign('left').run(), editor.isActive({ textAlign: 'left' })],
                ['Align centre', AlignCenter, () => editor.chain().focus().setTextAlign('center').run(), editor.isActive({ textAlign: 'center' })],
                ['Align right', AlignRight, () => editor.chain().focus().setTextAlign('right').run(), editor.isActive({ textAlign: 'right' })],
              ] as const).map(([label, Icon, run, on]) => (
                <DropdownMenu.CheckboxItem key={label} checked={on} onSelect={() => run()} className={moreItemCls}>
                  <Icon className="w-3.5 h-3.5" aria-hidden="true" /> {label}
                </DropdownMenu.CheckboxItem>
              ))}
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>

        <div className="w-px h-5 bg-[#2e3454] mx-1" aria-hidden="true" />

        <ToolbarBtn onClick={() => editor.chain().focus().undo().run()} active={false} title="Undo"><Undo className="w-3.5 h-3.5" aria-hidden="true" /></ToolbarBtn>
        <ToolbarBtn onClick={() => editor.chain().focus().redo().run()} active={false} title="Redo"><Redo className="w-3.5 h-3.5" aria-hidden="true" /></ToolbarBtn>

        <div className="flex-1" />

        {/* Save status */}
        <div className="flex items-center gap-2 text-xs text-[#9da3c8]" aria-live="polite">
          {saving ? (
            <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Saving...</>
          ) : lastSaved ? (
            <span>Saved {lastSaved.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
          ) : null}
          <button
            onClick={manualSave}
            className="flex items-center gap-1 px-2.5 py-1 bg-[#1f2440] rounded hover:bg-[#252a45] transition-colors text-[#9da3c8]"
          >
            <Save className="w-3 h-3" aria-hidden="true" /> Save
          </button>
        </div>
      </div>
      )}

      {/* Editor area */}
      <div className="flex-1 overflow-y-auto">
        <div className={`mx-auto px-8 py-8 ${readOnly ? 'max-w-2xl reading-mode' : 'max-w-3xl'}`}>
          <h2 className="text-xs font-medium text-[#8e94bd] uppercase tracking-widest mb-6">
            Chapter {chapter.chapter_number} — {chapter.title}
          </h2>
          <EditorContent editor={editor} />
        </div>
      </div>
    </div>
  )
}
