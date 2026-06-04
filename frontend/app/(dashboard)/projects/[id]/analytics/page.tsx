'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { ArrowLeft, BarChart3, BookOpen, FileText, Clock, Feather, Loader2, TrendingUp } from 'lucide-react'
import { projectsApi, chaptersApi } from '@/lib/api'
import { Story, Chapter } from '@/lib/types'
import { toast } from 'sonner'

function readabilityScore(text: string): number {
  if (!text.trim()) return 0
  const sentences = text.split(/[.!?]+/).filter((s) => s.trim().length > 0)
  const words = text.trim().split(/\s+/)
  const syllables = words.reduce((acc, w) => acc + Math.max(1, w.replace(/[^aeiou]/gi, '').length), 0)
  if (sentences.length === 0 || words.length === 0) return 0
  const fk = 206.835 - 1.015 * (words.length / sentences.length) - 84.6 * (syllables / words.length)
  return Math.round(Math.max(0, Math.min(100, fk)))
}

function dialogueRatio(text: string): number {
  const dialogue = (text.match(/[""][^""]*[""]/g) || []).join('').length
  return text.length > 0 ? Math.round((dialogue / text.length) * 100) : 0
}

function avgSentenceLength(text: string): number {
  const sentences = text.split(/[.!?]+/).filter((s) => s.trim().length > 5)
  if (sentences.length === 0) return 0
  const total = sentences.reduce((a, s) => a + s.trim().split(/\s+/).length, 0)
  return Math.round(total / sentences.length)
}

export default function AnalyticsPage({ params }: { params: { id: string } }) {
  const { id: storyId } = params
  const [story, setStory] = useState<Story | null>(null)
  const [chapters, setChapters] = useState<Chapter[]>([])
  const [chapterContents, setChapterContents] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      try {
        const [sr, cr] = await Promise.all([projectsApi.get(storyId), chaptersApi.list(storyId)])
        setStory(sr.data)
        const chs: Chapter[] = cr.data
        setChapters(chs)
        // Load content for each chapter (for metrics)
        const contents: Record<string, string> = {}
        await Promise.all(
          chs.map(async (ch) => {
            try {
              const r = await chaptersApi.get(storyId, ch.chapter_id)
              contents[ch.chapter_id] = r.data.content?.replace(/<[^>]+>/g, ' ') || ''
            } catch {}
          })
        )
        setChapterContents(contents)
      } catch {
        toast.error('Failed to load analytics')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [storyId])

  const allText = Object.values(chapterContents).join(' ')
  const totalWords = story?.word_count || 0
  const avgWC = chapters.length > 0 ? Math.round(totalWords / chapters.length) : 0
  const overallReadability = readabilityScore(allText)
  const overallDialogue = dialogueRatio(allText)
  const overallAvgSentence = avgSentenceLength(allText)
  const targetNovelWords = 80000
  const progressPct = Math.min(100, Math.round((totalWords / targetNovelWords) * 100))

  const metrics = [
    { label: 'Total Words', value: totalWords.toLocaleString(), icon: FileText, color: 'text-amber-400' },
    { label: 'Chapters', value: chapters.length, icon: BookOpen, color: 'text-blue-400' },
    { label: 'Avg Words/Chapter', value: avgWC.toLocaleString(), icon: BarChart3, color: 'text-green-400' },
    { label: 'Readability Score', value: `${overallReadability}/100`, icon: TrendingUp, color: 'text-purple-400' },
    { label: 'Dialogue Ratio', value: `${overallDialogue}%`, icon: Clock, color: 'text-pink-400' },
    { label: 'Avg Sentence Length', value: `${overallAvgSentence} words`, icon: FileText, color: 'text-cyan-400' },
  ]

  if (loading) {
    return (
      <div className="h-screen bg-[#0d0f1a] flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-amber-500" />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#0d0f1a]">
      {/* Nav */}
      <nav className="fixed top-0 left-0 right-0 z-50 bg-[#0d0f1a] border-b border-[#1f2440]">
        <div className="max-w-5xl mx-auto px-6 h-14 flex items-center gap-3">
          <Link href={`/projects/${storyId}`} className="text-[#5c6391] hover:text-amber-400">
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <div className="w-px h-4 bg-[#2e3454]" />
          <Feather className="w-4 h-4 text-amber-500" />
          <span className="text-sm font-medium text-[#9da3c8]">{story?.title}</span>
          <span className="text-[#3d4466] text-sm">/ Analytics</span>
        </div>
      </nav>

      <div className="max-w-5xl mx-auto px-6 pt-24 pb-16">
        <div className="mb-8">
          <h1 className="text-2xl font-bold mb-1">Writing Statistics</h1>
          <p className="text-[#5c6391] text-sm">Narrative analytics for {story?.title}</p>
        </div>

        {/* Novel progress */}
        <div className="bg-[#13162a] border border-[#1f2440] rounded-2xl p-6 mb-6">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-medium">Novel Progress</span>
            <span className="text-sm text-amber-400">{progressPct}% of 80,000 words</span>
          </div>
          <div className="h-3 bg-[#0d0f1a] rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-amber-500 to-amber-600 rounded-full transition-all"
              style={{ width: `${progressPct}%` }}
            />
          </div>
          <div className="flex justify-between mt-2 text-xs text-[#5c6391]">
            <span>{totalWords.toLocaleString()} written</span>
            <span>{Math.max(0, 80000 - totalWords).toLocaleString()} remaining</span>
          </div>
        </div>

        {/* Metric cards */}
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
          {metrics.map((m) => (
            <div key={m.label} className="bg-[#13162a] border border-[#1f2440] rounded-xl p-5">
              <div className="flex items-center gap-2 text-[#5c6391] mb-2">
                <m.icon className="w-3.5 h-3.5" />
                <span className="text-xs">{m.label}</span>
              </div>
              <div className={`text-2xl font-bold ${m.color}`}>{m.value}</div>
            </div>
          ))}
        </div>

        {/* Chapter breakdown */}
        <div className="bg-[#13162a] border border-[#1f2440] rounded-2xl overflow-hidden">
          <div className="px-6 py-4 border-b border-[#1f2440]">
            <h2 className="font-semibold">Chapter Breakdown</h2>
          </div>
          <div className="divide-y divide-[#1f2440]">
            {chapters.map((ch) => {
              const text = chapterContents[ch.chapter_id] || ''
              const rd = readabilityScore(text)
              const dr = dialogueRatio(text)
              const asl = avgSentenceLength(text)
              const maxWC = Math.max(...chapters.map((c) => c.word_count), 1)
              const barW = Math.round((ch.word_count / maxWC) * 100)

              return (
                <div key={ch.chapter_id} className="px-6 py-4 hover:bg-[#1a1e36] transition-colors">
                  <div className="flex items-center justify-between mb-2">
                    <div>
                      <span className="text-xs text-[#5c6391] mr-2">Ch.{ch.chapter_number}</span>
                      <span className="text-sm font-medium text-[#e8eaf6]">{ch.title}</span>
                    </div>
                    <div className="flex items-center gap-4 text-xs text-[#5c6391]">
                      <span>{ch.word_count.toLocaleString()} words</span>
                      <span className="hidden sm:block">Readability: <span className="text-[#9da3c8]">{rd}</span></span>
                      <span className="hidden sm:block">Dialogue: <span className="text-[#9da3c8]">{dr}%</span></span>
                    </div>
                  </div>
                  <div className="h-1.5 bg-[#0d0f1a] rounded-full overflow-hidden">
                    <div
                      className="h-full bg-amber-500/50 rounded-full"
                      style={{ width: `${barW}%` }}
                    />
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Phase 2 features notice */}
        <div className="mt-6 bg-[#13162a] border border-[#1f2440] rounded-2xl p-6">
          <h2 className="font-semibold mb-3 text-[#9da3c8]">Phase 2 Analytics (Coming Soon)</h2>
          <div className="grid sm:grid-cols-3 gap-3">
            {[
              { title: 'Emotion Flow Graph', desc: 'Visualize emotional arc chapter-by-chapter' },
              { title: 'Pacing Analysis', desc: 'Scene rhythm and tension mapping' },
              { title: 'Plot Hole Detection', desc: 'Cross-chapter contradiction analysis' },
            ].map((f) => (
              <div key={f.title} className="border border-[#2e3454] rounded-xl p-4 opacity-60">
                <div className="text-sm font-medium text-[#9da3c8] mb-1">{f.title}</div>
                <div className="text-xs text-[#5c6391]">{f.desc}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
