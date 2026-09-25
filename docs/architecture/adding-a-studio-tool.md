# Adding a tool to the Studio

Stage 8 (task 8.7). The Studio is driven by four registries. A new tool is a row
in one or two of them. It should never need changes to the shell, the rail, the
routing or the layout. If it does, that is a design problem to raise before
writing code.

| Registry | File | Decides |
|---|---|---|
| Workspaces | `frontend/lib/registries/workspaces.ts` | The rail entries and route segments (`/projects/[id]/<segment>`) |
| Panels | `frontend/lib/registries/panels.tsx` | Analyze-style tools: cards on the dashboard that open full width |
| Actions | `frontend/lib/registries/actions.ts` | Command Palette entries (Ctrl/⌘K) |
| Tool Homes | `frontend/lib/registries/toolHomes.ts` | The one place each tool lives. Tests and deep links read it |

**Rule: one tool, one home.** Every author-facing tool has exactly one row in
`TOOL_HOMES`. A second place to *manage* the same tool is a regression. A
read-only contextual view elsewhere is allowed only as an `alsoShownIn` entry
with a written reason (see the Idea Shelf row, decision D10).

## Recipes

### An analysis (most new tools)

1. Build the component under `frontend/components/...`. It receives the props
   listed in `needs` (`storyId`, `chapterId`, `characterId`).
2. Add a `dynamic(() => import(...), { ssr: false })` constant and a `PANELS`
   row with `workspace: 'analyze'`, `surface: 'page'`, a title, an icon and a
   one-line `blurb`.
3. Add a `TOOL_HOMES` row with `workspace: 'analyze'` and `section: <panel id>`.
4. Optional: a `Run` action in `ACTIONS` using `c.runAnalysis('<panel id>')`.

Nothing else. The Analyze dashboard renders a card per panel, opens it full
width, moves focus to its heading and returns focus to the card on close.

### A section in Plan or World

1. Add the section to `WORKSPACE_SECTIONS` in `toolHomes.ts` **and** to the
   `SECTIONS` list at the top of the workspace page (the page list adds the
   icon). The `tool-homes` unit test fails if they disagree.
2. Render the component inside the page's `<SectionPanel>` behind
   `section === '<id>'`. Use `next/dynamic` so it stays out of the other
   sections' bundles.
3. Add a `TOOL_HOMES` row and a `Navigate` action using
   `c.go('<workspace>', { section: '<id>' })`.

`SectionTabs` gives you the ARIA tablist, arrow/Home/End keys, the `?section=`
deep link and the per-story "last section" memory without further work.

### A new workspace

Add a `WORKSPACES` row and a page at `app/(dashboard)/projects/[id]/<segment>/page.tsx`.
The rail, `aria-current`, the palette's Navigate group and workspace memory pick
it up automatically. Extra routes owned by the workspace go in `childSegments`.
Adding a workspace is a product decision: check with the design owner first.

### A Write-sidecar AI tool

Add it to the right group (`Rewrite`, `Generate`, or `Versions` for Phase 3) in
`GROUPS` in `components/ai-tools/AIToolsSidebar.tsx`. Do not add a new top-level
tab. Add or extend the `TOOL_HOMES` row (`section: 'sidecar'`).

### Phase 3 tools

Mark the `TOOL_HOMES` row and any action `phase3: true`, and gate the UI on
`NEXT_PUBLIC_P3_ENABLED`. The P3-off build must still pass (see below).

## Test obligations

| Change | Must pass |
|---|---|
| Any registry row | `npx playwright test --project=unit` (includes `tests/tool-homes.spec.ts`) |
| Anything visible | Studio suite: `npm run test:studio`, including `a11y.spec.ts` (zero serious/critical axe findings) and `responsive.spec.ts` (no horizontal scroll at 768–1920 wide) |
| A Phase 3 tool | `STUDIO_VARIANT=p3-off` run of `tests/studio/variants.spec.ts` |
| Anything a live browser spec clicks | Update the spec in `tests/browser/` in the same commit and check `npx playwright test --project=browser --list` |
| A new control in Write | Keep `modes.spec.ts`'s control-count ceilings. If the tool adds visible controls, put them behind a menu or disclosure rather than raising the ceiling |

The studio suite runs against a mocked API (`tests/studio/mockApi.ts`); add
mocks for the new endpoints there. Calls with no mock are recorded in
`log.unmatched`; assert it is empty in the new tool's test.

## The scalability check (mock tool)

`NEXT_PUBLIC_E2E_MOCK_TOOL=true` builds add a test-only "Mock Tool" through the
analysis recipe above: one `PANELS` row and one `TOOL_HOMES` row, nothing else.
`tests/studio/variants.spec.ts` then checks:

- **mock-tool build:** the tool appears in Analyze, opens full width, and the
  rail and existing tools don't move; no horizontal scroll.
- **default build:** the marker string from `MockToolPanel.tsx` appears nowhere
  in the build output, so the test tool can never ship.
- **p3-off build:** Phase 3 surfaces disappear and every other home still works.

`next.config.js` always defines `NEXT_PUBLIC_E2E_MOCK_TOOL` (as `'true'` or
`'false'`). That is what lets the build drop the branch: an undefined
`NEXT_PUBLIC_` variable is not inlined, and the dead branch would be bundled.

```bash
cd frontend
npm run test:studio            # default build (builds first unless STUDIO_SKIP_BUILD=1)
npm run test:studio:variants   # mock-tool and p3-off builds
```
