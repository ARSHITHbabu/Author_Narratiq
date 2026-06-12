'use client'

// Selection Toolbar — appears when prose is selected in the Write editor. Runs the
// ai_transform FEATURE on the EXACT selection (never RAG), shows a preview, and on
// Apply replaces only the selected range via the editor bridge. Mirrors the voice
// transform preview→apply flow; uses existing aiApi endpoints.

import { useState } from 'react'
import { Sparkles, Loader2, Check, X } from 'lucide-react'
import { toast } from 'sonner'
import { aiApi } from '@/lib/api'
import { useStoryContext } from './StoryContextEngine'
import type { LiveSelection } from '@/components/editor/EditorWithMethods'

type Action = 'refine' | 'emotion' | 'tone' | 'shorten' | 'age_adapt'

const QUICK: { id: Action; label: string }[] = [
  { id: 'refine', label: 'Refine' },
  { id: 'emotion', label: 'More emotion' },
  { id: 'tone', label: 'Darker' },
  { id: 'shorten', label: 'Tighten' },
  { id: 'age_adapt', label: 'For YA' },
]

async function runTransform(action: Action, text: string, storyId: string): Promise<string> {
  switch (action) {
    case 'refine':   return (await aiApi.refine(text, 'standard', storyId)).data.transformed
    case 'emotion':  return (await aiApi.emotion(text, 'tension', 'medium')).data.transformed
    case 'tone':     return (await aiApi.tone(text, 'darker', storyId)).data.transformed
    case 'shorten':  return (await aiApi.refine(text, 'standard', storyId)).data.transformed
    case 'age_adapt': return (await aiApi.ageAdapt(text, 'ya', storyId)).data.transformed
  }
}

export default function SelectionToolbar({ selection }: { selection: LiveSelection | null }) {
  const { storyId, editor, logActivity } = useStoryContext()
  const [busy, setBusy] = useState<Action | null>(null)
  const [preview, setPreview] = useState<{ text: string; from: number; to: number } | null>(null)

  if (!selection && !preview) return null

  const run = async (action: Action) => {
    if (!selection) return
    const { from, to, text } = selection
    setBusy(action)
    try {
      const out = await runTransform(action, text, storyId)
      setPreview({ text: out, from, to })
      logActivity({ category: 'ai', type: `${action}_transform`, title: `AI ${action} on selection`, summary: out.slice(0, 160), ref_type: 'selection' })
    } catch {
      toast.error('Transform failed')
    } finally {
      setBusy(null)
    }
  }

  const apply = () => {
    if (preview && editor) {
      editor.replaceRange(preview.from, preview.to, preview.text)
      toast.success('Applied to your selection')
    }
    setPreview(null)
  }

  return (
    <div className="absolute top-2 left-1/2 -translate-x-1/2 z-20 max-w-2xl w-[min(92%,42rem)]">
      {!preview ? (
        <div className="flex items-center gap-1 rounded-full border border-[#2e3454] bg-[#13162a] shadow-xl px-2 py-1">
          <Sparkles className="w-3.5 h-3.5 text-amber-400 ml-1" />
          {QUICK.map((q) => (
            <button key={q.id} disabled={!!busy} onClick={() => run(q.id)}
              className="text-[11px] px-2 py-1 rounded-full text-[#cdd2f0] hover:bg-[#1f2440] disabled:opacity-50 flex items-center gap-1">
              {busy === q.id && <Loader2 className="w-3 h-3 animate-spin" />}{q.label}
            </button>
          ))}
        </div>
      ) : (
        <div className="rounded-lg border border-amber-500/30 bg-[#13162a] shadow-xl p-3 space-y-2">
          <p className="text-[10px] uppercase tracking-wide text-amber-300/80">Preview (selected text)</p>
          <p className="text-xs text-[#cdd2f0] leading-relaxed max-h-40 overflow-y-auto whitespace-pre-wrap">{preview.text}</p>
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
