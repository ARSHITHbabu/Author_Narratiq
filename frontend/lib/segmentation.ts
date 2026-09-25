// Sentence segmentation with a byte-exact reassembly invariant (spec §24.2):
//   assemble(segmentSentences(text)) === text   — always.
// `trailing` keeps the whitespace after each sentence, so paragraph breaks
// inside a selection survive. Dialogue-aware: a closing quote after the
// terminal punctuation stays with its sentence ("Run," she said. is one unit
// when the quote closes before the tag).

export interface Segment { index: number; text: string; trailing: string; start: number; end: number }

const FALLBACK = /[^.!?…]+[.!?…]+["'”’)\]]*\s*|[^.!?…]+$/gu

export function segmentSentences(text: string, locale = 'en'): Segment[] {
  const raw: string[] = []
  const Seg = (Intl as unknown as { Segmenter?: new (l: string, o: { granularity: 'sentence' }) => { segment: (t: string) => Iterable<{ segment: string }> } }).Segmenter
  if (Seg) {
    for (const s of new Seg(locale, { granularity: 'sentence' }).segment(text)) raw.push(s.segment)
  } else {
    let m: RegExpExecArray | null
    FALLBACK.lastIndex = 0
    let consumed = 0
    while ((m = FALLBACK.exec(text)) && m[0].length) { raw.push(m[0]); consumed += m[0].length }
    if (consumed < text.length) raw.push(text.slice(consumed))
  }
  const out: Segment[] = []
  let pos = 0
  for (const piece of raw) {
    const body = piece.replace(/\s+$/u, '')
    const trailing = piece.slice(body.length)
    if (!body && out.length) {                // pure whitespace → attach to previous
      out[out.length - 1].trailing += trailing
    } else {
      out.push({ index: out.length, text: body, trailing, start: pos, end: pos + body.length })
    }
    pos += piece.length
  }
  return out
}

export function assemble(segments: Pick<Segment, 'text' | 'trailing'>[]): string {
  return segments.map((s) => s.text + s.trailing).join('')
}
