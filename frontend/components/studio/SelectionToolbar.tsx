'use client'

// Selection Toolbar — compact, expandable AI transforms on the EXACT selected text.
// Driven entirely by the shared transform config (lib/transforms) so it exposes the
// full real option set (refine modes, tones, emotions+intensity, audiences, styles,
// languages) without duplicating definitions. Every option calls the correct
// ai_transform endpoint with the selected text only (never RAG/plot/Q&A). Shows a
// preview; Apply replaces only the originally-captured range.

import { useEffect, useRef, useState } from 'react'
import { Sparkles, Loader2, Check, X, ChevronDown } from 'lucide-react'
import { toast } from 'sonner'
import { TRANSFORM_GROUPS, INTENSITIES, runTransform, type GroupId } from '@/lib/transforms'
import { useStoryContext } from './StoryContextEngine'
import { deriveToolDefaults, hasGenreProfile } from '@/lib/genreDefaults'
import type { LiveSelection } from '@/components/editor/EditorWithMethods'

export default function SelectionToolbar({ selection }: { selection: LiveSelection | null }) {
  const { storyId, activeChapterId, editor, logActivity, genreProfile } = useStoryContext()
  const [openGroup, setOpenGroup] = useState<GroupId | null>(null)
  const [busy, setBusy] = useState(false)
  const [intensity, setIntensity] = useState<string>('medium')
  const [preview, setPreview] = useState<{ text: string; from: number; to: number; group: GroupId; value: string } | null>(null)

  // Genre-recommended option per group (only when the story has a genre profile).
  // Drives a "recommended" highlight + a dot on the group button, so the toolbar
  // visually guides toward genre-appropriate choices without blocking any option.
  const profilePresent = hasGenreProfile(genreProfile)
  const d = deriveToolDefaults(genreProfile)
  const recByGroup: Partial<Record<GroupId, string>> = profilePresent
    ? { tone: d.tone, emotion: d.emotion, style: d.style, age_adapt: d.age }
    : {}
  const isRecommended = (g: GroupId, optId: string) =>
    (recByGroup[g] ?? '').toLowerCase() === optId.toLowerCase()

  // Selection lifecycle: when the live selection changes (new range, or cleared),
  // close any open dropdown and drop a stale preview — never keep stale UI.
  const selKey = selection ? `${selection.from}:${selection.to}` : null
  const prevKeyRef = useRef<string | null>(null)
  useEffect(() => {
    if (selKey !== prevKeyRef.current) {
      prevKeyRef.current = selKey
      setOpenGroup(null)
      if (selKey) setPreview(null)        // a fresh selection invalidates an old preview
    }
  }, [selKey])

  // Hide entirely when there is neither a live selection nor a preview to review.
  if (!selection && !preview) return null

  const run = async (group: GroupId, value: string) => {
    if (!selection) { toast.error('Select the text again to transform it.'); return }
    const { from, to, text } = selection
    setBusy(true); setOpenGroup(null)
    try {
      const out = await runTransform(group, value, text, { storyId, chapterId: activeChapterId ?? undefined, intensity })
      setPreview({ text: out, from, to, group, value })
      logActivity({ category: 'ai', type: `${group}_transform`, title: `AI ${group} on selection`, summary: out.slice(0, 160), ref_type: 'selection', metadata: { value } })
    } catch {
      toast.error('Transform failed')
    } finally {
      setBusy(false)
    }
  }

  const apply = () => {
    if (!preview) return
    if (!editor) { toast.error('Editor not ready — please reselect.'); setPreview(null); return }
    editor.replaceRange(preview.from, preview.to, preview.text)
    toast.success('Applied to your selected text')
    setPreview(null)
  }

  return (
    <div className="absolute top-2 left-1/2 -translate-x-1/2 z-20 w-[min(94%,46rem)]"
      onMouseDown={(e) => e.stopPropagation()}>
      {!preview ? (
        <div className="relative flex items-center gap-0.5 rounded-full border border-[#2e3454] bg-[#13162a] shadow-xl px-2 py-1">
          <Sparkles className="w-3.5 h-3.5 text-amber-400 mx-1 flex-shrink-0" />
          {busy && <Loader2 className="w-3.5 h-3.5 animate-spin text-amber-400" />}
          {TRANSFORM_GROUPS.map((g) => (
            <div key={g.id} className="relative">
              <button disabled={busy} onClick={() => setOpenGroup((o) => (o === g.id ? null : g.id))}
                title={recByGroup[g.id] ? `Genre recommends: ${recByGroup[g.id]}` : undefined}
                className={`relative flex items-center gap-1 text-[11px] px-2 py-1 rounded-full ${openGroup === g.id ? 'bg-[#1f2440] text-amber-300' : 'text-[#cdd2f0] hover:bg-[#1f2440]'} disabled:opacity-50`}>
                <g.icon className="w-3 h-3" /> {g.label} <ChevronDown className="w-2.5 h-2.5 opacity-60" />
                {recByGroup[g.id] && (
                  <span className="absolute -top-0.5 -right-0.5 w-1.5 h-1.5 rounded-full bg-amber-400" aria-hidden />
                )}
              </button>
              {openGroup === g.id && (
                <div className="absolute top-full mt-1 left-0 z-30 w-56 rounded-lg border border-[#2e3454] bg-[#13162a] shadow-2xl py-1 max-h-72 overflow-y-auto">
                  {g.id === 'emotion' && (
                    <div className="flex items-center gap-1 px-2 py-1.5 border-b border-[#1f2440]">
                      <span className="text-[10px] text-[#5c6391] mr-1">Intensity</span>
                      {INTENSITIES.map((i) => (
                        <button key={i} onClick={() => setIntensity(i)}
                          className={`text-[10px] px-1.5 py-0.5 rounded ${intensity === i ? 'bg-amber-500/20 text-amber-300' : 'text-[#9da3c8] hover:bg-[#1f2440]'}`}>{i}</button>
                      ))}
                    </div>
                  )}
                  {recByGroup[g.id] && (
                    <div className="px-3 py-1 text-[10px] text-amber-300/80 border-b border-[#1f2440]">
                      ★ Recommended for {genreProfile?.genre || 'this genre'}
                    </div>
                  )}
                  {g.options.map((o) => {
                    const recommended = isRecommended(g.id, o.id)
                    return (
                      <button key={o.id} onClick={() => run(g.id, o.id)}
                        className={`w-full text-left px-3 py-1.5 flex items-center gap-2 ${recommended ? 'bg-amber-500/10 hover:bg-amber-500/20' : 'hover:bg-[#1f2440]'}`}>
                        {o.emoji && <span>{o.emoji}</span>}
                        <span className={`text-xs ${recommended ? 'text-amber-300' : 'text-[#e8eaf6]'}`}>{o.label}</span>
                        {recommended && <span className="text-[10px] text-amber-400">★</span>}
                        {o.desc && <span className="text-[10px] text-[#5c6391] ml-auto">{o.desc}</span>}
                      </button>
                    )
                  })}
                </div>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="rounded-lg border border-amber-500/30 bg-[#13162a] shadow-2xl p-3 space-y-2">
          <p className="text-[10px] uppercase tracking-wide text-amber-300/80">
            Preview · {preview.group.replace('_', ' ')} {preview.value} (selected text)
          </p>
          <p className="text-xs text-[#cdd2f0] leading-relaxed max-h-48 overflow-y-auto whitespace-pre-wrap font-serif">{preview.text}</p>
          <div className="flex gap-2">
            <button onClick={apply} className="flex-1 text-xs py-1.5 rounded bg-amber-500 hover:bg-amber-400 text-black font-medium flex items-center justify-center gap-1">
              <Check className="w-3.5 h-3.5" /> Apply to selection
            </button>
            <button onClick={() => setPreview(null)} className="flex-1 text-xs py-1.5 rounded border border-[#2a3057] text-[#9da3c8] hover:text-white flex items-center justify-center gap-1">
              <X className="w-3.5 h-3.5" /> Discard
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
