'use client'

import { useState, useEffect } from 'react'
import {
  X, Sparkles, Loader2, Users, AlertCircle,
  ChevronDown, ChevronRight, CheckCircle2,
} from 'lucide-react'
import { charactersApi } from '@/lib/api'
import { CastSuggestion, CastGenerationResult, CastConfirmResult, Character } from '@/lib/types'
import { toast } from 'sonner'

interface Props {
  storyId:     string
  onClose:     () => void
  onConfirmed: (characters: Character[], mentionsIndexing: boolean) => void
}

const ROLE_COLORS: Record<string, string> = {
  protagonist: 'text-amber-400 border-amber-500/40 bg-amber-500/10',
  antagonist:  'text-red-400   border-red-500/40   bg-red-500/10',
  supporting:  'text-blue-400  border-blue-500/40  bg-blue-500/10',
  minor:       'text-[#5c6391] border-[#2e3454]    bg-transparent',
}

// Rich profile fields the model may extract. Rendered dynamically — only fields
// the model actually populated are shown (no empty placeholders, no fakes).
const DETAIL_FIELDS: { key: keyof CastSuggestion; label: string }[] = [
  { key: 'age',         label: 'Age' },
  { key: 'appearance',  label: 'Appearance' },
  { key: 'personality', label: 'Personality' },
  { key: 'goals',       label: 'Goals' },
  { key: 'motivations', label: 'Motivations' },
  { key: 'backstory',   label: 'Backstory' },
  { key: 'arc_notes',   label: 'Arc notes' },
  { key: 'traits',      label: 'Traits' },
]

function hasDetail(s: CastSuggestion): boolean {
  return DETAIL_FIELDS.some(({ key }) => {
    const v = (s as any)[key]
    return Array.isArray(v) ? v.length > 0 : Boolean(v)
  })
}

export default function CastGenerationModal({ storyId, onClose, onConfirmed }: Props) {
  const [phase,    setPhase]    = useState<'loading' | 'review' | 'confirming' | 'error'>('loading')
  const [result,   setResult]   = useState<CastGenerationResult | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [error,    setError]    = useState('')

  useEffect(() => {
    let cancelled = false
    const run = async () => {
      try {
        const res = await charactersApi.generateCast(storyId)
        if (cancelled) return
        const data = res.data as CastGenerationResult
        setResult(data)
        // Pre-select all new (non-existing) suggestions
        setSelected(new Set(
          data.suggestions.filter(s => !s.already_exists).map(s => s.name)
        ))
        setPhase('review')
      } catch (err: any) {
        if (cancelled) return
        setError(err?.response?.data?.detail || 'Failed to analyse story chapters.')
        setPhase('error')
      }
    }
    run()
    return () => { cancelled = true }
  }, [storyId])

  const toggle = (name: string) => setSelected(prev => {
    const next = new Set(prev)
    next.has(name) ? next.delete(name) : next.add(name)
    return next
  })

  const toggleExpand = (name: string) => setExpanded(prev => {
    const next = new Set(prev)
    next.has(name) ? next.delete(name) : next.add(name)
    return next
  })

  const handleConfirm = async () => {
    if (!result || selected.size === 0) return
    setPhase('confirming')
    const toSave = result.suggestions
      .filter(s => !s.already_exists && selected.has(s.name))
      .map(s => ({
        name:             s.name,
        role:             s.role,
        status:           s.status,
        description:      s.description,
        aliases:          s.aliases,
        evidence_snippet: s.evidence_snippet,
        age:              s.age ?? '',
        appearance:       s.appearance ?? '',
        personality:      s.personality ?? '',
        goals:            s.goals ?? '',
        motivations:      s.motivations ?? '',
        backstory:        s.backstory ?? '',
        arc_notes:        s.arc_notes ?? '',
        traits:           s.traits ?? [],
      }))
    try {
      const res = await charactersApi.confirmCast(storyId, toSave)
      const data = res.data as CastConfirmResult
      const n = data.created.length
      toast.success(
        `Added ${n} character${n !== 1 ? 's' : ''} — indexing story mentions in background`
      )
      onConfirmed(data.created, true)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to add characters')
      setPhase('review')
    }
  }

  const newSuggestions      = result?.suggestions.filter(s => !s.already_exists) ?? []
  const existingSuggestions = result?.suggestions.filter(s =>  s.already_exists) ?? []
  const selectedCount       = [...selected].filter(n =>
    newSuggestions.some(s => s.name === n)
  ).length

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-[#0d0f1a] border border-[#1f2440] rounded-2xl w-full max-w-lg max-h-[85vh] flex flex-col shadow-2xl">

        {/* Header */}
        <div className="flex items-center gap-2.5 px-5 py-4 border-b border-[#1f2440] flex-shrink-0">
          <Sparkles className="w-4 h-4 text-amber-400" />
          <span className="text-sm font-semibold text-[#e8eaf6] flex-1">Generate Cast from Story</span>
          <button onClick={onClose} className="text-[#3d4466] hover:text-[#9da3c8] transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto">

          {/* Loading */}
          {phase === 'loading' && (
            <div className="flex flex-col items-center justify-center py-16 gap-3">
              <Loader2 className="w-6 h-6 text-amber-400 animate-spin" />
              <p className="text-xs text-[#5c6391]">Scanning chapters for characters…</p>
            </div>
          )}

          {/* Confirming */}
          {phase === 'confirming' && (
            <div className="flex flex-col items-center justify-center py-16 gap-3">
              <Loader2 className="w-6 h-6 text-amber-400 animate-spin" />
              <p className="text-xs text-[#5c6391]">Adding characters to cast…</p>
            </div>
          )}

          {/* Error */}
          {phase === 'error' && (
            <div className="flex flex-col items-center justify-center py-12 gap-3 px-6">
              <AlertCircle className="w-8 h-8 text-red-400" />
              <p className="text-xs text-red-400 text-center">{error}</p>
              <button
                onClick={onClose}
                className="text-xs px-3 py-1.5 rounded-lg border border-[#2e3454] text-[#9da3c8] hover:border-[#3d4466] transition-colors"
              >
                Close
              </button>
            </div>
          )}

          {/* Review */}
          {phase === 'review' && result && (
            <div className="p-4 flex flex-col gap-4">

              {/* Summary bar */}
              <div className="flex items-center gap-2 text-[10px] text-[#5c6391]">
                <Users className="w-3 h-3" />
                <span>
                  Found <span className="text-[#9da3c8]">{result.suggestions.length}</span> characters
                  across <span className="text-[#9da3c8]">{result.chapters_scanned}</span> chapter{result.chapters_scanned !== 1 ? 's' : ''}
                  {result.existing_count > 0 && (
                    <> · <span className="text-[#9da3c8]">{result.existing_count}</span> already in cast</>
                  )}
                </span>
              </div>

              {/* No new characters */}
              {newSuggestions.length === 0 && (
                <div className="flex flex-col items-center gap-2 py-6">
                  <CheckCircle2 className="w-6 h-6 text-green-400" />
                  <p className="text-xs text-[#5c6391] text-center">
                    All detected characters are already in your cast.
                  </p>
                </div>
              )}

              {/* New suggestions */}
              {newSuggestions.length > 0 && (
                <div className="flex flex-col gap-1.5">
                  <p className="text-[10px] font-semibold text-[#5c6391] uppercase tracking-wider">
                    New characters ({newSuggestions.length})
                  </p>
                  {newSuggestions.map(s => (
                    <SuggestionRow
                      key={s.name}
                      suggestion={s}
                      checked={selected.has(s.name)}
                      expanded={expanded.has(s.name)}
                      onToggle={() => toggle(s.name)}
                      onExpand={() => toggleExpand(s.name)}
                    />
                  ))}
                </div>
              )}

              {/* Already in cast */}
              {existingSuggestions.length > 0 && (
                <div className="flex flex-col gap-1.5">
                  <p className="text-[10px] font-semibold text-[#3d4466] uppercase tracking-wider">
                    Already in cast ({existingSuggestions.length})
                  </p>
                  {existingSuggestions.map(s => (
                    <SuggestionRow
                      key={s.name}
                      suggestion={s}
                      checked={false}
                      expanded={expanded.has(s.name)}
                      onToggle={() => {}}
                      onExpand={() => toggleExpand(s.name)}
                      disabled
                    />
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        {phase === 'review' && result && (
          <div className="flex items-center justify-between gap-3 px-5 py-4 border-t border-[#1f2440] flex-shrink-0">
            <button
              onClick={onClose}
              className="text-xs px-3 py-1.5 rounded-lg border border-[#2e3454] text-[#5c6391] hover:text-[#9da3c8] hover:border-[#3d4466] transition-all"
            >
              Cancel
            </button>
            <div className="flex items-center gap-2">
              {newSuggestions.length > 0 && (
                <button
                  onClick={() => setSelected(
                    selected.size === newSuggestions.length
                      ? new Set()
                      : new Set(newSuggestions.map(s => s.name))
                  )}
                  className="text-[10px] text-[#5c6391] hover:text-[#9da3c8] transition-colors"
                >
                  {selected.size === newSuggestions.length ? 'Deselect all' : 'Select all'}
                </button>
              )}
              <button
                onClick={handleConfirm}
                disabled={selectedCount === 0}
                className="text-xs px-4 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-600 disabled:opacity-40 disabled:cursor-not-allowed text-black font-semibold transition-colors"
              >
                {selectedCount === 0
                  ? 'Add Characters'
                  : `Add ${selectedCount} Character${selectedCount !== 1 ? 's' : ''}`}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Suggestion row ─────────────────────────────────────────────────────────────

interface RowProps {
  suggestion: CastSuggestion
  checked:    boolean
  expanded:   boolean
  disabled?:  boolean
  onToggle:   () => void
  onExpand:   () => void
}

function SuggestionRow({ suggestion: s, checked, expanded, disabled, onToggle, onExpand }: RowProps) {
  const roleColor = ROLE_COLORS[s.role] ?? ROLE_COLORS.minor

  return (
    <div
      className={`border rounded-xl transition-all ${
        disabled
          ? 'border-[#1a1d2e] opacity-50'
          : checked
            ? 'border-amber-500/30 bg-amber-500/5'
            : 'border-[#1f2440] hover:border-[#2e3454]'
      }`}
    >
      {/* Main row */}
      <div className="flex items-start gap-2.5 p-3">
        {/* Checkbox */}
        <button
          onClick={disabled ? undefined : onToggle}
          disabled={disabled}
          className={`mt-0.5 flex-shrink-0 w-3.5 h-3.5 rounded border transition-all ${
            disabled
              ? 'border-[#2e3454] bg-transparent cursor-default'
              : checked
                ? 'border-amber-500 bg-amber-500'
                : 'border-[#3d4466] hover:border-amber-500/60'
          }`}
        >
          {checked && !disabled && (
            <svg viewBox="0 0 14 14" className="w-full h-full text-black">
              <path d="M2 7l4 4 6-6" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          )}
        </button>

        {/* Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-xs font-medium text-[#e8eaf6]">{s.name}</span>
            <span className={`text-[9px] px-1.5 py-0.5 rounded-full border capitalize ${roleColor}`}>
              {s.role}
            </span>
            {s.confidence === 'uncertain' && (
              <span className="text-[9px] px-1.5 py-0.5 rounded-full border border-yellow-500/30 bg-yellow-500/10 text-yellow-400">
                uncertain
              </span>
            )}
          </div>
          {s.description && (
            <p className="text-[10px] text-[#5c6391] mt-0.5 leading-relaxed line-clamp-2">
              {s.description}
            </p>
          )}
          {s.aliases.length > 0 && (
            <p className="text-[9px] text-[#3d4466] mt-0.5">
              Also: {s.aliases.join(', ')}
            </p>
          )}
        </div>

        {/* Expand toggle (evidence + extracted detail) */}
        {(s.evidence_snippet || hasDetail(s)) && (
          <button
            onClick={onExpand}
            className="flex-shrink-0 text-[#3d4466] hover:text-[#5c6391] transition-colors mt-0.5"
            title="Show extracted detail"
          >
            {expanded
              ? <ChevronDown className="w-3 h-3" />
              : <ChevronRight className="w-3 h-3" />}
          </button>
        )}
      </div>

      {/* Extracted detail + evidence */}
      {expanded && (s.evidence_snippet || hasDetail(s)) && (
        <div className="px-3 pb-3 pt-0 flex flex-col gap-2">
          {/* Extracted profile fields — only render what the model actually found */}
          {hasDetail(s) && (
            <div className="grid grid-cols-1 gap-1">
              {DETAIL_FIELDS.map(({ key, label }) => {
                const val = (s as any)[key]
                const text = Array.isArray(val) ? val.join(', ') : (val || '')
                if (!text) return null
                return (
                  <div key={key} className="flex gap-1.5 text-[9px] leading-relaxed">
                    <span className="text-[#3d4466] flex-shrink-0 w-20">{label}</span>
                    <span className="text-[#9da3c8]">{text}</span>
                  </div>
                )
              })}
            </div>
          )}

          {s.evidence_snippet && (
            <div className="border-l-2 border-[#2e3454] pl-2.5">
              <p className="text-[9px] text-[#5c6391] leading-relaxed italic">
                &ldquo;{s.evidence_snippet}&rdquo;
              </p>
              {s.first_appearance && (
                <p className="text-[9px] text-[#3d4466] mt-0.5">
                  First appears: {s.first_appearance}
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
