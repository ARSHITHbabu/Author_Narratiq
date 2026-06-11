'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import {
  ArrowLeft, Loader2, Trash2, Plus, X, ChevronDown, ChevronUp,
  Crown, Sword, Users, Eye, Check, BookOpen, Wand2, GitBranch,
} from 'lucide-react'
import { charactersApi, relationshipsApi, voiceCheckApi } from '@/lib/api'
import {
  Character, CharacterMention, CharacterRelationship,
  CharacterRole, CharacterStatus, EnrichResult, EnrichSuggestion,
  RelationshipType, RelationshipStrength, VoiceCheckResponse,
} from '@/lib/types'
import { toast } from 'sonner'
import CharacterArcTimelinePanel from './CharacterArcTimelinePanel'

// ── Constants ─────────────────────────────────────────────────────────────────

const ROLES: { value: CharacterRole; label: string; icon: typeof Crown }[] = [
  { value: 'protagonist', label: 'Protagonist', icon: Crown },
  { value: 'antagonist',  label: 'Antagonist',  icon: Sword },
  { value: 'supporting',  label: 'Supporting',  icon: Users },
  { value: 'minor',       label: 'Minor',       icon: Eye  },
]

const STATUSES: { value: CharacterStatus; label: string }[] = [
  { value: 'active',   label: 'Active'   },
  { value: 'deceased', label: 'Deceased' },
  { value: 'unknown',  label: 'Unknown'  },
]

const REL_TYPES: RelationshipType[] = ['ally', 'rival', 'family', 'romantic', 'mentor', 'enemy', 'neutral']
const STRENGTHS: RelationshipStrength[] = ['weak', 'moderate', 'strong', 'critical']

const STRENGTH_COLOR: Record<RelationshipStrength, string> = {
  weak:     'text-[#5c6391]',
  moderate: 'text-sky-400',
  strong:   'text-amber-400',
  critical: 'text-red-400',
}

const REL_COLOR: Record<RelationshipType, string> = {
  ally:      'text-green-400',
  rival:     'text-amber-400',
  family:    'text-violet-400',
  romantic:  'text-pink-400',
  mentor:    'text-sky-400',
  enemy:     'text-red-400',
  neutral:   'text-[#5c6391]',
}

// ── Types ─────────────────────────────────────────────────────────────────────

interface Props {
  storyId:   string
  character: Character
  allChars:  Character[]
  onBack:    () => void
  onUpdated: (char: Character) => void
  onDeleted: (characterId: string) => void
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function CharacterProfilePanel({
  storyId, character, allChars, onBack, onUpdated, onDeleted,
}: Props) {

  // ── Identity fields ────────────────────────────────────────────────────────
  const [name,       setName]       = useState(character.name)
  const [role,       setRole]       = useState<CharacterRole>(character.role)
  const [status,     setStatus]     = useState<CharacterStatus>(character.status)
  const [aliases,    setAliases]    = useState<string[]>(character.aliases)
  const [aliasInput, setAliasInput] = useState('')
  const [savingId,   setSavingId]   = useState(false)

  // Refs so identity save always reads current values regardless of closure age
  const identityRef = useRef({ name, role, status, aliases })
  identityRef.current = { name, role, status, aliases }

  // ── Profile fields ─────────────────────────────────────────────────────────
  const [age,          setAge]          = useState(character.profile?.age         || '')
  const [appearance,   setAppearance]   = useState(character.profile?.appearance  || '')
  const [personality,  setPersonality]  = useState(character.profile?.personality || '')
  const [goals,        setGoals]        = useState(character.profile?.goals       || '')
  const [motivations,  setMotivations]  = useState(character.profile?.motivations || '')
  const [backstory,    setBackstory]    = useState(character.profile?.backstory   || '')
  const [arcNotes,     setArcNotes]     = useState(character.profile?.arc_notes   || '')
  const [traits,       setTraits]       = useState<string[]>(character.profile?.traits || [])
  const [traitInput,   setTraitInput]   = useState('')
  const [showRawNotes, setShowRawNotes] = useState(false)

  const [savingProfile, setSavingProfile] = useState(false)
  const [profileSaved,  setProfileSaved]  = useState(false)
  const profileTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Profile fields ref — timer reads from here so it always gets latest values
  const profileRef = useRef({ age, appearance, personality, goals, motivations, backstory, arcNotes, traits })
  profileRef.current = { age, appearance, personality, goals, motivations, backstory, arcNotes, traits }

  // ── Relationships ──────────────────────────────────────────────────────────
  const [rels,        setRels]        = useState<CharacterRelationship[]>([])
  const [loadingRels, setLoadingRels] = useState(false)
  const [showAddRel,  setShowAddRel]  = useState(false)
  const [relTarget,   setRelTarget]   = useState('')
  const [relType,     setRelType]     = useState<RelationshipType>('ally')
  const [relStrength, setRelStrength] = useState<RelationshipStrength>('moderate')
  const [relDesc,     setRelDesc]     = useState('')
  const [relMutual,   setRelMutual]   = useState(false)
  const [savingRel,   setSavingRel]   = useState(false)

  // ── Story Mentions ─────────────────────────────────────────────────────────
  const [showMentions,   setShowMentions]   = useState(false)
  const [mentions,       setMentions]       = useState<CharacterMention[] | null>(null)
  const [loadingMentions, setLoadingMentions] = useState(false)

  // ── Enrichment ─────────────────────────────────────────────────────────────
  const [enrichResult,  setEnrichResult]  = useState<EnrichResult | null>(null)
  const [enrichLoading, setEnrichLoading] = useState(false)

  // ── Arc Timeline ───────────────────────────────────────────────────────────
  const [showArcTimeline, setShowArcTimeline] = useState(false)

  // ── Voice Check ────────────────────────────────────────────────────────────
  const [voiceResult,  setVoiceResult]  = useState<VoiceCheckResponse | null>(null)
  const [voiceLoading, setVoiceLoading] = useState(false)
  const [showVoice,    setShowVoice]    = useState(false)

  // ── Delete ─────────────────────────────────────────────────────────────────
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleting,      setDeleting]      = useState(false)

  // ── Load relationships on mount ────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false
    setLoadingRels(true)
    relationshipsApi.list(storyId, character.character_id)
      .then(res => { if (!cancelled) setRels(res.data as CharacterRelationship[]) })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoadingRels(false) })
    return () => { cancelled = true }
  }, [storyId, character.character_id])

  // ── Identity save ──────────────────────────────────────────────────────────
  // Reads from identityRef so always uses the current value, even when called
  // from button onClick handlers where state may not yet have updated.

  const saveIdentityWith = useCallback(async (overrides: {
    name?: string; role?: CharacterRole; status?: CharacterStatus; aliases?: string[]
  }) => {
    const cur = identityRef.current
    const trimmedName = (overrides.name ?? cur.name).trim()
    if (!trimmedName) return
    setSavingId(true)
    try {
      const res = await charactersApi.update(storyId, character.character_id, {
        name:    trimmedName,
        role:    overrides.role    ?? cur.role,
        status:  overrides.status  ?? cur.status,
        aliases: overrides.aliases ?? cur.aliases,
      })
      onUpdated(res.data as Character)
      toast.success('Character updated')
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      if (err?.response?.status === 409) {
        toast.error(detail || 'Another character with that name already exists')
        setName(character.name)
      } else {
        toast.error(detail || 'Failed to update character')
      }
    } finally {
      setSavingId(false)
    }
  }, [storyId, character.character_id, character.name, onUpdated])

  // ── Profile auto-save (debounced) ─────────────────────────────────────────
  // Reads from profileRef at fire time — no stale closures.

  const scheduleProfileSave = useCallback(() => {
    setProfileSaved(false)
    if (profileTimer.current) clearTimeout(profileTimer.current)
    profileTimer.current = setTimeout(async () => {
      const p = profileRef.current
      setSavingProfile(true)
      try {
        const res = await charactersApi.updateProfile(storyId, character.character_id, {
          age:         p.age,
          appearance:  p.appearance,
          personality: p.personality,
          goals:       p.goals,
          motivations: p.motivations,
          backstory:   p.backstory,
          arc_notes:   p.arcNotes,
          traits:      p.traits,
        })
        onUpdated(res.data as Character)
        setProfileSaved(true)
      } catch {
        toast.error('Failed to save profile')
      } finally {
        setSavingProfile(false)
      }
    }, 800)
  }, [storyId, character.character_id, onUpdated])

  // ── Traits ─────────────────────────────────────────────────────────────────

  const addTrait = () => {
    const t = traitInput.trim().toLowerCase()
    if (!t || traits.includes(t)) { setTraitInput(''); return }
    setTraits(prev => [...prev, t])
    setTraitInput('')
    scheduleProfileSave()
  }

  const removeTrait = (t: string) => {
    setTraits(prev => prev.filter(x => x !== t))
    scheduleProfileSave()
  }

  // ── Story Mentions loader ──────────────────────────────────────────────────

  const mentionRetryRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const loadMentions = useCallback(async () => {
    setLoadingMentions(true)
    try {
      const res = await charactersApi.getMentions(storyId, character.character_id)
      const data = res.data as CharacterMention[]
      setMentions(data)
      // If empty, schedule one auto-retry after 5 s (indexing may still be running)
      if (data.length === 0) {
        if (mentionRetryRef.current) clearTimeout(mentionRetryRef.current)
        mentionRetryRef.current = setTimeout(async () => {
          try {
            const r2 = await charactersApi.getMentions(storyId, character.character_id)
            setMentions(r2.data as CharacterMention[])
          } catch { /* silently ignore retry */ }
        }, 5000)
      }
    } catch {
      toast.error('Failed to load story mentions')
      setMentions([])
    } finally {
      setLoadingMentions(false)
    }
  }, [storyId, character.character_id])

  // Clear retry timer on unmount
  useEffect(() => () => {
    if (mentionRetryRef.current) clearTimeout(mentionRetryRef.current)
  }, [])

  const handleToggleMentions = () => {
    if (!showMentions && mentions === null) loadMentions()
    setShowMentions(v => !v)
  }

  // ── Enrich from story ──────────────────────────────────────────────────────

  const handleEnrich = async () => {
    setEnrichLoading(true)
    setEnrichResult(null)
    try {
      const res = await charactersApi.enrich(storyId, character.character_id)
      const data = res.data as EnrichResult
      if (data.suggestions.length === 0) {
        toast.info('No new suggestions found in story mentions')
      } else {
        setEnrichResult(data)
      }
    } catch (err: any) {
      const msg = err?.response?.data?.detail || 'Failed to extract suggestions'
      toast.error(msg)
    } finally {
      setEnrichLoading(false)
    }
  }

  const applyEnrichSuggestion = (s: EnrichSuggestion) => {
    if (s.field === 'traits') {
      const newTraits = s.value.split(',').map(t => t.trim().toLowerCase()).filter(Boolean)
      setTraits(prev => [...new Set([...prev, ...newTraits])])
    } else {
      const setters: Partial<Record<string, (v: string) => void>> = {
        appearance:  setAppearance,
        personality: setPersonality,
        goals:       setGoals,
        motivations: setMotivations,
        backstory:   setBackstory,
        arc_notes:   setArcNotes,
      }
      setters[s.field]?.(s.value)
    }
    scheduleProfileSave()
    setEnrichResult(prev => prev
      ? { ...prev, suggestions: prev.suggestions.filter(x => x !== s) }
      : null
    )
    toast.success(`Applied ${s.field.replace('_', ' ')}`)
  }

  // ── Aliases ────────────────────────────────────────────────────────────────

  const addAlias = () => {
    const a = aliasInput.trim()
    if (!a || aliases.includes(a)) { setAliasInput(''); return }
    const next = [...aliases, a]
    setAliases(next)
    setAliasInput('')
    saveIdentityWith({ aliases: next })
  }

  const removeAlias = (a: string) => {
    const next = aliases.filter(x => x !== a)
    setAliases(next)
    saveIdentityWith({ aliases: next })
  }

  // ── Relationships ──────────────────────────────────────────────────────────

  const createRelationship = async () => {
    if (!relTarget) return
    setSavingRel(true)
    try {
      const res = await relationshipsApi.create(storyId, character.character_id, {
        to_character_id:   relTarget,
        relationship_type: relType,
        strength:          relStrength,
        description:       relDesc,
        is_mutual:         relMutual,
      })
      setRels(prev => [...prev, res.data as CharacterRelationship])
      setShowAddRel(false)
      setRelTarget(''); setRelType('ally'); setRelStrength('moderate')
      setRelDesc(''); setRelMutual(false)
      toast.success('Relationship added')
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      if (err?.response?.status === 409) {
        toast.error(detail || 'This relationship type already exists between these characters')
      } else {
        toast.error(detail || 'Failed to create relationship')
      }
    } finally {
      setSavingRel(false)
    }
  }

  const deleteRelationship = async (rel: CharacterRelationship) => {
    try {
      await relationshipsApi.delete(storyId, rel.from_character_id, rel.relationship_id)
      setRels(prev => prev.filter(r => r.relationship_id !== rel.relationship_id))
    } catch {
      toast.error('Failed to delete relationship')
    }
  }

  // ── Delete character ───────────────────────────────────────────────────────

  const deleteCharacter = async () => {
    setDeleting(true)
    try {
      await charactersApi.delete(storyId, character.character_id)
      toast.success(`"${character.name}" deleted`)
      onDeleted(character.character_id)
    } catch {
      toast.error('Failed to delete character')
      setDeleting(false)
      setConfirmDelete(false)
    }
  }

  // ── Shared profile field component ────────────────────────────────────────

  const ProfileField = ({
    label, value, onChange, rows = 3,
  }: { label: string; value: string; onChange: (v: string) => void; rows?: number }) => (
    <div>
      <label className="text-xs text-[#5c6391] mb-1 block">{label}</label>
      <textarea
        value={value}
        onChange={e => { onChange(e.target.value); scheduleProfileSave() }}
        rows={rows}
        className="w-full bg-[#0d0f1a] border border-[#2e3454] rounded-xl px-3 py-2 text-xs text-[#e8eaf6] focus:outline-none focus:border-amber-500/50 transition-colors resize-none leading-relaxed"
      />
    </div>
  )

  const otherChars = allChars.filter(c => c.character_id !== character.character_id)

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-4 py-3 border-b border-[#1f2440] flex items-center gap-2 flex-shrink-0">
        <button onClick={onBack} className="text-[#5c6391] hover:text-[#9da3c8] transition-colors">
          <ArrowLeft className="w-4 h-4" />
        </button>
        <span className="text-xs font-medium text-[#9da3c8] truncate flex-1">{character.name}</span>
        {savingProfile && <Loader2 className="w-3 h-3 text-[#3d4466] animate-spin flex-shrink-0" />}
        {!savingProfile && profileSaved && (
          <Check className="w-3 h-3 text-green-500/60 flex-shrink-0" />
        )}
        {savingId && <Loader2 className="w-3 h-3 text-amber-500/60 animate-spin flex-shrink-0" />}
      </div>

      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-5">

        {/* ── Identity ──────────────────────────────────────────────────── */}
        <section>
          <p className="text-[10px] font-semibold text-[#3d4466] uppercase tracking-wider mb-2">Identity</p>

          {/* Name */}
          <div className="mb-3">
            <label className="text-xs text-[#5c6391] mb-1 block">Name</label>
            <input
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              onBlur={() => saveIdentityWith({})}
              className="w-full bg-[#0d0f1a] border border-[#2e3454] rounded-xl px-3 py-2 text-sm text-[#e8eaf6] focus:outline-none focus:border-amber-500/50 transition-colors"
            />
          </div>

          {/* Role */}
          <div className="mb-3">
            <label className="text-xs text-[#5c6391] mb-1 block">Role</label>
            <div className="grid grid-cols-2 gap-1">
              {ROLES.map(r => {
                const Icon = r.icon
                return (
                  <button
                    key={r.value}
                    onClick={() => {
                      setRole(r.value)
                      saveIdentityWith({ role: r.value })
                    }}
                    className={`flex items-center gap-1.5 py-1.5 px-2 rounded-lg border text-[11px] font-medium transition-all ${
                      role === r.value
                        ? 'border-amber-500/50 bg-amber-500/10 text-amber-400'
                        : 'border-[#1f2440] text-[#5c6391] hover:border-[#2e3454] hover:text-[#9da3c8]'
                    }`}
                  >
                    <Icon className="w-3 h-3" />
                    {r.label}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Status */}
          <div className="mb-3">
            <label className="text-xs text-[#5c6391] mb-1 block">Status</label>
            <div className="grid grid-cols-3 gap-1">
              {STATUSES.map(s => (
                <button
                  key={s.value}
                  onClick={() => {
                    setStatus(s.value)
                    saveIdentityWith({ status: s.value })
                  }}
                  className={`py-1.5 rounded-lg border text-[11px] font-medium transition-all ${
                    status === s.value
                      ? 'border-amber-500/50 bg-amber-500/10 text-amber-400'
                      : 'border-[#1f2440] text-[#5c6391] hover:border-[#2e3454] hover:text-[#9da3c8]'
                  }`}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>

          {/* Aliases */}
          <div>
            <label className="text-xs text-[#5c6391] mb-1 block">Aliases</label>
            <div className="flex flex-wrap gap-1 mb-1.5">
              {aliases.map(a => (
                <span
                  key={a}
                  className="flex items-center gap-1 text-[11px] px-2 py-0.5 bg-[#1f2440] border border-[#2e3454] rounded-full text-[#9da3c8]"
                >
                  {a}
                  <button onClick={() => removeAlias(a)} className="text-[#3d4466] hover:text-red-400 transition-colors">
                    <X className="w-2.5 h-2.5" />
                  </button>
                </span>
              ))}
            </div>
            <div className="flex gap-1">
              <input
                type="text"
                value={aliasInput}
                onChange={e => setAliasInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addAlias() } }}
                placeholder="Add alias…"
                className="flex-1 bg-[#0d0f1a] border border-[#2e3454] rounded-lg px-2.5 py-1.5 text-xs text-[#e8eaf6] placeholder-[#3d4466] focus:outline-none focus:border-amber-500/50 transition-colors"
              />
              <button
                onClick={addAlias}
                className="px-2 py-1.5 rounded-lg border border-[#2e3454] text-[#5c6391] hover:text-amber-400 hover:border-amber-500/30 transition-colors"
              >
                <Plus className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </section>

        {/* ── Traits ────────────────────────────────────────────────────── */}
        <section>
          <p className="text-[10px] font-semibold text-[#3d4466] uppercase tracking-wider mb-2">Traits</p>
          <div className="flex flex-wrap gap-1 mb-1.5">
            {traits.map(t => (
              <span
                key={t}
                className="flex items-center gap-1 text-[11px] px-2 py-0.5 bg-amber-500/10 border border-amber-500/20 rounded-full text-amber-400"
              >
                {t}
                <button onClick={() => removeTrait(t)} className="text-amber-500/50 hover:text-red-400 transition-colors">
                  <X className="w-2.5 h-2.5" />
                </button>
              </span>
            ))}
          </div>
          <div className="flex gap-1">
            <input
              type="text"
              value={traitInput}
              onChange={e => setTraitInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addTrait() } }}
              placeholder="Add trait (e.g. stubborn)…"
              className="flex-1 bg-[#0d0f1a] border border-[#2e3454] rounded-lg px-2.5 py-1.5 text-xs text-[#e8eaf6] placeholder-[#3d4466] focus:outline-none focus:border-amber-500/50 transition-colors"
            />
            <button
              onClick={addTrait}
              className="px-2 py-1.5 rounded-lg border border-[#2e3454] text-[#5c6391] hover:text-amber-400 hover:border-amber-500/30 transition-colors"
            >
              <Plus className="w-3.5 h-3.5" />
            </button>
          </div>
          <p className="text-[10px] text-[#3d4466] mt-1">Traits are included in Plot Assistant character context.</p>
        </section>

        {/* ── Profile fields ─────────────────────────────────────────────── */}
        <section className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <p className="text-[10px] font-semibold text-[#3d4466] uppercase tracking-wider">Profile</p>
            <button
              onClick={handleEnrich}
              disabled={enrichLoading}
              className="flex items-center gap-1 text-[9px] text-[#5c6391] hover:text-amber-400 transition-colors disabled:opacity-50"
              title="Extract profile suggestions from story mentions"
            >
              {enrichLoading
                ? <Loader2 className="w-3 h-3 animate-spin" />
                : <Wand2 className="w-3 h-3" />
              }
              Enrich from Story
            </button>
          </div>

          {/* Enrichment suggestions */}
          {enrichResult && enrichResult.suggestions.length > 0 && (
            <div className="bg-amber-500/5 border border-amber-500/20 rounded-xl p-3 flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <p className="text-[10px] font-semibold text-amber-400">
                  {enrichResult.suggestions.length} suggestion{enrichResult.suggestions.length !== 1 ? 's' : ''}{' '}
                  from {enrichResult.mentions_analyzed} mention{enrichResult.mentions_analyzed !== 1 ? 's' : ''}
                </p>
                <button
                  onClick={() => setEnrichResult(null)}
                  className="text-[#3d4466] hover:text-[#9da3c8] transition-colors"
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
              {enrichResult.suggestions.map((s, i) => (
                <div key={i} className="border border-[#2e3454] rounded-lg p-2.5 flex flex-col gap-1.5">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-medium text-[#9da3c8] capitalize">
                      {s.field.replace('_', ' ')}
                    </span>
                    <span className="text-[9px] text-[#3d4466]">
                      {Math.round(s.confidence * 100)}% · Ch{s.chapter}
                    </span>
                  </div>
                  <p className="text-[11px] text-[#e8eaf6] leading-relaxed">
                    {s.value.length > 150 ? s.value.slice(0, 150) + '…' : s.value}
                  </p>
                  {s.evidence && (
                    <p className="text-[9px] text-[#3d4466] italic border-l-2 border-[#2e3454] pl-2">
                      &ldquo;{s.evidence.length > 120 ? s.evidence.slice(0, 120) + '…' : s.evidence}&rdquo;
                    </p>
                  )}
                  <button
                    onClick={() => applyEnrichSuggestion(s)}
                    className="self-end text-[10px] px-2.5 py-1 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 text-amber-400 transition-colors"
                  >
                    Apply
                  </button>
                </div>
              ))}
            </div>
          )}
          <div>
            <label className="text-xs text-[#5c6391] mb-1 block">Age</label>
            <input
              type="text"
              value={age}
              onChange={e => { setAge(e.target.value); scheduleProfileSave() }}
              placeholder="e.g. 28, early thirties, ageless"
              className="w-full bg-[#0d0f1a] border border-[#2e3454] rounded-xl px-3 py-2 text-xs text-[#e8eaf6] placeholder-[#3d4466] focus:outline-none focus:border-amber-500/50 transition-colors"
            />
          </div>
          <ProfileField label="Appearance"  value={appearance}  onChange={setAppearance}  rows={3} />
          <ProfileField label="Personality" value={personality} onChange={setPersonality} rows={3} />
          <ProfileField label="Goals"       value={goals}       onChange={setGoals}       rows={2} />
          <ProfileField label="Motivations" value={motivations} onChange={setMotivations} rows={2} />
          <ProfileField label="Backstory"   value={backstory}   onChange={setBackstory}   rows={4} />
          <ProfileField label="Arc Notes"   value={arcNotes}    onChange={setArcNotes}    rows={2} />
        </section>

        {/* ── OCR Notes (read-only staging area) ────────────────────────── */}
        {character.profile?.raw_notes && (
          <section>
            <button
              onClick={() => setShowRawNotes(v => !v)}
              className="w-full flex items-center justify-between text-[10px] font-semibold text-[#3d4466] uppercase tracking-wider mb-1"
            >
              <span>OCR Notes (staging)</span>
              {showRawNotes ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </button>
            {showRawNotes ? (
              <pre className="bg-[#0d0f1a] border border-[#1f2440] rounded-xl p-3 text-[11px] text-[#5c6391] whitespace-pre-wrap break-words font-mono">
                {character.profile.raw_notes}
              </pre>
            ) : (
              <p className="text-[10px] text-[#3d4466]">
                Handwritten OCR notes — promote content to structured fields above.
              </p>
            )}
          </section>
        )}

        {/* ── Story Mentions ─────────────────────────────────────────────── */}
        <section>
          <div className="flex items-center justify-between mb-1">
            <button
              onClick={handleToggleMentions}
              className="flex items-center gap-1.5 text-[10px] font-semibold text-[#3d4466] uppercase tracking-wider"
            >
              <BookOpen className="w-3 h-3" />
              Story Mentions
              {mentions !== null && (
                <span className="text-[#5c6391] normal-case font-normal">
                  ({mentions.length})
                </span>
              )}
              {showMentions ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </button>
            {showMentions && (
              <button
                onClick={loadMentions}
                disabled={loadingMentions}
                title="Refresh mentions"
                className="text-[#3d4466] hover:text-amber-400 transition-colors disabled:opacity-40"
              >
                <Loader2 className={`w-3 h-3 ${loadingMentions ? 'animate-spin text-amber-400' : ''}`} />
              </button>
            )}
          </div>
          {showMentions && (
            <div className="flex flex-col gap-2">
              {loadingMentions && mentions === null ? (
                <div className="flex justify-center py-3">
                  <Loader2 className="w-4 h-4 text-[#3d4466] animate-spin" />
                </div>
              ) : mentions && mentions.length === 0 ? (
                <div className="flex flex-col gap-1.5 py-1">
                  <p className="text-[11px] text-[#3d4466] leading-relaxed">
                    No story mentions found yet.
                  </p>
                  <p className="text-[10px] text-[#2e3454] leading-relaxed">
                    If you just added this character, mention indexing is running in the
                    background — click ↻ above in a few seconds to refresh.
                    If chapters were added before this character, use{' '}
                    <span className="text-[#5c6391]">Sync Mentions</span> from the cast menu.
                  </p>
                </div>
              ) : mentions ? (
                mentions.map(m => (
                  <div key={m.mention_id} className="border-l-2 border-[#2e3454] pl-2.5">
                    <p className="text-[9px] text-amber-400/60 mb-0.5">Chapter {m.chapter_number}</p>
                    <p className="text-[10px] text-[#5c6391] leading-relaxed">
                      {m.passage_text.length > 220
                        ? m.passage_text.slice(0, 220) + '…'
                        : m.passage_text}
                    </p>
                  </div>
                ))
              ) : null}
            </div>
          )}
        </section>

        {/* ── Arc Timeline ───────────────────────────────────────────────── */}
        <section>
          <button
            onClick={() => setShowArcTimeline(v => !v)}
            className="w-full flex items-center gap-1.5 text-[10px] font-semibold text-[#3d4466] uppercase tracking-wider mb-2"
          >
            <GitBranch className="w-3 h-3" />
            Arc Timeline
            {showArcTimeline ? <ChevronUp className="w-3 h-3 ml-auto" /> : <ChevronDown className="w-3 h-3 ml-auto" />}
          </button>
          {showArcTimeline && (
            <CharacterArcTimelinePanel
              storyId={storyId}
              characterId={character.character_id}
              characterName={character.name}
            />
          )}
        </section>

        {/* ── Voice Consistency Check ─────────────────────────────────────── */}
        <section>
          <div className="flex items-center justify-between mb-1.5">
            <button
              onClick={() => setShowVoice(v => !v)}
              className="flex items-center gap-1.5 text-[10px] font-semibold text-[#3d4466] uppercase tracking-wider"
            >
              <Wand2 className="w-3 h-3" />
              Voice Consistency
              {showVoice ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </button>
            {showVoice && (
              <button
                onClick={async () => {
                  setVoiceLoading(true)
                  setVoiceResult(null)
                  try {
                    const res = await voiceCheckApi.check(storyId, character.character_id)
                    setVoiceResult(res.data)
                  } catch (err: any) {
                    toast.error(err?.response?.data?.detail ?? 'Voice check failed')
                  } finally {
                    setVoiceLoading(false)
                  }
                }}
                disabled={voiceLoading}
                className="flex items-center gap-1 text-[9px] text-[#5c6391] hover:text-amber-400 disabled:opacity-50"
              >
                {voiceLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Wand2 className="w-3 h-3" />}
                Run Check
              </button>
            )}
          </div>
          {showVoice && (
            <div className="flex flex-col gap-2">
              {!voiceResult && !voiceLoading && (
                <p className="text-[10px] text-[#3d4466]">
                  Analyse dialogue passages to detect inconsistent voice across chapters. Click "Run Check" above.
                </p>
              )}
              {voiceLoading && (
                <div className="flex items-center gap-1.5 text-[#5c6391] text-xs">
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />Analysing passages…
                </div>
              )}
              {voiceResult && (
                <>
                  <div className="flex items-center gap-3 text-xs">
                    {voiceResult.consistency_score != null && (
                      <span className="text-[#9da3c8]">
                        Score: <span className="text-amber-400 font-medium">{Math.round(voiceResult.consistency_score * 100)}%</span>
                      </span>
                    )}
                    <span className="text-[#5c6391]">{voiceResult.dialogue_count} passages</span>
                    <span className="text-[#5c6391]">{voiceResult.inconsistent_pairs.length} inconsistencies</span>
                  </div>
                  {voiceResult.inconsistent_pairs.length === 0 ? (
                    <p className="text-[11px] text-emerald-400">Voice is consistent across all analysed passages.</p>
                  ) : (
                    voiceResult.inconsistent_pairs.map((pair, i) => (
                      <div key={i} className="bg-[#0d0f1a] border border-[#1f2440] rounded-xl p-3">
                        <div className="text-[10px] text-amber-400 mb-1.5">Ch {pair.chapter_a} vs Ch {pair.chapter_b} · {Math.round(pair.similarity_score * 100)}% similar</div>
                        <div className="grid grid-cols-2 gap-2 mb-1.5">
                          <p className="text-[11px] text-[#9da3c8] italic leading-relaxed line-clamp-3">"{pair.passage_a}"</p>
                          <p className="text-[11px] text-[#9da3c8] italic leading-relaxed line-clamp-3">"{pair.passage_b}"</p>
                        </div>
                        {pair.description && (
                          <p className="text-[10px] text-[#5c6391] leading-relaxed">{pair.description}</p>
                        )}
                      </div>
                    ))
                  )}
                </>
              )}
            </div>
          )}
        </section>

        {/* ── Relationships ──────────────────────────────────────────────── */}
        <section>
          <div className="flex items-center justify-between mb-2">
            <p className="text-[10px] font-semibold text-[#3d4466] uppercase tracking-wider">Relationships</p>
            <button
              onClick={() => setShowAddRel(v => !v)}
              className="flex items-center gap-1 text-[10px] text-[#5c6391] hover:text-amber-400 transition-colors"
            >
              <Plus className="w-3 h-3" />
              Add
            </button>
          </div>

          {showAddRel && otherChars.length === 0 && (
            <p className="text-[11px] text-[#3d4466] mb-2">Create more characters first to add relationships.</p>
          )}

          {showAddRel && otherChars.length > 0 && (
            <div className="bg-[#0d0f1a] border border-[#2e3454] rounded-xl p-3 mb-2 flex flex-col gap-2">
              <select
                value={relTarget}
                onChange={e => setRelTarget(e.target.value)}
                className="w-full bg-[#1f2440] border border-[#2e3454] rounded-lg px-2.5 py-1.5 text-xs text-[#e8eaf6] focus:outline-none focus:border-amber-500/50"
              >
                <option value="">Select character…</option>
                {otherChars.map(c => (
                  <option key={c.character_id} value={c.character_id}>{c.name}</option>
                ))}
              </select>

              <div className="grid grid-cols-2 gap-1">
                {REL_TYPES.map(t => (
                  <button
                    key={t}
                    onClick={() => setRelType(t)}
                    className={`py-1 rounded-lg border text-[10px] capitalize font-medium transition-all ${
                      relType === t
                        ? 'border-amber-500/50 bg-amber-500/10 text-amber-400'
                        : 'border-[#1f2440] text-[#5c6391] hover:border-[#2e3454]'
                    }`}
                  >
                    {t}
                  </button>
                ))}
              </div>

              <div className="grid grid-cols-4 gap-1">
                {STRENGTHS.map(s => (
                  <button
                    key={s}
                    onClick={() => setRelStrength(s)}
                    className={`py-1 rounded-lg border text-[10px] capitalize font-medium transition-all ${
                      relStrength === s
                        ? 'border-amber-500/50 bg-amber-500/10 text-amber-400'
                        : 'border-[#1f2440] text-[#5c6391] hover:border-[#2e3454]'
                    }`}
                  >
                    {s}
                  </button>
                ))}
              </div>

              <textarea
                value={relDesc}
                onChange={e => setRelDesc(e.target.value)}
                rows={2}
                placeholder="Description (optional)…"
                className="w-full bg-[#1f2440] border border-[#2e3454] rounded-lg px-2.5 py-1.5 text-xs text-[#e8eaf6] placeholder-[#3d4466] focus:outline-none focus:border-amber-500/50 resize-none"
              />

              <label className="flex items-center gap-2 text-[11px] text-[#5c6391] cursor-pointer">
                <input
                  type="checkbox"
                  checked={relMutual}
                  onChange={e => setRelMutual(e.target.checked)}
                  className="accent-amber-500"
                />
                Mark as mutual (bidirectional)
              </label>

              <div className="flex gap-1">
                <button
                  onClick={() => setShowAddRel(false)}
                  className="flex-1 py-1.5 rounded-lg border border-[#2e3454] text-xs text-[#5c6391] hover:text-[#9da3c8] transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={createRelationship}
                  disabled={savingRel || !relTarget}
                  className="flex-1 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-xs font-semibold text-black transition-colors flex items-center justify-center gap-1"
                >
                  {savingRel && <Loader2 className="w-3 h-3 animate-spin" />}
                  Save
                </button>
              </div>
            </div>
          )}

          {loadingRels ? (
            <div className="flex justify-center py-3">
              <Loader2 className="w-4 h-4 text-[#3d4466] animate-spin" />
            </div>
          ) : rels.length === 0 ? (
            <p className="text-[11px] text-[#3d4466]">No relationships yet.</p>
          ) : (
            <div className="flex flex-col gap-1.5">
              {rels.map(rel => {
                const otherId   = rel.from_character_id === character.character_id
                  ? rel.to_character_id : rel.from_character_id
                const otherChar = allChars.find(c => c.character_id === otherId)
                const isFrom    = rel.from_character_id === character.character_id
                return (
                  <div
                    key={rel.relationship_id}
                    className="flex items-start gap-2 p-2.5 bg-[#0d0f1a] border border-[#1f2440] rounded-xl"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5 mb-0.5 flex-wrap">
                        <span className={`text-[11px] font-medium capitalize ${REL_COLOR[rel.relationship_type]}`}>
                          {rel.relationship_type}
                        </span>
                        <span className="text-[10px] text-[#3d4466]">
                          {isFrom ? '→' : rel.is_mutual ? '↔' : '←'}
                        </span>
                        <span className="text-[11px] text-[#9da3c8] truncate">{otherChar?.name ?? 'Unknown'}</span>
                        <span className={`text-[10px] capitalize ${STRENGTH_COLOR[rel.strength]}`}>
                          {rel.strength}
                        </span>
                      </div>
                      {rel.description && (
                        <p className="text-[10px] text-[#3d4466] line-clamp-2">{rel.description}</p>
                      )}
                    </div>
                    <button
                      onClick={() => deleteRelationship(rel)}
                      className="text-[#3d4466] hover:text-red-400 transition-colors flex-shrink-0"
                      title="Delete relationship"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                )
              })}
            </div>
          )}
        </section>

        {/* ── Danger zone ────────────────────────────────────────────────── */}
        <section className="border-t border-[#1f2440] pt-4">
          {!confirmDelete ? (
            <button
              onClick={() => setConfirmDelete(true)}
              className="flex items-center gap-1.5 text-xs text-[#3d4466] hover:text-red-400 transition-colors"
            >
              <Trash2 className="w-3.5 h-3.5" />
              Delete character
            </button>
          ) : (
            <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-3">
              <p className="text-xs text-red-400 mb-2">
                Delete "{character.name}"? This also deletes their profile and relationships. Cannot be undone.
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => setConfirmDelete(false)}
                  className="flex-1 py-1.5 rounded-lg border border-[#2e3454] text-xs text-[#9da3c8] hover:text-[#e8eaf6] transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={deleteCharacter}
                  disabled={deleting}
                  className="flex-1 py-1.5 rounded-lg bg-red-500 hover:bg-red-600 disabled:opacity-50 text-xs font-semibold text-white transition-colors flex items-center justify-center gap-1"
                >
                  {deleting && <Loader2 className="w-3 h-3 animate-spin" />}
                  Delete
                </button>
              </div>
            </div>
          )}
        </section>

      </div>
    </div>
  )
}
