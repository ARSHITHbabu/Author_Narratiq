'use client'

// useVoiceAgent — the client half of the Real-Time Voice Agent.
// Owns: mic permission, MediaRecorder streaming over the WebSocket, live partial
// transcripts, receiving the consolidated plan, and executing it via lib/voiceActions
// (auto-running safe steps, holding mutating steps for confirmation).

import { useCallback, useEffect, useRef, useState } from 'react'
import { voiceApi, voiceWsUrl } from '@/lib/api'
import { executeVoiceAction, resultKindFor, type VoiceActionContext, type VoiceActionResult } from '@/lib/voiceActions'
import type { VoiceAgentResponse, VoiceContextSnapshot, WorkflowNode } from '@/lib/types'

export type VoiceStatus =
  | 'idle' | 'requesting' | 'listening' | 'transcribing' | 'thinking'
  | 'ready' | 'error' | 'denied'

interface UseVoiceAgentOptions {
  enabled: boolean
  getContext: () => VoiceContextSnapshot
  actionCtx: VoiceActionContext
}

interface NodeRun extends VoiceActionResult {
  node_key: string
}

export function useVoiceAgent({ enabled, getContext, actionCtx }: UseVoiceAgentOptions) {
  const [status, setStatus] = useState<VoiceStatus>('idle')
  const [partial, setPartial] = useState('')
  const [response, setResponse] = useState<VoiceAgentResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [nodeResults, setNodeResults] = useState<Record<string, NodeRun>>({})
  const [pendingConfirm, setPendingConfirm] = useState<WorkflowNode[]>([])

  const sessionRef = useRef<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  // keep latest callbacks/context without reopening the socket
  const getContextRef = useRef(getContext)
  const actionCtxRef = useRef(actionCtx)
  getContextRef.current = getContext
  actionCtxRef.current = actionCtx

  const cleanupMedia = useCallback(() => {
    try { recorderRef.current?.state !== 'inactive' && recorderRef.current?.stop() } catch { /* noop */ }
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    recorderRef.current = null
  }, [])

  const closeSocket = useCallback(() => {
    try { wsRef.current?.close() } catch { /* noop */ }
    wsRef.current = null
  }, [])

  useEffect(() => () => { cleanupMedia(); closeSocket() }, [cleanupMedia, closeSocket])

  // ── Execute the consolidated plan ───────────────────────────────────────────
  const runPlan = useCallback(async (resp: VoiceAgentResponse) => {
    const ctx = { ...actionCtxRef.current, storyId: getContextRef.current().story_id || actionCtxRef.current.storyId }
    const nodes = resp.workflow?.nodes ?? []
    const results: Record<string, NodeRun> = {}
    const holds: WorkflowNode[] = []

    for (const node of nodes) {
      if (node.execution_locus === 'server') {
        results[node.node_key] = { node_key: node.node_key, ok: true, data: node.result ?? undefined, message: node.user_message }
        continue
      }
      if (node.requires_confirmation) { holds.push(node); continue }   // wait for the user
      const r = await executeVoiceAction(node, ctx)
      results[node.node_key] = { node_key: node.node_key, ...r }
      // Report the real outcome. Without this the backend never learns what
      // happened to a client-side step and its command stays at whatever was
      // assumed when the plan was built — the false-success defect.
      if (resp.command_id) {
        try { await voiceApi.reportResult(resp.command_id, node.node_key, r.ok, r.message) }
        catch { /* best effort — the backend's timeout sweep is the backstop */ }
      }
      // feed generate/analyze results into session memory for follow-ups
      const kind = resultKindFor(node)
      if (kind && r.ok && resp.session_id) {
        try { await voiceApi.remember(resp.session_id, kind, r.data) } catch { /* best effort */ }
      }
    }
    setNodeResults(results)
    setPendingConfirm(holds)
  }, [])

  // ── Confirm (or reject) a held mutating node ────────────────────────────────
  const confirm = useCallback(async (node: WorkflowNode, approve: boolean) => {
    const resp = response
    if (!resp) return
    if (!approve) {
      if (resp.command_id) { try { await voiceApi.confirm(resp.command_id, node.node_key, false, false) } catch { /* noop */ } }
      setPendingConfirm((p) => p.filter((n) => n.node_key !== node.node_key))
      return
    }
    const ctx = { ...actionCtxRef.current, storyId: getContextRef.current().story_id || actionCtxRef.current.storyId }
    // Approval and outcome are two different facts, reported separately: the
    // author approving a change is not the same as the change having worked.
    if (resp.command_id) { try { await voiceApi.confirm(resp.command_id, node.node_key, true, false) } catch { /* noop */ } }
    const r = await executeVoiceAction(node, ctx)
    setNodeResults((prev) => ({ ...prev, [node.node_key]: { node_key: node.node_key, ...r } }))
    if (resp.command_id) {
      try { await voiceApi.reportResult(resp.command_id, node.node_key, r.ok, r.message) }
      catch { /* best effort — the backend's timeout sweep is the backstop */ }
    }
    setPendingConfirm((p) => p.filter((n) => n.node_key !== node.node_key))
  }, [response])

  // ── WebSocket message handling ──────────────────────────────────────────────
  const handleFinal = useCallback(async (resp: VoiceAgentResponse) => {
    sessionRef.current = resp.session_id
    setResponse(resp)
    setStatus('ready')
    setPartial('')
    if (resp.status === 'success' || resp.status === 'needs_confirmation') {
      await runPlan(resp)
    }
  }, [runPlan])

  const openSocket = useCallback((): Promise<WebSocket> => {
    return new Promise((resolve, reject) => {
      const token = typeof window !== 'undefined' ? localStorage.getItem('narratiq_token') : null
      if (!token) { reject(new Error('Not authenticated')); return }
      const ws = new WebSocket(voiceWsUrl(token))
      ws.binaryType = 'arraybuffer'
      ws.onopen = () => resolve(ws)
      ws.onerror = () => reject(new Error('WebSocket error'))
      ws.onmessage = (ev) => {
        let msg: { type: string; transcript?: string; value?: string; response?: VoiceAgentResponse; message?: string }
        try { msg = JSON.parse(ev.data as string) } catch { return }
        if (msg.type === 'partial') setPartial(msg.transcript || '')
        else if (msg.type === 'state') {
          if (msg.value === 'transcribing') setStatus('transcribing')
          else if (msg.value === 'thinking') setStatus('thinking')
        } else if (msg.type === 'final' && msg.response) {
          void handleFinal(msg.response)
        } else if (msg.type === 'error') {
          setError(msg.message || 'Voice error')
          setStatus('error')
        }
      }
      ws.onclose = () => { wsRef.current = null }
    })
  }, [handleFinal])

  // ── Recording controls ──────────────────────────────────────────────────────
  const start = useCallback(async () => {
    if (!enabled) return
    setError(null); setResponse(null); setNodeResults({}); setPendingConfirm([]); setPartial('')
    setStatus('requesting')
    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch {
      setStatus('denied')
      setError('Microphone permission denied. Enable it in your browser to use the voice assistant.')
      return
    }
    streamRef.current = stream
    try {
      const ws = wsRef.current && wsRef.current.readyState === WebSocket.OPEN
        ? wsRef.current
        : await openSocket()
      wsRef.current = ws
      ws.send(JSON.stringify({ type: 'start', context: getContextRef.current(), session_id: sessionRef.current }))

      const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : 'audio/webm'
      const rec = new MediaRecorder(stream, { mimeType: mime })
      rec.ondataavailable = (e) => {
        if (e.data && e.data.size > 0 && ws.readyState === WebSocket.OPEN) ws.send(e.data)
      }
      rec.onstop = () => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'stop', context: getContextRef.current() }))
        }
        streamRef.current?.getTracks().forEach((t) => t.stop())
      }
      recorderRef.current = rec
      rec.start(250)               // 250ms timeslice → low-latency partials
      setStatus('listening')
    } catch (e) {
      setStatus('error')
      setError((e as Error).message || 'Could not start voice session.')
      cleanupMedia()
    }
  }, [enabled, openSocket, cleanupMedia])

  const stop = useCallback(() => {
    if (recorderRef.current && recorderRef.current.state !== 'inactive') {
      setStatus('transcribing')
      recorderRef.current.stop()    // triggers onstop → sends {type:'stop'}
    }
  }, [])

  const cancel = useCallback(() => {
    try { wsRef.current?.send(JSON.stringify({ type: 'cancel' })) } catch { /* noop */ }
    cleanupMedia()
    setStatus('idle'); setPartial('')
  }, [cleanupMedia])

  const clear = useCallback(() => {
    setResponse(null); setNodeResults({}); setPendingConfirm([]); setPartial(''); setError(null)
    setStatus('idle')
  }, [])

  return {
    status, partial, response, error, nodeResults, pendingConfirm,
    sessionId: sessionRef.current,
    start, stop, cancel, confirm, clear,
  }
}
