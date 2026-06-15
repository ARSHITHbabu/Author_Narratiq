'use client'

// Copyright / Plagiarism Risk Detection panel. Runs the on-demand risk analysis
// at three scopes — Selection / Chapter / Whole Story — reusing the editor bridge
// from the Story Context Engine for selection & chapter text. This is RISK
// guidance, NOT legal advice (disclaimer shown in the footer).

import { useState } from 'react'
import {
  ShieldAlert, ShieldCheck, ChevronDown, ChevronUp, Loader2, ScanSearch, Info,
} from 'lucide-react'
import { copyrightRiskApi } from '@/lib/api'
import { CopyrightRiskFinding, CopyrightRiskResponse, RiskLevel } from '@/lib/types'
import { useStoryContext } from '@/components/studio/StoryContextEngine'
import { toast } from 'sonner'

type Scope = 'selection' | 'chapter' | 'project'

const RISK_STYLES: Record<RiskLevel, { badge: string; border: string; text: string }> = {
  high:   { badge: 'bg-red-500/20 text-red-400 border-red-500/30',       border: 'border-red-500/20',   text: 'text-red-400' },
  medium: { badge: 'bg-amber-500/20 text-amber-400 border-amber-500/30', border: 'border-amber-500/20', text: 'text-amber-400' },
  low:    { badge: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30', border: 'border-[#1f2440]', text: 'text-emerald-400' },
}

const TYPE_LABEL: Record<string, string> = {
  direct_text:     'Direct text',
  plot:            'Plot',
  character:       'Character',
  world_building:  'World-building',
  scene:           'Scene',
  style_imitation: 'Style imitation',
  trope_overuse:   'Trope overuse',
}

function FindingCard({ f }: { f: CopyrightRiskFinding }) {
  const [expanded, setExpanded] = useState(false)
  const styles = RISK_STYLES[f.risk_score] ?? RISK_STYLES.low
  const typeLabel = TYPE_LABEL[f.risk_type] ?? f.risk_type

  return (
    <div className={`border rounded-xl bg-[#0d0f1a] ${styles.border} overflow-hidden`}>
      <button className="w-full text-left p-3 flex items-start gap-2.5" onClick={() => setExpanded(!expanded)}>
        <ShieldAlert className={`w-3.5 h-3.5 mt-0.5 flex-shrink-0 ${styles.text}`} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap mb-1">
            <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded border ${styles.badge}`}>
              {f.risk_score.toUpperCase()}
            </span>
            <span className="text-[10px] text-[#5c6391] px-1.5 py-0.5 rounded bg-[#0f1220] border border-[#1f2440]">
              {typeLabel}
            </span>
            {f.is_generic_trope && (
              <span className="text-[10px] text-[#9da3c8] px-1.5 py-0.5 rounded bg-[#1f2440]">generic trope</span>
            )}
          </div>
          <p className="text-xs text-[#c8cce8] leading-relaxed line-clamp-2">{f.description}</p>
        </div>
        <div className="flex-shrink-0 text-[#3d4466] mt-0.5">
          {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </div>
      </button>

      {expanded && (
        <div className="px-3 pb-3 border-t border-[#1f2440] pt-2.5 space-y-2">
          <p className="text-xs text-[#9da3c8] leading-relaxed">{f.description}</p>
          {f.problematic_excerpt && (
            <div className="bg-[#0f1220] border border-[#1f2440] rounded-lg p-2.5">
              <p className="text-[10px] text-[#5c6391] font-medium mb-1">Implicated passage</p>
              <p className="text-xs text-[#c8cce8] leading-relaxed italic font-serif">“{f.problematic_excerpt}”</p>
            </div>
          )}
          {f.rewrite_suggestion && (
            <div className="bg-[#0f1220] border border-amber-500/20 rounded-lg p-2.5">
              <p className="text-[10px] text-amber-500/70 font-medium mb-1">How to make it more original</p>
              <p className="text-xs text-[#9da3c8] leading-relaxed">{f.rewrite_suggestion}</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

interface Props {
  storyId: string
}

export default function CopyrightRiskPanel({ storyId }: Props) {
  const { editor } = useStoryContext()
  const [scope, setScope] = useState<Scope>('project')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<CopyrightRiskResponse | null>(null)
  const [notEnough, setNotEnough] = useState(false)

  const run = async () => {
    let text: string | undefined
    if (scope === 'selection') {
      text = editor?.getSelectedText()?.trim() || ''
      if (!text) { toast.error('Select some text in the editor first.'); return }
    } else if (scope === 'chapter') {
      text = editor?.getFullText()?.trim() || ''
      if (!text) { toast.error('Open a chapter with some text first.'); return }
    }

    setLoading(true)
    setResult(null)
    setNotEnough(false)
    try {
      const res = await copyrightRiskApi.analyze(storyId, { scope, text })
      setResult(res.data as CopyrightRiskResponse)
    } catch (err: any) {
      const status = err?.response?.status
      const detail = err?.response?.data?.detail || ''
      if (status === 422) setNotEnough(true)
      else toast.error(detail || 'Analysis failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const overallStyles = result ? (RISK_STYLES[result.overall_risk] ?? RISK_STYLES.low) : RISK_STYLES.low

  // Sort findings high → medium → low.
  const sorted = result
    ? [...result.findings].sort((a, b) => {
        const order = { high: 0, medium: 1, low: 2 }
        return (order[a.risk_score] ?? 3) - (order[b.risk_score] ?? 3)
      })
    : []

  return (
    <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4">

      {/* Scope selector */}
      <div>
        <label className="text-[10px] text-[#5c6391] block mb-1.5">Scope</label>
        <div className="grid grid-cols-3 gap-1.5">
          {([
            { id: 'selection', label: 'Selection' },
            { id: 'chapter',   label: 'Chapter'   },
            { id: 'project',   label: 'Whole Story' },
          ] as { id: Scope; label: string }[]).map((s) => (
            <button
              key={s.id}
              onClick={() => { setScope(s.id); setResult(null); setNotEnough(false) }}
              className={`py-1.5 rounded-lg border text-xs transition-all ${
                scope === s.id
                  ? 'border-amber-500/50 bg-amber-500/10 text-amber-400'
                  : 'border-[#2e3454] text-[#9da3c8] hover:border-[#3d4466]'
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      {/* Run button */}
      <button
        onClick={run}
        disabled={loading}
        className="w-full flex items-center justify-center gap-2 py-2.5 px-4 bg-amber-500 hover:bg-amber-600 disabled:opacity-40 disabled:cursor-not-allowed text-black text-sm font-medium rounded-xl transition-colors"
      >
        {loading
          ? <><Loader2 className="w-4 h-4 animate-spin" /> Analyzing…</>
          : <><ScanSearch className="w-4 h-4" /> Check {scope === 'project' ? 'Whole Story' : scope === 'chapter' ? 'Chapter' : 'Selection'}</>
        }
      </button>

      {/* Not enough data */}
      {notEnough && !loading && (
        <div className="flex flex-col items-center gap-2 py-4 text-center">
          <Info className="w-6 h-6 text-amber-400/60" />
          <p className="text-xs text-[#9da3c8] font-medium">Nothing to analyze yet</p>
          <p className="text-xs text-[#5c6391] leading-relaxed">
            {scope === 'project'
              ? 'Sync at least 1 chapter using Sync Summaries in the chapter list.'
              : 'Add some text first, then try again.'}
          </p>
        </div>
      )}

      {/* Results */}
      {result && !loading && (
        <div className="flex flex-col gap-3">
          <div className={`flex items-center justify-between rounded-xl border p-3 ${overallStyles.border} bg-[#0d0f1a]`}>
            <div className="flex items-center gap-2">
              {result.overall_risk === 'low'
                ? <ShieldCheck className={`w-5 h-5 ${overallStyles.text}`} />
                : <ShieldAlert className={`w-5 h-5 ${overallStyles.text}`} />}
              <div>
                <p className="text-xs text-[#5c6391]">Overall risk</p>
                <p className={`text-sm font-semibold ${overallStyles.text}`}>{result.overall_risk.toUpperCase()}</p>
              </div>
            </div>
            <span className="text-[10px] text-[#5c6391]">
              {result.units_analyzed} {result.scope === 'project' ? 'chapter(s)' : 'passage'} · {result.findings_count} finding(s)
            </span>
          </div>

          {result.findings_count === 0 && (
            <div className="flex flex-col items-center gap-2 py-4 text-center">
              <ShieldCheck className="w-7 h-7 text-emerald-500/60" />
              <p className="text-xs text-[#9da3c8] font-medium">No notable similarity detected</p>
              <p className="text-xs text-[#5c6391]">This content reads as original within the analyzed scope.</p>
            </div>
          )}

          {sorted.map((f) => <FindingCard key={f.finding_id} f={f} />)}

          {result.note && (
            <p className="text-[10px] text-[#3d4466] leading-relaxed border-t border-[#1f2440] pt-2">{result.note}</p>
          )}

          {/* Non-legal-advice disclaimer */}
          <div className="flex items-start gap-1.5 rounded-lg bg-[#1a1e36] border border-[#2e3454] p-2.5">
            <Info className="w-3 h-3 text-[#5c6391] mt-0.5 flex-shrink-0" />
            <p className="text-[10px] text-[#5c6391] leading-relaxed">{result.disclaimer}</p>
          </div>
        </div>
      )}

      {/* Empty state */}
      {!loading && !result && !notEnough && (
        <div className="flex flex-col items-center gap-3 py-6 text-center">
          <ShieldAlert className="w-8 h-8 text-[#2e3454]" />
          <div>
            <p className="text-xs text-[#5c6391] font-medium">Check for copyright / plagiarism risk</p>
            <p className="text-xs text-[#3d4466] mt-1 leading-relaxed">
              Flags text, plot, character, world,<br />scene, style and trope similarity.
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
