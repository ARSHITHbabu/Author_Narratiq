import { test, expect } from '@playwright/test'
import { tokenize, diffWords, stats, groupBySentence, mergeBlocks, MAX_DIFF_TOKENS } from '../lib/diff'

// P3-04 — client-side comparison (spec §23). Pure functions, no browser.

test('tokenize reassembles exactly, whitespace attached to the preceding word', () => {
  const s = 'The  corridor breathed.\nElara  counted four doors. '
  expect(tokenize(s).join('')).toBe(s)
})

test('word-level diff: accurate highlighting and counts', () => {
  const { ops, sentenceLevel } = diffWords('The corridor was long and dark.', 'The corridor breathed, long and dark.')
  expect(sentenceLevel).toBe(false)
  expect(ops.filter((o) => o.kind === 'delete').map((o) => o.text.trim())).toEqual(['was'])
  expect(ops.filter((o) => o.kind === 'insert').map((o) => o.text.trim())).toEqual(['breathed,'])
  expect(stats(ops)).toEqual({ added: 1, removed: 1, unchanged: 5 })
})

test('whitespace-only changes never render as diffs', () => {
  const { ops } = diffWords('Four doors waited.', 'Four   doors  waited.')
  expect(ops.every((o) => o.kind === 'equal')).toBe(true)
})

test('identical texts produce no changed blocks', () => {
  const t = 'One. Two. Three.'
  expect(groupBySentence(t, t).some((b) => b.changed)).toBe(false)
})

test('MAX_DIFF_TOKENS falls back to sentence-level diffing', () => {
  const big = 'word '.repeat(MAX_DIFF_TOKENS + 5)
  expect(diffWords(big, big + 'extra.').sentenceLevel).toBe(true)
})

test('per-block merge produces exactly the chosen blocks', () => {
  const a = 'The corridor breathed. Elara counted four doors. She trusted none.'
  const b = 'The corridor breathed. Kira counted five doors. She trusted none.'
  const blocks = groupBySentence(a, b)
  const changedIdx = blocks.findIndex((x) => x.changed)
  expect(changedIdx).toBeGreaterThan(-1)
  const pickB = blocks.map((_, i) => (i === changedIdx ? 'b' : 'a')) as ('a' | 'b')[]
  expect(mergeBlocks(blocks, pickB).map((x) => x.text).join('')).toBe(b)
  const pickA = blocks.map(() => 'a') as ('a' | 'b')[]
  expect(mergeBlocks(blocks, pickA).map((x) => x.text).join('')).toBe(a)
  expect(mergeBlocks(blocks, pickB).find((x) => x.source === 'b')?.text).toContain('Kira')
})
