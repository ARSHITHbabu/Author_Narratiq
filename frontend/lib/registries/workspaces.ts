// Workspace Registry — the single declarative source for the 8 author workspaces.
// The Workspace Rail, routing, Command Palette "navigate" group, and Workspace
// Memory all read this. Add a workspace by adding a row here — no nav/routing edits.
// Future Phase-3 modules / AI agents register additional workspaces the same way.

import {
  PenLine, Map, Users, Globe, BarChart3, Bot, Upload, LibraryBig,
  type LucideIcon,
} from 'lucide-react'

export type WorkspaceId =
  | 'write' | 'plan' | 'characters' | 'world' | 'analyze' | 'assistant' | 'publish'

export interface WorkspaceDef {
  id: WorkspaceId
  label: string
  icon: LucideIcon
  segment: string                 // route segment under /projects/[id]/
  description: string
  /** future gate: a permission key the Collaboration layer can check */
  requires?: string
}

export const WORKSPACES: WorkspaceDef[] = [
  { id: 'write',      label: 'Write',      icon: PenLine,    segment: 'write',      description: 'The manuscript — chapters, scenes, focused editor' },
  { id: 'plan',       label: 'Plan',       icon: Map,        segment: 'plan',       description: 'Outline, beats, plot assistant, pacing, threads, notes' },
  { id: 'characters', label: 'Characters', icon: Users,      segment: 'characters', description: 'Cast, profiles, relationships, arcs, voice' },
  { id: 'world',      label: 'World',      icon: Globe,      segment: 'world',      description: 'Story bible, notes, OCR worldbuilding' },
  { id: 'analyze',    label: 'Analyze',    icon: BarChart3,  segment: 'analyze',    description: 'Intelligence dashboard — all analyses & metrics' },
  { id: 'assistant',  label: 'Assistant',  icon: Bot,        segment: 'assistant',  description: 'Voice agent & AI history' },
  { id: 'publish',    label: 'Publish',    icon: Upload,     segment: 'publish',    description: 'Export & submission' },
]

// Projects is the cross-story library (lives at /dashboard, not inside a story).
export const PROJECTS_WORKSPACE = {
  id: 'projects' as const, label: 'Projects', icon: LibraryBig, route: '/dashboard',
  description: 'Manuscript library',
}

export function workspacePath(storyId: string, ws: WorkspaceId): string {
  return `/projects/${storyId}/${ws}`
}

export function workspaceById(id: string): WorkspaceDef | undefined {
  return WORKSPACES.find((w) => w.id === id)
}
