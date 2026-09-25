'use client'

// Binder markers for the Idea Shelf (P3-09 §27.4): each chapter row shows how
// many open ideas are waiting for it. Opening the marker lists them with two
// ways to use one — drag it into the editor, or "Insert at cursor" (the
// keyboard path; drag is never the only way). Using an idea marks it "used",
// with Undo. Inserting goes through the editor bridge → the normal autosave,
// never a server-side write into the manuscript.

import { useCallback, useEffect, useState } from 'react'
import { Lightbulb, ArrowDownToLine } from 'lucide-react'
import { toast } from 'sonner'
import { ocrApi } from '@/lib/api'
import { useStoryContext } from '@/components/studio/StoryContextEngine'
import type { IdeaCard } from '@/lib/types'

export function useChapterIdeas(storyId: string) {
  const [byChapter, setByChapter] = useState<Record<string, IdeaCard[]>>({})
  const reload = useCallback(() => {
    ocrApi.ideaCards(storyId, { status: 'open' })
      .then((r) => {
        const m: Record<string, IdeaCard[]> = {}
        for (const c of r.data as IdeaCard[]) if (c.target_chapter_id && c.card_type !== 'style_sample') (m[c.target_chapter_id] ??= []).push(c)
        setByChapter(m)
      })
      .catch(() => setByChapter({}))   // markers are a convenience; a failure hides them, never blocks writing
  }, [storyId])
  useEffect(() => { reload() }, [reload])
  return { byChapter, reload }
}

export function ChapterIdeasMarker({ count, open, onToggle }: { count: number; open: boolean; onToggle: () => void }) {
  if (!count) return null
  return (
    <button type="button" onClick={(e) => { e.stopPropagation(); onToggle() }} aria-expanded={open}
      data-testid="chapter-ideas-marker"
      title={`${count} idea${count === 1 ? '' : 's'} waiting for this chapter`}
      className="flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded-full bg-amber-500/15 text-amber-300 border border-amber-500/30">
      <Lightbulb className="w-2.5 h-2.5" /> {count}
    </button>
  )
}

export function ChapterIdeasList({ ideas, onUsed }: { ideas: IdeaCard[]; onUsed: () => void }) {
  const { editor } = useStoryContext()
  const markUsed = (c: IdeaCard) =>
    ocrApi.updateIdeaCard(c.card_id, { status: 'used' }).then(() => {
      onUsed()
      toast.success('Idea used — marked as used on the Idea Shelf', {
        action: { label: 'Undo', onClick: () => ocrApi.updateIdeaCard(c.card_id, { status: 'open' }).then(onUsed) },
      })
    }).catch(() => toast.error('Inserted, but the idea could not be marked as used.'))

  return (
    <ul className="mx-4 mb-2 space-y-1" data-testid="chapter-ideas-list" aria-label="Ideas waiting for this chapter">
      <li className="text-[10px] text-[#5c6391]">{ideas.length} idea{ideas.length === 1 ? '' : 's'} waiting here — drag into the text, or insert at the cursor.</li>
      {ideas.map((c) => (
        <li key={c.card_id} draggable
          onDragStart={(e) => e.dataTransfer.setData('text/plain', c.content)}
          onDragEnd={(e) => { if (e.dataTransfer.dropEffect !== 'none') markUsed(c) }}
          className="rounded border border-[#1f2440] bg-[#0d0f1a] p-1.5 cursor-grab">
          <p className="text-[11px] text-[#9da3c8] line-clamp-3 font-serif">{c.title ? <strong className="text-[#cdd2f0]">{c.title}: </strong> : null}{c.content}</p>
          <button type="button" onClick={() => {
            if (!editor) { toast.error('Open this chapter in the editor first.'); return }
            editor.insertText(c.content); markUsed(c)
          }} className="mt-1 inline-flex items-center gap-1 text-[10px] text-[#cdd2f0] hover:text-amber-400">
            <ArrowDownToLine className="w-3 h-3" /> Insert at cursor
          </button>
        </li>
      ))}
    </ul>
  )
}
