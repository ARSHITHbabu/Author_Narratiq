// Voice action executor — maps a planned WorkflowNode's logical client_call
// ("<capability>.<action>") to the real, already-authenticated api.ts methods.
// This is the "frontend executes" half of the agent-plans/frontend-executes
// model: every call reuses existing endpoints, auth, ownership and rate limits.

import api, {
  projectsApi, chaptersApi, charactersApi, relationshipsApi, intakeApi, plotApi,
  aiApi, searchApi, analysisApi, exportApi, emotionalArcApi, duplicateScenesApi,
  styleDriftApi, continuityApi, continuationApi, outlineApi, voiceCheckApi,
  storyBibleApi, narrativeThreadsApi, pacingApi, ocrApi,
} from './api'
import type { WorkflowNode } from './types'

export interface VoiceActionContext {
  storyId: string
  navigate?: (url: string) => void
  editor?: {
    getSelectedText: () => string
    getFullText: () => string
    insertText: (text: string) => void
  } | null
  onOpenChapter?: (chapterId: string) => void
  onGuideUpload?: (kind: 'manuscript' | 'ocr' | 'audio') => void
  onLogout?: () => void
}

export interface VoiceActionResult {
  ok: boolean
  data?: unknown
  message?: string
}

const str = (v: unknown, d = ''): string => (typeof v === 'string' ? v : d)
const num = (v: unknown, d = 0): number => (typeof v === 'number' ? v : d)

async function downloadBlob(res: { data: Blob }, filename: string) {
  const url = window.URL.createObjectURL(res.data)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  window.URL.revokeObjectURL(url)
}

/**
 * Execute one planned node. Returns a normalized result the panel can render.
 * Mutating nodes are only ever reached AFTER the user confirms in the UI.
 */
export async function executeVoiceAction(
  node: WorkflowNode,
  ctx: VoiceActionContext,
): Promise<VoiceActionResult> {
  // Server-run nodes already carry their result inline.
  if (node.execution_locus === 'server' || !node.execution) {
    return { ok: true, data: node.result ?? undefined, message: node.user_message }
  }

  const call = node.execution.client_call || `${node.capability}.${node.action}`
  const a = node.execution.args || {}
  const storyId = str(a.story_id, ctx.storyId)

  try {
    switch (call) {
      // ── Project management ────────────────────────────────────────────────
      case 'project_mgmt.create': {
        const res = await projectsApi.create(str(a.title, 'Untitled Story'), str(a.description))
        const id = (res.data as { story_id?: string })?.story_id
        if (id && ctx.navigate) ctx.navigate(`/projects/${id}`)
        return { ok: true, data: res.data, message: 'Story created.' }
      }
      case 'project_mgmt.list':
        return { ok: true, data: (await projectsApi.list()).data }
      case 'project_mgmt.open':
        if (ctx.navigate) ctx.navigate(`/projects/${str(a.story_id, storyId)}`)
        return { ok: true, message: 'Opening story.' }
      case 'project_mgmt.rename':
        return { ok: true, data: (await projectsApi.update(storyId, { title: str(a.title) })).data, message: 'Renamed.' }
      case 'project_mgmt.delete':
        await projectsApi.delete(str(a.story_id, storyId))
        if (ctx.navigate) ctx.navigate('/projects')
        return { ok: true, message: 'Story deleted.' }

      // ── Chapters ──────────────────────────────────────────────────────────
      case 'chapter_mgmt.create':
        return { ok: true, data: (await chaptersApi.create(storyId, str(a.title, 'New Chapter'), str(a.content))).data, message: 'Chapter created.' }
      case 'chapter_mgmt.open':
        if (ctx.onOpenChapter) ctx.onOpenChapter(str(a.chapter_id))
        return { ok: true, message: 'Opening chapter.' }
      case 'chapter_mgmt.edit':
        return { ok: true, data: (await chaptersApi.update(storyId, str(a.chapter_id), { content: str(a.content) })).data, message: 'Chapter updated.' }
      case 'chapter_mgmt.versions':
        return { ok: true, data: (await chaptersApi.versions(storyId, str(a.chapter_id))).data }
      case 'chapter_mgmt.delete':
        await chaptersApi.delete(storyId, str(a.chapter_id))
        return { ok: true, message: 'Chapter deleted.' }
      case 'chapter_mgmt.restore': {
        const v = await chaptersApi.getVersion(storyId, str(a.chapter_id), str(a.version_id))
        const content = (v.data as { content?: string })?.content ?? ''
        return { ok: true, data: (await chaptersApi.update(storyId, str(a.chapter_id), { content })).data, message: 'Version restored.' }
      }
      case 'chapter_mgmt.sync':
        return { ok: true, data: (await api.post(`/api/stories/${storyId}/chapters/sync-summaries`)).data, message: 'Summaries synced.' }

      // ── Characters ────────────────────────────────────────────────────────
      case 'character_mgmt.create':
        return { ok: true, data: (await charactersApi.create(storyId, { name: str(a.name), role: str(a.role, 'supporting'), status: str(a.status, 'active') })).data, message: 'Character created.' }
      case 'character_mgmt.update':
        return { ok: true, data: (await charactersApi.update(storyId, str(a.character_id), a)).data, message: 'Character updated.' }
      case 'character_mgmt.generate_cast':
        return { ok: true, data: (await charactersApi.generateCast(storyId)).data }
      case 'character_mgmt.search':
        if (a.character_id) return { ok: true, data: (await charactersApi.getMentions(storyId, str(a.character_id))).data }
        return { ok: true, data: (await charactersApi.search(storyId, { q: str(a.query) })).data }
      case 'character_mgmt.graph':
        return { ok: true, data: (await charactersApi.graph(storyId)).data }
      case 'character_mgmt.relationships':
        return { ok: true, data: (await relationshipsApi.list(storyId, str(a.character_id))).data }
      case 'character_voice_check.analyze':
        return { ok: true, data: (await voiceCheckApi.check(storyId, str(a.character_id))).data }

      // ── Intake / genre ────────────────────────────────────────────────────
      case 'intake_genre.analyze':
        return { ok: true, data: (await intakeApi.analyze(storyId, str(a.description))).data }
      case 'intake_genre.confirm':
        return { ok: true, data: (await intakeApi.confirm(storyId, str(a.intake_id))).data, message: 'Intake confirmed.' }
      case 'intake_genre.get':
        return { ok: true, data: (await intakeApi.getGenreProfile(storyId)).data }

      // ── Plot assistant (brainstorming only) ───────────────────────────────
      // Pass the current visible chapter text from the editor (context priority 2)
      // so the plot feature is grounded — fixes the empty-context bug.
      case 'plot_assistant.brainstorm': {
        const chapterText = ctx.editor?.getFullText?.() || str(a.current_chapter_text)
        return { ok: true, data: (await plotApi.suggest(storyId, str(a.question), chapterText, undefined, num(a.chapter_number, undefined as unknown as number))).data }
      }

      // ── Text transforms ───────────────────────────────────────────────────
      case 'text_transform.refine':
        return { ok: true, data: (await aiApi.refine(str(a.text), 'standard', storyId, str(a.chapter_id))).data }
      case 'text_transform.tone':
        return { ok: true, data: (await aiApi.tone(str(a.text), str(a.tone, 'darker'), storyId)).data }
      case 'text_transform.emotion':
        return { ok: true, data: (await aiApi.emotion(str(a.text), str(a.emotion, 'tension'), str(a.intensity, 'medium'))).data }
      case 'text_transform.age_adapt':
        return { ok: true, data: (await aiApi.ageAdapt(str(a.text), str(a.target_age, 'adult'), storyId)).data }
      case 'text_transform.style':
        return { ok: true, data: (await aiApi.style(str(a.text), str(a.style, 'literary'))).data }
      case 'text_transform.translate':
        return { ok: true, data: (await aiApi.translate(str(a.text), str(a.target_language), storyId)).data }
      case 'text_transform.rewrite_section':
        // multi-step rewrite sub-step — still via the ai_transform feature (Qwen)
        return { ok: true, data: (await aiApi.refine(str(a.text) || ctx.editor?.getSelectedText?.() || '', 'standard', storyId, str(a.chapter_id))).data }
      case 'text_transform.apply_rewrite': {
        const content = str(a.content)
        if (ctx.editor && content) {
          ctx.editor.insertText(content)            // replaces current selection
          return { ok: true, message: 'Rewrite applied to the editor.' }
        }
        return { ok: true, data: (await chaptersApi.update(storyId, str(a.chapter_id), { content })).data, message: 'Chapter updated.' }
      }

      // ── Import / export / OCR (client uploads) ────────────────────────────
      case 'manuscript_import.guide':
        if (ctx.onGuideUpload) ctx.onGuideUpload('manuscript')
        return { ok: true, message: 'Choose a manuscript file to import.' }
      case 'ocr_inject.guide':
        if (ctx.onGuideUpload) ctx.onGuideUpload('ocr')
        return { ok: true, message: 'Choose an image to scan.' }
      case 'export.export': {
        const fmt = (str(a.format, 'docx') === 'pdf' ? 'pdf' : 'docx') as 'pdf' | 'docx'
        const res = await exportApi.export(storyId, fmt)
        await downloadBlob(res as { data: Blob }, `story.${fmt}`)
        return { ok: true, message: `Exported as ${fmt.toUpperCase()}.` }
      }

      // ── Search & replace ──────────────────────────────────────────────────
      case 'search_replace.exact':
        return { ok: true, data: (await searchApi.exact(storyId, str(a.query), false, false)).data }
      case 'search_replace.semantic':
        return { ok: true, data: (await searchApi.semantic(storyId, str(a.query))).data }
      case 'search_replace.replace':
        return { ok: true, data: (await searchApi.replace(storyId, { query: str(a.query), replacement: str(a.replacement), caseSensitive: false, wholeWord: false, chapterIds: a.chapter_id ? [str(a.chapter_id)] : null, dryRun: false })).data, message: 'Replaced.' }

      // ── Analysis & intelligence ───────────────────────────────────────────
      case 'plot_holes.analyze':
        return { ok: true, data: (await analysisApi.detectPlotHoles(storyId)).data }
      case 'manuscript_report.analyze':
        return { ok: true, data: (await analysisApi.getManuscriptReport(storyId)).data }
      case 'story_intel.analyze':
        return { ok: true, data: (await api.post(`/api/stories/${storyId}/intelligence/analyze`, { passes: [], force_refresh: false })).data }
      case 'story_intel.dna':
        return { ok: true, data: (await api.get(`/api/stories/${storyId}/intelligence/dna`)).data }
      case 'story_intel.audience':
        return { ok: true, data: (await api.get(`/api/stories/${storyId}/intelligence/audience`)).data }
      case 'story_intel.genre':
        return { ok: true, data: (await api.get(`/api/stories/${storyId}/intelligence/genre`)).data }
      case 'story_intel.themes':
        return { ok: true, data: (await api.get(`/api/stories/${storyId}/intelligence/themes`)).data }
      case 'narrative_threads.scan':
        return { ok: true, data: (await narrativeThreadsApi.scan(storyId)).data }
      case 'narrative_threads.list':
        return { ok: true, data: (await narrativeThreadsApi.list(storyId)).data }

      // ── Phase 2 analyses & generators ─────────────────────────────────────
      case 'emotional_arc.analyze':
        return { ok: true, data: (await emotionalArcApi.get(storyId, true)).data }
      case 'duplicate_scenes.analyze':
        return { ok: true, data: (await duplicateScenesApi.detect(storyId)).data }
      case 'style_drift.analyze':
        return { ok: true, data: (await styleDriftApi.check(storyId)).data }
      case 'continuity_check.analyze':
        return { ok: true, data: (await continuityApi.check(storyId)).data }
      case 'continuation.generate':
        return { ok: true, data: (await continuationApi.suggest(storyId, str(a.chapter_id), str(a.tail_text), 'medium')).data }
      case 'outline.generate':
        return { ok: true, data: (await outlineApi.generate(storyId, str(a.chapter_id), str(a.chapter_goal, 'advance the plot'), num(a.scene_count, 4))).data }
      case 'story_bible.generate':
        return { ok: true, data: (await storyBibleApi.generate(storyId)).data, message: 'Generating story bible…' }
      case 'story_bible.get':
        return { ok: true, data: (await storyBibleApi.get(storyId)).data }
      case 'pacing_goals.set':
        return { ok: true, data: (await pacingApi.set(storyId, num(a.target_word_count), num(a.target_chapter_count), num(a.target_words_per_chapter))).data, message: 'Pacing goal set.' }
      case 'pacing_goals.get':
        return { ok: true, data: (await pacingApi.get(storyId)).data }

      // ── Voice note (P2-11 secondary path) ─────────────────────────────────
      case 'voice_note.save':
        return { ok: true, data: (await ocrApi.createNote(storyId, 'Voice note', str(a.content))).data, message: 'Saved as a story note.' }

      // ── Account ───────────────────────────────────────────────────────────
      case 'account.logout':
        if (ctx.onLogout) ctx.onLogout()
        return { ok: true, message: 'Logged out.' }

      default:
        return { ok: false, message: `No executor for "${call}".` }
    }
  } catch (e) {
    const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    return { ok: false, message: msg || `Failed to run ${call}.` }
  }
}

/** Result-kind hint for session memory (so "use the second option" works). */
export function resultKindFor(node: WorkflowNode): string | null {
  if (node.capability === 'continuation') return 'continuation'
  if (node.action_type === 'analyze') return 'analysis'
  if (node.capability === 'story_bible') return 'bible'
  return null
}
