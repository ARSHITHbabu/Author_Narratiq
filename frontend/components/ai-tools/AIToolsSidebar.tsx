'use client'

import { useState } from 'react'
import {
  Wand2, Palette, Heart, Users, Type, Globe,
  Copy, Check, Loader2, X, ArrowDownToLine,
  Play, List,
} from 'lucide-react'
import { aiApi, continuationApi, outlineApi } from '@/lib/api'
import { TransformResponse, ContinuationSuggestion, OutlineBeat } from '@/lib/types'
import { toast } from 'sonner'
// Shared transform option config — single source of truth (also powers the
// Selection Toolbar). No duplicated option lists across components.
import { TONES, EMOTIONS, STYLES, LANGUAGES, REFINE_MODES, AUDIENCES } from '@/lib/transforms'

interface Props {
  storyId: string
  chapterId: string
  getSelectedText: () => string
  getFullText: () => string
  insertText?: (text: string) => void
}

type TabId = 'refine' | 'tone' | 'emotion' | 'age' | 'style' | 'translate' | 'continue' | 'outline'

const TABS = [
  { id: 'refine'    as TabId, label: 'Refine',    icon: Wand2    },
  { id: 'tone'      as TabId, label: 'Tone',      icon: Palette  },
  { id: 'emotion'   as TabId, label: 'Emotion',   icon: Heart    },
  { id: 'age'       as TabId, label: 'Audience',  icon: Users    },
  { id: 'style'     as TabId, label: 'Style',     icon: Type     },
  { id: 'translate' as TabId, label: 'Translate', icon: Globe    },
  { id: 'continue'  as TabId, label: 'Continue',  icon: Play     },
  { id: 'outline'   as TabId, label: 'Outline',   icon: List     },
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

  // Continue tab
  const [continuations, setContinuations] = useState<ContinuationSuggestion[]>([])
  const [contLoading, setContLoading] = useState(false)
  const [contLength, setContLength] = useState<'short' | 'medium' | 'long'>('medium')

  // Outline tab
  const [chapterGoal, setChapterGoal] = useState('')
  const [sceneCount, setSceneCount] = useState(4)
  const [beats, setBeats] = useState<OutlineBeat[]>([])
  const [outlineLoading, setOutlineLoading] = useState(false)

  const generateContinuations = async () => {
    const tail = getFullText().split(/\s+/).slice(-300).join(' ')
    if (!tail.trim()) return toast.error('Write some text in the editor first')
    setContLoading(true)
    setContinuations([])
    try {
      const res = await continuationApi.suggest(storyId, chapterId, tail, contLength)
      setContinuations(res.data.suggestions ?? [])
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Failed to generate continuations')
    } finally {
      setContLoading(false)
    }
  }

  const generateOutline = async () => {
    if (chapterGoal.trim().split(/\s+/).length < 3) {
      return toast.error('Chapter goal must be at least 3 words')
    }
    setOutlineLoading(true)
    setBeats([])
    try {
      const res = await outlineApi.generate(storyId, chapterId, chapterGoal, sceneCount)
      setBeats(res.data.beats ?? [])
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Failed to generate outline')
    } finally {
      setOutlineLoading(false)
    }
  }

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
      refine:    'Refine',
      tone:      `Apply ${selectedTone} Tone`,
      emotion:   `Apply ${selectedEmotion}`,
      age:       `Adapt for ${selectedAge === 'ya' ? 'YA' : selectedAge.charAt(0).toUpperCase() + selectedAge.slice(1)}`,
      style:     `Apply ${selectedStyle} Style`,
      translate: `Translate to ${selectedLang}`,
      continue:  'Generate Continuations',
      outline:   'Generate Outline',
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
              {REFINE_MODES.map((m) => (
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
            {AUDIENCES.map((a) => (
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

        {/* ── Continue Tab ─────────────────────────────────────────────────── */}
        {activeTab === 'continue' && (
          <div className="space-y-3">
            <p className="text-xs text-[#5c6391]">Generate 3 possible continuations based on your chapter's tail text and story context.</p>
            <div>
              <label className="text-[10px] text-[#5c6391] block mb-1.5">Length</label>
              <div className="grid grid-cols-3 gap-1.5">
                {(['short', 'medium', 'long'] as const).map(l => (
                  <button
                    key={l}
                    onClick={() => setContLength(l)}
                    className={`py-1.5 rounded-lg border text-xs capitalize transition-all ${
                      contLength === l
                        ? 'border-amber-500/50 bg-amber-500/10 text-amber-400'
                        : 'border-[#2e3454] text-[#9da3c8] hover:border-[#3d4466]'
                    }`}
                  >
                    {l}
                  </button>
                ))}
              </div>
            </div>
            <button
              onClick={generateContinuations}
              disabled={contLoading}
              className="w-full bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-black font-semibold py-2.5 rounded-xl text-sm transition-colors flex items-center justify-center gap-2"
            >
              {contLoading ? <><Loader2 className="w-4 h-4 animate-spin" />Generating…</> : <><Play className="w-4 h-4" />Generate Continuations</>}
            </button>
            {continuations.map((c, i) => (
              <div key={i} className="bg-[#0d0f1a] border border-[#1f2440] rounded-xl p-3">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-[10px] font-medium text-amber-400">Option {i + 1} · {c.direction}</span>
                  <button
                    onClick={() => { insertText?.(c.text); toast.success('Inserted at cursor') }}
                    className="text-[10px] text-[#5c6391] hover:text-amber-400 flex items-center gap-1"
                  >
                    <ArrowDownToLine className="w-3 h-3" />Insert
                  </button>
                </div>
                <p className="text-xs text-[#9da3c8] leading-relaxed line-clamp-5 font-serif">{c.text}</p>
                {c.rationale && <p className="text-[10px] text-[#5c6391] mt-1.5 italic">{c.rationale}</p>}
              </div>
            ))}
          </div>
        )}

        {/* ── Outline Tab ──────────────────────────────────────────────────── */}
        {activeTab === 'outline' && (
          <div className="space-y-3">
            <p className="text-xs text-[#5c6391]">Generate a scene-by-scene outline for this chapter based on your story context.</p>
            <div>
              <label className="text-[10px] text-[#5c6391] block mb-1.5">Chapter goal (what must happen)</label>
              <textarea
                value={chapterGoal}
                onChange={e => setChapterGoal(e.target.value)}
                rows={3}
                placeholder="e.g. The protagonist discovers the forged letter and confronts her mentor"
                className="w-full bg-[#0d0f1a] border border-[#2e3454] rounded-lg px-3 py-2 text-xs text-[#e8eaf6] focus:border-amber-500/50 outline-none resize-none"
              />
            </div>
            <div>
              <label className="text-[10px] text-[#5c6391] block mb-1.5">Number of scenes: {sceneCount}</label>
              <input
                type="range" min={2} max={8} value={sceneCount}
                onChange={e => setSceneCount(Number(e.target.value))}
                className="w-full accent-amber-500"
              />
              <div className="flex justify-between text-[10px] text-[#3d4466] mt-0.5">
                <span>2</span><span>8</span>
              </div>
            </div>
            <button
              onClick={generateOutline}
              disabled={outlineLoading}
              className="w-full bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-black font-semibold py-2.5 rounded-xl text-sm transition-colors flex items-center justify-center gap-2"
            >
              {outlineLoading ? <><Loader2 className="w-4 h-4 animate-spin" />Generating…</> : <><List className="w-4 h-4" />Generate Outline</>}
            </button>
            {beats.map((beat, i) => (
              <div key={i} className="bg-[#0d0f1a] border border-[#1f2440] rounded-xl p-3">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-[10px] font-medium text-amber-400">Scene {beat.scene_number}</span>
                  {beat.pacing_note && <span className="text-[10px] text-[#5c6391]">{beat.pacing_note}</span>}
                </div>
                <p className="text-xs text-[#c8cce8] font-medium mb-1">{beat.beat_description}</p>
                {beat.location && <p className="text-[10px] text-[#5c6391] mt-0.5">@ {beat.location}</p>}
                {beat.characters_present?.length > 0 && (
                  <p className="text-[10px] text-[#5c6391] mt-0.5">{beat.characters_present.join(', ')}</p>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Run button — only for transform tabs */}
        {!(['continue', 'outline'] as TabId[]).includes(activeTab) && (
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
        )}

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
