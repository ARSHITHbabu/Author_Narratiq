'use client'

import { useState } from 'react'
import { Loader2, TrendingUp, AlertCircle, RefreshCw } from 'lucide-react'
import { emotionalArcApi } from '@/lib/api'
import { EmotionalArcResponse, EmotionalArcEntry } from '@/lib/types'
import { toast } from 'sonner'

const TONE_COLORS: Record<string, string> = {
  joyful:     '#f59e0b',
  hopeful:    '#10b981',
  tense:      '#ef4444',
  fearful:    '#8b5cf6',
  melancholic: '#6366f1',
  angry:      '#f97316',
  neutral:    '#6b7280',
  excited:    '#ec4899',
  sad:        '#3b82f6',
  triumphant: '#84cc16',
}

function toneColor(tone: string): string {
  const key = tone?.toLowerCase().split(' ')[0] ?? ''
  return TONE_COLORS[key] ?? '#9da3c8'
}

interface Props { storyId: string }

export default function EmotionalArcPanel({ storyId }: Props) {
  const [data, setData] = useState<EmotionalArcResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [withAssessment, setWithAssessment] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const res = await emotionalArcApi.get(storyId, withAssessment)
      setData(res.data)
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Failed to load emotional arc')
    } finally {
      setLoading(false)
    }
  }

  if (!data && !loading) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 p-6 h-full">
        <TrendingUp className="w-10 h-10 text-[#2e3454]" />
        <p className="text-xs text-[#5c6391] text-center">Map the emotional journey across all chapters</p>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5 cursor-pointer">
            <input
              type="checkbox"
              checked={withAssessment}
              onChange={e => setWithAssessment(e.target.checked)}
              className="accent-amber-500"
            />
            <span className="text-xs text-[#9da3c8]">AI assessment</span>
          </label>
          <button
            onClick={load}
            className="px-3 py-1.5 rounded-lg text-xs bg-amber-500/10 text-amber-400 border border-amber-500/20 hover:bg-amber-500/20 transition-all"
          >
            Generate Arc Map
          </button>
        </div>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full gap-2 text-[#5c6391]">
        <Loader2 className="w-4 h-4 animate-spin" />
        <span className="text-xs">Analysing chapters…</span>
      </div>
    )
  }

  const arc = data!.arc
  if (arc.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 p-6 h-full">
        <AlertCircle className="w-8 h-8 text-[#2e3454]" />
        <p className="text-xs text-[#5c6391] text-center">No indexed chapters found. Index chapters first via AI Tools.</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      <div className="px-4 pt-3 pb-2 flex items-center justify-between flex-shrink-0">
        <span className="text-xs text-[#9da3c8]">{arc.length} chapters · emotional journey</span>
        <button
          onClick={load}
          className="text-[#5c6391] hover:text-amber-400 transition-colors"
          title="Refresh"
        >
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Colour bar — each chapter shown as a full-height block coloured by tone */}
      <div className="px-3 pb-3 flex-shrink-0">
        <div className="flex items-stretch gap-0.5 h-12">
          {arc.map((entry: EmotionalArcEntry) => {
            const color = toneColor(entry.emotional_tone ?? '')
            return (
              <div
                key={entry.chapter_number}
                className="flex-1 group relative cursor-default rounded"
                style={{ backgroundColor: color, opacity: 0.75 }}
                title={`Ch ${entry.chapter_number}: ${entry.emotional_tone ?? 'unknown'}`}
              >
                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 hidden group-hover:block z-10 pointer-events-none">
                  <div className="bg-[#1a1e36] border border-[#2e3454] rounded-md px-2 py-1 text-[10px] text-[#e8eaf6] whitespace-nowrap shadow-xl">
                    Ch {entry.chapter_number}: {entry.emotional_tone ?? 'unknown'}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
        <div className="flex gap-0.5 mt-0.5">
          {arc.map((entry: EmotionalArcEntry) => (
            <div key={entry.chapter_number} className="flex-1 text-[9px] text-[#3d4466] text-center truncate">
              {entry.chapter_number}
            </div>
          ))}
        </div>
      </div>

      {/* Legend */}
      <div className="px-3 pb-2 flex flex-wrap gap-1.5 flex-shrink-0">
        {Object.entries(TONE_COLORS).map(([tone, color]) => {
          const used = arc.some(e => e.emotional_tone?.toLowerCase().startsWith(tone))
          if (!used) return null
          return (
            <span key={tone} className="flex items-center gap-1 text-[10px] text-[#9da3c8]">
              <span className="w-2 h-2 rounded-full inline-block" style={{ backgroundColor: color }} />
              {tone}
            </span>
          )
        })}
      </div>

      {/* Assessment */}
      {data!.assessment && (
        <div className="mx-3 mb-3 p-3 bg-[#0d0f1a] border border-[#1f2440] rounded-xl flex-shrink-0">
          <div className="text-[10px] font-medium text-amber-400 mb-1.5">AI Arc Assessment</div>
          <p className="text-xs text-[#9da3c8] leading-relaxed">{data!.assessment}</p>
        </div>
      )}

      {/* Chapter list */}
      <div className="px-3 flex flex-col gap-1.5 pb-4">
        {arc.map((entry: EmotionalArcEntry) => (
          <div key={entry.chapter_number} className="flex items-center gap-2 text-xs">
            <span className="text-[#3d4466] w-10 flex-shrink-0">Ch {entry.chapter_number}</span>
            <span
              className="w-2 h-2 rounded-full flex-shrink-0"
              style={{ backgroundColor: toneColor(entry.emotional_tone ?? '') }}
            />
            <span className="text-[#9da3c8] truncate flex-1">{entry.emotional_tone ?? '—'}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
