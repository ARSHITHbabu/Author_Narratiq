'use client'

// Panel Registry — declarative panels rendered by PanelHost. Replaces the old
// 10-way conditional. Each panel is a lazy-loaded existing component reused as-is.
// Add a Phase-3 panel by adding a row; PanelHost + Analyze dashboard pick it up.

import dynamic from 'next/dynamic'
import {
  Activity, AlertTriangle, GitBranch, Palette, Copy, Heart, FileText, Sparkles, ShieldAlert,
  type LucideIcon,
} from 'lucide-react'
import type { ComponentType } from 'react'
import type { WorkspaceId } from './workspaces'

export type PanelSurface = 'dock' | 'sheet' | 'float' | 'page'

export interface PanelDef {
  id: string
  title: string
  icon: LucideIcon
  workspace: WorkspaceId
  surface: PanelSurface
  category?: 'ai' | 'analysis' | 'project'
  /** props this panel needs from the Story Context Engine */
  needs: ('storyId' | 'chapterId' | 'characterId')[]
  component: ComponentType<any>
  blurb?: string
}

const EmotionalArc = dynamic(() => import('@/components/analysis/EmotionalArcPanel'), { ssr: false })
const Continuity = dynamic(() => import('@/components/analysis/ContinuityPanel'), { ssr: false })
const StyleDrift = dynamic(() => import('@/components/analysis/StyleDriftPanel'), { ssr: false })
const DuplicateScenes = dynamic(() => import('@/components/analysis/DuplicateScenesPanel'), { ssr: false })
const NarrativeThreads = dynamic(() => import('@/components/analysis/NarrativeThreadsPanel'), { ssr: false })
const PlotHoles = dynamic(() => import('@/components/plot-holes/PlotHolesPanel'), { ssr: false })
const ManuscriptReport = dynamic(() => import('@/components/plot-holes/ManuscriptReportPanel'), { ssr: false })
const CopyrightRisk = dynamic(() => import('@/components/analysis/CopyrightRiskPanel'), { ssr: false })

// ── Analyze workspace panels (the 7 previously-buried analyses + report) ──────
export const PANELS: PanelDef[] = [
  { id: 'emotional_arc', title: 'Emotional Arc', icon: Heart, workspace: 'analyze', surface: 'page',
    category: 'analysis', needs: ['storyId'], component: EmotionalArc,
    blurb: 'How the emotional intensity rises and falls across chapters.' },
  { id: 'continuity', title: 'Continuity', icon: GitBranch, workspace: 'analyze', surface: 'page',
    category: 'analysis', needs: ['storyId'], component: Continuity,
    blurb: 'Cross-chapter consistency of facts, characters and timeline.' },
  { id: 'style_drift', title: 'Style Drift', icon: Palette, workspace: 'analyze', surface: 'page',
    category: 'analysis', needs: ['storyId'], component: StyleDrift,
    blurb: 'Whether your prose style stays consistent throughout.' },
  { id: 'duplicate_scenes', title: 'Duplicate Scenes', icon: Copy, workspace: 'analyze', surface: 'page',
    category: 'analysis', needs: ['storyId'], component: DuplicateScenes,
    blurb: 'Scenes that repeat the same beat or feel redundant.' },
  { id: 'narrative_threads', title: 'Narrative Threads', icon: Activity, workspace: 'analyze', surface: 'page',
    category: 'analysis', needs: ['storyId'], component: NarrativeThreads,
    blurb: 'Plot/subplot threads — introduced, tracked, resolved or dropped.' },
  { id: 'plot_holes', title: 'Plot Holes', icon: AlertTriangle, workspace: 'analyze', surface: 'page',
    category: 'analysis', needs: ['storyId'], component: PlotHoles,
    blurb: 'Logical gaps and unresolved setups.' },
  { id: 'manuscript_report', title: 'Manuscript Report', icon: FileText, workspace: 'analyze', surface: 'page',
    category: 'analysis', needs: ['storyId'], component: ManuscriptReport,
    blurb: 'Full editorial report: arcs, pacing, threads, strengths, fixes.' },
  { id: 'copyright_risk', title: 'Copyright Risk', icon: ShieldAlert, workspace: 'analyze', surface: 'page',
    category: 'analysis', needs: ['storyId'], component: CopyrightRisk,
    blurb: 'Plagiarism / copyright risk — text, plot, character, world and trope similarity.' },
]

export function panelsForWorkspace(ws: WorkspaceId): PanelDef[] {
  return PANELS.filter((p) => p.workspace === ws)
}

export function panelById(id: string): PanelDef | undefined {
  return PANELS.find((p) => p.id === id)
}

export const SPARKLES = Sparkles
