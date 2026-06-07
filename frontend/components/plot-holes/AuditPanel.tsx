'use client'

import { useState } from 'react'
import { AlertTriangle, ScanSearch, BookOpen } from 'lucide-react'
import PlotHolesPanel from './PlotHolesPanel'
import ManuscriptReportPanel from './ManuscriptReportPanel'

type AuditTab = 'issues' | 'report'

interface Props {
  storyId: string
}

export default function AuditPanel({ storyId }: Props) {
  const [activeTab, setActiveTab] = useState<AuditTab>('issues')

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-4 py-3 border-b border-[#1f2440] flex-shrink-0">
        <div className="flex items-center gap-2 mb-2.5">
          <AlertTriangle className="w-4 h-4 text-amber-500" />
          <span className="text-xs font-medium text-[#9da3c8] uppercase tracking-wider">Story Audit</span>
        </div>
        <div className="flex gap-1 bg-[#0f1220] rounded-lg p-0.5">
          <button
            onClick={() => setActiveTab('issues')}
            className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-md text-[11px] font-medium transition-colors ${
              activeTab === 'issues'
                ? 'bg-[#1a1d35] text-[#c8cce8]'
                : 'text-[#5c6391] hover:text-[#9da3c8]'
            }`}
          >
            <ScanSearch className="w-3 h-3" />
            Issues
          </button>
          <button
            onClick={() => setActiveTab('report')}
            className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-md text-[11px] font-medium transition-colors ${
              activeTab === 'report'
                ? 'bg-[#1a1d35] text-[#c8cce8]'
                : 'text-[#5c6391] hover:text-[#9da3c8]'
            }`}
          >
            <BookOpen className="w-3 h-3" />
            Report
          </button>
        </div>
      </div>

      {activeTab === 'issues'
        ? <PlotHolesPanel storyId={storyId} />
        : <ManuscriptReportPanel storyId={storyId} />
      }
    </div>
  )
}
