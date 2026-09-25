'use client'

// Selection Toolbar — compact, expandable AI transforms on the EXACT selected text.
// Driven entirely by the shared transform config (lib/transforms) so it exposes the
// full real option set (refine modes, tones, emotions+intensity, audiences, styles,
// languages) without duplicating definitions. Every option calls the correct
// ai_transform endpoint with the selected text only (never RAG/plot/Q&A). Shows a
// preview; Apply replaces only the originally-captured range.
//
// PRE-2 (QA Issues 1 and 11) — three guarantees, all decided in one place
// (lib/selectionOwnership), never by this component reaching into another:
//   1. It shows only for a live, meaningful selection, and Escape dismisses it.
//   2. It stands down whenever the AI Assistant sidebar is on screen — one surface
//      owns a selection at a time. A generated preview still stays reviewable;
//      opening a panel must not destroy AI output the author has not read yet.
//   3. It rests at the bottom of the editor column, clear of the formatting bar and
//      the Save control, and the author can drag it anywhere inside that column.
//
// Manuscript safety: a preview is bound to the chapter it was generated for.
// `from`/`to` are document offsets — applying them to a different chapter would
// overwrite unrelated prose. Every path (chapter switch, late AI response, Apply)
// re-checks that binding and discards rather than guesses.

import { useEffect, useMemo, useRef, useState } from 'react'
import { Sparkles, Loader2, Check, X, ChevronDown, GripVertical, Lock, Unlock, AlertTriangle } from 'lucide-react'
import { toast } from 'sonner'
import {
  TRANSFORM_GROUPS, INTENSITIES, runTransform, splitSentences, LOCKABLE_GROUPS, STRENGTH_LEVELS,
  type GroupId, type StrengthLevel, type SentenceSpan,
} from '@/lib/transforms'
import { useStoryContext } from './StoryContextEngine'
import { deriveToolDefaults, hasGenreProfile } from '@/lib/genreDefaults'
import {
  isDismissedFor, previewInvalidReason, resolveToolbarMode, selectionKey, selectionSafeProps,
  type PreviewIdentity,
} from '@/lib/selectionOwnership'
import {
  clampToolbarPosition, defaultToolbarPosition, menuOpensUpward, type Point, type Size,
} from '@/lib/toolbarPosition'
import type { LiveSelection } from '@/components/editor/EditorWithMethods'
import { P3_ENABLED, CONTROLLABLE_GROUPS, buildControls } from '@/lib/generationControls'
import { useGenerationStore } from '@/lib/generationStore'
import GenerationWarnings, { applyNameFixes } from '@/components/generation/GenerationWarnings'
import PinActions from '@/components/generation/PinActions'
import type { GenerationWarning } from '@/lib/types'

interface Preview extends PreviewIdentity {
  text: string
  group: GroupId
  value: string
  // Task 5.3 — surfaced deterministic signals from the Stage 5 response, not
  // just the rewritten prose. See preservation_violations/strengthViolation.
  preservationViolations: string[]
  strengthViolation: boolean
  lockedSentenceCount: number
  // Phase 3 (Stage 7)
  warnings: GenerationWarning[]
  sessionId: string
  toolParams: Record<string, unknown>
  contextPinIds: string[]
}

interface Props {
  selection: LiveSelection | null
  /** True when the AI Assistant sidebar is on screen and therefore owns the selection. */
  sidebarVisible: boolean
}

const sameSize = (a: Size | null, b: Size) => !!a && a.width === b.width && a.height === b.height

export default function SelectionToolbar({ selection, sidebarVisible }: Props) {
  const { storyId, activeChapterId, editor, logActivity, genreProfile } = useStoryContext()
  const gen = useGenerationStore()
  useEffect(() => { gen.setStory(storyId) }, [storyId]) // eslint-disable-line react-hooks/exhaustive-deps
  const [openGroup, setOpenGroup] = useState<GroupId | null>(null)
  const [busy, setBusy] = useState(false)
  const [intensity, setIntensity] = useState<string>('medium')
  // Task 5.6 — strength control, offered only for the groups whose backend
  // schema accepts it (LOCKABLE_GROUPS — same set as the lock feature, since
  // both come from schemas.StrengthMixin).
  const [strength, setStrength] = useState<StrengthLevel>('light')
  // Task 5.4 — indices into splitSentences(selection.text) the author has
  // marked locked for the NEXT transform run on this selection.
  const [lockedIdx, setLockedIdx] = useState<Set<number>>(new Set())
  const [preview, setPreview] = useState<Preview | null>(null)
  // Escape hides the toolbar for the selection it was pressed on; the author's
  // next selection — even of the same words — brings it back (isDismissedFor).
  const [dismissedFor, setDismissedFor] = useState<LiveSelection | null>(null)
  const dismissed = isDismissedFor(dismissedFor, selection)
  // Only the newest transform may produce a preview; older ones resolve into nothing.
  const requestSeq = useRef(0)

  // Genre-recommended option per group (only when the story has a genre profile).
  // Drives a "recommended" highlight + a dot on the group button, so the toolbar
  // visually guides toward genre-appropriate choices without blocking any option.
  const profilePresent = hasGenreProfile(genreProfile)
  const d = deriveToolDefaults(genreProfile)
  const recByGroup: Partial<Record<GroupId, string>> = profilePresent
    ? { tone: d.tone, emotion: d.emotion, style: d.style, age_adapt: d.age }
    : {}
  const isRecommended = (g: GroupId, optId: string) =>
    (recByGroup[g] ?? '').toLowerCase() === optId.toLowerCase()

  // ── What this toolbar is (single ownership rule, not a local guess) ─────────
  const mode = resolveToolbarMode({ selection, preview, activeChapterId, sidebarVisible, dismissed })

  // Selection lifecycle: on a new range (or a cleared one) close any open dropdown,
  // drop a stale preview, and un-dismiss — a fresh selection is a fresh intent.
  const selKey = selectionKey(selection)
  const prevKeyRef = useRef<string | null>(null)
  useEffect(() => {
    if (selKey === prevKeyRef.current) return
    prevKeyRef.current = selKey
    setOpenGroup(null)
    if (selKey) setPreview(null)
    // A new selection is a new set of sentences — stale locked indices would
    // point at the wrong spans (or none at all) in different prose.
    setLockedIdx(new Set())
  }, [selKey])

  // Sentences of the CURRENT selection, for the lock picker — recomputed only
  // when the selected text itself changes, not on every render.
  const sentenceSpans: SentenceSpan[] = useMemo(
    () => (selection ? splitSentences(selection.text) : []),
    [selection?.text],
  )

  // Chapter boundary. A preview generated for another chapter is discarded the
  // moment the author moves away — it can never survive to be applied.
  const chapterRef = useRef<string | null>(activeChapterId)
  useEffect(() => {
    chapterRef.current = activeChapterId
    setPreview((p) => (p && p.chapterId !== activeChapterId ? null : p))
  }, [activeChapterId])

  // Handing ownership to the sidebar closes any open menu, so the toolbar does not
  // come back later with a stale dropdown hanging off it.
  useEffect(() => {
    if (sidebarVisible) setOpenGroup(null)
  }, [sidebarVisible])

  // Escape, from every state: menu → preview → toolbar.
  useEffect(() => {
    if (mode === 'hidden') return
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      if (openGroup) { setOpenGroup(null); return }
      if (preview) { setPreview(null); return }
      setDismissedFor(selection)
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [mode, openGroup, preview, selection])

  // ── Position: measured, clamped, draggable ─────────────────────────────────
  const containerRef = useRef<HTMLDivElement | null>(null)
  const boxRef = useRef<HTMLDivElement | null>(null)
  const [bounds, setBounds] = useState<Size | null>(null)
  const [size, setSize] = useState<Size | null>(null)
  // Where the author dragged it, for as long as this workspace stays mounted.
  // Deliberately NOT persisted: a component Phase 3A will redesign does not need a
  // localStorage schema, a migration path or a rollback story to be draggable.
  const [userPos, setUserPos] = useState<Point | null>(null)
  const [dragPos, setDragPos] = useState<Point | null>(null)

  useEffect(() => {
    const c = containerRef.current
    const b = boxRef.current
    if (!c || !b || typeof ResizeObserver === 'undefined') return
    const measure = () => {
      const nextBounds = { width: c.clientWidth, height: c.clientHeight }
      const nextSize = { width: b.offsetWidth, height: b.offsetHeight }
      setBounds((prev) => (sameSize(prev, nextBounds) ? prev : nextBounds))
      setSize((prev) => (sameSize(prev, nextSize) ? prev : nextSize))
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(c)
    ro.observe(b)
    return () => ro.disconnect()
  }, [mode])

  // The chosen position is held raw and clamped here, so shrinking the column brings
  // the toolbar back into view without destroying where the author put it — and
  // widening the column again returns it there.
  const pos = useMemo<Point | null>(() => {
    if (!bounds || !size) return null
    const base = dragPos ?? userPos ?? defaultToolbarPosition(size, bounds)
    return clampToolbarPosition(base, size, bounds)
  }, [dragPos, userPos, bounds, size])

  const menuUp = menuOpensUpward(pos, bounds)

  const dragRef = useRef<{ startX: number; startY: number; origin: Point; moved: boolean } | null>(null)

  const onDragStart = (e: React.PointerEvent) => {
    if (!pos) return
    e.preventDefault()                       // never steal the editor's selection
    e.currentTarget.setPointerCapture?.(e.pointerId)
    dragRef.current = { startX: e.clientX, startY: e.clientY, origin: pos, moved: false }
    setDragPos(pos)
  }
  const onDragMove = (e: React.PointerEvent) => {
    const drag = dragRef.current
    if (!drag || !size || !bounds) return
    drag.moved = true
    setDragPos(clampToolbarPosition(
      { x: drag.origin.x + (e.clientX - drag.startX), y: drag.origin.y + (e.clientY - drag.startY) },
      size, bounds,
    ))
  }
  const onDragEnd = () => {
    const drag = dragRef.current
    if (!drag) return
    dragRef.current = null
    // A click that never moved is not a reposition — leave the toolbar on its
    // default, which keeps re-centring itself when the column is resized.
    if (drag.moved && dragPos) setUserPos(dragPos)
    setDragPos(null)
  }

  if (mode === 'hidden') return null

  const run = async (group: GroupId, value: string) => {
    if (!selection) { toast.error('Select the text again to transform it.'); return }
    const { from, to, text, chapterId } = selection
    const lockable = LOCKABLE_GROUPS.includes(group)
    // Locked ranges are computed at RUN time, from the CURRENT sentence spans
    // and the author's current lock selections — never stale offsets held
    // over from a previous selection or a previous render.
    const spans = lockable ? splitSentences(text) : []
    const lockedRanges = lockable
      ? Array.from(lockedIdx).filter((i) => i < spans.length).map((i) => ({ start: spans[i].start, end: spans[i].end }))
      : undefined
    const seq = ++requestSeq.current
    setBusy(true); setOpenGroup(null)
    // Phase 3 — only for tools whose endpoint accepts controls. The avoid-set is
    // this session's earlier attempts for the same tool + chapter (P3-07's quiet
    // default); nothing about them is stored anywhere.
    const p3 = P3_ENABLED && CONTROLLABLE_GROUPS.includes(group)
    const contextPinIds = p3 ? [...gen.contextPinIds] : []
    const controls = p3 ? buildControls({
      contextPinIds, avoidPinIds: gen.avoidPinIds, avoidTexts: gen.recentTexts(chapterId, group),
      localContext: editor?.getSurroundingText?.(from, to) ?? undefined,
    }) : undefined
    const toolParams: Record<string, unknown> = group === 'emotion'
      ? { emotion: value.toLowerCase(), intensity } : group === 'age_adapt' ? { target_age: value } : { [group]: value.toLowerCase() }
    try {
      const result = await runTransform(group, value, text, {
        storyId, chapterId, intensity, controls,
        ...(lockable ? { strength, lockedRanges } : {}),
      })
      // A newer transform was started while this one was in flight — the author is
      // waiting on that one, and only it may produce the preview.
      if (requestSeq.current !== seq) return
      // The author may have switched chapters while the model was working. Those
      // offsets no longer describe anything real — discard rather than apply.
      if (chapterRef.current !== chapterId) {
        toast.info('You moved to another chapter, so that suggestion was discarded.')
        return
      }
      // Task 5.5 — already suitable: nothing to review or apply, tell the
      // author why instead of showing a no-op preview.
      if (result.no_change) {
        toast.info(result.reason ? `Already reads that way — ${result.reason}` : 'This already reads that way — no change made.')
        return
      }
      // A lock-contract failure: the server returned the ORIGINAL text. Keep the
      // current preview and the author's locks exactly as they were (P3-02).
      if (result.failed) {
        toast.error(result.reason ?? 'Those sentences could not be rewritten safely with the current locks. Nothing was changed.')
        return
      }
      const sessionId = `${Date.now()}-${seq}`
      if (p3) {
        const priorAttempts = gen.recentTexts(chapterId, group).length
        gen.record({ id: sessionId, text: result.transformed, tool: group, toolParams, chapterId, sourceText: text,
                     sourceFrom: from, sourceTo: to, createdAt: Date.now(), contextPinIds })
        if (priorAttempts >= 1 && !gen.firstRunHintShown) {
          gen.markHintShown()
          toast.info('Only pinned versions are kept. Everything else disappears when you refresh.')
        }
      }
      setPreview({
        text: result.transformed, from, to, group, value, chapterId, sourceText: text,
        preservationViolations: result.preservation_violations,
        strengthViolation: result.strength_violation,
        lockedSentenceCount: lockedRanges?.length ?? 0,
        warnings: result.warnings, sessionId, toolParams, contextPinIds,
      })
      logActivity({ category: 'ai', type: `${group}_transform`, title: `AI ${group} on selection`, summary: result.transformed.slice(0, 160), ref_type: 'selection', metadata: { value, strength: lockable ? strength : undefined, locked_count: lockedRanges?.length ?? 0 } })
    } catch (e: any) {
      const d = e?.response?.data?.detail
      if (requestSeq.current === seq) toast.error(typeof d === 'string' ? d : 'The AI could not rewrite this right now. Your text is unchanged.')
    } finally {
      if (requestSeq.current === seq) setBusy(false)
    }
  }

  // P3-02 "regenerate only these": swap locked and unlocked sentences.
  const invertLocks = () => setLockedIdx((prev) => new Set(sentenceSpans.map((_, i) => i).filter((i) => !prev.has(i))))

  const toggleLock = (idx: number) => {
    setLockedIdx((prev) => {
      const next = new Set(prev)
      if (next.has(idx)) next.delete(idx); else next.add(idx)
      return next
    })
  }

  const apply = () => {
    if (!preview) return
    if (!editor) { toast.error('Editor not ready — please reselect.'); setPreview(null); return }
    // Authoritative re-check at the moment of writing: the chapter must be the same
    // one AND the range must still hold the exact words the suggestion was made
    // from. Anything else and we discard — we never overwrite prose we cannot
    // account for.
    const reason = previewInvalidReason(preview, activeChapterId, editor.getTextInRange(preview.from, preview.to))
    if (reason) {
      setPreview(null)
      toast.error(reason === 'chapter-changed'
        ? 'That suggestion belonged to another chapter, so it was not applied.'
        : 'The text under this suggestion has changed, so it was not applied. Select it again.')
      return
    }
    editor.replaceRange(preview.from, preview.to, preview.text)
    toast.success('Applied to your selected text')
    setPreview(null)
  }

  // Best-effort check for display. Typing does not re-render this component, so a
  // stale "looks fine" is possible — which is why `apply()` re-checks at the moment
  // of writing. This exists so the common case shows the author the problem before
  // they click, not after.
  const previewProblem = preview && editor
    ? previewInvalidReason(preview, activeChapterId, editor.getTextInRange(preview.from, preview.to))
    : null

  const dragHandle = (
    <button
      type="button"
      onPointerDown={onDragStart}
      onPointerMove={onDragMove}
      onPointerUp={onDragEnd}
      onPointerCancel={onDragEnd}
      onDoubleClick={() => setUserPos(null)}
      title="Drag to move · double-click to reset position"
      aria-label="Move the AI toolbar. Double-click to reset its position."
      data-testid="toolbar-drag-handle"
      className="flex-shrink-0 px-0.5 text-[#8e94bd] hover:text-[#9da3c8] cursor-grab active:cursor-grabbing touch-none"
    >
      <GripVertical className="w-3.5 h-3.5" />
    </button>
  )

  return (
    <div ref={containerRef} className="absolute inset-0 z-20 pointer-events-none">
      <div
        ref={boxRef}
        style={pos ? { left: pos.x, top: pos.y } : undefined}
        className={`absolute pointer-events-auto w-[min(94%,46rem)] ${pos ? '' : 'left-1/2 -translate-x-1/2 bottom-3'}`}
        onMouseDown={(e) => e.stopPropagation()}
        {...selectionSafeProps()}
      >
        {mode === 'controls' ? (
          <div role="toolbar" aria-label="AI actions for the selected text"
            className="relative flex items-center gap-0.5 rounded-full border border-[#2e3454] bg-[#13162a] shadow-xl px-2 py-1">
            {dragHandle}
            <Sparkles className="w-3.5 h-3.5 text-amber-400 mx-1 flex-shrink-0" />
            {busy && <Loader2 className="w-3.5 h-3.5 animate-spin text-amber-400" />}
            {TRANSFORM_GROUPS.map((g) => (
              <div key={g.id} className="relative">
                <button disabled={busy} onClick={() => setOpenGroup((o) => (o === g.id ? null : g.id))}
                  aria-haspopup="menu" aria-expanded={openGroup === g.id}
                  title={recByGroup[g.id] ? `Genre recommends: ${recByGroup[g.id]}` : undefined}
                  className={`relative flex items-center gap-1 text-[11px] px-2 py-1 rounded-full ${openGroup === g.id ? 'bg-[#1f2440] text-amber-300' : 'text-[#cdd2f0] hover:bg-[#1f2440]'} disabled:opacity-50`}>
                  <g.icon className="w-3 h-3" /> {g.label} <ChevronDown className="w-2.5 h-2.5 opacity-60" />
                  {recByGroup[g.id] && (
                    <span className="absolute -top-0.5 -right-0.5 w-1.5 h-1.5 rounded-full bg-amber-400" aria-hidden />
                  )}
                </button>
                {openGroup === g.id && (
                  <div role="menu" className={`absolute ${menuUp ? 'bottom-full mb-1' : 'top-full mt-1'} left-0 z-30 w-56 rounded-lg border border-[#2e3454] bg-[#13162a] shadow-2xl py-1 max-h-72 overflow-y-auto`}>
                    {g.id === 'emotion' && (
                      <div className="flex items-center gap-1 px-2 py-1.5 border-b border-[#1f2440]">
                        <span className="text-[10px] text-[#8e94bd] mr-1">Intensity</span>
                        {INTENSITIES.map((i) => (
                          <button key={i} onClick={() => setIntensity(i)}
                            className={`text-[10px] px-1.5 py-0.5 rounded ${intensity === i ? 'bg-amber-500/20 text-amber-300' : 'text-[#9da3c8] hover:bg-[#1f2440]'}`}>{i}</button>
                        ))}
                      </div>
                    )}
                    {LOCKABLE_GROUPS.includes(g.id) && (
                      <>
                        {/* Task 5.6 — strength control. Applies to whichever option
                            below is clicked next. */}
                        <div className="flex items-center gap-1 px-2 py-1.5 border-b border-[#1f2440]">
                          <span className="text-[10px] text-[#8e94bd] mr-1">Strength</span>
                          {STRENGTH_LEVELS.map((s) => (
                            <button key={s} onClick={() => setStrength(s)}
                              title={
                                s === 'light' ? 'Word choice and connectives only' :
                                s === 'moderate' ? 'Sentence-level rewriting allowed' :
                                'Full rewrite within preservation limits'
                              }
                              className={`text-[10px] px-1.5 py-0.5 rounded ${strength === s ? 'bg-amber-500/20 text-amber-300' : 'text-[#9da3c8] hover:bg-[#1f2440]'}`}>{s}</button>
                          ))}
                        </div>
                        {/* Task 5.4 — sentence locking. Toggled sentences are sent as
                            locked_ranges and are guaranteed byte-identical in the
                            result, never trusted from the model's own output. */}
                        {sentenceSpans.length > 1 && (
                          <div className="px-2 py-1.5 border-b border-[#1f2440]">
                            <div className="flex items-center gap-1 mb-1">
                              <Lock className="w-2.5 h-2.5 text-[#8e94bd]" />
                              <span className="text-[10px] text-[#8e94bd]">
                                Lock sentences to keep unchanged{lockedIdx.size > 0 ? ` (${lockedIdx.size})` : ''}
                              </span>
                              <button type="button" onClick={invertLocks} data-testid="invert-locks"
                                title="Lock everything except the sentences picked — rewrite only those"
                                className="ml-auto text-[10px] px-1 rounded text-[#9da3c8] hover:text-amber-300">Invert</button>
                            </div>
                            <div className="max-h-24 overflow-y-auto space-y-0.5">
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
                        )}
                      </>
                    )}
                    {recByGroup[g.id] && (
                      <div className="px-3 py-1 text-[10px] text-amber-300/80 border-b border-[#1f2440]">
                        ★ Recommended for {genreProfile?.genre || 'this genre'}
                      </div>
                    )}
                    {g.options.map((o) => {
                      const recommended = isRecommended(g.id, o.id)
                      return (
                        <button key={o.id} role="menuitem" onClick={() => run(g.id, o.id)}
                          className={`w-full text-left px-3 py-1.5 flex items-center gap-2 ${recommended ? 'bg-amber-500/10 hover:bg-amber-500/20' : 'hover:bg-[#1f2440]'}`}>
                          {o.emoji && <span>{o.emoji}</span>}
                          <span className={`text-xs ${recommended ? 'text-amber-300' : 'text-[#e8eaf6]'}`}>{o.label}</span>
                          {recommended && <span className="text-[10px] text-amber-400">★</span>}
                          {o.desc && <span className="text-[10px] text-[#8e94bd] ml-auto">{o.desc}</span>}
                        </button>
                      )
                    })}
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : preview ? (
          <div className="rounded-lg border border-amber-500/30 bg-[#13162a] shadow-2xl p-3 space-y-2">
            <div className="flex items-center gap-1">
              {dragHandle}
              <p className="text-[10px] uppercase tracking-wide text-amber-300/80">
                Preview · {preview.group.replace('_', ' ')} {preview.value} (selected text)
                {preview.lockedSentenceCount > 0 && (
                  <span className="ml-1 normal-case text-amber-200/80">
                    · {preview.lockedSentenceCount} sentence{preview.lockedSentenceCount === 1 ? '' : 's'} locked
                  </span>
                )}
              </p>
            </div>
            <p className="text-xs text-[#cdd2f0] leading-relaxed max-h-48 overflow-y-auto whitespace-pre-wrap font-serif">{preview.text}</p>
            {preview.warnings.length > 0 && (
              <GenerationWarnings warnings={preview.warnings}
                onAutofix={(fixes) => setPreview((p) => (p ? { ...p, text: applyNameFixes(p.text, fixes),
                  warnings: p.warnings.filter((w) => !w.autofix) } : p))} />
            )}
            {/* Task 5.3 — surface preservation warnings in the UI, not just the API. */}
            {preview.warnings.length === 0 && preview.preservationViolations.length > 0 && (
              <p data-testid="preservation-warning" className="flex items-start gap-1 text-[11px] text-red-300 bg-red-500/10 border border-red-500/30 rounded px-2 py-1.5">
                <AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" />
                Could not confirm these character names were preserved: {preview.preservationViolations.join(', ')}.
              </p>
            )}
            {preview.strengthViolation && (
              <p data-testid="strength-warning" className="text-[11px] text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded px-2 py-1.5">
                This rewrite changed more than a {strength}-strength edit usually does — review before applying.
              </p>
            )}
            {previewProblem && (
              <p data-testid="preview-stale" className="text-[11px] text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded px-2 py-1.5">
                You have changed this passage since the suggestion was made, so it can no longer replace it.
                {previewProblem === 'text-changed' && P3_ENABLED ? ' You can insert it at your cursor instead, or select the text again to redo it.' : ' Select the text again to redo it.'}
              </p>
            )}
            {P3_ENABLED && CONTROLLABLE_GROUPS.includes(preview.group) && (
              <PinActions source={{
                text: preview.text, tool: preview.group, toolParams: preview.toolParams, chapterId: preview.chapterId,
                sourceText: preview.sourceText, sourceFrom: preview.from, sourceTo: preview.to,
                derivedFromPinIds: preview.contextPinIds, sessionId: preview.sessionId,
              }} />
            )}
            <div className="flex gap-2">
              {previewProblem === 'text-changed' && P3_ENABLED ? (
                <button data-testid="insert-at-cursor" onClick={() => {
                  if (!editor || preview.chapterId !== activeChapterId) { toast.error('Open the chapter this suggestion was made for first.'); return }
                  editor.insertText(preview.text); toast.success('Inserted at your cursor'); setPreview(null)
                }}
                  className="flex-1 text-xs py-1.5 rounded bg-amber-500 hover:bg-amber-400 text-black font-medium flex items-center justify-center gap-1">
                  <Check className="w-3.5 h-3.5" /> Insert at cursor instead
                </button>
              ) : (
              <button onClick={apply} disabled={!!previewProblem}
                className="flex-1 text-xs py-1.5 rounded bg-amber-500 hover:bg-amber-400 disabled:opacity-40 disabled:cursor-not-allowed text-black font-medium flex items-center justify-center gap-1">
                <Check className="w-3.5 h-3.5" /> Apply to selection
              </button>
              )}
              <button onClick={() => setPreview(null)} className="flex-1 text-xs py-1.5 rounded border border-[#2a3057] text-[#9da3c8] hover:text-white flex items-center justify-center gap-1">
                <X className="w-3.5 h-3.5" /> Discard
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}
