'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Search, X, ChevronDown, ChevronUp, ChevronLeft, ChevronRight,
  Replace, Check, AlertTriangle, Loader2, Sparkles
} from 'lucide-react'
import { searchApi } from '@/lib/api'
import {
  ChapterSearchResult,
  ExactSearchResponse,
  ReplacePreviewItem,
  ReplaceResponse,
  SemanticResult,
  SemanticSearchResponse,
} from '@/lib/types'
import { toast } from 'sonner'

interface Props {
  storyId: string
  activeChapterId: string
  onClose: () => void
  onJumpToMatch: (
    chapterId: string,
    localIndex: number,
    query: string,
    caseSensitive: boolean,
    wholeWord: boolean,
  ) => void
  onReplaceComplete: (affectedChapterIds: string[]) => void
  onSearchStateChange?: (state: { query: string; caseSensitive: boolean; wholeWord: boolean } | null) => void
}

type Mode = 'exact' | 'semantic'

// Compute which chapter and local index a global match index maps to
function resolveGlobalIndex(
  results: ChapterSearchResult[],
  globalIndex: number,
): { chapterId: string; localIndex: number } | null {
  let cumulative = 0
  for (const r of results) {
    if (globalIndex < cumulative + r.match_count) {
      return { chapterId: r.chapter_id, localIndex: globalIndex - cumulative }
    }
    cumulative += r.match_count
  }
  return null
}

export default function SearchPanel({
  storyId,
  activeChapterId,
  onClose,
  onJumpToMatch,
  onReplaceComplete,
  onSearchStateChange,
}: Props) {
  const [mode, setMode] = useState<Mode>('exact')
  const [query, setQuery] = useState('')
  const [caseSensitive, setCaseSensitive] = useState(false)
  const [wholeWord, setWholeWord] = useState(false)
  const [scope, setScope] = useState<'all' | 'current'>('all')
  const [loading, setLoading] = useState(false)

  // Exact results
  const [exactResults, setExactResults] = useState<ChapterSearchResult[]>([])
  const [totalMatches, setTotalMatches] = useState(0)
  const [chaptersHit, setChaptersHit] = useState(0)
  const [globalIndex, setGlobalIndex] = useState(-1)

  // Semantic results
  const [semanticResults, setSemanticResults] = useState<SemanticResult[]>([])

  // Collapsed chapter groups
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())

  // Replace state
  const [showReplace, setShowReplace] = useState(false)
  const [replacement, setReplacement] = useState('')
  const [replacing, setReplacing] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const [dryRunPreview, setDryRunPreview] = useState<ReplacePreviewItem[]>([])
  const [selectedChapters, setSelectedChapters] = useState<Set<string>>(new Set())

  const queryRef = useRef<HTMLInputElement>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Focus on open
  useEffect(() => {
    queryRef.current?.focus()
  }, [])

  // Clear results when mode or scope changes
  useEffect(() => {
    setExactResults([])
    setSemanticResults([])
    setTotalMatches(0)
    setChaptersHit(0)
    setGlobalIndex(-1)
  }, [mode, scope])

  // Keep parent's activeSearchRef in sync so it can re-apply highlights on
  // chapter switches.  Notify with null when query is empty (no active search).
  useEffect(() => {
    onSearchStateChange?.(
      query.trim() && mode === 'exact'
        ? { query, caseSensitive, wholeWord }
        : null,
    )
  }, [query, caseSensitive, wholeWord, mode])

  // ── Search ─────────────────────────────────────────────────────────────────

  const runSearch = useCallback(
    async (q: string, opts?: { cs?: boolean; ww?: boolean; sc?: 'all' | 'current' }) => {
      if (!q.trim()) {
        setExactResults([])
        setSemanticResults([])
        setTotalMatches(0)
        setChaptersHit(0)
        setGlobalIndex(-1)
        return
      }
      // Allow callers to pass the new value before the state update has flushed
      const cs = opts?.cs !== undefined ? opts.cs : caseSensitive
      const ww = opts?.ww !== undefined ? opts.ww : wholeWord
      const sc = opts?.sc !== undefined ? opts.sc : scope
      setLoading(true)
      try {
        if (mode === 'exact') {
          const chIds = sc === 'current' ? [activeChapterId] : null
          const res = await searchApi.exact(storyId, q, cs, ww, chIds)
          const data: ExactSearchResponse = res.data
          setExactResults(data.results)
          setTotalMatches(data.total_matches)
          setChaptersHit(data.chapters_hit)
          setGlobalIndex(data.total_matches > 0 ? 0 : -1)
          if (data.results.length > 0 && data.results[0].match_count > 0) {
            onJumpToMatch(data.results[0].chapter_id, 0, q, cs, ww)
          }
        } else {
          const res = await searchApi.semantic(storyId, q)
          const data: SemanticSearchResponse = res.data
          setSemanticResults(data.results)
        }
      } catch (err: any) {
        toast.error(err?.response?.data?.detail || 'Search failed')
      } finally {
        setLoading(false)
      }
    },
    [mode, scope, activeChapterId, storyId, caseSensitive, wholeWord, onJumpToMatch],
  )

  const handleQueryChange = (q: string) => {
    setQuery(q)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (mode === 'semantic') {
      // Semantic: debounce longer (embedding call)
      debounceRef.current = setTimeout(() => runSearch(q), 600)
    } else {
      debounceRef.current = setTimeout(() => runSearch(q), 250)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      if (debounceRef.current) clearTimeout(debounceRef.current)
      runSearch(query)
    }
    if (e.key === 'Escape') onClose()
  }

  // ── Navigation ─────────────────────────────────────────────────────────────

  const navigate = useCallback(
    (direction: 1 | -1) => {
      if (totalMatches === 0) return
      const next = (globalIndex + direction + totalMatches) % totalMatches
      setGlobalIndex(next)
      const resolved = resolveGlobalIndex(exactResults, next)
      if (resolved) {
        onJumpToMatch(resolved.chapterId, resolved.localIndex, query, caseSensitive, wholeWord)
      }
    },
    [globalIndex, totalMatches, exactResults, query, caseSensitive, wholeWord, onJumpToMatch],
  )

  const handleResultClick = (chapterId: string, localIndex: number, absGlobal: number) => {
    setGlobalIndex(absGlobal)
    onJumpToMatch(chapterId, localIndex, query, caseSensitive, wholeWord)
  }

  // ── Replace ─────────────────────────────────────────────────────────────────

  const handleReplaceOne = async () => {
    if (!query.trim() || globalIndex < 0) return
    const resolved = resolveGlobalIndex(exactResults, globalIndex)
    if (!resolved) return
    setReplacing(true)
    try {
      await searchApi.replace(storyId, {
        query,
        replacement,
        caseSensitive,
        wholeWord,
        chapterIds: [resolved.chapterId],
        occurrenceIndex: resolved.localIndex,
        dryRun: false,
      })
      toast.success('Replaced 1 occurrence')
      onReplaceComplete([resolved.chapterId])
      await runSearch(query) // refresh results
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Replace failed')
    } finally {
      setReplacing(false)
    }
  }

  const handleReplaceAllClick = async () => {
    if (!query.trim() || totalMatches === 0) return
    setReplacing(true)
    try {
      const res = await searchApi.replace(storyId, {
        query,
        replacement,
        caseSensitive,
        wholeWord,
        chapterIds: scope === 'current' ? [activeChapterId] : null,
        dryRun: true,
      })
      const data: ReplaceResponse = res.data
      setDryRunPreview(data.preview)
      setSelectedChapters(new Set(data.preview.map(p => p.chapter_id)))
      setShowConfirm(true)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Preview failed')
    } finally {
      setReplacing(false)
    }
  }

  const handleConfirmReplace = async () => {
    setShowConfirm(false)
    setReplacing(true)
    try {
      const chIds = [...selectedChapters]
      const res = await searchApi.replace(storyId, {
        query,
        replacement,
        caseSensitive,
        wholeWord,
        chapterIds: chIds.length > 0 ? chIds : null,
        dryRun: false,
      })
      const data: ReplaceResponse = res.data
      toast.success(`Replaced ${data.replaced_count} occurrence${data.replaced_count !== 1 ? 's' : ''} in ${data.chapters_affected} chapter${data.chapters_affected !== 1 ? 's' : ''}`)
      onReplaceComplete(chIds)
      await runSearch(query)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Replace failed')
    } finally {
      setReplacing(false)
      setDryRunPreview([])
    }
  }

  const toggleChapterSelect = (id: string) => {
    setSelectedChapters(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  // ── Helpers ─────────────────────────────────────────────────────────────────

  const toggleCollapse = (id: string) =>
    setCollapsed(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n })

  // Compute absolute global index from chapter + local
  const toAbsGlobal = (results: ChapterSearchResult[], chIdx: number, localIdx: number) => {
    let base = 0
    for (let i = 0; i < chIdx; i++) base += results[i].match_count
    return base + localIdx
  }

  const optionBtn = (label: string, active: boolean, onClick: () => void) => (
    <button
      onClick={onClick}
      className={`px-2 py-0.5 rounded text-xs font-mono transition-colors ${
        active ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30' : 'text-[#5c6391] border border-[#2e3454] hover:text-[#9da3c8]'
      }`}
    >
      {label}
    </button>
  )

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div
      className="fixed top-14 right-4 z-50 w-[480px] max-h-[78vh] flex flex-col bg-[#13162a] border border-[#2e3454] rounded-2xl shadow-2xl overflow-hidden"
      onClick={e => e.stopPropagation()}
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-[#1f2440] flex-shrink-0">
        {/* Mode tabs */}
        <div className="flex gap-1 bg-[#0d0f1a] rounded-lg p-0.5">
          <button
            onClick={() => setMode('exact')}
            className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
              mode === 'exact' ? 'bg-[#1f2440] text-[#e8eaf6]' : 'text-[#5c6391] hover:text-[#9da3c8]'
            }`}
          >
            Exact
          </button>
          <button
            onClick={() => setMode('semantic')}
            className={`flex items-center gap-1 px-3 py-1 rounded-md text-xs font-medium transition-colors ${
              mode === 'semantic' ? 'bg-[#1f2440] text-[#e8eaf6]' : 'text-[#5c6391] hover:text-[#9da3c8]'
            }`}
          >
            <Sparkles className="w-3 h-3" /> Semantic
          </button>
        </div>

        <div className="flex-1" />

        <button
          onClick={onClose}
          className="p-1 rounded text-[#5c6391] hover:text-[#e8eaf6] hover:bg-[#1f2440] transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Search input */}
      <div className="px-4 py-3 border-b border-[#1f2440] flex-shrink-0 space-y-2">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[#5c6391]" />
          <input
            ref={queryRef}
            value={query}
            onChange={e => handleQueryChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              mode === 'exact'
                ? 'Search across manuscript…'
                : 'Find scenes about… (e.g. "family conflict")'
            }
            className="w-full bg-[#0d0f1a] border border-[#2e3454] rounded-lg pl-9 pr-3 py-2 text-sm text-[#e8eaf6] placeholder-[#3d4466] focus:outline-none focus:border-amber-500/50 transition-colors"
          />
          {loading && (
            <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-amber-500 animate-spin" />
          )}
        </div>

        {/* Options row (Exact mode only) */}
        {mode === 'exact' && (
          <div className="flex items-center gap-2 flex-wrap">
            {optionBtn('Aa', caseSensitive, () => {
              const next = !caseSensitive
              setCaseSensitive(next)
              if (query) runSearch(query, { cs: next })
            })}
            {optionBtn('\\b', wholeWord, () => {
              const next = !wholeWord
              setWholeWord(next)
              if (query) runSearch(query, { ww: next })
            })}
            <div className="w-px h-4 bg-[#2e3454]" />
            <button
              onClick={() => { setScope('all'); if (query) runSearch(query, { sc: 'all' }) }}
              className={`text-xs px-2 py-0.5 rounded transition-colors ${scope === 'all' ? 'text-amber-400' : 'text-[#5c6391] hover:text-[#9da3c8]'}`}
            >
              All chapters
            </button>
            <button
              onClick={() => { setScope('current'); if (query) runSearch(query, { sc: 'current' }) }}
              className={`text-xs px-2 py-0.5 rounded transition-colors ${scope === 'current' ? 'text-amber-400' : 'text-[#5c6391] hover:text-[#9da3c8]'}`}
            >
              Current chapter
            </button>
          </div>
        )}
      </div>

      {/* Results summary + navigation */}
      {mode === 'exact' && query.trim() && !loading && (
        <div className="flex items-center justify-between px-4 py-2 border-b border-[#1f2440] flex-shrink-0 bg-[#0d0f1a]">
          <span className="text-xs text-[#5c6391]">
            {totalMatches === 0
              ? 'No matches'
              : `${totalMatches} match${totalMatches !== 1 ? 'es' : ''} across ${chaptersHit} chapter${chaptersHit !== 1 ? 's' : ''}`}
          </span>
          {totalMatches > 0 && (
            <div className="flex items-center gap-1">
              <span className="text-xs text-[#5c6391] mr-1">
                {globalIndex + 1} / {totalMatches}
              </span>
              <button
                onClick={() => navigate(-1)}
                className="p-1 rounded text-[#5c6391] hover:text-[#e8eaf6] hover:bg-[#1f2440] transition-colors"
              >
                <ChevronLeft className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={() => navigate(1)}
                className="p-1 rounded text-[#5c6391] hover:text-[#e8eaf6] hover:bg-[#1f2440] transition-colors"
              >
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </div>
          )}
        </div>
      )}

      {mode === 'semantic' && !loading && semanticResults.length > 0 && (
        <div className="px-4 py-2 border-b border-[#1f2440] flex-shrink-0 bg-[#0d0f1a]">
          <span className="text-xs text-[#5c6391]">
            {semanticResults.length} passage{semanticResults.length !== 1 ? 's' : ''} found
          </span>
        </div>
      )}

      {/* Results area */}
      <div className="flex-1 overflow-y-auto">
        {/* ── Exact results ── */}
        {mode === 'exact' && exactResults.map((chRes, chIdx) => {
          const isCollapsed = collapsed.has(chRes.chapter_id)
          return (
            <div key={chRes.chapter_id} className="border-b border-[#1f2440] last:border-0">
              {/* Chapter header */}
              <button
                onClick={() => toggleCollapse(chRes.chapter_id)}
                className="w-full flex items-center gap-2 px-4 py-2.5 hover:bg-[#1a1e36] transition-colors text-left"
              >
                {isCollapsed ? <ChevronRight className="w-3.5 h-3.5 text-[#5c6391]" /> : <ChevronDown className="w-3.5 h-3.5 text-[#5c6391]" />}
                <span className="text-xs font-medium text-[#9da3c8] flex-1 truncate">
                  Ch.{chRes.chapter_number} — {chRes.chapter_title}
                </span>
                <span className="text-xs text-[#5c6391] flex-shrink-0">
                  {chRes.match_count} match{chRes.match_count !== 1 ? 'es' : ''}
                </span>
              </button>

              {/* Match list */}
              {!isCollapsed && chRes.matches.map((m, localIdx) => {
                const absGlobal = toAbsGlobal(exactResults, chIdx, localIdx)
                const isActive = absGlobal === globalIndex
                return (
                  <button
                    key={localIdx}
                    onClick={() => handleResultClick(chRes.chapter_id, localIdx, absGlobal)}
                    className={`w-full text-left px-4 py-2 text-xs transition-colors border-l-2 ${
                      isActive
                        ? 'border-amber-500 bg-amber-500/5'
                        : 'border-transparent hover:bg-[#1a1e36] hover:border-[#2e3454]'
                    }`}
                  >
                    <span className="text-[#5c6391]">{m.context_before}</span>
                    <span
                      className="font-semibold rounded px-0.5"
                      style={{
                        backgroundColor: isActive ? 'rgba(251,146,60,0.5)' : 'rgba(251,191,36,0.35)',
                        color: isActive ? 'rgb(251,146,60)' : 'rgb(251,191,36)',
                      }}
                    >
                      {m.match_text}
                    </span>
                    <span className="text-[#5c6391]">{m.context_after}</span>
                  </button>
                )
              })}
            </div>
          )
        })}

        {/* ── Semantic results ── */}
        {mode === 'semantic' && semanticResults.map((r, i) => (
          <div key={i} className="border-b border-[#1f2440] last:border-0 px-4 py-3 hover:bg-[#1a1e36] transition-colors">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs font-medium text-[#9da3c8]">
                Ch.{r.chapter_number} — {r.chapter_title}
              </span>
              <span
                className={`text-xs font-medium ${
                  r.score > 0.85 ? 'text-green-400' : r.score > 0.70 ? 'text-amber-400' : 'text-[#5c6391]'
                }`}
              >
                {Math.round(r.score * 100)}% match
              </span>
            </div>
            <p className="text-xs text-[#5c6391] leading-relaxed line-clamp-3">{r.chunk_text}</p>
          </div>
        ))}

        {/* Empty state */}
        {!loading && query.trim() && mode === 'exact' && exactResults.length === 0 && (
          <div className="flex flex-col items-center justify-center py-10 text-center px-6">
            <Search className="w-8 h-8 text-[#2e3454] mb-2" />
            <p className="text-sm text-[#5c6391]">No matches found</p>
            <p className="text-xs text-[#3d4466] mt-1">Try different keywords or disable case-sensitive / whole-word</p>
          </div>
        )}
        {!loading && query.trim() && mode === 'semantic' && semanticResults.length === 0 && (
          <div className="flex flex-col items-center justify-center py-10 text-center px-6">
            <Sparkles className="w-8 h-8 text-[#2e3454] mb-2" />
            <p className="text-sm text-[#5c6391]">No passages found</p>
            <p className="text-xs text-[#3d4466] mt-1">Make sure you have indexed chapters (sync summaries)</p>
          </div>
        )}
        {!query.trim() && (
          <div className="flex flex-col items-center justify-center py-10 text-center px-6">
            <Search className="w-8 h-8 text-[#2e3454] mb-2" />
            <p className="text-sm text-[#5c6391]">
              {mode === 'exact' ? 'Type to search across all chapters' : 'Describe what you\'re looking for'}
            </p>
            {mode === 'exact' && (
              <p className="text-xs text-[#3d4466] mt-1">Keyboard: Enter to search · ← → to navigate · Esc to close</p>
            )}
          </div>
        )}
      </div>

      {/* Replace section (Exact mode only) */}
      {mode === 'exact' && (
        <div className="border-t border-[#1f2440] flex-shrink-0">
          <button
            onClick={() => setShowReplace(v => !v)}
            className="w-full flex items-center gap-2 px-4 py-2.5 text-xs text-[#5c6391] hover:text-[#9da3c8] hover:bg-[#1a1e36] transition-colors"
          >
            <Replace className="w-3.5 h-3.5" />
            <span>Replace</span>
            {showReplace ? <ChevronUp className="w-3.5 h-3.5 ml-auto" /> : <ChevronDown className="w-3.5 h-3.5 ml-auto" />}
          </button>

          {showReplace && (
            <div className="px-4 pb-3 space-y-2 bg-[#0d0f1a]">
              <input
                value={replacement}
                onChange={e => setReplacement(e.target.value)}
                placeholder="Replace with…"
                className="w-full bg-[#13162a] border border-[#2e3454] rounded-lg px-3 py-2 text-sm text-[#e8eaf6] placeholder-[#3d4466] focus:outline-none focus:border-amber-500/50 transition-colors"
              />
              <div className="flex gap-2">
                <button
                  onClick={handleReplaceOne}
                  disabled={replacing || globalIndex < 0 || !query.trim()}
                  className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg border border-[#2e3454] text-xs text-[#9da3c8] hover:border-amber-500/30 hover:text-amber-400 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  {replacing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Replace className="w-3.5 h-3.5" />}
                  Replace one
                </button>
                <button
                  onClick={handleReplaceAllClick}
                  disabled={replacing || totalMatches === 0 || !query.trim()}
                  className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg bg-amber-500/10 border border-amber-500/20 text-xs text-amber-400 hover:bg-amber-500/20 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  {replacing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Replace className="w-3.5 h-3.5" />}
                  Replace all ({totalMatches})
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Replace All confirmation modal */}
      {showConfirm && (
        <div className="absolute inset-0 bg-[#0d0f1a]/90 backdrop-blur-sm z-10 flex flex-col p-4">
          <div className="bg-[#13162a] border border-[#2e3454] rounded-xl overflow-hidden flex flex-col flex-1">
            <div className="flex items-center gap-2 px-4 py-3 border-b border-[#1f2440]">
              <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0" />
              <span className="text-sm font-medium text-[#e8eaf6]">Confirm Replace All</span>
            </div>

            <div className="px-4 py-3 text-xs text-[#5c6391] border-b border-[#1f2440]">
              <p>
                Replace <span className="text-amber-400 font-mono">"{query}"</span> with{' '}
                <span className="text-green-400 font-mono">"{replacement}"</span>
              </p>
              <p className="mt-1 text-[#3d4466]">
                Version snapshots will be created before replacing. Select chapters to include:
              </p>
            </div>

            <div className="flex-1 overflow-y-auto p-3 space-y-1.5">
              {dryRunPreview.map(p => (
                <label
                  key={p.chapter_id}
                  className="flex items-center gap-3 p-2.5 rounded-lg hover:bg-[#1a1e36] cursor-pointer"
                >
                  <input
                    type="checkbox"
                    checked={selectedChapters.has(p.chapter_id)}
                    onChange={() => toggleChapterSelect(p.chapter_id)}
                    className="w-3.5 h-3.5 accent-amber-500"
                  />
                  <span className="text-xs text-[#9da3c8] flex-1">
                    Ch.{p.chapter_number} — {p.chapter_title}
                  </span>
                  <span className="text-xs text-amber-400">
                    {p.match_count} replacement{p.match_count !== 1 ? 's' : ''}
                  </span>
                </label>
              ))}
            </div>

            <div className="flex gap-2 p-3 border-t border-[#1f2440]">
              <button
                onClick={() => { setShowConfirm(false); setDryRunPreview([]) }}
                className="flex-1 py-2 rounded-lg border border-[#2e3454] text-xs text-[#9da3c8] hover:border-[#3d4466] transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmReplace}
                disabled={selectedChapters.size === 0}
                className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg bg-amber-500 text-black text-xs font-semibold hover:bg-amber-600 disabled:opacity-40 transition-colors"
              >
                <Check className="w-3.5 h-3.5" />
                Replace in {selectedChapters.size} chapter{selectedChapters.size !== 1 ? 's' : ''}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
