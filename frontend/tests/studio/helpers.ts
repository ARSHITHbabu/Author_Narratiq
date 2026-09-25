import type { Page } from '@playwright/test'

/** Visible, enabled interactive controls on the page (the 8.4 disclosure metric).
 *  Per-chapter binder entries are excluded: they scale with the manuscript, not
 *  the interface, and before Stage 8 they were click-only divs the metric could
 *  not see — excluding them keeps the before/after comparison like for like. */
export async function countVisibleControls(page: Page): Promise<{ count: number; names: string[] }> {
  return page.evaluate(() => {
    const sel = 'button, a[href], input, select, textarea, [role="button"], [role="tab"], [role="menuitem"], [role="link"]'
    const names: string[] = []
    for (const el of Array.from(document.querySelectorAll<HTMLElement>(sel))) {
      if ((el as HTMLButtonElement).disabled) continue
      if (el.closest('[data-binder-item]')) continue
      const r = el.getBoundingClientRect()
      if (r.width === 0 || r.height === 0) continue
      const cs = getComputedStyle(el)
      if (cs.visibility === 'hidden' || cs.display === 'none') continue
      // Hover-revealed controls (opacity 0 on an ancestor) are not "visible" until asked for.
      let faded = false
      for (let a: HTMLElement | null = el; a; a = a.parentElement) if (Number(getComputedStyle(a).opacity) === 0) { faded = true; break }
      if (faded) continue
      if (r.bottom < 0 || r.right < 0 || r.top > innerHeight || r.left > innerWidth) continue
      names.push((el.getAttribute('aria-label') || el.getAttribute('title') || el.textContent || el.tagName).trim().slice(0, 40))
    }
    return { count: names.length, names }
  })
}

/** True when the document scrolls horizontally. */
export async function hasHorizontalScroll(page: Page): Promise<boolean> {
  return page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1)
}
