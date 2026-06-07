'use client'

import { useState } from 'react'
import { AlertTriangle, CheckCircle, ChevronDown, ChevronUp, Loader2, ScanSearch } from 'lucide-react'
import { analysisApi } from '@/lib/api'
import { PlotHoleIssue, PlotHoleResponse } from '@/lib/types'
import { toast } from 'sonner'

const SEVERITY_STYLES: Record<string, { badge: string; border: string }> = {
  high:   { badge: 'bg-red-500/20 text-red-400 border-red-500/30',    border: 'border-red-500/20' },
  medium: { badge: 'bg-amber-500/20 text-amber-400 border-amber-500/30', border: 'border-amber-500/20' },
  low:    { badge: 'bg-[#2e3454] text-[#9da3c8] border-[#3d4466]',    border: 'border-[#1f2440]' },
}

const TYPE_LABEL: Record<string, string> = {
  character_inconsistency: 'Character',
  location_inconsistency:  'Location',
  timeline_inconsistency:  'Timeline',
  unresolved_thread:       'Unresolved',
  continuity_break:        'Continuity',
  character_disappearance: 'Disappearance',
}

function IssueCard({ issue }: { issue: PlotHoleIssue }) {
  const [expanded, setExpanded] = useState(false)
  const styles = SEVERITY_STYLES[issue.severity] ?? SEVERITY_STYLES.low
  const typeLabel = TYPE_LABEL[issue.type] ?? issue.type

  return (
    <div className={`border rounded-xl bg-[#0d0f1a] ${styles.border} overflow-hidden`}>
      <button
        className="w-full text-left p-3 flex items-start gap-2.5"
        onClick={() => setExpanded(!expanded)}
      >
        <AlertTriangle className={`w-3.5 h-3.5 mt-0.5 flex-shrink-0 ${
          issue.severity === 'high' ? 'text-red-400' :
          issue.severity === 'medium' ? 'text-amber-400' : 'text-[#5c6391]'
        }`} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap mb-1">
            <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded border ${styles.badge}`}>
              {issue.severity.toUpperCase()}
            </span>
            <span className="text-[10px] text-[#5c6391] px-1.5 py-0.5 rounded bg-[#0f1220] border border-[#1f2440]">
              {typeLabel}
            </span>
            {issue.chapters.map(ch => (
              <span key={ch} className="text-[10px] text-[#9da3c8] px-1 py-0.5 rounded bg-[#1f2440]">
                Ch{ch}
              </span>
            ))}
          </div>
          <p className="text-xs text-[#c8cce8] leading-relaxed line-clamp-2">{issue.description}</p>
        </div>
        <div className="flex-shrink-0 text-[#3d4466] mt-0.5">
          {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </div>
      </button>

      {expanded && (
        <div className="px-3 pb-3 border-t border-[#1f2440] pt-2.5">
          <p className="text-xs text-[#9da3c8] leading-relaxed mb-2">{issue.description}</p>
          {issue.suggestion && (
            <div className="bg-[#0f1220] border border-[#1f2440] rounded-lg p-2.5">
              <p className="text-[10px] text-amber-500/70 font-medium mb-1">Suggestion</p>
              <p className="text-xs text-[#9da3c8] leading-relaxed">{issue.suggestion}</p>
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

export default function PlotHolesPanel({ storyId }: Props) {
  const [loading, setLoading]   = useState(false)
  const [result, setResult]     = useState<PlotHoleResponse | null>(null)
  const [notEnough, setNotEnough] = useState(false)

  const runScan = async () => {
    setLoading(true)
    setResult(null)
    setNotEnough(false)
    try {
      const res = await analysisApi.detectPlotHoles(storyId)
      setResult(res.data as PlotHoleResponse)
    } catch (err: any) {
      const status = err?.response?.status
      const detail = err?.response?.data?.detail || ''
      if (status === 422) {
        setNotEnough(true)
      } else {
        toast.error(detail || 'Analysis failed. Please try again.')
      }
    } finally {
      setLoading(false)
    }
  }

  const highCount   = result?.issues.filter(i => i.severity === 'high').length   ?? 0
  const mediumCount = result?.issues.filter(i => i.severity === 'medium').length ?? 0
  const lowCount    = result?.issues.filter(i => i.severity === 'low').length    ?? 0

  // Sort by severity: high → medium → low
  const sortedIssues = result
    ? [...result.issues].sort((a, b) => {
        const order = { high: 0, medium: 1, low: 2 }
        return (order[a.severity] ?? 3) - (order[b.severity] ?? 3)
      })
    : []

  return (
    <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4">

        {/* Scan button */}
        <button
          onClick={runScan}
          disabled={loading}
          className="w-full flex items-center justify-center gap-2 py-2.5 px-4 bg-amber-500 hover:bg-amber-600 disabled:opacity-40 disabled:cursor-not-allowed text-black text-sm font-medium rounded-xl transition-colors"
        >
          {loading
            ? <><Loader2 className="w-4 h-4 animate-spin" /> Analyzing chapters...</>
            : <><ScanSearch className="w-4 h-4" /> Scan Story</>
          }
        </button>

        {/* Not enough chapters */}
        {notEnough && !loading && (
          <div className="flex flex-col items-center gap-2 py-4 text-center">
            <AlertTriangle className="w-6 h-6 text-amber-400/60" />
            <p className="text-xs text-[#9da3c8] font-medium">Not enough indexed chapters</p>
            <p className="text-xs text-[#5c6391] leading-relaxed">
              Sync at least 2 chapters using the Sync Summaries button in the chapter list.
            </p>
          </div>
        )}

        {/* Results */}
        {result && !loading && (
          <div className="flex flex-col gap-3">

            {/* Summary bar */}
            <div className="flex items-center justify-between text-xs text-[#5c6391]">
              <span>{result.chapters_analyzed} chapter(s) analyzed</span>
              {result.issues_found > 0 && (
                <div className="flex items-center gap-1.5">
                  {highCount   > 0 && <span className="text-red-400">{highCount} high</span>}
                  {mediumCount > 0 && <span className="text-amber-400">{mediumCount} med</span>}
                  {lowCount    > 0 && <span className="text-[#9da3c8]">{lowCount} low</span>}
                </div>
              )}
            </div>

            {/* No issues found */}
            {result.issues_found === 0 && (
              <div className="flex flex-col items-center gap-2 py-4 text-center">
                <CheckCircle className="w-7 h-7 text-green-500/60" />
                <p className="text-xs text-[#9da3c8] font-medium">No issues detected</p>
                <p className="text-xs text-[#5c6391]">Your story is consistent across analyzed chapters.</p>
              </div>
            )}

            {/* Issue cards */}
            {sortedIssues.map(issue => (
              <IssueCard key={issue.issue_id} issue={issue} />
            ))}

            {/* Analysis note */}
            {result.analysis_note && (
              <p className="text-[10px] text-[#3d4466] leading-relaxed border-t border-[#1f2440] pt-2">
                {result.analysis_note}
              </p>
            )}
          </div>
        )}

        {/* Empty state */}
        {!loading && !result && !notEnough && (
          <div className="flex flex-col items-center gap-3 py-6 text-center">
            <ScanSearch className="w-8 h-8 text-[#2e3454]" />
            <div>
              <p className="text-xs text-[#5c6391] font-medium">Analyze your story for issues</p>
              <p className="text-xs text-[#3d4466] mt-1 leading-relaxed">
                Checks for character inconsistencies,<br />
                unresolved threads, and timeline gaps
              </p>
            </div>
          </div>
        )}
    </div>
  )
}
