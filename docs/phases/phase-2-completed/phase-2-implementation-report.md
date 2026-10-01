# Phase 2 — Implementation Report (Manuscript Intelligence)

| | |
|---|---|
| **Covers** | Phase 2 roadmap tasks P2-01 … P2-11 as implemented and running today |
| **Written** | 2026-10-01, task 11.6 (Stage 11), to satisfy roadmap §20.4 item 7 |
| **Supersedes** | The Phase 1 Production Implementation Report ([`phase-1-production-implementation-report.docx`](../phase-1-completed/phase-1-production-implementation-report.docx)) **for Phase 2**. That report predates Phase 2; its §11 describes Phase 2 only as a plan ("all 10 items", though the roadmap has 11), and its §12 migration names `0003_story_bibles` / `0004_narrative_threads` / `0005_pacing_goals` are wrong (the files are `0008`–`0010`, conflict C-6). Everything else in it still describes Phase 1 |
| **Specification** | [`phase-2-intelligence-expansion-roadmap.docx`](./phase-2-intelligence-expansion-roadmap.docx) |
| **Acceptance** | [`phase-2-acceptance-record.md`](./phase-2-acceptance-record.md) |

---

## 1. What Phase 2 delivered

Eleven capabilities that read the whole manuscript rather than one passage. They run on the existing three-service stack: vLLM/Qwen2.5-7B, FastAPI with in-process BGE-M3, and PostgreSQL 16 + pgvector. Phase 2 added one model, faster-whisper, and four tables. It added no new service, port, queue or external API.

| ID | Capability | Backend | Frontend | Model |
|---|---|---|---|---|
| P2-01 | Emotional arc map | `routers/analysis.py::get_emotional_arc` | `EmotionalArcPanel` | Chapter-summary tones; optional Qwen assessment |
| P2-02 | Chapter continuation (3 options) | `routers/writing_tools.py::generate_chapter_continuation` | AI sidecar (Write) | Qwen + chapter and character retrieval |
| P2-03 | Dialogue voice consistency | `routers/characters.py::check_voice_consistency` → `ai_service.check_dialogue_consistency` | `CharacterProfilePanel` | BGE-M3 + Qwen |
| P2-04 | Chapter / scene outline | `routers/writing_tools.py::generate_outline` | AI sidecar (Write) | Qwen |
| P2-05 | Continuity and world consistency | `routers/analysis.py::run_continuity_check` (batches of 10 chapters) | Analyze workspace | Qwen |
| P2-06 | Story Bible (5 sections, DOCX export, stale warning since Stage 11) | `routers/story_bible.py` (background job, `_generating` guard) | `StoryBiblePanel` (World) | Qwen |
| P2-07 | Dead-end narrative thread tracker | `routers/narrative_threads.py` (background scan) | `NarrativeThreadsPanel` | Qwen |
| P2-08 | Style drift | `routers/analysis.py::detect_style_drift` | `StyleDriftPanel` | BGE-M3 centroids, cosine in pgvector + Qwen |
| P2-09 | Pacing and word-count goals | `routers/pacing.py` | `PacingGoalPanel` (Plan) | none |
| P2-10 | Duplicate scenes | `routers/analysis.py::detect_duplicate_scenes` (pgvector `<=>`) | `DuplicateScenesPanel` | BGE-M3 + pgvector |
| P2-11 | Audio notes transcription | `routers/audio.py`, `services/audio_service.py` (lazy `_get_whisper`) | `AudioPanel` (World → notes) | faster-whisper large-v3-turbo + Qwen |

Endpoint paths are listed in [`CLAUDE.md`](../../../CLAUDE.md), "Phase 2 Features".

## 2. Database

| Migration | Table | Purpose |
|---|---|---|
| `0008` | `story_bibles` | Generated bible (`content_json`), version, timestamps. Stage 3 added `status` (`0015`) and `failed_sections` (`0016`) |
| `0009` | `narrative_threads` | Detected threads with status, which the author can resolve |
| `0010` | `pacing_goals` | Per-story targets |
| `0011` | `audio_uploads` | Transcription job and result, confirmation state |

The roadmap planned these as `0003`–`0006`; they were created as `0008`–`0011`, and `0003`–`0006` were never used. As specified in roadmap §7.4, no Phase 2 task added a vector column.

## 3. Models and runtime

- **Qwen2.5-7B-Instruct** and **BGE-M3** are reused. Every Qwen call goes through `services/ai_service.py`, and every embedding through the `get_bge()` singleton.
- **faster-whisper large-v3-turbo** is the one new model (roadmap §5.4). It is downloaded by `start-narratiq.sh` from `deepdml/faster-whisper-large-v3-turbo-ct2` at a pinned revision, because the roadmap's `openai/…` / `Systran/…` repositories now return 401. It runs on the CPU in int8 so it never competes with vLLM for GPU memory. It loads lazily on first use.
- **Long operations:**
  - The Story Bible, the narrative-thread scan and audio transcription run as `asyncio.create_task` background jobs, and the frontend polls.
  - The continuity check runs synchronously and splits large manuscripts into batches of 10 chapters.
  - Background Qwen work is bounded by `BG_AI_CONCURRENCY`.

## 4. What changed after Phase 2 shipped

Phase 2 was finished in June 2026. Later stages changed parts of it, and the changes matter for anyone comparing the roadmap with the code.

| When | Change | Task |
|---|---|---|
| Stage 3 | Continuation and outline crashed on every call (retrieval call-signature bug), now fixed | 3.1 |
| Stage 3 | Story Bible per-section outcomes: `completed` / `partial` / `failed`, `failed_sections`, per-section retry; placeholders are never stored as content | 3.2, 3.3 |
| Stage 3 | Degraded-output contract (continuity, plot holes) and the `_extract_json` hard-fail audit | 3.4, 3.5 |
| Stage 5 | Narrative-thread scan results persisted (`narrative_thread_scans`, `0023`) | Stage 5 D1 |
| Stage 8 | Every Phase 2 panel moved into the seven-workspace studio | 8.1, 8.8 |
| Stage 9 | All 14 Phase 2 production issues re-run as suites and re-verified resolved; cross-user isolation tested | 9.2, 9.5 (work done; task boxes open on other items) |
| Stage 10 | Audio files included in the orphan-upload sweep and in account deletion | 10.6 |
| Stage 11 | Story Bible stale warning (`0025`); P2-03/07/08 similarity moved to pgvector (R12); unmigrated columns recorded in Alembic (`0026`); prompt-injection defence for every AI call | 11.6, 11.7 |

## 5. Known limitations

- **Three deviations from the roadmap** are recorded and accepted in the acceptance record:
  - synchronous continuity checking (14.7 s for 200 chapters)
  - different audio route paths
  - the Whisper mirror and CPU device
- **Fixed in Stage 11:** numpy cosine moved to pgvector, stale detection built, and the voice-check scaling defect fixed. One decision is open: the R11 startup column guard.
- **A 200-chapter manuscript has been run through every Phase 2 feature** (Stage 11, rule R7). All features passed once the voice check was bounded.
- AI output quality is judged by authors in UAT (task 9.6), not by this report.
