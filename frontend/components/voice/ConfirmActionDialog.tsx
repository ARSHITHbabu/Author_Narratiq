'use client'

import { AlertTriangle } from 'lucide-react'
import type { WorkflowNode } from '@/lib/types'

const RISK_COPY: Record<string, string> = {
  destructive: 'This is destructive and cannot be undone.',
  export:      'This will export your manuscript to a file.',
  write:       'This will modify your story content.',
}

function describe(node: WorkflowNode): string {
  const a = node.execution?.args ?? {}
  const verb = `${node.capability.replace(/_/g, ' ')} · ${node.action.replace(/_/g, ' ')}`
  const preview = typeof a.content === 'string' ? (a.content as string).slice(0, 220)
    : typeof a.replacement === 'string' ? `"${a.query}" → "${a.replacement}"`
    : ''
  return preview ? `${verb}\n\n${preview}${preview.length >= 220 ? '…' : ''}` : verb
}

export default function ConfirmActionDialog({
  node, onConfirm, onCancel,
}: {
  node: WorkflowNode
  onConfirm: () => void
  onCancel: () => void
}) {
  return (
    <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 space-y-2">
      <div className="flex items-center gap-2 text-amber-300">
        <AlertTriangle className="w-4 h-4" />
        <span className="text-xs font-medium">Confirm before applying</span>
      </div>
      <pre className="text-[11px] text-[#cdd2f0] whitespace-pre-wrap font-sans">{describe(node)}</pre>
      <p className="text-[10px] text-amber-300/80">
        {RISK_COPY[node.action_type] ?? 'Please confirm this action.'}
      </p>
      <div className="flex gap-2 pt-1">
        <button
          onClick={onConfirm}
          className="flex-1 text-xs py-1.5 rounded bg-amber-500 hover:bg-amber-400 text-black font-medium transition-colors"
        >
          Apply
        </button>
        <button
          onClick={onCancel}
          className="flex-1 text-xs py-1.5 rounded border border-[#2a3057] text-[#9da3c8] hover:text-white transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}
