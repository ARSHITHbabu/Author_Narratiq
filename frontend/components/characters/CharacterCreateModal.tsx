'use client'

import { useState } from 'react'
import { X, Loader2, User } from 'lucide-react'
import { charactersApi } from '@/lib/api'
import { Character, CharacterRole, CharacterStatus } from '@/lib/types'
import { toast } from 'sonner'

const ROLES: { value: CharacterRole; label: string }[] = [
  { value: 'protagonist', label: 'Protagonist' },
  { value: 'antagonist',  label: 'Antagonist'  },
  { value: 'supporting',  label: 'Supporting'  },
  { value: 'minor',       label: 'Minor'       },
]

const STATUSES: { value: CharacterStatus; label: string }[] = [
  { value: 'active',   label: 'Active'   },
  { value: 'deceased', label: 'Deceased' },
  { value: 'unknown',  label: 'Unknown'  },
]

interface Props {
  storyId:  string
  onCreated: (character: Character) => void
  onClose:   () => void
}

export default function CharacterCreateModal({ storyId, onCreated, onClose }: Props) {
  const [name,     setName]     = useState('')
  const [role,     setRole]     = useState<CharacterRole>('supporting')
  const [status,   setStatus]   = useState<CharacterStatus>('active')
  const [aliasRaw, setAliasRaw] = useState('')  // comma-separated alias input
  const [saving,   setSaving]   = useState(false)
  const [error,    setError]    = useState<string | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    const trimmedName = name.trim()
    if (!trimmedName) return

    const aliases = aliasRaw
      .split(',')
      .map(a => a.trim())
      .filter(Boolean)

    setSaving(true)
    setError(null)
    try {
      const res = await charactersApi.create(storyId, {
        name:    trimmedName,
        role,
        status,
        aliases,
      })
      toast.success(`Character "${trimmedName}" created`)
      onCreated(res.data as Character)
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      if (err?.response?.status === 409) {
        setError(detail || `A character named "${trimmedName}" already exists in this story.`)
      } else {
        toast.error(detail || 'Failed to create character')
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60">
      <div className="w-full max-w-md bg-[#0f1220] border border-[#2e3454] rounded-2xl shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-[#1f2440]">
          <div className="flex items-center gap-2">
            <User className="w-4 h-4 text-amber-500" />
            <span className="text-sm font-semibold text-[#e8eaf6]">New Character</span>
          </div>
          <button onClick={onClose} className="text-[#5c6391] hover:text-[#9da3c8] transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        <form onSubmit={submit} className="p-5 flex flex-col gap-4">
          {/* Name */}
          <div>
            <label className="text-xs text-[#5c6391] mb-1.5 block">
              Character name <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              value={name}
              onChange={e => { setName(e.target.value); setError(null) }}
              placeholder="e.g. Elara Voss"
              autoFocus
              className="w-full bg-[#0d0f1a] border border-[#2e3454] rounded-xl px-3 py-2 text-sm text-[#e8eaf6] placeholder-[#3d4466] focus:outline-none focus:border-amber-500/50 transition-colors"
            />
            {error && (
              <p className="text-xs text-red-400 mt-1">{error}</p>
            )}
          </div>

          {/* Role */}
          <div>
            <label className="text-xs text-[#5c6391] mb-1.5 block">Role</label>
            <div className="grid grid-cols-2 gap-1.5">
              {ROLES.map(r => (
                <button
                  key={r.value}
                  type="button"
                  onClick={() => setRole(r.value)}
                  className={`py-2 rounded-lg border text-xs font-medium transition-all ${
                    role === r.value
                      ? 'border-amber-500/50 bg-amber-500/10 text-amber-400'
                      : 'border-[#1f2440] text-[#9da3c8] hover:border-[#2e3454]'
                  }`}
                >
                  {r.label}
                </button>
              ))}
            </div>
          </div>

          {/* Status */}
          <div>
            <label className="text-xs text-[#5c6391] mb-1.5 block">Status</label>
            <div className="grid grid-cols-3 gap-1.5">
              {STATUSES.map(s => (
                <button
                  key={s.value}
                  type="button"
                  onClick={() => setStatus(s.value)}
                  className={`py-2 rounded-lg border text-xs font-medium transition-all ${
                    status === s.value
                      ? 'border-amber-500/50 bg-amber-500/10 text-amber-400'
                      : 'border-[#1f2440] text-[#9da3c8] hover:border-[#2e3454]'
                  }`}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>

          {/* Aliases */}
          <div>
            <label className="text-xs text-[#5c6391] mb-1.5 block">
              Aliases <span className="text-[#3d4466]">(comma-separated, optional)</span>
            </label>
            <input
              type="text"
              value={aliasRaw}
              onChange={e => setAliasRaw(e.target.value)}
              placeholder="e.g. El, The Silver Archer"
              className="w-full bg-[#0d0f1a] border border-[#2e3454] rounded-xl px-3 py-2 text-sm text-[#e8eaf6] placeholder-[#3d4466] focus:outline-none focus:border-amber-500/50 transition-colors"
            />
          </div>

          {/* Actions */}
          <div className="flex gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 py-2.5 rounded-xl border border-[#2e3454] text-sm text-[#9da3c8] hover:border-[#3d4466] hover:text-[#e8eaf6] transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving || !name.trim()}
              className="flex-1 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-sm font-semibold text-black transition-colors flex items-center justify-center gap-2"
            >
              {saving && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              Create Character
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
