'use client'

// Idea Shelf (Phase 3 P3-09) — a tab inside Notes, not a new navigation entry
// (decision D10, QA Issue 10). Ideas are ordinary note cards with an idea type,
// so they are permanent, survive pin expiry, and are found by the existing
// note search and Plot Assistant retrieval with no extra pipeline.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Loader2, RefreshCw, Plus, Archive, CheckCircle2, Trash2, Copy, RotateCcw, Tag } from 'lucide-react'
import { toast } from 'sonner'
import { ocrApi } from '@/lib/api'
import { IDEA_TYPES, apiErrorText } from '@/lib/generationControls'
import { useStoryContext } from '@/components/studio/StoryContextEngine'
import type { IdeaCard } from '@/lib/types'

type Grouping = 'type' | 'chapter' | 'date'
const typeLabel = (id: string) => IDEA_TYPES.find((t) => t.id === id)?.label ?? id

export default function IdeaShelfTab({ storyId }: { storyId: string }) {
  const { chapters } = useStoryContext()
  const [ideas, setIdeas] = useState<IdeaCard[]>([])
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [filterType, setFilterType] = useState('')
  const [filterStatus, setFilterStatus] = useState<'open' | 'used' | 'archived' | ''>('open')
  const [filterChapter, setFilterChapter] = useState('')
  const [filterTag, setFilterTag] = useState('')
  const [q, setQ] = useState('')
  const [grouping, setGrouping] = useState<Grouping>('type')
  const [creating, setCreating] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  const load = useCallback(() => {
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl
    setStatus((s) => (s === 'ready' ? s : 'loading'))
    ocrApi.ideaCards(storyId, {
      ...(filterStatus ? { status: filterStatus } : {}), ...(filterType ? { card_type: filterType } : {}),
      ...(filterChapter ? { target_chapter_id: filterChapter } : {}), ...(filterTag ? { tag: filterTag } : {}),
      ...(q.trim() ? { q: q.trim() } : {}),
    }, ctrl.signal)
      .then((r) => { setIdeas(r.data); setStatus('ready') })
      .catch((e) => { if (e?.code !== 'ERR_CANCELED' && e?.name !== 'CanceledError') setStatus('error') })
  }, [storyId, filterStatus, filterType, filterChapter, filterTag, q])

  useEffect(() => {
    const t = setTimeout(load, 200)
    return () => { clearTimeout(t); abortRef.current?.abort() }
  }, [load])

  const update = async (card: IdeaCard, data: Parameters<typeof ocrApi.updateIdeaCard>[1], ok: string, undo?: Parameters<typeof ocrApi.updateIdeaCard>[1]) => {
    try {
      await ocrApi.updateIdeaCard(card.card_id, data)
      load()
      toast.success(ok, undo ? { action: { label: 'Undo', onClick: () => ocrApi.updateIdeaCard(card.card_id, undo).then(load) } } : undefined)
    } catch (e) {
      toast.error(apiErrorText(e, 'That idea could not be updated.'))
    }
  }

  const chapterName = (id: string | null) => {
    const c = chapters.find((x) => x.chapter_id === id)
    return c ? `Ch ${c.chapter_number}: ${c.title || 'Untitled'}` : 'Unassigned'
  }

  const groups = useMemo(() => {
    const keyOf = (c: IdeaCard) => grouping === 'type' ? typeLabel(c.card_type)
      : grouping === 'chapter' ? chapterName(c.target_chapter_id)
      : new Date(c.created_at.endsWith('Z') ? c.created_at : `${c.created_at}Z`).toLocaleDateString()
    const m = new Map<string, IdeaCard[]>()
    for (const c of ideas) m.set(keyOf(c), [...(m.get(keyOf(c)) ?? []), c])
    return [...m.entries()]
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ideas, grouping, chapters])

  const allTags = useMemo(() => [...new Set(ideas.flatMap((c) => c.tags ?? []))], [ideas])
  const sel = 'bg-[#13162a] border border-[#2e3454] rounded px-1.5 py-1 text-[11px] text-[#e8eaf6]'

  return (
    <div className="flex flex-col h-full overflow-hidden" data-testid="idea-shelf">
      <div className="p-3 border-b border-[#1f2440] space-y-2 flex-shrink-0">
        <p className="text-[11px] text-[#8e94bd]">Ideas are kept permanently. Pinned AI versions expire — send the good ones here.</p>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search ideas…" aria-label="Search ideas"
          className="w-full bg-[#0d0f1a] border border-[#2e3454] rounded-lg px-2.5 py-1.5 text-xs text-[#e8eaf6]" />
        <div className="grid grid-cols-2 gap-1.5">
          <select className={sel} value={filterType} onChange={(e) => setFilterType(e.target.value)} aria-label="Idea type">
            <option value="">All types</option>
            {IDEA_TYPES.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
          </select>
          <select className={sel} value={filterStatus} onChange={(e) => setFilterStatus(e.target.value as typeof filterStatus)} aria-label="Status">
            <option value="open">Open</option><option value="used">Used</option><option value="archived">Archived</option><option value="">All</option>
          </select>
          <select className={sel} value={filterChapter} onChange={(e) => setFilterChapter(e.target.value)} aria-label="Chapter">
            <option value="">Any chapter</option>
            {chapters.map((c) => <option key={c.chapter_id} value={c.chapter_id}>Ch {c.chapter_number}: {c.title || 'Untitled'}</option>)}
          </select>
          <select className={sel} value={filterTag} onChange={(e) => setFilterTag(e.target.value)} aria-label="Tag">
            <option value="">Any tag</option>
            {allTags.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <div className="flex items-center gap-1 text-[10px] text-[#8e94bd]">
          Group by
          {(['type', 'chapter', 'date'] as Grouping[]).map((g) => (
            <button key={g} onClick={() => setGrouping(g)} aria-pressed={grouping === g}
              className={`px-1.5 py-0.5 rounded ${grouping === g ? 'bg-amber-500/20 text-amber-300' : 'hover:bg-[#1f2440]'}`}>{g}</button>
          ))}
          <button onClick={() => setCreating((c) => !c)} className="ml-auto flex items-center gap-1 text-[#9da3c8] hover:text-amber-400"><Plus className="w-3 h-3" /> New idea</button>
        </div>
        {creating && <CreateIdea storyId={storyId} onDone={() => { setCreating(false); load() }} />}
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {status === 'loading' && <div className="flex justify-center py-6"><Loader2 className="w-4 h-4 animate-spin text-[#8e94bd]" /></div>}
        {status === 'error' && (
          <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-xs">
            Your ideas could not be loaded. Nothing has been lost.
            <button onClick={load} className="mt-2 flex items-center gap-1 text-[11px] px-2 py-1 rounded border border-[#2e3454]"><RefreshCw className="w-3 h-3" /> Try again</button>
          </div>
        )}
        {status === 'ready' && ideas.length === 0 && (
          <p data-testid="ideas-empty" className="text-xs text-[#8e94bd] text-center py-6">No ideas here yet. Use “Send to Idea Shelf” on any AI result or pinned version.</p>
        )}
        {status === 'ready' && groups.map(([name, cards]) => (
          <section key={name} aria-label={name}>
            <h3 className="text-[10px] uppercase tracking-wide text-[#8e94bd] mb-1">{name} · {cards.length}</h3>
            <ul className="space-y-1.5">
              {cards.map((c) => (
                <li key={c.card_id} data-testid="idea-card" draggable
                  onDragStart={(e) => e.dataTransfer.setData('text/plain', c.content)}
                  className="rounded-lg border border-[#1f2440] bg-[#0d0f1a] p-2 space-y-1">
                  <div className="flex items-center gap-1.5 text-[10px] text-[#8e94bd]">
                    <span className="px-1.5 py-px rounded bg-[#1a1e36] text-[#9da3c8]">{typeLabel(c.card_type)}</span>
                    <span className="truncate">{chapterName(c.target_chapter_id)}</span>
                    {c.status !== 'open' && <span className="ml-auto">{c.status}</span>}
                  </div>
                  {c.title && <p className="text-xs font-medium text-[#e8eaf6]">{c.title}</p>}
                  <p className="text-xs text-[#9da3c8] font-serif whitespace-pre-wrap line-clamp-4">{c.content}</p>
                  {c.tags?.length ? <p className="text-[10px] text-[#8e94bd] flex items-center gap-1"><Tag className="w-2.5 h-2.5" />{c.tags.join(', ')}</p> : null}
                  <div className="flex flex-wrap gap-1 pt-0.5">
                    <select aria-label="Assign to chapter" value={c.target_chapter_id ?? ''} className={sel}
                      onChange={(e) => update(c, e.target.value ? { target_chapter_id: e.target.value } : { clear_target_chapter: true }, 'Chapter updated')}>
                      <option value="">Unassigned</option>
                      {chapters.map((ch) => <option key={ch.chapter_id} value={ch.chapter_id}>Ch {ch.chapter_number}</option>)}
                    </select>
                    <button className="text-[10px] px-1.5 py-1 rounded border border-[#2e3454] text-[#cdd2f0]"
                      onClick={() => { navigator.clipboard?.writeText(c.content); toast.success('Idea copied — paste it into your chapter') }}>
                      <Copy className="inline w-3 h-3" /> Copy
                    </button>
                    <TagEditor card={c} onSave={(tags) => update(c, { tags }, 'Tags saved')} />
                    {c.status === 'open' ? (
                      <>
                        <button className="text-[10px] px-1.5 py-1 rounded border border-[#2e3454] text-[#cdd2f0]"
                          onClick={() => update(c, { status: 'used' }, 'Marked as used', { status: 'open' })}><CheckCircle2 className="inline w-3 h-3" /> Used</button>
                        <button className="text-[10px] px-1.5 py-1 rounded border border-[#2e3454] text-[#cdd2f0]"
                          onClick={() => update(c, { status: 'archived' }, 'Archived', { status: 'open' })}><Archive className="inline w-3 h-3" /> Archive</button>
                      </>
                    ) : (
                      <button className="text-[10px] px-1.5 py-1 rounded border border-[#2e3454] text-[#cdd2f0]"
                        onClick={() => update(c, { status: 'open' }, 'Back on the shelf')}><RotateCcw className="inline w-3 h-3" /> Reopen</button>
                    )}
                    <DeleteIdea card={c} onDeleted={load} />
                  </div>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  )
}

function TagEditor({ card, onSave }: { card: IdeaCard; onSave: (tags: string[]) => void }) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState((card.tags ?? []).join(', '))
  if (!editing) return <button className="text-[10px] px-1.5 py-1 rounded border border-[#2e3454] text-[#cdd2f0]" onClick={() => setEditing(true)}><Tag className="inline w-3 h-3" /> Tags</button>
  return (
    <form className="flex gap-1" onSubmit={(e) => { e.preventDefault(); setEditing(false); onSave(value.split(',').map((t) => t.trim()).filter(Boolean)) }}>
      <input autoFocus value={value} onChange={(e) => setValue(e.target.value)} aria-label="Tags, separated by commas"
        className="w-28 bg-[#13162a] border border-[#2e3454] rounded px-1.5 py-0.5 text-[10px] text-[#e8eaf6]" />
      <button type="submit" className="text-[10px] px-1.5 rounded border border-[#2e3454]">Save</button>
    </form>
  )
}

function DeleteIdea({ card, onDeleted }: { card: IdeaCard; onDeleted: () => void }) {
  const [confirm, setConfirm] = useState(false)
  if (!confirm) return <button className="text-[10px] px-1.5 py-1 rounded border border-[#2e3454] text-red-300" onClick={() => setConfirm(true)} aria-label="Delete idea"><Trash2 className="inline w-3 h-3" /></button>
  return (
    <span className="flex items-center gap-1 text-[10px] text-red-200">
      Delete permanently?
      <button className="px-1.5 py-0.5 rounded border border-red-500/40" onClick={() => ocrApi.deleteNoteCard(card.card_id).then(() => { toast.success('Idea deleted'); onDeleted() }).catch(() => toast.error('The idea could not be deleted.'))}>Delete</button>
      <button className="px-1.5 py-0.5 rounded border border-[#2e3454]" onClick={() => setConfirm(false)}>Keep</button>
    </span>
  )
}

function CreateIdea({ storyId, onDone }: { storyId: string; onDone: () => void }) {
  const { chapters } = useStoryContext()
  const [content, setContent] = useState('')
  const [type, setType] = useState('future_scene')
  const [chapter, setChapter] = useState('')
  const [busy, setBusy] = useState(false)
  const save = async () => {
    if (!content.trim()) return
    setBusy(true)
    try {
      await ocrApi.createIdeaCard(storyId, { content: content.trim(), card_type: type, target_chapter_id: chapter || null })
      toast.success('Idea saved'); onDone()
    } catch (e) { toast.error(apiErrorText(e, 'The idea could not be saved.')) } finally { setBusy(false) }
  }
  return (
    <div className="space-y-1.5">
      <textarea value={content} onChange={(e) => setContent(e.target.value)} rows={3} placeholder="Your idea…" aria-label="Idea text"
        className="w-full bg-[#0d0f1a] border border-[#2e3454] rounded px-2 py-1 text-xs text-[#e8eaf6] resize-none" />
      <div className="flex gap-1.5">
        <select value={type} onChange={(e) => setType(e.target.value)} aria-label="Idea type" className="flex-1 bg-[#13162a] border border-[#2e3454] rounded px-1.5 py-1 text-[11px] text-[#e8eaf6]">
          {IDEA_TYPES.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
        </select>
        <select value={chapter} onChange={(e) => setChapter(e.target.value)} aria-label="Chapter" className="flex-1 bg-[#13162a] border border-[#2e3454] rounded px-1.5 py-1 text-[11px] text-[#e8eaf6]">
          <option value="">Unassigned</option>
          {chapters.map((c) => <option key={c.chapter_id} value={c.chapter_id}>Ch {c.chapter_number}</option>)}
        </select>
        <button onClick={save} disabled={busy} className="px-2 rounded bg-amber-500 text-black text-[11px] font-medium disabled:opacity-50">Save</button>
      </div>
    </div>
  )
}
