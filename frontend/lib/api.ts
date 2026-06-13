import axios from 'axios'

const BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const api = axios.create({ baseURL: BASE })

api.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('narratiq_token')
    if (token) config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401 && typeof window !== 'undefined') {
      localStorage.removeItem('narratiq_token')
      localStorage.removeItem('narratiq_user')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

// ── Auth ──────────────────────────────────────────────────────────────────────
export const authApi = {
  register: (email: string, username: string, password: string) =>
    api.post('/api/auth/register', { email, username, password }),
  login: (email: string, password: string) =>
    api.post('/api/auth/login', { email, password }),
  me: () => api.get('/api/auth/me'),
}

// ── Projects ──────────────────────────────────────────────────────────────────
export const projectsApi = {
  list: () => api.get('/api/projects/'),
  create: (title: string, description?: string) =>
    api.post('/api/projects/', { title, description }),
  get: (id: string) => api.get(`/api/projects/${id}`),
  update: (id: string, data: object) => api.patch(`/api/projects/${id}`, data),
  delete: (id: string) => api.delete(`/api/projects/${id}`),
}

// ── Chapters ──────────────────────────────────────────────────────────────────
export const chaptersApi = {
  list: (storyId: string) => api.get(`/api/stories/${storyId}/chapters`),
  get: (storyId: string, chapterId: string) =>
    api.get(`/api/stories/${storyId}/chapters/${chapterId}`),
  create: (storyId: string, title: string, content?: string) =>
    api.post(`/api/stories/${storyId}/chapters`, { title, content }),
  update: (storyId: string, chapterId: string, data: object) =>
    api.patch(`/api/stories/${storyId}/chapters/${chapterId}`, data),
  delete: (storyId: string, chapterId: string) =>
    api.delete(`/api/stories/${storyId}/chapters/${chapterId}`),
  versions: (storyId: string, chapterId: string) =>
    api.get(`/api/stories/${storyId}/chapters/${chapterId}/versions`),
  getVersion: (storyId: string, chapterId: string, versionId: string) =>
    api.get(`/api/stories/${storyId}/chapters/${chapterId}/versions/${versionId}`),
}

// ── Story Intake ──────────────────────────────────────────────────────────────
export const intakeApi = {
  analyze: (storyId: string, description: string, audienceHint?: string) =>
    api.post(`/api/intake/${storyId}`, { description, audience_hint: audienceHint }),
  confirm: (storyId: string, intakeId: string, overrides?: object) =>
    api.post(`/api/intake/${storyId}/confirm`, { intake_id: intakeId, overrides }),
  getGenreProfile: (storyId: string) => api.get(`/api/intake/${storyId}/genre-profile`),
  // Saved Story Intake / Genre Detection report (previous result) for this story.
  getReport: (storyId: string) => api.get(`/api/intake/${storyId}/report`),
}

// ── Plot Assistant ─────────────────────────────────────────────────────────────
export const plotApi = {
  suggest: (
    storyId: string,
    question: string,
    currentChapterText?: string,
    template?: string,
    chapterNumber?: number,
  ) =>
    api.post('/api/plot-assistant/', {
      story_id:               storyId,
      question,
      current_chapter_text:   currentChapterText,
      template,
      current_chapter_number: chapterNumber ?? null,
    }),
  markUsed: (sessionId: string, index: number) =>
    api.patch(`/api/plot-assistant/${sessionId}/use?suggestion_index=${index}`),
}

// ── AI Transforms ─────────────────────────────────────────────────────────────
export const aiApi = {
  refine: (text: string, mode = 'standard', storyId?: string, chapterId?: string) =>
    api.post('/api/ai/refine', { text, mode, story_id: storyId, chapter_id: chapterId }),
  tone: (text: string, tone: string, storyId?: string) =>
    api.post('/api/ai/tone', { text, tone, story_id: storyId }),
  emotion: (text: string, emotion: string, intensity = 'medium', storyId?: string) =>
    api.post('/api/ai/emotion', { text, emotion, intensity, story_id: storyId }),
  ageAdapt: (text: string, targetAge: string, storyId?: string) =>
    api.post('/api/ai/age-adapt', { text, target_age: targetAge, story_id: storyId }),
  style: (text: string, style: string, storyId?: string) =>
    api.post('/api/ai/style', { text, style, story_id: storyId }),
  translate: (text: string, targetLanguage: string, storyId?: string) =>
    api.post('/api/ai/translate', { text, target_language: targetLanguage, story_id: storyId }),
  suggestions: (storyId: string, chapterId: string, text: string) =>
    api.post('/api/ai/suggestions', { story_id: storyId, chapter_id: chapterId, text }),
}

// ── OCR ───────────────────────────────────────────────────────────────────────
export const ocrApi = {
  extract: (storyId: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post(`/api/ocr/extract/${storyId}`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  confirm: (
    uploadId: string,
    finalText: string,
    destination: string,
    chapterId?: string,
    characterName?: string,
  ) =>
    api.post('/api/ocr/confirm', {
      upload_id:      uploadId,
      final_text:     finalText,
      destination,
      chapter_id:     chapterId     ?? null,
      character_name: characterName ?? null,
    }),
  list:      (storyId: string) => api.get(`/api/ocr/${storyId}/uploads`),
  notes:     (storyId: string) => api.get(`/api/ocr/${storyId}/notes`),
  noteCards: (storyId: string) => api.get(`/api/ocr/${storyId}/note-cards`),
  createNote: (storyId: string, title: string, content: string) =>
    api.post(`/api/ocr/${storyId}/notes`, { title, content }),
  updateNote: (noteId: string, data: { title?: string; content?: string }) =>
    api.patch(`/api/ocr/notes/${noteId}`, data),
  deleteNote: (noteId: string) =>
    api.delete(`/api/ocr/notes/${noteId}`),
  createNoteCard: (storyId: string, title: string, content: string, cardType: string) =>
    api.post(`/api/ocr/${storyId}/note-cards`, { title, content, card_type: cardType }),
  updateNoteCard: (cardId: string, data: { title?: string; content?: string; card_type?: string }) =>
    api.patch(`/api/ocr/note-cards/${cardId}`, data),
  deleteNoteCard: (cardId: string) =>
    api.delete(`/api/ocr/note-cards/${cardId}`),
}

// ── Characters ────────────────────────────────────────────────────────────────
export const charactersApi = {
  list:   (storyId: string) =>
    api.get(`/api/stories/${storyId}/characters`),
  search: (storyId: string, params: { q?: string; role?: string; status?: string }) =>
    api.get(`/api/stories/${storyId}/characters/search`, { params }),
  graph:  (storyId: string) =>
    api.get(`/api/stories/${storyId}/characters/graph`),
  get:    (storyId: string, characterId: string) =>
    api.get(`/api/stories/${storyId}/characters/${characterId}`),
  create: (storyId: string, data: { name: string; aliases?: string[]; role?: string; status?: string }) =>
    api.post(`/api/stories/${storyId}/characters`, data),
  update: (storyId: string, characterId: string, data: object) =>
    api.patch(`/api/stories/${storyId}/characters/${characterId}`, data),
  delete: (storyId: string, characterId: string) =>
    api.delete(`/api/stories/${storyId}/characters/${characterId}`),
  updateProfile: (storyId: string, characterId: string, data: object) =>
    api.patch(`/api/stories/${storyId}/characters/${characterId}/profile`, data),
  generateCast: (storyId: string) =>
    api.post(`/api/stories/${storyId}/characters/generate-cast`),
  confirmCast: (
    storyId: string,
    suggestions: {
      name: string; role: string; status: string;
      description: string; aliases: string[]; evidence_snippet: string;
      age?: string; appearance?: string; personality?: string;
      goals?: string; motivations?: string; backstory?: string;
      arc_notes?: string; traits?: string[];
    }[],
  ) => api.post(`/api/stories/${storyId}/characters/confirm-cast`, { suggestions }),
  getMentions: (storyId: string, characterId: string) =>
    api.get(`/api/stories/${storyId}/characters/${characterId}/mentions`),
  syncMentions: (storyId: string) =>
    api.post(`/api/stories/${storyId}/characters/sync-mentions`),
  enrich: (storyId: string, characterId: string) =>
    api.post(`/api/stories/${storyId}/characters/${characterId}/enrich`),
  getArcTimeline: (storyId: string, characterId: string) =>
    api.post(`/api/stories/${storyId}/characters/${characterId}/arc-timeline`),
  getHints: (storyId: string) =>
    api.get(`/api/stories/${storyId}/characters/hints`),
  dismissHint: (storyId: string, hintId: string) =>
    api.post(`/api/stories/${storyId}/characters/hints/${hintId}/dismiss`),
  promoteHint: (storyId: string, hintId: string) =>
    api.post(`/api/stories/${storyId}/characters/hints/${hintId}/promote`),
}

// ── Character Relationships ───────────────────────────────────────────────────
export const relationshipsApi = {
  list: (storyId: string, characterId: string) =>
    api.get(`/api/stories/${storyId}/characters/${characterId}/relationships`),
  create: (
    storyId: string,
    characterId: string,
    data: {
      to_character_id: string
      relationship_type: string
      strength?: string
      description?: string
      is_mutual?: boolean
    },
  ) => api.post(`/api/stories/${storyId}/characters/${characterId}/relationships`, data),
  update: (
    storyId: string,
    characterId: string,
    relationshipId: string,
    data: { relationship_type?: string; strength?: string; description?: string; is_mutual?: boolean },
  ) => api.patch(
    `/api/stories/${storyId}/characters/${characterId}/relationships/${relationshipId}`,
    data,
  ),
  delete: (storyId: string, characterId: string, relationshipId: string) =>
    api.delete(
      `/api/stories/${storyId}/characters/${characterId}/relationships/${relationshipId}`,
    ),
}

// ── Manuscript ────────────────────────────────────────────────────────────────
export const manuscriptApi = {
  upload: (storyId: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post(`/api/manuscript/upload/${storyId}`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  jobStatus: (jobId: string) => api.get(`/api/manuscript/job/${jobId}`),
}

// ── Search & Replace ──────────────────────────────────────────────────────────
export const searchApi = {
  exact: (
    storyId: string,
    query: string,
    caseSensitive: boolean,
    wholeWord: boolean,
    chapterIds?: string[] | null,
  ) =>
    api.post(`/api/search/exact/${storyId}`, {
      query,
      case_sensitive: caseSensitive,
      whole_word: wholeWord,
      chapter_ids: chapterIds ?? null,
    }),

  semantic: (storyId: string, query: string, topK = 8) =>
    api.post(`/api/search/semantic/${storyId}`, { query, top_k: topK }),

  replace: (
    storyId: string,
    params: {
      query: string
      replacement: string
      caseSensitive: boolean
      wholeWord: boolean
      chapterIds?: string[] | null
      occurrenceIndex?: number | null
      dryRun: boolean
    },
  ) =>
    api.post(`/api/search/replace/${storyId}`, {
      query: params.query,
      replacement: params.replacement,
      case_sensitive: params.caseSensitive,
      whole_word: params.wholeWord,
      chapter_ids: params.chapterIds ?? null,
      occurrence_index: params.occurrenceIndex ?? null,
      dry_run: params.dryRun,
    }),
}

// ── Story Analysis ────────────────────────────────────────────────────────────
export const analysisApi = {
  detectPlotHoles: (storyId: string) =>
    api.post(`/api/stories/${storyId}/plot-holes`),
  getManuscriptReport: (storyId: string) =>
    api.post(`/api/stories/${storyId}/manuscript-report`),
}

// ── Export ────────────────────────────────────────────────────────────────────
export const exportApi = {
  export: async (storyId: string, format: 'docx' | 'pdf') => {
    const res = await api.post(
      '/api/export/',
      { story_id: storyId, format },
      { responseType: 'blob' }
    )
    return res
  },
}

// ── Phase 2 — Emotional Arc (P2-01) ──────────────────────────────────────────
export const emotionalArcApi = {
  get: (storyId: string, withAssessment = false) =>
    api.get(`/api/stories/${storyId}/emotional-arc`, { params: { include_assessment: withAssessment } }),
}

// ── Phase 2 — Duplicate Scenes (P2-10) ───────────────────────────────────────
export const duplicateScenesApi = {
  detect: (storyId: string) => api.post(`/api/stories/${storyId}/duplicate-scenes`),
}

// ── Phase 2 — Style Drift (P2-08) ────────────────────────────────────────────
export const styleDriftApi = {
  check: (storyId: string) => api.post(`/api/stories/${storyId}/style-drift`),
}

// ── Phase 2 — Continuity Check (P2-05) ───────────────────────────────────────
export const continuityApi = {
  check: (storyId: string) => api.post(`/api/stories/${storyId}/continuity-check`),
}

// ── Phase 2 — Continuation Suggestion (P2-02) ────────────────────────────────
const CONT_LENGTH_MAP: Record<string, number> = { short: 100, medium: 200, long: 350 }

export const continuationApi = {
  suggest: (storyId: string, chapterId: string, tailText: string, continuationLength: string | number = 'medium') => {
    const words = typeof continuationLength === 'number'
      ? continuationLength
      : (CONT_LENGTH_MAP[continuationLength] ?? 200)
    return api.post(`/api/stories/${storyId}/chapters/${chapterId}/continue`, {
      tail_text: tailText,
      continuation_length: words,
    })
  },
}

// ── Phase 2 — Chapter Outline (P2-04) ────────────────────────────────────────
export const outlineApi = {
  generate: (storyId: string, chapterId: string, chapterGoal: string, sceneCount = 4) =>
    api.post(`/api/stories/${storyId}/chapters/${chapterId}/outline`, {
      chapter_goal: chapterGoal,
      scene_count: sceneCount,
    }),
}

// ── Phase 2 — Voice Check (P2-03) ────────────────────────────────────────────
export const voiceCheckApi = {
  check: (storyId: string, characterId: string) =>
    api.post(`/api/stories/${storyId}/characters/${characterId}/voice-check`),
}

// ── Phase 2 — Story Bible (P2-06) ────────────────────────────────────────────
export const storyBibleApi = {
  generate: (storyId: string)   => api.post(`/api/stories/${storyId}/story-bible`),
  get:      (storyId: string)   => api.get(`/api/stories/${storyId}/story-bible`),
  exportUrl:(storyId: string)   => `${BASE}/api/stories/${storyId}/story-bible/export`,
}

// ── Phase 2 — Narrative Threads (P2-07) ──────────────────────────────────────
export const narrativeThreadsApi = {
  scan:   (storyId: string)                              => api.post(`/api/stories/${storyId}/narrative-threads/scan`),
  list:   (storyId: string, status?: string)             => api.get(`/api/stories/${storyId}/narrative-threads`, { params: status ? { status } : {} }),
  update: (storyId: string, threadId: string, status: string) =>
    api.patch(`/api/stories/${storyId}/narrative-threads/${threadId}`, { status }),
}

// ── Phase 2 — Pacing (P2-09) ─────────────────────────────────────────────────
export const pacingApi = {
  get: (storyId: string) => api.get(`/api/stories/${storyId}/pacing-goals`),
  set: (storyId: string, targetWordCount: number, targetChapterCount: number, targetWordsPerChapter: number) =>
    api.post(`/api/stories/${storyId}/pacing-goals`, {
      target_word_count: targetWordCount,
      target_chapter_count: targetChapterCount,
      target_words_per_chapter: targetWordsPerChapter,
    }),
}

// ── Phase 2 — Audio (P2-11) ──────────────────────────────────────────────────
export const audioApi = {
  upload: (storyId: string, file: File, noteId?: string) => {
    const form = new FormData()
    form.append('file', file)
    if (noteId) form.append('note_id', noteId)
    return api.post(`/api/stories/${storyId}/audio`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  get:     (storyId: string, audioId: string)   => api.get(`/api/stories/${storyId}/audio/${audioId}`),
  list:    (storyId: string)                    => api.get(`/api/stories/${storyId}/audio`),
  confirm: (storyId: string, audioId: string, noteId: string, editedText?: string) =>
    api.post(`/api/stories/${storyId}/audio/${audioId}/confirm`, {
      note_id:     noteId,
      edited_text: editedText ?? null,
    }),
}

// ── Real-Time Voice Agent ─────────────────────────────────────────────────────
export const voiceApi = {
  // STT-free agent core (also used to re-plan after a clarification answer)
  interpret: (transcript: string, context: object, sessionId?: string | null) =>
    api.post('/api/voice/interpret', {
      transcript,
      context,
      session_id: sessionId ?? null,
    }),
  // One-shot transcription fallback (non-WS path)
  transcribe: (file: Blob) => {
    const form = new FormData()
    form.append('file', file, 'voice.webm')
    return api.post('/api/voice/transcribe', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  // Push a client-executed result into session memory ("use the second option")
  remember: (sessionId: string, resultKind: string, output: unknown) =>
    api.post(`/api/voice/sessions/${sessionId}/remember`, { result_kind: resultKind, output }),
  // Record confirmation / applied conversion for a proposed mutating action
  confirm: (commandId: string, nodeKey: string, confirmed: boolean, applied: boolean) =>
    api.post(`/api/voice/commands/${commandId}/confirm`, {
      node_key: nodeKey, confirmed, applied,
    }),
  session: (sessionId: string) => api.get(`/api/voice/sessions/${sessionId}`),
  analyticsSummary: (days = 7) => api.get('/api/voice/analytics/summary', { params: { days } }),
}

// ── Global Activity Timeline ──────────────────────────────────────────────────
export const activityApi = {
  record: (storyId: string, event: {
    category: 'ai' | 'analysis' | 'project' | 'voice' | 'export'
    type: string; title?: string; summary?: string
    ref_type?: string; ref_id?: string; metadata?: Record<string, unknown>
  }) => api.post(`/api/stories/${storyId}/activity`, event),
  list: (storyId: string, params?: { category?: string; q?: string; limit?: number }) =>
    api.get(`/api/stories/${storyId}/activity`, { params: params ?? {} }),
}

// WebSocket URL for the streaming mic endpoint (token in query param).
export function voiceWsUrl(token: string): string {
  const httpBase = BASE.replace(/\/$/, '')
  const wsBase = httpBase.replace(/^http/, 'ws')
  return `${wsBase}/api/voice/stream?token=${encodeURIComponent(token)}`
}

export default api
