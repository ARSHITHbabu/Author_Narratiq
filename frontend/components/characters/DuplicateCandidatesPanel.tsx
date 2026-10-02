'use client'

// Stage 12 A7 (CAST-C4) — "Possible duplicates" for the Characters workspace.
//
// Detect → suggest → the AUTHOR confirms. Nothing here merges on its own: the
// author picks which character to keep, reads what will happen, and confirms
// in-page. "Not the same person" hides a pair in this browser only (no server
// state); it can come back on another device.

import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, ChevronDown, ChevronRight, Loader2, Users } from 'lucide-react'
import { toast } from 'sonner'
import { charactersApi } from '@/lib/api'
import type { Character, DuplicateCandidate } from '@/lib/types'

interface Props {
  storyId: string
  /** Reload trigger from the parent (changes whenever the cast changes). */
  refreshKey: number
  /** Called after a successful merge with the surviving character. */
  onMerged: (survivor: Character, removedId: string) => void
}

const pairKey = (p: DuplicateCandidate) =>
  [p.character_a.character_id, p.character_b.character_id].sort().join(':')

function loadDismissed(storyId: string): Set<string> {
  try {
    const raw = window.localStorage.getItem(`narratiq_dup_dismissed:${storyId}`)
    return new Set(raw ? (JSON.parse(raw) as string[]) : [])
  } catch {
    return new Set()
  }
}

function saveDismissed(storyId: string, keys: Set<string>) {
  try {
    window.localStorage.setItem(`narratiq_dup_dismissed:${storyId}`, JSON.stringify([...keys]))
  } catch {
    // storage unavailable — the pair simply reappears next time
  }
}

export default function DuplicateCandidatesPanel({ storyId, refreshKey, onMerged }: Props) {
  const [pairs, setPairs] = useState<DuplicateCandidate[]>([])
  const [dismissed, setDismissed] = useState<Set<string>>(new Set())
  const [open, setOpen] = useState(false)
  const [loadFailed, setLoadFailed] = useState(false)

  const load = useCallback(async () => {
    try {
      const res = await charactersApi.duplicateCandidates(storyId)
      setPairs(res.data as DuplicateCandidate[])
      setLoadFailed(false)
    } catch {
      setLoadFailed(true)
    }
  }, [storyId])

  useEffect(() => { setDismissed(loadDismissed(storyId)) }, [storyId])
  useEffect(() => { load() }, [load, refreshKey])

  const visible = pairs.filter(p => !dismissed.has(pairKey(p)))
  if (loadFailed || visible.length === 0) return null

  const dismiss = (p: DuplicateCandidate) => {
    const next = new Set(dismissed)
    next.add(pairKey(p))
    setDismissed(next)
    saveDismissed(storyId, next)
  }

  return (
    <div data-testid="duplicates-panel" className="border-b border-sky-500/20 bg-sky-500/5 flex-shrink-0">
      <button
        onClick={() => setOpen(o => !o)}
        aria-expanded={open}
        className="w-full px-3 py-2 flex items-center gap-1.5 text-left"
      >
        <Users className="w-3 h-3 text-sky-300 flex-shrink-0" />
        <span className="text-[10px] font-semibold text-sky-300 flex-1">
          {visible.length} possible duplicate{visible.length !== 1 ? 's' : ''} — review
        </span>
        {open ? <ChevronDown className="w-3 h-3 text-sky-300" /> : <ChevronRight className="w-3 h-3 text-sky-300" />}
      </button>
      {open && (
        <div className="px-3 pb-2 flex flex-col gap-2 max-h-80 overflow-y-auto">
          <p className="text-[10px] text-[#8e94bd]">
            These characters might be the same person. Nothing is merged unless you confirm it —
            similar names can belong to different characters.
          </p>
          {visible.map(p => (
            <PairCard key={pairKey(p)} storyId={storyId} pair={p}
              onDismiss={() => dismiss(p)}
              onMerged={(survivor, removedId) => {
                setPairs(prev => prev.filter(x =>
                  x.character_a.character_id !== removedId && x.character_b.character_id !== removedId))
                onMerged(survivor, removedId)
              }} />
          ))}
        </div>
      )}
    </div>
  )
}

function PairCard({ storyId, pair, onDismiss, onMerged }: {
  storyId: string
  pair: DuplicateCandidate
  onDismiss: () => void
  onMerged: (survivor: Character, removedId: string) => void
}) {
  const a = pair.character_a, b = pair.character_b
  const [keepId, setKeepId] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const keep = keepId === a.character_id ? a : keepId === b.character_id ? b : null
  const drop = keep ? (keep === a ? b : a) : null

  const merge = async () => {
    if (!keep || !drop) return
    setBusy(true)
    setError(null)
    try {
      const res = await charactersApi.merge(storyId, keep.character_id, drop.character_id)
      const survivor = (res.data as { survivor: Character }).survivor
      toast.success(`Merged “${drop.name}” into “${keep.name}”`)
      onMerged(survivor, drop.character_id)
    } catch {
      setError('The merge did not happen — both characters are unchanged. Please try again.')
      setBusy(false)
      setConfirming(false)
    }
  }

  return (
    <div data-testid="duplicate-pair" className="border border-[#2e3454] rounded-lg p-2 bg-[#0d0f1a]">
      <p className="text-xs text-[#e8eaf6]">
        <span className="font-medium">{a.name}</span>
        <span className="text-[#8a90ba]"> and </span>
        <span className="font-medium">{b.name}</span>
      </p>
      <ul className="mt-1 flex flex-col gap-0.5">
        {pair.reasons.map((r, i) => (
          <li key={i} className="text-[10px] text-[#9da3c8]">{r.text}</li>
        ))}
      </ul>

      {!confirming && (
        <div className="mt-2 flex flex-col gap-1.5">
          <fieldset className="flex flex-wrap gap-2 text-[10px] text-[#cdd2f0]">
            <legend className="sr-only">Which character should be kept?</legend>
            {[a, b].map(c => (
              <label key={c.character_id} className="flex items-center gap-1 cursor-pointer">
                <input type="radio" name={`keep-${a.character_id}-${b.character_id}`}
                  checked={keepId === c.character_id} onChange={() => setKeepId(c.character_id)} />
                Keep “{c.name}”
              </label>
            ))}
          </fieldset>
          <div className="flex gap-2">
            <button data-testid="duplicate-merge" disabled={!keep}
              onClick={() => setConfirming(true)}
              className="text-[10px] px-2 py-1 rounded border border-sky-500/40 text-sky-300 hover:bg-sky-500/10 disabled:opacity-40 disabled:cursor-not-allowed">
              Merge…
            </button>
            <button data-testid="duplicate-dismiss" onClick={onDismiss}
              className="text-[10px] px-2 py-1 rounded border border-[#2e3454] text-[#8e94bd] hover:text-[#cdd2f0]">
              Not the same person
            </button>
          </div>
        </div>
      )}

      {confirming && keep && drop && (
        <div data-testid="duplicate-confirm" role="alertdialog" aria-label="Confirm merge"
          className="mt-2 border border-amber-500/30 bg-amber-500/5 rounded p-2">
          <p className="text-[10px] text-amber-200 flex gap-1">
            <AlertTriangle className="w-3 h-3 flex-shrink-0 mt-0.5" />
            <span>
              “{drop.name}” will be merged into “{keep.name}”. Its profile details, relationships and story
              mentions move to “{keep.name}”, and “{drop.name}” is kept as an alias. This cannot be undone.
            </span>
          </p>
          <div className="mt-2 flex gap-2">
            <button data-testid="duplicate-confirm-merge" onClick={merge} disabled={busy}
              className="text-[10px] px-2 py-1 rounded bg-amber-500 hover:bg-amber-600 text-black font-semibold disabled:opacity-50 flex items-center gap-1">
              {busy && <Loader2 className="w-3 h-3 animate-spin" />}
              Merge characters
            </button>
            <button onClick={() => setConfirming(false)} disabled={busy}
              className="text-[10px] px-2 py-1 rounded border border-[#2e3454] text-[#8e94bd]">
              Cancel
            </button>
          </div>
        </div>
      )}
      {error && <p role="alert" className="mt-1 text-[10px] text-red-300">{error}</p>}
    </div>
  )
}
