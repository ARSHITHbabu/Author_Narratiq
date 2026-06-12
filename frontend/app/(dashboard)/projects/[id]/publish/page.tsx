'use client'

// Publish Workspace — end-of-pipeline export. Reuses exportApi (DOCX/PDF). Records
// to the Activity Timeline. The manuscript report lives in Analyze.

import { useRouter } from 'next/navigation'
import { useState } from 'react'
import { FileText, FileType2, Loader2, ClipboardCheck } from 'lucide-react'
import { toast } from 'sonner'
import { exportApi } from '@/lib/api'
import { useStoryContext } from '@/components/studio/StoryContextEngine'

export default function PublishWorkspace() {
  const router = useRouter()
  const { storyId, story, logActivity } = useStoryContext()
  const [busy, setBusy] = useState<'docx' | 'pdf' | null>(null)

  const doExport = async (fmt: 'docx' | 'pdf') => {
    setBusy(fmt)
    try {
      const res = await exportApi.export(storyId, fmt)
      const url = window.URL.createObjectURL(res.data as Blob)
      const a = document.createElement('a')
      a.href = url; a.download = `${(story?.title || 'manuscript').replace(/[^\w]+/g, '_')}.${fmt}`; a.click()
      window.URL.revokeObjectURL(url)
      logActivity({ category: 'export', type: `export_${fmt}`, title: `Exported ${fmt.toUpperCase()}` })
      toast.success(`Exported ${fmt.toUpperCase()}`)
    } catch {
      toast.error('Export failed')
    } finally {
      setBusy(null)
    }
  }

  const Card = ({ fmt, icon: Icon, label, desc }: { fmt: 'docx' | 'pdf'; icon: typeof FileText; label: string; desc: string }) => (
    <button onClick={() => doExport(fmt)} disabled={!!busy}
      className="text-left rounded-lg border border-[#1f2440] bg-[#13162a] hover:border-[#3d4466] hover:bg-[#1a1e36] transition p-5 disabled:opacity-60">
      <div className="flex items-center gap-2 mb-2">
        <span className="w-10 h-10 rounded-lg bg-amber-500/10 flex items-center justify-center">
          {busy === fmt ? <Loader2 className="w-5 h-5 text-amber-400 animate-spin" /> : <Icon className="w-5 h-5 text-amber-400" />}
        </span>
        <span className="text-base font-medium text-[#e8eaf6]">{label}</span>
      </div>
      <p className="text-xs text-[#9da3c8]">{desc}</p>
    </button>
  )

  return (
    <div className="h-full overflow-y-auto bg-[#0d0f1a]">
      <div className="max-w-3xl mx-auto px-6 py-8">
        <h1 className="text-xl font-semibold text-[#e8eaf6] mb-1">Publish</h1>
        <p className="text-sm text-[#9da3c8] mb-6">Export your manuscript for submission, formatting, or backup.</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Card fmt="docx" icon={FileText} label="Word (DOCX)" desc="Formatted manuscript with title page and chapters — ideal for editing and submission." />
          <Card fmt="pdf" icon={FileType2} label="PDF" desc="Print-ready PDF with justified body and standard manuscript margins." />
        </div>
        <button onClick={() => router.push(`/projects/${storyId}/analyze`)}
          className="mt-4 flex items-center gap-2 text-sm text-[#9da3c8] hover:text-white">
          <ClipboardCheck className="w-4 h-4" /> Need an editorial report first? Open Analyze →
        </button>
      </div>
    </div>
  )
}
