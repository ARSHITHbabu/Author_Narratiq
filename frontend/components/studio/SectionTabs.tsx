'use client'

// Section tabs for multi-section workspaces (Plan, World). A real ARIA tablist:
// arrow keys / Home / End move between tabs (roving tabindex), and the active
// section is deep-linkable with ?section=<id> and remembered per story, so the
// Command Palette can open "World › Notes" directly.

import { useCallback, useEffect, useRef, type ReactNode } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import type { LucideIcon } from 'lucide-react'
import { useStudioStore } from '@/lib/studioStore'
import type { WorkspaceId } from '@/lib/registries/workspaces'

export interface SectionDef<T extends string> {
  id: T
  label: string
  icon: LucideIcon
}

/** Current section: ?section= wins, then this story's memory, then the first. */
export function useWorkspaceSection<T extends string>(
  storyId: string, ws: WorkspaceId, sections: readonly SectionDef<T>[],
): [T, (id: T) => void] {
  const params = useSearchParams()
  const router = useRouter()
  const pathname = usePathname()
  const store = useStudioStore()
  const ids = sections.map((s) => s.id)
  const fromUrl = params.get('section') as T | null
  const remembered = store.getStory(storyId).lastSections?.[ws] as T | undefined
  const current: T =
    (fromUrl && ids.includes(fromUrl) ? fromUrl : undefined) ??
    (remembered && ids.includes(remembered) ? remembered : undefined) ??
    ids[0]

  useEffect(() => { store.setSection(storyId, ws, current) }, [storyId, ws, current]) // eslint-disable-line react-hooks/exhaustive-deps

  const select = useCallback((id: T) => {
    store.setSection(storyId, ws, id)
    const next = new URLSearchParams(params.toString())
    next.set('section', id)
    next.delete('tab')
    router.replace(`${pathname}?${next.toString()}`, { scroll: false })
  }, [storyId, ws, params, pathname, router, store])

  return [current, select]
}

export function SectionTabs<T extends string>({
  label, sections, current, onSelect, trailing,
}: {
  label: string
  sections: readonly SectionDef<T>[]
  current: T
  onSelect: (id: T) => void
  trailing?: ReactNode
}) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({})

  const onKeyDown = (e: React.KeyboardEvent) => {
    const i = sections.findIndex((s) => s.id === current)
    let n = -1
    if (e.key === 'ArrowRight') n = (i + 1) % sections.length
    else if (e.key === 'ArrowLeft') n = (i - 1 + sections.length) % sections.length
    else if (e.key === 'Home') n = 0
    else if (e.key === 'End') n = sections.length - 1
    if (n < 0) return
    e.preventDefault()
    onSelect(sections[n].id)
    refs.current[sections[n].id]?.focus()
  }

  return (
    <div className="h-10 flex items-center gap-1 px-3 border-b border-[#1f2440] flex-shrink-0">
      <div role="tablist" aria-label={label} className="flex items-center gap-1" onKeyDown={onKeyDown}>
        {sections.map((s) => {
          const selected = s.id === current
          return (
            <button key={s.id} role="tab" id={`section-tab-${s.id}`} aria-selected={selected}
              aria-controls={`section-panel-${s.id}`} tabIndex={selected ? 0 : -1}
              ref={(el) => { refs.current[s.id] = el }}
              onClick={() => onSelect(s.id)}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/70 ${selected ? 'bg-amber-500/10 text-amber-400' : 'text-[#aeb3d6] hover:text-white hover:bg-[#1f2440]'}`}>
              <s.icon className="w-3.5 h-3.5" aria-hidden="true" /> {s.label}
            </button>
          )
        })}
      </div>
      {trailing && <div className="ml-auto flex items-center">{trailing}</div>}
    </div>
  )
}

/** The panel a section tab controls. */
export function SectionPanel({ id, children }: { id: string; children: ReactNode }) {
  return (
    <div role="tabpanel" id={`section-panel-${id}`} aria-labelledby={`section-tab-${id}`} className="flex-1 overflow-hidden">
      {children}
    </div>
  )
}
