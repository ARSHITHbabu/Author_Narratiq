// Phase 3 generation controls — the single source of truth for which tools
// accept `controls`, the author-facing names of every Phase 3 option, and how
// a controls payload is built. Mirrors lib/transforms.ts's role for options.
//
// The client never decides a limit or an ownership rule: it builds the request
// and renders what the server returns (spec §21.3).

import type { DerivationIntent, GenerationControls, PreserveRuleKey, PreserveValue, StyleMatch } from './types'
import type { GroupId } from './transforms'

/** Phase 3 UI is on unless explicitly switched off at build time (rollback
 *  switch, spec §36.3). NEXT_PUBLIC_* is inlined at build — a change needs a rebuild. */
export const P3_ENABLED = process.env.NEXT_PUBLIC_P3_ENABLED !== 'false'

/** Tools whose backend request accepts `controls` (the Stage 5 constrained
 *  pipeline). Refine, author style and translate keep their existing behaviour. */
export const CONTROLLABLE_GROUPS: GroupId[] = ['tone', 'emotion', 'age_adapt', 'style']

export const DERIVATIONS: { id: DerivationIntent; label: string; needs?: string; hint: string }[] = [
  { id: 'variation', label: 'Make a variation', hint: 'Same idea, genuinely different wording' },
  { id: 'improve', label: 'Improve this', hint: 'Tighter craft, same events' },
  { id: 'continue', label: 'Continue from here', hint: 'Carry on in the same voice' },
  { id: 'keep_structure_change_ending', label: 'Keep structure, change the ending', needs: 'The new ending', hint: '' },
  { id: 'keep_idea_change_tone', label: 'Keep the idea, change the tone', needs: 'New tone (e.g. hopeful)', hint: '' },
  { id: 'expand', label: 'Make it longer', hint: 'Deepen what is there — no new events' },
  { id: 'condense', label: 'Make it shorter', hint: 'Keep every plot fact' },
  { id: 'custom', label: 'Custom instruction…', needs: 'Your instruction', hint: '' },
]

export const PRESERVE_RULES: { key: PreserveRuleKey; label: string; help: string }[] = [
  { key: 'character_names', label: 'Character names', help: 'Names and nicknames stay exactly as you wrote them.' },
  { key: 'tone', label: 'Your narrative voice', help: 'Only the requested change is made.' },
  { key: 'tense', label: 'Tense', help: 'Past stays past, present stays present.' },
  { key: 'pov', label: 'Point of view', help: 'First, second or third person is kept.' },
  { key: 'dialogue_meaning', label: 'What characters say', help: 'Lines of dialogue keep their meaning.' },
  { key: 'timeline', label: 'Timeline', help: 'No new “later”, “yesterday”, dates or days.' },
  { key: 'story_facts', label: 'Established story facts', help: 'Uses your Story Intelligence facts as rules.' },
]

export const PRESERVE_LEVELS: { value: PreserveValue; label: string; help: string }[] = [
  { value: true, label: 'Keep', help: 'Told to the AI and checked afterwards; one automatic retry if broken.' },
  { value: 'warn', label: 'Check', help: 'Checked afterwards and flagged — the AI is not told.' },
  { value: false, label: 'Off', help: 'Not checked.' },
]

export const STYLE_MATCH_LEVELS: { value: StyleMatch; label: string; help: string }[] = [
  { value: 'off', label: 'Off', help: 'No voice matching.' },
  { value: 'light', label: 'Match my voice', help: 'Uses your measured prose fingerprint.' },
  { value: 'strong', label: 'Match my voice closely', help: 'Fingerprint, your style samples and the surrounding text.' },
]

export interface ControlsInput {
  contextPinIds?: string[]
  avoidPinIds?: string[]
  avoidTexts?: string[]
  basePinId?: string
  derivation?: DerivationIntent
  derivationParam?: string
  styleMatch?: StyleMatch
  localContext?: { before: string; after: string }
  instruction?: string
}

/** Builds a `controls` object with empty fields dropped. Sending `{}` still
 *  opts into Phase 3 behaviour (project preferences, consistency, voice). */
export function buildControls(input: ControlsInput = {}): GenerationControls {
  const c: GenerationControls = {}
  if (input.contextPinIds?.length) c.context_pin_ids = [...new Set(input.contextPinIds)]
  if (input.avoidPinIds?.length) c.avoid_pin_ids = [...new Set(input.avoidPinIds)].slice(0, 8)
  if (input.avoidTexts?.length) c.avoid_texts = input.avoidTexts.filter((t) => t.trim()).map((t) => t.slice(0, 240)).slice(-8)
  if (input.basePinId) {
    c.base_pin_id = input.basePinId
    c.derivation = input.derivation ?? 'variation'
    if (input.derivationParam?.trim()) c.derivation_param = input.derivationParam.trim().slice(0, 300)
  }
  if (input.styleMatch) c.style_match = input.styleMatch
  if (input.localContext && (input.localContext.before || input.localContext.after)) {
    c.local_context = {
      before: input.localContext.before.split(/\s+/).slice(-120).join(' ').slice(-1200),
      after: input.localContext.after.split(/\s+/).slice(0, 120).join(' ').slice(0, 1200),
    }
  }
  if (input.instruction?.trim()) c.instruction = input.instruction.trim().slice(0, 600)
  return c
}

/** SHA-256 hex of text, for pin source tracking (detects "source changed since"). */
export async function sha256Hex(text: string): Promise<string> {
  if (typeof crypto === 'undefined' || !crypto.subtle) return ''
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text))
  return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, '0')).join('')
}

/** Author-facing time-to-expiry, e.g. "expires in 6 days", "expires tomorrow". */
export function expiryLabel(expiresAt: string, now: Date = new Date()): { text: string; soon: boolean } {
  const ms = new Date(expiresAt.endsWith('Z') ? expiresAt : `${expiresAt}Z`).getTime() - now.getTime()
  const hours = ms / 3_600_000
  if (hours <= 0) return { text: 'expired', soon: true }
  if (hours < 24) return { text: `expires in ${Math.max(1, Math.round(hours))} h`, soon: true }
  const days = Math.round(hours / 24)
  if (days === 1) return { text: 'expires tomorrow', soon: true }
  return { text: `expires in ${days} days`, soon: hours < 48 }
}

export const TOOL_LABELS: Record<string, string> = {
  refine: 'Refine', tone: 'Tone', emotion: 'Emotion', age_adapt: 'Audience', style: 'Style',
  author_style: 'Author style', translate: 'Translation', continuation: 'Continuation',
  outline: 'Outline', plot_suggestion: 'Plot idea', segment_regen: 'Partial rewrite', merge: 'Merge',
}

export const IDEA_TYPES: { id: string; label: string }[] = [
  { id: 'future_scene', label: 'Future scene' },
  { id: 'dialogue_idea', label: 'Dialogue' },
  { id: 'plot_twist', label: 'Plot twist' },
  { id: 'character_idea', label: 'Character idea' },
  { id: 'research', label: 'Research' },
  { id: 'ending_idea', label: 'Ending' },
  { id: 'worldbuilding', label: 'Worldbuilding' },
  { id: 'style_sample', label: 'Style sample (my voice)' },
]
export const IDEA_TYPE_IDS = IDEA_TYPES.map((t) => t.id)

/** Error text for the author from a Phase 3 API error (flat {detail, code}). */
export function apiErrorText(e: unknown, fallback: string): string {
  const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof d === 'string' && d.trim() ? d : fallback
}
