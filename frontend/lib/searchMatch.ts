// Exact-search matching over the editor document (Stage 12 remediation A9).
//
// Mirrors backend/services/search_match.py exactly, so the number the Search
// panel shows (counted by the backend over the saved chapter) equals the number
// of highlights here, the Replace All preview and the number replaced:
//   * text is matched per textblock (paragraph, heading, list item, …) — a
//     match never crosses a block, and never crosses a hard line break;
//   * inline formatting (bold, italic, underline, highlight, links) is joined
//     with no separator, so "Dev**ika**" reads "Devika";
//   * runs of ASCII whitespace collapse to one space and whitespace at the start
//     or end of a block is ignored (ProseMirror already does this on load; the
//     same rule here covers anything typed since); a non-breaking space stays a
//     distinct character;
//   * the query is literal; whole word = not preceded or followed by a letter,
//     combining mark, digit or underscore (Unicode-aware: café, हिंदी);
//     case-insensitive uses Unicode simple case folding;
//   * curly and straight quotes are not treated as equal.
// Shared fixtures: backend/tests/fixtures/search_match_cases.json.

export interface MatchRange { from: number; to: number }

const COLLAPSIBLE = new Set([' ', '\t', '\n', '\r', '\f'])
const WORD = '[\\p{L}\\p{M}\\p{N}_]'

export function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

export function buildPattern(query: string, caseSensitive: boolean, wholeWord: boolean): RegExp {
  const body = escapeRegex(query)
  const src = wholeWord ? `(?<!${WORD})${body}(?!${WORD})` : body
  return new RegExp(src, caseSensitive ? 'gu' : 'giu')
}

interface Segment { text: string; pos: number[] }

/** Split a ProseMirror doc into searchable segments, each with the document
 *  position of every character. Duck-typed so tests can pass a doc built from
 *  any TipTap schema. */
export function searchSegments(doc: any): Segment[] {
  const out: Segment[] = []
  doc.descendants((node: any, nodePos: number) => {
    if (!node.isTextblock) return true
    const preserve = node.type?.spec?.code === true || node.type?.name === 'codeBlock'
    let seg: Segment = { text: '', pos: [] }
    const close = () => {
      if (!preserve) {
        while (seg.text.endsWith(' ')) { seg.text = seg.text.slice(0, -1); seg.pos.pop() }
      }
      if (seg.text) out.push(seg)
      seg = { text: '', pos: [] }
    }
    node.forEach((child: any, offset: number) => {
      if (!child.isText) { close(); return }            // hard break, image, … → boundary
      const base = nodePos + 1 + offset
      const t: string = child.text
      // Iterate by code point so astral characters keep one entry per UTF-16 unit.
      for (let i = 0; i < t.length; i++) {
        let ch = t[i]
        if (!preserve && COLLAPSIBLE.has(ch)) {
          if (!seg.text || seg.text.endsWith(' ')) continue
          ch = ' '
        }
        seg.text += ch
        seg.pos.push(base + i)
      }
    })
    close()
    return false
  })
  return out
}

/** Every match of `query` in document order, as document ranges. */
export function findMatchRanges(doc: any, query: string, caseSensitive: boolean, wholeWord: boolean): MatchRange[] {
  if (!query || !query.trim()) return []
  const pattern = buildPattern(query, caseSensitive, wholeWord)
  const ranges: MatchRange[] = []
  for (const seg of searchSegments(doc)) {
    pattern.lastIndex = 0
    let m: RegExpExecArray | null
    while ((m = pattern.exec(seg.text)) !== null) {
      if (m[0].length === 0) { pattern.lastIndex++; continue }
      const start = m.index
      const end = m.index + m[0].length
      ranges.push({ from: seg.pos[start], to: seg.pos[end - 1] + 1 })
    }
  }
  return ranges
}
