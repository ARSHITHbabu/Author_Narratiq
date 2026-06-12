'use client'

// Studio Shell — the one persistent chrome for every story workspace. Replaces the
// four duplicated per-page top bars. Renders the Context Bar (story switcher, ⌘K,
// mic, activity, user) + the left Workspace Rail, and mounts the Command Palette and
// Activity Timeline. Focus/Zen modes hide the chrome so the editor can breathe.

import { useEffect, useState } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import {
  Command as CommandIcon, Mic, History, ChevronDown, PanelLeftClose, PanelLeft,
} from 'lucide-react'
import { WORKSPACES, PROJECTS_WORKSPACE, workspacePath, type WorkspaceId } from '@/lib/registries/workspaces'
import { useStudioStore } from '@/lib/studioStore'
import { useStoryContext } from './StoryContextEngine'
import { projectsApi } from '@/lib/api'
import type { Story } from '@/lib/types'
import { useAuth } from '@/lib/auth'
import CommandPalette from './CommandPalette'
import ActivityTimeline from './ActivityTimeline'

function currentWorkspace(pathname: string, storyId: string): WorkspaceId {
  const seg = pathname.split(`/projects/${storyId}/`)[1]?.split('/')[0]
  return (WORKSPACES.find((w) => w.segment === seg)?.id ?? 'write')
}

export default function StudioShell({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const { user, logout } = useAuth()
  const { storyId, story } = useStoryContext()
  const store = useStudioStore()
  const ws = currentWorkspace(pathname, storyId)

  const [paletteOpen, setPaletteOpen] = useState(false)
  const [activityOpen, setActivityOpen] = useState(false)
  const [switcherOpen, setSwitcherOpen] = useState(false)

  const storiesQ = useQuery({ queryKey: ['projects'], queryFn: async () => (await projectsApi.list()).data as Story[] })

  // Persist the active workspace whenever the route changes (Workspace Memory).
  useEffect(() => { store.setWorkspace(storyId, ws) }, [ws, storyId]) // eslint-disable-line react-hooks/exhaustive-deps

  // Global keyboard map.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey
      if (mod && e.key.toLowerCase() === 'k') { e.preventDefault(); setPaletteOpen((o) => !o) }
      else if (mod && e.key === '.') { e.preventDefault(); store.setFocusMode(!store.focusMode) }
      else if (mod && /^[1-7]$/.test(e.key)) { e.preventDefault(); const w = WORKSPACES[Number(e.key) - 1]; if (w) router.push(workspacePath(storyId, w.id)) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [storyId, router, store])

  const chromeHidden = store.zenMode
  const railHidden = store.zenMode || store.focusMode || store.railCollapsed

  const go = (id: WorkspaceId) => router.push(workspacePath(storyId, id))

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-[#0d0f1a] text-[#e8eaf6]">
      {/* ── Context Bar ─────────────────────────────────────────────────────── */}
      {!chromeHidden && (
        <header className="h-11 flex-shrink-0 flex items-center gap-2 px-3 border-b border-[#1f2440] bg-[#0f1220]">
          <button onClick={() => store.toggleRail()} className="p-1.5 rounded text-[#9da3c8] hover:text-white hover:bg-[#1f2440]" title="Toggle rail">
            {store.railCollapsed ? <PanelLeft className="w-4 h-4" /> : <PanelLeftClose className="w-4 h-4" />}
          </button>

          {/* Story switcher */}
          <div className="relative">
            <button onClick={() => setSwitcherOpen((o) => !o)}
              className="flex items-center gap-1.5 px-2 py-1 rounded hover:bg-[#1f2440] max-w-[260px]">
              <span className="text-amber-500 font-semibold text-sm">NarratIQ</span>
              <span className="text-[#3d4466]">/</span>
              <span className="text-sm text-[#e8eaf6] truncate">{story?.title ?? '…'}</span>
              <ChevronDown className="w-3.5 h-3.5 text-[#5c6391]" />
            </button>
            {switcherOpen && (
              <>
                <div className="fixed inset-0 z-20" onClick={() => setSwitcherOpen(false)} />
                <div className="absolute left-0 top-full mt-1 w-72 z-30 rounded-lg border border-[#2e3454] bg-[#13162a] shadow-xl py-1 max-h-80 overflow-y-auto">
                  <p className="px-3 py-1 text-[10px] uppercase tracking-wide text-[#5c6391]">Switch manuscript</p>
                  {(storiesQ.data ?? []).map((s) => (
                    <button key={s.story_id} onClick={() => { setSwitcherOpen(false); router.push(workspacePath(s.story_id, store.getStory(s.story_id).lastWorkspace)) }}
                      className={`w-full text-left px-3 py-1.5 text-sm hover:bg-[#1f2440] truncate ${s.story_id === storyId ? 'text-amber-400' : 'text-[#cdd2f0]'}`}>
                      {s.title}
                    </button>
                  ))}
                  <div className="border-t border-[#1f2440] mt-1 pt-1">
                    <button onClick={() => router.push('/dashboard')} className="w-full text-left px-3 py-1.5 text-xs text-[#9da3c8] hover:bg-[#1f2440]">
                      All manuscripts →
                    </button>
                  </div>
                </div>
              </>
            )}
          </div>

          <span className="text-[#3d4466] text-sm">›</span>
          <span className="text-sm text-[#9da3c8] capitalize">{WORKSPACES.find((w) => w.id === ws)?.label}</span>

          <div className="flex-1" />

          <button onClick={() => setPaletteOpen(true)}
            className="hidden sm:flex items-center gap-1.5 px-2 py-1 rounded border border-[#2e3454] text-[11px] text-[#9da3c8] hover:text-white hover:border-[#3d4466]">
            <CommandIcon className="w-3 h-3" /> <span>⌘K</span>
          </button>
          <button onClick={() => go('assistant')} className="p-1.5 rounded text-[#9da3c8] hover:text-white hover:bg-[#1f2440]" title="Voice assistant">
            <Mic className="w-4 h-4" />
          </button>
          <button onClick={() => setActivityOpen(true)} className="p-1.5 rounded text-[#9da3c8] hover:text-white hover:bg-[#1f2440]" title="Activity timeline">
            <History className="w-4 h-4" />
          </button>
          <div className="w-px h-5 bg-[#2e3454] mx-1" />
          <div className="relative group">
            <button className="flex items-center gap-1.5 px-2 py-1 rounded hover:bg-[#1f2440]">
              <span className="w-6 h-6 rounded-full bg-amber-500/20 text-amber-400 text-xs flex items-center justify-center">
                {user?.username?.[0]?.toUpperCase() ?? '?'}
              </span>
            </button>
            <div className="absolute right-0 top-full mt-1 w-40 rounded-lg border border-[#2e3454] bg-[#13162a] shadow-xl py-1 opacity-0 invisible group-hover:opacity-100 group-hover:visible transition">
              <p className="px-3 py-1 text-xs text-[#9da3c8] truncate">{user?.username}</p>
              <button onClick={() => logout()} className="w-full text-left px-3 py-1.5 text-sm text-[#cdd2f0] hover:bg-[#1f2440]">Log out</button>
            </div>
          </div>
        </header>
      )}

      {/* ── Rail + workspace content ────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">
        {!railHidden && (
          <nav className="w-16 flex-shrink-0 border-r border-[#1f2440] bg-[#0f1220] flex flex-col items-center py-2 gap-1">
            {WORKSPACES.map((w) => {
              const Icon = w.icon
              const active = w.id === ws
              return (
                <button key={w.id} onClick={() => go(w.id)} title={w.description}
                  className={`w-full flex flex-col items-center gap-0.5 py-2 transition-colors ${active ? 'text-amber-400' : 'text-[#5c6391] hover:text-[#9da3c8]'}`}>
                  <span className={`relative flex items-center justify-center w-9 h-9 rounded-lg ${active ? 'bg-amber-500/10' : 'hover:bg-[#1f2440]'}`}>
                    <Icon className="w-[18px] h-[18px]" />
                    {active && <span className="absolute -left-2 top-1/2 -translate-y-1/2 w-0.5 h-5 bg-amber-500 rounded" />}
                  </span>
                  <span className="text-[9px]">{w.label}</span>
                </button>
              )
            })}
            <div className="flex-1" />
            <button onClick={() => router.push(PROJECTS_WORKSPACE.route)} title={PROJECTS_WORKSPACE.description}
              className="w-full flex flex-col items-center gap-0.5 py-2 text-[#5c6391] hover:text-[#9da3c8]">
              <span className="flex items-center justify-center w-9 h-9 rounded-lg hover:bg-[#1f2440]">
                <PROJECTS_WORKSPACE.icon className="w-[18px] h-[18px]" />
              </span>
              <span className="text-[9px]">Library</span>
            </button>
          </nav>
        )}

        <main className="flex-1 min-w-0 overflow-hidden">{children}</main>
      </div>

      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
      <ActivityTimeline open={activityOpen} onClose={() => setActivityOpen(false)} />
    </div>
  )
}
