'use client'

import { useState, useEffect, useRef } from 'react'
import { Loader2, BookOpen, RefreshCw, Download, Users, MapPin, Clock, Globe, Palette } from 'lucide-react'
import { storyBibleApi } from '@/lib/api'
import { StoryBibleOut } from '@/lib/types'
import { toast } from 'sonner'

interface Props { storyId: string }

type BibleSection = 'characters' | 'locations' | 'timeline' | 'world_rules' | 'themes'

const SECTIONS: { key: BibleSection; label: string; icon: React.ElementType }[] = [
  { key: 'characters',  label: 'Characters',  icon: Users     },
  { key: 'locations',   label: 'Locations',   icon: MapPin    },
  { key: 'timeline',    label: 'Timeline',    icon: Clock     },
  { key: 'world_rules', label: 'World Rules', icon: Globe     },
  { key: 'themes',      label: 'Themes',      icon: Palette   },
]

function SectionContent({ text }: { text: string }) {
  if (!text) return <p className="text-xs text-[#5c6391] italic">Not yet generated.</p>
  return (
    <div className="text-xs text-[#9da3c8] leading-relaxed whitespace-pre-wrap">
      {text}
    </div>
  )
}

export default function StoryBiblePanel({ storyId }: Props) {
  const [bible, setBible] = useState<StoryBibleOut | null>(null)
  const [content, setContent]   = useState<Record<string, string>>({})
  const [generating, setGenerating] = useState(false)
  const [activeSection, setActiveSection] = useState<BibleSection>('characters')
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const loadBible = async () => {
    try {
      const res = await storyBibleApi.get(storyId)
      const b: StoryBibleOut = res.data
      setBible(b)
      try {
        setContent(JSON.parse(b.content_json))
      } catch {
        setContent({})
      }
    } catch (e: any) {
      if (e?.response?.status !== 404) {
        toast.error('Failed to load story bible')
      }
    }
  }

  const generate = async () => {
    setGenerating(true)
    try {
      await storyBibleApi.generate(storyId)
      toast.success('Bible generation started. This may take 1–2 min — refresh to check.')
      if (pollTimerRef.current) clearTimeout(pollTimerRef.current)
      pollTimerRef.current = setTimeout(loadBible, 30_000)
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Generation failed')
    } finally {
      setGenerating(false)
    }
  }

  const downloadDocx = () => {
    const url = storyBibleApi.exportUrl(storyId)
    const token = typeof window !== 'undefined' ? localStorage.getItem('narratiq_token') : null
    // Create a temporary link with Bearer token via query param workaround is not ideal;
    // use fetch + blob instead for auth
    fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.blob())
      .then(blob => {
        const a = document.createElement('a')
        a.href = URL.createObjectURL(blob)
        a.download = 'story_bible.docx'
        a.click()
      })
      .catch(() => toast.error('Export failed'))
  }

  useEffect(() => {
    loadBible()
    return () => { if (pollTimerRef.current) clearTimeout(pollTimerRef.current) }
  }, [storyId])

  if (!bible) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 p-6 h-full">
        <BookOpen className="w-10 h-10 text-[#2e3454]" />
        <p className="text-xs text-[#5c6391] text-center">
          Generate a comprehensive story bible: characters, locations, timeline, world rules, and themes
        </p>
        <button
          onClick={generate}
          disabled={generating}
          className="px-3 py-1.5 rounded-lg text-xs bg-amber-500/10 text-amber-400 border border-amber-500/20 hover:bg-amber-500/20 transition-all disabled:opacity-50"
        >
          {generating
            ? <><Loader2 className="w-3 h-3 animate-spin inline mr-1" />Generating…</>
            : 'Generate Story Bible'}
        </button>
        <p className="text-[10px] text-[#3d4466] text-center">Takes 1–3 min depending on manuscript size</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="px-3 pt-3 pb-2 flex items-center justify-between flex-shrink-0">
        <span className="text-xs text-[#9da3c8]">Version {bible.version}</span>
        <div className="flex gap-1">
          <button
            onClick={generate}
            disabled={generating}
            className="text-[10px] text-amber-400 border border-amber-500/20 px-2 py-0.5 rounded hover:bg-amber-500/10 disabled:opacity-50"
          >
            {generating ? '…' : 'Regenerate'}
          </button>
          <button
            onClick={downloadDocx}
            className="text-[#5c6391] hover:text-amber-400 transition-colors"
            title="Download DOCX"
          >
            <Download className="w-3.5 h-3.5" />
          </button>
          <button onClick={loadBible} className="text-[#5c6391] hover:text-amber-400 transition-colors" title="Refresh">
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Section tabs */}
      <div className="px-3 pb-2 flex gap-1 flex-wrap flex-shrink-0">
        {SECTIONS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setActiveSection(key)}
            className={`flex items-center gap-1 text-[10px] px-2 py-1 rounded border transition-colors ${
              activeSection === key
                ? 'text-amber-400 bg-amber-500/10 border-amber-500/20'
                : 'text-[#5c6391] border-[#2e3454] hover:text-[#9da3c8]'
            }`}
          >
            <Icon className="w-2.5 h-2.5" />
            {label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto px-3 pb-4">
        <SectionContent text={content[activeSection] ?? ''} />
      </div>
    </div>
  )
}
