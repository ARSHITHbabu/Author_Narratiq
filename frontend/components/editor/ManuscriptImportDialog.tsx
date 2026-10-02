'use client'

// Stage 12 A8 — Import a manuscript (.txt / .docx) into the open story.
//
// The backend saves every chapter in one transaction before it answers, numbered
// after the story's existing chapters; only AI preparation (summaries, search
// index) runs afterwards. So once the upload succeeds the author's text is safe,
// and this dialog says so plainly — even if the preparation step later stops.

import { useEffect, useRef, useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { AlertTriangle, CheckCircle2, FileUp, Loader2, X } from 'lucide-react'
import { manuscriptApi } from '@/lib/api'
import { selectionSafeProps } from '@/lib/selectionOwnership'

const MAX_MB = 25
const ACCEPT = '.txt,.docx,text/plain,application/vnd.openxmlformats-officedocument.wordprocessingml.document'
const POLL_MS = 2000

type Phase =
  | { kind: 'idle' }
  | { kind: 'uploading' }
  | { kind: 'preparing'; saved: number; stage: string; percent: number }
  | { kind: 'done'; saved: number; message: string }
  | { kind: 'partial'; saved: number; message: string }
  | { kind: 'saved-unknown'; saved: number }
  | { kind: 'failed'; message: string }

interface Props {
  storyId: string
  existingChapters: number
  onClose: () => void
  /** Called as soon as chapters are saved, so the binder can show them. */
  onImported: () => void
}

function friendlyUploadError(err: any): string {
  const status = err?.response?.status
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string' && status && status < 500 && !/Traceback|Exception/.test(detail)) return detail
  if (status === 413) return `This file is larger than ${MAX_MB} MB. Nothing was imported.`
  if (status === 429) return 'Too many uploads in a short time. Wait a minute and try again. Nothing was imported.'
  if (typeof detail === 'string' && status === 500 && detail.includes('Nothing was imported')) return detail
  if (!err?.response) return 'The server could not be reached. Nothing was imported — check your connection and try again.'
  return 'The import did not complete. Nothing was imported and your chapters are unchanged. Please try again.'
}

export default function ManuscriptImportDialog({ storyId, existingChapters, onClose, onImported }: Props) {
  const [file, setFile] = useState<File | null>(null)
  const [fileError, setFileError] = useState<string | null>(null)
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' })
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const alive = useRef(true)

  useEffect(() => () => {
    alive.current = false
    if (timer.current) clearTimeout(timer.current)
  }, [])

  const pick = (f: File | null) => {
    setFileError(null)
    setFile(null)
    if (!f) return
    const name = f.name.toLowerCase()
    if (!name.endsWith('.txt') && !name.endsWith('.docx')) {
      setFileError('Choose a .txt or .docx file. Other formats (PDF, .doc, .rtf) cannot be imported.')
      return
    }
    if (f.size > MAX_MB * 1024 * 1024) {
      setFileError(`This file is larger than ${MAX_MB} MB.`)
      return
    }
    if (f.size === 0) {
      setFileError('This file is empty.')
      return
    }
    setFile(f)
  }

  const poll = (jobId: string, saved: number, failures = 0) => {
    timer.current = setTimeout(async () => {
      if (!alive.current) return
      try {
        const { data } = await manuscriptApi.jobStatus(jobId)
        if (!alive.current) return
        if (data.status === 'complete') {
          setPhase({ kind: 'done', saved, message: data.message || `${saved} chapters imported.` })
        } else if (data.status === 'partial' || data.status === 'error') {
          setPhase({ kind: 'partial', saved, message: data.message })
        } else {
          setPhase({ kind: 'preparing', saved, stage: data.stage, percent: data.percent })
          poll(jobId, saved)
        }
      } catch {
        if (failures >= 4) setPhase({ kind: 'saved-unknown', saved })
        else poll(jobId, saved, failures + 1)
      }
    }, POLL_MS)
  }

  const start = async () => {
    if (!file) return
    setPhase({ kind: 'uploading' })
    try {
      const { data } = await manuscriptApi.upload(storyId, file)
      if (!alive.current) return
      onImported()
      setPhase({ kind: 'preparing', saved: data.chapter_count, stage: 'Preparing chapters for AI tools', percent: 10 })
      poll(data.job_id, data.chapter_count)
    } catch (err) {
      if (alive.current) setPhase({ kind: 'failed', message: friendlyUploadError(err) })
    }
  }

  const busy = phase.kind === 'uploading'
  const plural = (n: number) => `${n} chapter${n !== 1 ? 's' : ''}`

  return (
    <Dialog.Root open onOpenChange={(o) => { if (!o && !busy) onClose() }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/60 z-50" />
        <Dialog.Content {...selectionSafeProps()} data-testid="manuscript-import-dialog"
          className="fixed z-50 left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[min(92vw,30rem)] bg-[#0d0f1a] border border-[#1f2440] rounded-2xl shadow-2xl p-5 text-[#e8eaf6]">
          <div className="flex items-center gap-2 mb-3">
            <FileUp className="w-4 h-4 text-amber-400" />
            <Dialog.Title className="text-sm font-semibold flex-1">Import manuscript</Dialog.Title>
            <Dialog.Close disabled={busy} aria-label="Close" className="p-1 rounded text-[#9da3c8] hover:text-white disabled:opacity-40">
              <X className="w-4 h-4" />
            </Dialog.Close>
          </div>
          <Dialog.Description className="text-xs text-[#9da3c8] leading-relaxed">
            Add a .txt or .docx file (up to {MAX_MB} MB) to this story. Lines such as &ldquo;Chapter 1&rdquo; start a new
            chapter. {existingChapters > 0
              ? <>The imported chapters are added after your existing {plural(existingChapters)}, which are not changed.</>
              : <>The imported chapters become this story&rsquo;s chapters.</>}
          </Dialog.Description>

          {(phase.kind === 'idle' || phase.kind === 'failed') && (
            <div className="mt-4 flex flex-col gap-3">
              <label className="text-xs text-[#cdd2f0]">
                <span className="block mb-1">Manuscript file</span>
                <input data-testid="manuscript-file-input" type="file" accept={ACCEPT}
                  onChange={(e) => pick(e.target.files?.[0] ?? null)}
                  className="block w-full text-xs text-[#9da3c8] file:mr-3 file:rounded-lg file:border-0 file:bg-[#1f2440] file:px-3 file:py-1.5 file:text-[#e8eaf6]" />
              </label>
              {fileError && <p role="alert" className="text-xs text-red-300">{fileError}</p>}
              {phase.kind === 'failed' && (
                <p role="alert" data-testid="manuscript-import-error" className="text-xs text-red-300 flex gap-1.5">
                  <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />{phase.message}
                </p>
              )}
              <div className="flex justify-end gap-2">
                <button onClick={onClose} className="text-xs px-3 py-1.5 rounded-lg border border-[#2e3454] text-[#8e94bd] hover:text-[#cdd2f0]">
                  Cancel
                </button>
                <button data-testid="manuscript-import-start" onClick={start} disabled={!file}
                  className="text-xs px-4 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-600 text-black font-semibold disabled:opacity-40 disabled:cursor-not-allowed">
                  Import
                </button>
              </div>
            </div>
          )}

          {phase.kind === 'uploading' && (
            <p className="mt-4 text-xs text-[#cdd2f0] flex items-center gap-2" role="status">
              <Loader2 className="w-3.5 h-3.5 animate-spin" /> Saving your chapters…
            </p>
          )}

          {phase.kind === 'preparing' && (
            <div className="mt-4 flex flex-col gap-2" role="status" data-testid="manuscript-import-preparing">
              <p className="text-xs text-emerald-300 flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5" /> {plural(phase.saved)} saved to your story.
              </p>
              <p className="text-xs text-[#9da3c8] flex items-center gap-2">
                <Loader2 className="w-3.5 h-3.5 animate-spin" /> {phase.stage}…
              </p>
              <div className="h-1 bg-[#1f2440] rounded" aria-hidden>
                <div className="h-1 bg-amber-500 rounded transition-all" style={{ width: `${phase.percent}%` }} />
              </div>
              <p className="text-[11px] text-[#8a90ba]">
                You can close this window and keep writing — your chapters are already saved.
              </p>
            </div>
          )}

          {phase.kind === 'done' && (
            <div className="mt-4 flex flex-col gap-3" role="status" data-testid="manuscript-import-done">
              <p className="text-xs text-emerald-300 flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5" /> {phase.message} Search and AI tools can now use them.
              </p>
              <div className="flex justify-end">
                <button onClick={onClose} className="text-xs px-4 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-600 text-black font-semibold">Done</button>
              </div>
            </div>
          )}

          {(phase.kind === 'partial' || phase.kind === 'saved-unknown') && (
            <div className="mt-4 flex flex-col gap-3" role="status" data-testid="manuscript-import-partial">
              <p className="text-xs text-emerald-300 flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5" /> {plural(phase.saved)} saved to your story.
              </p>
              <p className="text-xs text-amber-200 flex gap-1.5">
                <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                {phase.kind === 'partial'
                  ? phase.message
                  : 'We could not check whether search and AI preparation finished. Your chapters are saved; if a tool does not find them, open and save the chapter.'}
              </p>
              <div className="flex justify-end">
                <button onClick={onClose} className="text-xs px-4 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-600 text-black font-semibold">Close</button>
              </div>
            </div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
