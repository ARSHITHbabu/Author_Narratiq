// Selection Ownership — the one rule for which surface owns a text selection.
//
// Two surfaces can act on selected manuscript text: the floating Selection
// Toolbar and the AI Assistant sidebar (AISidecar → AIToolsSidebar). QA Issue 11
// was both being live at once — two controls for one action. The rule is:
//
//   sidebar visible  → the sidebar owns the selection
//   sidebar hidden   → the floating toolbar owns a meaningful selection
//   neither          → nobody owns it
//
// Everything here is pure and framework-free so the rule can be unit-tested
// without a browser, and so future surfaces (Phase 3A pin/regenerate/lock/compare,
// the Command Palette, the Voice Agent) reuse it instead of re-deriving it. No
// component decides ownership for another component; each asks this module.

/** Marks a DOM subtree that reads the editor selection, so a click inside it must
 *  NOT be treated as "the author clicked away and abandoned the selection". */
export const SELECTION_SAFE_ATTR = 'data-selection-safe'

/** Spread onto the root element of any surface that consumes the selection. */
export function selectionSafeProps(): Record<string, string> {
  return { [SELECTION_SAFE_ATTR]: 'true' }
}

/** A live editor selection, stamped with the chapter it was taken from.
 *  The chapter id is what makes cross-chapter application impossible — document
 *  offsets (`from`/`to`) are only meaningful inside the chapter they came from. */
export interface OwnedSelection {
  text: string
  from: number
  to: number
  chapterId: string
}

export type SelectionSurface = 'sidebar' | 'toolbar' | 'none'

/** What the floating toolbar should be showing.
 *  `controls` = the transform buttons. `preview` = an AI result awaiting review. */
export type ToolbarMode = 'hidden' | 'controls' | 'preview'

/** Anything that was generated for a specific chapter and may later be applied. */
export interface ChapterBound {
  chapterId: string
}

/** A whitespace-only drag is not a selection an author meant to transform. */
export function isMeaningfulSelection(selection: { text: string } | null | undefined): boolean {
  return !!selection && selection.text.trim().length > 0
}

/** Identity of a selection — changes whenever the range or the chapter changes.
 *  Used to reset transient toolbar state (open menu, dismissal, stale preview). */
export function selectionKey(selection: OwnedSelection | null | undefined): string | null {
  return selection ? `${selection.chapterId}:${selection.from}:${selection.to}` : null
}

/** Chapter boundary check. Anything generated for another chapter is invalid here,
 *  and an unknown active chapter is treated as invalid rather than assumed safe. */
export function isPreviewValid(
  preview: ChapterBound | null | undefined,
  activeChapterId: string | null | undefined,
): boolean {
  return !!preview && !!activeChapterId && preview.chapterId === activeChapterId
}

/** THE ownership rule. Every surface asks this; none of them decides for itself. */
export function selectionOwner(input: {
  selection: { text: string } | null
  sidebarVisible: boolean
}): SelectionSurface {
  // The sidebar owns the selection whenever it is on screen — including when
  // nothing is selected, because it then explicitly works on the full chapter.
  if (input.sidebarVisible) return 'sidebar'
  return isMeaningfulSelection(input.selection) ? 'toolbar' : 'none'
}

/** What the floating toolbar renders, derived from the ownership rule.
 *
 *  A valid preview outranks everything: it holds AI output the author has not
 *  reviewed yet, and opening a panel must never destroy generated text. A preview
 *  for a different chapter is not "outranking" anything — it is invalid. */
export function resolveToolbarMode(input: {
  selection: OwnedSelection | null
  preview: ChapterBound | null
  activeChapterId: string | null
  sidebarVisible: boolean
  dismissed: boolean
}): ToolbarMode {
  if (isPreviewValid(input.preview, input.activeChapterId)) return 'preview'
  if (input.dismissed) return 'hidden'
  const owner = selectionOwner({ selection: input.selection, sidebarVisible: input.sidebarVisible })
  return owner === 'toolbar' ? 'controls' : 'hidden'
}

/** True when the event target sits inside a surface that consumes the selection.
 *  Part of the ownership contract, not general DOM utility: it is how a surface
 *  declares "a click here is still about the selection". */
export function isSelectionSafeTarget(target: unknown): boolean {
  const el = target as { closest?: (s: string) => unknown } | null
  if (!el || typeof el.closest !== 'function') return false
  return !!el.closest(`[${SELECTION_SAFE_ATTR}]`)
}

/** A generated result, bound to the exact text it was generated from.
 *  Chapter identity alone is not enough: the author can edit the chapter while a
 *  generation is in flight, which leaves `from`/`to` pointing at different words. */
export interface PreviewIdentity extends ChapterBound {
  from: number
  to: number
  /** The selected text as it was when generation started. */
  sourceText: string
}

export type PreviewInvalidReason = 'chapter-changed' | 'text-changed' | null

/** Why a preview may no longer be applied — or null when it is safe.
 *  `currentText` is what the document holds in that range right now; an empty
 *  string means the range no longer exists, which is a change like any other. */
export function previewInvalidReason(
  preview: PreviewIdentity | null,
  activeChapterId: string | null,
  currentText: string | null,
): PreviewInvalidReason {
  if (!preview) return null
  if (!isPreviewValid(preview, activeChapterId)) return 'chapter-changed'
  if (currentText !== preview.sourceText) return 'text-changed'
  return null
}
