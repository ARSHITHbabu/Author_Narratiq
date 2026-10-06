// Stage 12.3 agent review (HR-11) — with no selection, Suggestions sent the first
// 2000 characters of the chapter cut mid-word ("…preying o"), and the model then
// reported "the excerpt ends mid-sentence", a problem that is not in the manuscript.
// The text sent is now cut at the last whole sentence. Pure function, no browser.
import { test, expect } from '@playwright/test'
import { SUGGESTION_CHARS, wholeSentences } from '../lib/suggestionText'

const SENT = 'The tide turned at the harbour wall and the gulls rose over Greymouth. '

test('a long chapter is cut at the last whole sentence inside the limit', () => {
  const chapter = SENT.repeat(40) + 'Smugglers were preying on unsuspecting sailors.'
  const out = wholeSentences(chapter, SUGGESTION_CHARS)
  expect(out.length).toBeLessThanOrEqual(SUGGESTION_CHARS)
  expect(out.endsWith('Greymouth.')).toBe(true)
  expect(chapter.startsWith(out)).toBe(true)
})

test('the live HR-11 cut point no longer ends mid-word', () => {
  const chapter = 'x'.repeat(10) + '. ' + 'a'.repeat(1980) + ' preying on unsuspecting sailors.'
  const out = wholeSentences(chapter, SUGGESTION_CHARS)
  expect(out).toBe('x'.repeat(10) + '.')
})

test('closing quotes stay with their sentence', () => {
  const line = '"We row at slack water," said Ada. "Bring the lamp!" '
  const out = wholeSentences(line.repeat(60), 500)
  expect(out.endsWith('"Bring the lamp!"')).toBe(true)
})

test('short text and selections under the limit are sent whole', () => {
  expect(wholeSentences('  A short chapter with no full stop  ', SUGGESTION_CHARS)).toBe('A short chapter with no full stop')
})

test('text with no sentence end falls back to a word boundary, never mid-word', () => {
  const out = wholeSentences('word '.repeat(600), SUGGESTION_CHARS)
  expect(out.endsWith('word')).toBe(true)
  expect(out.length).toBeLessThanOrEqual(SUGGESTION_CHARS)
})
