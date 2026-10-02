// Stage 12 remediation A9 — the editor's exact-search matcher (lib/searchMatch.ts).
// Pure functions over a real TipTap document built from the editor's own
// extensions (no browser). The browser half, against the same HTML the backend
// tests use, is tests/studio/search-consistency.spec.ts.
import { test, expect } from '@playwright/test'
import { getSchema } from '@tiptap/core'
import StarterKit from '@tiptap/starter-kit'
import Underline from '@tiptap/extension-underline'
import Highlight from '@tiptap/extension-highlight'
import { findMatchRanges, buildPattern } from '../lib/searchMatch'

const schema = getSchema([StarterKit, Underline, Highlight])
const t = (text: string, marks: string[] = []) => ({ type: 'text', text, marks: marks.map((m) => ({ type: m })) })
const para = (...content: any[]) => ({ type: 'paragraph', content })
const docOf = (...blocks: any[]) => schema.nodeFromJSON({ type: 'doc', content: blocks })

function hits(doc: any, q: string, cs = false, ww = false) {
  return findMatchRanges(doc, q, cs, ww).map((r) => doc.textBetween(r.from, r.to, '', ''))
}

test('a match across bold is found and maps to the right document range', () => {
  const doc = docOf(para(t('Dev'), t('ika', ['bold']), t(' met Devika.')))
  expect(hits(doc, 'Devika')).toEqual(['Devika', 'Devika'])
})

test('nested marks and underline/highlight join with no separator', () => {
  const doc = docOf(para(t('the '), t('old ', ['bold']), t('cas', ['bold', 'italic']), t('tle stands')),
    para(t('Mar', ['underline']), t('a', ['highlight']), t(' Coste')))
  expect(hits(doc, 'old castle')).toEqual(['old castle'])
  expect(hits(doc, 'Mara', true, true)).toEqual(['Mara'])
})

test('matches never cross paragraphs or hard line breaks', () => {
  const doc = docOf(para(t('end here.')), para(t('Next one')),
    para(t('line one'), { type: 'hardBreak' }, t('two lines')))
  expect(hits(doc, 'here. Next')).toEqual([])
  expect(hits(doc, 'one two')).toEqual([])
  expect(hits(doc, 'one')).toEqual(['one', 'one'])   // "Next one" and "line one"
})

test('headings, list items and blockquotes are each searched', () => {
  const doc = docOf({ type: 'heading', attrs: { level: 2 }, content: [t('The Harbour')] },
    { type: 'bulletList', content: [{ type: 'listItem', content: [para(t('harbour lights'))] }] },
    { type: 'blockquote', content: [para(t('A harbour.'))] })
  expect(hits(doc, 'harbour', false, true)).toHaveLength(3)
})

test('Unicode whole word: café and Devanagari', () => {
  expect(hits(docOf(para(t('Café, cafés and the café.'))), 'café', false, true)).toEqual(['Café', 'café'])
  expect(hits(docOf(para(t('हिंदी भाषा हिंदीभाषा हिंदी'))), 'हिंदी', false, true)).toHaveLength(2)
  expect(hits(docOf(para(t('ÉLÉONORE and éléonore'))), 'éléonore')).toHaveLength(2)
})

test('whole word off by default matches partial words; on excludes them', () => {
  const doc = docOf(para(t('wolf wolfhound wolf')))
  expect(hits(doc, 'wolf')).toHaveLength(3)
  expect(hits(doc, 'wolf', false, true)).toHaveLength(2)
})

test('case sensitivity, special characters and a distinct non-breaking space', () => {
  expect(hits(docOf(para(t('Rook rook ROOK'))), 'Rook', true)).toEqual(['Rook'])
  for (const q of ['$5.00', '(approx.)', 'fair?', '[yes]', 'a+b', '^c', '\\', '*']) {
    expect(() => buildPattern(q, false, false)).not.toThrow()
  }
  expect(hits(docOf(para(t('Cost: $5.00 (approx.) fair?'))), '(approx.)')).toEqual(['(approx.)'])
  expect(hits(docOf(para(t('Mr. Vance and Mr. Vance'))), 'Mr. Vance')).toHaveLength(1)
})

test('typed runs of spaces collapse like the saved chapter does', () => {
  expect(hits(docOf(para(t('two  spaces here'))), 'two spaces here')).toEqual(['two  spaces here'])
})

test('empty or whitespace-only queries match nothing', () => {
  const doc = docOf(para(t('anything')))
  expect(findMatchRanges(doc, '', false, false)).toEqual([])
  expect(findMatchRanges(doc, '   ', false, false)).toEqual([])
})
