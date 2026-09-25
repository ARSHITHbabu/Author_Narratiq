'use client'

// Versions — the author's pinned generations for this story (Phase 3 P3-01),
// shown as a lineage tree (P3-06), with every pin action in one place:
// insert · compare · use as context (P3-03) · avoid ideas like this (P3-07) ·
// generate from this (P3-06) · send to the Idea Shelf (P3-09) · rename ·
// favourite · extend (plan-gated) · delete.
//
// Pins are temporary by contract; the expiry is always visible and warned
// about before it happens. Nothing here is automatic — every change to a pin
// is an explicit author action.

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Pin as PinIcon, Star, Trash2, ArrowDownToLine, Columns2, Layers, Ban, GitBranch, Lightbulb,
  Loader2, RefreshCw, Pencil, Clock, ChevronDown, ChevronRight,
} from 'lucide-react'
import { toast } from 'sonner'
import { generationApi, pinsApi } from '@/lib/api'
import {
  CONTROLLABLE_GROUPS, DERIVATIONS, IDEA_TYPES, TOOL_LABELS, apiErrorText, buildControls, expiryLabel,
} from '@/lib/generationControls'
import { useGenerationStore } from '@/lib/generationStore'
import { runTransform, type GroupId, type TransformResult } from '@/lib/transforms'
import { useStoryContext } from '@/components/studio/StoryContextEngine'
import GenerationWarnings from './GenerationWarnings'
import PinActions from './PinActions'
import type { DerivationIntent, Pin, PlanLimitsOut } from '@/lib/types'

type Status = 'loading' | 'ready' | 'error'

function toolValue(pin: Pin): string {
  const p = pin.tool_params as Record<string, string>
  return p.tone ?? p.emotion ?? p.target_age ?? p.style ?? ''
}

export default function VersionsPanel({ selectedText }: { selectedText?: string }) {
  const { storyId, activeChapterId, editor } = useStoryContext()
  const gen = useGenerationStore()
  const [pins, setPins] = useState<Pin[]>([])
  const [status, setStatus] = useState<Status>('loading')
  const [limits, setLimits] = useState<PlanLimitsOut | null>(null)
  const [open, setOpen] = useState<string | null>(null)
  const [full, setFull] = useState<Record<string, string>>({})
  const [comparePick, setComparePick] = useState<Pin | null>(null)

  const load = useCallback(async () => {
    setStatus((s) => (s === 'ready' ? s : 'loading'))
    try {
      const [p, l] = await Promise.all([pinsApi.list(storyId, { limit: 200 }), generationApi.limits(storyId)])
      setPins(p.data.pins)
      setLimits(l.data)
      gen.setHistoryMax(l.data.session_history_max)
      setStatus('ready')
    } catch {
      setStatus('error')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storyId])

  useEffect(() => { load() }, [load, gen.pinsVersion])

  // Keep context/avoid selections honest: a pin that has gone is deselected.
  useEffect(() => {
    if (status !== 'ready') return
    const live = new Set(pins.map((p) => p.pin_id))
    gen.contextPinIds.filter((id) => !live.has(id)).forEach((id) => gen.toggleContextPin(id, 99))
    gen.avoidPinIds.filter((id) => !live.has(id)).forEach((id) => gen.toggleAvoidPin(id))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pins, status])

  // Lineage tree: roots newest first, children under their root by depth.
  const tree = useMemo(() => {
    const byRoot = new Map<string, Pin[]>()
    for (const p of pins) {
      const root = p.root_pin_id ?? p.pin_id
      byRoot.set(root, [...(byRoot.get(root) ?? []), p])
    }
    const groups = [...byRoot.values()].map((g) => g.sort((a, b) => a.lineage_depth - b.lineage_depth || a.created_at.localeCompare(b.created_at)))
    return groups.sort((a, b) => b[b.length - 1].created_at.localeCompare(a[a.length - 1].created_at))
  }, [pins])
  const live = new Set(pins.map((p) => p.pin_id))

  const content = async (pin: Pin): Promise<string> => {
    if (full[pin.pin_id]) return full[pin.pin_id]
    const r = await pinsApi.get(storyId, pin.pin_id)
    setFull((f) => ({ ...f, [pin.pin_id]: r.data.content }))
    return r.data.content
  }

  const act = async (fn: () => Promise<unknown>, ok: string, fail: string) => {
    try { await fn(); toast.success(ok); gen.pinsChanged() } catch (e) { toast.error(apiErrorText(e, fail)) }
  }

  const maxContext = limits?.limits.max_context_pins ?? 2

  if (status === 'loading') {
    return <div className="flex justify-center py-8"><Loader2 className="w-4 h-4 animate-spin text-[#5c6391]" /></div>
  }
  if (status === 'error') {
    return (
      <div data-testid="versions-error" className="rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-xs text-[#e8eaf6]">
        Your pinned versions could not be loaded. Nothing has been lost.
        <button onClick={load} className="mt-2 flex items-center gap-1 text-[11px] px-2 py-1 rounded border border-[#2e3454] hover:bg-[#1f2440]">
          <RefreshCw className="w-3 h-3" /> Try again
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-3" data-testid="versions-panel">
      <div className="flex items-center justify-between text-[11px]">
        <span className="text-[#9da3c8]">
          <PinIcon className="inline w-3 h-3 mr-1 text-amber-400" />
          {limits ? `${limits.usage.pins} of ${limits.limits.max_pins} pins · ${limits.plan} plan · kept ${limits.limits.pin_ttl_days} days` : `${pins.length} pins`}
        </span>
        <button onClick={load} title="Refresh" className="p-1 rounded text-[#5c6391] hover:text-[#9da3c8]"><RefreshCw className="w-3 h-3" /></button>
      </div>

      {(gen.contextPinIds.length > 0 || gen.avoidPinIds.length > 0) && (
        <div data-testid="context-pin-bar" className="rounded-lg border border-sky-500/30 bg-sky-500/10 px-2.5 py-1.5 text-[11px] text-sky-200 flex items-center gap-2">
          <Layers className="w-3 h-3" />
          <span className="flex-1">
            {gen.contextPinIds.length > 0 && `Using ${gen.contextPinIds.length} of ${maxContext} pinned version${gen.contextPinIds.length === 1 ? '' : 's'} as context`}
            {gen.contextPinIds.length > 0 && gen.avoidPinIds.length > 0 && ' · '}
            {gen.avoidPinIds.length > 0 && `avoiding ideas like ${gen.avoidPinIds.length}`}
            {' — applies to your next Tone, Emotion, Audience or Style run.'}
          </span>
          <button onClick={gen.clearSelections} className="underline">Clear</button>
        </div>
      )}

      {comparePick && (
        <p className="text-[11px] text-amber-300">Choose a second version to compare with “{comparePick.label || comparePick.preview.slice(0, 30)}”, or <button className="underline" onClick={() => setComparePick(null)}>cancel</button>.</p>
      )}

      {tree.length === 0 ? (
        <p data-testid="versions-empty" className="text-xs text-[#5c6391] leading-relaxed py-4 text-center">
          No pinned versions yet. When an AI result is worth keeping, press <strong>Pin</strong> on it — pinned versions
          appear here for {limits?.limits.pin_ttl_days ?? 7} days.
        </p>
      ) : tree.map((group) => (
        <div key={group[0].root_pin_id ?? group[0].pin_id} className="space-y-1">
          {group.map((pin) => {
            const exp = expiryLabel(pin.expires_at)
            const isOpen = open === pin.pin_id
            const inContext = gen.contextPinIds.includes(pin.pin_id)
            const avoiding = gen.avoidPinIds.includes(pin.pin_id)
            const orphan = pin.lineage_depth > 0 && pin.parent_pin_id && !live.has(pin.parent_pin_id)
            return (
              <div key={pin.pin_id} data-testid="pin-card" style={{ marginLeft: Math.min(pin.lineage_depth, 6) * 12 }}
                className={`rounded-lg border ${inContext ? 'border-sky-500/40' : 'border-[#1f2440]'} bg-[#0d0f1a]`}>
                <button type="button" onClick={() => { setOpen(isOpen ? null : pin.pin_id); if (!isOpen) content(pin).catch(() => {}) }}
                  aria-expanded={isOpen}
                  className="w-full text-left px-2.5 py-2 flex items-start gap-1.5">
                  {isOpen ? <ChevronDown className="w-3 h-3 mt-0.5 text-[#5c6391]" /> : <ChevronRight className="w-3 h-3 mt-0.5 text-[#5c6391]" />}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5 text-[10px] flex-wrap">
                      {pin.is_favourite && <Star className="w-3 h-3 text-amber-400 fill-amber-400" aria-label="Favourite" />}
                      <span className="font-medium text-[#e8eaf6]">{pin.label || TOOL_LABELS[pin.tool] || pin.tool}</span>
                      <span className="text-[#5c6391]">{TOOL_LABELS[pin.tool] ?? pin.tool}{toolValue(pin) ? ` · ${toolValue(pin)}` : ''} · {pin.word_count} words</span>
                      <span className={`ml-auto flex items-center gap-0.5 ${exp.soon ? 'text-amber-300' : 'text-[#5c6391]'}`}><Clock className="w-2.5 h-2.5" />{exp.text}</span>
                    </div>
                    {pin.lineage_depth > 0 && (
                      <p className="text-[10px] text-[#5c6391]">↳ {orphan ? 'from a version that has expired' : `${pin.derivation || 'derived'} of an earlier version`}</p>
                    )}
                    {!isOpen && <p className="text-[11px] text-[#9da3c8] line-clamp-2 font-serif mt-0.5">{pin.preview}</p>}
                  </div>
                </button>
                {isOpen && (
                  <PinDetail pin={pin} text={full[pin.pin_id]} storyId={storyId} canExtend={!!limits?.limits.can_extend_ttl}
                    inContext={inContext} avoiding={avoiding} maxContext={maxContext}
                    comparePick={comparePick} selectedText={selectedText}
                    onCompare={async () => {
                      // Explicit two-step pick: first press chooses A, the next pin's
                      // "Compare with this" chooses B. Never guessed from the selection.
                      if (comparePick && comparePick.pin_id !== pin.pin_id) {
                        const [a, b] = await Promise.all([content(comparePick), content(pin)])
                        gen.openCompare({ label: comparePick.label || 'Version A', text: a, pinId: comparePick.pin_id },
                                        { label: pin.label || 'Version B', text: b, pinId: pin.pin_id })
                        setComparePick(null)
                      } else {
                        setComparePick(comparePick?.pin_id === pin.pin_id ? null : pin)
                      }
                    }}
                    onCompareSelection={async () => {
                      if (!selectedText?.trim()) return
                      gen.openCompare({ label: 'Your selected text', text: selectedText }, { label: pin.label || 'Pinned version', text: await content(pin), pinId: pin.pin_id })
                    }}
                    onInsert={async () => {
                      if (!editor) { toast.error('Open a chapter in the editor first.'); return }
                      editor.insertText(await content(pin))
                      pinsApi.applied(storyId, pin.pin_id).catch(() => {})
                      toast.success(selectedText?.trim() ? 'Replaced your selection with this version' : 'Inserted at the cursor')
                    }}
                    onToggleContext={() => {
                      if (!gen.toggleContextPin(pin.pin_id, maxContext)) toast.info(`Your ${limits?.plan ?? ''} plan can use up to ${maxContext} pinned versions as context.`)
                    }}
                    onToggleAvoid={() => gen.toggleAvoidPin(pin.pin_id)}
                    act={act}
                    chapterId={activeChapterId}
                  />
                )}
              </div>
            )
          })}
        </div>
      ))}
    </div>
  )
}

function PinDetail(props: {
  pin: Pin; text?: string; storyId: string; canExtend: boolean; inContext: boolean; avoiding: boolean
  maxContext: number; comparePick: Pin | null; selectedText?: string; chapterId: string | null
  onCompare: () => void; onCompareSelection: () => void; onInsert: () => void; onToggleContext: () => void; onToggleAvoid: () => void
  act: (fn: () => Promise<unknown>, ok: string, fail: string) => Promise<void>
}) {
  const { pin, text, storyId, act } = props
  const [renaming, setRenaming] = useState(false)
  const [label, setLabel] = useState(pin.label)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deriving, setDeriving] = useState<DerivationIntent | null>(null)
  const [param, setParam] = useState('')
  const [busy, setBusy] = useState(false)
  const [derived, setDerived] = useState<TransformResult | null>(null)
  const [derivedIntent, setDerivedIntent] = useState<DerivationIntent>('variation')
  const [promoteType, setPromoteType] = useState<string | null>(null)
  const controllable = CONTROLLABLE_GROUPS.includes(pin.tool as GroupId)

  const runDerivation = async (intent: DerivationIntent) => {
    const need = DERIVATIONS.find((d) => d.id === intent)?.needs
    if (need && !param.trim()) { toast.info(`${need} is needed for this option.`); return }
    setBusy(true); setDerived(null)
    try {
      const r = await runTransform(pin.tool as GroupId, toolValue(pin) || 'neutral', pin.source_excerpt || pin.preview, {
        storyId, chapterId: pin.chapter_id ?? props.chapterId ?? undefined,
        intensity: (pin.tool_params as Record<string, string>).intensity,
        controls: buildControls({ basePinId: pin.pin_id, derivation: intent, derivationParam: param }),
      })
      if (r.failed) toast.error(r.reason ?? 'That could not be generated safely. Your pinned version is unchanged.')
      else { setDerived(r); setDerivedIntent(intent) }
      setDeriving(null); setParam('')
    } catch (e) {
      toast.error(apiErrorText(e, 'The AI could not generate a new version. Your pinned version is unchanged.'))
    } finally {
      setBusy(false)
    }
  }

  const b = 'inline-flex items-center gap-1 text-[10px] px-1.5 py-1 rounded border border-[#2e3454] text-[#cdd2f0] hover:bg-[#1f2440] disabled:opacity-40'
  return (
    <div className="px-2.5 pb-2.5 space-y-2">
      <p className="text-xs text-[#cdd2f0] font-serif whitespace-pre-wrap max-h-48 overflow-y-auto">{text ?? pin.preview}</p>
      {pin.source_excerpt && <p className="text-[10px] text-[#5c6391] italic line-clamp-2">From: “{pin.source_excerpt}”</p>}
      <div className="flex flex-wrap gap-1">
        <button className={b} onClick={props.onInsert} title={props.selectedText?.trim() ? 'Replace the selected text with this version' : 'Insert at the cursor'}>
          <ArrowDownToLine className="w-3 h-3" /> {props.selectedText?.trim() ? 'Replace selection' : 'Insert'}
        </button>
        <button className={b} onClick={props.onCompare} aria-pressed={props.comparePick?.pin_id === pin.pin_id}>
          <Columns2 className="w-3 h-3" /> {props.comparePick && props.comparePick.pin_id !== pin.pin_id ? 'Compare with this' : props.comparePick?.pin_id === pin.pin_id ? 'Cancel compare' : 'Compare with another version'}
        </button>
        {props.selectedText?.trim() && (
          <button className={b} onClick={props.onCompareSelection} title="Compare this version with the text selected in your chapter">
            <Columns2 className="w-3 h-3" /> Compare with selection
          </button>
        )}
        <button className={`${b} ${props.inContext ? 'border-sky-500/50 text-sky-300' : ''}`} aria-pressed={props.inContext}
          onClick={props.onToggleContext} disabled={!controllable && !props.inContext}
          title="Give this version to the AI as material for your next Tone / Emotion / Audience / Style run">
          <Layers className="w-3 h-3" /> Use as context
        </button>
        <button className={`${b} ${props.avoiding ? 'border-rose-500/50 text-rose-300' : ''}`} aria-pressed={props.avoiding}
          onClick={props.onToggleAvoid} title="Ask the AI for something materially different from this idea (this session only)">
          <Ban className="w-3 h-3" /> Avoid ideas like this
        </button>
        <button className={b} onClick={() => setDeriving(deriving ? null : 'variation')} disabled={!controllable}
          title={controllable ? 'Generate a new version starting from this one' : 'Generating from a version is available for Tone, Emotion, Audience and Style results'}>
          <GitBranch className="w-3 h-3" /> Generate from this
        </button>
        <button className={b} onClick={() => setPromoteType(promoteType ? null : 'future_scene')}><Lightbulb className="w-3 h-3" /> Idea Shelf</button>
        <button className={b} onClick={() => setRenaming(true)}><Pencil className="w-3 h-3" /> Rename</button>
        <button className={b} onClick={() => act(() => pinsApi.update(storyId, pin.pin_id, { is_favourite: !pin.is_favourite }), pin.is_favourite ? 'Removed from favourites' : 'Marked as favourite', 'Could not update this pin.')}>
          <Star className="w-3 h-3" /> {pin.is_favourite ? 'Unfavourite' : 'Favourite'}
        </button>
        {props.canExtend && (
          <button className={b} onClick={() => act(() => pinsApi.update(storyId, pin.pin_id, { extend_ttl: true }), 'Kept for longer', 'Could not extend this pin.')}>
            <Clock className="w-3 h-3" /> Keep longer
          </button>
        )}
        <button className={`${b} text-red-300`} onClick={() => setConfirmDelete(true)}><Trash2 className="w-3 h-3" /> Delete</button>
      </div>

      {renaming && (
        <form onSubmit={(e) => { e.preventDefault(); setRenaming(false); act(() => pinsApi.update(storyId, pin.pin_id, { label }), 'Renamed', 'Could not rename this pin.') }}
          className="flex gap-1">
          <input autoFocus value={label} onChange={(e) => setLabel(e.target.value)} maxLength={80} aria-label="Pin name"
            className="flex-1 bg-[#13162a] border border-[#2e3454] rounded px-2 py-1 text-[11px] text-[#e8eaf6]" />
          <button className={b} type="submit">Save</button>
        </form>
      )}
      {confirmDelete && (
        <div role="alertdialog" aria-label="Delete this pinned version" className="flex items-center gap-2 text-[11px] text-red-200 bg-red-500/10 border border-red-500/30 rounded px-2 py-1.5">
          <span className="flex-1">Delete this pinned version now? This cannot be undone.</span>
          <button className={b} onClick={() => act(() => pinsApi.remove(storyId, pin.pin_id), 'Pinned version deleted', 'Could not delete this pin.')}>Delete</button>
          <button className={b} onClick={() => setConfirmDelete(false)}>Keep</button>
        </div>
      )}
      {promoteType && (
        <div className="flex items-center gap-1 text-[11px]">
          <select value={promoteType} onChange={(e) => setPromoteType(e.target.value)} aria-label="Idea type"
            className="flex-1 bg-[#13162a] border border-[#2e3454] rounded px-1.5 py-1 text-[#e8eaf6]">
            {IDEA_TYPES.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
          </select>
          <button className={b} onClick={() => act(() => pinsApi.promote(storyId, pin.pin_id, { card_type: promoteType, release_pin: true }),
            'Saved to the Idea Shelf (kept permanently)', 'Could not save this idea.')}>Save as idea</button>
        </div>
      )}
      {deriving && (
        <div className="rounded border border-[#2e3454] p-2 space-y-1.5">
          <div className="grid grid-cols-2 gap-1">
            {DERIVATIONS.map((d) => (
              <button key={d.id} type="button" onClick={() => setDeriving(d.id)} aria-pressed={deriving === d.id}
                title={d.hint} className={`text-[10px] text-left px-1.5 py-1 rounded border ${deriving === d.id ? 'border-amber-500/50 text-amber-300 bg-amber-500/10' : 'border-[#2e3454] text-[#9da3c8]'}`}>
                {d.label}
              </button>
            ))}
          </div>
          {DERIVATIONS.find((d) => d.id === deriving)?.needs && (
            <input value={param} onChange={(e) => setParam(e.target.value)} maxLength={300}
              placeholder={DERIVATIONS.find((d) => d.id === deriving)?.needs} aria-label="Instruction for this option"
              className="w-full bg-[#13162a] border border-[#2e3454] rounded px-2 py-1 text-[11px] text-[#e8eaf6]" />
          )}
          <button type="button" onClick={() => runDerivation(deriving)} disabled={busy}
            className="w-full py-1 rounded bg-amber-500 hover:bg-amber-400 text-black text-[11px] font-medium disabled:opacity-50 flex items-center justify-center gap-1">
            {busy ? <><Loader2 className="w-3 h-3 animate-spin" /> Generating…</> : 'Generate'}
          </button>
        </div>
      )}
      {derived && (
        <div className="rounded border border-amber-500/30 p-2 space-y-1.5" data-testid="derived-result">
          <p className="text-[10px] uppercase tracking-wide text-amber-300/80">↳ New version from “{pin.label || 'this pin'}” · not kept unless you pin it</p>
          <p className="text-xs text-[#cdd2f0] font-serif whitespace-pre-wrap">{derived.transformed}</p>
          <GenerationWarnings warnings={derived.warnings} compact />
          <PinActions source={{
            text: derived.transformed, tool: pin.tool, toolParams: pin.tool_params, chapterId: pin.chapter_id,
            sourceText: pin.source_excerpt, sourceFrom: null, sourceTo: null, parentPinId: pin.pin_id,
            derivation: derivedIntent,
          }} compact />
        </div>
      )}
    </div>
  )
}
