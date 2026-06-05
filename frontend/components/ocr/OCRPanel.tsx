'use client'

import { useState, useRef } from 'react'
import { Camera, Upload, Loader2, Check, Edit3, AlertCircle, X, ChevronDown, ChevronUp, Lightbulb } from 'lucide-react'
import { ocrApi } from '@/lib/api'
import { OcrResult, OcrSuggestion } from '@/lib/types'
import { toast } from 'sonner'

const DESTINATIONS = [
  { id: 'story_notes',       label: 'Story Notes' },
  { id: 'chapter_draft',     label: 'Current Chapter Draft' },
  { id: 'character_profile', label: 'Character Profile' },
  { id: 'note_card',         label: 'Note Card' },
]

interface Props {
  storyId: string
}

export default function OCRPanel({ storyId }: Props) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [preview, setPreview]           = useState<string | null>(null)
  const [file, setFile]                 = useState<File | null>(null)
  const [extracting, setExtracting]     = useState(false)
  const [result, setResult]             = useState<OcrResult | null>(null)
  const [editedText, setEditedText]     = useState('')
  const [destination, setDestination]   = useState('story_notes')
  const [confirming, setConfirming]     = useState(false)
  const [showRaw, setShowRaw]           = useState(false)
  // Tracks which suggestion originals the author has dismissed (applied or ignored)
  const [dismissed, setDismissed]       = useState<Set<string>>(new Set())

  // Active suggestions = all suggestions minus dismissed ones
  const activeSuggestions: OcrSuggestion[] = (result?.suggestions ?? []).filter(
    s => !dismissed.has(s.original)
  )

  const applySuggestion = (s: OcrSuggestion) => {
    // Replace ALL occurrences of the OCR term with the suggested story term
    setEditedText(prev => prev.replaceAll(s.original, s.suggested))
    setDismissed(prev => new Set([...prev, s.original]))
    toast.success(`"${s.original}" replaced with "${s.suggested}"`)
  }

  const ignoreSuggestion = (s: OcrSuggestion) => {
    setDismissed(prev => new Set([...prev, s.original]))
  }

  const handleFile = (f: File) => {
    if (!f.type.startsWith('image/')) return toast.error('Please select an image file')
    setFile(f)
    setPreview(URL.createObjectURL(f))
    setResult(null)
    setEditedText('')
    setShowRaw(false)
    setDismissed(new Set())
  }

  const extract = async () => {
    if (!file) return
    setExtracting(true)
    setDismissed(new Set())
    try {
      const res = await ocrApi.extract(storyId, file)
      const data: OcrResult = res.data
      setResult(data)
      // Prefer Qwen-cleaned text; fall back to raw OCR if cleanup produced nothing
      setEditedText(data.cleaned_text || data.raw_text)
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      toast.error(detail || 'OCR extraction failed. Please try again.')
    } finally {
      setExtracting(false)
    }
  }

  const confirm = async () => {
    if (!result || !editedText.trim()) return
    setConfirming(true)
    try {
      await ocrApi.confirm(result.upload_id, editedText, destination)
      toast.success(`Note saved to ${DESTINATIONS.find(d => d.id === destination)?.label}`)
      setPreview(null)
      setFile(null)
      setResult(null)
      setEditedText('')
      setShowRaw(false)
      setDismissed(new Set())
    } catch {
      toast.error('Failed to save note')
    } finally {
      setConfirming(false)
    }
  }

  const reset = () => {
    setPreview(null)
    setFile(null)
    setResult(null)
    setEditedText('')
    setShowRaw(false)
    setDismissed(new Set())
  }

  // True extraction failure: GOT-OCR2.0 returned no text
  const extractionFailed = result !== null && !result.raw_text && !result.cleaned_text

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-4 py-3 border-b border-[#1f2440]">
        <div className="flex items-center gap-2">
          <Camera className="w-4 h-4 text-amber-500" />
          <span className="text-xs font-medium text-[#9da3c8] uppercase tracking-wider">Handwritten Notes OCR</span>
        </div>
        <p className="text-xs text-[#3d4466] mt-1">Photograph your notes → AI extracts & cleans → inject into project</p>
      </div>

      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4">

        {/* Upload area */}
        {!preview ? (
          <div
            onClick={() => fileRef.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) handleFile(f) }}
            className="border-2 border-dashed border-[#2e3454] rounded-xl p-8 text-center cursor-pointer hover:border-amber-500/40 hover:bg-amber-500/5 transition-all"
          >
            <Camera className="w-10 h-10 text-[#3d4466] mx-auto mb-3" />
            <p className="text-sm text-[#9da3c8] mb-1">Upload handwritten note photo</p>
            <p className="text-xs text-[#3d4466]">JPEG, PNG, WebP — drag & drop or click</p>
            <p className="text-xs text-[#3d4466] mt-2 italic">Tip: Clear handwriting on plain white paper gives best results</p>
          </div>
        ) : (
          <div className="relative">
            <img src={preview} alt="Preview" className="w-full rounded-xl border border-[#2e3454] max-h-48 object-cover" />
            <button
              onClick={reset}
              className="absolute top-2 right-2 p-1 bg-[#0d0f1a]/80 rounded-full text-[#9da3c8] hover:text-red-400"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        <input
          ref={fileRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className="hidden"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f) }}
        />

        {/* Extract button */}
        {preview && !result && (
          <button
            onClick={extract}
            disabled={extracting}
            className="w-full bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-black font-semibold py-3 rounded-xl text-sm transition-colors flex items-center justify-center gap-2"
          >
            {extracting ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Extracting text… (GOT-OCR2.0, ~25–60 seconds on CPU)
              </>
            ) : (
              <>
                <Upload className="w-4 h-4" />
                Extract Text
              </>
            )}
          </button>
        )}

        {/* ── OCR Result ─────────────────────────────────────────────────── */}
        {result && (
          <div className="animate-slide-up space-y-4">

            {/* Extraction failed — no text detected */}
            {extractionFailed ? (
              <div className="flex flex-col gap-3">
                <div className="flex items-start gap-2 bg-red-500/10 border border-red-500/30 rounded-xl p-4">
                  <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="text-sm font-medium text-red-400 mb-1">No text detected</p>
                    <p className="text-xs text-red-300/80 leading-relaxed">
                      The OCR pipeline could not find any text in this image.
                    </p>
                  </div>
                </div>
                <div className="bg-[#0d0f1a] border border-[#1f2440] rounded-xl p-3">
                  <p className="text-xs font-medium text-[#9da3c8] mb-2">Tips for better results:</p>
                  <ul className="text-xs text-[#5c6391] space-y-1">
                    <li>• Use plain white or light-coloured paper</li>
                    <li>• Ensure good, even lighting — avoid shadows</li>
                    <li>• Keep handwriting dark and clear</li>
                    <li>• Hold the phone directly above the paper (avoid angles)</li>
                    <li>• Avoid very small or faint handwriting</li>
                  </ul>
                </div>
                <button
                  onClick={reset}
                  className="w-full border border-[#2e3454] text-[#9da3c8] hover:border-amber-500/40 hover:text-amber-400 font-medium py-2.5 rounded-xl text-sm transition-colors"
                >
                  Try a different image
                </button>
              </div>
            ) : (
              <>
                {/* Confidence + engine + lines info */}
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <span className="text-xs text-amber-400 font-medium">Text Extracted</span>
                  <div className="flex items-center gap-3 text-xs text-[#5c6391]">
                    <span title="OCR engine used">Engine: {result.ocr_engine}</span>
                    <span
                      className={
                        result.confidence > 0.8
                          ? 'text-green-400'
                          : result.confidence > 0.5
                          ? 'text-amber-400'
                          : 'text-red-400'
                      }
                      title="Extraction quality score — ratio of word-like tokens in the output"
                    >
                      {Math.round(result.confidence * 100)}% quality
                    </span>
                  </div>
                </div>

                {/* Low confidence warning */}
                {result.confidence < 0.5 && result.confidence > 0 && (
                  <div className="flex items-start gap-2 bg-amber-500/10 border border-amber-500/20 rounded-xl p-3">
                    <AlertCircle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
                    <p className="text-xs text-amber-400">
                      Low confidence — review the extracted text carefully before saving.
                    </p>
                  </div>
                )}

                {/* Note type badge */}
                {result.note_type && result.note_type !== 'other' && (
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-[#5c6391]">Classified as:</span>
                    <span className="px-2 py-0.5 bg-amber-500/10 border border-amber-500/20 rounded-full text-xs text-amber-400 capitalize">
                      {result.note_type}
                    </span>
                  </div>
                )}

                {/* Editable cleaned text */}
                <div>
                  <div className="flex items-center gap-1 text-xs text-[#5c6391] mb-1.5">
                    <Edit3 className="w-3 h-3" />
                    {result.cleaned_text
                      ? 'AI-cleaned text — review and edit before saving:'
                      : 'Raw OCR text — review and edit before saving:'}
                  </div>
                  <textarea
                    value={editedText}
                    onChange={(e) => setEditedText(e.target.value)}
                    rows={8}
                    className="w-full bg-[#0d0f1a] border border-[#2e3454] rounded-xl px-3 py-2.5 text-sm text-[#e8eaf6] focus:outline-none focus:border-amber-500/50 transition-colors resize-none font-mono"
                  />
                </div>

                {/* Raw OCR output — collapsible, for review/debugging */}
                {result.raw_text && result.cleaned_text && result.raw_text !== result.cleaned_text && (
                  <div className="border border-[#1f2440] rounded-xl overflow-hidden">
                    <button
                      onClick={() => setShowRaw(!showRaw)}
                      className="w-full flex items-center justify-between px-3 py-2 text-xs text-[#5c6391] hover:text-[#9da3c8] hover:bg-[#0d0f1a] transition-colors"
                    >
                      <span>Raw OCR output (before AI cleanup)</span>
                      {showRaw
                        ? <ChevronUp className="w-3.5 h-3.5" />
                        : <ChevronDown className="w-3.5 h-3.5" />
                      }
                    </button>
                    {showRaw && (
                      <pre className="px-3 py-2.5 text-xs text-[#5c6391] bg-[#0d0f1a] font-mono whitespace-pre-wrap break-words border-t border-[#1f2440]">
                        {result.raw_text}
                      </pre>
                    )}
                  </div>
                )}

                {/* ── Story-context suggestions ─────────────────────────── */}
                {activeSuggestions.length > 0 && (
                  <div className="border border-amber-500/20 rounded-xl overflow-hidden">
                    {/* Header */}
                    <div className="flex items-center gap-2 px-3 py-2 bg-amber-500/5 border-b border-amber-500/20">
                      <Lightbulb className="w-3.5 h-3.5 text-amber-500 flex-shrink-0" />
                      <span className="text-xs font-medium text-amber-400">
                        Possible Corrections Using Story Context
                      </span>
                      <span className="ml-auto text-xs text-[#5c6391]">
                        {activeSuggestions.length} suggestion{activeSuggestions.length !== 1 ? 's' : ''}
                      </span>
                    </div>

                    {/* Note — author retains full control */}
                    <p className="px-3 pt-2 text-xs text-[#5c6391] leading-relaxed">
                      These are possible matches from your manuscript. Review carefully — OCR may have
                      captured a new name that genuinely differs from an existing character.
                    </p>

                    {/* Suggestion cards */}
                    <div className="p-3 flex flex-col gap-2">
                      {activeSuggestions.map((s) => (
                        <div
                          key={s.original}
                          className="bg-[#0d0f1a] border border-[#2e3454] rounded-xl p-3"
                        >
                          {/* Term comparison row */}
                          <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                            <span className="text-xs font-mono px-1.5 py-0.5 rounded bg-red-500/10 text-red-400 border border-red-500/20">
                              {s.original}
                            </span>
                            <span className="text-xs text-[#3d4466]">→</span>
                            <span className="text-xs font-mono px-1.5 py-0.5 rounded bg-green-500/10 text-green-400 border border-green-500/20">
                              {s.suggested}
                            </span>
                            {/* Confidence badge */}
                            <span
                              className={`ml-auto text-xs font-medium ${
                                s.confidence >= 0.80 ? 'text-green-400'
                                : s.confidence >= 0.65 ? 'text-amber-400'
                                : 'text-[#5c6391]'
                              }`}
                              title="String similarity to story term"
                            >
                              {Math.round(s.confidence * 100)}%
                            </span>
                          </div>

                          {/* Reason */}
                          <p className="text-xs text-[#5c6391] mb-2.5">{s.reason}</p>

                          {/* Action buttons */}
                          <div className="flex gap-2">
                            <button
                              onClick={() => applySuggestion(s)}
                              className="flex-1 text-xs py-1.5 rounded-lg bg-green-500/10 border border-green-500/20 text-green-400 hover:bg-green-500/20 transition-colors font-medium"
                            >
                              Apply
                            </button>
                            <button
                              onClick={() => ignoreSuggestion(s)}
                              className="flex-1 text-xs py-1.5 rounded-lg border border-[#2e3454] text-[#5c6391] hover:text-[#9da3c8] hover:border-[#3d4466] transition-colors"
                            >
                              Ignore
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Destination picker */}
                <div>
                  <label className="text-xs text-[#5c6391] mb-1.5 block">Save to:</label>
                  <div className="grid grid-cols-2 gap-1.5">
                    {DESTINATIONS.map((d) => (
                      <button
                        key={d.id}
                        onClick={() => setDestination(d.id)}
                        className={`py-2 px-2 rounded-lg border text-xs text-left transition-all ${
                          destination === d.id
                            ? 'border-amber-500/50 bg-amber-500/10 text-amber-400'
                            : 'border-[#1f2440] text-[#9da3c8] hover:border-[#2e3454]'
                        }`}
                      >
                        {d.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Save button */}
                <button
                  onClick={confirm}
                  disabled={confirming || !editedText.trim()}
                  className="w-full bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-black font-semibold py-3 rounded-xl text-sm transition-colors flex items-center justify-center gap-2"
                >
                  {confirming ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                  Confirm & Save to Project
                </button>
              </>
            )}
          </div>
        )}

      </div>
    </div>
  )
}
