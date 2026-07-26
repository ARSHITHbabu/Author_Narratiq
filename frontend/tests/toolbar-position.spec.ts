import { test, expect } from '@playwright/test'
import {
  clampToolbarPosition,
  defaultToolbarPosition,
  menuOpensUpward,
} from '../lib/toolbarPosition'

// Floating-toolbar geometry (QA Issue 1 — "the toolbar blocks editor controls").
// Pure logic; the DOM behaviour it drives is covered by the browser project.

const BOX = { width: 400, height: 40 }
const COLUMN = { width: 1000, height: 700 }

test('the default position is the bottom centre — never the top, where the formatting bar and Save live', () => {
  const p = defaultToolbarPosition(BOX, COLUMN)
  expect(p.x).toBe(300)
  expect(p.y).toBe(700 - 40 - 12)
  expect(p.y).toBeGreaterThan(COLUMN.height / 2)
})

test('a dragged position inside the column is kept exactly', () => {
  expect(clampToolbarPosition({ x: 120, y: 300 }, BOX, COLUMN)).toEqual({ x: 120, y: 300 })
})

test('a position past any edge is pulled back inside', () => {
  expect(clampToolbarPosition({ x: -500, y: -500 }, BOX, COLUMN)).toEqual({ x: 12, y: 12 })
  expect(clampToolbarPosition({ x: 99999, y: 99999 }, BOX, COLUMN))
    .toEqual({ x: 1000 - 400 - 12, y: 700 - 40 - 12 })
})

test('a position remembered on a large window is recovered on a small one', () => {
  const remembered = { x: 560, y: 640 }        // valid in a 1000×700 column
  const small = { width: 500, height: 300 }    // the column after a resize / sidebar open
  const recovered = clampToolbarPosition(remembered, BOX, small)
  expect(recovered.x).toBeLessThanOrEqual(small.width - BOX.width - 12)
  expect(recovered.y).toBeLessThanOrEqual(small.height - BOX.height - 12)
  expect(recovered.x).toBeGreaterThanOrEqual(12)
  expect(recovered.y).toBeGreaterThanOrEqual(12)
})

test('shrinking then restoring the window returns the toolbar to where the author put it', () => {
  const remembered = { x: 560, y: 640 }
  expect(clampToolbarPosition(remembered, BOX, COLUMN)).toEqual(remembered)          // valid here
  clampToolbarPosition(remembered, BOX, { width: 500, height: 300 })  // clamped for display only
  expect(clampToolbarPosition(remembered, BOX, COLUMN)).toEqual(remembered)
})

test('a column narrower than the toolbar still yields a visible, on-screen position', () => {
  const tiny = { width: 200, height: 100 }
  const p = clampToolbarPosition({ x: 0, y: 0 }, BOX, tiny)
  expect(p).toEqual({ x: 12, y: 12 })
  const d = defaultToolbarPosition(BOX, tiny)
  expect(d.x).toBeGreaterThanOrEqual(0)
  expect(d.y).toBeGreaterThanOrEqual(0)
})

test('clamping is idempotent — repeated resizes cannot drift the toolbar', () => {
  const once = clampToolbarPosition({ x: 5000, y: 5000 }, BOX, COLUMN)
  const twice = clampToolbarPosition(once, BOX, COLUMN)
  expect(twice).toEqual(once)
})

test('menus open upward from the bottom rest and downward once dragged high', () => {
  expect(menuOpensUpward({ x: 300, y: 648 }, COLUMN)).toBe(true)
  expect(menuOpensUpward({ x: 300, y: 40 }, COLUMN)).toBe(false)
})

test('menu direction defaults to upward before the toolbar has been measured', () => {
  expect(menuOpensUpward(null, COLUMN)).toBe(true)
  expect(menuOpensUpward({ x: 0, y: 0 }, null)).toBe(true)
})
