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
  emotion: (text: string, emotion: string, intensity = 'medium') =>
    api.post('/api/ai/emotion', { text, emotion, intensity }),
  ageAdapt: (text: string, targetAge: string, storyId?: string) =>
    api.post('/api/ai/age-adapt', { text, target_age: targetAge, story_id: storyId }),
  style: (text: string, style: string) =>
    api.post('/api/ai/style', { text, style }),
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

export default api
