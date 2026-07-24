# Additional Features — Author-Inspired Style Rewrite & Copyright / Plagiarism Risk Detection

Status: **Design + Implementation reference**
Author: Engineering
Scope: NarratIQ AI (FastAPI backend + Next.js 14 frontend + vLLM/Qwen2.5-7B + BGE-M3)

This document is the single source of truth for two new features:

1. **Feature 1 — Author-Inspired Style Rewrite** (a new selection text-transform).
2. **Feature 2 — Copyright / Plagiarism Risk Detection** (a new on-demand analysis).

It follows the existing system conventions so the features are production-grade,
reuse the established AI service architecture, and add **no breaking changes** to
the current refine / tone / emotion / style / age / translate tools.

---

## 1. Current System Analysis

**Three-service stack** (see `CLAUDE.md`):

- **vLLM** (`Qwen2.5-7B-Instruct`, port 9001) — all generative LLM calls.
- **FastAPI backend** (port 8000) — routers + services + SQLAlchemy/pgvector.
- **Next.js 14 frontend** (port 3000) — App Router, TipTap editor, lazy panels.

**AI text generation** flows exclusively through two primitives in
`backend/services/ai_service.py`:

- `_complete(system, user, temperature, max_tokens)` — non-streaming, used for
  structured JSON and deterministic transforms. Raises `AIServiceUnavailableError`
  on vLLM connection / 5xx errors.
- `_stream_generate(system, user, temperature, max_tokens)` — token streaming for
  SSE. Same error semantics.
- `_extract_json(text, fallback)` — robust JSON extraction (fences, balanced
  spans, trailing-comma repair) used by every analysis feature.

**Genre awareness:** `services/genre_context.build_genre_context(story_id, db)`
returns a prompt-ready genre block (or `""` when Story Intake was skipped).
`ai_service._with_genre(system, genre_context)` prepends it. All transforms
**except translate** inject this.

**Selection transform pipeline (Feature 1's template):**

- Router: `backend/routers/ai_transform.py` (registered at prefix `/api/ai`).
  Each transform has a non-stream (`response_model=TransformResponse`) and a
  `/stream` SSE variant, both rate-limited with
  `settings.rate_limit_realtime_ai` keyed per-user (`get_user_id`).
- Request schemas: `backend/schemas.py` — `TransformRequest`, `ToneRequest`,
  `EmotionRequest`, `AgeAdaptRequest`, `StyleRequest`, `TranslationRequest`;
  response `TransformResponse{original, transformed, mode, tokens_used}`.
- Service functions: `refine_text`, `transform_tone`, `rewrite_emotion`,
  `adapt_for_age`, `transform_style`, `translate_text` (+ `stream_*` variants).
- Frontend single source of truth: `frontend/lib/transforms.ts`
  - Option lists (`REFINE_MODES`, `TONES`, `EMOTIONS`, `AUDIENCES`, `STYLES`,
    `LANGUAGES`), `TRANSFORM_GROUPS`, `buildTransformCall()`, `runTransform()`.
  - Consumed by **both** the `SelectionToolbar` (floating, replaces exact range)
    and `AIToolsSidebar` (right dock tabs).
- Editor bridge: `frontend/components/editor/EditorWithMethods.tsx` exposes
  `getSelectedText`, `getFullText`, `insertText`, `getSelectionRange`,
  `replaceRange(from, to, text)`. `SelectionToolbar` captures `{from,to,text}`,
  previews the AI output, and applies via `editor.replaceRange(from, to, text)`.
- Context: `frontend/components/studio/StoryContextEngine.tsx` exposes
  `useStoryContext()` → `storyId`, `activeChapterId`, `editor`, `genreProfile`,
  `logActivity`, plus `selection` and analysis selection (`activeAnalysis`).

**On-demand analysis pipeline (Feature 2's template):**

- Router example: `backend/routers/plot_holes.py` — `POST /{story_id}/plot-holes`,
  rate-limited `settings.rate_limit_heavy_ai`, ownership check via
  `_check_story_access`, loads `ChapterSummary` rows, calls a service strategy,
  maps results into a Pydantic response, returns `422` when `< 2` indexed chapters.
- Service: `detect_plot_holes(story_id, summaries, strategy)` with a strategy
  registry (`_PLOT_HOLE_STRATEGIES`) — clean extension point.
- Schemas: `PlotHoleIssue` / `PlotHoleResponse` (string-literal severity
  `high|medium|low`, `List[...]` nested findings).
- Frontend panel: `frontend/components/plot-holes/PlotHolesPanel.tsx` — scan
  button, loading / not-enough / empty / results states, severity badges,
  expandable cards.
- Panel registry: `frontend/lib/registries/panels.tsx` (`PANELS[]`) →
  auto-rendered by the **Analyze** workspace
  (`app/(dashboard)/projects/[id]/analyze/page.tsx`) which passes `storyId`.
- API client: `frontend/lib/api.ts` (`analysisApi`, `aiApi`, …).
- Router registration: `backend/main.py` `app.include_router(..., prefix="/api/stories")`.

**Cross-cutting hardening already present** (Phase 3): rate limiting (slowapi,
per-user JWT), `AIServiceUnavailableError` → HTTP 503, background concurrency
semaphores, structured logging, configurable `.env`. No hardcoded limits.

---

## 2. Existing Related Features Found in the Codebase

| Concern | Existing feature | Location | Reused by |
|---|---|---|---|
| Style rewrite | `transform_style` / `/api/ai/style` | `ai_service.py`, `ai_transform.py` | **Feature 1** (direct template) |
| Selection replace UX | `SelectionToolbar` + `runTransform` | `components/studio/SelectionToolbar.tsx`, `lib/transforms.ts` | **Feature 1** |
| Dock tabs UX | `AIToolsSidebar` | `components/ai-tools/AIToolsSidebar.tsx` | **Feature 1** |
| Genre-aware prompts | `build_genre_context` / `_with_genre` | `services/genre_context.py`, `ai_service.py` | Both |
| On-demand JSON analysis | `detect_plot_holes` (strategy registry) | `ai_service.py`, `routers/plot_holes.py` | **Feature 2** (direct template) |
| Analysis panel UX | `PlotHolesPanel` + `panels.tsx` registry | `components/plot-holes/`, `lib/registries/panels.tsx` | **Feature 2** |
| Whole-story scope | `manuscript_report` (chapter summaries) | `routers/manuscript_report.py` | **Feature 2** (project scope) |

**Conclusion:** Both features map cleanly onto two battle-tested patterns. No new
infrastructure is required — only new service functions, schemas, one router, one
transform group, one panel, and the wiring.

---

## 3. New Feature Requirements

### Feature 1 — Author-Inspired Style Rewrite

- New selection action "Author Style" alongside refine/tone/emotion/style/etc.
- User selects text → picks an author/style → AI rewrites in that **influence**,
  preserving meaning, plot, characters, and intent.
- **Safety:** never reproduce copyrighted text; never closely imitate living /
  in-copyright authors. Only **public-domain** authors get "inspired-by"
  transformation; generic style categories are always safe. Unknown / risky
  author strings degrade safely to a generic literary influence.
- UI presents a curated author list, with public-domain authors clearly separated
  from generic styles, plus an explanatory safety note.
- Must work through the existing exact-range replacement workflow.
- Scalable: adding an author = one entry (backend authority + frontend list).

### Feature 2 — Copyright / Plagiarism Risk Detection

- On-demand analysis at three scopes: **selection**, **chapter**, **whole story**.
- Output:
  1. **Risk score** — `low | medium | high` (overall) + per-finding.
  2. **Risk type** — `direct_text | plot | character | world_building | scene |
     style_imitation | trope_overuse`.
  3. **Explanation** — why risky, which part, generic-trope vs serious similarity.
  4. **Rewrite suggestions** — how to increase originality / reduce risk.
- Framed as **risk detection, not legal advice** (explicit disclaimer in payload
  and UI). No claims of legal certainty.

---

## 4. Frontend Changes Needed

### Feature 1

- `lib/transforms.ts`
  - Add `AUTHOR_STYLES: AuthorOpt[]` (id, label, desc, `publicDomain`, `group`).
  - Add `'author_style'` to `GroupId`, a `TRANSFORM_GROUPS` entry (icon
    `BookOpen`), and a `buildTransformCall` case → `POST /api/ai/author-style`
    body `{ text, author, story_id }`. This auto-wires `SelectionToolbar`.
- `lib/api.ts` — add `aiApi.authorStyle(text, author, storyId)`.
- `components/ai-tools/AIToolsSidebar.tsx` — add an "Author" tab using
  `AUTHOR_STYLES`, with a visual separation of public-domain vs generic and a
  one-line safety caption. Reuses the existing run/result flow (`aiApi.authorStyle`).
- `SelectionToolbar.tsx` — **no change required** (driven by `TRANSFORM_GROUPS`);
  it will show "Author Style" automatically and replace the exact range.

### Feature 2

- `lib/types.ts` — add `CopyrightRiskFinding`, `CopyrightRiskResponse`.
- `lib/api.ts` — add `copyrightRiskApi.analyze(storyId, {scope, text?, chapterId?})`.
- `components/analysis/CopyrightRiskPanel.tsx` — new panel:
  - Scope toggle: **Selection / Chapter / Whole Story** (uses `useStoryContext()`
    → `editor.getSelectedText()` / `getFullText()`).
  - Run button with loading / error / not-enough / empty / results states.
  - Overall risk badge + per-finding cards (type, score, explanation,
    problematic excerpt, rewrite suggestion) + non-legal disclaimer footer.
- `lib/registries/panels.tsx` — register `copyright_risk` panel (icon `ShieldAlert`,
  workspace `analyze`, `needs: ['storyId']`). Auto-appears in the Analyze grid.

All new network calls use the shared `api` axios instance (JWT + 401 interceptor)
and render explicit loading and error states (toast on failure).

---

## 5. Backend / API Changes Needed

### Feature 1

- `schemas.py` — `AuthorStyleRequest{story_id?, chapter_id?, text, author}`
  (reuses `TransformResponse`).
- `services/ai_service.py`
  - `_AUTHOR_STYLES` registry: `key → {label, descriptor, public_domain}`. This is
    the **safety authority**: only public-domain authors + generic styles.
  - `_resolve_author_style(author)` → resolves to a safe descriptor; unknown /
    non-public-domain strings fall back to the generic literary influence.
  - `_AUTHOR_SAFETY` system-prompt clause (no verbatim copying, influence only,
    preserve meaning).
  - `rewrite_in_author_style(text, author, genre_context)` + streaming
    `stream_author_style(...)`.
- `routers/ai_transform.py` — `POST /api/ai/author-style` (+ `/stream`),
  rate-limited `rate_limit_realtime_ai`, genre context injected; and a read-only
  `GET /api/ai/author-styles` returning the curated catalog (so the list is
  server-authoritative and future-proof).

### Feature 2

- `schemas.py` — `CopyrightRiskRequest{scope, text?, chapter_id?}`,
  `CopyrightRiskFinding`, `CopyrightRiskResponse`.
- `services/ai_service.py` — `analyze_copyright_risk(scope, text, chapters,
  genre_context)`:
  - Builds a strict-JSON prompt (temperature 0) with the risk taxonomy and a
    "risk, not legal advice" instruction.
  - Returns `{overall_risk, findings[], note, disclaimer, units_analyzed}`,
    parsed with `_extract_json`.
- `routers/copyright_risk.py` — `POST /api/stories/{story_id}/copyright-risk`,
  rate-limited `rate_limit_heavy_ai`, ownership check:
  - `scope=selection|chapter` → analyze provided `text` (validated, length-capped).
  - `scope=project` → load `ChapterSummary` rows (≥1) into structured units.
  - Maps to `CopyrightRiskResponse`; `422` when there is nothing to analyze.
- `main.py` — `app.include_router(copyright_risk.router, prefix="/api/stories")`.

---

## 6. Database Changes Needed

**None.** Both features are stateless / on-demand:

- Feature 1 returns transformed text (applied by the editor; chapter persistence
  uses the existing chapter autosave). No new tables/columns.
- Feature 2 returns an ephemeral report (same model as plot-holes / manuscript
  report, which are not persisted). No migration required.

If result history is desired later, a `copyright_risk_reports` table can be added
via Alembic autogenerate — explicitly out of scope here.

---

## 7. AI Prompt / Service Changes Needed

- **Feature 1** prompt shape (system):
  - "You are a literary writing coach. Rewrite the passage so it is **influenced by**
    the style of {descriptor} — sentence rhythm, diction, imagery, dramatic
    expression. **Preserve the original meaning, plot, characters, and intent.**
    Produce original prose **inspired by** the style; **never reproduce or closely
    imitate any copyrighted text or any specific published passage.** Return ONLY
    the rewritten passage." Temperature 0.6, `max_tokens ≈ words*2 + 150`
    (matches existing style transform).
- **Feature 2** prompt shape (system): risk analyst persona, the 7-type taxonomy,
  strict JSON contract, "Do NOT claim legal certainty; this is risk guidance, not
  legal advice", "distinguish generic tropes from serious, specific similarity",
  and require per-finding `problematic_excerpt` + `rewrite_suggestion`.
  Temperature 0.0, JSON via `_extract_json`.
- Both reuse `_complete` / `_stream_generate` and `_with_genre`. No change to the
  primitives.

---

## 8. Safety and Copyright Guardrails

- **Server is the authority.** The frontend list is convenience; the backend
  `_AUTHOR_STYLES` registry + `_resolve_author_style` decide what is allowed.
- **Public-domain only for named authors.** Curated set: Shakespeare, Jane Austen,
  Charles Dickens, Edgar Allan Poe, the Brontës, Mark Twain (all long
  public-domain). Generic styles (poetic / cinematic / literary / gothic, etc.)
  are always safe. **No living / in-copyright authors** are offered (Hemingway,
  Woolf, and Christie are noted below).
- **Hemingway / Virginia Woolf / Agatha Christie:** requested in the brief but
  their major works are **not uniformly public domain** in all jurisdictions
  (and living-author imitation is explicitly disallowed by the brief). They are
  **mapped to safe generic descriptors** ("spare, understated minimalist prose";
  "stream-of-consciousness literary prose"; "classic whodunit mystery prose")
  rather than to the named author, so the feature delivers the *stylistic intent*
  without copyright/style-infringement risk. This satisfies the brief's
  requirement to "clearly separate public-domain from modern/living author styles
  and provide safer alternatives."
- **Influence, not imitation.** Every prompt forbids verbatim reproduction and
  close imitation, and mandates preservation of the user's meaning/plot/characters.
- **Unknown author strings** degrade to the generic literary influence (never
  passed raw into an "imitate X" instruction).
- **Feature 2 is risk guidance, not legal advice** — disclaimer included in both
  the API payload (`disclaimer` field) and the UI footer. No legal certainty is
  claimed; generic tropes are explicitly distinguished from serious similarity.
- **Validation:** non-empty text, length caps, and rate limits prevent abuse.

---

## 9. Implementation Plan

1. **Backend schemas** — add Feature 1 + Feature 2 Pydantic models to `schemas.py`.
2. **AI service** — add `_AUTHOR_STYLES`, `_resolve_author_style`,
   `rewrite_in_author_style`, `stream_author_style`; add
   `analyze_copyright_risk`.
3. **Routers** — extend `ai_transform.py` (author-style endpoints + catalog GET);
   add `routers/copyright_risk.py`; register it in `main.py`.
4. **Frontend shared config** — extend `lib/transforms.ts` (author group + routing),
   `lib/api.ts` (`authorStyle`, `copyrightRiskApi`), `lib/types.ts` (risk types).
5. **Frontend UI** — add Author tab to `AIToolsSidebar`; add `CopyrightRiskPanel`
   and register it in `panels.tsx` (SelectionToolbar gets Feature 1 for free).
6. **Tests** — backend unit tests (stubbed `_complete`) for author-style
   resolution/safeguards and copyright JSON parsing; frontend transform-routing
   test for the author group.
7. **Docs** — this file; plus a `CHANGELOG.md` note.

---

## 10. Testing Plan

- **Backend unit (pytest, no DB/LLM):**
  - `_resolve_author_style`: public-domain key → named descriptor; Hemingway/
    Woolf/Christie → generic safe descriptor (no named imitation); unknown →
    generic literary.
  - `rewrite_in_author_style` with monkeypatched `_complete` returns text and
    builds a safety-bearing system prompt.
  - `analyze_copyright_risk` with monkeypatched `_complete` parses strict JSON,
    normalizes `overall_risk`, and always includes the disclaimer.
- **Frontend unit (Playwright `tests/transforms.spec.ts`):**
  - `buildTransformCall('author_style', 'shakespeare', SEL, {storyId})` →
    `path '/api/ai/author-style'`, body `{text: SEL, author: 'shakespeare', story_id}`.
  - `AUTHOR_STYLES` exposes public-domain + generic groups; no living authors as
    named imitation targets.
- **Manual / integration (see Final Report → "How to test"):** selection toolbar
  author rewrite + apply-to-range; AIToolsSidebar Author tab; Copyright panel at
  all three scopes incl. `422` when project has no indexed chapters.

---

## 11. Risks and Limitations

- **Model quality:** Qwen-7B style imitation is approximate; "inspired-by" framing
  is both a safety feature and a realistic expectation.
- **Copyright detection is heuristic:** the model reasons from training knowledge,
  not a database of copyrighted works — it cannot guarantee detection and may
  flag generic tropes or miss subtle copying. Hence the explicit non-legal-advice
  framing and `low/medium/high` (not numeric certainty) scoring.
- **Project-scope analysis** relies on indexed `ChapterSummary` rows (run *Sync
  Summaries* first); very large manuscripts are capped per pass like plot-holes.
- **No persistence:** reports are ephemeral (consistent with existing analyses).
- **Living-author requests** are intentionally redirected to safe generic
  descriptors; users will not get a literal "write exactly like <living author>".
- **Latency:** whole-story analysis is a heavy AI call; rate-limited and shown
  with a loading state.
