'use client'

import { useState, useEffect } from 'react'
import { Loader2, GitBranch, RefreshCw, ChevronDown, ChevronRight } from 'lucide-react'
import { narrativeThreadsApi } from '@/lib/api'
import { NarrativeThreadOut, NarrativeScanResponse } from '@/lib/types'
import { toast } from 'sonner'

interface Props { storyId: string }

const STATUS_STYLES: Record<string, { label: string; badge: string }> = {
  open:     { label: 'Open',     badge: 'text-blue-400 bg-blue-500/10 border-blue-500/20' },
  dead_end: { label: 'Dead End', badge: 'text-red-400 bg-red-500/10 border-red-500/20' },
  resolved: { label: 'Resolved', badge: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20' },
}

function ThreadCard({ thread, storyId, onUpdated }: { thread: NarrativeThreadOut; storyId: string; onUpdated: () => void }) {
  const [open, setOpen] = useState(false)
  const [updating, setUpdating] = useState(false)

  const setStatus = async (status: string) => {
    setUpdating(true)
    try {
      await narrativeThreadsApi.update(storyId, thread.thread_id, status)
      toast.success(`Marked as ${status}`)
      onUpdated()
    } catch {
      toast.error('Update failed')
    } finally {
      setUpdating(false)
    }
  }

  const s = STATUS_STYLES[thread.status] ?? STATUS_STYLES.open

  return (
    <div className="bg-[#0d0f1a] border border-[#1f2440] rounded-xl overflow-hidden">
      <button
        className="w-full flex items-start gap-2 p-3 text-left"
        onClick={() => setOpen(v => !v)}
      >
        {open ? <ChevronDown className="w-3.5 h-3.5 text-[#5c6391] mt-0.5 flex-shrink-0" /> : <ChevronRight className="w-3.5 h-3.5 text-[#5c6391] mt-0.5 flex-shrink-0" />}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded border ${s.badge}`}>
              {s.label}
            </span>
            {thread.introduced_chapter && (
              <span className="text-[10px] text-[#5c6391]">
                Ch {thread.introduced_chapter}
                {thread.last_seen_chapter ? `–${thread.last_seen_chapter}` : ''}
              </span>
            )}
          </div>
          <p className="text-xs text-[#c8cce8] font-medium leading-snug">{thread.name}</p>
        </div>
      </button>
      {open && (
        <div className="px-3 pb-3 pl-8 border-t border-[#1f2440]">
          {thread.description && (
            <p className="text-xs text-[#9da3c8] leading-relaxed mt-2 mb-3">{thread.description}</p>
          )}
          <div className="flex gap-1.5">
            {(['open', 'resolved', 'dead_end'] as const).map(st => (
              <button
                key={st}
                disabled={updating || thread.status === st}
                onClick={() => setStatus(st)}
                className={`text-[10px] px-2 py-1 rounded border transition-colors ${
                  thread.status === st
                    ? STATUS_STYLES[st].badge
                    : 'text-[#5c6391] border-[#2e3454] hover:text-[#9da3c8] hover:border-[#3d4466]'
                } disabled:opacity-50`}
              >
                {st === 'dead_end' ? 'Dead End' : st.charAt(0).toUpperCase() + st.slice(1)}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default function NarrativeThreadsPanel({ storyId }: Props) {
  const [threads, setThreads] = useState<NarrativeThreadOut[] | null>(null)
  const [scanning, setScanning] = useState(false)
  const [loadingList, setLoadingList] = useState(false)
  const [filter, setFilter] = useState<string>('all')

  const loadThreads = async () => {
    setLoadingList(true)
    try {
      const res = await narrativeThreadsApi.list(storyId)
      setThreads(res.data)
    } catch {
      toast.error('Failed to load threads')
    } finally {
      setLoadingList(false)
    }
  }

  const scan = async () => {
    setScanning(true)
    try {
      await narrativeThreadsApi.scan(storyId)
      toast.success('Scan started — threads will appear once ready')
      // Poll once after 10 s
      setTimeout(() => loadThreads(), 10_000)
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Scan failed')
    } finally {
      setScanning(false)
    }
  }

  useEffect(() => {
    loadThreads()
  }, [storyId])

  const filtered = threads?.filter(t => filter === 'all' || t.status === filter) ?? []
  const deadEnds = threads?.filter(t => t.status === 'dead_end').length ?? 0

  if (loadingList && !threads) {
    return (
      <div className="flex items-center justify-center h-full gap-2 text-[#5c6391]">
        <Loader2 className="w-4 h-4 animate-spin" />
        <span className="text-xs">Loading threads…</span>
      </div>
    )
  }

  if (!threads || threads.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 p-6 h-full">
        <GitBranch className="w-10 h-10 text-[#2e3454]" />
        <p className="text-xs text-[#5c6391] text-center">Track narrative threads across your manuscript and flag dead ends</p>
        <button
          onClick={scan}
          disabled={scanning}
          className="px-3 py-1.5 rounded-lg text-xs bg-amber-500/10 text-amber-400 border border-amber-500/20 hover:bg-amber-500/20 transition-all disabled:opacity-50"
        >
          {scanning ? <><Loader2 className="w-3 h-3 animate-spin inline mr-1" />Scanning…</> : 'Scan Threads'}
        </button>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="px-3 pt-3 pb-2 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-[#9da3c8]">{threads.length} threads</span>
          {deadEnds > 0 && (
            <span className="text-[10px] text-red-400 bg-red-500/10 border border-red-500/20 px-1.5 py-0.5 rounded">
              {deadEnds} dead ends
            </span>
          )}
        </div>
        <div className="flex gap-1">
          <button
            onClick={scan}
            disabled={scanning}
            className="text-[10px] text-amber-400 border border-amber-500/20 px-2 py-0.5 rounded hover:bg-amber-500/10 disabled:opacity-50"
          >
            {scanning ? '…' : 'Rescan'}
          </button>
          <button onClick={loadThreads} className="text-[#5c6391] hover:text-amber-400">
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Filter pills */}
      <div className="px-3 pb-2 flex gap-1 flex-shrink-0">
        {['all', 'open', 'dead_end', 'resolved'].map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`text-[10px] px-2 py-0.5 rounded border transition-colors ${
              filter === f
                ? 'text-amber-400 bg-amber-500/10 border-amber-500/20'
                : 'text-[#5c6391] border-[#2e3454] hover:text-[#9da3c8]'
            }`}
          >
            {f === 'dead_end' ? 'Dead Ends' : f.charAt(0).toUpperCase() + f.slice(1)}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto px-3 pb-4 flex flex-col gap-2">
        {filtered.length === 0 ? (
          <p className="text-xs text-[#5c6391] text-center py-6">No threads match this filter.</p>
        ) : (
          filtered.map(thread => (
            <ThreadCard key={thread.thread_id} thread={thread} storyId={storyId} onUpdated={loadThreads} />
          ))
        )}
      </div>
    </div>
  )
}
