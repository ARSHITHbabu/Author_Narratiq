'use client'

import { useCallback, useMemo, useRef, useState, type ReactNode } from 'react'
import dynamic from 'next/dynamic'
import { useRouter } from 'next/navigation'
import { Mic, Square, RotateCcw, Loader2, AlertCircle, ChevronDown, ChevronRight } from 'lucide-react'
import { toast } from 'sonner'
import { useVoiceAgent } from './useVoiceAgent'
import WorkflowStepList from './WorkflowStepList'
import ConfirmActionDialog from './ConfirmActionDialog'
import type { VoiceContextSnapshot, WorkflowNode } from '@/lib/types'

// Legacy upload→note flow, retained as a secondary path.
const AudioPanel = dynamic(() => import('@/components/audio/AudioPanel'), { ssr: false })

interface Props {
  storyId: string
  chapterId: string | null
  chapterNumber: number | null
  chapterTitle?: string
  getSelectedText: () => string
  getFullText: () => string
  insertText: (text: string) => void
  getSelectionRange: () => { from: number; to: number } | null
  replaceRange: (from: number, to: number, text: string) => void
  onOpenChapter?: (chapterId: string) => void
}

// Transform actions that produce a previewed rewrite of the SELECTED text.
const TRANSFORM_ACTIONS = new Set(['tone', 'emotion', 'refine', 'age_adapt', 'style', 'translate', 'rewrite_section'])

const STATUS_LABEL: Record<string, string> = {
  idle: 'Tap the mic and speak',
  requesting: 'Requesting microphone…',
  listening: 'Listening…',
  transcribing: 'Transcribing…',
  thinking: 'Understanding…',
  ready: 'Done',
  error: 'Something went wrong',
  denied: 'Microphone blocked',
}

// Render a read/query/generate result as a readable answer (no raw IDs/JSON).
function AnswerCard({ node, run }: { node: WorkflowNode; run?: { ok: boolean; data?: unknown; message?: string } }) {
  // mutating actions are handled by the confirmation dialog, not here
  if (['write', 'destructive', 'export'].includes(node.action_type)) return null
  if (!run) {
    const serverMsg = node.user_message || (node.result ? 'Done.' : '')
    return serverMsg ? <div className="rounded-md border border-[#1f2440] bg-[#11152b] px-3 py-2 text-xs text-[#cdd2f0]">{serverMsg}</div> : null
  }
  if (!run.ok) {
    return <div className="rounded-md border border-red-500/20 bg-red-500/5 px-3 py-2 text-xs text-red-200">{run.message || 'That didn’t work.'}</div>
  }
  const d = run.data as Record<string, unknown> | unknown[] | null
  let body: ReactNode = run.message || 'Done.'
  if (d && typeof d === 'object') {
    const obj = d as Record<string, unknown>
    if (typeof obj.answer === 'string' && obj.answer) body = obj.answer as string
    else if (Array.isArray((obj as { suggestions?: unknown[] }).suggestions)) {
      const s = (obj as { suggestions: { text?: string }[] }).suggestions
      body = (
        <ul className="list-disc pl-4 space-y-1">
          {s.slice(0, 3).map((x, i) => <li key={i}>{x.text ?? JSON.stringify(x).slice(0, 120)}</li>)}
        </ul>
      )
    } else if (Array.isArray(d)) {
      body = `${d.length} result${d.length === 1 ? '' : 's'} found.`
    } else if (typeof obj.total_matches === 'number') {
      body = `${obj.total_matches} match${obj.total_matches === 1 ? '' : 'es'} found.`
    }
  }
  return <div className="rounded-md border border-[#1f2440] bg-[#11152b] px-3 py-2 text-xs text-[#cdd2f0] leading-relaxed">{body}</div>
}

export default function VoiceAgentPanel({
  storyId, chapterId, chapterNumber, chapterTitle,
  getSelectedText, getFullText, insertText, getSelectionRange, replaceRange, onOpenChapter,
}: Props) {
  const router = useRouter()
  const [showLegacy, setShowLegacy] = useState(false)
  const [showDebug, setShowDebug] = useState(false)
  // Selection captured at the moment the mic is pressed (before focus can shift),
  // used for the snapshot AND for Apply (so we replace the exact original range).
  const capturedSelRef = useRef<{ text: string; from: number; to: number } | null>(null)
  const [applied, setApplied] = useState(false)

  const captureSelection = useCallback(() => {
    const text = getSelectedText() || ''
    const range = getSelectionRange()
    capturedSelRef.current = text && range ? { text, from: range.from, to: range.to } : null
  }, [getSelectedText, getSelectionRange])

  const getContext = useMemo(() => (): VoiceContextSnapshot => {
    // Prefer the selection captured on mic-press; fall back to a live read.
    const cap = capturedSelRef.current
    const sel = cap?.text || getSelectedText() || ''
    const range = cap ? [cap.from, cap.to] : (getSelectionRange() ? [getSelectionRange()!.from, getSelectionRange()!.to] : null)
    return {
      story_id: storyId,
      chapter_id: chapterId,
      chapter_number: chapterNumber,
      chapter_title: chapterTitle ?? null,
      selected_text: sel || null,
      selected_text_range: range,
      has_selection: sel.length > 0,
      full_chapter_text: (getFullText() || '').slice(0, 6000) || null,
      active_panel: 'voice',
    }
  }, [storyId, chapterId, chapterNumber, chapterTitle, getSelectedText, getFullText, getSelectionRange])

  const actionCtx = useMemo(() => ({
    storyId,
    navigate: (url: string) => router.push(url),
    editor: { getSelectedText, getFullText, insertText },
    onOpenChapter,
    onGuideUpload: (kind: 'manuscript' | 'ocr' | 'audio') => {
      if (kind === 'audio') setShowLegacy(true)
      else toast.info(`Open the ${kind === 'ocr' ? 'OCR' : 'Manuscript'} panel to choose a file.`)
    },
    onLogout: () => {
      localStorage.removeItem('narratiq_token')
      localStorage.removeItem('narratiq_user')
      router.push('/login')
    },
  }), [storyId, getSelectedText, getFullText, insertText, onOpenChapter, router])

  const {
    status, partial, response, error, nodeResults, pendingConfirm,
    start, stop, cancel, confirm, clear,
  } = useVoiceAgent({ enabled: true, getContext, actionCtx })

  const isRecording = status === 'listening'
  const isBusy = status === 'transcribing' || status === 'thinking' || status === 'requesting'

  // Selected-text transform preview: the feature returns the rewritten selection;
  // we show it and only replace the ORIGINAL captured range when the author applies.
  const primaryNode = response?.workflow?.nodes?.[0]
  const isTransform = !!primaryNode && primaryNode.capability === 'text_transform'
    && TRANSFORM_ACTIONS.has(primaryNode.action)
  const transformData = primaryNode ? (nodeResults[primaryNode.node_key]?.data as
    { transformed?: string; text?: string } | undefined) : undefined
  const transformedText = transformData?.transformed || transformData?.text || ''

  const applyTransform = () => {
    const cap = capturedSelRef.current
    if (cap && transformedText) {
      replaceRange(cap.from, cap.to, transformedText)   // replaces ONLY the selection
      setApplied(true)
      toast.success('Applied to your selected text')
    } else {
      toast.error('Selection was lost — please re-select and try again.')
    }
  }

  const onMicClick = () => {
    if (isRecording) stop()
    else if (!isBusy) start()
  }

  // Capture the editor selection on mousedown — BEFORE the button steals focus /
  // collapses the selection — and keep the editor focused (preventDefault).
  const onMicMouseDown = (e: { preventDefault: () => void }) => {
    if (!isRecording && !isBusy) {
      e.preventDefault()
      setApplied(false)
      captureSelection()
    }
  }

  return (
    <div className="h-full overflow-y-auto p-3 space-y-3">
      {/* ── Mic control ──────────────────────────────────────────────────── */}
      <div className="flex flex-col items-center gap-2 py-3">
        <button
          onMouseDown={onMicMouseDown}
          onClick={onMicClick}
          disabled={isBusy}
          aria-label={isRecording ? 'Stop recording' : 'Start voice command'}
          className={`relative w-16 h-16 rounded-full flex items-center justify-center transition-all ${
            isRecording
              ? 'bg-red-500 hover:bg-red-400 shadow-lg shadow-red-500/30'
              : isBusy
                ? 'bg-[#2a3057] cursor-not-allowed'
                : 'bg-amber-500 hover:bg-amber-400 shadow-lg shadow-amber-500/30'
          }`}
        >
          {isBusy ? <Loader2 className="w-6 h-6 text-white animate-spin" />
            : isRecording ? <Square className="w-5 h-5 text-white fill-white" />
            : <Mic className="w-6 h-6 text-black" />}
          {isRecording && <span className="absolute inset-0 rounded-full border-2 border-red-300 animate-ping" />}
        </button>
        <p className="text-[11px] text-[#9da3c8]">{STATUS_LABEL[status] ?? ''}</p>
        {isRecording && (
          <button onClick={stop} className="text-[10px] text-red-300 hover:text-red-200">Stop & run</button>
        )}
      </div>

      {/* ── Live / final transcript ──────────────────────────────────────── */}
      {(partial || response?.cleaned_transcript) && (
        <div className="rounded-md border border-[#1f2440] bg-[#0d1124] px-3 py-2">
          <p className="text-[10px] uppercase tracking-wide text-[#5c6391] mb-1">
            {response ? 'You said' : 'Listening'}
          </p>
          <p className="text-sm text-[#cdd2f0] italic">
            {response?.cleaned_transcript || partial}
          </p>
        </div>
      )}

      {/* ── Error ────────────────────────────────────────────────────────── */}
      {error && (
        <div className="rounded-md border border-red-500/20 bg-red-500/5 px-3 py-2 flex items-start gap-2">
          <AlertCircle className="w-4 h-4 text-red-400 mt-0.5 flex-shrink-0" />
          <p className="text-xs text-red-200">{error}</p>
        </div>
      )}

      {/* ── Agent response (author-facing) ───────────────────────────────── */}
      {response && (
        <div className="space-y-2">
          {/* Understood + resolved entities (names, never ids) */}
          {response.resolved_entities && response.resolved_entities.length > 0 && (
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-[10px] text-[#5c6391]">Understood:</span>
              {response.resolved_entities.map((e, i) => (
                <span key={i} className="text-[10px] px-2 py-0.5 rounded-full bg-sky-500/10 border border-sky-500/20 text-sky-300">
                  {e.name}<span className="text-[#5c6391]"> · {e.kind}</span>
                </span>
              ))}
            </div>
          )}

          {response.context_used && response.status !== 'needs_clarification' && (
            <p className="text-[10px] text-[#5c6391]">
              <span className="text-[#7d84b0]">Using:</span> {response.context_used}
            </p>
          )}

          {response.user_message && (
            <p className="text-xs text-[#cdd2f0]">{response.user_message}</p>
          )}

          {/* Clarification — natural, name-based, no field names */}
          {response.status === 'needs_clarification' && response.clarification && (
            <div className="rounded-md border border-sky-500/20 bg-sky-500/5 px-3 py-2 space-y-1.5">
              <p className="text-xs text-sky-200">{response.clarification.question}</p>
              {response.clarification.options && response.clarification.options.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {response.clarification.options.map((o, i) => (
                    <span key={i} className="text-[11px] px-2 py-0.5 rounded border border-[#2a3057] text-[#9da3c8]">
                      {String(o.label ?? o.capability ?? '')}
                    </span>
                  ))}
                </div>
              )}
              <p className="text-[10px] text-[#5c6391]">Tap the mic and say it.</p>
            </div>
          )}

          {/* Selected-text transform: preview + Apply (replaces only the selection) */}
          {response.status !== 'needs_clarification' && isTransform && transformedText && (
            <div className="rounded-md border border-amber-500/20 bg-amber-500/5 p-3 space-y-2">
              <p className="text-[10px] uppercase tracking-wide text-amber-300/80">Preview (selected text)</p>
              <p className="text-xs text-[#cdd2f0] leading-relaxed whitespace-pre-wrap">{transformedText}</p>
              {applied ? (
                <p className="text-[11px] text-emerald-400">✓ Applied to your selection</p>
              ) : (
                <div className="flex gap-2 pt-0.5">
                  <button onClick={applyTransform}
                    className="flex-1 text-xs py-1.5 rounded bg-amber-500 hover:bg-amber-400 text-black font-medium">
                    Apply to selection
                  </button>
                  <button onClick={clear}
                    className="flex-1 text-xs py-1.5 rounded border border-[#2a3057] text-[#9da3c8] hover:text-white">
                    Discard
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Direct answer / result for a single read/query/generate action */}
          {response.status !== 'needs_clarification' && !response.is_multi_step && !isTransform &&
            response.workflow?.nodes?.[0] && (
              <AnswerCard node={response.workflow.nodes[0]} run={nodeResults[response.workflow.nodes[0].node_key]} />
            )}

          {/* Step list ONLY for genuinely multi-step workflows */}
          {response.is_multi_step && response.workflow && (
            <WorkflowStepList
              nodes={response.workflow.nodes}
              results={nodeResults}
              multiStep
            />
          )}

          {/* Pending confirmations (destructive/write/export) */}
          {pendingConfirm.map((node) => (
            <ConfirmActionDialog
              key={node.node_key}
              node={node}
              onConfirm={() => confirm(node, true)}
              onCancel={() => confirm(node, false)}
            />
          ))}

          <div className="flex items-center gap-3 pt-1">
            <button onClick={clear} className="flex items-center gap-1 text-[11px] text-[#5c6391] hover:text-[#9da3c8]">
              <RotateCcw className="w-3 h-3" /> Clear
            </button>
            <button onClick={() => setShowDebug((v) => !v)} className="text-[11px] text-[#5c6391] hover:text-[#9da3c8]">
              {showDebug ? 'Hide details' : 'Details'}
            </button>
          </div>

          {/* Technical metadata — hidden by default (debug view) */}
          {showDebug && (
            <div className="rounded-md border border-[#1f2440] bg-[#0b0e1d] px-3 py-2 space-y-0.5 text-[10px] text-[#5c6391] font-mono">
              <div>intent: {response.detected_intent || '—'}</div>
              <div>capability: {response.capability} · router: {response.target_router}</div>
              <div>action_type: {response.action_type} · confidence: {(response.confidence * 100).toFixed(0)}%</div>
              <div>multi_step: {String(response.is_multi_step)} · status: {response.status}</div>
              <div>raw: &quot;{response.cleaned_transcript}&quot; → &quot;{response.corrected_transcript}&quot;</div>
              {response.workflow && (
                <div>nodes: {response.workflow.nodes.map((n) => `${n.capability}.${n.action}`).join(', ')}</div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── Secondary: legacy upload → note ──────────────────────────────── */}
      <div className="border-t border-[#1f2440] pt-2">
        <button
          onClick={() => setShowLegacy((v) => !v)}
          className="flex items-center gap-1 text-[11px] text-[#5c6391] hover:text-[#9da3c8]"
        >
          {showLegacy ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
          Saved dictation → note (upload an audio file)
        </button>
        {showLegacy && (
          <div className="mt-2">
            <AudioPanel storyId={storyId} />
          </div>
        )}
      </div>
    </div>
  )
}
