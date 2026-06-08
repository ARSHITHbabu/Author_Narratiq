'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Sparkles, Loader2, ChevronRight, Edit3, Check, Feather } from 'lucide-react'
import { intakeApi } from '@/lib/api'
import { GenreProfile, IntakeResponse } from '@/lib/types'
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

export default function StoryIntakePage({ params }: { params: { id: string } }) {
  const { id: storyId } = params
  const router = useRouter()
  const [description, setDescription] = useState('')
  const [audienceHint, setAudienceHint] = useState('')
  const [analyzing, setAnalyzing] = useState(false)
  const [result, setResult] = useState<IntakeResponse | null>(null)
  const [overrides, setOverrides] = useState<Partial<GenreProfile>>({})
  const [confirming, setConfirming] = useState(false)

  const analyze = async () => {
    if (description.trim().length < 20) return toast.error('Please write at least 20 characters about your story')
    setAnalyzing(true)
    try {
      const res = await intakeApi.analyze(storyId, description, audienceHint || undefined)
      setResult(res.data)
    } catch {
      toast.error('Analysis failed. Please try again.')
    } finally {
      setAnalyzing(false)
    }
  }

  const confirm = async () => {
    if (!result) return
    setConfirming(true)
    try {
      await intakeApi.confirm(storyId, result.intake_id, overrides)
      toast.success('Genre profile saved! Opening your editor...')
      router.push(`/projects/${storyId}`)
    } catch {
      toast.error('Failed to save. Please try again.')
    } finally {
      setConfirming(false)
    }
  }

  const skip = () => router.push(`/projects/${storyId}`)

  const profile = result ? { ...result.genre_profile, ...overrides } : null

  return (
    <div className="min-h-screen bg-[#0d0f1a]">
      {/* Nav */}
      <nav className="fixed top-0 left-0 right-0 z-50 bg-[#0d0f1a] border-b border-[#1f2440]">
        <div className="max-w-4xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Feather className="w-5 h-5 text-amber-500" />
            <span className="font-semibold text-sm">Story Intake</span>
          </div>
          <button onClick={skip} className="text-sm text-[#5c6391] hover:text-[#9da3c8]">
            Skip for now →
          </button>
        </div>
      </nav>

      <div className="max-w-4xl mx-auto px-6 pt-24 pb-16">
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-2 bg-amber-500/10 border border-amber-500/30 rounded-full px-4 py-1.5 text-sm text-amber-400 mb-4">
            <Sparkles className="w-4 h-4" />
            AI Genre Intelligence
          </div>
          <h1 className="text-3xl font-bold mb-3">Tell us about your story</h1>
          <p className="text-[#9da3c8] max-w-xl mx-auto">
            Describe your story idea and AI will detect your genre, tone, audience, and story structure —
            making every AI tool genre-aware from the start.
          </p>
        </div>

        {!result ? (
          <div className="bg-[#13162a] border border-[#1f2440] rounded-2xl p-8">
            <div className="mb-6">
              <label className="block text-sm font-medium text-[#9da3c8] mb-2">
                Your Story Idea
              </label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Describe your story idea, plot, characters, setting, or themes. Even a rough paragraph helps.&#10;&#10;Example: A family moves into an old Victorian house. Strange sounds at night. The daughter starts drawing figures she's never seen. The father finds journals in the basement..."
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

            <button
              onClick={analyze}
              disabled={analyzing || description.trim().length < 20}
              className="w-full bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-black font-semibold py-3.5 rounded-xl transition-colors flex items-center justify-center gap-2"
            >
              {analyzing ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Analyzing your story...
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4" />
                  Analyze My Story
                </>
              )}
            </button>
          </div>
        ) : (
          <div className="space-y-5 animate-slide-up">
            {/* Genre Card */}
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
                      <span key={t} className="px-3 py-1 bg-amber-500/10 border border-amber-500/30 rounded-full text-xs text-amber-400">
                        {t}
                      </span>
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
                      <span key={t} className="px-3 py-1 bg-[#1f2440] rounded-full text-xs text-[#9da3c8]">
                        {t}
                      </span>
                    ))}
                  </div>
                </div>

                {/* ── Richer Story Intelligence — rendered dynamically ──────── */}
                {/* Single-value craft fields: only shown when the backend returns them */}
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

                {/* Chip/array fields: only shown when non-empty */}
                {INTEL_CHIP_FIELDS.map(({ key, label, danger }) => {
                  const list: string[] = (profile as any)?.[key] || []
                  if (!list.length) return null
                  return (
                    <div key={key} className="sm:col-span-2 bg-[#0d0f1a] rounded-xl p-4 border border-[#1f2440]">
                      <div className="text-xs text-[#5c6391] mb-2">{label}</div>
                      <div className="flex flex-wrap gap-2">
                        {list.map((t) => (
                          <span
                            key={t}
                            className={`px-3 py-1 rounded-full text-xs border ${
                              danger
                                ? 'bg-red-500/10 border-red-500/30 text-red-300'
                                : 'bg-[#1f2440] border-transparent text-[#9da3c8]'
                            }`}
                          >
                            {t}
                          </span>
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
                Confirm & Open Editor
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
