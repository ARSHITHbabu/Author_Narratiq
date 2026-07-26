import { test, expect } from '@playwright/test'
import {
  SELECTION_SAFE_ATTR,
  isMeaningfulSelection,
  isPreviewValid,
  isSelectionSafeTarget,
  previewInvalidReason,
  resolveToolbarMode,
  selectionKey,
  selectionOwner,
  selectionSafeProps,
  type OwnedSelection,
  type PreviewIdentity,
} from '../lib/selectionOwnership'

// PRE-2 (Phase 2 QA Issues 1 and 11) — the selection-ownership rule.
// Pure logic, no browser: the rule itself is what must not regress. The DOM
// behaviour that consumes it is covered by tests/browser/selection-toolbar.spec.ts.

const sel = (over: Partial<OwnedSelection> = {}): OwnedSelection =>
  ({ text: 'the lighthouse kept its own hours', from: 10, to: 43, chapterId: 'ch-1', ...over })

// ── Meaningful selection ────────────────────────────────────────────────────

test('a null selection is not meaningful', () => {
  expect(isMeaningfulSelection(null)).toBe(false)
  expect(isMeaningfulSelection(undefined)).toBe(false)
})

test('a whitespace-only drag is not a selection an author meant to transform', () => {
  for (const text of ['', ' ', '   ', '\n', '\t\n ']) {
    expect(isMeaningfulSelection({ text })).toBe(false)
  }
})

test('any real text is a meaningful selection', () => {
  expect(isMeaningfulSelection({ text: 'a' })).toBe(true)
  expect(isMeaningfulSelection({ text: '  she waited.  ' })).toBe(true)
})

// ── Ownership: exactly one surface at a time (QA Issue 11) ──────────────────

test('the sidebar owns the selection whenever it is visible', () => {
  expect(selectionOwner({ selection: sel(), sidebarVisible: true })).toBe('sidebar')
})

test('the sidebar still owns the selection when nothing is selected — it uses the full chapter', () => {
  expect(selectionOwner({ selection: null, sidebarVisible: true })).toBe('sidebar')
})

test('the toolbar owns a meaningful selection only while the sidebar is hidden', () => {
  expect(selectionOwner({ selection: sel(), sidebarVisible: false })).toBe('toolbar')
})

test('nobody owns an empty selection with the sidebar hidden', () => {
  expect(selectionOwner({ selection: null, sidebarVisible: false })).toBe('none')
  expect(selectionOwner({ selection: sel({ text: '   ' }), sidebarVisible: false })).toBe('none')
})

test('the two surfaces are never both owners — for every input combination', () => {
  for (const selection of [null, sel(), sel({ text: ' ' })]) {
    for (const sidebarVisible of [true, false]) {
      const owner = selectionOwner({ selection, sidebarVisible })
      expect(['sidebar', 'toolbar', 'none']).toContain(owner)
      if (sidebarVisible) expect(owner).not.toBe('toolbar')
    }
  }
})

// ── Toolbar mode ────────────────────────────────────────────────────────────

const mode = (over: Partial<Parameters<typeof resolveToolbarMode>[0]> = {}) =>
  resolveToolbarMode({
    selection: sel(),
    preview: null,
    activeChapterId: 'ch-1',
    sidebarVisible: false,
    dismissed: false,
    ...over,
  })

test('a live selection with the sidebar hidden shows the controls', () => {
  expect(mode()).toBe('controls')
})

test('deselecting hides the toolbar', () => {
  expect(mode({ selection: null })).toBe('hidden')
})

test('a whitespace-only selection does not raise the toolbar', () => {
  expect(mode({ selection: sel({ text: '  ' }) })).toBe('hidden')
})

test('opening the AI sidebar suppresses the toolbar controls', () => {
  expect(mode({ sidebarVisible: true })).toBe('hidden')
})

test('Escape hides the toolbar even with a live selection', () => {
  expect(mode({ dismissed: true })).toBe('hidden')
})

test('a valid preview stays reviewable when the sidebar opens — AI output is never destroyed by a panel', () => {
  expect(mode({ sidebarVisible: true, preview: { chapterId: 'ch-1' } })).toBe('preview')
})

test('a valid preview stays reviewable after the selection is gone', () => {
  expect(mode({ selection: null, preview: { chapterId: 'ch-1' } })).toBe('preview')
})

test('a preview from another chapter is not shown — it is invalid, not merely outranked', () => {
  expect(mode({ selection: null, preview: { chapterId: 'ch-2' } })).toBe('hidden')
})

test('a preview with no active chapter is treated as invalid rather than assumed safe', () => {
  expect(mode({ selection: null, activeChapterId: null, preview: { chapterId: 'ch-1' } })).toBe('hidden')
})

test('closing the sidebar hands the same selection straight back to the toolbar', () => {
  expect(mode({ sidebarVisible: true })).toBe('hidden')
  expect(mode({ sidebarVisible: false })).toBe('controls')
})

test('repeated sidebar open/close cycles are stateless — the rule is derived, never remembered', () => {
  for (let i = 0; i < 10; i++) {
    expect(mode({ sidebarVisible: true })).toBe('hidden')
    expect(mode({ sidebarVisible: false })).toBe('controls')
  }
})

// ── Chapter boundary (manuscript safety) ────────────────────────────────────

test('a preview is valid only inside the chapter it was generated for', () => {
  expect(isPreviewValid({ chapterId: 'ch-1' }, 'ch-1')).toBe(true)
  expect(isPreviewValid({ chapterId: 'ch-1' }, 'ch-2')).toBe(false)
  expect(isPreviewValid({ chapterId: 'ch-1' }, null)).toBe(false)
  expect(isPreviewValid(null, 'ch-1')).toBe(false)
})

test('the selection key changes when the chapter changes, even at identical offsets', () => {
  const a = selectionKey(sel({ chapterId: 'ch-1' }))
  const b = selectionKey(sel({ chapterId: 'ch-2' }))
  expect(a).not.toBe(b)
})

test('the selection key changes on every new range, so rapid re-selection cannot reuse stale state', () => {
  const keys = [sel({ from: 1, to: 5 }), sel({ from: 2, to: 5 }), sel({ from: 1, to: 6 })].map(selectionKey)
  expect(new Set(keys).size).toBe(3)
  expect(selectionKey(null)).toBeNull()
})

test('the same range in the same chapter is the same selection', () => {
  expect(selectionKey(sel())).toBe(selectionKey(sel()))
})

// ── Selection-safe surfaces ─────────────────────────────────────────────────

test('selection-safe props carry the documented attribute', () => {
  expect(selectionSafeProps()).toEqual({ [SELECTION_SAFE_ATTR]: 'true' })
})

test('a click inside a selection-safe surface does not read as abandoning the selection', () => {
  const inside = { closest: (s: string) => (s === `[${SELECTION_SAFE_ATTR}]` ? {} : null) }
  const outside = { closest: () => null }
  expect(isSelectionSafeTarget(inside)).toBe(true)
  expect(isSelectionSafeTarget(outside)).toBe(false)
})

test('a non-element event target is handled without throwing', () => {
  expect(isSelectionSafeTarget(null)).toBe(false)
  expect(isSelectionSafeTarget(undefined)).toBe(false)
  expect(isSelectionSafeTarget({})).toBe(false)
  expect(isSelectionSafeTarget('text node')).toBe(false)
})


// ── Preview validity beyond chapter identity (manuscript safety) ────────────

const previewId = (over: Partial<PreviewIdentity> = {}): PreviewIdentity =>
  ({ chapterId: 'ch-1', from: 10, to: 43, sourceText: 'the lighthouse kept its own hours', ...over })

test('a preview over unchanged text in its own chapter is applicable', () => {
  expect(previewInvalidReason(previewId(), 'ch-1', 'the lighthouse kept its own hours')).toBeNull()
})

test('a preview is refused after the chapter changes', () => {
  expect(previewInvalidReason(previewId(), 'ch-2', 'the lighthouse kept its own hours')).toBe('chapter-changed')
})

test('a preview is refused when the author edited the passage under it', () => {
  expect(previewInvalidReason(previewId(), 'ch-1', 'the lighthouse kept ITS OWN hours, mostly'))
    .toBe('text-changed')
})

test('a preview is refused when its range no longer exists — an empty range reads as changed', () => {
  expect(previewInvalidReason(previewId(), 'ch-1', '')).toBe('text-changed')
  expect(previewInvalidReason(previewId(), 'ch-1', null)).toBe('text-changed')
})

test('a one-character edit is enough to refuse — no fuzzy matching, no guessing', () => {
  expect(previewInvalidReason(previewId(), 'ch-1', 'the lighthouse kept its own hour')).toBe('text-changed')
  expect(previewInvalidReason(previewId(), 'ch-1', 'The lighthouse kept its own hours')).toBe('text-changed')
})

test('the chapter is checked before the text — the stronger boundary reports first', () => {
  expect(previewInvalidReason(previewId(), 'ch-2', 'something else entirely')).toBe('chapter-changed')
})

test('no preview means nothing to refuse', () => {
  expect(previewInvalidReason(null, 'ch-1', 'anything')).toBeNull()
})
