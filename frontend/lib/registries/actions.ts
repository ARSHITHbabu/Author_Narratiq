'use client'

// Action Registry — declarative actions shared by the Command Palette and the
// voice-agent vocabulary (same capability names). Static actions live here;
// dynamic items (jump to a specific chapter/character) are composed by the palette
// from the Story Context Engine. New AI actions/agents register a row here.

import type { WorkspaceId } from './workspaces'

export interface ActionContext {
  storyId: string
  go: (ws: WorkspaceId, params?: Record<string, string>) => void
  openSidecar: () => void
  openSearch: () => void
  toggleFocus: () => void
  startVoice: () => void
  runAnalysis: (panelId: string) => void   // navigates to /analyze?panel=
  exportStory: (fmt: 'docx' | 'pdf') => void
}

export interface ActionDef {
  id: string
  label: string
  group: 'Navigate' | 'Run' | 'AI' | 'Export' | 'View'
  keywords?: string
  run: (ctx: ActionContext) => void
  /** only offered when the Phase 3 UI is enabled */
  phase3?: boolean
}

export const ACTIONS: ActionDef[] = [
  // ── Deep links to a tool's one home (see toolHomes.ts) ──────────────────────
  { id: 'nav.notes', label: 'Go to Notes', group: 'Navigate', keywords: 'notes note cards world',
    run: (c) => c.go('world', { section: 'notes' }) },
  { id: 'nav.ideas', label: 'Go to Idea Shelf', group: 'Navigate', keywords: 'ideas idea shelf notes', phase3: true,
    run: (c) => c.go('world', { section: 'notes', tab: 'ideas' }) },
  { id: 'nav.bible', label: 'Go to Story Bible', group: 'Navigate', keywords: 'story bible world lore',
    run: (c) => c.go('world', { section: 'bible' }) },
  { id: 'nav.ocr', label: 'Scan handwritten pages', group: 'Navigate', keywords: 'ocr scan photo handwriting',
    run: (c) => c.go('world', { section: 'ocr' }) },
  { id: 'nav.pacing', label: 'Go to Pacing', group: 'Navigate', keywords: 'pacing goals target words',
    run: (c) => c.go('plan', { section: 'pacing' }) },
  { id: 'nav.plot', label: 'Go to Plot Assistant', group: 'Navigate', keywords: 'plot assistant brainstorm',
    run: (c) => c.go('plan', { section: 'plot' }) },
  { id: 'nav.search', label: 'Search & replace in manuscript', group: 'Navigate', keywords: 'search find replace ctrl f',
    run: (c) => { c.go('write'); c.openSearch() } },

  // ── AI ────────────────────────────────────────────────────────────────────
  { id: 'ai.sidecar', label: 'Open AI assistant', group: 'AI', keywords: 'ai sidecar assistant help',
    run: (c) => { c.go('write'); c.openSidecar() } },
  { id: 'ai.voice', label: 'Start voice agent', group: 'AI', keywords: 'voice mic speak dictate',
    run: (c) => c.startVoice() },

  // ── Run analyses (route to Analyze workspace with the panel open) ───────────
  { id: 'run.continuity', label: 'Run continuity check', group: 'Run', keywords: 'continuity consistency',
    run: (c) => c.runAnalysis('continuity') },
  { id: 'run.arc', label: 'Run emotional arc analysis', group: 'Run', keywords: 'emotion arc curve',
    run: (c) => c.runAnalysis('emotional_arc') },
  { id: 'run.threads', label: 'Scan narrative threads', group: 'Run', keywords: 'threads subplot',
    run: (c) => c.runAnalysis('narrative_threads') },
  { id: 'run.style', label: 'Check style drift', group: 'Run', keywords: 'style drift consistency',
    run: (c) => c.runAnalysis('style_drift') },
  { id: 'run.dupes', label: 'Detect duplicate scenes', group: 'Run', keywords: 'duplicate repeated scenes',
    run: (c) => c.runAnalysis('duplicate_scenes') },
  { id: 'run.holes', label: 'Find plot holes', group: 'Run', keywords: 'plot holes logic',
    run: (c) => c.runAnalysis('plot_holes') },
  { id: 'run.report', label: 'Generate manuscript report', group: 'Run', keywords: 'report editorial',
    run: (c) => c.runAnalysis('manuscript_report') },

  // ── Export ──────────────────────────────────────────────────────────────────
  { id: 'export.docx', label: 'Export as DOCX', group: 'Export', keywords: 'export docx word download',
    run: (c) => c.exportStory('docx') },
  { id: 'export.pdf', label: 'Export as PDF', group: 'Export', keywords: 'export pdf download',
    run: (c) => c.exportStory('pdf') },

  // ── View ──────────────────────────────────────────────────────────────────
  { id: 'view.focus', label: 'Toggle focus mode', group: 'View', keywords: 'focus zen distraction',
    run: (c) => c.toggleFocus() },
]
