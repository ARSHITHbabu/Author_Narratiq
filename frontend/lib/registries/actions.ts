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
}

export const ACTIONS: ActionDef[] = [
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
