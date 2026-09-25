// Word-level diff (LCS) with sentence grouping — spec §23.1. No dependency.
//
// Client-side on purpose: both inputs are already in the browser, and a live
// (unpinned) generation must never be uploaded just to be compared (R1).
// Tokenisation keeps whitespace attached to the preceding word, so joining the
// tokens reproduces the input exactly and whitespace-only edits never show as
// changes. MAX_DIFF_TOKENS guards against pathological inputs by falling back
// to sentence-level diffing instead of freezing the tab.

import { segmentSentences } from './segmentation'

export type OpKind = 'equal' | 'insert' | 'delete'
export interface DiffOp { kind: OpKind; text: string }
export interface DiffBlock { a: string; b: string; changed: boolean }

export const MAX_DIFF_TOKENS = 4000

export function tokenize(s: string): string[] {
  return s.match(/\S+\s*|\s+/g) ?? []
}

const norm = (t: string) => t.trim()

export function diffTokens(a: string[], b: string[]): DiffOp[] {
  const n = a.length, m = b.length
  // LCS lengths, rolling from the end so backtracking walks forward.
  const dp: Uint16Array[] = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1))
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = norm(a[i]) === norm(b[j]) ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1])
    }
  }
  const ops: DiffOp[] = []
  const push = (kind: OpKind, text: string) => {
    const last = ops[ops.length - 1]
    if (last && last.kind === kind) last.text += text
    else ops.push({ kind, text })
  }
  let i = 0, j = 0
  while (i < n && j < m) {
    if (norm(a[i]) === norm(b[j])) { push('equal', b[j]); i++; j++ }
    else if (dp[i + 1][j] >= dp[i][j + 1]) { push('delete', a[i]); i++ }
    else { push('insert', b[j]); j++ }
  }
  while (i < n) push('delete', a[i++])
  while (j < m) push('insert', b[j++])
  return ops
}

export interface DiffResult { ops: DiffOp[]; sentenceLevel: boolean }

export function diffWords(a: string, b: string): DiffResult {
  const ta = tokenize(a), tb = tokenize(b)
  if (ta.length > MAX_DIFF_TOKENS || tb.length > MAX_DIFF_TOKENS) {
    const sa = segmentSentences(a).map((s) => s.text + s.trailing)
    const sb = segmentSentences(b).map((s) => s.text + s.trailing)
    return { ops: diffTokens(sa, sb), sentenceLevel: true }
  }
  return { ops: diffTokens(ta, tb), sentenceLevel: false }
}

export function stats(ops: DiffOp[]): { added: number; removed: number; unchanged: number } {
  const words = (t: string) => (t.trim() ? t.trim().split(/\s+/).length : 0)
  const out = { added: 0, removed: 0, unchanged: 0 }
  for (const op of ops) {
    if (op.kind === 'insert') out.added += words(op.text)
    else if (op.kind === 'delete') out.removed += words(op.text)
    else out.unchanged += words(op.text)
  }
  return out
}

/** Aligns two texts into blocks for per-block A/B merge. Sentences are the
 *  unit — the same segmentation the lock editor uses — and unchanged runs
 *  become a single shared block. */
export function groupBySentence(a: string, b: string): DiffBlock[] {
  const sa = segmentSentences(a).map((s) => s.text + s.trailing)
  const sb = segmentSentences(b).map((s) => s.text + s.trailing)
  const ops = diffTokens(sa, sb)
  // Re-split merged ops back to sentence granularity is unnecessary: pair
  // each delete run with the following insert run as one changed block.
  const blocks: DiffBlock[] = []
  for (let k = 0; k < ops.length; k++) {
    const op = ops[k]
    if (op.kind === 'equal') blocks.push({ a: op.text, b: op.text, changed: false })
    else if (op.kind === 'delete') {
      const next = ops[k + 1]
      if (next && next.kind === 'insert') { blocks.push({ a: op.text, b: next.text, changed: true }); k++ }
      else blocks.push({ a: op.text, b: '', changed: true })
    } else blocks.push({ a: '', b: op.text, changed: true })
  }
  return blocks
}

/** Assemble a merged text from per-block choices ('a' | 'b'); unchanged
 *  blocks are identical on both sides. */
export function mergeBlocks(blocks: DiffBlock[], choice: ('a' | 'b')[]): { text: string; source: 'a' | 'b' | 'both' }[] {
  return blocks
    .map((blk, i) => ({ text: blk.changed ? (choice[i] === 'b' ? blk.b : blk.a) : blk.a,
                        source: (blk.changed ? choice[i] ?? 'a' : 'both') as 'a' | 'b' | 'both' }))
    .filter((x) => x.text.length > 0)
}
