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
  /** other route segments that belong to this workspace (e.g. Analyze's /intake) */
  childSegments?: string[]
  description: string
  /** future gate: a permission key the Collaboration layer can check */
  requires?: string
}

export const WORKSPACES: WorkspaceDef[] = [
  { id: 'write',      label: 'Write',      icon: PenLine,    segment: 'write',      description: 'The manuscript — chapters, scenes, focused editor' },
  { id: 'plan',       label: 'Plan',       icon: Map,        segment: 'plan',       description: 'Plot assistant and pacing' },
  { id: 'characters', label: 'Characters', icon: Users,      segment: 'characters', description: 'Cast, profiles, relationships, arcs, voice' },
  { id: 'world',      label: 'World',      icon: Globe,      segment: 'world',      description: 'Story bible, notes, ideas and scanned pages' },
  { id: 'analyze',    label: 'Analyze',    icon: BarChart3,  segment: 'analyze',    description: 'Intelligence dashboard — all analyses & metrics', childSegments: ['intake', 'analytics'] },
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

export function workspacePathWith(storyId: string, ws: WorkspaceId, params: Record<string, string>): string {
  const q = new URLSearchParams(params).toString()
  return `${workspacePath(storyId, ws)}${q ? `?${q}` : ''}`
}

/** The workspace a /projects/[id]/<segment> route belongs to. Unknown → Write. */
export function workspaceForSegment(segment: string | undefined): WorkspaceId {
  if (!segment) return 'write'
  return (
    WORKSPACES.find((w) => w.segment === segment || w.childSegments?.includes(segment))?.id ?? 'write'
  )
}

export function workspaceById(id: string): WorkspaceDef | undefined {
  return WORKSPACES.find((w) => w.id === id)
}
