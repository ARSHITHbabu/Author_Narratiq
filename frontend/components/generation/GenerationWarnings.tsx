'use client'

// One banner for every Phase 3 post-generation signal (preservation checks,
// story consistency, context that was dropped, similarity). Shared by the
// Selection Toolbar preview and the AI Sidecar result so an author sees the
// same thing on both surfaces.
//
// Nothing here changes the author's text by itself. "Fix names" applies the
// server's name suggestions only when the author clicks it.

import { AlertTriangle, Info, Wand2 } from 'lucide-react'
import type { GenerationWarning } from '@/lib/types'

const TONE: Record<GenerationWarning['severity'], string> = {
  hard: 'text-red-300 bg-red-500/10 border-red-500/30',
  soft: 'text-amber-300 bg-amber-500/10 border-amber-500/30',
  info: 'text-[#9da3c8] bg-[#1a1e36] border-[#2e3454]',
}

const ENTITY_HINT: Record<string, string> = {
  story_fact: 'If the story has moved on, update this fact in Story Intelligence.',
  character: 'Check the character’s profile if this was intended.',
}

interface Props {
  warnings: GenerationWarning[]
  /** Apply {replace → with} pairs to the result text (author-initiated only). */
  onAutofix?: (fixes: { replace: string; with: string }[]) => void
  compact?: boolean
}

export default function GenerationWarnings({ warnings, onAutofix, compact }: Props) {
  if (!warnings?.length) return null
  // Hard first, then soft, then info — the author reads the important ones first.
  const order = { hard: 0, soft: 1, info: 2 }
  const sorted = [...warnings].sort((a, b) => order[a.severity] - order[b.severity])
  return (
    <ul data-testid="generation-warnings" className="space-y-1" aria-label="Notes about this result">
      {sorted.map((w, i) => (
        <li key={`${w.kind}-${i}`} data-kind={w.kind}
          className={`flex items-start gap-1.5 text-[11px] leading-snug border rounded px-2 py-1.5 ${TONE[w.severity]}`}>
          {w.severity === 'info'
            ? <Info className="w-3 h-3 mt-0.5 flex-shrink-0" aria-hidden />
            : <AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" aria-hidden />}
          <div className="min-w-0 flex-1">
            <span>{w.message}</span>
            {!compact && w.entity?.type && ENTITY_HINT[w.entity.type] && (
              <span className="block opacity-80 mt-0.5">{ENTITY_HINT[w.entity.type]}</span>
            )}
            {w.autofix?.length && onAutofix ? (
              <button type="button" onClick={() => onAutofix(w.autofix!)}
                className="mt-1 inline-flex items-center gap-1 px-1.5 py-0.5 rounded border border-current/40 hover:bg-white/5">
                <Wand2 className="w-3 h-3" aria-hidden />
                Restore “{w.autofix.map((f) => f.with).join('”, “')}”
              </button>
            ) : null}
          </div>
        </li>
      ))}
    </ul>
  )
}

/** Deterministic, exact client-side name substitution (spec §25.4). */
export function applyNameFixes(text: string, fixes: { replace: string; with: string }[]): string {
  let out = text
  for (const f of fixes) {
    const escaped = f.replace.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    out = out.replace(new RegExp(`\\b${escaped}\\b`, 'g'), f.with)
  }
  return out
}
