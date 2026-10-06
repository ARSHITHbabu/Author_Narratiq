// Suggestions with no selection read the start of the chapter, cut at a sentence end.
export const SUGGESTION_CHARS = 2000
export function wholeSentences(text: string, max: number): string {
  const t = text.trim()
  if (t.length <= max) return t
  const head = t.slice(0, max)
  const ends = [...head.matchAll(/[.!?…]["”’')\]]*(?=\s)/g)]
  if (ends.length) {
    const last = ends[ends.length - 1]
    return head.slice(0, (last.index ?? 0) + last[0].length)
  }
  const space = head.lastIndexOf(' ')
  return space > 0 ? head.slice(0, space) : head
}
