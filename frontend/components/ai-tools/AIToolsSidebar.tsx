'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Wand2, Palette, Heart, Users, Type, Globe, BookOpen,
  Copy, Check, Loader2, X, ArrowDownToLine,
  Play, List, Sparkles, Lock, Unlock, Pin as PinIcon,
} from 'lucide-react'
import { aiApi, continuationApi, outlineApi } from '@/lib/api'
import { TransformResponse, ContinuationSuggestion, OutlineBeat, GenreProfile } from '@/lib/types'
import { toast } from 'sonner'
// Shared transform option config — single source of truth (also powers the
// Selection Toolbar). No duplicated option lists across components.
import { TONES, EMOTIONS, STYLES, LANGUAGES, REFINE_MODES, AUDIENCES, AUTHOR_STYLES, STRENGTH_LEVELS, splitSentences, type StrengthLevel } from '@/lib/transforms'
import { deriveToolDefaults, NEUTRAL_DEFAULTS, hasGenreProfile } from '@/lib/genreDefaults'
import { P3_ENABLED, buildControls } from '@/lib/generationControls'
import { useGenerationStore } from '@/lib/generationStore'
import GenerationWarnings, { applyNameFixes } from '@/components/generation/GenerationWarnings'
import PinActions, { type PinSource } from '@/components/generation/PinActions'
import PreservationRulesPopover from '@/components/generation/PreservationRulesPopover'
import VersionsPanel from '@/components/generation/VersionsPanel'
import { useStoryContext } from '@/components/studio/StoryContextEngine'

interface Props {
  storyId: string
  chapterId: string
  getSelectedText: () => string
  getFullText: () => string
  insertText?: (text: string) => void
  // Genre profile from Story Intake — drives genre-aware default tool selections.
  genreProfile?: Partial<GenreProfile> | null
  // The workspace's live selection, when the host tracks one (the Write workspace
  // does). `getSelectedText()` is a pull — it reads the editor at call time and this
  // component does not re-render when the selection changes, so the scope banner
  // could say "no selection" while a transform still rewrote the selected words.
  // When this prop is supplied it is the single truth for BOTH the banner and the
  // transform, so what the author is told and what the AI receives cannot diverge.
  // Omit it and the component behaves exactly as before.
  liveSelection?: { text: string; from?: number; to?: number } | null
}

type TabId = 'refine' | 'tone' | 'emotion' | 'age' | 'style' | 'author' | 'translate' | 'continue' | 'outline' | 'versions'

// Stage 5 (tasks 5.4/5.6) — tabs whose endpoint accepts strength + locked_ranges.
// Same set as LOCKABLE_GROUPS in lib/transforms.ts, in this component's tab ids.
const LOCKABLE_TABS: TabId[] = ['tone', 'age', 'style']
// Phase 3 — tabs whose endpoint accepts `controls` (lib/generationControls CONTROLLABLE_GROUPS).
const CONTROLLABLE_TABS: TabId[] = ['tone', 'emotion', 'age', 'style']
const TAB_TOOL: Partial<Record<TabId, string>> = { tone: 'tone', emotion: 'emotion', age: 'age_adapt', style: 'style' }

const TABS = [
  { id: 'refine'    as TabId, label: 'Refine',    icon: Wand2    },
  { id: 'tone'      as TabId, label: 'Tone',      icon: Palette  },
  { id: 'emotion'   as TabId, label: 'Emotion',   icon: Heart    },
  { id: 'age'       as TabId, label: 'Audience',  icon: Users    },
  { id: 'style'     as TabId, label: 'Style',     icon: Type     },
  { id: 'author'    as TabId, label: 'Author',    icon: BookOpen },
  { id: 'translate' as TabId, label: 'Translate', icon: Globe    },
  { id: 'continue'  as TabId, label: 'Continue',  icon: Play     },
  { id: 'outline'   as TabId, label: 'Outline',   icon: List     },
  ...(P3_ENABLED ? [{ id: 'versions' as TabId, label: 'Versions', icon: PinIcon }] : []),
]

function ResultPanel({
  result,
  hasSelection,
  onClose,
  onInsert,
  pinSource,
  onAutofix,
}: {
  result: TransformResponse
  hasSelection: boolean
  onClose: () => void
  onInsert?: (text: string) => void
  pinSource?: PinSource | null
  onAutofix?: (fixes: { replace: string; with: string }[]) => void
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

      {(result.warnings?.length ?? 0) > 0 && (
        <div className="mx-3 mb-2"><GenerationWarnings warnings={result.warnings!} onAutofix={onAutofix} /></div>
      )}
      {!(result.warnings?.length) && (result.preservation_violations?.length ?? 0) > 0 && (
        <p className="mx-3 mb-2 text-[11px] text-red-300 bg-red-500/10 border border-red-500/30 rounded px-2 py-1.5">
          Could not confirm these character names were preserved: {result.preservation_violations!.join(', ')}.
        </p>
      )}
      {pinSource && <div className="mx-3 mb-2"><PinActions source={pinSource} /></div>}
      {result.strength_violation && (
        <p data-testid="sidebar-strength-warning" className="mx-3 mb-2 text-[11px] text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded px-2 py-1.5">
          This rewrite changed more than the selected strength usually allows — review before applying.
        </p>
      )}

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

export default function AIToolsSidebar({ storyId, chapterId, getSelectedText, getFullText, insertText, genreProfile, liveSelection }: Props) {
  const [activeTab, setActiveTab] = useState<TabId>('refine')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<TransformResponse | null>(null)
  const [pinSource, setPinSource] = useState<PinSource | null>(null)
  const gen = useGenerationStore()
  const { editor } = useStoryContext()
  useEffect(() => { gen.setStory(storyId) }, [storyId]) // eslint-disable-line react-hooks/exhaustive-deps

  // Genre-aware defaults: start from the story's detected genre profile so the
  // tools open on sensible, genre-matched selections. With no profile these are
  // truly neutral (NOT Horror/Gothic).
  const profilePresent = hasGenreProfile(genreProfile)
  const defaults = useMemo(() => deriveToolDefaults(genreProfile), [genreProfile])

  const [selectedTone, setSelectedTone] = useState(NEUTRAL_DEFAULTS.tone)
  const [selectedEmotion, setSelectedEmotion] = useState(NEUTRAL_DEFAULTS.emotion)
  const [intensity, setIntensity] = useState('medium')
  const [selectedAge, setSelectedAge] = useState(NEUTRAL_DEFAULTS.age)
  const [selectedStyle, setSelectedStyle] = useState(NEUTRAL_DEFAULTS.style)
  const [selectedAuthor, setSelectedAuthor] = useState(AUTHOR_STYLES[0].id)
  const [selectedLang, setSelectedLang] = useState('French')
  const [refineMode, setRefineMode] = useState('standard')
  const [hadSelection, setHadSelection] = useState(false)
  // Stage 5 — strength (5.6) and sentence locks (5.4) for LOCKABLE_TABS. Lock
  // indices point into splitSentences(selection text) and are reset whenever the
  // selected text changes, so they can never refer to different prose.
  const [strength, setStrength] = useState<StrengthLevel>('light')
  const [lockedIdx, setLockedIdx] = useState<Set<number>>(new Set())

  // Apply genre-derived defaults once the profile resolves — but never clobber a
  // choice the user has already made this session (tracked per field).
  const touched = useRef({ tone: false, emotion: false, style: false, age: false })
  useEffect(() => {
    if (!profilePresent) return
    if (!touched.current.tone)    setSelectedTone(defaults.tone)
    if (!touched.current.emotion) setSelectedEmotion(defaults.emotion)
    if (!touched.current.style)   setSelectedStyle(defaults.style)
    if (!touched.current.age)     setSelectedAge(defaults.age)
  }, [profilePresent, defaults])

  const pickTone    = (v: string) => { touched.current.tone = true;    setSelectedTone(v) }
  const pickEmotion = (v: string) => { touched.current.emotion = true; setSelectedEmotion(v) }
  const pickStyle   = (v: string) => { touched.current.style = true;   setSelectedStyle(v) }
  const pickAge     = (v: string) => { touched.current.age = true;     setSelectedAge(v) }

  const genreLabel = genreProfile?.genre?.trim() || null
  // Genre-recommended option id per tab (only when a profile exists).
  const rec = profilePresent
    ? { tone: defaults.tone, emotion: defaults.emotion, style: defaults.style, age: defaults.age }
    : null
  const RecBadge = () => (
    <span className="ml-1 text-[9px] px-1 py-px rounded bg-amber-500/20 text-amber-300 border border-amber-500/30">★ genre pick</span>
  )

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
    // Must match the backend's minimum (writing_tools.py) — a lower threshold
    // here just produces a round trip that comes back as a 400.
    if (chapterGoal.trim().split(/\s+/).length < 10) {
      return toast.error('Chapter goal must be at least 10 words — describe what should happen')
    }
    setOutlineLoading(true)
    setBeats([])
    try {
      const res = await outlineApi.generate(storyId, chapterId, chapterGoal, sceneCount)
      // Backend field is `outline` (schemas.py OutlineResponse), not `beats`.
      setBeats(res.data.outline ?? [])
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Failed to generate outline')
    } finally {
      setOutlineLoading(false)
    }
  }

  // The one place this component reads the selection. When the host tracks a live
  // selection we use it; otherwise we pull from the editor as before. Everything —
  // the scope banner, the full-chapter fallback and the text sent to the model —
  // goes through here, so the author is never told one scope and given another.
  const selectionProvided = liveSelection !== undefined
  const readSelection = () => (selectionProvided ? (liveSelection?.text ?? '') : getSelectedText())

  const getText = () => {
    const sel = readSelection()
    return sel.trim() || getFullText().slice(0, 2000)
  }

  const run = async () => {
    const text = getText()
    if (!text) return toast.error('Write some text in the editor first')
    const sel = readSelection()
    setHadSelection(!!sel.trim())
    // Locks only apply to a real selection: offsets are into THIS request's text,
    // which is the selection itself (getText() returns it unmodified).
    const spans = sel.trim() ? splitSentences(sel) : []
    const lock = {
      strength,
      lockedRanges: Array.from(lockedIdx).filter((i) => i < spans.length).map((i) => ({ start: spans[i].start, end: spans[i].end })),
    }
    setLoading(true)
    setResult(null)
    setPinSource(null)
    // Phase 3 — controls only for the tabs whose endpoint accepts them. Same
    // rules as the floating toolbar: selected context/avoid pins, this
    // session's earlier attempts as the avoid-set, surrounding text for voice.
    const tool = TAB_TOOL[activeTab]
    const useP3 = P3_ENABLED && CONTROLLABLE_TABS.includes(activeTab) && !!tool
    const range = liveSelection && typeof liveSelection.from === 'number' && typeof liveSelection.to === 'number' && sel.trim()
      ? { from: liveSelection.from, to: liveSelection.to! } : null
    const contextPinIds = useP3 ? [...gen.contextPinIds] : []
    const p3 = useP3 ? { chapterId, controls: buildControls({
      contextPinIds, avoidPinIds: gen.avoidPinIds, avoidTexts: gen.recentTexts(chapterId, tool!),
      localContext: range ? editor?.getSurroundingText?.(range.from, range.to) : undefined,
    }) } : undefined
    const toolParams: Record<string, unknown> =
      activeTab === 'tone' ? { tone: selectedTone.toLowerCase() } : activeTab === 'emotion' ? { emotion: selectedEmotion.toLowerCase(), intensity }
      : activeTab === 'age' ? { target_age: selectedAge } : activeTab === 'style' ? { style: selectedStyle.toLowerCase() } : {}
    try {
      let res
      switch (activeTab) {
        case 'refine': res = await aiApi.refine(text, refineMode, storyId, chapterId); break
        case 'tone': res = await aiApi.tone(text, selectedTone.toLowerCase(), storyId, lock, p3); break
        case 'emotion': res = await aiApi.emotion(text, selectedEmotion.toLowerCase(), intensity, storyId, p3); break
        case 'age': res = await aiApi.ageAdapt(text, selectedAge, storyId, lock, p3); break
        case 'style': res = await aiApi.style(text, selectedStyle.toLowerCase(), storyId, lock, p3); break
        case 'author': res = await aiApi.authorStyle(text, selectedAuthor, storyId, chapterId); break
        case 'translate': res = await aiApi.translate(text, selectedLang, storyId); break
      }
      const data: TransformResponse | null = res?.data || null
      if (data?.failed) {
        // Lock contract failure: the server returned the original text. Say so;
        // never present the unchanged text as a rewrite. Locks stay as they are.
        toast.error(data.reason || 'Those sentences could not be rewritten safely with the current locks. Nothing was changed.')
        return
      }
      setResult(data)
      if (data && useP3 && !data.no_change) {
        const sessionId = `${Date.now()}`
        const priorAttempts = gen.recentTexts(chapterId, tool!).length
        gen.record({ id: sessionId, text: data.transformed, tool: tool!, toolParams, chapterId, sourceText: text,
                     sourceFrom: range?.from ?? null, sourceTo: range?.to ?? null, createdAt: Date.now(), contextPinIds })
        setPinSource({ text: data.transformed, tool: tool!, toolParams, chapterId, sourceText: text,
                       sourceFrom: range?.from ?? null, sourceTo: range?.to ?? null, derivedFromPinIds: contextPinIds, sessionId })
        if (priorAttempts >= 1 && !gen.firstRunHintShown) {
          gen.markHintShown()
          toast.info('Only pinned versions are kept. Everything else disappears when you refresh.')
        }
      }
    } catch (err: any) {
      const d = err?.response?.data?.detail
      toast.error(typeof d === 'string' ? d : 'The AI could not complete this right now. Your text is unchanged.')
    } finally {
      setLoading(false)
    }
  }

  const selText = readSelection()
  const selWordCount = selText.trim() ? selText.trim().split(/\s+/).length : 0
  const sentenceSpans = useMemo(() => (selText.trim() ? splitSentences(selText) : []), [selText])
  useEffect(() => { setLockedIdx(new Set()) }, [selText])
  const toggleLock = (i: number) => setLockedIdx((prev) => {
    const next = new Set(prev)
    if (next.has(i)) next.delete(i); else next.add(i)
    return next
  })

  const runLabel = (() => {
    const actionMap: Record<TabId, string> = {
      refine:    'Refine',
      tone:      `Apply ${selectedTone} Tone`,
      emotion:   `Apply ${selectedEmotion}`,
      age:       `Adapt for ${selectedAge === 'ya' ? 'YA' : selectedAge.charAt(0).toUpperCase() + selectedAge.slice(1)}`,
      style:     `Apply ${selectedStyle} Style`,
      author:    `Rewrite in ${AUTHOR_STYLES.find(a => a.id === selectedAuthor)?.label ?? 'Author'} Style`,
      translate: `Translate to ${selectedLang}`,
      continue:  'Generate Continuations',
      outline:   'Generate Outline',
      versions:  '',
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
          {genreLabel ? (
            <span
              title="AI tools are tuned to this story's genre profile"
              className="ml-auto flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/30 text-[10px] text-amber-400"
            >
              <Sparkles className="w-2.5 h-2.5" />
              {genreLabel}
            </span>
          ) : (
            <span
              title="No genre profile — defaults are neutral. Complete Story Intake to make tools genre-aware."
              className="ml-auto px-2 py-0.5 rounded-full bg-[#1a1e36] border border-[#2e3454] text-[10px] text-[#5c6391]"
            >
              No genre profile
            </span>
          )}
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

        {P3_ENABLED && CONTROLLABLE_TABS.includes(activeTab) && (
          <div className="mb-4 space-y-2">
            <PreservationRulesPopover storyId={storyId} />
            {(gen.contextPinIds.length > 0 || gen.avoidPinIds.length > 0) && (
              <p data-testid="sidebar-context-bar" className="text-[11px] text-sky-200 bg-sky-500/10 border border-sky-500/30 rounded-lg px-2.5 py-1.5">
                {gen.contextPinIds.length > 0 && `Using ${gen.contextPinIds.length} pinned version${gen.contextPinIds.length === 1 ? '' : 's'} as context. `}
                {gen.avoidPinIds.length > 0 && `Avoiding ideas like ${gen.avoidPinIds.length}. `}
                <button className="underline" onClick={() => setActiveTab('versions')}>Change in Versions</button>
              </p>
            )}
          </div>
        )}

        {activeTab === 'versions' && <VersionsPanel selectedText={readSelection()} />}

        {LOCKABLE_TABS.includes(activeTab) && (
          <div data-testid="sidebar-lock-strength" className="mb-4 space-y-3 rounded-xl border border-[#1f2440] p-3">
            <div className="flex items-center gap-1">
              <span className="text-[10px] text-[#5c6391] mr-1">Strength</span>
              {STRENGTH_LEVELS.map((s) => (
                <button key={s} type="button" onClick={() => setStrength(s)}
                  aria-pressed={strength === s}
                  title={
                    s === 'light' ? 'Word choice and connectives only' :
                    s === 'moderate' ? 'Sentence-level rewriting allowed' :
                    'Full rewrite within preservation limits'
                  }
                  className={`text-[11px] px-2 py-0.5 rounded ${strength === s ? 'bg-amber-500/20 text-amber-300' : 'text-[#9da3c8] hover:bg-[#1f2440]'}`}>{s}</button>
              ))}
            </div>
            {sentenceSpans.length > 1 ? (
              <div>
                <div className="flex items-center gap-1 mb-1">
                  <Lock className="w-2.5 h-2.5 text-[#5c6391]" />
                  <span className="text-[10px] text-[#5c6391]">
                    Lock sentences to keep unchanged{lockedIdx.size > 0 ? ` (${lockedIdx.size})` : ''}
                  </span>
                </div>
                <div className="max-h-40 overflow-y-auto space-y-0.5">
                  {sentenceSpans.map((s, i) => {
                    const locked = lockedIdx.has(i)
                    return (
                      <button key={i} type="button" onClick={() => toggleLock(i)}
                        aria-pressed={locked}
                        title={locked ? 'Locked — click to unlock' : 'Click to lock this sentence unchanged'}
                        className={`w-full flex items-start gap-1 text-left px-1.5 py-1 rounded text-[10px] leading-snug ${locked ? 'bg-amber-500/15 text-amber-200' : 'text-[#9da3c8] hover:bg-[#1f2440]'}`}>
                        {locked ? <Lock className="w-2.5 h-2.5 mt-0.5 flex-shrink-0" /> : <Unlock className="w-2.5 h-2.5 mt-0.5 flex-shrink-0 opacity-40" />}
                        <span className="line-clamp-2">{s.text}</span>
                      </button>
                    )
                  })}
                </div>
              </div>
            ) : (
              <p className="text-[10px] text-[#5c6391]">Select two or more sentences in the editor to lock individual sentences.</p>
            )}
          </div>
        )}

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
                onClick={() => pickTone(tone.id)}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl border text-left transition-all ${
                  selectedTone === tone.id
                    ? 'border-amber-500/50 bg-amber-500/10 text-amber-400'
                    : 'border-[#1f2440] text-[#9da3c8] hover:border-[#2e3454] hover:bg-[#1a1e36]'
                }`}
              >
                <span className="text-base leading-none">{tone.emoji}</span>
                <span className="text-sm">{tone.id}</span>
                {rec && tone.id.toLowerCase() === rec.tone.toLowerCase() && <RecBadge />}
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
                    onClick={() => pickEmotion(em.id)}
                    className={`py-2.5 px-3 rounded-xl border text-xs flex items-center gap-2 transition-all ${
                      selectedEmotion === em.id
                        ? 'border-amber-500/50 bg-amber-500/10 text-amber-400'
                        : 'border-[#1f2440] text-[#9da3c8] hover:border-[#2e3454]'
                    }`}
                  >
                    <span>{em.emoji}</span>
                    {em.id}
                    {rec && em.id.toLowerCase() === rec.emotion.toLowerCase() && <RecBadge />}
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
                onClick={() => pickAge(a.id)}
                className={`w-full p-3.5 rounded-xl border text-left transition-all ${
                  selectedAge === a.id
                    ? 'border-amber-500/50 bg-amber-500/10'
                    : 'border-[#1f2440] hover:border-[#2e3454] hover:bg-[#1a1e36]'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className={`text-sm font-medium ${selectedAge === a.id ? 'text-amber-400' : 'text-[#e8eaf6]'}`}>
                    {a.label}
                    {rec && a.id.toLowerCase() === rec.age.toLowerCase() && <RecBadge />}
                  </span>
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
                onClick={() => pickStyle(s.id)}
                className={`w-full flex items-center justify-between px-3 py-2.5 rounded-xl border text-left transition-all ${
                  selectedStyle === s.id
                    ? 'border-amber-500/50 bg-amber-500/10 text-amber-400'
                    : 'border-[#1f2440] text-[#9da3c8] hover:border-[#2e3454] hover:bg-[#1a1e36]'
                }`}
              >
                <span className="text-sm font-medium">
                  {s.id}
                  {rec && s.id.toLowerCase() === rec.style.toLowerCase() && <RecBadge />}
                </span>
                <span className={`text-xs ${selectedStyle === s.id ? 'text-amber-400/70' : 'text-[#3d4466]'}`}>{s.desc}</span>
              </button>
            ))}
          </div>
        )}

        {activeTab === 'author' && (
          <div className="space-y-2">
            <p className="text-xs text-[#5c6391]">Rewrite in a style <span className="text-amber-400/90">inspired by</span> an author — meaning, plot and characters preserved.</p>
            <div className="flex items-start gap-1.5 px-2.5 py-1.5 rounded-lg bg-[#1a1e36] border border-[#2e3454]">
              <Sparkles className="w-3 h-3 text-amber-400 mt-0.5 flex-shrink-0" />
              <p className="text-[10px] text-[#9da3c8] leading-relaxed">
                Public-domain authors only. Modern styles use safe generic influences — never a copy.
              </p>
            </div>

            <label className="text-[10px] text-[#5c6391] block pt-1">Public-domain authors</label>
            {AUTHOR_STYLES.filter(a => a.group === 'public_domain').map((a) => (
              <button
                key={a.id}
                onClick={() => setSelectedAuthor(a.id)}
                className={`w-full flex items-center justify-between px-3 py-2.5 rounded-xl border text-left transition-all ${
                  selectedAuthor === a.id
                    ? 'border-amber-500/50 bg-amber-500/10 text-amber-400'
                    : 'border-[#1f2440] text-[#9da3c8] hover:border-[#2e3454] hover:bg-[#1a1e36]'
                }`}
              >
                <span className="text-sm font-medium">{a.label}</span>
                <span className={`text-[10px] ${selectedAuthor === a.id ? 'text-amber-400/70' : 'text-[#3d4466]'}`}>{a.desc}</span>
              </button>
            ))}

            <label className="text-[10px] text-[#5c6391] block pt-2">Generic styles (always safe)</label>
            <div className="grid grid-cols-2 gap-1.5">
              {AUTHOR_STYLES.filter(a => a.group === 'generic').map((a) => (
                <button
                  key={a.id}
                  onClick={() => setSelectedAuthor(a.id)}
                  className={`px-3 py-2 rounded-xl border text-left transition-all ${
                    selectedAuthor === a.id
                      ? 'border-amber-500/50 bg-amber-500/10 text-amber-400'
                      : 'border-[#1f2440] text-[#9da3c8] hover:border-[#2e3454] hover:bg-[#1a1e36]'
                  }`}
                >
                  <div className="text-xs font-medium">{a.label}</div>
                  <div className="text-[10px] text-[#3d4466] mt-0.5">{a.desc}</div>
                </button>
              ))}
            </div>
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
        {!(['continue', 'outline', 'versions'] as TabId[]).includes(activeTab) && (
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
            onClose={() => { setResult(null); setPinSource(null) }}
            onInsert={insertText}
            pinSource={pinSource}
            onAutofix={(fixes) => {
              setResult((r) => (r ? { ...r, transformed: applyNameFixes(r.transformed, fixes), warnings: (r.warnings ?? []).filter((w) => !w.autofix) } : r))
              setPinSource((p) => (p ? { ...p, text: applyNameFixes(p.text, fixes) } : p))
            }}
          />
        )}
      </div>
    </div>
  )
}
