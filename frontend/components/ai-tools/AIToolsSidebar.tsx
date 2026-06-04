'use client'

import { useState } from 'react'
import {
  Wand2, Palette, Heart, Users, Type, Globe,
  Copy, Check, Loader2, X, ArrowDownToLine
} from 'lucide-react'
import { aiApi } from '@/lib/api'
import { TransformResponse } from '@/lib/types'
import { toast } from 'sonner'

interface Props {
  storyId: string
  chapterId: string
  getSelectedText: () => string
  getFullText: () => string
  insertText?: (text: string) => void
}

type TabId = 'refine' | 'tone' | 'emotion' | 'age' | 'style' | 'translate'

const TABS = [
  { id: 'refine' as TabId, label: 'Refine', icon: Wand2 },
  { id: 'tone' as TabId, label: 'Tone', icon: Palette },
  { id: 'emotion' as TabId, label: 'Emotion', icon: Heart },
  { id: 'age' as TabId, label: 'Audience', icon: Users },
  { id: 'style' as TabId, label: 'Style', icon: Type },
  { id: 'translate' as TabId, label: 'Translate', icon: Globe },
]

const TONES = [
  { id: 'Dark', emoji: '🌑' },
  { id: 'Suspenseful', emoji: '⚡' },
  { id: 'Romantic', emoji: '🌹' },
  { id: 'Humorous', emoji: '😄' },
  { id: 'Epic', emoji: '⚔️' },
  { id: 'Melancholic', emoji: '🌧️' },
  { id: 'Hopeful', emoji: '🌤️' },
  { id: 'Tense', emoji: '🔥' },
  { id: 'Lyrical', emoji: '🎵' },
]

const EMOTIONS = [
  { id: 'Joy', emoji: '✨' },
  { id: 'Sadness', emoji: '💧' },
  { id: 'Fear', emoji: '😰' },
  { id: 'Anger', emoji: '💢' },
  { id: 'Surprise', emoji: '⚡' },
  { id: 'Anticipation', emoji: '🎯' },
]

const STYLES = [
  { id: 'Gothic', desc: 'Dark, ornate, brooding' },
  { id: 'Noir', desc: 'Hard-boiled, cynical' },
  { id: 'Contemporary', desc: 'Modern, accessible' },
  { id: 'Minimalist', desc: 'Spare, precise' },
  { id: 'Lyrical', desc: 'Musical, poetic' },
  { id: 'Pulp', desc: 'Fast, visceral' },
  { id: 'Literary', desc: 'Layered, introspective' },
  { id: 'Thriller', desc: 'Taut, relentless' },
]

const LANGUAGES = [
  'French', 'Spanish', 'German', 'Italian', 'Portuguese', 'Japanese', 'Korean',
  'Chinese (Simplified)', 'Russian', 'Arabic', 'Hindi', 'Tamil', 'Dutch', 'Polish',
]

function ResultPanel({
  result,
  hasSelection,
  onClose,
  onInsert,
}: {
  result: TransformResponse
  hasSelection: boolean
  onClose: () => void
  onInsert?: (text: string) => void
}) {
  const [copied, setCopied] = useState(false)

  const copy = () => {
    navigator.clipboard.writeText(result.transformed)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
    toast.success('Copied to clipboard')
  }

  const insert = () => {
    onInsert?.(result.transformed)
    toast.success(hasSelection ? 'Selection replaced' : 'Inserted at cursor')
    onClose()
  }

  return (
    <div className="mt-4 border border-amber-500/30 rounded-xl overflow-hidden animate-slide-up">
      <div className="flex items-center justify-between px-3 py-2 bg-amber-500/10 border-b border-amber-500/20">
        <span className="text-xs font-medium text-amber-400">AI Result</span>
        <div className="flex items-center gap-2">
          <button onClick={copy} className="text-xs text-[#9da3c8] hover:text-amber-400 flex items-center gap-1">
            {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
            {copied ? 'Copied' : 'Copy'}
          </button>
          <button onClick={onClose} className="text-[#5c6391] hover:text-[#9da3c8]">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      <div className="p-3 bg-[#0d0f1a]">
        <p className="text-xs text-[#9da3c8] leading-relaxed font-serif whitespace-pre-wrap">
          {result.transformed}
        </p>
      </div>

      <div className="px-3 py-2.5 border-t border-[#1f2440] flex items-center justify-between gap-2">
        <span className="text-xs text-[#3d4466]">{result.tokens_used} tokens</span>
        {onInsert && (
          <button
            onClick={insert}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-500 hover:bg-amber-600 text-black rounded-lg text-xs font-semibold transition-colors"
          >
            <ArrowDownToLine className="w-3 h-3" />
            {hasSelection ? 'Replace Selection' : 'Insert at Cursor'}
          </button>
        )}
      </div>
    </div>
  )
}

export default function AIToolsSidebar({ storyId, chapterId, getSelectedText, getFullText, insertText }: Props) {
  const [activeTab, setActiveTab] = useState<TabId>('refine')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<TransformResponse | null>(null)
  const [selectedTone, setSelectedTone] = useState('Dark')
  const [selectedEmotion, setSelectedEmotion] = useState('Fear')
  const [intensity, setIntensity] = useState('medium')
  const [selectedAge, setSelectedAge] = useState('adult')
  const [selectedStyle, setSelectedStyle] = useState('Gothic')
  const [selectedLang, setSelectedLang] = useState('French')
  const [refineMode, setRefineMode] = useState('standard')
  const [hadSelection, setHadSelection] = useState(false)

  const getText = () => {
    const sel = getSelectedText()
    return sel.trim() || getFullText().slice(0, 2000)
  }

  const run = async () => {
    const text = getText()
    if (!text) return toast.error('Write some text in the editor first')
    const sel = getSelectedText()
    setHadSelection(!!sel.trim())
    setLoading(true)
    setResult(null)
    try {
      let res
      switch (activeTab) {
        case 'refine': res = await aiApi.refine(text, refineMode, storyId, chapterId); break
        case 'tone': res = await aiApi.tone(text, selectedTone.toLowerCase(), storyId); break
        case 'emotion': res = await aiApi.emotion(text, selectedEmotion.toLowerCase(), intensity); break
        case 'age': res = await aiApi.ageAdapt(text, selectedAge, storyId); break
        case 'style': res = await aiApi.style(text, selectedStyle.toLowerCase()); break
        case 'translate': res = await aiApi.translate(text, selectedLang, storyId); break
      }
      setResult(res?.data || null)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'AI transformation failed')
    } finally {
      setLoading(false)
    }
  }

  const selText = getSelectedText()
  const selWordCount = selText.trim() ? selText.trim().split(/\s+/).length : 0

  const runLabel = (() => {
    const actionMap: Record<TabId, string> = {
      refine: 'Refine',
      tone: `Apply ${selectedTone} Tone`,
      emotion: `Apply ${selectedEmotion}`,
      age: `Adapt for ${selectedAge === 'ya' ? 'YA' : selectedAge.charAt(0).toUpperCase() + selectedAge.slice(1)}`,
      style: `Apply ${selectedStyle} Style`,
      translate: `Translate to ${selectedLang}`,
    }
    return actionMap[activeTab]
  })()

  return (
    <div className="flex flex-col h-full">
      {/* Header with scope indicator */}
      <div className="px-4 py-3 border-b border-[#1f2440]">
        <div className="flex items-center gap-2 mb-2">
          <Wand2 className="w-4 h-4 text-amber-500" />
          <span className="text-xs font-medium text-[#9da3c8] uppercase tracking-wider">AI Tools</span>
        </div>
        {selText.trim() ? (
          <div className="flex items-center gap-1.5 px-2.5 py-1.5 bg-amber-500/10 border border-amber-500/20 rounded-lg">
            <div className="w-1.5 h-1.5 rounded-full bg-amber-500 flex-shrink-0" />
            <span className="text-xs text-amber-400 truncate min-w-0">
              {selWordCount} word{selWordCount !== 1 ? 's' : ''} selected — AI will work on this
            </span>
          </div>
        ) : (
          <div className="flex items-center gap-1.5 px-2.5 py-1.5 bg-[#1a1e36] rounded-lg">
            <div className="w-1.5 h-1.5 rounded-full bg-[#5c6391] flex-shrink-0" />
            <span className="text-xs text-[#5c6391]">No selection — using full chapter</span>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-2 border-b border-[#1f2440] flex-wrap">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => { setActiveTab(tab.id); setResult(null) }}
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs transition-all ${
              activeTab === tab.id
                ? 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
                : 'text-[#5c6391] hover:text-[#9da3c8] hover:bg-[#1f2440]'
            }`}
          >
            <tab.icon className="w-3 h-3" />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="flex-1 overflow-y-auto p-4">

        {activeTab === 'refine' && (
          <div className="space-y-3">
            <p className="text-xs text-[#5c6391]">Fix grammar, elevate prose, or polish dialogue — pick the mode that fits.</p>
            <div className="grid grid-cols-2 gap-2">
              {[
                { id: 'standard', label: 'Standard', desc: 'Grammar + clarity' },
                { id: 'literary', label: 'Literary', desc: 'Elevated prose' },
                { id: 'grammar', label: 'Grammar', desc: 'Errors only' },
                { id: 'dialogue', label: 'Dialogue', desc: 'Speech patterns' },
              ].map((m) => (
                <button
                  key={m.id}
                  onClick={() => setRefineMode(m.id)}
                  className={`p-2.5 rounded-xl border text-left transition-all ${
                    refineMode === m.id
                      ? 'border-amber-500/50 bg-amber-500/10'
                      : 'border-[#2e3454] hover:border-[#3d4466]'
                  }`}
                >
                  <div className={`text-xs font-medium ${refineMode === m.id ? 'text-amber-400' : 'text-[#e8eaf6]'}`}>{m.label}</div>
                  <div className="text-xs text-[#5c6391] mt-0.5">{m.desc}</div>
                </button>
              ))}
            </div>
          </div>
        )}

        {activeTab === 'tone' && (
          <div className="space-y-2">
            <p className="text-xs text-[#5c6391] mb-3">Pick a tone and the AI rewrites your prose to match.</p>
            {TONES.map((tone) => (
              <button
                key={tone.id}
                onClick={() => setSelectedTone(tone.id)}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl border text-left transition-all ${
                  selectedTone === tone.id
                    ? 'border-amber-500/50 bg-amber-500/10 text-amber-400'
                    : 'border-[#1f2440] text-[#9da3c8] hover:border-[#2e3454] hover:bg-[#1a1e36]'
                }`}
              >
                <span className="text-base leading-none">{tone.emoji}</span>
                <span className="text-sm">{tone.id}</span>
              </button>
            ))}
          </div>
        )}

        {activeTab === 'emotion' && (
          <div className="space-y-4">
            <p className="text-xs text-[#5c6391]">Inject specific emotional depth into your prose.</p>
            <div>
              <label className="text-xs text-[#5c6391] mb-2 block">Emotion</label>
              <div className="grid grid-cols-2 gap-1.5">
                {EMOTIONS.map((em) => (
                  <button
                    key={em.id}
                    onClick={() => setSelectedEmotion(em.id)}
                    className={`py-2.5 px-3 rounded-xl border text-xs flex items-center gap-2 transition-all ${
                      selectedEmotion === em.id
                        ? 'border-amber-500/50 bg-amber-500/10 text-amber-400'
                        : 'border-[#1f2440] text-[#9da3c8] hover:border-[#2e3454]'
                    }`}
                  >
                    <span>{em.emoji}</span>
                    {em.id}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="text-xs text-[#5c6391] mb-2 block">Intensity</label>
              <div className="grid grid-cols-3 gap-2">
                {(['low', 'medium', 'high'] as const).map((i) => (
                  <button
                    key={i}
                    onClick={() => setIntensity(i)}
                    className={`py-2 rounded-xl border text-xs capitalize transition-all ${
                      intensity === i
                        ? 'border-amber-500/50 bg-amber-500/10 text-amber-400'
                        : 'border-[#1f2440] text-[#9da3c8] hover:border-[#2e3454]'
                    }`}
                  >
                    {i}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'age' && (
          <div className="space-y-2">
            <p className="text-xs text-[#5c6391] mb-3">Adapt your prose for a specific reader age group.</p>
            {[
              { id: 'children', label: 'Children', age: '5–10', desc: 'Simple words, short sentences' },
              { id: 'ya', label: 'Young Adult', age: '10–18', desc: 'Age-appropriate complexity' },
              { id: 'adult', label: 'Adult', age: '18+', desc: 'Full literary complexity' },
            ].map((a) => (
              <button
                key={a.id}
                onClick={() => setSelectedAge(a.id)}
                className={`w-full p-3.5 rounded-xl border text-left transition-all ${
                  selectedAge === a.id
                    ? 'border-amber-500/50 bg-amber-500/10'
                    : 'border-[#1f2440] hover:border-[#2e3454] hover:bg-[#1a1e36]'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className={`text-sm font-medium ${selectedAge === a.id ? 'text-amber-400' : 'text-[#e8eaf6]'}`}>{a.label}</span>
                  <span className="text-xs text-[#3d4466]">{a.age}</span>
                </div>
                <div className="text-xs text-[#5c6391] mt-0.5">{a.desc}</div>
              </button>
            ))}
          </div>
        )}

        {activeTab === 'style' && (
          <div className="space-y-1.5">
            <p className="text-xs text-[#5c6391] mb-3">Rewrite in a genre-inspired literary style.</p>
            {STYLES.map((s) => (
              <button
                key={s.id}
                onClick={() => setSelectedStyle(s.id)}
                className={`w-full flex items-center justify-between px-3 py-2.5 rounded-xl border text-left transition-all ${
                  selectedStyle === s.id
                    ? 'border-amber-500/50 bg-amber-500/10 text-amber-400'
                    : 'border-[#1f2440] text-[#9da3c8] hover:border-[#2e3454] hover:bg-[#1a1e36]'
                }`}
              >
                <span className="text-sm font-medium">{s.id}</span>
                <span className={`text-xs ${selectedStyle === s.id ? 'text-amber-400/70' : 'text-[#3d4466]'}`}>{s.desc}</span>
              </button>
            ))}
          </div>
        )}

        {activeTab === 'translate' && (
          <div className="space-y-1.5">
            <p className="text-xs text-[#5c6391] mb-3">Literary-quality translation preserving your narrative voice.</p>
            <div className="flex flex-col gap-1 max-h-72 overflow-y-auto pr-1">
              {LANGUAGES.map((lang) => (
                <button
                  key={lang}
                  onClick={() => setSelectedLang(lang)}
                  className={`px-3 py-2.5 rounded-xl border text-sm text-left transition-all ${
                    selectedLang === lang
                      ? 'border-amber-500/50 bg-amber-500/10 text-amber-400'
                      : 'border-[#1f2440] text-[#9da3c8] hover:border-[#2e3454] hover:bg-[#1a1e36]'
                  }`}
                >
                  {lang}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Run button */}
        <button
          onClick={run}
          disabled={loading}
          className="w-full mt-5 bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-black font-semibold py-3 rounded-xl text-sm transition-colors flex items-center justify-center gap-2"
        >
          {loading ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Processing...
            </>
          ) : (
            <>
              <Wand2 className="w-4 h-4" />
              {runLabel}
            </>
          )}
        </button>

        {result && (
          <ResultPanel
            result={result}
            hasSelection={hadSelection}
            onClose={() => setResult(null)}
            onInsert={insertText}
          />
        )}
      </div>
    </div>
  )
}
