// Stage 12 A10 — how a character is present in the story, in author language.
// Separate from life status: a historical figure is usually deceased, a
// referenced one may be alive, and an on-page character can die in the story.
import type { CharacterPresence } from './types'

export const PRESENCE_OPTIONS: { value: CharacterPresence; label: string; hint: string }[] = [
  { value: 'on_page',    label: 'On page',        hint: 'Appears in scenes — acts or speaks' },
  { value: 'referenced', label: 'Mentioned only', hint: 'Talked about but never appears in a scene' },
  { value: 'historical', label: 'In the past',    hint: "Belongs to the story's past — remembered or recounted" },
]

export const presenceLabel = (p?: CharacterPresence | null) =>
  PRESENCE_OPTIONS.find((o) => o.value === p)?.label ?? null

/** True for figures the author should look at before adding to the cast. */
export const isOffPage = (p?: CharacterPresence | null) => p === 'referenced' || p === 'historical'
