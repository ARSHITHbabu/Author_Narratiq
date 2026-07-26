// Floating-toolbar geometry — where a draggable overlay may sit inside a panel.
//
// Split out of lib/selectionOwnership.ts: that module answers "which surface owns
// the selection", this one answers "where does a box rest inside a column". They
// are used together by SelectionToolbar but neither needs the other, and geometry
// is reusable by any future floating surface.
//
// Pure and framework-free so it is unit-testable without a browser.

export interface Point { x: number; y: number }
export interface Size { width: number; height: number }

/** Gap kept between the toolbar and the edges of its column. */
export const TOOLBAR_INSET = 12

/** Keeps the box fully inside its column.
 *  Also the recovery path after a resize: a position chosen in a large column is
 *  clamped back into view in a small one, so the box can never be stranded. */
export function clampToolbarPosition(
  pos: Point,
  size: Size,
  bounds: Size,
  inset: number = TOOLBAR_INSET,
): Point {
  const maxX = Math.max(inset, bounds.width - size.width - inset)
  const maxY = Math.max(inset, bounds.height - size.height - inset)
  return {
    x: Math.min(Math.max(pos.x, inset), maxX),
    y: Math.min(Math.max(pos.y, inset), maxY),
  }
}

/** Default resting place: bottom-centre of the column.
 *  Deliberately NOT the top — that is where the formatting bar and the Save
 *  control live, and covering them is QA Issue 1. */
export function defaultToolbarPosition(
  size: Size,
  bounds: Size,
  inset: number = TOOLBAR_INSET,
): Point {
  return clampToolbarPosition(
    { x: (bounds.width - size.width) / 2, y: bounds.height - size.height - inset },
    size,
    bounds,
    inset,
  )
}

/** Dropdowns open away from the nearer edge: upward from the bottom rest,
 *  downward once the box has been dragged into the upper half of the column. */
export function menuOpensUpward(pos: Point | null, bounds: Size | null): boolean {
  if (!pos || !bounds) return true
  return pos.y > bounds.height / 2
}
