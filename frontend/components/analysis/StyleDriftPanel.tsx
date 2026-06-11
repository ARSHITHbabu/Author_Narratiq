'use client'

import { useState } from 'react'
import { Loader2, PenLine, RefreshCw, AlertCircle } from 'lucide-react'
import { styleDriftApi } from '@/lib/api'
import { StyleDriftResponse } from '@/lib/types'
import { toast } from 'sonner'

interface Props { storyId: string }

function DriftGauge({ score }: { score: number }) {
  const pct = Math.round(score * 100)
  const color = pct < 30 ? '#10b981'
              : pct < 60 ? '#f59e0b'
              : '#ef4444'
  const label = pct < 30 ? 'Consistent'
              : pct < 60 ? 'Some Drift'
              : 'Significant Drift'

  return (
    <div className="flex flex-col items-center gap-2 py-4">
      <div className="relative w-20 h-20">
        <svg viewBox="0 0 36 36" className="w-20 h-20 -rotate-90">
          <circle cx="18" cy="18" r="15.9" fill="none" stroke="#1f2440" strokeWidth="3.5" />
          <circle
            cx="18" cy="18" r="15.9" fill="none"
            stroke={color} strokeWidth="3.5"
            strokeDasharray={`${pct} ${100 - pct}`}
            strokeLinecap="round"
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-lg font-bold" style={{ color }}>{pct}</span>
        </div>
      </div>
      <span className="text-xs font-medium" style={{ color }}>{label}</span>
    </div>
  )
}

export default function StyleDriftPanel({ storyId }: Props) {
  const [data, setData] = useState<StyleDriftResponse | null>(null)
  const [loading, setLoading] = useState(false)

  const check = async () => {
    setLoading(true)
    try {
      const res = await styleDriftApi.check(storyId)
      setData(res.data)
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Style drift check failed')
    } finally {
      setLoading(false)
    }
  }

  if (!data && !loading) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 p-6 h-full">
        <PenLine className="w-10 h-10 text-[#2e3454]" />
        <p className="text-xs text-[#5c6391] text-center">Detect if your writing style has shifted between early and late chapters</p>
        <button
          onClick={check}
          className="px-3 py-1.5 rounded-lg text-xs bg-amber-500/10 text-amber-400 border border-amber-500/20 hover:bg-amber-500/20 transition-all"
        >
          Analyse Style Drift
        </button>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full gap-2 text-[#5c6391]">
        <Loader2 className="w-4 h-4 animate-spin" />
        <span className="text-xs">Analysing writing style…</span>
      </div>
    )
  }

  const d = data!

  if (d.status === 'insufficient_data') {
    return (
      <div className="flex flex-col items-center justify-center gap-3 p-6 h-full">
        <AlertCircle className="w-8 h-8 text-[#2e3454]" />
        <p className="text-xs text-[#5c6391] text-center">Need at least 6 indexed chapters to detect style drift.</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      <div className="px-4 pt-3 pb-1 flex items-center justify-between flex-shrink-0">
        <span className="text-xs text-[#9da3c8]">{(d.early_chapters?.length ?? 0) + (d.late_chapters?.length ?? 0)} chapters analysed</span>
        <button onClick={check} className="text-[#5c6391] hover:text-amber-400" title="Refresh">
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      </div>

      <DriftGauge score={d.drift_score ?? 0} />

      {d.description && (
        <div className="mx-3 mb-3 p-3 bg-[#0d0f1a] border border-[#1f2440] rounded-xl">
          <div className="text-[10px] font-medium text-amber-400 mb-1.5">AI Analysis</div>
          <p className="text-xs text-[#9da3c8] leading-relaxed">{d.description}</p>
        </div>
      )}

      <div className="grid grid-cols-2 gap-2 px-3 pb-4">
        {d.sample_early && (
          <div className="bg-[#0d0f1a] border border-[#1f2440] rounded-xl p-3">
            <div className="text-[10px] font-medium text-emerald-400 mb-1.5">Early Style</div>
            <p className="text-[11px] text-[#9da3c8] leading-relaxed line-clamp-6 italic">"{d.sample_early}"</p>
          </div>
        )}
        {d.sample_late && (
          <div className="bg-[#0d0f1a] border border-[#1f2440] rounded-xl p-3">
            <div className="text-[10px] font-medium text-purple-400 mb-1.5">Late Style</div>
            <p className="text-[11px] text-[#9da3c8] leading-relaxed line-clamp-6 italic">"{d.sample_late}"</p>
          </div>
        )}
      </div>
    </div>
  )
}
