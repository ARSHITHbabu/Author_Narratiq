# Browser-only defect reintroduction — runbook (PREPARED, NOT RUN)

These Phase 2 items are guarded in the traceability matrix only by LIVE browser specs
(`frontend/tests/browser/*.spec.ts`), or (P2-10b) by the mocked-API studio spec. Running them needs a live,
isolated stack (or, for the studio spec, a working Chromium). Neither was available to the sub-agent that
prepared these patches, so **none of them has been run**. Each patch was checked with `git apply --check`
against commit `2b63b51`.

Each patch is one minimal mutation that reintroduces the closed defect in the production code the spec guards.

| Patch | Issue | Production file | Mutation | Spec to run | Expected to fail |
|---|---|---|---|---|---|
| `P2-01-toolbar-escape-dismiss.patch` | P2-1 | `frontend/lib/selectionOwnership.ts` | `resolveToolbarMode` ignores `dismissed`, so Escape no longer hides the toolbar | `tests/browser/selection-toolbar.spec.ts` | `9: Escape closes the menu, then the toolbar; and discards a preview` |
| `P2-11-toolbar-with-sidebar-open.patch` | P2-11 | `frontend/lib/selectionOwnership.ts` | `selectionOwner` no longer gives the selection to the open AI sidebar, so the floating toolbar shows next to it | `tests/browser/selection-toolbar.spec.ts` | `3+4: opening the sidebar suppresses the toolbar…`, `3: with the sidebar already open, a new selection never raises the toolbar`, `visual: the sidebar keeps its own controls clear…` (and probably `11: Focus mode…`) |
| `P2-03-analytics-not-scrollable.patch` | P2-3 | `frontend/app/(dashboard)/projects/[id]/analytics/page.tsx` | `min-h-0 overflow-y-auto` removed from the page's single scroll container, so content below the fold is clipped by StudioShell's `overflow-hidden` | `tests/browser/analytics-scroll.spec.ts` | every `the last analytics section can be scrolled into view at <viewport>` case |
| `P2-06-ocr-upload-hidden-without-chapter.patch` | P2-6 | `frontend/components/ocr/OCRPanel.tsx` | `if (!chapterId) return null`, so the OCR panel shows nothing on a story with no chapters | `tests/browser/ocr-panel.spec.ts` | `…upload control on a story with NO chapters (QA Issue 6)`, `the chapter hint explains what is unavailable…`, `the OCR tab renders without a page error in either story` |
| `P2-07-notes-failure-shown-as-empty.patch` | P2-7 | `frontend/components/notes/NotesPanel.tsx` | a failed notes/cards request is stored as `{data: [], status: 'ready'}`, so the author sees "no notes" instead of an error | `tests/browser/notes-reliability.spec.ts` | `note cards fail, story notes still render…`, `story notes fail, note cards still render`, `both fail: two honest errors, no empty state anywhere` |
| `../patches/P2-10-notes-duplicated-in-plan.patch` (same patch as the run P2-10 item) | P2-10 (studio half) | `frontend/app/(dashboard)/projects/[id]/plan/page.tsx` | Notes mounted again as a Plan section | `tests/studio/navigation.spec.ts` (mocked API, no backend) | `Plan offers Plot Assistant and Pacing only, and points to World for notes` (and possibly `Notes and the Idea Shelf have one home: World`) |

Supplementary evidence that *was* run: P2-1 and P2-11 are also covered by a deterministic unit spec that the
traceability table doesn't list, `frontend/tests/selection-ownership.spec.ts`. The same two mutations were run
against it (see `../README.md`, rows `P2-01u` / `P2-11u`).

## Why the studio spec was not run here

`npx playwright install chromium` succeeded, but the headless shell won't start on this pod:
`chrome-headless-shell: error while loading shared libraries: libnspr4.so` (log:
`../raw/studio-navigation-baseline-attempt.log`). Installing system packages (`playwright install-deps`) would
change the shared pod, which was out of scope for this sub-agent. With a working Chromium
(`PW_CHROMIUM_PATH=…`), the studio spec needs no backend at all.

## Procedure (one patch at a time, in a disposable worktree, never in the main checkout)

```bash
# 0. a clean worktree at the commit under test
git worktree add /tmp/defect-wt 2b63b51 && cd /tmp/defect-wt/frontend && npm ci

# 1. baseline: the spec must pass on the unmodified tree (isolated stack as in
#    docs/testing/stage-09-regression-results.md: backend :8100 on narratiq_test with raised RATE_LIMIT_*,
#    frontend built with NEXT_DIST_DIR=.next-e2e NEXT_PUBLIC_API_URL=http://localhost:8100 and served on :3200,
#    fixtures from backend/scripts/seed_browser_fixtures.py)
E2E_BASE_URL=http://localhost:3200 E2E_API_URL=http://localhost:8100 \
E2E_EMAIL=… E2E_PASSWORD=… E2E_STORY_ID=… [E2E_EMPTY_STORY_ID=…] \
  npx playwright test --project=browser --workers=1 tests/browser/<spec>.spec.ts

# 2. reintroduce the defect, then REBUILD/RESTART the :3200 frontend so it serves the mutated code
git -C /tmp/defect-wt apply <path>/browser-prepared/<patch>.patch
#    (rebuild: NEXT_DIST_DIR=.next-e2e NEXT_PUBLIC_API_URL=http://localhost:8100 npx next build && npx next start -p 3200)

# 3. run the same spec — expect the tests in the table above to FAIL; record ids and the summary line

# 4. restore, check the tree is clean, rebuild, re-run — expect PASS
git -C /tmp/defect-wt checkout -- <file> && git -C /tmp/defect-wt diff --quiet && echo clean
```

Studio spec (P2-10b), no backend needed:

```bash
cd /tmp/defect-wt/frontend
STUDIO_PORT=3177 npx playwright test -c playwright.studio.config.ts navigation          # baseline: pass
git -C /tmp/defect-wt apply <path>/patches/P2-10-notes-duplicated-in-plan.patch
STUDIO_PORT=3177 npx playwright test -c playwright.studio.config.ts navigation          # expect red (rebuilds .next-studio)
git -C /tmp/defect-wt checkout -- "frontend/app/(dashboard)/projects/[id]/plan/page.tsx"
STUDIO_PORT=3177 npx playwright test -c playwright.studio.config.ts navigation          # pass again
```

Note: Playwright writes the tracked file `frontend/test-results/.last-run.json`. Revert it
(`git checkout -- frontend/test-results/.last-run.json`) or pass `--output=<scratch dir>` before the
`git diff --quiet` check. The studio build also rewrites the tracked `frontend/next-env.d.ts`; revert that too.
