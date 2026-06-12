'use client'

import { CheckCircle2, Circle, Loader2, AlertCircle, ShieldQuestion } from 'lucide-react'
import type { WorkflowNode } from '@/lib/types'

interface NodeRun { ok: boolean; data?: unknown; message?: string }

const ACTION_COLORS: Record<string, string> = {
  read:        'text-sky-300 bg-sky-500/10 border-sky-500/20',
  analyze:     'text-violet-300 bg-violet-500/10 border-violet-500/20',
  generate:    'text-emerald-300 bg-emerald-500/10 border-emerald-500/20',
  write:       'text-amber-300 bg-amber-500/10 border-amber-500/20',
  destructive: 'text-red-300 bg-red-500/10 border-red-500/20',
  export:      'text-orange-300 bg-orange-500/10 border-orange-500/20',
}

function StepIcon({ node, run }: { node: WorkflowNode; run?: NodeRun }) {
  if (run) {
    return run.ok
      ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
      : <AlertCircle className="w-3.5 h-3.5 text-red-400" />
  }
  if (node.requires_confirmation) return <ShieldQuestion className="w-3.5 h-3.5 text-amber-400" />
  if (node.status === 'done') return <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
  if (node.status === 'running') return <Loader2 className="w-3.5 h-3.5 text-sky-400 animate-spin" />
  if (node.status === 'failed') return <AlertCircle className="w-3.5 h-3.5 text-red-400" />
  return <Circle className="w-3.5 h-3.5 text-[#5c6391]" />
}

export default function WorkflowStepList({
  nodes, results, multiStep,
}: {
  nodes: WorkflowNode[]
  results: Record<string, NodeRun>
  multiStep: boolean
}) {
  if (!nodes.length) return null
  return (
    <div className="space-y-1.5">
      {multiStep && (
        <p className="text-[10px] uppercase tracking-wide text-[#5c6391]">
          {nodes.length}-step workflow
        </p>
      )}
      {nodes.map((n, i) => {
        const run = results[n.node_key]
        return (
          <div key={n.node_key} className="rounded-md border border-[#1f2440] bg-[#11152b] px-2.5 py-2">
            <div className="flex items-center gap-2">
              <StepIcon node={n} run={run} />
              {multiStep && <span className="text-[10px] text-[#5c6391]">{i + 1}.</span>}
              <span className="text-xs text-[#cdd2f0] flex-1">
                {n.capability.replace(/_/g, ' ')} · {n.action.replace(/_/g, ' ')}
              </span>
              <span className={`text-[9px] px-1.5 py-0.5 rounded border ${ACTION_COLORS[n.action_type] ?? ACTION_COLORS.read}`}>
                {n.action_type}
              </span>
            </div>
            {(run?.message || n.user_message) && (
              <p className="text-[11px] text-[#9da3c8] mt-1 ml-5.5 pl-0.5">
                {run?.message || n.user_message}
              </p>
            )}
            {run && !run.ok && (
              <p className="text-[11px] text-red-300 mt-1">{run.message}</p>
            )}
          </div>
        )
      })}
    </div>
  )
}
