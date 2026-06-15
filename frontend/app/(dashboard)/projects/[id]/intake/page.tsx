'use client'

import { useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useQueryClient } from '@tanstack/react-query'
import { Sparkles, Loader2, Edit3, Check, Feather, RefreshCw, BookOpen, AlertCircle } from 'lucide-react'
import { intakeApi } from '@/lib/api'
import { GenreProfile, IntakeResponse, IntakeReport } from '@/lib/types'
import { toast } from 'sonner'

// Richer Story Intelligence fields, rendered dynamically only when the backend
// actually returns a value. No hardcoded values, no placeholders.
const INTEL_TEXT_FIELDS: { key: keyof GenreProfile; label: string }[] = [
  { key: 'marketing_category', label: 'Marketing Category' },
  { key: 'narrative_pov',      label: 'Narrative POV' },
  { key: 'pacing',             label: 'Pacing' },
  { key: 'emotional_arc',      label: 'Emotional Arc' },
]

const INTEL_CHIP_FIELDS: { key: keyof GenreProfile; label: string; danger?: boolean }[] = [
  { key: 'secondary_genres',  label: 'Secondary Genres' },
  { key: 'comparable_titles', label: 'Comparable Titles' },
  { key: 'content_warnings',  label: 'Content Warnings', danger: true },
]

// ── Read-only rendering of a saved/derived profile (shared by saved view) ──────
function ProfileReadout({ profile }: { profile: GenreProfile }) {
  const textVal = (v: unknown) => (typeof v === 'string' ? v : '')
  const baseFields = [
    { label: 'Primary Genre',        value: profile.genre },
    { label: 'Sub-Genre',            value: profile.sub_genre },
    { label: 'Target Audience',      value: profile.audience },
    { label: 'Emotional Direction',  value: profile.conflict },
  ]
  return (
    <div className="grid sm:grid-cols-2 gap-5">
      {baseFields.map((item) => (
        <div key={item.label} className="bg-[#0d0f1a] rounded-xl p-4 border border-[#1f2440]">
          <div className="text-xs text-[#5c6391] mb-1">{item.label}</div>
          <div className="text-sm font-medium text-[#e8eaf6]">{item.value || '—'}</div>
        </div>
      ))}

      <div className="sm:col-span-2 bg-[#0d0f1a] rounded-xl p-4 border border-[#1f2440]">
        <div className="text-xs text-[#5c6391] mb-2">Tone</div>
        <div className="flex flex-wrap gap-2">
          {(profile.tone || []).length
            ? profile.tone.map((t) => (
                <span key={t} className="px-3 py-1 bg-amber-500/10 border border-amber-500/30 rounded-full text-xs text-amber-400">{t}</span>
              ))
            : <span className="text-sm text-[#5c6391]">—</span>}
        </div>
      </div>

      {profile.structure && (
        <div className="sm:col-span-2 bg-[#0d0f1a] rounded-xl p-4 border border-[#1f2440]">
          <div className="text-xs text-[#5c6391] mb-1">Suggested Structure</div>
          <p className="text-sm text-[#e8eaf6]">{profile.structure}</p>
        </div>
      )}

      {profile.writing_direction && (
        <div className="sm:col-span-2 bg-[#0d0f1a] rounded-xl p-4 border border-[#1f2440]">
          <div className="text-xs text-[#5c6391] mb-1">Writing Direction Notes</div>
          <p className="text-sm text-[#9da3c8] italic">{profile.writing_direction}</p>
        </div>
      )}

      {(profile.themes || []).length > 0 && (
        <div className="sm:col-span-2 bg-[#0d0f1a] rounded-xl p-4 border border-[#1f2440]">
          <div className="text-xs text-[#5c6391] mb-2">Theme Hints</div>
          <div className="flex flex-wrap gap-2">
            {profile.themes.map((t) => (
              <span key={t} className="px-3 py-1 bg-[#1f2440] rounded-full text-xs text-[#9da3c8]">{t}</span>
            ))}
          </div>
        </div>
      )}

      {INTEL_TEXT_FIELDS.map(({ key, label }) => {
        const value = textVal((profile as any)[key])
        if (!value) return null
        return (
          <div key={key} className="bg-[#0d0f1a] rounded-xl p-4 border border-[#1f2440]">
            <div className="text-xs text-[#5c6391] mb-1">{label}</div>
            <p className="text-sm text-[#e8eaf6]">{value}</p>
          </div>
        )
      })}

      {INTEL_CHIP_FIELDS.map(({ key, label, danger }) => {
        const list: string[] = ((profile as any)[key] as string[]) || []
        if (!list.length) return null
        return (
          <div key={key} className="sm:col-span-2 bg-[#0d0f1a] rounded-xl p-4 border border-[#1f2440]">
            <div className="text-xs text-[#5c6391] mb-2">{label}</div>
            <div className="flex flex-wrap gap-2">
              {list.map((t) => (
                <span key={t} className={`px-3 py-1 rounded-full text-xs border ${danger ? 'bg-red-500/10 border-red-500/30 text-red-300' : 'bg-[#1f2440] border-transparent text-[#9da3c8]'}`}>{t}</span>
              ))}
            </div>
          </div>
        )
      })}

      {profile.intelligence_notes && (
        <div className="sm:col-span-2 bg-amber-500/5 rounded-xl p-4 border border-amber-500/20">
          <div className="flex items-center gap-1.5 text-xs text-amber-400 mb-1">
            <Sparkles className="w-3 h-3" />
            Story Intelligence Notes
          </div>
          <p className="text-sm text-[#9da3c8] italic">{profile.intelligence_notes}</p>
        </div>
      )}
    </div>
  )
}

export default function StoryIntakePage({ params }: { params: { id: string } }) {
  const { id: storyId } = params
  const router = useRouter()
  const queryClient = useQueryClient()

  // Saved-report lifecycle: loading → (view | edit). 'edit' is the first-time /
  // re-analyze flow; 'view' shows the previously saved Genre Detection report.
  const [loadingReport, setLoadingReport] = useState(true)
  const [reportError, setReportError] = useState(false)
  const [report, setReport] = useState<IntakeReport | null>(null)
  const [mode, setMode] = useState<'view' | 'edit'>('edit')
  const firstTimeRef = useRef(true)   // true when no saved report existed on load

  const [description, setDescription] = useState('')
  const [audienceHint, setAudienceHint] = useState('')
  const [analyzing, setAnalyzing] = useState(false)
  const [result, setResult] = useState<IntakeResponse | null>(null)
  const [overrides, setOverrides] = useState<Partial<GenreProfile>>({})
  const [confirming, setConfirming] = useState(false)

  const loadReport = async () => {
    setLoadingReport(true)
    setReportError(false)
    try {
      const res = await intakeApi.getReport(storyId)
      const data = res.data as IntakeReport
      setReport(data)
      if (data?.exists && data.genre_profile) {
        firstTimeRef.current = false
        setMode('view')
        setDescription(data.raw_description || '')
      } else {
        firstTimeRef.current = true
        setMode('edit')
      }
    } catch {
      setReportError(true)
    } finally {
      setLoadingReport(false)
    }
  }

  useEffect(() => { loadReport() }, [storyId]) // eslint-disable-line react-hooks/exhaustive-deps

  const analyze = async () => {
    if (description.trim().length < 20) return toast.error('Please write at least 20 characters about your story')
    setAnalyzing(true)
    try {
      const res = await intakeApi.analyze(storyId, description, audienceHint || undefined)
      setResult(res.data)
      setOverrides({})
    } catch (err: any) {
      // Surface the backend's meaningful message (validation 400 / AI 503).
      // `detail` is a string for our HTTPExceptions; tolerate FastAPI's array
      // shape too, and fall back only when nothing useful is available.
      const detail = err?.response?.data?.detail
      const message =
        typeof detail === 'string'
          ? detail
          : Array.isArray(detail)
            ? (detail[0]?.msg ?? 'Analysis failed. Please try again.')
            : 'Analysis failed. Please try again.'
      toast.error(message)
    } finally {
      setAnalyzing(false)
    }
  }

  const confirm = async () => {
    if (!result) return
    setConfirming(true)
    try {
      await intakeApi.confirm(storyId, result.intake_id, overrides)
      // Keep AI-tool defaults and the saved report in sync with the new profile.
      queryClient.invalidateQueries({ queryKey: ['genre-profile', storyId] })
      const wasFirstTime = firstTimeRef.current
      if (wasFirstTime) {
        toast.success('Genre profile saved! Opening your editor…')
        router.push(`/projects/${storyId}`)
      } else {
        toast.success('Genre profile updated.')
        setResult(null)
        await loadReport()   // returns to the saved 'view' with the fresh report
      }
    } catch {
      toast.error('Failed to save. Please try again.')
    } finally {
      setConfirming(false)
    }
  }

  const startReanalyze = () => {
    setResult(null)
    setOverrides({})
    setMode('edit')
  }

  const openEditor = () => router.push(`/projects/${storyId}`)
  const skip = () => router.push(`/projects/${storyId}`)

  const profile = result ? { ...result.genre_profile, ...overrides } : null

  return (
    // Own scroll inside StudioShell's overflow-hidden main; sticky nav.
    <div className="h-full overflow-y-auto bg-[#0d0f1a]">
      <nav className="sticky top-0 z-20 bg-[#0d0f1a] border-b border-[#1f2440]">
        <div className="max-w-4xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Feather className="w-5 h-5 text-amber-500" />
            <span className="font-semibold text-sm">Story Intake</span>
          </div>
          <button onClick={skip} className="text-sm text-[#5c6391] hover:text-[#9da3c8]">
            {mode === 'view' ? 'Back to editor →' : 'Skip for now →'}
          </button>
        </div>
      </nav>

      <div className="max-w-4xl mx-auto px-6 pt-10 pb-16">
        {/* ── Loading saved report ─────────────────────────────────────────── */}
        {loadingReport ? (
          <div className="flex flex-col items-center justify-center gap-3 py-24 text-[#5c6391]">
            <Loader2 className="w-6 h-6 animate-spin" />
            <p className="text-sm">Loading your genre profile…</p>
          </div>
        ) : reportError ? (
          <div className="flex flex-col items-center justify-center gap-3 py-24">
            <AlertCircle className="w-6 h-6 text-red-300" />
            <p className="text-sm text-[#9da3c8]">Couldn’t load your saved report.</p>
            <button onClick={loadReport} className="text-sm px-3 py-1.5 rounded-lg border border-[#2e3454] text-[#9da3c8] hover:border-[#3d4466]">
              Retry
            </button>
          </div>
        ) : mode === 'view' && report?.exists && report.genre_profile ? (
          /* ── Saved report view ──────────────────────────────────────────── */
          <div className="space-y-5">
            <div className="text-center mb-6">
              <div className="inline-flex items-center gap-2 bg-amber-500/10 border border-amber-500/30 rounded-full px-4 py-1.5 text-sm text-amber-400 mb-4">
                <Check className="w-4 h-4" />
                Saved Genre Profile
              </div>
              <h1 className="text-3xl font-bold mb-3">Your story’s genre intelligence</h1>
              <p className="text-[#9da3c8] max-w-xl mx-auto">
                This is the saved profile your AI tools use. Review it, or re-run detection to update it.
              </p>
            </div>

            <div className="bg-[#13162a] border border-amber-500/30 rounded-2xl p-8">
              <div className="flex items-center gap-2 text-amber-400 mb-6">
                <Sparkles className="w-4 h-4" />
                <span className="text-sm font-medium">Genre Detection {report.confirmed ? 'Confirmed' : 'Saved'}</span>
                {typeof report.genre_profile.confidence === 'number' && (
                  <span className="text-xs text-[#5c6391] ml-auto">
                    Confidence: {Math.round((report.genre_profile.confidence || 0.85) * 100)}%
                  </span>
                )}
              </div>
              <ProfileReadout profile={report.genre_profile} />
            </div>

            <div className="flex gap-4">
              <button
                onClick={startReanalyze}
                className="flex-1 border border-[#2e3454] text-[#9da3c8] py-3 rounded-xl text-sm hover:border-[#3d4466] transition-colors flex items-center justify-center gap-2"
              >
                <RefreshCw className="w-4 h-4" />
                Re-run Genre Detection
              </button>
              <button
                onClick={openEditor}
                className="flex-1 bg-amber-500 hover:bg-amber-600 text-black font-semibold py-3 rounded-xl text-sm transition-colors flex items-center justify-center gap-2"
              >
                <BookOpen className="w-4 h-4" />
                Open Editor
              </button>
            </div>
          </div>
        ) : (
          /* ── First-time / re-analyze flow ───────────────────────────────── */
          <>
            <div className="text-center mb-10">
              <div className="inline-flex items-center gap-2 bg-amber-500/10 border border-amber-500/30 rounded-full px-4 py-1.5 text-sm text-amber-400 mb-4">
                <Sparkles className="w-4 h-4" />
                AI Genre Intelligence
              </div>
              <h1 className="text-3xl font-bold mb-3">
                {report?.exists ? 'Re-run genre detection' : 'Tell us about your story'}
              </h1>
              <p className="text-[#9da3c8] max-w-xl mx-auto">
                {report?.exists
                  ? 'Update your story idea and we’ll regenerate the genre profile. Your current profile stays until you confirm.'
                  : 'Describe your story idea and AI will detect your genre, tone, audience, and story structure — making every AI tool genre-aware from the start.'}
              </p>
            </div>

            {!result ? (
              <div className="bg-[#13162a] border border-[#1f2440] rounded-2xl p-8">
                <div className="mb-6">
                  <label className="block text-sm font-medium text-[#9da3c8] mb-2">Your Story Idea</label>
                  <textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="Describe your story idea, plot, characters, setting, or themes. Even a rough paragraph helps."
                    rows={8}
                    className="w-full bg-[#0d0f1a] border border-[#2e3454] rounded-xl px-4 py-3 text-sm text-[#e8eaf6] placeholder-[#3d4466] focus:outline-none focus:border-amber-500 transition-colors resize-none font-serif"
                  />
                  <div className="flex justify-between mt-1">
                    <span className="text-xs text-[#3d4466]">Minimum 20 characters</span>
                    <span className={`text-xs ${description.length >= 20 ? 'text-amber-400' : 'text-[#3d4466]'}`}>
                      {description.length} chars
                    </span>
                  </div>
                </div>

                <div className="mb-8">
                  <label className="block text-sm font-medium text-[#9da3c8] mb-2">
                    Target Audience <span className="text-[#3d4466]">(optional)</span>
                  </label>
                  <div className="flex gap-3 flex-wrap">
                    {['', 'children', 'ya', 'adult'].map((a) => (
                      <button
                        key={a}
                        onClick={() => setAudienceHint(a)}
                        className={`px-4 py-2 rounded-lg text-sm border transition-colors ${
                          audienceHint === a
                            ? 'border-amber-500 bg-amber-500/10 text-amber-400'
                            : 'border-[#2e3454] text-[#5c6391] hover:border-[#3d4466]'
                        }`}
                      >
                        {a === '' ? 'Let AI Decide' : a === 'ya' ? 'Young Adult' : a.charAt(0).toUpperCase() + a.slice(1)}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="flex gap-3">
                  {report?.exists && (
                    <button
                      onClick={() => { setMode('view'); setResult(null) }}
                      className="px-4 border border-[#2e3454] text-[#9da3c8] py-3.5 rounded-xl hover:border-[#3d4466] transition-colors text-sm"
                    >
                      Cancel
                    </button>
                  )}
                  <button
                    onClick={analyze}
                    disabled={analyzing || description.trim().length < 20}
                    className="flex-1 bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-black font-semibold py-3.5 rounded-xl transition-colors flex items-center justify-center gap-2"
                  >
                    {analyzing
                      ? <><Loader2 className="w-4 h-4 animate-spin" />Analyzing your story…</>
                      : <><Sparkles className="w-4 h-4" />Analyze My Story</>}
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-y-5 animate-slide-up">
                <div className="bg-[#13162a] border border-amber-500/30 rounded-2xl p-8">
                  <div className="flex items-center gap-2 text-amber-400 mb-6">
                    <Sparkles className="w-4 h-4" />
                    <span className="text-sm font-medium">AI Genre Detection Complete</span>
                    <span className="text-xs text-[#5c6391] ml-auto">
                      Confidence: {Math.round((result.genre_profile.confidence || 0.85) * 100)}%
                    </span>
                  </div>

                  <div className="grid sm:grid-cols-2 gap-5">
                    {[
                      { label: 'Primary Genre', field: 'genre', value: profile?.genre },
                      { label: 'Sub-Genre', field: 'sub_genre', value: profile?.sub_genre },
                      { label: 'Target Audience', field: 'audience', value: profile?.audience },
                      { label: 'Emotional Direction', field: 'conflict', value: profile?.conflict },
                    ].map((item) => (
                      <div key={item.field} className="bg-[#0d0f1a] rounded-xl p-4 border border-[#1f2440]">
                        <div className="text-xs text-[#5c6391] mb-1">{item.label}</div>
                        <input
                          value={(overrides as any)[item.field] ?? item.value ?? ''}
                          onChange={(e) => setOverrides((o) => ({ ...o, [item.field]: e.target.value }))}
                          className="w-full bg-transparent text-[#e8eaf6] font-medium text-sm focus:outline-none border-b border-transparent hover:border-[#2e3454] focus:border-amber-500 transition-colors pb-0.5"
                        />
                        {(overrides as any)[item.field] && (overrides as any)[item.field] !== item.value && (
                          <div className="flex items-center gap-1 mt-1">
                            <Edit3 className="w-3 h-3 text-amber-400" />
                            <span className="text-xs text-amber-400">Edited</span>
                          </div>
                        )}
                      </div>
                    ))}

                    <div className="sm:col-span-2 bg-[#0d0f1a] rounded-xl p-4 border border-[#1f2440]">
                      <div className="text-xs text-[#5c6391] mb-2">Tone</div>
                      <div className="flex flex-wrap gap-2">
                        {(profile?.tone || []).map((t: string) => (
                          <span key={t} className="px-3 py-1 bg-amber-500/10 border border-amber-500/30 rounded-full text-xs text-amber-400">{t}</span>
                        ))}
                      </div>
                    </div>

                    <div className="sm:col-span-2 bg-[#0d0f1a] rounded-xl p-4 border border-[#1f2440]">
                      <div className="text-xs text-[#5c6391] mb-1">Suggested Structure</div>
                      <p className="text-sm text-[#e8eaf6]">{profile?.structure}</p>
                    </div>

                    {profile?.writing_direction && (
                      <div className="sm:col-span-2 bg-[#0d0f1a] rounded-xl p-4 border border-[#1f2440]">
                        <div className="text-xs text-[#5c6391] mb-1">Writing Direction Notes</div>
                        <p className="text-sm text-[#9da3c8] italic">{profile.writing_direction}</p>
                      </div>
                    )}

                    <div className="sm:col-span-2 bg-[#0d0f1a] rounded-xl p-4 border border-[#1f2440]">
                      <div className="text-xs text-[#5c6391] mb-2">Theme Hints</div>
                      <div className="flex flex-wrap gap-2">
                        {(profile?.themes || []).map((t: string) => (
                          <span key={t} className="px-3 py-1 bg-[#1f2440] rounded-full text-xs text-[#9da3c8]">{t}</span>
                        ))}
                      </div>
                    </div>

                    {INTEL_TEXT_FIELDS.map(({ key, label }) => {
                      const value = (profile as any)?.[key]
                      if (!value) return null
                      return (
                        <div key={key} className="bg-[#0d0f1a] rounded-xl p-4 border border-[#1f2440]">
                          <div className="text-xs text-[#5c6391] mb-1">{label}</div>
                          <p className="text-sm text-[#e8eaf6]">{value}</p>
                        </div>
                      )
                    })}

                    {INTEL_CHIP_FIELDS.map(({ key, label, danger }) => {
                      const list: string[] = (profile as any)?.[key] || []
                      if (!list.length) return null
                      return (
                        <div key={key} className="sm:col-span-2 bg-[#0d0f1a] rounded-xl p-4 border border-[#1f2440]">
                          <div className="text-xs text-[#5c6391] mb-2">{label}</div>
                          <div className="flex flex-wrap gap-2">
                            {list.map((t) => (
                              <span key={t} className={`px-3 py-1 rounded-full text-xs border ${danger ? 'bg-red-500/10 border-red-500/30 text-red-300' : 'bg-[#1f2440] border-transparent text-[#9da3c8]'}`}>{t}</span>
                            ))}
                          </div>
                        </div>
                      )
                    })}

                    {profile?.intelligence_notes && (
                      <div className="sm:col-span-2 bg-amber-500/5 rounded-xl p-4 border border-amber-500/20">
                        <div className="flex items-center gap-1.5 text-xs text-amber-400 mb-1">
                          <Sparkles className="w-3 h-3" />
                          Story Intelligence Notes
                        </div>
                        <p className="text-sm text-[#9da3c8] italic">{profile.intelligence_notes}</p>
                      </div>
                    )}
                  </div>

                  <p className="text-xs text-[#5c6391] mt-4 flex items-center gap-1">
                    <Edit3 className="w-3 h-3" />
                    Click any field to edit. AI suggestions are starting points — you have full control.
                  </p>
                </div>

                <div className="flex gap-4">
                  <button
                    onClick={() => setResult(null)}
                    className="flex-1 border border-[#2e3454] text-[#9da3c8] py-3 rounded-xl text-sm hover:border-[#3d4466] transition-colors"
                  >
                    ← Regenerate
                  </button>
                  <button
                    onClick={confirm}
                    disabled={confirming}
                    className="flex-1 bg-amber-500 hover:bg-amber-600 text-black font-semibold py-3 rounded-xl text-sm transition-colors flex items-center justify-center gap-2"
                  >
                    {confirming ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                    {firstTimeRef.current ? 'Confirm & Open Editor' : 'Save Updated Profile'}
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
