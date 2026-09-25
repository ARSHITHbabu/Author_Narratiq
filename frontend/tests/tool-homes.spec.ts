// Stage 8.1 / 8.8 — every tool has exactly one home (Phase 2 Issue 10).
// Pure logic: reads the Tool Homes table and the workspace sources, no browser.
import { test, expect } from '@playwright/test'
import { readFileSync } from 'fs'
import { join } from 'path'
import { TOOL_HOMES, WORKSPACE_SECTIONS, visibleToolHomes } from '../lib/registries/toolHomes'

const root = join(__dirname, '..')
const src = (p: string) => readFileSync(join(root, p), 'utf8')
const sectionIds = (p: string) => [...src(p).matchAll(/\{ id: '([a-z_]+)', label: '[^']+', icon:/g)].map((m) => m[1])

test('tool ids are unique — one row, one home', () => {
  const ids = TOOL_HOMES.map((t) => t.id)
  expect(new Set(ids).size).toBe(ids.length)
})

test('Plan and World pages offer exactly the registered sections', () => {
  expect(sectionIds('app/(dashboard)/projects/[id]/plan/page.tsx')).toEqual(WORKSPACE_SECTIONS.plan!.map((s) => s.id))
  expect(sectionIds('app/(dashboard)/projects/[id]/world/page.tsx')).toEqual(WORKSPACE_SECTIONS.world!.map((s) => s.id))
})

test('Notes and Narrative Threads are no longer duplicated (Phase 2 Issue 10)', () => {
  const plan = src('app/(dashboard)/projects/[id]/plan/page.tsx')
  expect(plan).not.toMatch(/NotesPanel|NarrativeThreadsPanel/)
  expect(src('app/(dashboard)/projects/[id]/world/page.tsx')).toMatch(/NotesPanel/)
  expect(src('lib/registries/panels.tsx')).toMatch(/id: 'narrative_threads'/)
  // Only one page-level mount of each panel across all workspaces.
  const pages = ['write', 'plan', 'characters', 'world', 'analyze', 'assistant', 'publish']
    .map((w) => src(`app/(dashboard)/projects/[id]/${w}/page.tsx`))
  expect(pages.filter((p) => /import\('@\/components\/notes\/NotesPanel'\)/.test(p))).toHaveLength(1)
  expect(pages.filter((p) => /NarrativeThreadsPanel/.test(p))).toHaveLength(0)   // lives in the panel registry
})

test('every Analyze panel in the registry has a Tool Homes row in Analyze', () => {
  const panelIds = [...src('lib/registries/panels.tsx').matchAll(/\{ id: '([a-z_]+)', title:/g)].map((m) => m[1])
  expect(panelIds.length).toBeGreaterThanOrEqual(8)
  for (const id of panelIds) {
    const home = TOOL_HOMES.find((t) => t.id === id)
    expect(home?.workspace, id).toBe('analyze')
  }
})

test('sections named in Tool Homes exist in their workspace', () => {
  for (const t of TOOL_HOMES) {
    const secs = WORKSPACE_SECTIONS[t.workspace]
    if (secs && t.section) expect(secs.map((s) => s.id), t.id).toContain(t.section)
  }
})

test('contextual second views carry a documented reason', () => {
  for (const t of TOOL_HOMES) for (const v of t.alsoShownIn ?? []) expect(v.reason.length, t.id).toBeGreaterThan(20)
})

test('Search & replace has a home and is mounted there (it was unreachable before Stage 8)', () => {
  expect(TOOL_HOMES.find((t) => t.id === 'search')?.workspace).toBe('write')
  expect(src('app/(dashboard)/projects/[id]/write/page.tsx')).toMatch(/import\('@\/components\/search\/SearchPanel'\)/)
})

test('P3-off build drops Phase 3 homes cleanly (rollback, review L5)', () => {
  const off = visibleToolHomes(false).map((t) => t.id)
  expect(off).not.toContain('versions')
  expect(off).not.toContain('idea_shelf')
  expect(off).toContain('notes')
})
