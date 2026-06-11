'use client'

import { useState, useEffect } from 'react'
import { Loader2, Target, Save, BarChart2 } from 'lucide-react'
import { pacingApi } from '@/lib/api'
import { PacingGoalResponse, ChapterWordCount } from '@/lib/types'
import { toast } from 'sonner'

interface Props { storyId: string }

function ProgressBar({ value, color = '#f59e0b' }: { value: number; color?: string }) {
  return (
    <div className="w-full h-2 bg-[#1f2440] rounded-full overflow-hidden">
      <div
        className="h-full rounded-full transition-all"
        style={{ width: `${Math.min(value, 100)}%`, backgroundColor: color }}
      />
    </div>
  )
}

function ChapterBar({ chapter, max }: { chapter: ChapterWordCount; max: number }) {
  const width = max > 0 ? (chapter.word_count / max) * 100 : 0
  return (
    <div className="flex items-center gap-2 text-[10px]">
      <span className="text-[#3d4466] w-6 text-right flex-shrink-0">{chapter.chapter_number}</span>
      <div className="flex-1 h-3 bg-[#1f2440] rounded-sm overflow-hidden">
        <div
          className="h-full rounded-sm"
          style={{ width: `${width}%`, backgroundColor: '#6366f1', opacity: 0.8 }}
          title={`${chapter.word_count.toLocaleString()} words`}
        />
      </div>
      <span className="text-[#5c6391] w-12 text-right flex-shrink-0">{chapter.word_count.toLocaleString()}</span>
    </div>
  )
}

export default function PacingGoalPanel({ storyId }: Props) {
  const [data, setData] = useState<PacingGoalResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [editMode, setEditMode] = useState(false)

  const [targetWC,  setTargetWC]  = useState('')
  const [targetCC,  setTargetCC]  = useState('')
  const [targetWPC, setTargetWPC] = useState('')

  const load = async () => {
    try {
      const res = await pacingApi.get(storyId)
      const d: PacingGoalResponse = res.data
      setData(d)
      setTargetWC(d.target_word_count > 0 ? String(d.target_word_count) : '')
      setTargetCC(d.target_chapter_count > 0 ? String(d.target_chapter_count) : '')
      setTargetWPC(d.target_words_per_chapter > 0 ? String(d.target_words_per_chapter) : '')
    } catch {
      toast.error('Failed to load pacing data')
    } finally {
      setLoading(false)
    }
  }

  const save = async () => {
    setSaving(true)
    try {
      const res = await pacingApi.set(
        storyId,
        Number(targetWC)  || 0,
        Number(targetCC)  || 0,
        Number(targetWPC) || 0,
      )
      setData(res.data)
      setEditMode(false)
      toast.success('Pacing goals saved')
    } catch {
      toast.error('Failed to save goals')
    } finally {
      setSaving(false)
    }
  }

  useEffect(() => { load() }, [storyId])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full gap-2 text-[#5c6391]">
        <Loader2 className="w-4 h-4 animate-spin" />
        <span className="text-xs">Loading pacing data…</span>
      </div>
    )
  }

  const d = data!
  const maxWC = Math.max(...(d.chapter_distribution.map(c => c.word_count)), 1)

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      <div className="px-3 pt-3 pb-2 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-1.5">
          <Target className="w-3.5 h-3.5 text-amber-500" />
          <span className="text-xs font-medium text-[#9da3c8]">Pacing Goals</span>
        </div>
        <button
          onClick={() => setEditMode(v => !v)}
          className="text-[10px] text-[#5c6391] hover:text-amber-400 border border-[#2e3454] px-2 py-0.5 rounded"
        >
          {editMode ? 'Cancel' : 'Edit'}
        </button>
      </div>

      {editMode ? (
        <div className="px-3 flex flex-col gap-3 pb-3">
          {[
            { label: 'Target word count',          val: targetWC,  set: setTargetWC,  placeholder: 'e.g. 80000'  },
            { label: 'Target chapter count',       val: targetCC,  set: setTargetCC,  placeholder: 'e.g. 30'     },
            { label: 'Target words per chapter',   val: targetWPC, set: setTargetWPC, placeholder: 'e.g. 2500'   },
          ].map(({ label, val, set, placeholder }) => (
            <div key={label}>
              <label className="text-[10px] text-[#5c6391] block mb-1">{label}</label>
              <input
                type="number"
                value={val}
                onChange={e => set(e.target.value)}
                placeholder={placeholder}
                className="w-full bg-[#0d0f1a] border border-[#2e3454] rounded-lg px-3 py-1.5 text-xs text-[#e8eaf6] focus:border-amber-500/50 outline-none"
              />
            </div>
          ))}
          <button
            onClick={save}
            disabled={saving}
            className="flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs bg-amber-500/10 text-amber-400 border border-amber-500/20 hover:bg-amber-500/20 transition-all disabled:opacity-50"
          >
            {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
            Save Goals
          </button>
        </div>
      ) : (
        <>
          {/* Progress overview */}
          <div className="px-3 pb-3 flex flex-col gap-3 flex-shrink-0">
            {d.target_word_count > 0 && (
              <div>
                <div className="flex justify-between text-[10px] text-[#9da3c8] mb-1">
                  <span>Word count progress</span>
                  <span className="text-amber-400">{d.progress_pct.toFixed(1)}%</span>
                </div>
                <ProgressBar value={d.progress_pct} />
                <div className="flex justify-between text-[10px] text-[#5c6391] mt-1">
                  <span>{d.actual_word_count.toLocaleString()} words</span>
                  <span>goal: {d.target_word_count.toLocaleString()}</span>
                </div>
              </div>
            )}

            <div className="grid grid-cols-2 gap-2">
              {[
                { label: 'Chapters',       val: d.actual_chapter_count,       target: d.target_chapter_count,       unit: '' },
                { label: 'Avg per chapter', val: d.avg_words_per_chapter,       target: d.target_words_per_chapter,    unit: 'w' },
              ].map(({ label, val, target, unit }) => (
                <div key={label} className="bg-[#0d0f1a] border border-[#1f2440] rounded-xl p-2.5">
                  <div className="text-[10px] text-[#5c6391] mb-1">{label}</div>
                  <div className="text-sm font-bold text-[#e8eaf6]">{val.toLocaleString()}{unit}</div>
                  {target > 0 && (
                    <div className="text-[10px] text-[#5c6391]">goal: {target.toLocaleString()}{unit}</div>
                  )}
                </div>
              ))}
            </div>

            {d.estimated_chapters_remaining > 0 && (
              <div className="text-[11px] text-[#9da3c8] bg-[#0d0f1a] border border-[#1f2440] rounded-xl p-2.5">
                <span className="text-amber-400">{d.estimated_chapters_remaining}</span> chapter(s) remaining to goal
              </div>
            )}
          </div>

          {/* Chapter distribution */}
          {d.chapter_distribution.length > 0 && (
            <div className="px-3 pb-4">
              <div className="flex items-center gap-1.5 mb-2">
                <BarChart2 className="w-3 h-3 text-[#5c6391]" />
                <span className="text-[10px] text-[#5c6391] font-medium uppercase tracking-wider">Chapter Distribution</span>
              </div>
              <div className="flex flex-col gap-1.5">
                {d.chapter_distribution.map(ch => (
                  <ChapterBar key={ch.chapter_number} chapter={ch} max={maxWC} />
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
