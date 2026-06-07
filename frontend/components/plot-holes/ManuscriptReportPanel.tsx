'use client'

import { useState } from 'react'
import {
  BookOpen, Loader2, AlertTriangle, ChevronDown, ChevronUp,
  Users, Zap, Link2, Sparkles, TrendingUp,
} from 'lucide-react'
import { analysisApi } from '@/lib/api'
import {
  ManuscriptReport, CharacterArcEntry, StrengthEntry,
  ImprovementEntry, UnresolvedThread,
} from '@/lib/types'
import { toast } from 'sonner'

function ChPill({ n }: { n: number }) {
  return (
    <span className="text-[10px] text-[#9da3c8] px-1 py-0.5 rounded bg-[#1f2440]">
      Ch{n}
    </span>
  )
}

const COMPLETENESS_STYLES: Record<string, string> = {
  complete:   'bg-green-500/20 text-green-400 border-green-500/30',
  partial:    'bg-amber-500/20 text-amber-400 border-amber-500/30',
  unresolved: 'bg-red-500/20 text-red-400 border-red-500/30',
}

function ArcCard({ arc }: { arc: CharacterArcEntry }) {
  const [expanded, setExpanded] = useState(false)
  const badge = COMPLETENESS_STYLES[arc.completeness] ?? COMPLETENESS_STYLES.partial
  const sorted = [...arc.appears_in].sort((a, b) => a - b)
  const first  = sorted[0]
  const last   = sorted[sorted.length - 1]

  return (
    <div className="border border-[#1f2440] rounded-xl bg-[#0d0f1a] overflow-hidden">
      <button
        className="w-full text-left p-3 flex items-start gap-2.5"
        onClick={() => setExpanded(!expanded)}
      >
        <Users className="w-3.5 h-3.5 mt-0.5 flex-shrink-0 text-[#5c6391]" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap mb-1">
            <span className="text-xs font-medium text-[#c8cce8]">{arc.name}</span>
            <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded border ${badge}`}>
              {arc.completeness}
            </span>
          </div>
          <div className="flex items-center gap-1 flex-wrap">
            {first !== undefined && <ChPill n={first} />}
            {sorted.length > 2 && (
              <span className="text-[10px] text-[#3d4466]">···</span>
            )}
            {last !== undefined && last !== first && <ChPill n={last} />}
            <span className="text-[10px] text-[#3d4466]">
              {sorted.length} chapter{sorted.length !== 1 ? 's' : ''}
            </span>
          </div>
        </div>
        <div className="flex-shrink-0 text-[#3d4466] mt-0.5">
          {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </div>
      </button>
      {expanded && (
        <div className="px-3 pb-3 border-t border-[#1f2440] pt-2.5 space-y-2">
          <p className="text-xs text-[#9da3c8] leading-relaxed">{arc.arc_summary}</p>
          <div className="flex flex-wrap gap-1">
            {sorted.map(n => <ChPill key={n} n={n} />)}
          </div>
        </div>
      )}
    </div>
  )
}

function EvidencedCard({
  text, chapters, color,
}: {
  text: string
  chapters: number[]
  color: 'green' | 'amber'
}) {
  const pillClass = color === 'green'
    ? 'text-[10px] text-green-400 px-1.5 py-0.5 rounded bg-green-500/10'
    : 'text-[10px] text-amber-400 px-1.5 py-0.5 rounded bg-amber-500/10'

  return (
    <div className="bg-[#0d0f1a] border border-[#1f2440] rounded-xl p-3 space-y-2">
      <p className="text-xs text-[#c8cce8] leading-relaxed">{text}</p>
      {chapters.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {[...chapters].sort((a, b) => a - b).map(n => (
            <span key={n} className={pillClass}>Ch{n}</span>
          ))}
        </div>
      )}
    </div>
  )
}

interface Props {
  storyId: string
}

export default function ManuscriptReportPanel({ storyId }: Props) {
  const [loading, setLoading]     = useState(false)
  const [report, setReport]       = useState<ManuscriptReport | null>(null)
  const [notEnough, setNotEnough] = useState(false)

  const runReport = async () => {
    setLoading(true)
    setReport(null)
    setNotEnough(false)
    try {
      const res = await analysisApi.getManuscriptReport(storyId)
      setReport(res.data as ManuscriptReport)
    } catch (err: any) {
      if (err?.response?.status === 422) {
        setNotEnough(true)
      } else {
        toast.error(
          err?.response?.data?.detail || 'Report generation failed. Please try again.',
        )
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4">

      {/* Generate button */}
      <button
        onClick={runReport}
        disabled={loading}
        className="w-full flex items-center justify-center gap-2 py-2.5 px-4 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium rounded-xl transition-colors"
      >
        {loading
          ? <><Loader2 className="w-4 h-4 animate-spin" /> Analyzing manuscript...</>
          : <><BookOpen className="w-4 h-4" /> Generate Report</>
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

      {/* Report */}
      {report && !loading && (
        <div className="flex flex-col gap-4">

          {/* Overview */}
          <div className="bg-[#0d0f1a] border border-[#1f2440] rounded-xl p-3">
            <div className="flex items-center justify-between text-xs text-[#5c6391]">
              <span>{report.chapters_analyzed} chapter{report.chapters_analyzed !== 1 ? 's' : ''} analyzed</span>
              {report.word_count_total > 0 && (
                <span>{report.word_count_total.toLocaleString()} words</span>
              )}
            </div>
          </div>

          {/* Character Arcs */}
          {report.character_arcs.length > 0 && (
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-2">
                <Users className="w-3.5 h-3.5 text-indigo-400" />
                <span className="text-[10px] font-medium text-[#9da3c8] uppercase tracking-wider">
                  Character Arcs
                </span>
                <span className="text-[10px] text-[#3d4466]">
                  ({report.character_arcs.length})
                </span>
              </div>
              {report.character_arcs.map((arc, i) => (
                <ArcCard key={i} arc={arc} />
              ))}
            </div>
          )}

          {/* Pacing */}
          {(
            report.pacing.slow_chapters.length > 0 ||
            report.pacing.intense_chapters.length > 0 ||
            report.pacing.assessment
          ) && (
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-2">
                <Zap className="w-3.5 h-3.5 text-amber-400" />
                <span className="text-[10px] font-medium text-[#9da3c8] uppercase tracking-wider">
                  Pacing
                </span>
              </div>
              <div className="bg-[#0d0f1a] border border-[#1f2440] rounded-xl p-3 space-y-2.5">
                {report.pacing.assessment && (
                  <p className="text-xs text-[#c8cce8] leading-relaxed">
                    {report.pacing.assessment}
                  </p>
                )}
                {report.pacing.slow_chapters.length > 0 && (
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="text-[10px] text-[#5c6391]">Slow:</span>
                    {[...report.pacing.slow_chapters].sort((a, b) => a - b).map(n => (
                      <span key={n} className="text-[10px] text-[#9da3c8] px-1.5 py-0.5 rounded bg-[#1f2440]">
                        Ch{n}
                      </span>
                    ))}
                  </div>
                )}
                {report.pacing.intense_chapters.length > 0 && (
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="text-[10px] text-[#5c6391]">Intense:</span>
                    {[...report.pacing.intense_chapters].sort((a, b) => a - b).map(n => (
                      <span key={n} className="text-[10px] text-amber-400 px-1.5 py-0.5 rounded bg-amber-500/10">
                        Ch{n}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Unresolved Threads */}
          {report.unresolved_threads.length > 0 && (
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-2">
                <Link2 className="w-3.5 h-3.5 text-red-400" />
                <span className="text-[10px] font-medium text-[#9da3c8] uppercase tracking-wider">
                  Unresolved Threads
                </span>
                <span className="text-[10px] text-[#3d4466]">
                  ({report.unresolved_threads.length})
                </span>
              </div>
              {report.unresolved_threads.map((thread, i) => (
                <div key={i} className="bg-[#0d0f1a] border border-red-500/20 rounded-xl p-3 space-y-2">
                  <p className="text-xs text-[#c8cce8] leading-relaxed">{thread.description}</p>
                  <div className="flex items-center gap-1.5 flex-wrap">
                    {thread.introduced_in > 0 && (
                      <span className="text-[10px] text-red-400 px-1.5 py-0.5 rounded bg-red-500/10">
                        Intro: Ch{thread.introduced_in}
                      </span>
                    )}
                    {thread.chapters
                      .filter(n => n !== thread.introduced_in)
                      .sort((a, b) => a - b)
                      .map(n => (
                        <span key={n} className="text-[10px] text-[#9da3c8] px-1 py-0.5 rounded bg-[#1f2440]">
                          Ch{n}
                        </span>
                      ))
                    }
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Strengths */}
          {report.strengths.length > 0 && (
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-2">
                <Sparkles className="w-3.5 h-3.5 text-green-400" />
                <span className="text-[10px] font-medium text-[#9da3c8] uppercase tracking-wider">
                  Strengths
                </span>
              </div>
              {report.strengths.map((s, i) => (
                <EvidencedCard key={i} text={s.text} chapters={s.chapters} color="green" />
              ))}
            </div>
          )}

          {/* Improvements */}
          {report.improvements.length > 0 && (
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-2">
                <TrendingUp className="w-3.5 h-3.5 text-amber-400" />
                <span className="text-[10px] font-medium text-[#9da3c8] uppercase tracking-wider">
                  Areas for Improvement
                </span>
              </div>
              {report.improvements.map((imp, i) => (
                <EvidencedCard key={i} text={imp.text} chapters={imp.chapters} color="amber" />
              ))}
            </div>
          )}

          {/* Analysis note */}
          {report.analysis_note && (
            <p className="text-[10px] text-[#3d4466] leading-relaxed border-t border-[#1f2440] pt-2">
              {report.analysis_note}
            </p>
          )}
        </div>
      )}

      {/* Empty state */}
      {!loading && !report && !notEnough && (
        <div className="flex flex-col items-center gap-3 py-6 text-center">
          <BookOpen className="w-8 h-8 text-[#2e3454]" />
          <div>
            <p className="text-xs text-[#5c6391] font-medium">Editorial analysis report</p>
            <p className="text-xs text-[#3d4466] mt-1 leading-relaxed">
              Character arcs, pacing, unresolved threads,<br />
              strengths, and improvement suggestions
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
