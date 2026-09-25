# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: tests/browser/selection-toolbar.spec.ts >> 9: Escape closes the menu, then the toolbar; and discards a preview
- Location: tests/browser/selection-toolbar.spec.ts:221:5

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByRole('toolbar', { name: 'AI actions for the selected text' })
Expected: visible
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 5000ms
  - waiting for getByRole('toolbar', { name: 'AI actions for the selected text' })

```

```yaml
- banner:
  - button "Toggle rail":
    - img
  - button "NarratIQ / S7 browser fixture B":
    - text: NarratIQ / S7 browser fixture B
    - img
  - text: › Write
  - button "⌘K":
    - img
    - text: ⌘K
  - button "Voice assistant":
    - img
  - button "Activity timeline":
    - img
  - button "User menu": S
- navigation:
  - button "Write":
    - img
    - text: Write
  - button "Plan":
    - img
    - text: Plan
  - button "Characters":
    - img
    - text: Characters
  - button "World":
    - img
    - text: World
  - button "Analyze":
    - img
    - text: Analyze
  - button "Assistant":
    - img
    - text: Assistant
  - button "Publish":
    - img
    - text: Publish
  - button "Library":
    - img
    - text: Library
- main:
  - img
  - text: Chapters
  - button "Add chapter":
    - img
  - text: Chapter 1 The lighthouse 37 words
  - button:
    - img
  - button:
    - img
  - text: Chapter 2 The harbour 13 words
  - button:
    - img
  - button:
    - img
  - separator
  - button "Bold":
    - img
  - button "Italic":
    - img
  - button "Underline":
    - img
  - button "Strikethrough":
    - img
  - button "Highlight":
    - img
  - button "Heading 1":
    - img
  - button "Heading 2":
    - img
  - button "Blockquote":
    - img
  - button "Bullet List":
    - img
  - button "Ordered List":
    - img
  - button "Left":
    - img
  - button "Center":
    - img
  - button "Right":
    - img
  - button "Undo":
    - img
  - button "Redo":
    - img
  - button "Save":
    - img
    - text: Save
  - heading "Chapter 1 — The lighthouse" [level=2]
  - paragraph: The lighthouse had been dark for a week. Nobody in the village could say why.
  - paragraph: On the eighth night the keeper's daughter climbed the stairs with a lamp of her own, and the harbour watched her go.
  - text: "Ch 1: The lighthouse · 37 words · Story 50"
  - button "AI sidecar (⌘\\\\)":
    - img
  - button "Typewriter":
    - img
  - button "Focus (⌘.)":
    - img
  - button "Zen mode":
    - img
  - button "Fullscreen":
    - img
- region "Notifications alt+T"
- alert
```

# Test source

```ts
  134 | 
  135 | // ── 3, 4, 5: sidebar deference ──────────────────────────────────────────────
  136 | 
  137 | test('3+4: opening the sidebar suppresses the toolbar, closing it gives the selection back', async ({ page }) => {
  138 |   await selectLine(page)
  139 |   await expect(toolbar(page)).toBeVisible()
  140 | 
  141 |   await sidecarToggle(page).click()
  142 |   await expect(sidecarPanel(page)).toBeVisible()
  143 |   await expect(toolbar(page)).toHaveCount(0)
  144 |   // The selection survived the handover — the sidebar knows about it.
  145 |   await expect(page.getByText(/words selected — AI will work on this/)).toBeVisible()
  146 | 
  147 |   await page.getByTitle(/^Close/).click()
  148 |   await expect(sidecarPanel(page)).toHaveCount(0)
  149 |   await expect(toolbar(page)).toBeVisible()
  150 | })
  151 | 
  152 | test('3: with the sidebar already open, a new selection never raises the toolbar', async ({ page }) => {
  153 |   await sidecarToggle(page).click()
  154 |   await expect(sidecarPanel(page)).toBeVisible()
  155 |   await selectLine(page)
  156 |   await expect(page.getByText(/words selected — AI will work on this/)).toBeVisible()
  157 |   await expect(toolbar(page)).toHaveCount(0)
  158 | })
  159 | 
  160 | test('5: the sidebar scope updates when the selection changes', async ({ page }) => {
  161 |   await sidecarToggle(page).click()
  162 |   await expect(page.getByText('No selection — using full chapter')).toBeVisible()
  163 | 
  164 |   await selectLine(page)
  165 |   const firstScope = await page.getByText(/words selected/).innerText()
  166 | 
  167 |   await editorArea(page).click()
  168 |   await page.keyboard.press('ControlOrMeta+a')
  169 |   await expect
  170 |     .poll(async () => page.getByText(/words selected/).innerText(), { timeout: 10_000 })
  171 |     .not.toBe(firstScope)
  172 | })
  173 | 
  174 | // ── 6, 7, 8: preview lifecycle and manuscript safety ────────────────────────
  175 | 
  176 | test('6: a pending preview stays reviewable when the sidebar opens', async ({ page }) => {
  177 |   await selectLine(page)
  178 |   await runTransform(page, 'Refine', 'Grammar')
  179 |   await expect(previewCard(page)).toBeVisible({ timeout: AI_TIMEOUT })
  180 | 
  181 |   await sidecarToggle(page).click()
  182 |   await expect(sidecarPanel(page)).toBeVisible()
  183 |   await expect(previewCard(page)).toBeVisible()      // AI output survives the panel
  184 |   await expect(toolbar(page)).toHaveCount(0)          // but the duplicate controls do not
  185 | })
  186 | 
  187 | test('7: changing chapter invalidates a pending preview', async ({ page }) => {
  188 |   await selectLine(page)
  189 |   await runTransform(page, 'Refine', 'Grammar')
  190 |   await expect(previewCard(page)).toBeVisible({ timeout: AI_TIMEOUT })
  191 | 
  192 |   await openChapter(page, 2)
  193 |   await expect(previewCard(page)).toHaveCount(0)
  194 | })
  195 | 
  196 | test('8: a generation finishing after a chapter switch cannot apply anywhere', async ({ page }) => {
  197 |   await openChapter(page, 2)
  198 |   const chapterTwoBefore = await editorArea(page).innerText()
  199 |   await openChapter(page, 1)
  200 | 
  201 |   // Hold the transform response open so the chapter switch is guaranteed to land
  202 |   // while the generation is still in flight — the case being verified.
  203 |   await page.route('**/api/ai/**', async (route) => {
  204 |     await new Promise((r) => setTimeout(r, 6000))
  205 |     await route.continue()
  206 |   })
  207 | 
  208 |   await selectLine(page)
  209 |   await runTransform(page, 'Refine', 'Grammar')
  210 |   await page.getByText('Chapter 2', { exact: true }).click()   // leave while it generates
  211 |   await expect(page.getByRole('heading', { name: /Chapter 2 —/ })).toBeVisible()
  212 | 
  213 |   await expect(page.getByText('You moved to another chapter, so that suggestion was discarded.'))
  214 |     .toBeVisible({ timeout: AI_TIMEOUT })
  215 |   await expect(previewCard(page)).toHaveCount(0)
  216 |   expect(await editorArea(page).innerText()).toBe(chapterTwoBefore)
  217 | })
  218 | 
  219 | // ── 9: Escape order ─────────────────────────────────────────────────────────
  220 | 
  221 | test('9: Escape closes the menu, then the toolbar; and discards a preview', async ({ page }) => {
  222 |   await selectLine(page)
  223 |   await toolbar(page).getByRole('button', { name: /Tone/i }).first().click()
  224 |   await expect(page.getByRole('menu')).toBeVisible()
  225 | 
  226 |   await page.keyboard.press('Escape')
  227 |   await expect(page.getByRole('menu')).toHaveCount(0)
  228 |   await expect(toolbar(page)).toBeVisible()            // menu only — toolbar stays
  229 | 
  230 |   await page.keyboard.press('Escape')
  231 |   await expect(toolbar(page)).toHaveCount(0)           // now the toolbar
  232 | 
  233 |   await selectLine(page)                                // a new selection brings it back
> 234 |   await expect(toolbar(page)).toBeVisible()
      |                               ^ Error: expect(locator).toBeVisible() failed
  235 |   await runTransform(page, 'Refine', 'Grammar')
  236 |   await expect(previewCard(page)).toBeVisible({ timeout: AI_TIMEOUT })
  237 |   await page.keyboard.press('Escape')
  238 |   await expect(previewCard(page)).toHaveCount(0)
  239 | })
  240 | 
  241 | // ── 11: Focus and Zen preserve the ownership rule ───────────────────────────
  242 | 
  243 | test('11: Focus mode hides the sidebar, so the toolbar takes the selection back', async ({ page }) => {
  244 |   await selectLine(page)
  245 |   await sidecarToggle(page).click()
  246 |   await expect(toolbar(page)).toHaveCount(0)
  247 | 
  248 |   await page.keyboard.press('ControlOrMeta+.')          // Focus mode, keyboard only
  249 |   await expect(sidecarPanel(page)).toHaveCount(0)
  250 |   await expect(toolbar(page)).toBeVisible()
  251 | 
  252 |   await page.keyboard.press('ControlOrMeta+.')          // back out
  253 |   await expect(sidecarPanel(page)).toBeVisible()
  254 |   await expect(toolbar(page)).toHaveCount(0)
  255 | })
  256 | 
  257 | test('11: in Zen mode the toolbar still owns a selection', async ({ page }) => {
  258 |   await page.getByTitle('Zen mode').click()
  259 |   await expect(page.getByText('Exit Zen (Esc)')).toBeVisible()
  260 |   // Entering a mode re-lays out the panel group and the editor reloads its content.
  261 |   // That reload can land just after a selection and collapse it — a pre-existing
  262 |   // behaviour, not something the ownership rule controls. An author would simply
  263 |   // select again, so the test does too, and asserts that selecting in Zen mode
  264 |   // raises the toolbar.
  265 |   await expect(editorArea(page)).toContainText('The lighthouse')
  266 |   await expect.poll(async () => {
  267 |     await selectLine(page)
  268 |     return toolbar(page).count()
  269 |   }, { timeout: 15_000 }).toBeGreaterThan(0)
  270 | })
  271 | 
  272 | // ── 12, 13, 14: geometry, dragging, menu direction ──────────────────────────
  273 | 
  274 | test('12: resizing keeps the toolbar inside the editor column', async ({ page }) => {
  275 |   await selectLine(page)
  276 |   await expect(toolbar(page)).toBeVisible()
  277 | 
  278 |   for (const size of [{ width: 1280, height: 720 }, { width: 1024, height: 700 }, { width: 900, height: 620 }]) {
  279 |     await page.setViewportSize(size)
  280 |     await page.waitForTimeout(300)
  281 |     const bar = await boxOf(toolbar(page))
  282 |     const column = await boxOf(page.locator('.ProseMirror').locator('xpath=ancestor::div[contains(@class,"relative")][1]'))
  283 |     expect(bar.x).toBeGreaterThanOrEqual(column.x - 1)
  284 |     expect(bar.x + bar.width).toBeLessThanOrEqual(column.x + column.width + 1)
  285 |     expect(bar.y + bar.height).toBeLessThanOrEqual(size.height + 1)
  286 |   }
  287 | })
  288 | 
  289 | test('13+14: dragging keeps the selection and flips the menu direction', async ({ page }) => {
  290 |   await selectLine(page)
  291 |   const handle = page.getByTestId('toolbar-drag-handle').first()
  292 |   const before = await boxOf(toolbar(page))
  293 | 
  294 |   // Default rest is low in the column, so menus open upward.
  295 |   await toolbar(page).getByRole('button', { name: /Tone/i }).first().click()
  296 |   const buttonBox = await boxOf(toolbar(page).getByRole('button', { name: /Tone/i }).first())
  297 |   const menuUp = await boxOf(page.getByRole('menu'))
  298 |   expect(menuUp.y).toBeLessThan(buttonBox.y)
  299 |   await page.keyboard.press('Escape')
  300 | 
  301 |   const h = await boxOf(handle)
  302 |   await page.mouse.move(h.x + h.width / 2, h.y + h.height / 2)
  303 |   await page.mouse.down()
  304 |   await page.mouse.move(h.x + h.width / 2, 120, { steps: 12 })
  305 |   await page.mouse.up()
  306 | 
  307 |   // 13: the drag did not clear the editor selection — the toolbar is still up.
  308 |   await expect(toolbar(page)).toBeVisible()
  309 |   const after = await boxOf(toolbar(page))
  310 |   expect(after.y).toBeLessThan(before.y)
  311 | 
  312 |   // 14: high in the column, menus now open downward.
  313 |   await toolbar(page).getByRole('button', { name: /Tone/i }).first().click()
  314 |   const buttonBox2 = await boxOf(toolbar(page).getByRole('button', { name: /Tone/i }).first())
  315 |   const menuDown = await boxOf(page.getByRole('menu'))
  316 |   expect(menuDown.y).toBeGreaterThan(buttonBox2.y)
  317 | 
  318 |   // Double-clicking the handle returns it to the default rest.
  319 |   await page.keyboard.press('Escape')
  320 |   await handle.dblclick()
  321 |   const reset = await boxOf(toolbar(page))
  322 |   expect(Math.abs(reset.y - before.y)).toBeLessThan(4)
  323 | })
  324 | 
  325 | // ── Visual verification: the toolbar never covers editor controls ───────────
  326 | 
  327 | const VIEWPORTS = [
  328 |   { name: '1366x768 (reported QA resolution)', width: 1366, height: 768 },
  329 |   { name: '1180x720 (narrower desktop)', width: 1180, height: 720 },
  330 |   { name: '1024x640 (minimum supported)', width: 1024, height: 640 },
  331 | ]
  332 | 
  333 | for (const vp of VIEWPORTS) {
  334 |   test(`visual: no overlap with editor controls at ${vp.name}`, async ({ page }, testInfo) => {
```