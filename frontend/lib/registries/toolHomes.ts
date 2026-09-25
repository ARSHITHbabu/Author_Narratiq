// Tool Homes — the one table that says where every author-facing tool lives.
//
// Stage 8 (tasks 8.1 / 8.8): every Phase 1, 2 and 3 tool has exactly ONE home — a
// workspace, and optionally a section inside it. Navigation, the Command Palette
// deep links and the tests all read this table, so "where does X live?" has a
// single answer. Icon-free on purpose: the unit tests import it without a browser.
//
// A tool may also be *shown* somewhere else when that view is contextual rather
// than a second place to manage it. Those are listed in `alsoShownIn` with the
// reason; anything else appearing in two workspaces is a regression the
// `tool-homes` test catches.

import type { WorkspaceId } from './workspaces'

export interface ToolHome {
  id: string
  label: string
  workspace: WorkspaceId
  /** section id within the workspace (Plan / World sections, Analyze panels) */
  section?: string
  /** contextual views elsewhere — never a second place to manage the tool */
  alsoShownIn?: { where: string; reason: string }[]
  /** only present when Phase 3 UI is enabled (NEXT_PUBLIC_P3_ENABLED) */
  phase3?: boolean
}

export const TOOL_HOMES: ToolHome[] = [
  // ── Write ─────────────────────────────────────────────────────────────────
  { id: 'editor', label: 'Manuscript editor', workspace: 'write' },
  { id: 'binder', label: 'Chapter binder', workspace: 'write' },
  { id: 'search', label: 'Search & replace', workspace: 'write', section: 'search' },
  { id: 'ai_rewrite', label: 'AI rewrite tools (refine, tone, emotion, audience, style, author voice, translate)', workspace: 'write', section: 'sidecar' },
  { id: 'ai_generate', label: 'AI continue & outline', workspace: 'write', section: 'sidecar' },
  { id: 'selection_toolbar', label: 'Selection toolbar', workspace: 'write' },
  { id: 'versions', label: 'Versions & pins', workspace: 'write', section: 'sidecar', phase3: true },
  { id: 'compare', label: 'Compare & merge', workspace: 'write', phase3: true },
  { id: 'preservation_rules', label: 'Preservation rules & locks', workspace: 'write', section: 'sidecar', phase3: true },

  // ── Plan ──────────────────────────────────────────────────────────────────
  { id: 'plot_assistant', label: 'Plot Assistant', workspace: 'plan', section: 'plot' },
  { id: 'pacing', label: 'Pacing goals', workspace: 'plan', section: 'pacing' },

  // ── Characters ────────────────────────────────────────────────────────────
  { id: 'cast', label: 'Cast, profiles, relationships & voice check', workspace: 'characters' },

  // ── World ─────────────────────────────────────────────────────────────────
  { id: 'story_bible', label: 'Story Bible', workspace: 'world', section: 'bible' },
  { id: 'notes', label: 'Notes & note cards', workspace: 'world', section: 'notes' },
  {
    id: 'idea_shelf', label: 'Idea Shelf', workspace: 'world', section: 'notes', phase3: true,
    alsoShownIn: [{
      where: 'Write binder',
      reason: 'Per-chapter "ideas waiting" markers show ideas aimed at that chapter while writing it; they are managed only on the shelf (decision D10).',
    }],
  },
  { id: 'ocr', label: 'Scan handwritten pages (OCR)', workspace: 'world', section: 'ocr' },

  // ── Analyze ───────────────────────────────────────────────────────────────
  { id: 'emotional_arc', label: 'Emotional Arc', workspace: 'analyze', section: 'emotional_arc' },
  { id: 'continuity', label: 'Continuity', workspace: 'analyze', section: 'continuity' },
  { id: 'style_drift', label: 'Style Drift', workspace: 'analyze', section: 'style_drift' },
  { id: 'duplicate_scenes', label: 'Duplicate Scenes', workspace: 'analyze', section: 'duplicate_scenes' },
  { id: 'narrative_threads', label: 'Narrative Threads', workspace: 'analyze', section: 'narrative_threads' },
  { id: 'plot_holes', label: 'Plot Holes', workspace: 'analyze', section: 'plot_holes' },
  { id: 'manuscript_report', label: 'Manuscript Report', workspace: 'analyze', section: 'manuscript_report' },
  { id: 'copyright_risk', label: 'Copyright Risk', workspace: 'analyze', section: 'copyright_risk' },
  { id: 'genre_intelligence', label: 'Genre Intelligence', workspace: 'analyze', section: 'intake' },
  { id: 'metrics', label: 'Writing metrics', workspace: 'analyze', section: 'analytics' },

  // ── Assistant ─────────────────────────────────────────────────────────────
  { id: 'voice_agent', label: 'Voice agent', workspace: 'assistant' },
  { id: 'audio', label: 'Audio transcription', workspace: 'assistant' },

  // ── Publish ───────────────────────────────────────────────────────────────
  { id: 'export', label: 'Export (DOCX / PDF)', workspace: 'publish' },

  // Test-only (Stage 8.7): present only in a NEXT_PUBLIC_E2E_MOCK_TOOL=true build.
  ...(process.env.NEXT_PUBLIC_E2E_MOCK_TOOL === 'true'
    ? [{ id: 'mock_tool', label: 'Mock Tool', workspace: 'analyze' as const, section: 'mock_tool' }]
    : []),
]

/** Sections each multi-section workspace offers, in display order. */
export const WORKSPACE_SECTIONS: Partial<Record<WorkspaceId, { id: string; label: string }[]>> = {
  plan: [
    { id: 'plot', label: 'Plot Assistant' },
    { id: 'pacing', label: 'Pacing' },
  ],
  world: [
    { id: 'bible', label: 'Story Bible' },
    { id: 'notes', label: 'Notes' },
    { id: 'ocr', label: 'Scan (OCR)' },
  ],
}

export function toolHome(id: string): ToolHome | undefined {
  return TOOL_HOMES.find((t) => t.id === id)
}

/** Homes visible in this build (Phase 3 tools drop out when the P3 UI is off). */
export function visibleToolHomes(p3Enabled: boolean): ToolHome[] {
  return TOOL_HOMES.filter((t) => p3Enabled || !t.phase3)
}
