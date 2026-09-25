'use client'

// Analyze Workspace — the Intelligence Dashboard. Promotes the 7 previously-buried
// analyses (continuity, arc, threads, style drift, dupes, plot holes, report) to ONE
// level as a card grid, plus genre intelligence & writing metrics. Panels are reused
// as-is from the Panel Registry. Deep-linkable via the engine's activeAnalysis memory.

import { useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { ArrowLeft, Sparkles, BarChart3 } from 'lucide-react'
import { PANELS, panelById } from '@/lib/registries/panels'
import { useStoryContext } from '@/components/studio/StoryContextEngine'

export default function AnalyzeWorkspace() {
  const router = useRouter()
  const { storyId, activeAnalysis, setActiveAnalysis } = useStoryContext()

  const open = activeAnalysis ? panelById(activeAnalysis) : undefined
  // Focus management (8.9): opening a panel moves focus to its heading; going
  // back returns it to the card the author came from.
  const headingRef = useRef<HTMLHeadingElement | null>(null)
  const lastCard = useRef<string | null>(null)
  useEffect(() => {
    if (open) headingRef.current?.focus()
    else if (lastCard.current) document.querySelector<HTMLElement>(`[data-panel-card="${lastCard.current}"]`)?.focus()
  }, [open])

  if (open) {
    const Panel = open.component
    return (
      <div className="h-full flex flex-col bg-[#0d0f1a]">
        <div className="h-10 flex items-center gap-2 px-3 border-b border-[#1f2440] flex-shrink-0">
          <button onClick={() => setActiveAnalysis(null)} aria-label="Back to all analyses"
            className="p-1.5 rounded text-[#9da3c8] hover:text-white hover:bg-[#1f2440] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/70"><ArrowLeft className="w-4 h-4" aria-hidden="true" /></button>
          <open.icon className="w-4 h-4 text-amber-400" aria-hidden="true" />
          <h1 ref={headingRef} tabIndex={-1} className="text-sm text-[#e8eaf6] focus:outline-none">{open.title}</h1>
        </div>
        <div className="flex-1 overflow-y-auto"><Panel storyId={storyId} /></div>
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto bg-[#0d0f1a]">
      <div className="max-w-5xl mx-auto px-6 py-6">
        <div className="flex items-center gap-2 mb-1">
          <BarChart3 className="w-5 h-5 text-amber-400" />
          <h1 className="text-xl font-semibold text-[#e8eaf6]">Story Intelligence</h1>
        </div>
        <p className="text-sm text-[#9da3c8] mb-5">Every analysis in one place. Run on demand — results are grounded in your manuscript.</p>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {PANELS.map((p) => (
            <button key={p.id} data-panel-card={p.id} onClick={() => { lastCard.current = p.id; setActiveAnalysis(p.id) }}
              className="text-left rounded-lg border border-[#1f2440] bg-[#13162a] hover:border-[#3d4466] hover:bg-[#1a1e36] transition p-4">
              <div className="flex items-center gap-2 mb-1.5">
                <span className="w-8 h-8 rounded-lg bg-amber-500/10 flex items-center justify-center"><p.icon className="w-4 h-4 text-amber-400" /></span>
                <span className="text-sm font-medium text-[#e8eaf6]">{p.title}</span>
              </div>
              <p className="text-xs text-[#9da3c8] leading-relaxed">{p.blurb}</p>
            </button>
          ))}

          {/* Genre intelligence + writing metrics reuse the existing routes */}
          <button onClick={() => router.push(`/projects/${storyId}/intake`)}
            className="text-left rounded-lg border border-[#1f2440] bg-[#13162a] hover:border-[#3d4466] hover:bg-[#1a1e36] transition p-4">
            <div className="flex items-center gap-2 mb-1.5">
              <span className="w-8 h-8 rounded-lg bg-sky-500/10 flex items-center justify-center"><Sparkles className="w-4 h-4 text-sky-400" /></span>
              <span className="text-sm font-medium text-[#e8eaf6]">Genre Intelligence</span>
            </div>
            <p className="text-xs text-[#9da3c8]">Genre, tone, audience, POV, comparable titles, content warnings.</p>
          </button>
          <button onClick={() => router.push(`/projects/${storyId}/analytics`)}
            className="text-left rounded-lg border border-[#1f2440] bg-[#13162a] hover:border-[#3d4466] hover:bg-[#1a1e36] transition p-4">
            <div className="flex items-center gap-2 mb-1.5">
              <span className="w-8 h-8 rounded-lg bg-emerald-500/10 flex items-center justify-center"><BarChart3 className="w-4 h-4 text-emerald-400" /></span>
              <span className="text-sm font-medium text-[#e8eaf6]">Writing Metrics</span>
            </div>
            <p className="text-xs text-[#9da3c8]">Word counts, readability, dialogue ratio, sentence length, progress.</p>
          </button>
        </div>
      </div>
    </div>
  )
}
