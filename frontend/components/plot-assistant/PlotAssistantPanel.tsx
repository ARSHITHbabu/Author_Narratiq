'use client'

import { useState } from 'react'
import { Brain, Loader2, Send, Copy, Check, Sparkles, MessageSquare, Lightbulb } from 'lucide-react'
import { plotApi } from '@/lib/api'
import { PlotSuggestion, PlotAssistantResponse } from '@/lib/types'
import { toast } from 'sonner'

const CREATIVE_TEMPLATES = [
  { label: "What should happen next?",      prompt: "What should happen next in my story?" },
  { label: "Suggest a plot twist",          prompt: "Suggest a surprising plot twist that fits my story." },
  { label: "I'm stuck — give me ideas",     prompt: "I'm stuck. Give me 5 varied directions this story could go from here." },
  { label: "Conflict ideas",                prompt: "Give me conflict ideas between my established characters." },
  { label: "Better chapter ending",         prompt: "Suggest a better ending for this chapter with more narrative hook." },
  { label: "Make scene more intense",       prompt: "How can I make this scene more intense and genre-appropriate?" },
  { label: "Character motivation ideas",    prompt: "Give me character motivation ideas that fit my story." },
]

const MODE_LABEL: Record<string, string> = {
  qa:          'Answer',
  suggestions: 'Suggestions',
  mixed:       'Answer + Suggestions',
}

const MODE_COLOR: Record<string, string> = {
  qa:          'text-sky-400',
  suggestions: 'text-amber-400',
  mixed:       'text-violet-400',
}

interface Props {
  storyId: string
  getEditorText: () => string
}

export default function PlotAssistantPanel({ storyId, getEditorText }: Props) {
  const [question, setQuestion]   = useState('')
  const [loading, setLoading]     = useState(false)
  const [result, setResult]       = useState<PlotAssistantResponse | null>(null)
  const [copiedId, setCopiedId]   = useState<number | null>(null)
  const [answerCopied, setAnswerCopied] = useState(false)

  const ask = async (q?: string) => {
    const finalQ = q || question.trim()
    if (!finalQ) return toast.error('Select a question or type your own')
    setLoading(true)
    setResult(null)
    try {
      const res = await plotApi.suggest(storyId, finalQ, getEditorText().slice(0, 1500))
      setResult(res.data as PlotAssistantResponse)
      if (q) setQuestion('')
    } catch (err: any) {
      const msg = err?.response?.data?.detail || 'Plot assistant failed. Please try again.'
      toast.error(msg)
    } finally {
      setLoading(false)
    }
  }

  const copySuggestion = (s: PlotSuggestion) => {
    navigator.clipboard.writeText(s.text)
    setCopiedId(s.id)
    setTimeout(() => setCopiedId(null), 2000)
    toast.success('Copied to clipboard')
  }

  const copyAnswer = () => {
    if (!result?.answer) return
    navigator.clipboard.writeText(result.answer)
    setAnswerCopied(true)
    setTimeout(() => setAnswerCopied(false), 2000)
    toast.success('Copied to clipboard')
  }

  const markUsed = async (index: number) => {
    if (!result?.session_id) return
    try {
      await plotApi.markUsed(result.session_id, index)
      toast.success('Great! Used in your story.')
    } catch {}
  }

  // Direct null check so TypeScript narrows result to non-null inside the JSX block.
  // 'hasContent' via a derived variable breaks TypeScript narrowing and causes a
  // TS2531 "possibly null" error that silently prevents the component updating.
  const hasResult = result !== null

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-4 py-3 border-b border-[#1f2440]">
        <div className="flex items-center gap-2">
          <Brain className="w-4 h-4 text-amber-500" />
          <span className="text-xs font-medium text-[#9da3c8] uppercase tracking-wider">Plot Assistant</span>
        </div>
        <p className="text-xs text-[#3d4466] mt-1">Ask anything — story facts or creative ideas</p>
      </div>

      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4">

        {/* Quick creative templates */}
        <div>
          <div className="flex items-center gap-1.5 text-xs text-[#5c6391] mb-2.5">
            <Sparkles className="w-3 h-3 text-amber-500/70" />
            <span>Creative templates</span>
          </div>
          <div className="flex flex-col gap-1.5">
            {CREATIVE_TEMPLATES.map((t) => (
              <button
                key={t.label}
                onClick={() => ask(t.prompt)}
                disabled={loading}
                className="text-left text-sm px-3.5 py-2.5 bg-[#0d0f1a] border border-[#1f2440] rounded-xl text-[#9da3c8] hover:border-amber-500/40 hover:text-[#e8eaf6] hover:bg-[#13162a] transition-all disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>

        {/* Divider */}
        <div className="flex items-center gap-3">
          <div className="flex-1 h-px bg-[#1f2440]" />
          <span className="text-xs text-[#3d4466]">or ask your own</span>
          <div className="flex-1 h-px bg-[#1f2440]" />
        </div>

        {/* Input */}
        <div className="relative">
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask() } }}
            placeholder={'Ask a story question or request ideas...\nExamples:\n  "Who is Mr. Dinesh?"\n  "Suggest a plot twist involving Ravi."'}
            rows={3}
            className="w-full bg-[#0d0f1a] border border-[#2e3454] rounded-xl px-3 py-2.5 text-sm text-[#e8eaf6] placeholder-[#3d4466] focus:outline-none focus:border-amber-500/50 transition-colors resize-none pr-10"
          />
          <button
            onClick={() => ask()}
            disabled={loading || !question.trim()}
            className="absolute right-2 bottom-2.5 p-1.5 bg-amber-500 rounded-lg text-black hover:bg-amber-600 disabled:opacity-40 transition-colors"
          >
            {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
          </button>
        </div>

        {/* Loading */}
        {loading && (
          <div className="flex flex-col items-center gap-3 py-6 text-[#5c6391]">
            <div className="flex items-center gap-2 text-sm">
              <Brain className="w-4 h-4 text-amber-500 animate-pulse" />
              <span>Reading your story context...</span>
            </div>
            <p className="text-xs text-[#3d4466]">Detecting intent · Searching chapters · Asking Qwen</p>
          </div>
        )}

        {/* Results — direct null guard lets TypeScript narrow result to non-null */}
        {result && (
          <div className="flex flex-col gap-3">

            {/* Context + mode badge */}
            <div className="flex items-center justify-between">
              <span className={`text-xs font-medium ${MODE_COLOR[result.mode] ?? 'text-amber-400'}`}>
                {MODE_LABEL[result.mode] ?? result.mode}
              </span>
              {result.context_used && (
                <span className="text-xs text-[#3d4466] truncate max-w-[160px]" title={result.context_used}>
                  {result.context_used}
                </span>
              )}
            </div>

            {/* Q&A answer card */}
            {result.answer && (
              <div className="bg-[#0d0f1a] border border-sky-500/20 rounded-xl p-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-1.5">
                    <MessageSquare className="w-3.5 h-3.5 text-sky-400" />
                    <span className="text-xs font-medium text-sky-400">Answer</span>
                  </div>
                  <button
                    onClick={copyAnswer}
                    className="text-[#5c6391] hover:text-sky-400 transition-colors"
                    title="Copy answer"
                  >
                    {answerCopied
                      ? <Check className="w-3.5 h-3.5 text-green-400" />
                      : <Copy className="w-3.5 h-3.5" />
                    }
                  </button>
                </div>
                <p className="text-sm text-[#e8eaf6] leading-relaxed whitespace-pre-wrap">{result.answer}</p>
              </div>
            )}

            {/* Suggestions */}
            {result.suggestions.length > 0 && (
              <div className="flex flex-col gap-3">
                {result.mode === 'mixed' && (
                  <div className="flex items-center gap-1.5 text-xs text-[#5c6391]">
                    <Lightbulb className="w-3 h-3 text-amber-500/70" />
                    <span>Creative suggestions based on your story</span>
                  </div>
                )}
                {result.suggestions.map((s, i) => (
                  <div
                    key={s.id}
                    className="bg-[#0d0f1a] border border-[#1f2440] rounded-xl p-4 hover:border-[#2e3454] transition-all"
                  >
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <span className="text-xs font-bold text-amber-500 flex-shrink-0">#{s.id}</span>
                      <button
                        onClick={() => copySuggestion(s)}
                        className="text-[#5c6391] hover:text-amber-400 transition-colors flex-shrink-0"
                      >
                        {copiedId === s.id
                          ? <Check className="w-3.5 h-3.5 text-green-400" />
                          : <Copy className="w-3.5 h-3.5" />
                        }
                      </button>
                    </div>
                    <p className="text-sm text-[#e8eaf6] leading-relaxed mb-2">{s.text}</p>
                    <p className="text-xs text-[#5c6391] italic border-t border-[#1f2440] pt-2">{s.rationale}</p>
                    <button
                      onClick={() => markUsed(i)}
                      className="mt-2 text-xs text-amber-400/50 hover:text-amber-400 transition-colors"
                    >
                      ✓ Using this idea
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Empty state */}
        {!loading && !hasResult && (
          <div className="flex flex-col items-center gap-3 py-6 text-center">
            <Brain className="w-8 h-8 text-[#2e3454]" />
            <div>
              <p className="text-xs text-[#5c6391] font-medium">Ask a story question or request ideas</p>
              <p className="text-xs text-[#3d4466] mt-1">
                "Who is Ravi?" → direct answer<br />
                "Suggest a twist" → 4 creative ideas
              </p>
            </div>
          </div>
        )}

      </div>
    </div>
  )
}
