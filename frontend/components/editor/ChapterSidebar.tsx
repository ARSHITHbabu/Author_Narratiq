'use client'

import { useState } from 'react'
import { Chapter } from '@/lib/types'
import { Plus, Trash2, Edit3, Check, X, BookOpen, Loader2 } from 'lucide-react'
import { chaptersApi } from '@/lib/api'
import { toast } from 'sonner'

interface Props {
  storyId: string
  chapters: Chapter[]
  activeChapterId: string | null
  onSelect: (ch: Chapter) => void
  onChaptersChange: (chapters: Chapter[]) => void
}

export default function ChapterSidebar({ storyId, chapters, activeChapterId, onSelect, onChaptersChange }: Props) {
  const [adding, setAdding] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editTitle, setEditTitle] = useState('')
  const [loading, setLoading] = useState<string | null>(null)

  const addChapter = async () => {
    if (!newTitle.trim()) return
    setLoading('new')
    try {
      const res = await chaptersApi.create(storyId, newTitle.trim())
      onChaptersChange([...chapters, res.data])
      setAdding(false)
      setNewTitle('')
    } catch {
      toast.error('Failed to add chapter')
    } finally {
      setLoading(null)
    }
  }

  const renameChapter = async (chapter: Chapter) => {
    if (!editTitle.trim() || editTitle === chapter.title) {
      setEditingId(null)
      return
    }
    setLoading(chapter.chapter_id)
    try {
      await chaptersApi.update(storyId, chapter.chapter_id, { title: editTitle.trim() })
      onChaptersChange(chapters.map((c) => (c.chapter_id === chapter.chapter_id ? { ...c, title: editTitle.trim() } : c)))
    } catch {
      toast.error('Failed to rename')
    } finally {
      setLoading(null)
      setEditingId(null)
    }
  }

  const deleteChapter = async (ch: Chapter) => {
    if (chapters.length === 1) return toast.error('A story must have at least one chapter')
    if (!confirm(`Delete "${ch.title}"? This cannot be undone.`)) return
    setLoading(ch.chapter_id)
    try {
      await chaptersApi.delete(storyId, ch.chapter_id)
      const updated = chapters.filter((c) => c.chapter_id !== ch.chapter_id)
      onChaptersChange(updated)
      if (activeChapterId === ch.chapter_id && updated.length > 0) {
        onSelect(updated[0])
      }
    } catch {
      toast.error('Failed to delete chapter')
    } finally {
      setLoading(null)
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-[#1f2440] flex items-center justify-between">
        <div className="flex items-center gap-2">
          <BookOpen className="w-4 h-4 text-amber-500" />
          <span className="text-xs font-medium text-[#9da3c8] uppercase tracking-wider">Chapters</span>
        </div>
        <button
          onClick={() => {
            setNewTitle(`Chapter ${chapters.length + 1}`)
            setAdding(true)
            setTimeout(() => {
              const el = document.getElementById('new-chapter-input') as HTMLInputElement | null
              el?.focus()
              el?.select()
            }, 50)
          }}
          className="p-1 text-[#5c6391] hover:text-amber-400 transition-colors"
          title="Add chapter"
        >
          <Plus className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto py-2">
        {chapters.map((ch) => (
          <div
            key={ch.chapter_id}
            className={`group flex items-center gap-2 px-3 py-2 mx-2 rounded-lg cursor-pointer transition-all ${
              activeChapterId === ch.chapter_id
                ? 'bg-amber-500/10 border border-amber-500/20'
                : 'hover:bg-[#1f2440]'
            }`}
          >
            {editingId === ch.chapter_id ? (
              <div className="flex items-center gap-1 flex-1 min-w-0">
                <input
                  autoFocus
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') renameChapter(ch)
                    if (e.key === 'Escape') setEditingId(null)
                  }}
                  className="flex-1 bg-[#0d0f1a] border border-amber-500/40 rounded px-2 py-0.5 text-xs text-[#e8eaf6] focus:outline-none min-w-0"
                />
                <button onClick={() => renameChapter(ch)} className="text-amber-400 hover:text-amber-300 flex-shrink-0">
                  <Check className="w-3.5 h-3.5" />
                </button>
                <button onClick={() => setEditingId(null)} className="text-[#5c6391] hover:text-[#9da3c8] flex-shrink-0">
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            ) : (
              <>
                <div className="flex-1 min-w-0" onClick={() => onSelect(ch)}>
                  <div className="text-xs text-[#5c6391] mb-0.5">
                    Chapter {ch.chapter_number}
                  </div>
                  <div className={`text-sm font-medium truncate ${
                    activeChapterId === ch.chapter_id ? 'text-amber-400' : 'text-[#e8eaf6]'
                  }`}>
                    {ch.title}
                  </div>
                  <div className="text-xs text-[#3d4466] mt-0.5">
                    {ch.word_count > 0 ? `${ch.word_count} words` : 'Empty'}
                  </div>
                </div>
                {loading === ch.chapter_id ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-[#5c6391] flex-shrink-0" />
                ) : (
                  <div className="flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity flex gap-1">
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        setEditingId(ch.chapter_id)
                        setEditTitle(ch.title)
                      }}
                      className="p-1 text-[#5c6391] hover:text-amber-400"
                    >
                      <Edit3 className="w-3 h-3" />
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); deleteChapter(ch) }}
                      className="p-1 text-[#5c6391] hover:text-red-400"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        ))}

        {adding && (
          <div className="px-3 py-2 mx-2">
            <input
              id="new-chapter-input"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') addChapter()
                if (e.key === 'Escape') { setAdding(false); setNewTitle('') }
              }}
              placeholder="Chapter title..."
              className="w-full bg-[#0d0f1a] border border-amber-500/40 rounded-lg px-3 py-1.5 text-sm text-[#e8eaf6] placeholder-[#3d4466] focus:outline-none"
            />
            <div className="flex gap-2 mt-2">
              <button
                onClick={addChapter}
                disabled={loading === 'new'}
                className="flex-1 bg-amber-500/20 text-amber-400 text-xs py-1.5 rounded hover:bg-amber-500/30 flex items-center justify-center gap-1"
              >
                {loading === 'new' ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
                Add
              </button>
              <button
                onClick={() => { setAdding(false); setNewTitle('') }}
                className="flex-1 border border-[#2e3454] text-[#5c6391] text-xs py-1.5 rounded hover:border-[#3d4466]"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
