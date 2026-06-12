'use client'

// Command Palette (⌘K) — the Quick Actions Layer. Keyboard-first access to all
// navigation (workspaces, chapters, characters) and actions (analyses, exports, AI).
// Static actions come from the Action Registry (shared vocabulary with the voice
// agent); dynamic items (specific chapters/characters) come from the Story Context
// Engine. Reuses existing endpoints/routes — no new APIs.

import { Command } from 'cmdk'
import { useRouter } from 'next/navigation'
import { useMemo } from 'react'
import { toast } from 'sonner'
import { ACTIONS, type ActionContext } from '@/lib/registries/actions'
import { WORKSPACES, workspacePath, type WorkspaceId } from '@/lib/registries/workspaces'
import { useStoryContext } from './StoryContextEngine'
import { useStudioStore } from '@/lib/studioStore'
import { exportApi } from '@/lib/api'

export default function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const router = useRouter()
  const store = useStudioStore()
  const { storyId, chapters, characters, setActiveChapter, setActiveCharacter, setActiveAnalysis, logActivity } = useStoryContext()

  const ctx: ActionContext = useMemo(() => ({
    storyId,
    go: (ws: WorkspaceId) => router.push(workspacePath(storyId, ws)),
    openSidecar: () => store.toggleSidecar(true),
    toggleFocus: () => store.setFocusMode(!store.focusMode),
    startVoice: () => router.push(workspacePath(storyId, 'assistant')),
    runAnalysis: (panelId: string) => { setActiveAnalysis(panelId); router.push(workspacePath(storyId, 'analyze')) },
    exportStory: async (fmt: 'docx' | 'pdf') => {
      try {
        const res = await exportApi.export(storyId, fmt)
        const url = window.URL.createObjectURL(res.data as Blob)
        const a = document.createElement('a'); a.href = url; a.download = `story.${fmt}`; a.click()
        window.URL.revokeObjectURL(url)
        logActivity({ category: 'export', type: `export_${fmt}`, title: `Exported ${fmt.toUpperCase()}` })
      } catch { toast.error('Export failed') }
    },
  }), [storyId, router, store, setActiveAnalysis, logActivity])

  const run = (fn: () => void) => { onOpenChange(false); fn() }

  return (
    <Command.Dialog open={open} onOpenChange={onOpenChange} label="Command palette"
      className="fixed inset-0 z-50 flex items-start justify-center pt-[12vh]">
      <div className="fixed inset-0 bg-black/50" onClick={() => onOpenChange(false)} />
      <div className="relative w-full max-w-xl rounded-xl border border-[#2e3454] bg-[#13162a] shadow-2xl overflow-hidden">
        <Command.Input autoFocus placeholder="Search workspaces, chapters, characters, actions…"
          className="w-full px-4 py-3 bg-transparent text-[#e8eaf6] placeholder-[#5c6391] outline-none border-b border-[#1f2440]" />
        <Command.List className="max-h-[55vh] overflow-y-auto p-2 text-sm">
          <Command.Empty className="px-3 py-6 text-center text-[#5c6391]">No results.</Command.Empty>

          <Command.Group heading="Navigate" className="text-[10px] uppercase tracking-wide text-[#5c6391] [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1">
            {WORKSPACES.map((w) => (
              <Command.Item key={w.id} value={`go ${w.label} ${w.description}`} onSelect={() => run(() => ctx.go(w.id))}
                className="flex items-center gap-2 px-2 py-1.5 rounded text-[#cdd2f0] aria-selected:bg-[#1f2440] cursor-pointer">
                <w.icon className="w-4 h-4 text-[#9da3c8]" /> Go to {w.label}
              </Command.Item>
            ))}
          </Command.Group>

          {chapters.length > 0 && (
            <Command.Group heading="Chapters" className="text-[10px] uppercase tracking-wide text-[#5c6391] [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1">
              {chapters.map((c) => (
                <Command.Item key={c.chapter_id} value={`chapter ${c.chapter_number} ${c.title}`}
                  onSelect={() => run(() => { setActiveChapter(c.chapter_id); router.push(workspacePath(storyId, 'write')) })}
                  className="flex items-center gap-2 px-2 py-1.5 rounded text-[#cdd2f0] aria-selected:bg-[#1f2440] cursor-pointer">
                  <span className="text-[#5c6391] text-xs">Ch {c.chapter_number}</span> {c.title || 'Untitled'}
                </Command.Item>
              ))}
            </Command.Group>
          )}

          {characters.length > 0 && (
            <Command.Group heading="Characters" className="text-[10px] uppercase tracking-wide text-[#5c6391] [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1">
              {characters.map((c) => (
                <Command.Item key={c.character_id} value={`character ${c.name}`}
                  onSelect={() => run(() => { setActiveCharacter(c.character_id); router.push(workspacePath(storyId, 'characters')) })}
                  className="flex items-center gap-2 px-2 py-1.5 rounded text-[#cdd2f0] aria-selected:bg-[#1f2440] cursor-pointer">
                  {c.name}
                </Command.Item>
              ))}
            </Command.Group>
          )}

          {(['Run', 'Export', 'AI', 'View'] as const).map((grp) => (
            <Command.Group key={grp} heading={grp} className="text-[10px] uppercase tracking-wide text-[#5c6391] [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1">
              {ACTIONS.filter((a) => a.group === grp).map((a) => (
                <Command.Item key={a.id} value={`${a.label} ${a.keywords ?? ''}`} onSelect={() => run(() => a.run(ctx))}
                  className="px-2 py-1.5 rounded text-[#cdd2f0] aria-selected:bg-[#1f2440] cursor-pointer">
                  {a.label}
                </Command.Item>
              ))}
            </Command.Group>
          ))}
        </Command.List>
      </div>
    </Command.Dialog>
  )
}
