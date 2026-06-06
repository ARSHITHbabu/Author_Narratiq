'use client'

import { User, Crown, Sword, Users, Eye } from 'lucide-react'
import { Character } from '@/lib/types'

const ROLE_CONFIG: Record<string, { label: string; color: string; icon: typeof User }> = {
  protagonist: { label: 'Protagonist', color: 'text-amber-400 bg-amber-500/10 border-amber-500/20', icon: Crown },
  antagonist:  { label: 'Antagonist',  color: 'text-red-400 bg-red-500/10 border-red-500/20',     icon: Sword },
  supporting:  { label: 'Supporting',  color: 'text-sky-400 bg-sky-500/10 border-sky-500/20',     icon: Users },
  minor:       { label: 'Minor',       color: 'text-[#5c6391] bg-[#1f2440] border-[#2e3454]',     icon: Eye  },
}

const STATUS_COLOR: Record<string, string> = {
  active:   'bg-green-500',
  deceased: 'bg-red-500',
  unknown:  'bg-[#5c6391]',
}

interface Props {
  character: Character
  onClick:   () => void
}

export default function CharacterCard({ character, onClick }: Props) {
  const role   = ROLE_CONFIG[character.role] ?? ROLE_CONFIG.supporting
  const RoleIcon = role.icon
  const blurb  =
    character.profile?.appearance?.slice(0, 80) ||
    character.profile?.personality?.slice(0, 80) ||
    character.profile?.raw_notes?.slice(0, 80) ||
    ''

  return (
    <button
      onClick={onClick}
      className="w-full text-left p-3 rounded-xl border border-[#1f2440] bg-[#0d0f1a] hover:border-amber-500/30 hover:bg-amber-500/5 transition-all group"
    >
      <div className="flex items-start gap-2.5">
        {/* Avatar placeholder */}
        <div className="w-8 h-8 rounded-full bg-[#1f2440] flex items-center justify-center flex-shrink-0 group-hover:bg-amber-500/10 transition-colors">
          <User className="w-4 h-4 text-[#5c6391] group-hover:text-amber-500" />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            {/* Status dot */}
            <span
              className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${STATUS_COLOR[character.status] ?? 'bg-[#5c6391]'}`}
              title={character.status}
            />
            <span className="text-sm font-medium text-[#e8eaf6] truncate">{character.name}</span>
          </div>

          <div className="flex items-center gap-1.5 mb-1">
            <span className={`flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full border font-medium ${role.color}`}>
              <RoleIcon className="w-2.5 h-2.5" />
              {role.label}
            </span>
            {character.profile?.traits && character.profile.traits.length > 0 && (
              <span className="text-[10px] text-[#3d4466] truncate">
                {character.profile.traits.slice(0, 2).join(', ')}
              </span>
            )}
          </div>

          {blurb && (
            <p className="text-[11px] text-[#3d4466] line-clamp-1">{blurb}</p>
          )}

          {/* Profile completeness bar */}
          {character.completeness_score > 0 && (
            <div className="mt-1.5 h-0.5 w-full bg-[#1a1d2e] rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${
                  character.completeness_score >= 70 ? 'bg-green-500/50' :
                  character.completeness_score >= 30 ? 'bg-amber-500/50' :
                  'bg-[#3d4466]'
                }`}
                style={{ width: `${character.completeness_score}%` }}
              />
            </div>
          )}
        </div>
      </div>
    </button>
  )
}
