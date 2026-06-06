'use client'

import { useState, useEffect, useRef } from 'react'
import { Plus, Trash2, ChevronDown, ChevronUp, Loader2 } from 'lucide-react'
import { ocrApi } from '@/lib/api'
import { StoryNote, NoteCard, NoteCardType } from '@/lib/types'
import { toast } from 'sonner'

interface Props {
  storyId:    string
  reloadKey?: number
}

const CARD_TYPES: NoteCardType[] = ['scene', 'location', 'theme', 'character', 'general']

const CARD_TYPE_STYLES: Record<NoteCardType, string> = {
  scene:     'bg-blue-500/15 text-blue-300 border-blue-500/25',
  location:  'bg-green-500/15 text-green-300 border-green-500/25',
  theme:     'bg-purple-500/15 text-purple-300 border-purple-500/25',
  character: 'bg-orange-500/15 text-orange-300 border-orange-500/25',
  general:   'bg-[#252a45] text-[#9da3c8] border-[#2e3454]',
}

export default function NotesPanel({ storyId, reloadKey }: Props) {
  const [tab, setTab]               = useState<'notes' | 'cards'>('notes')
  const [notes, setNotes]           = useState<StoryNote[]>([])
  const [noteCards, setNoteCards]   = useState<NoteCard[]>([])
  const [loading, setLoading]       = useState(true)
  const [cardFilter, setCardFilter] = useState<NoteCardType | 'all'>('all')
  const [creating, setCreating]     = useState<'note' | 'card' | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    Promise.all([ocrApi.notes(storyId), ocrApi.noteCards(storyId)])
      .then(([nr, cr]) => {
        if (!cancelled) {
          setNotes(nr.data)
          setNoteCards(cr.data)
          setLoading(false)
        }
      })
      .catch(() => {
        if (!cancelled) {
          toast.error('Failed to load notes')
          setLoading(false)
        }
      })
    return () => { cancelled = true }
  }, [storyId, reloadKey])

  const handleNoteCreated  = (n: StoryNote)  => { setNotes(p => [n, ...p]); setCreating(null) }
  const handleNoteUpdated  = (n: StoryNote)  => setNotes(p => p.map(x => x.note_id === n.note_id ? n : x))
  const handleNoteDeleted  = (id: string)    => setNotes(p => p.filter(x => x.note_id !== id))
  const handleCardCreated  = (c: NoteCard)   => { setNoteCards(p => [c, ...p]); setCreating(null) }
  const handleCardUpdated  = (c: NoteCard)   => setNoteCards(p => p.map(x => x.card_id === c.card_id ? c : x))
  const handleCardDeleted  = (id: string)    => setNoteCards(p => p.filter(x => x.card_id !== id))

  const filteredCards = cardFilter === 'all' ? noteCards : noteCards.filter(c => c.card_type === cardFilter)

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="w-4 h-4 animate-spin text-[#5c6391]" />
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Sub-tab toggle */}
      <div className="flex border-b border-[#1f2440] flex-shrink-0">
        {(['notes', 'cards'] as const).map(t => (
          <button
            key={t}
            onClick={() => { setTab(t); setCreating(null) }}
            className={`flex-1 py-2 text-xs font-medium transition-colors ${
              tab === t
                ? 'text-amber-400 border-b-2 border-amber-500'
                : 'text-[#5c6391] hover:text-[#9da3c8]'
            }`}
          >
            {t === 'notes' ? 'Story Notes' : 'Note Cards'}
          </button>
        ))}
      </div>

      {tab === 'notes' && (
        <div className="flex flex-col h-full overflow-hidden">
          <div className="p-3 border-b border-[#1f2440] flex-shrink-0">
            {creating === 'note' ? (
              <CreateNoteForm
                storyId={storyId}
                onCreated={handleNoteCreated}
                onCancel={() => setCreating(null)}
              />
            ) : (
              <button
                onClick={() => setCreating('note')}
                className="w-full flex items-center justify-center gap-1.5 py-1.5 text-xs text-[#5c6391] hover:text-amber-400 border border-dashed border-[#2e3454] hover:border-amber-500/40 rounded-lg transition-colors"
              >
                <Plus className="w-3.5 h-3.5" />
                New Note
              </button>
            )}
          </div>

          <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-2">
            {notes.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full gap-2 text-center py-8">
                <p className="text-xs text-[#5c6391] leading-relaxed">
                  No story notes yet.<br />
                  Create one above or scan handwritten notes with the OCR panel.
                </p>
              </div>
            ) : (
              notes.map(note => (
                <NoteItem
                  key={note.note_id}
                  note={note}
                  onUpdated={handleNoteUpdated}
                  onDeleted={handleNoteDeleted}
                />
              ))
            )}
          </div>
        </div>
      )}

      {tab === 'cards' && (
        <div className="flex flex-col h-full overflow-hidden">
          <div className="p-3 border-b border-[#1f2440] flex-shrink-0">
            {creating === 'card' ? (
              <CreateCardForm
                storyId={storyId}
                onCreated={handleCardCreated}
                onCancel={() => setCreating(null)}
              />
            ) : (
              <button
                onClick={() => setCreating('card')}
                className="w-full flex items-center justify-center gap-1.5 py-1.5 text-xs text-[#5c6391] hover:text-amber-400 border border-dashed border-[#2e3454] hover:border-amber-500/40 rounded-lg transition-colors"
              >
                <Plus className="w-3.5 h-3.5" />
                New Card
              </button>
            )}
          </div>

          {/* Card-type filter chips */}
          {creating !== 'card' && (
            <div className="px-3 py-2 border-b border-[#1f2440] flex flex-wrap gap-1 flex-shrink-0">
              {(['all', ...CARD_TYPES] as const).map(type => (
                <button
                  key={type}
                  onClick={() => setCardFilter(type)}
                  className={`px-2 py-0.5 rounded text-[10px] font-medium border transition-colors capitalize ${
                    cardFilter === type
                      ? 'bg-amber-500/20 text-amber-400 border-amber-500/30'
                      : 'bg-[#0d0f1a] text-[#5c6391] border-[#1f2440] hover:text-[#9da3c8]'
                  }`}
                >
                  {type}
                </button>
              ))}
            </div>
          )}

          <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-2">
            {filteredCards.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full gap-2 text-center py-8">
                <p className="text-xs text-[#5c6391] leading-relaxed">
                  {noteCards.length === 0
                    ? 'No note cards yet.\nCreate one above or use the OCR panel.'
                    : `No ${cardFilter} cards.`}
                </p>
              </div>
            ) : (
              filteredCards.map(card => (
                <NoteCardItem
                  key={card.card_id}
                  card={card}
                  onUpdated={handleCardUpdated}
                  onDeleted={handleCardDeleted}
                />
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ── NoteItem ──────────────────────────────────────────────────────────────────

function NoteItem({ note, onUpdated, onDeleted }: {
  note:       StoryNote
  onUpdated:  (n: StoryNote) => void
  onDeleted:  (id: string) => void
}) {
  const [expanded, setExpanded]         = useState(false)
  const [title, setTitle]               = useState(note.title)
  const [content, setContent]           = useState(note.content)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [saving, setSaving]             = useState(false)
  const [deleting, setDeleting]         = useState(false)

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const saveFnRef   = useRef<() => void>(() => {})

  // Keep saveFnRef current so the debounce timer always calls the latest version.
  useEffect(() => {
    saveFnRef.current = async () => {
      setSaving(true)
      try {
        const res = await ocrApi.updateNote(note.note_id, { title, content })
        onUpdated(res.data)
      } catch {
        toast.error('Failed to save note')
      } finally {
        setSaving(false)
      }
    }
  }, [title, content, note.note_id, onUpdated])

  const scheduleSave = () => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => saveFnRef.current(), 800)
  }

  const handleTitleChange = (v: string) => { setTitle(v); scheduleSave() }
  const handleContentChange = (v: string) => { setContent(v); scheduleSave() }

  const handleDelete = async () => {
    setDeleting(true)
    try {
      await ocrApi.deleteNote(note.note_id)
      onDeleted(note.note_id)
    } catch {
      toast.error('Failed to delete note')
      setDeleting(false)
      setConfirmDelete(false)
    }
  }

  return (
    <div className="bg-[#0d0f1a] border border-[#1f2440] rounded-xl overflow-hidden">
      <button
        onClick={() => { setExpanded(v => !v); setConfirmDelete(false) }}
        className="w-full flex items-start gap-2 p-3 text-left hover:bg-[#111428] transition-colors"
      >
        <div className="flex-1 min-w-0">
          <div className="text-xs font-medium text-[#e8eaf6] truncate">
            {title.trim() || 'Untitled Note'}
          </div>
          {!expanded && (
            <div className="text-[10px] text-[#5c6391] mt-0.5 line-clamp-2 leading-relaxed">
              {content || 'Empty note'}
            </div>
          )}
        </div>
        {expanded
          ? <ChevronUp   className="w-3 h-3 text-[#5c6391] flex-shrink-0 mt-0.5" />
          : <ChevronDown className="w-3 h-3 text-[#5c6391] flex-shrink-0 mt-0.5" />}
      </button>

      {expanded && (
        <div className="px-3 pb-3 flex flex-col gap-2">
          <input
            type="text"
            value={title}
            onChange={e => handleTitleChange(e.target.value)}
            placeholder="Untitled Note"
            className="w-full bg-[#1a1e36] border border-[#2e3454] rounded-lg px-2.5 py-1.5 text-xs text-[#e8eaf6] placeholder-[#3d4466] focus:outline-none focus:border-amber-500/50"
          />
          <textarea
            value={content}
            onChange={e => handleContentChange(e.target.value)}
            rows={5}
            className="w-full bg-[#1a1e36] border border-[#2e3454] rounded-lg px-2.5 py-1.5 text-xs text-[#e8eaf6] resize-none focus:outline-none focus:border-amber-500/50 leading-relaxed"
          />
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-[#3d4466]">
              {saving ? 'Saving…' : 'Auto-saved'}
            </span>
            {confirmDelete ? (
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] text-[#9da3c8]">Delete?</span>
                <button
                  onClick={handleDelete}
                  disabled={deleting}
                  className="px-2 py-0.5 text-[10px] bg-red-500/20 text-red-400 border border-red-500/30 rounded hover:bg-red-500/30 transition-colors disabled:opacity-40"
                >
                  {deleting ? '…' : 'Yes'}
                </button>
                <button
                  onClick={() => setConfirmDelete(false)}
                  className="px-2 py-0.5 text-[10px] text-[#5c6391] hover:text-[#9da3c8] transition-colors"
                >
                  No
                </button>
              </div>
            ) : (
              <button
                onClick={() => setConfirmDelete(true)}
                className="flex items-center gap-1 text-[10px] text-[#3d4466] hover:text-red-400 transition-colors"
              >
                <Trash2 className="w-3 h-3" />
                Delete
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ── NoteCardItem ──────────────────────────────────────────────────────────────

function NoteCardItem({ card, onUpdated, onDeleted }: {
  card:       NoteCard
  onUpdated:  (c: NoteCard) => void
  onDeleted:  (id: string) => void
}) {
  const [expanded, setExpanded]           = useState(false)
  const [title, setTitle]                 = useState(card.title)
  const [content, setContent]             = useState(card.content)
  const [cardType, setCardType]           = useState<NoteCardType>(card.card_type)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [saving, setSaving]               = useState(false)
  const [deleting, setDeleting]           = useState(false)

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const saveFnRef   = useRef<() => void>(() => {})

  useEffect(() => {
    saveFnRef.current = async () => {
      setSaving(true)
      try {
        const res = await ocrApi.updateNoteCard(card.card_id, { title, content })
        onUpdated(res.data)
      } catch {
        toast.error('Failed to save note card')
      } finally {
        setSaving(false)
      }
    }
  }, [title, content, card.card_id, onUpdated])

  const scheduleSave = () => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => saveFnRef.current(), 800)
  }

  const handleTitleChange   = (v: string) => { setTitle(v); scheduleSave() }
  const handleContentChange = (v: string) => { setContent(v); scheduleSave() }

  const handleCardTypeChange = async (v: NoteCardType) => {
    setCardType(v)
    try {
      const res = await ocrApi.updateNoteCard(card.card_id, { card_type: v })
      onUpdated(res.data)
    } catch {
      toast.error('Failed to update card type')
      setCardType(card.card_type)
    }
  }

  const handleDelete = async () => {
    setDeleting(true)
    try {
      await ocrApi.deleteNoteCard(card.card_id)
      onDeleted(card.card_id)
    } catch {
      toast.error('Failed to delete note card')
      setDeleting(false)
      setConfirmDelete(false)
    }
  }

  return (
    <div className="bg-[#0d0f1a] border border-[#1f2440] rounded-xl overflow-hidden">
      <button
        onClick={() => { setExpanded(v => !v); setConfirmDelete(false) }}
        className="w-full flex items-start gap-2 p-3 text-left hover:bg-[#111428] transition-colors"
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 mb-0.5">
            <span className={`px-1.5 py-px text-[9px] font-medium rounded border capitalize flex-shrink-0 ${CARD_TYPE_STYLES[cardType]}`}>
              {cardType}
            </span>
          </div>
          <div className="text-xs font-medium text-[#e8eaf6] truncate">
            {title.trim() || 'Untitled Card'}
          </div>
          {!expanded && (
            <div className="text-[10px] text-[#5c6391] mt-0.5 line-clamp-2 leading-relaxed">
              {content || 'Empty card'}
            </div>
          )}
        </div>
        {expanded
          ? <ChevronUp   className="w-3 h-3 text-[#5c6391] flex-shrink-0 mt-0.5" />
          : <ChevronDown className="w-3 h-3 text-[#5c6391] flex-shrink-0 mt-0.5" />}
      </button>

      {expanded && (
        <div className="px-3 pb-3 flex flex-col gap-2">
          <select
            value={cardType}
            onChange={e => handleCardTypeChange(e.target.value as NoteCardType)}
            className="w-full bg-[#1a1e36] border border-[#2e3454] rounded-lg px-2.5 py-1.5 text-xs text-[#e8eaf6] focus:outline-none focus:border-amber-500/50 capitalize"
          >
            {CARD_TYPES.map(t => (
              <option key={t} value={t} className="capitalize">{t}</option>
            ))}
          </select>
          <input
            type="text"
            value={title}
            onChange={e => handleTitleChange(e.target.value)}
            placeholder="Untitled Card"
            className="w-full bg-[#1a1e36] border border-[#2e3454] rounded-lg px-2.5 py-1.5 text-xs text-[#e8eaf6] placeholder-[#3d4466] focus:outline-none focus:border-amber-500/50"
          />
          <textarea
            value={content}
            onChange={e => handleContentChange(e.target.value)}
            rows={4}
            className="w-full bg-[#1a1e36] border border-[#2e3454] rounded-lg px-2.5 py-1.5 text-xs text-[#e8eaf6] resize-none focus:outline-none focus:border-amber-500/50 leading-relaxed"
          />
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-[#3d4466]">
              {saving ? 'Saving…' : 'Auto-saved'}
            </span>
            {confirmDelete ? (
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] text-[#9da3c8]">Delete?</span>
                <button
                  onClick={handleDelete}
                  disabled={deleting}
                  className="px-2 py-0.5 text-[10px] bg-red-500/20 text-red-400 border border-red-500/30 rounded hover:bg-red-500/30 transition-colors disabled:opacity-40"
                >
                  {deleting ? '…' : 'Yes'}
                </button>
                <button
                  onClick={() => setConfirmDelete(false)}
                  className="px-2 py-0.5 text-[10px] text-[#5c6391] hover:text-[#9da3c8] transition-colors"
                >
                  No
                </button>
              </div>
            ) : (
              <button
                onClick={() => setConfirmDelete(true)}
                className="flex items-center gap-1 text-[10px] text-[#3d4466] hover:text-red-400 transition-colors"
              >
                <Trash2 className="w-3 h-3" />
                Delete
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Create forms ──────────────────────────────────────────────────────────────

function CreateNoteForm({ storyId, onCreated, onCancel }: {
  storyId:   string
  onCreated: (n: StoryNote) => void
  onCancel:  () => void
}) {
  const [title, setTitle]   = useState('')
  const [content, setContent] = useState('')
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    if (!content.trim()) { toast.error('Note content is required'); return }
    setSaving(true)
    try {
      const res = await ocrApi.createNote(storyId, title, content)
      onCreated(res.data)
    } catch {
      toast.error('Failed to create note')
      setSaving(false)
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <input
        type="text"
        value={title}
        onChange={e => setTitle(e.target.value)}
        placeholder="Title (optional)"
        autoFocus
        className="w-full bg-[#0d0f1a] border border-[#2e3454] rounded-lg px-2.5 py-1.5 text-xs text-[#e8eaf6] placeholder-[#3d4466] focus:outline-none focus:border-amber-500/50"
      />
      <textarea
        value={content}
        onChange={e => setContent(e.target.value)}
        placeholder="Note content…"
        rows={4}
        className="w-full bg-[#0d0f1a] border border-[#2e3454] rounded-lg px-2.5 py-1.5 text-xs text-[#e8eaf6] placeholder-[#3d4466] resize-none focus:outline-none focus:border-amber-500/50 leading-relaxed"
      />
      <div className="flex gap-2">
        <button
          onClick={handleSave}
          disabled={saving || !content.trim()}
          className="flex-1 py-1.5 text-xs bg-amber-500/20 text-amber-400 border border-amber-500/30 rounded-lg hover:bg-amber-500/30 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {saving ? 'Saving…' : 'Save'}
        </button>
        <button
          onClick={onCancel}
          className="px-3 py-1.5 text-xs text-[#5c6391] hover:text-[#9da3c8] transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

function CreateCardForm({ storyId, onCreated, onCancel }: {
  storyId:   string
  onCreated: (c: NoteCard) => void
  onCancel:  () => void
}) {
  const [title, setTitle]       = useState('')
  const [content, setContent]   = useState('')
  const [cardType, setCardType] = useState<NoteCardType>('general')
  const [saving, setSaving]     = useState(false)

  const handleSave = async () => {
    if (!content.trim()) { toast.error('Card content is required'); return }
    setSaving(true)
    try {
      const res = await ocrApi.createNoteCard(storyId, title, content, cardType)
      onCreated(res.data)
    } catch {
      toast.error('Failed to create note card')
      setSaving(false)
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <select
        value={cardType}
        onChange={e => setCardType(e.target.value as NoteCardType)}
        className="w-full bg-[#0d0f1a] border border-[#2e3454] rounded-lg px-2.5 py-1.5 text-xs text-[#e8eaf6] focus:outline-none focus:border-amber-500/50 capitalize"
      >
        {CARD_TYPES.map(t => (
          <option key={t} value={t} className="capitalize">{t}</option>
        ))}
      </select>
      <input
        type="text"
        value={title}
        onChange={e => setTitle(e.target.value)}
        placeholder="Title (optional)"
        autoFocus
        className="w-full bg-[#0d0f1a] border border-[#2e3454] rounded-lg px-2.5 py-1.5 text-xs text-[#e8eaf6] placeholder-[#3d4466] focus:outline-none focus:border-amber-500/50"
      />
      <textarea
        value={content}
        onChange={e => setContent(e.target.value)}
        placeholder="Card content…"
        rows={3}
        className="w-full bg-[#0d0f1a] border border-[#2e3454] rounded-lg px-2.5 py-1.5 text-xs text-[#e8eaf6] placeholder-[#3d4466] resize-none focus:outline-none focus:border-amber-500/50 leading-relaxed"
      />
      <div className="flex gap-2">
        <button
          onClick={handleSave}
          disabled={saving || !content.trim()}
          className="flex-1 py-1.5 text-xs bg-amber-500/20 text-amber-400 border border-amber-500/30 rounded-lg hover:bg-amber-500/30 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {saving ? 'Saving…' : 'Save'}
        </button>
        <button
          onClick={onCancel}
          className="px-3 py-1.5 text-xs text-[#5c6391] hover:text-[#9da3c8] transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}
