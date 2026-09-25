'use client'

// Compare two versions and merge them (Phase 3 P3-04).
//
// The diff runs in the browser (lib/diff.ts): both texts are already here, and
// an unpinned result must never be uploaded just to be compared (R1). The two
// optional AI steps — a description of the trade-off and smoothing the joins
// of a merge — only ever receive text the author is looking at, and smoothing
// is rejected server-side if it would alter the chosen passages (R6).

import { useEffect, useMemo, useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { X, Loader2, Sparkles, ArrowDownToLine, Wand2 } from 'lucide-react'
import { toast } from 'sonner'
import { diffWords, groupBySentence, mergeBlocks, stats } from '@/lib/diff'
import { generationApi } from '@/lib/api'
import { apiErrorText } from '@/lib/generationControls'
import { useGenerationStore } from '@/lib/generationStore'
import { useStoryContext } from '@/components/studio/StoryContextEngine'
import GenerationWarnings from './GenerationWarnings'
import PinActions from './PinActions'
import { selectionSafeProps } from '@/lib/selectionOwnership'
import type { GenerationWarning } from '@/lib/types'

type View = 'side' | 'unified' | 'changes'

export default function VersionCompareView() {
  const { compare, closeCompare } = useGenerationStore()
  const { storyId, activeChapterId, editor } = useStoryContext()
  const [view, setView] = useState<View>('side')
  const [choice, setChoice] = useState<('a' | 'b')[]>([])
  const [summary, setSummary] = useState<{ summary: string; a_strengths: string[]; b_strengths: string[]; recommendation: string } | null>(null)
  const [summaryState, setSummaryState] = useState<'idle' | 'loading' | 'unavailable'>('idle')
  const [merged, setMerged] = useState<{ text: string; warnings: GenerationWarning[]; smoothed: boolean } | null>(null)
  const [smoothing, setSmoothing] = useState(false)

  const left = compare?.left, right = compare?.right
  const diff = useMemo(() => (left && right ? diffWords(left.text, right.text) : null), [left, right])
  const counts = useMemo(() => (diff ? stats(diff.ops) : null), [diff])
  const blocks = useMemo(() => (left && right ? groupBySentence(left.text, right.text) : []), [left, right])

  useEffect(() => {
    setChoice(blocks.map(() => 'a'))
    setSummary(null); setSummaryState('idle'); setMerged(null)
  }, [blocks])

  if (!compare || !left || !right || !diff || !counts) return null

  const assembled = mergeBlocks(blocks, choice)
  const assembledText = assembled.map((b) => b.text).join('')

  const describe = async () => {
    setSummaryState('loading')
    try {
      const r = await generationApi.compareSummary(storyId, left.text, right.text)
      if (r.data.available) { setSummary(r.data); setSummaryState('idle') } else setSummaryState('unavailable')
    } catch (e) {
      setSummaryState('unavailable')
      toast.error(apiErrorText(e, 'The AI could not describe the differences right now.'))
    }
  }

  const smooth = async () => {
    setSmoothing(true)
    try {
      const r = await generationApi.mergeVersions(storyId, assembled)
      setMerged({ text: r.data.merged, warnings: r.data.warnings ?? [], smoothed: r.data.smoothed })
    } catch (e) {
      toast.error(apiErrorText(e, 'Smoothing is unavailable right now. Your merge is unchanged.'))
    } finally {
      setSmoothing(false)
    }
  }

  const finalText = merged?.text ?? assembledText
  const insert = () => {
    if (!editor) { toast.error('Open a chapter in the editor first.'); return }
    editor.insertText(finalText)
    toast.success('Inserted into your chapter')
    closeCompare()
  }

  const seg = (kind: 'equal' | 'insert' | 'delete', text: string, i: number) => (
    <span key={i} className={kind === 'insert' ? 'bg-emerald-500/20 text-emerald-200' : kind === 'delete' ? 'bg-rose-500/20 text-rose-200 line-through' : ''}>{text}</span>
  )

  return (
    <Dialog.Root open onOpenChange={(o) => { if (!o) closeCompare() }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/60 z-50" />
        <Dialog.Content {...selectionSafeProps()} aria-describedby={undefined}
          className="fixed z-50 left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[min(96vw,64rem)] max-h-[90vh] overflow-y-auto rounded-xl border border-[#2e3454] bg-[#0f1220] p-4 space-y-3 text-[#e8eaf6]">
          <div className="flex items-center gap-2">
            <Dialog.Title className="text-sm font-medium">Compare versions</Dialog.Title>
            <span className="text-[11px] text-[#5c6391]">
              +{counts.added} words · −{counts.removed} words · {counts.unchanged} unchanged{diff.sentenceLevel ? ' · long texts are compared sentence by sentence' : ''}
            </span>
            <div className="ml-auto flex items-center gap-1" role="tablist" aria-label="Comparison view">
              {(['side', 'unified', 'changes'] as View[]).map((v) => (
                <button key={v} role="tab" aria-selected={view === v} onClick={() => setView(v)}
                  className={`text-[11px] px-2 py-1 rounded ${view === v ? 'bg-amber-500/20 text-amber-300' : 'text-[#9da3c8] hover:bg-[#1f2440]'}`}>
                  {v === 'side' ? 'Side by side' : v === 'unified' ? 'Unified' : 'Changes only'}
                </button>
              ))}
            </div>
            <Dialog.Close className="p-1 rounded text-[#9da3c8] hover:text-white" aria-label="Close comparison"><X className="w-4 h-4" /></Dialog.Close>
          </div>

          {view === 'side' && (
            <div className="grid grid-cols-2 gap-3 text-xs font-serif leading-relaxed">
              <div><p className="text-[10px] uppercase text-[#5c6391] mb-1">{left.label}</p>
                <div className="whitespace-pre-wrap rounded border border-[#1f2440] p-2">{diff.ops.filter((o) => o.kind !== 'insert').map((o, i) => seg(o.kind, o.text, i))}</div></div>
              <div><p className="text-[10px] uppercase text-[#5c6391] mb-1">{right.label}</p>
                <div className="whitespace-pre-wrap rounded border border-[#1f2440] p-2">{diff.ops.filter((o) => o.kind !== 'delete').map((o, i) => seg(o.kind, o.text, i))}</div></div>
            </div>
          )}
          {view === 'unified' && (
            <div className="whitespace-pre-wrap rounded border border-[#1f2440] p-2 text-xs font-serif leading-relaxed">{diff.ops.map((o, i) => seg(o.kind, o.text, i))}</div>
          )}
          {view === 'changes' && (
            <ul className="space-y-1 text-xs font-serif">
              {blocks.filter((b) => b.changed).map((b, i) => (
                <li key={i} className="rounded border border-[#1f2440] p-2 grid grid-cols-2 gap-2">
                  <span className="text-rose-200">{b.a || <em className="text-[#5c6391]">(nothing)</em>}</span>
                  <span className="text-emerald-200">{b.b || <em className="text-[#5c6391]">(nothing)</em>}</span>
                </li>
              ))}
              {!blocks.some((b) => b.changed) && <li className="text-[#5c6391]">The two versions are identical.</li>}
            </ul>
          )}

          <div className="rounded border border-[#1f2440] p-2 space-y-1.5">
            <div className="flex items-center gap-2">
              <span className="text-[11px] text-[#9da3c8]">What’s different?</span>
              <button onClick={describe} disabled={summaryState === 'loading'} className="text-[11px] px-2 py-0.5 rounded border border-[#2e3454] hover:bg-[#1f2440] inline-flex items-center gap-1">
                {summaryState === 'loading' ? <Loader2 className="w-3 h-3 animate-spin" /> : <Sparkles className="w-3 h-3" />} Describe with AI
              </button>
              {summaryState === 'unavailable' && <span className="text-[11px] text-[#5c6391]">A description could not be produced this time — the comparison above is complete without it.</span>}
            </div>
            {summary && (
              <div className="text-[11px] text-[#cdd2f0] space-y-1">
                <p>{summary.summary}</p>
                {summary.a_strengths.length > 0 && <p><strong>{left.label}:</strong> {summary.a_strengths.join('; ')}</p>}
                {summary.b_strengths.length > 0 && <p><strong>{right.label}:</strong> {summary.b_strengths.join('; ')}</p>}
                {summary.recommendation && <p className="text-[#9da3c8]">{summary.recommendation}</p>}
              </div>
            )}
          </div>

          {blocks.some((b) => b.changed) && (
            <div className="rounded border border-[#1f2440] p-2 space-y-2" data-testid="merge-section">
              <p className="text-[11px] text-[#9da3c8]">Merge: pick a side for each changed passage.</p>
              <ol className="space-y-1">
                {blocks.map((b, i) => b.changed ? (
                  <li key={i} className="grid grid-cols-2 gap-2 text-xs font-serif">
                    {(['a', 'b'] as const).map((side) => (
                      <button key={side} type="button" aria-pressed={choice[i] === side}
                        onClick={() => { setChoice((c) => c.map((x, k) => (k === i ? side : x))); setMerged(null) }}
                        className={`text-left rounded border p-1.5 ${choice[i] === side ? 'border-amber-500/60 bg-amber-500/10' : 'border-[#1f2440] opacity-70 hover:opacity-100'}`}>
                        <span className="block text-[9px] uppercase text-[#5c6391]">{side === 'a' ? left.label : right.label}</span>
                        {(side === 'a' ? b.a : b.b) || <em className="text-[#5c6391]">(leave out)</em>}
                      </button>
                    ))}
                  </li>
                ) : null)}
              </ol>
              <div className="rounded border border-[#1f2440] p-2">
                <p className="text-[10px] uppercase text-[#5c6391] mb-1">Merged result {merged?.smoothed ? '· joins smoothed' : ''}</p>
                <p className="text-xs font-serif whitespace-pre-wrap" data-testid="merged-text">{finalText}</p>
              </div>
              {merged && <GenerationWarnings warnings={merged.warnings} compact />}
              <div className="flex flex-wrap gap-2 items-start">
                <button onClick={smooth} disabled={smoothing} className="text-[11px] px-2 py-1 rounded border border-[#2e3454] hover:bg-[#1f2440] inline-flex items-center gap-1">
                  {smoothing ? <Loader2 className="w-3 h-3 animate-spin" /> : <Wand2 className="w-3 h-3" />} Smooth the joins with AI
                </button>
                <button onClick={insert} className="text-[11px] px-2 py-1 rounded bg-amber-500 hover:bg-amber-400 text-black font-medium inline-flex items-center gap-1">
                  <ArrowDownToLine className="w-3 h-3" /> Insert at cursor
                </button>
                <div className="flex-1 min-w-[14rem]">
                  <PinActions compact source={{
                    text: finalText, tool: 'merge', toolParams: {}, chapterId: activeChapterId, sourceText: left.text,
                    sourceFrom: null, sourceTo: null,
                    derivedFromPinIds: [left.pinId, right.pinId].filter(Boolean) as string[],
                  }} />
                </div>
              </div>
            </div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
