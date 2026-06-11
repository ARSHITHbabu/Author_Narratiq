'use client'

import { useState } from 'react'
import {
  AlertTriangle, ScanSearch, BookOpen,
  TrendingUp, Link2, PenLine, Copy, GitBranch,
} from 'lucide-react'
import PlotHolesPanel         from './PlotHolesPanel'
import ManuscriptReportPanel  from './ManuscriptReportPanel'
import EmotionalArcPanel      from '@/components/analysis/EmotionalArcPanel'
import ContinuityPanel        from '@/components/analysis/ContinuityPanel'
import StyleDriftPanel        from '@/components/analysis/StyleDriftPanel'
import DuplicateScenesPanel   from '@/components/analysis/DuplicateScenesPanel'
import NarrativeThreadsPanel  from '@/components/analysis/NarrativeThreadsPanel'

type AuditTab = 'issues' | 'report' | 'arc' | 'continuity' | 'style' | 'dupes' | 'threads'

const TABS: { id: AuditTab; icon: React.ElementType; label: string }[] = [
  { id: 'issues',     icon: ScanSearch,  label: 'Issues'   },
  { id: 'report',     icon: BookOpen,    label: 'Report'   },
  { id: 'arc',        icon: TrendingUp,  label: 'Arc'      },
  { id: 'continuity', icon: Link2,       label: 'Cont.'    },
  { id: 'style',      icon: PenLine,     label: 'Style'    },
  { id: 'dupes',      icon: Copy,        label: 'Dupes'    },
  { id: 'threads',    icon: GitBranch,   label: 'Threads'  },
]

interface Props {
  storyId: string
}

export default function AuditPanel({ storyId }: Props) {
  const [activeTab, setActiveTab] = useState<AuditTab>('issues')

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-4 py-2.5 border-b border-[#1f2440] flex-shrink-0">
        <div className="flex items-center gap-2 mb-2">
          <AlertTriangle className="w-4 h-4 text-amber-500" />
          <span className="text-xs font-medium text-[#9da3c8] uppercase tracking-wider">Story Audit</span>
        </div>
        <div className="flex gap-0.5 bg-[#0f1220] rounded-lg p-0.5 overflow-x-auto">
          {TABS.map(({ id, icon: Icon, label }) => (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              className={`flex-1 flex flex-col items-center gap-0.5 py-1.5 px-1 rounded-md text-[10px] font-medium transition-colors min-w-[34px] ${
                activeTab === id
                  ? 'bg-[#1a1d35] text-[#c8cce8]'
                  : 'text-[#5c6391] hover:text-[#9da3c8]'
              }`}
            >
              <Icon className="w-3 h-3" />
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-hidden">
        {activeTab === 'issues'     && <PlotHolesPanel storyId={storyId} />}
        {activeTab === 'report'     && <ManuscriptReportPanel storyId={storyId} />}
        {activeTab === 'arc'        && <EmotionalArcPanel storyId={storyId} />}
        {activeTab === 'continuity' && <ContinuityPanel storyId={storyId} />}
        {activeTab === 'style'      && <StyleDriftPanel storyId={storyId} />}
        {activeTab === 'dupes'      && <DuplicateScenesPanel storyId={storyId} />}
        {activeTab === 'threads'    && <NarrativeThreadsPanel storyId={storyId} />}
      </div>
    </div>
  )
}
