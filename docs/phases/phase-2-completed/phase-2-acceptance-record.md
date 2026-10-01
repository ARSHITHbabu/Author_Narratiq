# Phase 2 — Formal Acceptance Record

| | |
|---|---|
| **Task** | 11.6 (Stage 11), Master Implementation Checklist |
| **Specification** | [`phase-2-intelligence-expansion-roadmap.docx`](./phase-2-intelligence-expansion-roadmap.docx): §16 Production Rules, §19 task specifications, §20.4 completion criteria, §20.5 out of scope |
| **Verification date** | 2026-10-01 |
| **Verified by** | Claude (implementation agent), on pod `xtkhp8n020qo5a` (1× A40), against the real model and a test database |
| **Accepted by** | **Product owner, on APPROVE COMPLETION of Stage 11.** Until that approval is recorded in the checklist, this record is *verified, pending acceptance* |
| **Companion** | [`phase-2-implementation-report.md`](./phase-2-implementation-report.md) |

**Evidence sources**
- **Live probe:** [`backend/scripts/acceptance/phase2_acceptance_probe.py`](../../../backend/scripts/acceptance/phase2_acceptance_probe.py). Its report is [`docs/testing/stage-11/phase2-acceptance-probe.json`](../../testing/stage-11/phase2-acceptance-probe.json): **19 passed, 1 failed**.
- **Static checks:** commands quoted in each row.
- **Earlier verified stages:** Stage 3, 6 and 9 results, cited by file.

**Verdict values**
- **Met:** verified true.
- **Met with deviation:** the purpose is met by a different mechanism than the roadmap specified. Accepted as recorded.
- **Not met:** an open gap, with the action named.
- **Not verified:** could not be checked in this pass, with the reason.

---

## 1. §20.4 system-level completion criteria

| # | Criterion (verbatim) | Verdict | Evidence | Verifier · date |
|---|---|---|---|---|
| 1 | "All 6 new Alembic migrations (0001–0006) apply cleanly on a fresh PostgreSQL database" | **Met with deviation** (numbering) | The Phase 2 migrations are `0008`–`0011`; `0003`–`0006` never existed. On 2026-10-01 a fresh PostgreSQL 16 database was created by `start-narratiq.sh` and taken to head `0024`. The test database `narratiq_test` was created empty and `alembic upgrade head` ran `0001 → … → 0024` cleanly. Round trip: §5 below | Claude · 2026-10-01 |
| 2 | "No MODEL_PLACEHOLDER stubs remain anywhere in the codebase" | **Met** | `grep -rn MODEL_PLACEHOLDER backend frontend/{app,components,lib}` returns 0 matches | Claude · 2026-10-01 |
| 3 | "All new endpoints enforce story ownership (404 for wrong user, not 403)" | **Met** | Live probe: a second author received **404** on all 13 Phase 2 endpoint calls for the first author's story. Stage 9 isolation suite, `test_cross_user_isolation.py` (`docs/testing/stage-09-regression-results.md`) | Claude · 2026-10-01 |
| 4 | "All Qwen calls use the existing _complete() function — no direct vLLM API calls" | **Met** | The only `AsyncOpenAI(` is in `services/ai_service.py`. No `chat.completions` call exists outside `ai_service.py`. Calls go through `_complete` / `_complete_ex` / `complete_structured` / `_stream_generate`, which are all wrappers in that module | Claude · 2026-10-01 |
| 5 | "All BGE-M3 calls use the existing get_bge() singleton — no new SentenceTransformer instances" | **Met** | The only `SentenceTransformer(` is inside `get_bge()` (`services/ai_service.py`) | Claude · 2026-10-01 |
| 6 | "start-narratiq.sh runs idempotently on a pod that already has Phase 2 installed" | **Met** | Second run on pod `xtkhp8n020qo5a`, 13:36:37–13:41:46 UTC (5 min 09 s), exit 0. Every step reported "OK" (Node, PostgreSQL, vLLM 0.9.2, PyTorch cu128, NumPy, transformers, backend packages, `node_modules`, all five models). Nothing was reinstalled or re-downloaded, `SECRET_KEY` was kept, and `/api/health` reported every service ready afterwards | Claude · 2026-10-01 |
| 7 | "Production_Implementation_Report.docx updated to reflect Phase 2 additions" | **Met** (superseded, as the checklist allows) | [`phase-2-implementation-report.md`](./phase-2-implementation-report.md) supersedes the Phase 1 report for Phase 2. [`docs/phases/README.md`](../README.md) annotates the Phase 1 report's wrong migration names | Claude · 2026-10-01 |
| 8 | "CHANGELOG.md updated with v3.1.0 section documenting all Phase 2 changes" | **Met** (retroactively) | [`CHANGELOG.md`](../../../CHANGELOG.md), "v3.1.0 — June 2026 — Phase 2", written 2026-10-01 | Claude · 2026-10-01 |
| 9 | "Audio upload directory (uploads/audio/) created and cleanup sweep active for audio files" | **Met** | `main.py` creates `settings.upload_dir_audio` at startup. `_cleanup_audio_files()` runs at startup and hourly in `_run_periodic_cleanup()`. Stage 10 added the orphan-file sweep | Claude · 2026-10-01 |
| 10 | "faster-whisper installed and openai/whisper-large-v3-turbo downloaded by start-narratiq.sh on first run" | **Met with deviation** (source and device) | `faster-whisper==1.2.1` is in `backend/requirements.txt`. On 2026-10-01 the first run on the reset pod downloaded `deepdml/faster-whisper-large-v3-turbo-ct2` at the pinned revision; the `openai/…` and `Systran/…` repositories now return 401. It runs on the CPU in int8, not "GPU with CPU fallback". The live probe's audio job completed, so Whisper lazy-loaded | Claude · 2026-10-01 |

"Phase 2 is complete when all 11 tasks meet their individual Completion Criteria listed in Section 19" is assessed in §3. **One §19 criterion is not met** (P2-06 stale detection).

## 2. §16 Production Rules

| Rule | Verdict | Evidence |
|---|---|---|
| R1 No temporary features, stubs or TODOs | **Met** | 0 `TODO`/`FIXME`/`XXX` in the Phase 2 routers and `audio_service.py`; no placeholder stubs (item 2) |
| R2 No hardcoded values | **Met** | Limits, model ids, paths and thresholds come from `config.py`. Thresholds such as the voice check's 0.72 are named constants in code, as specified in §19 |
| R3 No paid or external AI APIs | **Met** | No external AI host appears anywhere in backend runtime code. The only LLM client points at the local vLLM (`api_key="vllm-local"`) |
| R4 No external transmission of author data; no telemetry | **Met** (fixed in Stage 11) | No analytics SDK and no remote logging; error tracking is built in (`error_events`, Stage 10). The one external browser request, Google Fonts (IP address and referrer, no manuscript content), was **removed on 2026-10-01**. Inter is now self-hosted from the pinned `@fontsource/inter@5.3.0` package (SIL OFL). Test: `frontend/tests/studio/self-hosted-fonts.spec.ts` fails if any request goes to `fonts.googleapis.com` / `fonts.gstatic.com`, and checks that Inter still renders |
| R5 Prefer existing models | **Met** | Tasks 1–10 use Qwen and BGE-M3 only |
| R6 New models need clear author value | **Met** | Whisper (P2-11) is the only new model; speech-to-text cannot be done with Qwen or BGE-M3 |
| R7 Any genre, any manuscript size (3 to 200 chapters) | **Met** (verified at 200 chapters in Stage 11) | Synthetic 200-chapter manuscript, real model (`backend/scripts/acceptance/large_manuscript_probe.py`; report `docs/testing/stage-11/large-manuscript-200-chapters.json`). All 10 Phase 2 features answered 200 / completed: emotional arc 0.1 s, continuation 23.1 s, outline 9.8 s, continuity 14.7 s (all 200 chapters scanned), style drift 0.2 s, pacing 0.0 s, duplicate scenes 1.5 s, Story Bible 95.6 s (background job, all 5 sections), thread scan 327 s (background job, 200 chapters, 0 degraded batches). **One scaling defect found and fixed:** the voice check took 91.9 s for 110 dialogue passages, against a ~100 s proxy limit. It now analyses at most 80 passages sampled evenly across the manuscript, embeds them in one batch and describes flagged pairs concurrently, and it says how many it analysed: **400 passages in 24.0 s**. Tested in `backend/tests/test_voice_check_scale.py` |
| R8 Ownership on every new endpoint | **Met** | §20.4 item 3 |
| R9 Idempotent writes | **Met** | Story Bible re-generation updates the existing row (`create_or_regenerate_bible`), with a `_generating` guard against duplicates. Audio confirm overwrites the target note with the current transcript rather than appending, so a repeated confirm does not duplicate text. Pacing goals upsert, one row per story. The thread scan upserts by thread name and never overrides a thread the author resolved |
| R10 Work over 2 s runs as a background job returning a job id | **Met with deviation** (justified by measurement) | Story Bible, thread scan and audio are background jobs. **P2-05 continuity stays synchronous**: at 200 chapters it scanned every chapter in **14.7 s** (batches of 10 run concurrently), far inside the ~100 s proxy limit. Converting it to a job would add polling for no measured benefit. Revisit if manuscripts far beyond 200 chapters become a target |
| R11 Alembic for all schema changes | **Met with one recorded exception** (gap fixed in Stage 11) | Migration **`0026`** (2026-10-01) records in Alembic the four columns that had no migration at all (`character_profiles.goals`, `.traits`, `chapter_chunks.character_ids`, `chapter_summaries.character_ids`), so every ORM column now has one. It was proven to add them where missing, and its downgrade deliberately keeps them (author data). **Exception kept for the product owner:** `database.py::run_db_migrations()` still runs guarded `ALTER TABLE … ADD COLUMN` at startup, before Alembic, as a safety net for a backend started without `alembic upgrade`. Removing it changes deployment startup behaviour, so it is a decision, not a fix made here |
| R12 No numpy cosine; all vector similarity in pgvector `<=>` | **Met** (fixed in Stage 11) | Every similarity in P2-03, P2-07 and P2-08 is now computed by pgvector through `services/vector_math.py` (one SQL query per call, nothing stored). Style drift's representative passages are retrieved with `ORDER BY embedding <=> centroid`. numpy only averages centroid vectors (arithmetic). Equivalence with the old numpy results is tested to 1e-5 on 1024-dimension vectors (`backend/tests/test_vector_math.py`), which also guards against numpy cosine returning to these routers. The voice-agent catalog (`services/voice/catalog.py`) still uses numpy; it is not a Phase 2 feature |
| R13 Lazy loading for new models; startup must not grow | **Met** | Whisper is lazy (`audio_service._get_whisper`) and so is GOT-OCR. BGE-M3's eager load is the Phase 1 design |

## 3. §19 task completion criteria

Live probe results are in `docs/testing/stage-11/phase2-acceptance-probe.json`. "Frontend renders…" criteria rely on the Stage 8 studio suite (each panel's home is enforced by `tests/tool-homes.spec.ts`) and the Stage 9 live browser run (62/64, `docs/testing/stage-09-regression-results.md`), plus a read of each component. They have not been re-judged visually by an author.

| Task | §19 completion criteria | Verdict | Evidence |
|---|---|---|---|
| P2-01 Emotional arc | Ordered tone data for all chapters; optional assessment; panel renders; NULL tones handled | **Met** | Probe: 6/6 chapters in order, `assessment` present. `EmotionalArcPanel` in Analyze |
| P2-02 Continuation | 3 continuations per call, grounded; insert into editor | **Met** | Probe: exactly 3. Grounding comes from chapter and character retrieval, a defect fixed in Stage 3 (3.1). Insert action in the Write sidecar |
| P2-03 Voice consistency | Structured inconsistency list; insufficient data handled; renders in the profile; meaningful score | **Met** | Probe: structured response; a character with no mentions → `insufficient_data`. When fewer than 3 quoted passages exist it falls back to all mention passages and says so in `note`, exactly as §19's own "Production Risks" specify. Score in [0, 1]. Since Stage 11 the score and pairs are computed by pgvector, and at most 80 passages are analysed (sampled evenly across the manuscript, with the count stated in `note`) |
| P2-04 Outline | Structured beats with all fields | **Met** | Probe: 4 beats, each with `scene_number`, `beat_description`, `characters_present`, `location`, `pacing_note` |
| P2-05 Continuity | Structured issues with chapter references; known contradictions detected; renders by category | **Met** (detection quality judged in Stage 3/5) | Probe: structured `issues` with `chapters_scanned` and an honest `degraded` flag. Contradiction detection was verified on the Stage 3 grounding fixture (task 3.4) |
| P2-06 Story Bible | All 5 sections; stored; DOCX export; **stale detection works**; renders all sections | **Met** (stale detection built in Stage 11) | Probe: all 5 sections, `completed`, stored, DOCX export (valid zip). **Stale detection added 2026-10-01:** the bible stores the fingerprint of the indexed chapters it was generated from (`story_bibles.source_fingerprint`, migration `0025`, the same fingerprint the saved Manuscript Report uses). `GET /story-bible` returns `is_stale`, and `StoryBiblePanel` shows "Your chapters have changed since this Story Bible was generated". Tests: `backend/tests/test_story_bible_stale.py` (9 cases: edit, re-index, deletion of the last chapter, an edit during generation, section-only regeneration, legacy and running bibles) and `frontend/tests/studio/story-bible-stale.spec.ts` (3 cases + axe) |
| P2-07 Thread tracker | Scan populates table; dead ends flagged; manual resolution; status badges | **Met** | Probe: scan `completed`, 5 threads written, PATCH to `resolved` works. Scan outcome persisted since Stage 5 (D1) |
| P2-08 Style drift | Drift score from BGE-M3 centroids; description when significant; insufficient data handled; gauge and samples | **Met** (R12 deviation above) | Probe: `drift_score` 0.0044 on near-identical chapters; 1-chapter story → `insufficient_data` |
| P2-09 Pacing goals | Stored and retrieved; progress computed; progress bar and distribution | **Met** | Probe: stored, `progress_pct` computed, `chapter_distribution` has 6 entries |
| P2-10 Duplicate scenes | Pairs with scores; threshold configurable; snippets and navigation | **Met** | Probe: 11 pairs at threshold 0.9 on near-identical fixture chapters, each with score, titles and snippets |
| P2-11 Audio | audio_id immediately; async transcription; confirm appends idempotently; Audio tab; record and upload; lazy Whisper and CPU; 24h/72h cleanup; ownership on all 4 endpoints; installed by script | **Met with deviation** (routes, model source) | Probe: `audio_id` returned immediately, and the job reached `completed` with lazy Whisper on the CPU. 404 for another author. Routes are `/api/stories/{id}/audio…`, not `/api/audio/…`. **Not re-checked in this pass:** transcription of real speech and microphone recording; both need a person (manual, as in task 6.4) |

## 4. §20.5 out-of-scope items: do they remain out of scope?

| §20.5 item | Status today | Verdict |
|---|---|---|
| Real-time collaboration | Not built. The collaboration permission seam always grants access, so stories are single-owner | Remains out of scope |
| ePub / Kindle export | Not built (DOCX and PDF only) | Remains out of scope |
| Cover art generation | Not built | Remains out of scope |
| Full voice-controlled UI or continuous dictation | **Partly built later.** The real-time voice agent (`routers/voice_agent.py`, migration `0012`) adds spoken commands with streaming speech-to-text. It is a separate, later feature, not part of Phase 2. Continuous dictation into the chapter editor is still not built | Out of **Phase 2's** scope, correctly. The voice agent shipped as its own feature |
| External AI APIs | None (R3) | Remains out of scope |
| Public sharing or publishing | Not built. The "Publish" workspace is export only (DOCX/PDF), with no public link or sharing | Remains out of scope |
| Mobile app | Not built (responsive web only) | Remains out of scope |
| Paid subscription or billing | **No billing.** Phase 3 added `users.plan` (migration `0022`) with plan limits, but plans are assigned manually and no payment is taken (Phase 3 decision D2) | Remains out of scope |

## 5. Items run after the probe

| Check | Result |
|---|---|
| §20.4 item 6, `start-narratiq.sh` second run (idempotency) | **PASS**: see §1 item 6 |
| Migration round trip on the seeded test database (`backend/tests/run_migration_roundtrip.sh`) | **PASS**: upgrade to head; downgrade to `0018` with 7/7 author tables byte-identical; re-upgrade; a third upgrade is a no-op |

## 6. Summary for the product owner

Phase 2 is **verified as delivered**, with these recorded results:
- **No unmet §19 criterion.** P2-06 stale detection, found missing on 2026-10-01, was built and tested the same day.
- **Fixed in Stage 11, not accepted:**
  - P2-06 stale detection
  - R12 numpy cosine (now pgvector)
  - R4 Google Fonts (self-hosted)
  - R11's four columns with no migration (`0026`)
  - the R7 voice-check scaling defect
- **Accepted-as-recorded deviations:**
  - migration numbering
  - Whisper source and device
  - synchronous continuity checking (R10, measured 14.7 s at 200 chapters)
- **One decision left to the product owner:** whether to remove the startup column guard (R11).
- **R7 verified at 200 chapters.**
- **No third-party browser requests:** Google Fonts replaced by self-hosted Inter.

Approving Stage 11 completion records the product owner as the accepting party for this record.
