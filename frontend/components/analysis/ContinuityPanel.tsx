'use client'

import { useState } from 'react'
import { Loader2, Link2, RefreshCw, CheckCircle2, ChevronDown, ChevronRight } from 'lucide-react'
import { continuityApi } from '@/lib/api'
import { ContinuityCheckResponse, ContinuityIssue } from '@/lib/types'
import { toast } from 'sonner'

interface Props { storyId: string }

const SEVERITY_STYLES: Record<string, string> = {
  high:   'text-red-400 bg-red-500/10 border-red-500/20',
  medium: 'text-orange-400 bg-orange-500/10 border-orange-500/20',
  low:    'text-yellow-400 bg-yellow-500/10 border-yellow-500/20',
}

function IssueCard({ issue }: { issue: ContinuityIssue }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="bg-[#0d0f1a] border border-[#1f2440] rounded-xl overflow-hidden">
      <button
        className="w-full flex items-start gap-2 p-3 text-left"
        onClick={() => setOpen(v => !v)}
      >
        {open ? <ChevronDown className="w-3.5 h-3.5 text-[#5c6391] mt-0.5 flex-shrink-0" /> : <ChevronRight className="w-3.5 h-3.5 text-[#5c6391] mt-0.5 flex-shrink-0" />}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded border ${SEVERITY_STYLES[issue.severity] ?? SEVERITY_STYLES.low}`}>
              {issue.severity}
            </span>
            <span className="text-[10px] text-[#5c6391] font-medium">{issue.type.replace(/_/g, ' ')}</span>
          </div>
          <p className="text-xs text-[#c8cce8] leading-snug line-clamp-2">{issue.description}</p>
          <p className="text-[10px] text-[#5c6391] mt-1">
            Ch {issue.chapter_refs.join(', ')}
          </p>
        </div>
      </button>
      {open && issue.resolution_hint && (
        <div className="px-3 pb-3 pl-8">
          <div className="text-[10px] text-emerald-400 font-medium mb-1">Suggestion</div>
          <p className="text-xs text-[#9da3c8] leading-relaxed">{issue.resolution_hint}</p>
        </div>
      )}
    </div>
  )
}

export default function ContinuityPanel({ storyId }: Props) {
  const [data, setData] = useState<ContinuityCheckResponse | null>(null)
  const [loading, setLoading] = useState(false)

  const scan = async () => {
    setLoading(true)
    try {
      const res = await continuityApi.check(storyId)
      setData(res.data)
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Continuity check failed')
    } finally {
      setLoading(false)
    }
  }

  if (!data && !loading) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 p-6 h-full">
        <Link2 className="w-10 h-10 text-[#2e3454]" />
        <p className="text-xs text-[#5c6391] text-center">Scan for continuity errors, character inconsistencies, and world-building contradictions</p>
        <button
          onClick={scan}
          className="px-3 py-1.5 rounded-lg text-xs bg-amber-500/10 text-amber-400 border border-amber-500/20 hover:bg-amber-500/20 transition-all"
        >
          Run Continuity Scan
        </button>
        <p className="text-[10px] text-[#3d4466] text-center">For large manuscripts this may take 30–60 s</p>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-2 text-[#5c6391]">
        <Loader2 className="w-4 h-4 animate-spin" />
        <span className="text-xs">Scanning all chapters…</span>
      </div>
    )
  }

  const issues = data!.issues
  const high   = issues.filter(i => i.severity === 'high')
  const medium = issues.filter(i => i.severity === 'medium')
  const low    = issues.filter(i => i.severity === 'low')

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      <div className="px-4 pt-3 pb-2 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-xs text-[#9da3c8]">{issues.length} issue(s)</span>
          {high.length > 0 && <span className="text-[10px] text-red-400">{high.length} high</span>}
          {medium.length > 0 && <span className="text-[10px] text-orange-400">{medium.length} med</span>}
        </div>
        <button onClick={scan} className="text-[#5c6391] hover:text-amber-400" title="Refresh">
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      </div>

      {issues.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-3 p-6">
          <CheckCircle2 className="w-8 h-8 text-emerald-500/60" />
          <p className="text-xs text-[#5c6391] text-center">No continuity issues detected. Great consistency!</p>
        </div>
      ) : (
        <div className="flex flex-col gap-2 px-3 pb-4">
          {[...high, ...medium, ...low].map((issue, i) => (
            <IssueCard key={i} issue={issue} />
          ))}
        </div>
      )}
    </div>
  )
}
