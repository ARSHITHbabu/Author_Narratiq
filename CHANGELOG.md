# NarratIQ AI — Changelog

All production changes are documented here in reverse chronological order.

---

## Unreleased — Author-Inspired Style Rewrite & Copyright/Plagiarism Risk Detection

Design + implementation reference: `docs/additional_features_author_style_and_copyright_analysis.md`

### Feature 1 — Author-Inspired Style Rewrite (selection transform)
- New `/api/ai/author-style` (+ `/stream`) and read-only `/api/ai/author-styles`
  catalog endpoint in `routers/ai_transform.py`.
- `ai_service._AUTHOR_STYLES` registry is the safety authority: public-domain
  named authors only; living/in-copyright authors (Hemingway/Woolf/Christie) are
  redirected to safe generic descriptors; unknown strings fall back to generic
  literary. Prompts enforce "inspired-by, never copy" and preserve meaning.
- Frontend: new "Author" group in `lib/transforms.ts` (auto-wires the Selection
  Toolbar), `aiApi.authorStyle`, and an "Author" tab in `AIToolsSidebar` with
  public-domain vs generic separation and a safety caption.

### Feature 2 — Copyright / Plagiarism Risk Detection (on-demand analysis)
- New `POST /api/stories/{story_id}/copyright-risk` (`routers/copyright_risk.py`)
  at three scopes: selection / chapter / whole-story (chapter-summary digest).
- `ai_service.analyze_copyright_risk` returns risk score (low/med/high), 7-type
  taxonomy, explanation, implicated excerpt, generic-trope flag, and rewrite
  suggestions — framed as risk guidance, NOT legal advice (disclaimer always
  attached).
- Frontend: `CopyrightRiskPanel` registered in the Analyze workspace via
  `lib/registries/panels.tsx`; `copyrightRiskApi` client + risk types.

### Tests
- Backend: `tests/test_author_style_and_copyright.py` (10 unit tests, Qwen stubbed).
- Frontend: extended `tests/transforms.spec.ts` for author-style routing + catalog.

No DB migrations required. No new required env vars.

---

## v3.0.0 — June 2026

**Production architecture completion. All 14 roadmap tasks implemented. Zero remaining placeholders.**

The authoritative architecture reference for this release is:
`NarratIQ_AI_Production_Implementation_Report.docx`

---

### Export System — Production Implementation

**DOCX Export (`backend/routers/export.py`)**
- Replaced `MODEL_PLACEHOLDER` stub with full `python-docx` implementation
- Title page: story title (28pt bold, Times New Roman, centred), author name (16pt), optional story description (12pt italic)
- Chapter headings: Heading 1 style, Times New Roman 18pt, centred, include/exclude chapter numbers configurable
- Body text: Times New Roman, configurable font size (8–24pt), justified alignment, `\n\n`-split into separate paragraphs
- Page breaks between every chapter
- Standard manuscript margins: 1.25in left/right, 1.0in top/bottom
- Document metadata: `core_properties.author` and `core_properties.title` set from authenticated user and story
- Filename sanitisation: strips `\/*?:"<>|` (all filesystem-unsafe chars), truncates to 100 chars
- Added `python-docx>=1.1.0` to `start-narratiq.sh` pip install block

**PDF Export (`backend/routers/export.py`)**
- Replaced `MODEL_PLACEHOLDER` stub with full ReportLab Platypus implementation
- Identical title page structure to DOCX
- Body: Times-Roman, configurable font size, 1.6× leading, 0.3in first-line indent, justified (alignment=4)
- Page numbers rendered in footer via `onFirstPage`/`onLaterPages` callbacks; page 1 (title page) is suppressed
- LETTER page size, 1.25in side margins, 1.0in top/bottom
- XML entity escaping (`&`, `<`, `>`) applied to all text before passing to ReportLab Paragraph
- PDF document metadata (title, author) set in SimpleDocTemplate constructor
- Added `reportlab>=4.0.0` to `start-narratiq.sh` pip install block

---

### Manuscript Upload — Job Persistence

**PostgreSQL-Backed Job Store (`backend/routers/manuscript.py`, `backend/models.py`)**
- Removed `_jobs: dict = {}` in-memory job store (comment: `# In-memory job store (Redis in production)`)
- New `ManuscriptJob` ORM model (19th table): `job_id`, `story_id`, `user_id`, `status`, `stage`, `percent`, `message`, `chapter_count`, `created_at`, `updated_at`
- Upload endpoint creates a `ManuscriptJob` row in PostgreSQL before launching the asyncio pipeline
- `_ingest_pipeline()` calls `_update_job()` at each chapter to write progress to the DB row and commit
- `_update_job()` is a synchronous helper that queries, mutates, and commits the `ManuscriptJob` row — uses the pipeline's own `SessionLocal()`, decoupled from the request session
- Job state now survives: backend restarts, pod restarts, process kills
- `job_status` endpoint enforces user ownership: `ManuscriptJob.user_id == current_user.user_id` — returns 404 if job belongs to a different user (security fix; previous in-memory implementation had no ownership check)
- `Story.manuscript_jobs` cascade relationship added: deleting a story cleans up all its job records

**Alembic Migration 0002 (`backend/migrations/versions/0002_manuscript_jobs.py`)**
- `CREATE TABLE IF NOT EXISTS manuscript_jobs` — idempotent, safe when `create_all()` already ran
- Foreign keys: `story_id → stories(story_id) ON DELETE CASCADE`, `user_id → users(user_id)`
- Indexes: `ix_manuscript_jobs_story_id`, `ix_manuscript_jobs_user_id`
- Chains from migration 0001 (`down_revision = "0001"`)
- PostgreSQL-only (early return for other dialects, consistent with migration 0001)
- Downgrade: `DROP TABLE IF EXISTS` + `DROP INDEX IF EXISTS` (reversible)

---

### Database Architecture — PostgreSQL 16 + pgvector

**PostgreSQL Migration (`backend/database.py`, `backend/models.py`)**
- Replaced SQLite as the database engine with PostgreSQL 16
- `database.py`: `_build_engine()` selects connection kwargs by dialect; PostgreSQL uses `pool_size=10, max_overflow=20, pool_pre_ping=True, pool_recycle=3600`
- `database_url` reads from `settings.database_url` (overridden by `DATABASE_URL` env var in production)
- Added startup warning: if `DATABASE_URL` is SQLite, `warnings.warn()` is emitted at module import time alerting operators that pgvector features are unavailable
- `start-narratiq.sh`: installs PostgreSQL 16 + pgvector via PGDG apt repository (with Ubuntu 22.04 fallback), creates `narratiq` user and database, enables `vector` extension, writes `DATABASE_URL` to `backend/.env`

**pgvector Vector Similarity Search (`backend/models.py`, `backend/services/ai_service.py`)**
- 6 columns changed from `Column(JSON)` / `Column(Text)` to `Column(Vector(1024), nullable=True)`:
  - `chapter_summaries.embedding`
  - `chapter_chunks.embedding`
  - `character_profiles.embedding`
  - `character_profiles.mention_embedding`
  - `story_notes.embedding`
  - `note_cards.embedding`
- All 4 numpy cosine retrieval functions replaced with pgvector SQL using the `<=>` cosine distance operator:
  - `retrieve_chunks_from_store()` → `ORDER BY embedding <=> :q::vector`
  - `retrieve_relevant_chunks()` → `ORDER BY embedding <=> :q::vector`
  - `retrieve_character_context()` → SQL computes raw cosine scores; Python applies 0.4/0.6 hybrid weights
  - `retrieve_note_context()` → UNION ALL across `story_notes` and `note_cards`, ordered by cosine score

**HNSW Indexes — Alembic Migration 0001 (`backend/migrations/versions/0001_pgvector_hnsw_indexes.py`)**
- 6 HNSW indexes created on all vector(1024) columns: `m=16, ef_construction=64`, `vector_cosine_ops`
- `CREATE INDEX IF NOT EXISTS` — idempotent and safe to re-run
- PostgreSQL-only (no-op on other dialects)

**Database Safety Fix (`backend/database.py`)**
- `run_db_migrations()` now guards embedding column additions behind `if not is_postgres:`
- Prevents TEXT-type embedding columns being added to PostgreSQL tables where `create_all()` has already created them as `vector(1024)` — which would cause a type mismatch with HNSW indexes

---

### Character Management

**Character CRUD and Profiles**
- Full CRUD for characters (`/api/stories/{id}/characters`) with role (protagonist/antagonist/supporting/minor) and status (active/deceased/unknown)
- Character profiles: age, appearance, personality, motivations, goals, backstory, arc_notes, traits, raw_notes
- Profile completeness score (0–100%) computed in `CharacterOut.completeness_score`

**Character RAG (Hybrid Retrieval)**
- Dual BGE-M3 embeddings per character: profile embedding + mention embedding (story-passage-grounded)
- Hybrid retrieval: name-mention boost + pgvector cosine similarity (profile: 0.4 weight, mention: 0.6 weight)
- SQL retrieves raw cosine scores for both columns; Python applies weights and rank-merges
- 800-token context budget cap

**Character Hints**
- Qwen extracts unregistered character names from chapter summaries (`key_events`, `characters_present`)
- Author can promote a hint to a tracked Character, or dismiss it
- `character_hints` table with `is_dismissed` flag
- `CharacterList.tsx` shows a collapsible hints banner when unacknowledged hints exist

**Character Enrichment**
- `POST /api/stories/{id}/characters/{cid}/enrich`: Qwen analyzes `CharacterMention` passages to suggest profile field values (appearance, personality, goals, motivations, backstory, arc_notes, traits)
- Returns `EnrichSuggestion` list with evidence snippets, chapter references, and confidence scores
- `CharacterProfilePanel.tsx` shows suggestions with accept/reject controls

**Character Arc Timeline**
- Per-chapter snapshots via `character_arc_snapshots` table (19th table)
- One row per (character, chapter) pair, enforced by `UniqueConstraint`
- Fields: `role_in_chapter`, `emotional_state`, `key_action`, `development_note`, `status_change`
- `is_stale` + `mention_count` fields support future incremental rebuild detection
- `CharacterArcTimelinePanel.tsx` renders the full timeline in the character panel

**Character Mentions and Sync**
- `index_character_mentions()` scans chapter chunks for name/alias matches, stores `CharacterMention` rows
- `POST /api/stories/{id}/chapters/sync-summaries` triggers re-indexing and re-embedding
- `mention_embedding` computed from all mention passages concatenated for a character

---

### Notes RAG

**Story Notes and Note Cards Backend**
- Full CRUD: `POST /api/stories/{id}/notes`, `PATCH /{nid}`, `DELETE /{nid}`
- Full CRUD: `POST /api/stories/{id}/note-cards`, `PATCH /{cid}`, `DELETE /{cid}`
- Note card types: scene, location, theme, character, general (validated in schema)
- BGE-M3 embedding triggered on every create and update via `asyncio.create_task()`

**Story Notes and Note Cards Frontend**
- `NotesPanel.tsx` (594 lines): tabs for notes and cards, inline editing with debounced auto-save, card type filter, delete confirmation dialog
- Integrated into project page alongside Plot Assistant and Character panels

**Notes RAG in Plot Assistant**
- `retrieve_note_context()` uses pgvector UNION ALL across `story_notes` and `note_cards`, ordered by cosine distance score, with configurable `top_k`
- Note context injected into Plot Assistant system prompt at every query

---

### Plot Hole Detection

- `detect_plot_holes()` in `ai_service.py`: Qwen analyzes all `ChapterSummary` rows for 6 inconsistency types
- Types: `character_inconsistency`, `location_inconsistency`, `timeline_inconsistency`, `unresolved_thread`, `continuity_break`, `character_disappearance`
- Returns `PlotHoleIssue` list with severity (high/medium/low), chapter numbers, description, and resolution hint
- Minimum 3 chapters required; returns analysis note if insufficient data
- `PlotHolesPanel.tsx` renders issues grouped by severity
- `AuditPanel.tsx` wraps both PlotHolesPanel and ManuscriptReportPanel

---

### Full Manuscript Analysis

- `analyze_manuscript()` in `ai_service.py`: Qwen generates structured `ManuscriptReport`
- Report sections: character arcs (with completeness: complete/partial/unresolved), pacing (slow/intense chapter lists + assessment), unresolved narrative threads (with introduction chapter), strengths, improvements
- All findings include chapter number references
- `ManuscriptReportPanel.tsx` renders the full structured report in the UI

---

### OCR Improvements

**GOT-OCR2.0 Pipeline**
- GOT-OCR2.0 replaces TrOCR + EasyOCR as the sole OCR engine
- Lazy-loaded on first OCR request (no startup penalty); module-level singleton
- GPU auto-detection with CPU fallback on CUDA OOM
- `confidence` score based on word-validity ratio of extracted text

**HEIC/HEIF Support**
- `pillow-heif` registered at module import via `register_heif_opener()`
- Dual validation: MIME type (`image/heic`, `image/heif`) AND file extension (`.heic`, `.heif`)
- Transparent to the rest of the pipeline — HEIC files are opened by PIL identically to JPEG/PNG

**OCR Image Cleanup**
- Hourly cleanup sweep in `main.py` via `_run_periodic_cleanup()` (asyncio background task)
- Confirmed uploads: image deleted after 24 hours (text safely in DB)
- Unconfirmed uploads: image deleted after 72 hours (session abandoned)
- `OcrUpload` record retained after image deletion (idempotency guard + OCR text traceability)

**OCR → 4 Destinations**
- story_notes, chapter_draft, character_profile, note_card
- Idempotency guard: `confirmed=True` prevents double-injection
- BGE-M3 suggestion grounding: story terms compared against OCR tokens for name correction hints

---

### Security

**SECRET_KEY Enforcement**
- `SECRET_KEY` is a required env var with no default
- Pydantic `model_validator` rejects keys shorter than 32 characters at startup
- `start-narratiq.sh` auto-generates a 64-char hex key on first run if absent
- Changing SECRET_KEY invalidates all active JWT sessions (intentional — documented in CLAUDE.md)

**User Ownership Enforcement**
- All story mutations verify `current_user.user_id == story.user_id`
- All character mutations verify user ownership through the story FK chain
- Manuscript job_status endpoint enforces `ManuscriptJob.user_id == current_user.user_id` (added this release)
- No cross-user data leakage possible

**JWT Authentication**
- HS256 algorithm via `python-jose`
- 7-day token expiry
- 401 interceptor in `frontend/lib/api.ts`: clears token + redirects to `/login` on any 401 response

---

### Production Architecture Upgrades

**Startup Script (`start-narratiq.sh`)**
- Self-bootstrapping from brand-new pod
- PGDG apt repository fallback for Ubuntu 22.04 (PostgreSQL 16 not in default sources)
- GPU auto-detection: TP=1 (1 GPU), TP=2 (2 GPUs), TP=4 (4+ GPUs)
- NCCL flags (`NCCL_P2P_DISABLE=1 NCCL_SHM_DISABLE=1`) for NVIDIA Blackwell (sm_120) compatibility
- `ovis.py` patch: adds `exist_ok=True` to `AutoConfig.register()` calls for transformers 4.51+ compatibility
- NumPy pinned to `≤2.2` for numba compatibility
- PyTorch cu128 forced for Blackwell sm_120 GPU kernel support
- Idempotent on repeated runs

**Background Tasks**
- All embedding generation uses `asyncio.create_task()` — non-blocking, in-process
- No external queue required for single-worker deployment
- Manuscript pipeline opens its own `SessionLocal()` — decoupled from request session lifecycle

**Alembic Migration Infrastructure**
- `backend/alembic.ini` + `backend/migrations/env.py` + `backend/migrations/script.py.mako`
- `env.py` reads `settings.database_url` at runtime (no hardcoded URL in ini file)
- Migration 0001: HNSW indexes on 6 vector columns (idempotent)
- Migration 0002: `manuscript_jobs` table (idempotent)

---

## Architecture Reference

The single authoritative architecture document for this release:

**`NarratIQ_AI_Production_Implementation_Report.docx`** (project root)

Covers: full architecture, all 19 database tables, all 17 completed features, API summary (15 routers), security architecture, background job architecture, production readiness assessment, remaining limitations, and future roadmap.
