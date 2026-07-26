'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { Search, Plus, GitBranch, Loader2, Users, Sparkles, AlertCircle, X } from 'lucide-react'
import { charactersApi } from '@/lib/api'
import { Character, CharacterHint, CharacterRole, CharacterStatus } from '@/lib/types'
import CharacterCard from './CharacterCard'
import CharacterCreateModal from './CharacterCreateModal'
import CharacterProfilePanel from './CharacterProfilePanel'
import CharacterRelationshipGraph from './CharacterRelationshipGraph'
import CastGenerationModal from './CastGenerationModal'
import { toast } from 'sonner'

// ── Types ─────────────────────────────────────────────────────────────────────

type View = 'list' | 'profile' | 'graph'

interface Props {
  storyId: string
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function CharacterList({ storyId }: Props) {
  const [view,       setView]       = useState<View>('list')
  const [characters, setCharacters] = useState<Character[]>([])
  const [loading,    setLoading]    = useState(true)
  const [selected,   setSelected]   = useState<Character | null>(null)

  // Search + filter
  const [query,  setQuery]  = useState('')
  const [role,   setRole]   = useState<CharacterRole | ''>('')
  const [status, setStatus] = useState<CharacterStatus | ''>('')

  // Modals
  const [showCreate,       setShowCreate]       = useState(false)
  const [showGenerateCast, setShowGenerateCast] = useState(false)

  // Character hints
  const [hints, setHints] = useState<CharacterHint[]>([])

  // ── Load characters ────────────────────────────────────────────────────────

  // Mention indexing is background work; this says so rather than pretending it is
  // finished. Cleared by the author, not by a timer — a timer would be a guess.
  const [mentionsPending, setMentionsPending] = useState(0)

  // Every load is sequenced: a slower earlier response can never restore a stale
  // cast list or hint count over a newer one (the banner count is the visible half
  // of Issue 9, so it must not flicker backwards).
  const loadSeq = useRef(0)

  const loadCharacters = useCallback(async () => {
    const seq = ++loadSeq.current
    setLoading(true)
    try {
      const [charsRes, hintsRes] = await Promise.all([
        charactersApi.list(storyId),
        charactersApi.getHints(storyId),
      ])
      if (seq !== loadSeq.current) return          // superseded — drop it
      setCharacters(charsRes.data as Character[])
      setHints(hintsRes.data as CharacterHint[])
    } catch {
      if (seq === loadSeq.current) toast.error('Failed to load characters')
    } finally {
      if (seq === loadSeq.current) setLoading(false)
    }
  }, [storyId])

  useEffect(() => { loadCharacters() }, [loadCharacters])

  // ── Search (live — debounced via backend) ──────────────────────────────────

  useEffect(() => {
    if (!query && !role && !status) { loadCharacters(); return }
    const t = setTimeout(async () => {
      try {
        const res = await charactersApi.search(storyId, {
          q:      query  || undefined,
          role:   role   || undefined,
          status: status || undefined,
        })
        setCharacters(res.data as Character[])
      } catch {
        // silently degrade — keep previous list
      }
    }, 300)
    return () => clearTimeout(t)
  }, [query, role, status, storyId])

  // ── Handlers ───────────────────────────────────────────────────────────────

  const handleCreated = (char: Character) => {
    setCharacters(prev => [char, ...prev])
    setSelected(char)
    setView('profile')
    setShowCreate(false)
    if (char.mention_indexing_chapters) setMentionsPending(char.mention_indexing_chapters)
    // Registering a name can resolve unrecognised names — refetch, never guess.
    loadCharacters()
  }

  const handleUpdated = (char: Character) => {
    setCharacters(prev => prev.map(c => c.character_id === char.character_id ? char : c))
    setSelected(char)
    // A rename or a new alias can resolve a pending unrecognised name.
    loadCharacters()
  }

  const handleDeleted = (characterId: string) => {
    setCharacters(prev => prev.filter(c => c.character_id !== characterId))
    setSelected(null)
    setView('list')
  }

  const handleCastGenerated = (newChars: Character[], mentionsIndexing: boolean) => {
    // Immediately show new characters (optimistic)
    setCharacters(prev => [...newChars, ...prev])
    setShowGenerateCast(false)
    // Hint reconciliation happens inside the confirm-cast transaction, so the
    // server is already settled when it answers: refetch immediately instead of
    // waiting out a fixed delay and hoping.
    if (mentionsIndexing) setMentionsPending((n) => Math.max(n, newChars.length ? 1 : 0))
    loadCharacters()
  }

  const handleDismissHint = async (hintId: string) => {
    try {
      await charactersApi.dismissHint(storyId, hintId)
      setHints(prev => prev.filter(h => h.hint_id !== hintId))
    } catch {
      toast.error('Failed to dismiss hint')
    }
  }

  const handlePromoteHint = async (hintId: string) => {
    try {
      const res = await charactersApi.promoteHint(storyId, hintId)
      const newChar = res.data as Character
      setCharacters(prev => [newChar, ...prev])
      setHints(prev => prev.filter(h => h.hint_id !== hintId))
      if (newChar.mention_indexing_chapters) setMentionsPending(newChar.mention_indexing_chapters)
      toast.success(`Added "${newChar.name}" to cast`)
      loadCharacters()          // the same name may have been hinted from other chapters
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to add character')
    }
  }

  const openProfile = (char: Character) => {
    setSelected(char)
    setView('profile')
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  // Background mention indexing — stated as in progress, never as finished. Shown
  // in every view, because creating a character switches to the profile view and
  // the author must not lose sight of work that is still running.
  const mentionsBanner = mentionsPending > 0 ? (
    <div data-testid="mentions-pending" className="px-3 py-2 border-b border-[#1f2440] bg-[#1a1e36] flex items-start gap-1.5 flex-shrink-0">
      <Loader2 className="w-3 h-3 text-[#9da3c8] animate-spin flex-shrink-0 mt-0.5" />
      <div className="min-w-0">
        <p className="text-[10px] text-[#cdd2f0]">
          Story mentions are still being indexed for {mentionsPending} chapter{mentionsPending !== 1 ? 's' : ''}.
        </p>
        <p className="text-[10px] text-[#5c6391]">
          The cast is saved. Mention counts and mention-based search will fill in shortly.
        </p>
      </div>
      <button onClick={() => { setMentionsPending(0); loadCharacters() }}
        className="ml-auto text-[10px] text-[#9da3c8] hover:text-white underline flex-shrink-0">
        Refresh
      </button>
    </div>
  ) : null

  if (view === 'profile' && selected) {
    return (
      <div className="flex flex-col h-full">
        {mentionsBanner}
        <div className="flex-1 min-h-0">
      <CharacterProfilePanel
        storyId={storyId}
        character={selected}
        allChars={characters}
        onBack={() => { setView('list'); setSelected(null) }}
        onUpdated={handleUpdated}
        onDeleted={handleDeleted}
      />
        </div>
      </div>
    )
  }

  if (view === 'graph') {
    return (
      <CharacterRelationshipGraph
        storyId={storyId}
        onBack={() => setView('list')}
        onSelect={openProfile}
      />
    )
  }

  // ── List view ──────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-full">
      {mentionsBanner}
      {/* Header */}
      <div className="px-4 py-3 border-b border-[#1f2440] flex items-center gap-2 flex-shrink-0">
        <Users className="w-3.5 h-3.5 text-amber-500 flex-shrink-0" />
        <span className="text-xs font-semibold text-[#9da3c8] flex-1">Characters</span>
        <button
          onClick={() => setView('graph')}
          title="Relationship graph"
          className="text-[#3d4466] hover:text-amber-400 transition-colors"
        >
          <GitBranch className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={() => setShowGenerateCast(true)}
          title="Generate cast from story"
          className="text-[#3d4466] hover:text-amber-400 transition-colors"
        >
          <Sparkles className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-1 text-[10px] font-medium text-[#5c6391] hover:text-amber-400 border border-[#2e3454] hover:border-amber-500/30 rounded-lg px-2 py-1 transition-all"
        >
          <Plus className="w-3 h-3" />
          New
        </button>
      </div>

      {/* Character hints banner */}
      {hints.length > 0 && (
        <div data-testid="hints-banner" className="px-3 py-2 border-b border-amber-500/20 bg-amber-500/5 flex-shrink-0">
          <div className="flex items-center gap-1.5 mb-1.5">
            <AlertCircle className="w-3 h-3 text-amber-400 flex-shrink-0" />
            <span className="text-[10px] font-semibold text-amber-400">
              {hints.length} unrecognised name{hints.length !== 1 ? 's' : ''} in chapters
            </span>
          </div>
          <div className="flex flex-wrap gap-1">
            {hints.map(hint => (
              <div
                key={hint.hint_id}
                className="flex items-center gap-1 text-[10px] px-2 py-0.5 bg-[#1f2440] border border-amber-500/20 rounded-full"
              >
                <span className="text-[#9da3c8]">{hint.suggested_name}</span>
                <span className="text-[#3d4466]">Ch{hint.chapter_number}</span>
                <button
                  onClick={() => handlePromoteHint(hint.hint_id)}
                  title="Add to cast"
                  className="text-amber-400/60 hover:text-amber-400 transition-colors ml-0.5"
                >
                  <Plus className="w-2.5 h-2.5" />
                </button>
                <button
                  onClick={() => handleDismissHint(hint.hint_id)}
                  title="Dismiss"
                  className="text-[#3d4466] hover:text-red-400 transition-colors"
                >
                  <X className="w-2.5 h-2.5" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Search */}
      <div className="px-3 py-2 border-b border-[#1f2440] flex-shrink-0">
        <div className="flex items-center gap-1.5 bg-[#0d0f1a] border border-[#2e3454] rounded-lg px-2.5 py-1.5">
          <Search className="w-3 h-3 text-[#3d4466] flex-shrink-0" />
          <input
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Search characters…"
            className="flex-1 bg-transparent text-xs text-[#e8eaf6] placeholder-[#3d4466] focus:outline-none min-w-0"
          />
        </div>

        {/* Role / status filters */}
        <div className="flex gap-1 mt-1.5 flex-wrap">
          {(['', 'protagonist', 'antagonist', 'supporting', 'minor'] as const).map(r => (
            <button
              key={r || 'all-roles'}
              onClick={() => setRole(r)}
              className={`text-[9px] px-1.5 py-0.5 rounded-full border capitalize transition-all ${
                role === r
                  ? 'border-amber-500/50 bg-amber-500/10 text-amber-400'
                  : 'border-[#1f2440] text-[#3d4466] hover:border-[#2e3454] hover:text-[#5c6391]'
              }`}
            >
              {r || 'all'}
            </button>
          ))}
          <span className="text-[#1f2440]">|</span>
          {(['', 'active', 'deceased', 'unknown'] as const).map(s => (
            <button
              key={s || 'all-statuses'}
              onClick={() => setStatus(s)}
              className={`text-[9px] px-1.5 py-0.5 rounded-full border capitalize transition-all ${
                status === s
                  ? 'border-amber-500/50 bg-amber-500/10 text-amber-400'
                  : 'border-[#1f2440] text-[#3d4466] hover:border-[#2e3454] hover:text-[#5c6391]'
              }`}
            >
              {s || 'all'}
            </button>
          ))}
        </div>
      </div>

      {/* Character list */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center py-10">
            <Loader2 className="w-4 h-4 text-[#3d4466] animate-spin" />
          </div>
        ) : characters.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 gap-3 px-4">
            <Users className="w-8 h-8 text-[#2e3454]" />
            <p className="text-xs text-[#3d4466] text-center">
              {query || role || status
                ? 'No characters match your filters.'
                : 'No characters yet. Create your first character to get started.'}
            </p>
            {!query && !role && !status && (
              <div className="flex flex-col items-center gap-2 w-full">
                <button
                  onClick={() => setShowGenerateCast(true)}
                  className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-600 text-black font-semibold transition-colors"
                >
                  <Sparkles className="w-3 h-3" />
                  Generate Cast from Story
                </button>
                <button
                  onClick={() => setShowCreate(true)}
                  className="text-[10px] text-[#3d4466] hover:text-[#5c6391] transition-colors"
                >
                  or add manually
                </button>
              </div>
            )}
          </div>
        ) : (
          <div className="p-2 flex flex-col gap-1.5">
            {characters.map(char => (
              <CharacterCard
                key={char.character_id}
                character={char}
                onClick={() => openProfile(char)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Character count */}
      {!loading && characters.length > 0 && (
        <div className="flex-shrink-0 px-3 py-1.5 border-t border-[#1f2440]">
          <p className="text-[10px] text-[#3d4466]">
            {characters.length} character{characters.length !== 1 ? 's' : ''}
          </p>
        </div>
      )}

      {/* Create modal */}
      {showCreate && (
        <CharacterCreateModal
          storyId={storyId}
          onCreated={handleCreated}
          onClose={() => setShowCreate(false)}
        />
      )}

      {/* Generate cast modal */}
      {showGenerateCast && (
        <CastGenerationModal
          storyId={storyId}
          onClose={() => setShowGenerateCast(false)}
          onConfirmed={(chars, indexing) => handleCastGenerated(chars, indexing)}
        />
      )}
    </div>
  )
}
