'use client'

import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Loader2, BookOpen, RefreshCw, Download, Users, MapPin, Clock, Globe, Palette, AlertCircle } from 'lucide-react'
import { storyBibleApi } from '@/lib/api'
import { useStoryBible, storyBibleKey } from '@/lib/useStoryBible'
import type { FailedSection } from '@/lib/types'
import { toast } from 'sonner'

interface Props { storyId: string }

type BibleSection = 'characters' | 'locations' | 'timeline' | 'world_rules' | 'themes'

const SECTIONS: { key: BibleSection; label: string; icon: React.ElementType }[] = [
  { key: 'characters',  label: 'Characters',  icon: Users     },
  { key: 'locations',   label: 'Locations',   icon: MapPin    },
  { key: 'timeline',    label: 'Timeline',    icon: Clock     },
  { key: 'world_rules', label: 'World Rules', icon: Globe     },
  { key: 'themes',      label: 'Themes',      icon: Palette   },
]

function SectionContent({ text }: { text: string }) {
  if (!text) return <p className="text-xs text-[#5c6391] italic">Not yet generated.</p>
  return <div className="text-xs text-[#9da3c8] leading-relaxed whitespace-pre-wrap">{text}</div>
}

/** A section that did not produce usable content: what happened, and a way to
 *  fix just this one rather than rebuilding the whole bible. */
function SectionFailure({
  failure, onRetry, busy,
}: { failure: FailedSection; onRetry: () => void; busy: boolean }) {
  return (
    <div className="flex flex-col items-start gap-3 py-4">
      <div className="flex items-start gap-2">
        <AlertCircle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
        <p className="text-xs text-[#9da3c8] leading-relaxed">{failure.reason}</p>
      </div>
      <button
        onClick={onRetry}
        disabled={busy}
        className="px-3 py-1.5 rounded-lg text-xs bg-amber-500/10 text-amber-400 border border-amber-500/20 hover:bg-amber-500/20 transition-all disabled:opacity-50"
      >
        {busy
          ? <><Loader2 className="w-3 h-3 animate-spin inline mr-1" />Writing this section…</>
          : 'Regenerate this section'}
      </button>
      <p className="text-[10px] text-[#3d4466]">Only this section is rewritten — the rest of your bible is kept.</p>
    </div>
  )
}

export default function StoryBiblePanel({ storyId }: Props) {
  const qc = useQueryClient()
  const { data: bible, isLoading, isError, refetch } = useStoryBible(storyId)
  const [activeSection, setActiveSection] = useState<BibleSection>('characters')

  const status = bible?.status            // 'running' | 'completed' | 'partial' | 'failed' | undefined
  const isRunning = status === 'running'
  const failedSections = bible?.failed_sections ?? []
  const failureFor = (key: BibleSection) => failedSections.find(f => f.section === key)
  // Which section the author just asked us to repair. Local state, so we can
  // keep the bible on screen during a targeted retry instead of replacing it
  // with the whole-bible spinner.
  const [regenerating, setRegenerating] = useState<BibleSection | null>(null)

  // Generate / regenerate. Duplicate requests are blocked while running (button
  // disabled + backend persisted guard). On success we refetch so the panel
  // immediately flips to the in-progress state.
  const genMutation = useMutation({
    mutationFn: () => storyBibleApi.generate(storyId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: storyBibleKey(storyId) }) },
    onError: (e: any) => toast.error(e?.response?.data?.detail ?? 'Generation failed'),
  })
  const triggerGenerate = () => { if (!isRunning && !genMutation.isPending) genMutation.mutate() }

  // Repair one section. The bible stays on screen while it runs.
  const sectionMutation = useMutation({
    mutationFn: (key: BibleSection) => storyBibleApi.regenerateSection(storyId, key),
    onSuccess: () => { qc.invalidateQueries({ queryKey: storyBibleKey(storyId) }) },
    onError: (e: any) => {
      setRegenerating(null)
      toast.error(e?.response?.data?.detail ?? 'Could not regenerate that section')
    },
  })
  const triggerSection = (key: BibleSection) => {
    if (isRunning || sectionMutation.isPending) return
    setRegenerating(key)
    sectionMutation.mutate(key)
  }
  // Clear the local marker once the backend reaches a terminal state again.
  useEffect(() => {
    if (regenerating && status && status !== 'running') setRegenerating(null)
  }, [status, regenerating])

  let content: Record<string, string> = {}
  if (bible?.content_json) {
    try { content = JSON.parse(bible.content_json) } catch { content = {} }
  }

  const downloadDocx = () => {
    const url = storyBibleApi.exportUrl(storyId)
    const token = typeof window !== 'undefined' ? localStorage.getItem('narratiq_token') : null
    fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.blob())
      .then(blob => {
        const a = document.createElement('a')
        a.href = URL.createObjectURL(blob)
        a.download = 'story_bible.docx'
        a.click()
      })
      .catch(() => toast.error('Export failed'))
  }

  // ── Loading the initial status ──────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 p-6 h-full text-[#5c6391]">
        <Loader2 className="w-5 h-5 animate-spin" />
        <p className="text-xs">Loading story bible…</p>
      </div>
    )
  }

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 p-6 h-full">
        <AlertCircle className="w-8 h-8 text-red-300" />
        <p className="text-xs text-[#9da3c8] text-center">Couldn’t load the story bible.</p>
        <button onClick={() => refetch()} className="px-3 py-1.5 rounded-lg text-xs border border-[#2e3454] text-[#9da3c8] hover:border-[#3d4466]">Retry</button>
      </div>
    )
  }

  // ── In-progress ─────────────────────────────────────────────────────────────
  // A targeted section repair keeps the bible on screen (see `regenerating`);
  // only a whole-bible run replaces the panel with the spinner.
  if (isRunning && !regenerating) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 p-6 h-full text-center">
        <Loader2 className="w-9 h-9 text-amber-400 animate-spin" />
        <p className="text-sm text-[#e8eaf6] font-medium">Story Bible generation is in progress</p>
        <p className="text-xs text-[#5c6391] max-w-xs">
          You can continue working — we’ll notify you when it’s ready. This usually takes 1–3 minutes.
        </p>
      </div>
    )
  }

  // ── Failed ──────────────────────────────────────────────────────────────────
  if (status === 'failed') {
    return (
      <div className="flex flex-col items-center justify-center gap-4 p-6 h-full text-center">
        <AlertCircle className="w-9 h-9 text-red-300" />
        <p className="text-sm text-[#e8eaf6] font-medium">Story Bible generation failed</p>
        <p className="text-xs text-[#5c6391] max-w-xs">Something interrupted generation. You can try again.</p>
        <button
          onClick={triggerGenerate}
          disabled={genMutation.isPending}
          className="px-3 py-1.5 rounded-lg text-xs bg-amber-500/10 text-amber-400 border border-amber-500/20 hover:bg-amber-500/20 transition-all disabled:opacity-50"
        >
          {genMutation.isPending ? <><Loader2 className="w-3 h-3 animate-spin inline mr-1" />Retrying…</> : 'Retry generation'}
        </button>
      </div>
    )
  }

  // ── Idle (never generated) ──────────────────────────────────────────────────
  if (!bible) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 p-6 h-full">
        <BookOpen className="w-10 h-10 text-[#2e3454]" />
        <p className="text-xs text-[#5c6391] text-center">
          Generate a comprehensive story bible: characters, locations, timeline, world rules, and themes
        </p>
        <button
          onClick={triggerGenerate}
          disabled={genMutation.isPending}
          className="px-3 py-1.5 rounded-lg text-xs bg-amber-500/10 text-amber-400 border border-amber-500/20 hover:bg-amber-500/20 transition-all disabled:opacity-50"
        >
          {genMutation.isPending
            ? <><Loader2 className="w-3 h-3 animate-spin inline mr-1" />Starting…</>
            : 'Generate Story Bible'}
        </button>
        <p className="text-[10px] text-[#3d4466] text-center">Takes 1–3 min depending on manuscript size</p>
      </div>
    )
  }

  // ── Completed or partial — show the bible ───────────────────────────────────
  const activeFailure = failureFor(activeSection)
  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="px-3 pt-3 pb-2 flex items-center justify-between flex-shrink-0">
        <span className="text-xs text-[#9da3c8]">Version {bible.version}</span>
        <div className="flex gap-1 items-center">
          <button
            onClick={triggerGenerate}
            disabled={genMutation.isPending}
            className="text-[10px] text-amber-400 border border-amber-500/20 px-2 py-0.5 rounded hover:bg-amber-500/10 disabled:opacity-50"
          >
            {genMutation.isPending ? '…' : 'Regenerate'}
          </button>
          <button onClick={downloadDocx} className="text-[#5c6391] hover:text-amber-400 transition-colors" title="Download DOCX">
            <Download className="w-3.5 h-3.5" />
          </button>
          <button onClick={() => refetch()} className="text-[#5c6391] hover:text-amber-400 transition-colors" title="Refresh">
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Partial — say plainly what is missing rather than presenting the
          bible as finished. */}
      {status === 'partial' && (
        <div className="mx-3 mb-2 px-2.5 py-2 rounded-lg bg-amber-500/5 border border-amber-500/20 flex-shrink-0">
          <p className="text-[11px] text-amber-300/90 leading-relaxed">
            {failedSections.length === 1
              ? 'One section couldn’t be written. Everything else is ready.'
              : `${failedSections.length} sections couldn’t be written. Everything else is ready.`}
          </p>
          <p className="text-[10px] text-[#5c6391] mt-0.5">
            Open {failedSections.length === 1 ? 'it' : 'them'} below to see what happened and try again.
          </p>
        </div>
      )}

      <div className="px-3 pb-2 flex gap-1 flex-wrap flex-shrink-0">
        {SECTIONS.map(({ key, label, icon: Icon }) => {
          const failed = !!failureFor(key)
          return (
            <button
              key={key}
              onClick={() => setActiveSection(key)}
              title={failed ? 'This section needs another attempt' : undefined}
              className={`flex items-center gap-1 text-[10px] px-2 py-1 rounded border transition-colors ${
                activeSection === key
                  ? 'text-amber-400 bg-amber-500/10 border-amber-500/20'
                  : failed
                    ? 'text-amber-300/70 border-amber-500/20 hover:text-amber-300'
                    : 'text-[#5c6391] border-[#2e3454] hover:text-[#9da3c8]'
              }`}
            >
              <Icon className="w-2.5 h-2.5" />
              {label}
              {failed && <AlertCircle className="w-2.5 h-2.5" />}
            </button>
          )
        })}
      </div>

      <div className="flex-1 overflow-y-auto px-3 pb-4">
        {activeFailure
          ? <SectionFailure
              failure={activeFailure}
              onRetry={() => triggerSection(activeSection)}
              busy={regenerating === activeSection || sectionMutation.isPending}
            />
          : <SectionContent text={content[activeSection] ?? ''} />}
      </div>
    </div>
  )
}
