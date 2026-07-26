'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { Plus, Trash2, ChevronDown, ChevronUp, Loader2, AlertCircle, RefreshCw } from 'lucide-react'
import { ocrApi } from '@/lib/api'
import { StoryNote, NoteCard, NoteCardType } from '@/lib/types'
import { toast } from 'sonner'

interface Props {
  storyId:    string
  reloadKey?: number
}

// Notes and Note Cards are fetched INDEPENDENTLY (QA Issue 7). They used to share
// one `Promise.all`, so a failure in either discarded both — and the panel then
// rendered its ordinary empty state, telling the author they had no notes when the
// truth was that we could not read them. Each section now owns its own state:
//
//   loading → the request is in flight
//   ready   → we have the server's answer, which may legitimately be an empty list
//   error   → the request failed; the author is told so and offered Retry
//
// A cancelled request (unmount, navigation, a newer load) is NOT an error and never
// changes what is on screen. There is no automatic retry — a hidden retry would hide
// the defect this task exists to remove.
type SectionStatus = 'loading' | 'ready' | 'error'
interface Section<T> { data: T[]; status: SectionStatus }

const isCancellation = (err: unknown): boolean => {
  const e = err as { code?: string; name?: string; message?: string } | null
  return !!e && (e.code === 'ERR_CANCELED' || e.name === 'CanceledError' || e.name === 'AbortError')
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
  const [notesSection, setNotesSection] = useState<Section<StoryNote>>({ data: [], status: 'loading' })
  const [cardsSection, setCardsSection] = useState<Section<NoteCard>>({ data: [], status: 'loading' })
  const [cardFilter, setCardFilter] = useState<NoteCardType | 'all'>('all')
  const [creating, setCreating]     = useState<'note' | 'card' | null>(null)

  const notes     = notesSection.data
  const noteCards = cardsSection.data

  // Every load carries a sequence number and an abort signal. A response from an
  // older load can never overwrite a newer one, however fast the author navigates.
  const seqRef = useRef(0)
  const abortRef = useRef<AbortController | null>(null)

  const loadNotes = useCallback((seq: number, signal: AbortSignal) => {
    setNotesSection((s) => ({ ...s, status: 'loading' }))
    ocrApi.notes(storyId, signal)
      .then((r) => { if (seq === seqRef.current) setNotesSection({ data: r.data, status: 'ready' }) })
      .catch((e) => {
        if (isCancellation(e) || seq !== seqRef.current) return   // cancelled ≠ failed
        setNotesSection((s) => ({ ...s, status: 'error' }))
      })
  }, [storyId])

  const loadCards = useCallback((seq: number, signal: AbortSignal) => {
    setCardsSection((s) => ({ ...s, status: 'loading' }))
    ocrApi.noteCards(storyId, signal)
      .then((r) => { if (seq === seqRef.current) setCardsSection({ data: r.data, status: 'ready' }) })
      .catch((e) => {
        if (isCancellation(e) || seq !== seqRef.current) return
        setCardsSection((s) => ({ ...s, status: 'error' }))
      })
  }, [storyId])

  const load = useCallback((what: 'both' | 'notes' | 'cards' = 'both') => {
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl
    const seq = ++seqRef.current
    if (what !== 'cards') loadNotes(seq, ctrl.signal)
    if (what !== 'notes') loadCards(seq, ctrl.signal)
  }, [loadNotes, loadCards])

  useEffect(() => {
    load('both')
    return () => abortRef.current?.abort()
  }, [load, reloadKey])

  // One accurate toast per outcome, and only on a real failure. Announced once per
  // transition into the failed state, so a retry that fails again still tells the
  // author, but a steady failed state does not nag.
  const announcedRef = useRef<string>('')
  useEffect(() => {
    const failed = [
      notesSection.status === 'error' ? 'notes' : null,
      cardsSection.status === 'error' ? 'cards' : null,
    ].filter(Boolean).join('+')
    if (!failed) { announcedRef.current = ''; return }
    if (announcedRef.current === failed) return
    announcedRef.current = failed
    toast.error(
      failed === 'notes+cards' ? 'Notes and note cards could not be loaded.'
        : failed === 'notes'    ? 'Story notes could not be loaded. Note cards are unaffected.'
        :                         'Note cards could not be loaded. Your story notes are unaffected.',
    )
  }, [notesSection.status, cardsSection.status])

  const handleNoteCreated  = (n: StoryNote)  => { setNotesSection(s => ({ ...s, data: [n, ...s.data] })); setCreating(null) }
  const handleNoteUpdated  = (n: StoryNote)  => setNotesSection(s => ({ ...s, data: s.data.map(x => x.note_id === n.note_id ? n : x) }))
  const handleNoteDeleted  = (id: string)    => setNotesSection(s => ({ ...s, data: s.data.filter(x => x.note_id !== id) }))
  const handleCardCreated  = (c: NoteCard)   => { setCardsSection(s => ({ ...s, data: [c, ...s.data] })); setCreating(null) }
  const handleCardUpdated  = (c: NoteCard)   => setCardsSection(s => ({ ...s, data: s.data.map(x => x.card_id === c.card_id ? c : x) }))
  const handleCardDeleted  = (id: string)    => setCardsSection(s => ({ ...s, data: s.data.filter(x => x.card_id !== id) }))

  const filteredCards = cardFilter === 'all' ? noteCards : noteCards.filter(c => c.card_type === cardFilter)

  // Only the very first load blanks the panel. After that each section shows its own
  // state, so one slow or failed request never hides the other's content.
  const neverLoaded = notesSection.status === 'loading' && cardsSection.status === 'loading'
  if (neverLoaded) {
    return (
      <div data-testid="notes-loading" className="flex items-center justify-center h-full">
        <Loader2 className="w-4 h-4 animate-spin text-[#5c6391]" />
      </div>
    )
  }

  const sectionError = (which: 'notes' | 'cards') => (
    <div data-testid={`${which}-error`} className="m-3 rounded-xl border border-red-500/30 bg-red-500/10 p-3">
      <div className="flex items-start gap-2">
        <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
        <div className="min-w-0">
          <p className="text-xs text-[#e8eaf6]">
            {which === 'notes' ? 'Your story notes could not be loaded.' : 'Your note cards could not be loaded.'}
          </p>
          <p className="text-[11px] text-[#9da3c8] mt-0.5">
            Nothing has been lost — this is a problem reading them, not a problem with your writing.
          </p>
          <button
            onClick={() => load(which)}
            className="mt-2 inline-flex items-center gap-1.5 text-[11px] px-2 py-1 rounded-lg border border-[#2e3454] text-[#cdd2f0] hover:bg-[#1f2440]"
          >
            <RefreshCw className="w-3 h-3" /> Try again
          </button>
        </div>
      </div>
    </div>
  )

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Sub-tab toggle */}
      <div className="flex border-b border-[#1f2440] flex-shrink-0">
        {(['notes', 'cards'] as const).map(t => (
          <button
            key={t}
            onClick={() => { setTab(t); setCreating(null) }}
            className={`flex-1 py-2 text-xs font-medium transition-colors flex items-center justify-center gap-1.5 ${
              tab === t
                ? 'text-amber-400 border-b-2 border-amber-500'
                : 'text-[#5c6391] hover:text-[#9da3c8]'
            }`}
          >
            {t === 'notes' ? 'Story Notes' : 'Note Cards'}
            {/* A failure in the section you are NOT looking at is still visible. */}
            {(t === 'notes' ? notesSection.status : cardsSection.status) === 'error' && (
              <AlertCircle data-testid={`${t}-tab-error`} className="w-3 h-3 text-red-400" />
            )}
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
            {notesSection.status === 'error' ? (
              sectionError('notes')
            ) : notesSection.status === 'loading' ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="w-4 h-4 animate-spin text-[#5c6391]" />
              </div>
            ) : notes.length === 0 ? (
              <div data-testid="notes-empty" className="flex flex-col items-center justify-center h-full gap-2 text-center py-8">
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
            {cardsSection.status === 'error' ? (
              sectionError('cards')
            ) : cardsSection.status === 'loading' ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="w-4 h-4 animate-spin text-[#5c6391]" />
              </div>
            ) : filteredCards.length === 0 ? (
              <div data-testid="cards-empty" className="flex flex-col items-center justify-center h-full gap-2 text-center py-8">
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
