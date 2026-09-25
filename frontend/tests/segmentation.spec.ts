import { test, expect } from '@playwright/test'
import { segmentSentences, assemble } from '../lib/segmentation'

// P3-02 segmentation contract (spec §24.2): reassembly is byte-exact.

const SAMPLES = [
  'One sentence only',
  'First.  Second!\n\nThird paragraph? Yes…',
  '"Run," she said. He ran.',
  'Trailing space after. ',
  '   Leading whitespace. Then more.',
  'Ellipsis... then a word. Dialogue: "Stop!" he cried.',
  '',
]

for (const s of SAMPLES) {
  test(`assemble(segment(x)) === x for ${JSON.stringify(s).slice(0, 40)}`, () => {
    expect(assemble(segmentSentences(s))).toBe(s)
  })
}

test('offsets point at the sentence text itself', () => {
  const s = 'Alpha one.  Beta two.\nGamma three.'
  for (const seg of segmentSentences(s)) expect(s.slice(seg.start, seg.end)).toBe(seg.text)
})

test('a single sentence yields one segment (nothing left to regenerate once locked)', () => {
  expect(segmentSentences('Just one.').length).toBe(1)
})
