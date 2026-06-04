'use client'

import { useState, useRef } from 'react'
import { Camera, Upload, Loader2, Check, Edit3, AlertCircle, X } from 'lucide-react'
import { ocrApi } from '@/lib/api'
import { OcrResult } from '@/lib/types'
import { toast } from 'sonner'

const DESTINATIONS = [
  { id: 'story_notes', label: 'Story Notes' },
  { id: 'chapter_draft', label: 'Current Chapter Draft' },
  { id: 'character_profile', label: 'Character Profile' },
  { id: 'note_card', label: 'Note Card' },
]

interface Props {
  storyId: string
}

export default function OCRPanel({ storyId }: Props) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [extracting, setExtracting] = useState(false)
  const [result, setResult] = useState<OcrResult | null>(null)
  const [editedText, setEditedText] = useState('')
  const [destination, setDestination] = useState('story_notes')
  const [confirming, setConfirming] = useState(false)

  const handleFile = (f: File) => {
    if (!f.type.startsWith('image/')) return toast.error('Please select an image file')
    setFile(f)
    const url = URL.createObjectURL(f)
    setPreview(url)
    setResult(null)
    setEditedText('')
  }

  const extract = async () => {
    if (!file) return
    setExtracting(true)
    try {
      const res = await ocrApi.extract(storyId, file)
      setResult(res.data)
      setEditedText(res.data.cleaned_text)
    } catch {
      toast.error('OCR extraction failed. Please try again.')
    } finally {
      setExtracting(false)
    }
  }

  const confirm = async () => {
    if (!result || !editedText.trim()) return
    setConfirming(true)
    try {
      await ocrApi.confirm(result.upload_id, editedText, destination)
      toast.success(`Note saved to ${DESTINATIONS.find((d) => d.id === destination)?.label}`)
      setPreview(null)
      setFile(null)
      setResult(null)
      setEditedText('')
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
  }

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
            <p className="text-xs text-[#3d4466] mt-2 italic">Tip: Clear, neat handwriting on plain white paper works best</p>
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

        {preview && !result && (
          <button
            onClick={extract}
            disabled={extracting}
            className="w-full bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-black font-semibold py-3 rounded-xl text-sm transition-colors flex items-center justify-center gap-2"
          >
            {extracting ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Extracting text... (~10 seconds)
              </>
            ) : (
              <>
                <Upload className="w-4 h-4" />
                Extract Text
              </>
            )}
          </button>
        )}

        {/* OCR Result */}
        {result && (
          <div className="animate-slide-up space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-xs text-amber-400 font-medium">Text Extracted</span>
              <div className="flex items-center gap-2">
                <span className="text-xs text-[#5c6391]">Engine: {result.ocr_engine}</span>
                <span className={`text-xs ${result.confidence > 0.8 ? 'text-green-400' : result.confidence > 0.6 ? 'text-amber-400' : 'text-red-400'}`}>
                  {Math.round(result.confidence * 100)}% confidence
                </span>
              </div>
            </div>

            {result.confidence < 0.7 && (
              <div className="flex items-start gap-2 bg-amber-500/10 border border-amber-500/20 rounded-xl p-3">
                <AlertCircle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
                <p className="text-xs text-amber-400">Low confidence — please review carefully before saving</p>
              </div>
            )}

            {/* Note type badge */}
            <div className="flex items-center gap-2">
              <span className="text-xs text-[#5c6391]">Classified as:</span>
              <span className="px-2 py-0.5 bg-amber-500/10 border border-amber-500/20 rounded-full text-xs text-amber-400 capitalize">
                {result.note_type}
              </span>
            </div>

            {/* Editable text */}
            <div>
              <div className="flex items-center gap-1 text-xs text-[#5c6391] mb-1.5">
                <Edit3 className="w-3 h-3" />
                Review and edit before saving:
              </div>
              <textarea
                value={editedText}
                onChange={(e) => setEditedText(e.target.value)}
                rows={8}
                className="w-full bg-[#0d0f1a] border border-[#2e3454] rounded-xl px-3 py-2.5 text-sm text-[#e8eaf6] focus:outline-none focus:border-amber-500/50 transition-colors resize-none font-mono"
              />
            </div>

            {/* Destination */}
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

            <button
              onClick={confirm}
              disabled={confirming || !editedText.trim()}
              className="w-full bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-black font-semibold py-3 rounded-xl text-sm transition-colors flex items-center justify-center gap-2"
            >
              {confirming ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
              Confirm & Save to Project
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
