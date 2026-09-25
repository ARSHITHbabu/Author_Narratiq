'use client'

// "What the AI must not change" — this story's project defaults (P3-05) plus
// the voice-matching level (P3-10) and two opt-ins (strict consistency, plan-
// gated; one automatic retry on a near-duplicate, off by default — D6, D12).
//
// Saved per story on the server; every Tone / Emotion / Audience / Style run
// uses them unless a single run overrides them.

import { useEffect, useState } from 'react'
import { ShieldCheck, Loader2, ChevronDown, ChevronRight } from 'lucide-react'
import { toast } from 'sonner'
import { aiPrefsApi } from '@/lib/api'
import { PRESERVE_LEVELS, PRESERVE_RULES, STYLE_MATCH_LEVELS, apiErrorText } from '@/lib/generationControls'
import type { AiPreferences, PreserveRuleKey, PreserveValue, StyleMatch } from '@/lib/types'

export default function PreservationRulesPopover({ storyId }: { storyId: string }) {
  const [open, setOpen] = useState(false)
  const [prefs, setPrefs] = useState<AiPreferences | null>(null)
  const [state, setState] = useState<'idle' | 'loading' | 'saving' | 'error'>('idle')
  const [notes, setNotes] = useState('')

  useEffect(() => {
    if (!open || prefs) return
    setState('loading')
    aiPrefsApi.get(storyId)
      .then((r) => { setPrefs(r.data); setNotes(r.data.author_notes); setState('idle') })
      .catch(() => setState('error'))
  }, [open, prefs, storyId])

  const save = async (patch: Record<string, unknown>, ok = 'Saved') => {
    setState('saving')
    try {
      const r = await aiPrefsApi.update(storyId, patch)
      setPrefs(r.data); setState('idle'); toast.success(ok)
    } catch (e) {
      setState('idle'); toast.error(apiErrorText(e, 'Your AI settings could not be saved. Nothing was changed.'))
    }
  }

  const ruleValue = (key: PreserveRuleKey): PreserveValue => {
    if (!prefs) return false
    if (key === 'character_names') return prefs.preserve_character_names
    if (key === 'tone') return prefs.preserve_tone
    return prefs.preserve_rules[key]
  }
  const setRule = (key: PreserveRuleKey, v: PreserveValue) => {
    if (key === 'character_names') return save({ preserve_character_names: v !== false })
    if (key === 'tone') return save({ preserve_tone: v !== false })
    return save({ preserve_rules: { [key]: v } })
  }
  const binary = (key: PreserveRuleKey) => key === 'character_names' || key === 'tone'

  return (
    <div className="rounded-xl border border-[#1f2440]" data-testid="ai-rules">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
        className="w-full flex items-center gap-1.5 px-3 py-2 text-[11px] text-[#cdd2f0]">
        <ShieldCheck className="w-3.5 h-3.5 text-amber-400" />
        What the AI must keep · your voice
        {open ? <ChevronDown className="w-3 h-3 ml-auto" /> : <ChevronRight className="w-3 h-3 ml-auto" />}
      </button>
      {open && (
        <div className="px-3 pb-3 space-y-3 text-[11px]">
          {state === 'loading' && <Loader2 className="w-4 h-4 animate-spin text-[#5c6391]" />}
          {state === 'error' && <p className="text-red-300">These settings could not be loaded. The AI keeps using its safe defaults (character names and your voice are protected).</p>}
          {prefs && (
            <>
              <p className="text-[#5c6391]">Applies to Tone, Emotion, Audience and Style for this story.</p>
              <ul className="space-y-1.5">
                {PRESERVE_RULES.map((r) => (
                  <li key={r.key} className="flex items-center gap-2">
                    <span className="flex-1" title={r.help}>{r.label}</span>
                    <div role="radiogroup" aria-label={r.label} className="flex gap-0.5">
                      {PRESERVE_LEVELS.filter((l) => !binary(r.key) || l.value !== 'warn').map((l) => (
                        <button key={String(l.value)} role="radio" aria-checked={ruleValue(r.key) === l.value}
                          disabled={state === 'saving'} title={l.help} onClick={() => setRule(r.key, l.value)}
                          className={`px-1.5 py-0.5 rounded ${ruleValue(r.key) === l.value ? 'bg-amber-500/20 text-amber-300' : 'text-[#9da3c8] hover:bg-[#1f2440]'}`}>
                          {l.label}
                        </button>
                      ))}
                    </div>
                  </li>
                ))}
              </ul>
              <p className="text-[10px] text-[#5c6391]">“Check” flags a problem without telling the AI. Nothing is ever rewritten for you — warnings appear on the result.</p>

              <div>
                <p className="text-[#9da3c8] mb-1">Voice matching</p>
                <div role="radiogroup" aria-label="Voice matching" className="flex gap-1 flex-wrap">
                  {STYLE_MATCH_LEVELS.map((l) => (
                    <button key={l.value} role="radio" aria-checked={prefs.style_prefs.match_level === l.value} title={l.help}
                      onClick={() => save({ style_prefs: { match_level: l.value as StyleMatch } })}
                      className={`px-2 py-0.5 rounded border ${prefs.style_prefs.match_level === l.value ? 'border-amber-500/50 text-amber-300' : 'border-[#2e3454] text-[#9da3c8]'}`}>
                      {l.label}
                    </button>
                  ))}
                </div>
                {!prefs.story_dna_available && (
                  <p className="text-[10px] text-[#5c6391] mt-1">Run Story Intelligence to enable fingerprint matching — until then only the surrounding text is used.</p>
                )}
              </div>

              <label className="flex items-start gap-2">
                <input type="checkbox" checked={prefs.pin_prefs.strict_consistency} disabled={!prefs.strict_consistency_allowed}
                  onChange={(e) => save({ pin_prefs: { strict_consistency: e.target.checked } })} className="mt-0.5 accent-amber-500" />
                <span>Strict story-consistency check
                  <span className="block text-[10px] text-[#5c6391]">
                    {prefs.strict_consistency_allowed ? 'An extra AI check against your story facts — slower.' : 'Not included in your plan. The standard checks always run.'}
                  </span></span>
              </label>
              <label className="flex items-start gap-2">
                <input type="checkbox" checked={prefs.pin_prefs.duplicate_auto_retry}
                  onChange={(e) => save({ pin_prefs: { duplicate_auto_retry: e.target.checked } })} className="mt-0.5 accent-amber-500" />
                <span>Automatically retry once when a result repeats an idea I asked to avoid
                  <span className="block text-[10px] text-[#5c6391]">Off by default — each retry takes extra time.</span></span>
              </label>

              <div>
                <label htmlFor="ai-author-notes" className="text-[#9da3c8]">Your own rule for the AI (optional)</label>
                <textarea id="ai-author-notes" value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={1000} rows={2}
                  placeholder="e.g. Never use the word “suddenly”."
                  className="mt-1 w-full bg-[#0d0f1a] border border-[#2e3454] rounded px-2 py-1 text-[#e8eaf6] resize-none" />
                {notes !== prefs.author_notes && (
                  <button onClick={() => save({ author_notes: notes }, 'Rule saved')} className="mt-1 px-2 py-0.5 rounded border border-[#2e3454] hover:bg-[#1f2440]">Save rule</button>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
