'use client'

import { useState, useEffect, useRef } from 'react'
import { Loader2, Mic, Upload, CheckCircle2, AlertCircle, RefreshCw, Copy } from 'lucide-react'
import { audioApi } from '@/lib/api'
import { AudioUploadOut, AudioTranscribeResponse } from '@/lib/types'
import { toast } from 'sonner'

interface Props { storyId: string }

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    processing: 'text-yellow-400 bg-yellow-500/10 border-yellow-500/20',
    completed:  'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
    failed:     'text-red-400 bg-red-500/10 border-red-500/20',
  }
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded border ${map[status] ?? map.processing}`}>
      {status}
    </span>
  )
}

function TranscriptCard({
  storyId,
  upload,
  onConfirmed,
}: {
  storyId: string
  upload: AudioUploadOut
  onConfirmed: () => void
}) {
  const [noteId, setNoteId] = useState(upload.note_id ?? '')
  const [editedText, setEditedText] = useState(upload.cleaned_text ?? upload.raw_transcript ?? '')
  const [confirming, setConfirming] = useState(false)
  const [expanded, setExpanded] = useState(false)

  const confirm = async () => {
    if (!noteId.trim()) {
      toast.error('Enter a note ID to append this transcript to')
      return
    }
    setConfirming(true)
    try {
      await audioApi.confirm(storyId, upload.audio_id, noteId, editedText)
      toast.success('Transcript appended to note')
      onConfirmed()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Confirm failed')
    } finally {
      setConfirming(false)
    }
  }

  return (
    <div className="bg-[#0d0f1a] border border-[#1f2440] rounded-xl p-3">
      <div className="flex items-start justify-between gap-2 mb-2">
        <div>
          <StatusBadge status={upload.status} />
          {upload.language_detected && (
            <span className="text-[10px] text-[#5c6391] ml-2">{upload.language_detected.toUpperCase()}</span>
          )}
          {upload.duration_seconds != null && (
            <span className="text-[10px] text-[#5c6391] ml-2">{upload.duration_seconds.toFixed(1)}s</span>
          )}
        </div>
        {upload.status === 'completed' && (
          <button
            onClick={() => setExpanded(v => !v)}
            className="text-[10px] text-[#5c6391] hover:text-amber-400"
          >
            {expanded ? 'Collapse' : 'Expand'}
          </button>
        )}
      </div>

      {upload.status === 'completed' && (
        <>
          <p className={`text-xs text-[#9da3c8] leading-relaxed ${expanded ? '' : 'line-clamp-3'}`}>
            {upload.cleaned_text || upload.raw_transcript || '(empty transcript)'}
          </p>

          {!upload.confirmed && (
            <div className="mt-3 flex flex-col gap-2">
              <input
                type="text"
                value={noteId}
                onChange={e => setNoteId(e.target.value)}
                placeholder="Note ID to append to"
                className="w-full bg-[#0d0f1a] border border-[#2e3454] rounded-lg px-2 py-1 text-[11px] text-[#e8eaf6] focus:border-amber-500/50 outline-none"
              />
              {expanded && (
                <textarea
                  value={editedText}
                  onChange={e => setEditedText(e.target.value)}
                  rows={5}
                  className="w-full bg-[#0d0f1a] border border-[#2e3454] rounded-lg px-2 py-1 text-[11px] text-[#e8eaf6] focus:border-amber-500/50 outline-none resize-none"
                />
              )}
              <button
                onClick={confirm}
                disabled={confirming}
                className="flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-[11px] bg-amber-500/10 text-amber-400 border border-amber-500/20 hover:bg-amber-500/20 transition-all disabled:opacity-50"
              >
                {confirming ? <Loader2 className="w-3 h-3 animate-spin" /> : <CheckCircle2 className="w-3 h-3" />}
                Append to Note
              </button>
            </div>
          )}
          {upload.confirmed && (
            <div className="flex items-center gap-1 mt-2 text-[10px] text-emerald-400">
              <CheckCircle2 className="w-3 h-3" />
              Appended to note
            </div>
          )}
        </>
      )}

      {upload.status === 'failed' && (
        <p className="text-xs text-red-400 mt-1">Transcription failed.</p>
      )}

      {upload.status === 'processing' && (
        <div className="flex items-center gap-1.5 mt-1 text-[10px] text-yellow-400">
          <Loader2 className="w-3 h-3 animate-spin" />
          Transcribing…
        </div>
      )}
    </div>
  )
}

export default function AudioPanel({ storyId }: Props) {
  const [uploads, setUploads] = useState<AudioUploadOut[]>([])
  const [uploading, setUploading] = useState(false)
  const [loading, setLoading] = useState(true)
  const fileRef = useRef<HTMLInputElement>(null)

  // Poll processing uploads every 5 s
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const loadUploads = async () => {
    try {
      const res = await audioApi.list(storyId)
      setUploads(res.data)
    } catch {
      // silent
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadUploads()
    return () => { if (pollRef.current) clearTimeout(pollRef.current) }
  }, [storyId])

  // Poll if any upload is still processing
  useEffect(() => {
    const hasProcessing = uploads.some(u => u.status === 'processing')
    if (hasProcessing) {
      pollRef.current = setTimeout(loadUploads, 5_000)
    }
  }, [uploads])

  const handleFileUpload = async (file: File) => {
    setUploading(true)
    try {
      const res = await audioApi.upload(storyId, file)
      toast.success('Upload started — transcription in progress')
      await loadUploads()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    if (file) handleFileUpload(file)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full gap-2 text-[#5c6391]">
        <Loader2 className="w-4 h-4 animate-spin" />
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="px-3 pt-3 pb-2 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-1.5">
          <Mic className="w-3.5 h-3.5 text-amber-500" />
          <span className="text-xs font-medium text-[#9da3c8]">Audio Notes</span>
        </div>
        <button onClick={loadUploads} className="text-[#5c6391] hover:text-amber-400 transition-colors" title="Refresh">
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Drop zone */}
      <div
        className="mx-3 mb-3 flex-shrink-0"
        onDrop={handleDrop}
        onDragOver={e => e.preventDefault()}
      >
        <button
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
          className="w-full flex items-center justify-center gap-2 py-3 rounded-xl border border-dashed border-[#2e3454] hover:border-amber-500/40 hover:bg-amber-500/5 transition-all text-[#5c6391] hover:text-amber-400 disabled:opacity-50"
        >
          {uploading
            ? <><Loader2 className="w-4 h-4 animate-spin" /><span className="text-xs">Uploading…</span></>
            : <><Upload className="w-4 h-4" /><span className="text-xs">Upload audio or drag & drop</span></>
          }
        </button>
        <input
          ref={fileRef}
          type="file"
          className="hidden"
          accept=".mp3,.mp4,.m4a,.wav,.ogg,.flac,.webm,.opus"
          onChange={e => {
            const file = e.target.files?.[0]
            if (file) handleFileUpload(file)
            e.target.value = ''
          }}
        />
        <p className="text-[10px] text-[#3d4466] text-center mt-1">mp3 · wav · m4a · ogg · flac · webm</p>
      </div>

      {/* Uploads list */}
      <div className="flex-1 overflow-y-auto px-3 pb-4 flex flex-col gap-2">
        {uploads.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-3 py-8">
            <Mic className="w-8 h-8 text-[#2e3454]" />
            <p className="text-xs text-[#5c6391] text-center">Upload an audio note to transcribe it with Whisper AI</p>
          </div>
        ) : (
          uploads.map(u => (
            <TranscriptCard
              key={u.audio_id}
              storyId={storyId}
              upload={u}
              onConfirmed={loadUploads}
            />
          ))
        )}
      </div>
    </div>
  )
}
