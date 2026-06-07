'use client'

import { useState } from 'react'
import { Loader2, ChevronDown, ChevronUp, GitBranch } from 'lucide-react'
import { charactersApi } from '@/lib/api'
import { ArcRole, CharacterArcSnapshot, CharacterArcTimelineResponse } from '@/lib/types'
import { toast } from 'sonner'

// ── Role display config ───────────────────────────────────────────────────────

const ROLE_CONFIG: Record<ArcRole, { label: string; color: string; dot: string }> = {
  major_player:  { label: 'Major Player',  color: 'text-amber-400',  dot: 'bg-amber-400'  },
  turning_point: { label: 'Turning Point', color: 'text-red-400',    dot: 'bg-red-400'    },
  observer:      { label: 'Observer',      color: 'text-[#9da3c8]',  dot: 'bg-[#3d4466]'  },
  brief_mention: { label: 'Brief Mention', color: 'text-[#5c6391]',  dot: 'bg-[#2e3454]'  },
}

// ── Snapshot node ─────────────────────────────────────────────────────────────

function SnapshotNode({ snap }: { snap: CharacterArcSnapshot }) {
  const [expanded, setExpanded] = useState(false)
  const cfg = ROLE_CONFIG[snap.role_in_chapter] ?? ROLE_CONFIG.observer

  return (
    <div className="flex gap-3">
      {/* Timeline spine */}
      <div className="flex flex-col items-center flex-shrink-0">
        <div className={`w-2.5 h-2.5 rounded-full mt-1 flex-shrink-0 ${cfg.dot}`} />
        <div className="w-px flex-1 bg-[#1f2440] mt-1" />
      </div>

      {/* Content */}
      <div className="pb-4 flex-1 min-w-0">
        {/* Chapter header */}
        <div className="flex items-center gap-2 mb-1 flex-wrap">
          <span className="text-[10px] font-semibold text-[#5c6391]">Ch{snap.chapter_number}</span>
          <span className={`text-[9px] font-medium px-1.5 py-0.5 rounded-full border ${
            snap.role_in_chapter === 'major_player'  ? 'border-amber-500/30 bg-amber-500/10 text-amber-400' :
            snap.role_in_chapter === 'turning_point' ? 'border-red-500/30   bg-red-500/10   text-red-400'   :
            snap.role_in_chapter === 'observer'      ? 'border-[#2e3454]    bg-[#1f2440]    text-[#9da3c8]' :
                                                       'border-[#1f2440]    bg-transparent  text-[#5c6391]'
          }`}>
            {cfg.label}
          </span>
          {snap.status_change && (
            <span className="text-[9px] px-1.5 py-0.5 rounded-full border border-red-500/30 bg-red-500/10 text-red-400">
              {snap.status_change}
            </span>
          )}
          {snap.is_stale && (
            <span className="text-[9px] px-1.5 py-0.5 rounded-full border border-[#2e3454] text-[#3d4466]">
              stale
            </span>
          )}
        </div>

        {/* Key action — always visible */}
        {snap.key_action && (
          <p className="text-[11px] text-[#e8eaf6] leading-relaxed mb-1">
            {snap.key_action}
          </p>
        )}

        {/* Emotional state — always visible */}
        {snap.emotional_state && (
          <p className="text-[10px] text-[#9da3c8] leading-relaxed italic mb-1">
            {snap.emotional_state}
          </p>
        )}

        {/* Development note — collapsible */}
        {snap.development_note && (
          <button
            onClick={() => setExpanded(v => !v)}
            className="flex items-center gap-1 text-[9px] text-[#3d4466] hover:text-[#5c6391] transition-colors mt-0.5"
          >
            {expanded ? <ChevronUp className="w-2.5 h-2.5" /> : <ChevronDown className="w-2.5 h-2.5" />}
            Arc note
          </button>
        )}
        {expanded && snap.development_note && (
          <p className="text-[10px] text-[#5c6391] leading-relaxed mt-1 border-l-2 border-[#2e3454] pl-2">
            {snap.development_note}
          </p>
        )}
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

interface Props {
  storyId:       string
  characterId:   string
  characterName: string
}

export default function CharacterArcTimelinePanel({ storyId, characterId, characterName }: Props) {
  const [timeline,  setTimeline]  = useState<CharacterArcTimelineResponse | null>(null)
  const [loading,   setLoading]   = useState(false)
  const [noMentions, setNoMentions] = useState(false)

  const generate = async () => {
    setLoading(true)
    setNoMentions(false)
    try {
      const res  = await charactersApi.getArcTimeline(storyId, characterId)
      const data = res.data as CharacterArcTimelineResponse
      if (data.snapshots.length === 0) {
        toast.info('No chapter presence found — ensure mentions are synced')
      }
      setTimeline(data)
    } catch (err: any) {
      if (err?.response?.status === 422) {
        setNoMentions(true)
      } else {
        toast.error(err?.response?.data?.detail || 'Failed to generate arc timeline')
      }
    } finally {
      setLoading(false)
    }
  }

  // ── Not yet generated ──────────────────────────────────────────────────────
  if (!timeline && !loading && !noMentions) {
    return (
      <div className="flex flex-col items-center gap-3 py-4">
        <p className="text-[11px] text-[#5c6391] text-center leading-relaxed">
          Generate {characterName}&apos;s arc timeline to see how their journey unfolds chapter by chapter.
        </p>
        <button
          onClick={generate}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-500 hover:bg-indigo-600 text-xs font-semibold text-white transition-colors"
        >
          <GitBranch className="w-3 h-3" />
          Generate Arc Timeline
        </button>
      </div>
    )
  }

  // ── Loading ────────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="flex flex-col items-center gap-2 py-4">
        <Loader2 className="w-4 h-4 text-indigo-400 animate-spin" />
        <p className="text-[10px] text-[#5c6391]">Analysing {characterName}&apos;s story arc…</p>
      </div>
    )
  }

  // ── No mentions ────────────────────────────────────────────────────────────
  if (noMentions) {
    return (
      <div className="flex flex-col gap-2 py-2">
        <p className="text-[11px] text-[#5c6391] leading-relaxed">
          No story mentions found. Sync character mentions first, then generate the timeline.
        </p>
        <button
          onClick={generate}
          className="self-start flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-500 hover:bg-indigo-600 text-xs font-semibold text-white transition-colors"
        >
          <GitBranch className="w-3 h-3" />
          Try Again
        </button>
      </div>
    )
  }

  // ── Results ────────────────────────────────────────────────────────────────
  const { snapshots, chapters_with_presence, total_chapters, analysis_note } = timeline!

  return (
    <div className="flex flex-col gap-3">
      {/* Overview */}
      <div className="flex items-center justify-between">
        <p className="text-[10px] text-[#5c6391]">
          Present in {chapters_with_presence} of {total_chapters} chapter{total_chapters !== 1 ? 's' : ''}
        </p>
        <button
          onClick={generate}
          disabled={loading}
          className="text-[9px] text-[#3d4466] hover:text-indigo-400 transition-colors disabled:opacity-40"
          title="Regenerate arc timeline"
        >
          Regenerate
        </button>
      </div>

      {/* Timeline */}
      {snapshots.length === 0 ? (
        <p className="text-[11px] text-[#3d4466]">
          No chapter snapshots generated — character may not appear in indexed chapters.
        </p>
      ) : (
        <div className="flex flex-col">
          {snapshots.map(snap => (
            <SnapshotNode key={snap.arc_snapshot_id} snap={snap} />
          ))}
        </div>
      )}

      {/* Analysis note */}
      {analysis_note && (
        <p className="text-[9px] text-[#3d4466] leading-relaxed pt-1 border-t border-[#1f2440]">
          {analysis_note}
        </p>
      )}
    </div>
  )
}
