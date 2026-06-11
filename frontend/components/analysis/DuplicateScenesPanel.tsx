'use client'

import { useState } from 'react'
import { Loader2, Copy, AlertCircle, RefreshCw } from 'lucide-react'
import { duplicateScenesApi } from '@/lib/api'
import { DuplicateScenesResponse, DuplicatePair } from '@/lib/types'
import { toast } from 'sonner'

interface Props { storyId: string }

function SimilarityBadge({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const color = pct >= 90 ? 'text-red-400 bg-red-500/10 border-red-500/20'
              : pct >= 80 ? 'text-orange-400 bg-orange-500/10 border-orange-500/20'
              : 'text-yellow-400 bg-yellow-500/10 border-yellow-500/20'
  return (
    <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded border ${color}`}>
      {pct}% match
    </span>
  )
}

export default function DuplicateScenesPanel({ storyId }: Props) {
  const [data, setData] = useState<DuplicateScenesResponse | null>(null)
  const [loading, setLoading] = useState(false)

  const detect = async () => {
    setLoading(true)
    try {
      const res = await duplicateScenesApi.detect(storyId)
      setData(res.data)
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Detection failed')
    } finally {
      setLoading(false)
    }
  }

  if (!data && !loading) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 p-6 h-full">
        <Copy className="w-10 h-10 text-[#2e3454]" />
        <p className="text-xs text-[#5c6391] text-center">Find chapters with highly similar content using semantic search</p>
        <button
          onClick={detect}
          className="px-3 py-1.5 rounded-lg text-xs bg-amber-500/10 text-amber-400 border border-amber-500/20 hover:bg-amber-500/20 transition-all"
        >
          Detect Duplicates
        </button>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full gap-2 text-[#5c6391]">
        <Loader2 className="w-4 h-4 animate-spin" />
        <span className="text-xs">Scanning chapters…</span>
      </div>
    )
  }

  const pairs = data!.pairs
  return (
    <div className="flex flex-col h-full overflow-y-auto">
      <div className="px-4 pt-3 pb-2 flex items-center justify-between flex-shrink-0">
        <span className="text-xs text-[#9da3c8]">{pairs.length} duplicate pair(s) found</span>
        <button onClick={detect} className="text-[#5c6391] hover:text-amber-400" title="Refresh">
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      </div>

      {pairs.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-3 p-6">
          <AlertCircle className="w-8 h-8 text-emerald-500/40" />
          <p className="text-xs text-[#5c6391] text-center">No highly similar chapters detected. Your content is unique.</p>
        </div>
      ) : (
        <div className="flex flex-col gap-3 px-3 pb-4">
          {pairs.map((pair: DuplicatePair, i: number) => (
            <div key={i} className="bg-[#0d0f1a] border border-[#1f2440] rounded-xl p-3">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[11px] font-medium text-[#c8cce8]">
                  Ch {pair.chapter_a} × Ch {pair.chapter_b}
                </span>
                <SimilarityBadge value={pair.similarity_score} />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <div className="text-[10px] text-[#5c6391] mb-1 truncate">{pair.a_title}</div>
                  <p className="text-[11px] text-[#9da3c8] leading-relaxed line-clamp-3 italic">"{pair.a_snippet}"</p>
                </div>
                <div>
                  <div className="text-[10px] text-[#5c6391] mb-1 truncate">{pair.b_title}</div>
                  <p className="text-[11px] text-[#9da3c8] leading-relaxed line-clamp-3 italic">"{pair.b_snippet}"</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
