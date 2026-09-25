'use client'

// Result-card actions shared by the Selection Toolbar and the AI Sidecar:
//   Pin (P3-01) · Send to Idea Shelf (P3-09) · similarity badge (P3-11).
//
// Contract stated to the author (R1/R2): only pinned versions are kept; pins
// expire; ideas on the Idea Shelf are permanent. The cap is never enforced by
// silently evicting a pin — the author chooses, in this component.

import { useEffect, useState } from 'react'
import { Pin as PinIcon, Lightbulb, Loader2, Check, Copy as CompareIcon } from 'lucide-react'
import { toast } from 'sonner'
import { ocrApi, pinsApi } from '@/lib/api'
import { apiErrorText, expiryLabel, IDEA_TYPES, sha256Hex, TOOL_LABELS } from '@/lib/generationControls'
import { useGenerationStore } from '@/lib/generationStore'
import { useStoryContext } from '@/components/studio/StoryContextEngine'
import type { Pin, SimilarityMatch } from '@/lib/types'

export interface PinSource {
  text: string                      // the generated text
  tool: string
  toolParams: Record<string, unknown>
  chapterId: string | null
  sourceText: string                // the author's original selection (only 300 chars are stored)
  sourceFrom: number | null
  sourceTo: number | null
  parentPinId?: string | null       // when generated from a pinned version (P3-06)
  derivation?: string
  derivedFromPinIds?: string[]      // pins used as context (P3-03)
  sessionId?: string                // session-history id, to exclude itself from similarity
}

interface CapState { used: number; max: number; plan: string; oldest?: { label: string; created_at: string | null } }

export default function PinActions({ source, compact }: { source: PinSource; compact?: boolean }) {
  const { storyId, chapters } = useStoryContext()
  const { pinsChanged, recentTexts, openCompare } = useGenerationStore()
  const [pinning, setPinning] = useState(false)
  const [pinned, setPinned] = useState<Pin | null>(null)
  const [cap, setCap] = useState<CapState | null>(null)
  const [ideaOpen, setIdeaOpen] = useState(false)
  const [ideaType, setIdeaType] = useState('future_scene')
  const [ideaChapter, setIdeaChapter] = useState<string>('')
  const [savingIdea, setSavingIdea] = useState(false)
  const [similar, setSimilar] = useState<{ match: SimilarityMatch; label: string; text?: string } | null>(null)

  // New result → fresh state.
  useEffect(() => { setPinned(null); setCap(null); setIdeaOpen(false) }, [source.text])

  // P3-11 — informative only, never blocking. Compares against recent pins of
  // this tool and this session's earlier attempts; nothing is stored.
  useEffect(() => {
    let cancelled = false
    const earlier = source.chapterId ? recentTexts(source.chapterId, source.tool, source.sessionId) : []
    pinsApi.similarity(storyId, { text: source.text, tool: source.tool, against_texts: [] })
      .then(async (r) => {
        let best: { match: SimilarityMatch; label: string; text?: string } | null = null
        const top = (r.data.matches as SimilarityMatch[]).find((m) => m.label !== 'distinct' && m.score >= 0.75)
        if (top?.pin_id) best = { match: top, label: 'a pinned version' }
        if (earlier.length) {
          const r2 = await pinsApi.similarity(storyId, { text: source.text, against_texts: earlier.slice(-5) })
          const t = (r2.data.matches as SimilarityMatch[]).find((m) => m.label === 'near_duplicate')
          if (t && (!best || t.score > best.match.score)) best = { match: t, label: 'an earlier attempt', text: earlier.slice(-5)[t.text_index ?? 0] }
        }
        if (!cancelled) setSimilar(best)
      })
      .catch(() => { if (!cancelled) setSimilar(null) })   // similarity is optional; never an error for the author
    return () => { cancelled = true }
  }, [storyId, source.text, source.tool, source.chapterId, source.sessionId, recentTexts])

  const pin = async (replaceOldest = false) => {
    setPinning(true)
    try {
      const res = await pinsApi.create(storyId, {
        chapter_id: source.chapterId, tool: source.tool, scope: 'selection', tool_params: source.toolParams,
        content: source.text, source_excerpt: source.sourceText.slice(0, 300),
        source_text_sha256: await sha256Hex(source.sourceText),
        source_from: source.sourceFrom, source_to: source.sourceTo,
        parent_pin_id: source.parentPinId ?? null, derivation: source.derivation ?? '',
        derived_from_pin_ids: source.derivedFromPinIds ?? [], replace_oldest: replaceOldest,
      })
      const p: Pin = res.data.pin
      setPinned(p); setCap(null); pinsChanged()
      toast.success(res.data.already_pinned ? 'Already pinned' : `Pinned · ${expiryLabel(p.expires_at).text}`)
    } catch (e: any) {
      const d = e?.response?.data
      if (e?.response?.status === 409 && d?.code === 'pin_limit_reached') {
        setCap({ ...d.limits, oldest: d.oldest_pin })
      } else {
        toast.error(apiErrorText(e, 'This version could not be pinned. Nothing was lost — it is still shown here.'))
      }
    } finally {
      setPinning(false)
    }
  }

  const saveIdea = async () => {
    setSavingIdea(true)
    try {
      if (pinned) {
        await pinsApi.promote(storyId, pinned.pin_id, { card_type: ideaType, target_chapter_id: ideaChapter || null, release_pin: true })
        setPinned(null); pinsChanged()
      } else {
        await ocrApi.createIdeaCard(storyId, { content: source.text, card_type: ideaType, target_chapter_id: ideaChapter || null,
          title: `${TOOL_LABELS[source.tool] ?? 'AI'} idea` })
      }
      toast.success('Saved to the Idea Shelf — kept permanently (Notes → Ideas)')
      setIdeaOpen(false)
    } catch (e) {
      toast.error(apiErrorText(e, 'The idea could not be saved. Please try again.'))
    } finally {
      setSavingIdea(false)
    }
  }

  const btn = 'inline-flex items-center gap-1 text-[11px] px-2 py-1 rounded border transition-colors disabled:opacity-50'
  return (
    <div className="space-y-1.5" data-testid="pin-actions">
      <div className="flex flex-wrap items-center gap-1.5">
        <button type="button" onClick={() => pin(false)} disabled={pinning || !!pinned}
          data-testid="pin-button"
          aria-label={pinned ? `Pinned, ${expiryLabel(pinned.expires_at).text}` : 'Pin this version so you can come back to it'}
          className={`${btn} ${pinned ? 'border-amber-500/50 bg-amber-500/15 text-amber-300' : 'border-[#2e3454] text-[#cdd2f0] hover:bg-[#1f2440]'}`}>
          {pinning ? <Loader2 className="w-3 h-3 animate-spin" /> : pinned ? <Check className="w-3 h-3" /> : <PinIcon className="w-3 h-3" />}
          {pinned ? `Pinned · ${expiryLabel(pinned.expires_at).text}` : 'Pin'}
        </button>
        <button type="button" onClick={() => setIdeaOpen((o) => !o)} aria-expanded={ideaOpen}
          className={`${btn} border-[#2e3454] text-[#cdd2f0] hover:bg-[#1f2440]`}>
          <Lightbulb className="w-3 h-3" /> Send to Idea Shelf
        </button>
        {similar && (
          <button type="button" data-testid="similarity-badge"
            onClick={async () => {
              let other = similar.text
              if (!other && similar.match.pin_id) other = (await pinsApi.get(storyId, similar.match.pin_id)).data.content
              if (other) openCompare({ label: similar.label === 'a pinned version' ? 'Pinned version' : 'Earlier attempt', text: other, pinId: similar.match.pin_id ?? undefined },
                                     { label: 'This result', text: source.text })
            }}
            title="Open side-by-side comparison"
            className={`${btn} border-sky-500/30 bg-sky-500/10 text-sky-300 hover:bg-sky-500/20`}>
            <CompareIcon className="w-3 h-3" /> {Math.round(similar.match.score * 100)}% similar to {similar.label}
          </button>
        )}
      </div>
      {!compact && !pinned && (
        <p className="text-[10px] text-[#8e94bd]">Only pinned versions are kept. Everything else disappears when you refresh.</p>
      )}
      {cap && (
        <div role="alertdialog" aria-label="Pin limit reached" className="text-[11px] rounded border border-amber-500/30 bg-amber-500/10 p-2 space-y-1.5">
          <p className="text-amber-200">
            You have {cap.used} of {cap.max} pins on the {cap.plan} plan.
            {cap.oldest ? ` Replace the oldest${cap.oldest.label ? ` (“${cap.oldest.label}”)` : ''}, or free one first in Versions.` : ''}
          </p>
          <div className="flex gap-1.5">
            <button type="button" onClick={() => pin(true)} className={`${btn} border-amber-500/50 text-amber-200 hover:bg-amber-500/20`}>Replace oldest</button>
            <button type="button" onClick={() => setCap(null)} className={`${btn} border-[#2e3454] text-[#9da3c8]`}>Cancel</button>
          </div>
        </div>
      )}
      {ideaOpen && (
        <div className="rounded border border-[#2e3454] bg-[#0d0f1a] p-2 space-y-1.5 text-[11px]">
          <p className="text-[#9da3c8]">Ideas are kept permanently in Notes → Ideas{pinned ? ' (the pin is released)' : ''}.</p>
          <label className="flex items-center gap-2">
            <span className="w-16 text-[#8e94bd]">Type</span>
            <select value={ideaType} onChange={(e) => setIdeaType(e.target.value)}
              className="flex-1 bg-[#13162a] border border-[#2e3454] rounded px-1.5 py-1 text-[#e8eaf6]">
              {IDEA_TYPES.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
            </select>
          </label>
          <label className="flex items-center gap-2">
            <span className="w-16 text-[#8e94bd]">For chapter</span>
            <select value={ideaChapter} onChange={(e) => setIdeaChapter(e.target.value)}
              className="flex-1 bg-[#13162a] border border-[#2e3454] rounded px-1.5 py-1 text-[#e8eaf6]">
              <option value="">Unassigned</option>
              {chapters.map((c) => <option key={c.chapter_id} value={c.chapter_id}>Ch {c.chapter_number}: {c.title || 'Untitled'}</option>)}
            </select>
          </label>
          <button type="button" onClick={saveIdea} disabled={savingIdea}
            className="w-full py-1 rounded bg-amber-500 hover:bg-amber-400 text-black font-medium disabled:opacity-50">
            {savingIdea ? 'Saving…' : 'Save idea'}
          </button>
        </div>
      )}
    </div>
  )
}
