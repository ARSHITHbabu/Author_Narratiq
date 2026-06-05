import { Extension } from '@tiptap/core'
import { Plugin, PluginKey } from '@tiptap/pm/state'
import { Decoration, DecorationSet } from '@tiptap/pm/view'

interface SearchHighlightState {
  matches: Array<{ from: number; to: number }>
  activeIndex: number
}

export const searchHighlightKey = new PluginKey<SearchHighlightState>('searchHighlight')

export const SearchHighlightExtension = Extension.create({
  name: 'searchHighlight',

  addProseMirrorPlugins() {
    return [
      new Plugin({
        key: searchHighlightKey,
        state: {
          init: (): SearchHighlightState => ({ matches: [], activeIndex: -1 }),
          apply(tr, prev): SearchHighlightState {
            const meta = tr.getMeta(searchHighlightKey) as SearchHighlightState | undefined
            if (meta !== undefined) return meta

            // Map all match positions through the transaction so decorations
            // stay correct while the author is typing.
            // When setContent replaces the whole document, StoryEditor dispatches
            // an explicit clear-meta BEFORE the replace, so prev.matches is []
            // here and the loop is a no-op — providing a clean defence layer.
            if (!tr.docChanged || prev.matches.length === 0) return prev

            const newMatches: Array<{ from: number; to: number }> = []
            for (const m of prev.matches) {
              const from = tr.mapping.map(m.from)
              const to   = tr.mapping.map(m.to, -1)
              // Collapsed → the matched text was deleted (or this is a stale
              // position after a full document replacement that slipped through).
              // Treat any collapse as a signal to wipe the whole state so the
              // user never sees phantom highlights.
              if (from >= to) return { matches: [], activeIndex: -1 }
              newMatches.push({ from, to })
            }

            return { matches: newMatches, activeIndex: prev.activeIndex }
          },
        },
        props: {
          decorations(state) {
            const s = searchHighlightKey.getState(state)
            if (!s || !s.matches.length) return DecorationSet.empty

            const { matches, activeIndex } = s
            const decos = matches.map((m, i) =>
              Decoration.inline(m.from, m.to, {
                style:
                  i === activeIndex
                    ? 'background-color:rgba(251,146,60,0.55);border-radius:2px;outline:1px solid rgba(251,146,60,0.85);'
                    : 'background-color:rgba(251,191,36,0.35);border-radius:2px;',
              }),
            )
            return DecorationSet.create(state.doc, decos)
          },
        },
      }),
    ]
  },
})

// Escape regex special characters in a query string
function escapeRegex(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/**
 * Find all positions of query in the TipTap document.
 * Returns [{from, to}] in document order.
 */
export function findMatchPositions(
  doc: any,
  query: string,
  caseSensitive: boolean,
  wholeWord: boolean,
): Array<{ from: number; to: number }> {
  if (!query.trim()) return []
  const flags = caseSensitive ? 'g' : 'gi'
  const escaped = escapeRegex(query)
  const pattern = wholeWord ? new RegExp(`\\b${escaped}\\b`, flags) : new RegExp(escaped, flags)
  const positions: Array<{ from: number; to: number }> = []

  doc.descendants((node: any, pos: number) => {
    if (!node.isText || !node.text) return
    const regex = new RegExp(pattern.source, pattern.flags)
    let m: RegExpExecArray | null
    while ((m = regex.exec(node.text)) !== null) {
      positions.push({ from: pos + m.index, to: pos + m.index + m[0].length })
    }
  })

  return positions
}
