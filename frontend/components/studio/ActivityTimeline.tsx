'use client'

// Global Activity Timeline — a slide-over from the Studio Shell showing the
// project-wide history of meaningful actions (AI, analysis, project, voice, export).
// Filterable + searchable. Reads /api/stories/{id}/activity via React Query. Built
// to evolve toward audit/recovery/collaboration — not a version-history system.

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { X, Search, Sparkles, BarChart3, FolderGit2, Mic, Upload } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { activityApi } from '@/lib/api'
import { useStoryContext } from './StoryContextEngine'

const CATS = [
  { id: '', label: 'All' },
  { id: 'ai', label: 'AI' },
  { id: 'analysis', label: 'Analysis' },
  { id: 'project', label: 'Project' },
  { id: 'voice', label: 'Voice' },
  { id: 'export', label: 'Export' },
]
const ICONS: Record<string, typeof Sparkles> = {
  ai: Sparkles, analysis: BarChart3, project: FolderGit2, voice: Mic, export: Upload,
}

interface Event {
  event_id: string; category: string; type: string; title: string; summary: string; created_at: string | null
}

export default function ActivityTimeline({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { storyId } = useStoryContext()
  const [cat, setCat] = useState('')
  const [q, setQ] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['activity', storyId, cat, q],
    queryFn: async () => (await activityApi.list(storyId, { category: cat || undefined, q: q || undefined, limit: 200 })).data as Event[],
    enabled: open,
  })

  if (!open) return null
  return (
    <div className="fixed inset-0 z-40">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <aside className="absolute right-0 top-0 h-full w-full max-w-md bg-[#0f1220] border-l border-[#1f2440] flex flex-col shadow-2xl">
        <div className="h-11 flex items-center justify-between px-3 border-b border-[#1f2440]">
          <span className="text-sm font-medium text-[#e8eaf6]">Activity</span>
          <button onClick={onClose} className="p-1.5 rounded text-[#9da3c8] hover:text-white hover:bg-[#1f2440]"><X className="w-4 h-4" /></button>
        </div>
        <div className="p-3 space-y-2 border-b border-[#1f2440]">
          <div className="flex items-center gap-2 px-2 py-1.5 rounded bg-[#13162a] border border-[#1f2440]">
            <Search className="w-3.5 h-3.5 text-[#5c6391]" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search activity…"
              className="flex-1 bg-transparent text-xs text-[#e8eaf6] placeholder-[#5c6391] outline-none" />
          </div>
          <div className="flex flex-wrap gap-1">
            {CATS.map((c) => (
              <button key={c.id} onClick={() => setCat(c.id)}
                className={`text-[11px] px-2 py-0.5 rounded-full border ${cat === c.id ? 'border-amber-500/40 bg-amber-500/10 text-amber-300' : 'border-[#2e3454] text-[#9da3c8] hover:text-white'}`}>
                {c.label}
              </button>
            ))}
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-3 space-y-2">
          {isLoading && <p className="text-xs text-[#5c6391] text-center py-6">Loading…</p>}
          {!isLoading && (data?.length ?? 0) === 0 && (
            <p className="text-xs text-[#5c6391] text-center py-10">No activity yet. Your AI actions, analyses, exports and edits will appear here.</p>
          )}
          {(data ?? []).map((e) => {
            const Icon = ICONS[e.category] ?? Sparkles
            return (
              <div key={e.event_id} className="flex gap-2.5 rounded-md border border-[#1f2440] bg-[#13162a] px-3 py-2">
                <Icon className="w-4 h-4 text-[#9da3c8] mt-0.5 flex-shrink-0" />
                <div className="min-w-0">
                  <p className="text-xs text-[#cdd2f0]">{e.title || e.type}</p>
                  {e.summary && <p className="text-[11px] text-[#9da3c8] mt-0.5 line-clamp-2">{e.summary}</p>}
                  <p className="text-[10px] text-[#5c6391] mt-0.5">
                    {e.created_at ? formatDistanceToNow(new Date(e.created_at), { addSuffix: true }) : ''} · {e.category}
                  </p>
                </div>
              </div>
            )
          })}
        </div>
      </aside>
    </div>
  )
}
