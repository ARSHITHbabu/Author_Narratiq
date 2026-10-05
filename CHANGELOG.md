# NarratIQ AI — Changelog

All production changes are documented here in reverse chronological order.

---

## v3.3.0 — Release candidate, 2026-10-05 (NOT released)

**Status:** release candidate only. Release approval (checklist task 12.3, Gate 9) has not been given, and the
application still reports version `3.0.0` (`backend/main.py`, `/api/health`; `frontend/package.json` says `0.1.0`).
Aligning the version strings is a 12.3 step after sign-off. Release notes, gate status and the single list of known
limitations: [`docs/releases/v3.3.0-rc-release-notes.md`](docs/releases/v3.3.0-rc-release-notes.md).

This release candidate is everything since v3.2.0. It was recorded below in separate "Unreleased" sections as each
stage was approved; they are kept intact as the parts of v3.3.0, newest first, each with its original title:

| Part | Original section title |
|---|---|
| 9 | Stage 12.3 release preparation (below) |
| 8 | Unreleased — Stage 12.2 release-candidate documentation (this section's own changes, below) |
| 7 | Unreleased — Stage 12.1 release-candidate verification |
| 6 | Unreleased — Stage 12 remediation, Tranche 3 |
| 5 | Unreleased — Stage 12 remediation, Tranche 2b + voice D-1 |
| 4 | Unreleased — Stage 12 remediation, Tranche 2a |
| 3 | Unreleased — Stage 12 remediation, Tranche 1 |
| 2 | Unreleased — Stage 11: Phase 2 acceptance fixes and documentation tooling |
| 1b | Stages 3–6 and 8–10 (recorded retroactively on 2026-10-05; they had no CHANGELOG entry) |
| 1a | Unreleased — Phase 3: Author-Centric AI Workflow (Stage 7) |

Database: migrations `0016`–`0027` (`0019`–`0022` Stage 7; `0025`–`0026` Stage 11; `0027` Stage 12; the others in
part 1b). Migrations `0012`–`0015` (voice-agent tables, `activity_events`, `story_intakes.analysis`,
`story_bibles.status`) were added on 2026-06-12/13, before v3.2.0, and have never had a CHANGELOG entry; they are
listed here for completeness and are not part of this release candidate's changes.

### v3.3.0 RC · part 9 — Stage 12.3 release preparation

#### Fixed
- **Light strength changed almost as much as Strong for tone and age adaptation** (owner review A2: Light was
  acceptable and lighter in only 5 of 12 pairs). A Light rewrite that adds more than 45% new words — the boundary
  measured from the owner's labels — is now retried once with explicit feedback; the retry is used only if it is
  lighter and keeps every character name, and a result still too heavy shows the "changed more than expected" note.
  Requests for something new (derivations, combined pins, avoid-sets) are exempt. Light outputs over the boundary:
  age adaptation 51% → 14%, tone 32% → 20%, style 24% → 23% (600 generations,
  `backend/tests/fixtures/strength_t2b_after_v4_light_repair.json`). Human re-validation of Light is still open.
  Tests: `backend/tests/test_light_strength_repair.py`.

#### Added
- `scripts/daily_check.sh` — the read-only daily operational check required while alerts are not delivered to a
  person (W-4); `docs/operations/release-regression.md` — the regression every release records against its exact
  commit (W-1); `docs/releases/v3.3.0-sign-off.md` — the unsigned release-approval record.
- Browser test for single-step undo of an applied AI result (`frontend/tests/studio/undo.spec.ts`, task 7.3).

#### Configuration
- `LIGHT_STRENGTH_REPAIR` (default `true`), `LIGHT_NEW_SHARE_MAX` (default `0.45`).

### v3.3.0 RC · part 8 — Stage 12.2 release-candidate documentation

#### Documentation
- Release-candidate notes with one known-limitations list (`docs/releases/v3.3.0-rc-release-notes.md`).
- Operations runbooks checked against the scripts and corrected where they had gone stale: deployment (CORS scope,
  `npm ci`, `.next.prev`, the startup backup/guard, backup loop and watchdog steps, line references, model size),
  how-to-run (sign-in now returns a cookie, `BACKEND_INTERNAL_URL`, Next.js 15, migration count), backup and restore
  (new §4a on the empty-database guard), rollback (`0026`'s intentional no-op downgrade), storage and persistence
  (a pod replacement loses the volume's backups too; resolved §6), incident response.
- A documentation-only operator walkthrough on a fresh pod: `docs/testing/stage-12/stage-12.2/operator-walkthrough.md`.

#### Security (measurement)
- **Prompt-injection probe coverage completed** for chapter summaries, cast generation, Story Intelligence,
  transcript clean-up, OCR and voice commands: 0 obeyed (`backend/scripts/security/injection_coverage_probe.py`).
- **Found:** chapter-scoped story Q&A — the Plot Assistant's default request and voice story questions —
  followed an instruction planted in the open chapter (voice 12/12, Plot Assistant 9/12 with 3/12 refused, 0
  answered). The earlier "0 obeyed in 17 features" was measured with full-manuscript scope and no chapter text.

#### Fixed (security)
- **Chapter-scoped story Q&A no longer follows instructions planted in the chapter.** Story Q&A
  (`answer_story_question`: Plot Assistant Q&A and mixed answers, voice story, character and relationship
  questions) now *datamarks* the fenced material in the prompt copy: a `ˆ` replaces every 4th gap between words, and
  every gap in the open chapter's excerpt (the last material before the question). The author's stored text, the
  question and the answer are never marked; a marker echoed by the model is removed. The window fit measures the
  marked prompt, so it cannot overflow; a full-depth chapter-scoped prompt (10 passages) still fits with ~800 tokens
  to spare. Rewording the task was measured first and did not help (an explicit framing made obedience worse);
  marking every gap would have cost ~1.8× tokens and trimmed passages. End-to-end on the injected story, 12 runs per
  cell over two question wordings: Plot Assistant default request 0 obeyed / 0 refused / 12 correct (was 9 / 3 / 0),
  voice 0 / 0 / 12 (was 12 / 0 / 0), every other cell 12/12 correct. Six attack styles and questions about the planted
  text, clean natural-fiction chapters, the 17-feature probe, the coverage probe and the clean-prose probe: see
  `docs/testing/stage-12/stage-12.2/injection-coverage.md` §4. `PROMPT_INJECTION_DATAMARK_QA=false` restores the
  previous Q&A prompt. Tests: `backend/tests/test_qa_datamark.py`; probes `qa_injection_matrix.py`,
  `qa_adversarial_probe.py`.

#### Fixed
- **False "uvicorn is running WITHOUT --no-proxy-headers" ERROR at startup** when the backend was launched through a
  shell command line (`bash -c "… uvicorn … --no-proxy-headers"`): the check treated the shell's single command-string
  argument as a uvicorn launch that lacked the flag. It now recognises uvicorn only as the program or module itself
  (`startup/worker_guard.py`). Diagnostic only — rate limiting was never affected, and `start-narratiq.sh` launches
  were never misreported. Test: `test_monitoring_stage10.py::test_uvicorn_proxy_headers_warning` (fails on the old
  code).

#### Configuration
- `PROMPT_INJECTION_DATAMARK_QA` (default `true`; needs `PROMPT_INJECTION_GUARD`).

#### Changed
- `scripts/startup_backup.sh`: when the empty-database guard stops a start, its message now points to the rehearsed
  restore procedure (`backup-and-restore.md` §4) instead of printing a one-line `pg_restore --clean` command that
  ran as the application user and differed from that procedure. The guard's decision logic is unchanged.

---

### v3.3.0 RC · part 7 — Stage 12.1 release-candidate verification

*Original title: "Unreleased — Stage 12.1 release-candidate verification (not a release)".*

#### Fixed
- **Long chapters were summarised from their first 8,000 characters only.** `generate_chapter_summary` cut the
  chapter text at 8,000 characters (about 1,400 words), so anything later in a long chapter never reached the
  stored summary, the Story Bible or the Manuscript Report. The chapter is now read whole: in one call when it
  fits the model's context, otherwise in sentence-aligned windows sized from `max_model_len` whose results are
  merged (lists de-duplicated in order, one short merge call for the prose summary, falling back to the joined
  parts). Live: on a 4,034-word chapter the old code read 34 % of the text; a late revelation reached the summary
  0/3 times before and 3/3 after. Tests: `backend/tests/test_chapter_summary_windows.py`.
- **BGE-M3 embedding on CPU was throttled ~13x.** torch sized its CPU thread pool from the host (48 threads on the
  A40 pod) while the container's CPU quota is 7.65 CPUs; the two BGE workers ran ~96 threads. Indexing 40 chapters
  took 44 minutes. The thread count now follows the cgroup quota divided by the BGE workers (`cpu_quota()`,
  `bge_cpu_threads()` in `services/ai_service.py`); 12 chunks: 32.5 s → 2.4 s. Takes effect at the next backend
  start. Tests: `backend/tests/test_bge_cpu_threads.py`.
- **Plot Assistant ideas reported "0 passages, no chapters" while using three chapters.** Creative suggestions
  are grounded on chapter summaries, which the structured retrieval metadata (task 4.4) did not report, so a
  whole-story question classified as creative looked like it had searched nothing. `retrieval.summary_chapters` now
  names the summarised chapters the ideas were based on, and the panel shows them. Found by the live task 4.1 check.
  Tests: `backend/tests/test_plot_assistant_retrieval_meta.py` (fails without the fix),
  `frontend/tests/studio/plot-assistant-scope.spec.ts`, live `frontend/tests/browser/plot-assistant-scope.spec.ts`.
- **The Plot Assistant scope toggle exposed its state only by colour.** "This chapter" / "Full manuscript" are now a
  labelled group with `aria-pressed`, covered by the new studio test.
- **Story Bible copied the prompt's own examples into real bibles** (e.g. invented world rules from the example
  text) and could print a literal "[Ch N]". The prompts now use placeholders, and output lines that repeat a prompt
  example or carry the placeholder tag are dropped. Live: 9/10 and 10/10 leaking runs before, 0 in 10 × 5 sections
  after. Tests: `backend/tests/test_story_bible_prompt_examples.py`.
- **Search could show results for an older query** when responses arrived out of order (SEARCH-1/2/3). Only the
  newest request may update the panel. Studio test fails on the old code, passes on the fix.
- **The Manuscript Report did not show stakes, plot weight, themes or open tracker threads** that the backend
  already returned (AUDIT-H8/H9/H10).

#### Added
- Long-manuscript Plot Assistant measurement: a 40-chapter, 32k-word fixture with planted critical and decoy
  passages (`backend/tests/fixtures/long_manuscript_*`), and `measure_long_manuscript_ranking.py` /
  `measure_long_manuscript_coverage.py`. Results: `docs/testing/stage-12/stage-12.1/pa-long-manuscript-measurement.md`.

---

### v3.3.0 RC · part 6 — Stage 12 remediation, Tranche 3

*Original title: "Unreleased — Stage 12 remediation, Tranche 3 (release candidate work, not a release)".*

#### Fixed
- **Audio dictation could lose the author's words.** The transcript clean-up (Qwen) dropped a whole dictated
  sentence such as "Audio note for chapter 3." or "Note to self for the next draft." in 19 of 20 live runs,
  although its instructions forbid removing content. The cleaned text is what "Append to Note" saves. Code
  now enforces the rule: if the clean-up loses more than 10 % of the transcript's non-filler words, the raw
  Whisper transcript is kept. This also covers dictations longer than the 3,000 characters sent to the model,
  which used to lose their end. Measured after the fix: 40 of 40 outputs keep every word, and filler removal
  and dialogue punctuation still apply.
- **Continuity Check reported a marked flashback as a timeline error.** Indexing keeps a chapter's date
  ("April 20, 2010") but drops the cue ("In a flashback to …"), so a flashback that the text marks was
  reported in 3 of 3 runs. A chapter whose own text has a flashback or flash-forward cue in the same sentence
  as a date or year is now treated as one. An unrelated "years ago" elsewhere in a chapter still cannot hide
  a real reversal. MV-5.14-A now passes: the planted reversal is reported 3/3, and the marked flashback 0/3.
- **`start-narratiq.sh` only worked from `/workspace/narratiq-ai`.** It now finds its own checkout, so the
  repository can live at any path. No symlink is needed.
- **A pod that was only ever empty could not restart** (the Stage 10 empty-database guard false positive).
  The guard treated any valid backup as proof that author data had existed, including the hourly backups of an
  empty database. It now reads each set's checksummed manifest (`scripts/backup_evidence.py`). A set counts
  as evidence unless its manifest proves the snapshot held no author rows. Missing, unverifiable or unknown
  manifests still count, and an older data backup is never hidden by newer empty ones. An empty database
  whose backups hold author data still stops startup, deleted on purpose or not: the database cannot show
  why its rows are gone (`scripts/tests/test_startup_backup_guard.py`, 12 tests).
- **Restore runbook hazard.** With the connection variables from the verification step still exported,
  `su postgres -c "dropdb …"` dropped the database as its owner and `createdb` then failed.
  `backup-and-restore.md` §4 now says to clear them first.

#### Added
- **The live audio-transcription browser test runs** (it had been skipped since Stage 6). A synthetic speech
  fixture (espeak-ng, regenerable, byte-identical, see `frontend/tests/browser/fixtures/audio/README.md`)
  goes through upload → real transcript (at least 6 of 9 known words) → append to a note → reload. A silent
  file fails the test.
- **Security regression tests:** a replay of the output checks over every committed real model output
  (`test_output_checks_replay.py`), and a guard that every model call goes through the prompt-injection
  fence (`test_vllm_call_sites.py`). Every security probe output now records the commit, prompt version and
  guard setting that produced it.
- **Injection probe coverage:** emotion, age-adapt, style and translate. Current code: 0 obeyed in 17
  features, 0 false refusals in 84 legitimate rewrites and 60 clean-prose calls.

#### Documentation
- Current facts in `CLAUDE.md`, `README.md`, the product specification and the operations guides:
  - OCR works (Stage 12 A2);
  - Next.js 15.5;
  - migration head `0027`;
  - vLLM listens on 127.0.0.1;
  - streaming routes are off by default;
  - prompt v4;
  - three settings were missing from the environment-variable reference.

  Dated records are kept and given addenda instead of being rewritten.
- Rollback runbook: an isolated rehearsal of the previous release (`0032a81`, Next.js 14, `0026`) took
  369 s, with data intact apart from the documented presence labels. The model revision rollback took 26 s to
  download. The `PROMPT_VERSION` configuration rollback is now documented.
- Capacity: Tier-2 measured. At 50 % strict consistency, up to 15 active authors meet the rewrite and Q&A
  targets but search exceeds its p95 target. At 10 %, 60 authors meet every target.
- Backup/restore: the first end-to-end fresh-pod recovery time, about 21 minutes (target ≤ 2 h).

### v3.3.0 RC · part 5 — Stage 12 remediation, Tranche 2b + voice D-1

*Original title: "Unreleased — Stage 12 remediation, Tranche 2b + voice D-1 (release candidate work, not a release)".*

#### Fixed
- **Voice questions searched the whole manuscript while the author worked in an early chapter.** Voice story,
  character and relationship questions now stop at the open chapter (passages, character evidence and Story
  Intelligence, with the same provenance rule as the Plot Assistant). The whole manuscript is searched only when
  the author asks ("in the whole book", "across the whole manuscript", "all chapters"); a broad question is not
  such a request. With no chapter open the agent asks the author to open one instead of searching everything.
  Recorded relationships (no chapter information) are used only for whole-book questions.
- **Continue and Outline quoted character evidence from later chapters.** Character evidence now has the same
  chapter boundary as the summaries they already used.
- **Children's adaptation said "already suitable" for passages that only imply a death** ("nobody survived").
  For children's adaptation only, such a verdict now goes on to the normal rewrite the author reviews; it never
  blocks, removes or warns. YA and adult are unchanged. The suitability question no longer reads "ALREADY
  already …".
- **A rewrite could end with the prompt-injection fence marker** (`<<<END_AUTHOR_MATERIAL …>>>`, 1 of 780
  measured outputs). Echoed markers are removed from every model output.
- **Writing suggestions' sharpening pass never ran** since the v3 prompts became the default (it was gated on
  the resolved version being exactly "v2"). It runs again for every version except the frozen v1.

#### Added
- **Invented-name note (warning only):** a rewrite that introduces a capitalised name absent from the passage
  gets a soft note ("adds name(s) not found in your text or story"). Sentence starts, anything already in the
  passage in any capitalisation, calendar words, short acronyms, roman numerals and honorifics are ignored; it
  never blocks or retries. Measured: 1 flag in 647 stored rewrites (a fence marker, now stripped), every name
  inserted mid-sentence found; names at a sentence start are missed (documented).
- **Output check for generated text** (Q&A, plot suggestions, writing suggestions, continue): an output that
  copies an instruction out of the author's material verbatim and has dropped the story is retried once
  (Q&A) or dropped (list items, continuation options), then refused with 422 `instruction_like_text` and an
  honest message. Both conditions must hold, so fiction that quotes instruction-like dialogue is not refused.
  Measured before switching on: 0 flags in 203 clean-prose outputs, 0 of 84 Stage 11 rewrites, 3 of 3
  obeyed samples from before the Stage 11 fence.
- **`strength_detail`** on rewrite responses: how much of the author's wording survived (kept share, new
  share, word order, lowest per-sentence share). Data only; no threshold, warning or retry is attached.
- **Writing-suggestion hygiene:** items with no real recommendation and duplicates within one response are
  dropped; positive words inside a concrete recommendation never cause a drop.

#### Changed
- **Prompt version v4 is the default:** at Light strength, Style no longer asks the model to restructure
  sentences (v3 asked for restructuring at every strength, contradicting the Light rule). Measured: Light now
  keeps a median 0.71 of the author's words against Strong's 0.58 (v3: 0.60 vs 0.59). Light-only wording for
  tone and age adaptation, and a gentler children's guide, were measured and not adopted.
  `PROMPT_VERSION=v3` restores the previous prompts exactly.

#### Configuration
- `CHILDREN_SUITABILITY_OVERRIDE` (default `true`).

### v3.3.0 RC · part 4 — Stage 12 remediation, Tranche 2a

*Original title: "Unreleased — Stage 12 remediation, Tranche 2a (release candidate work, not a release)".*

#### Fixed
- **Search & replace could damage the manuscript.** Replacing "amp" turned `&amp;` into `&X;`; Replace One
  across bold/italic changed a different occurrence than the one selected; the replacement was inserted as
  raw HTML; and a reload after a replace could discard (or overwrite) the last 1.5 s of typing. Search,
  highlighting, the Replace All preview and the replacement itself now share one text model
  (`services/search_match.py`, mirrored by `frontend/lib/searchMatch.ts`): matches work across formatting,
  never cross paragraphs or line breaks, and whole-word matching is Unicode-aware. Replacement text is always
  stored as text; a replace that would alter the chapter's markup is refused and nothing is saved. Typing is
  saved before any search or replace.
- **Plot Assistant: "this chapter" with no chapter open searched the whole manuscript.** It now answers
  "Open a chapter or choose Full manuscript." Voice brainstorming uses the chapter open in the editor.
- **Cast generation could fail outright** when one pass described many characters (the model's JSON was cut
  off); every complete character is now kept. Two different people sharing a first name are no longer merged
  ("Tomas" vs "Tomas Reyne"); a kinship claim ("her sister") must be supported by the text near that
  character's name.

#### Added
- **Story Intelligence for chapter-scoped answers, safely.** Consolidated memory now records an upper bound
  (derived only from chapters 1–N); chapter-scoped Plot Assistant requests use it only at or after chapter N.
- **Cast presence**: each suggestion and character is *On page*, *Mentioned only* or *In the past*, separate
  from alive/deceased (migration `0027`, `characters.presence`). Off-page figures are listed and labelled,
  not pre-selected. Possible duplicates within one result, and records the AI may have combined, are noted.
- **Cast importance order** for suggestions (on page, role, mentions, first appearance, name), and an optional
  "By importance" sort for the saved cast — alphabetical stays the default.
- Plot Assistant Q&A: character questions are recognised by title, alias, possessive or part of a name;
  plot importance only breaks near-ties; evidence is spread across chapters at full scope; the prompt is
  measured with the real tokenizer and always fits the model window.

#### Changed
- Search options are labelled "Match case" and "Whole word" (whole word stays off by default).
- Cast prompt is versioned (`cast` v2 = previous prompt, v3 = presence); `PROMPT_VERSION=v2` restores it.

### v3.3.0 RC · part 3 — Stage 12 remediation, Tranche 1

*Original title: "Unreleased — Stage 12 remediation, Tranche 1 (release candidate work, not a release)".*

#### Added
- **Import a manuscript from the Write binder** ("Import manuscript…", .txt or .docx, up to 25 MB). Lines such
  as "Chapter 1" start a new chapter. Every chapter is saved, in one step, before the dialog reports success;
  imported chapters are numbered after the story's existing chapters, which are never changed. Search and AI
  preparation then runs in the background with a progress bar. If it stops, the dialog says how many chapters
  still need preparing, and the text stays saved. Unsupported and empty files are refused before upload.
- **Possible duplicate characters** (Characters workspace): pairs that may be the same person are listed with
  the reason (shared name or alias, shorter/longer form of a name, near-identical spelling, very similar
  profiles). The author picks which character to keep and confirms in-page; nothing merges automatically.
  "Not the same person" hides a pair in this browser. Cast generation marks a suggestion that may duplicate an
  existing character and does not pre-select it. `GET /api/stories/{id}/characters/duplicate-candidates`.

#### Fixed
- **Plot Assistant spoiler leak (D-1).** With the default chapter scope, creative and mixed answers still
  received whole-manuscript Story Intelligence: premise, themes, character secrets and arc stages, open
  threads and every story-memory entry. Chapter-scoped requests now receive only genre, tone, point of view
  and tense; "Search entire manuscript" is unchanged.
- **OCR never read an image** (`'DynamicCache' object has no attribute 'seen_tokens'`). GOT-OCR2.0's vendored
  code uses two cache members removed from the pinned transformers; `ocr_service` restores them before the
  model is used. Verified with the real model on the A40.
- **Manuscript import** created duplicate chapter numbers when the story already had chapters, could stop part
  way without saying so, showed raw error text, and stored plain text without paragraphs.
- **`scripts/rollback_frontend.sh`** stopped every Next.js process on the pod; it now stops only the server on
  its port, and finds the frontend relative to the script.

#### Changed
- **Unprotected streaming rewrite routes are off.** `/api/ai/<tool>/stream` skipped sentence locks, strength
  limits and the preservation and prompt-injection checks; no screen used them. They answer 404 unless
  `AI_STREAM_ROUTES_ENABLED=true` (diagnostics only).

#### Security
- vLLM now listens on `127.0.0.1:9001` only (was `0.0.0.0`, no API key).
- `python-jose` 3.4.0 → 3.5.0 and `pyasn1` 0.4.8 → 0.6.4 (four High advisories).
- Next.js 14.2.35 → 15.5.27 (see the Stage 12 Tranche 1 report for audit counts); image optimisation is
  disabled — the app serves no images through it.
- `requirements.vllm.txt` pins the vLLM version that actually runs (0.9.2).

### v3.3.0 RC · part 2 — Stage 11: Phase 2 acceptance fixes and documentation tooling

*Original title: "Unreleased — Stage 11: Phase 2 acceptance fixes and documentation tooling".*

#### Added
- **Story Bible stale warning** (Phase 2 roadmap §19 P2-06, never built until now). The bible records which
  version of the indexed chapters it was generated from (`services/source_fingerprint.py`, shared with the
  saved Manuscript Report). `GET /story-bible` returns `is_stale`, and the World → Story Bible panel says
  "Your chapters have changed since this Story Bible was generated."
- **`make docs` / `make docs-check`:** Word copies are regenerated from their Markdown sources with
  pandoc 3.7.0.2 and checked for drift (`scripts/docs/sync_docs.py`, the `docs-sync` regression suite).
  `scripts/docs/check_doc_paths.py` fails when an active document names a file that does not exist.

#### Fixed
- **Story Intelligence (P01–P29) never worked, and now does.** Every pass called `_complete(prompt, …)`
  without the required `user` argument. The `TypeError` was swallowed by the orchestrator, and the
  per-chapter, character and relationship passes were still reported "completed". All 20 calls now send
  instructions as `system` and the author's material as `user`, so the prompt-injection fence also covers
  them. Verified live: a full analysis completed all 29 passes in about 160 s, with every read endpoint
  returning story-grounded content.
- **Story Intelligence reports failures honestly.** Unusable model output fails the pass instead of storing
  an empty "completed" analysis. P08–P12, P23 and P24 fail when nothing succeeded. Every failure is logged
  with its exception type (with a traceback for programming errors) and recorded in the Stage 10 error
  tracker (`/api/ops/errors`).
- **Voice-triggered analysis did nothing.** The voice action sends `passes: []`, which ran zero passes and
  reported "complete". An empty list now means all passes, matching the job record.
- **New guard:** `backend/tests/test_model_call_contract.py` binds every call to a `services.ai_service`
  function across the backend against its real signature. It would have caught this defect and the
  Stage 3 `query=` defect.

#### Changed
- **Vector similarity in the voice check, narrative-thread clustering and style drift now runs in
  pgvector** (`services/vector_math.py`; Phase 2 rule R12). Results equal the previous numpy values to 1e-5.
- **The voice check stays fast on long manuscripts.** It analyses at most 80 dialogue passages, sampled
  evenly across the manuscript, embeds them in one batch and describes flagged pairs concurrently. It
  says how many passages it analysed. On 200 chapters, 400 passages now take 24 s; 110 passages took
  91.9 s before, close to the ~100 s proxy limit (Phase 2 rule R7).
- **Inter is self-hosted** (`@fontsource/inter` 5.3.0, SIL OFL). The browser no longer contacts Google
  Fonts; every request goes to this server only.

#### Database
- `0025`: `story_bibles.source_fingerprint` (nullable; a bible generated earlier reads as "staleness unknown").
- `0026`: records in Alembic four columns that only `create_all()` or the startup guard had ever created.
  It is a no-op where they exist, and its downgrade keeps them (author data).

#### Configuration
- `PROMPT_INJECTION_GUARD` (default `true`). See v3.2.0.

---

### v3.3.0 RC · part 1b — Stages 3–6 and 8–10 (recorded retroactively, 2026-10-05)

These stages were approved and committed (2026-07-26 to 2026-09-30) without CHANGELOG entries. This record was
written from the checklist's ticked items and their evidence. Items that are built but still await a review are
marked *(verification open)*. Full evidence: `docs/NarratIQ_Master_Implementation_Checklist.md`, Stages 3–10.

#### Stage 3 — Phase 2 production defects (gate closed 2026-07-26)
- **Fixed:** chapter continuation and outline failed with a `TypeError` (retrieval call signature, `routers/writing_tools.py`).
- **Fixed:** the Story Bible said "completed" on partial content. It now reports `completed`/`partial`/`failed` with
  the failed sections and per-section retry; every entry cites a source chapter, and gaps say "not established in the
  manuscript".
- **Fixed:** plot holes and continuity returned nothing or an error on imperfect model output; they now return partial
  results with an honest degraded notice (`complete_structured()`; every `_extract_json` caller registered and tested).
- **Fixed:** the voice agent reported success for actions that did not run; recognised commands now execute or explain
  why not, and a voice-recording HTTP 500 is gone.
- **Fixed:** the selection toolbar stayed open, covered Save and overlapped the AI sidebar; analytics could not scroll
  to its last section; the OCR panel was hidden for stories with no chapters; notes failed to load; names stayed in the
  "unrecognised names" queue after a character was added or merged.
- **Database:** `0016` `story_bibles.failed_sections`. **Setting:** `VOICE_EXECUTION_TIMEOUT_SECONDS` (180).

#### Stage 4 — Retrieval and data correctness (2026-09-21)
- **Plot Assistant scope (decision D-1):** chapter-scoped by default (spoiler-safe), with a "Full manuscript" option and
  a scope badge; character evidence is capped at the open chapter; "not found in the searched range" is kept apart from
  "not in your story". Retrieval depth raised (`top_k` 5/8/4 → 6/10/6); plot-critical passages rank above passing
  mentions.
- **Chapter summaries** record character-arc progress and relationship changes (existing stories need
  `POST …/chapters/sync-summaries`). **Database:** `0017`.
- **Character merge** keeping both records' data (`services/character_merge.py`). Duplicate *detection* came in
  Stage 12 (part 3).
- **Search:** near-duplicate passages removed from semantic results; repeated searches return identical results.
- **Story Bible:** carried possessions are no longer described as physical traits; a prompt example no longer becomes
  an invented character.
- 96-test retrieval regression suite (`tests/run_stage4_retrieval_suite.sh`).

#### Stage 5 — AI generation quality (implemented; gate open — blind author review and Gate 3b pending)
- **Sentence locking** (locked text kept byte for byte), **strength control** (Light default), **"no change needed"**
  responses, **character-name preservation** with one repair retry and warnings, per-story **translation glossary**.
- **Writing suggestions** rewritten as developmental notes (weakness first, observation/recommendation, priority,
  narrative risk); **Story Audit / Manuscript Report** deepened (uncited continuity findings suppressed; arcs, threads,
  stakes, plot importance, themes) — 5.14's timeline-reasoning, narrative-reasoning and relationship-arc items
  *(verification open, MV-5.14-D)*.
- **Writing analytics:** every metric explained, readability bands, genre benchmarks for 8 genres; syllable and
  curly-quote counting fixed.
- **Live-review fixes D1–D4:** Narrative Threads scan status and result shown; the Manuscript Report is saved and shows a
  stale notice; plot-hole parse failures mitigated with guided JSON; "Thriller" style now changes the text.
- **Prompt version registry** (`services/prompt_registry.py`, version logged on every generation; rollback is a config
  change). **Settings:** `PROMPT_VERSION`, `PROMPT_VERSION_FALLBACK`. **Database:** `0018`
  `story_preservation_settings`; `0023` `narrative_thread_scans`, `manuscript_reports`.
- **Behaviour change:** rewrites default to Light and may return the text unchanged.

#### Stage 6 — Test automation (closed under a revised scope; CI deferred, 6.1)
- Seeded fixture manuscript and deterministic test user; the author feature checklist automated (40/40 rows); Phase 2
  issues mapped 14/14 to regression tests; a fail-closed test-database guard (`backend/tests/db_safety_guard.py`);
  `python-jose` 3.3.0 → 3.4.0. Playwright journeys run on demand, not in CI.

#### Stage 8 — Studio workspace (implemented; gate open — author reviews and screen-reader pass pending)
- Seven workspaces (Write, Plan, Characters, World, Analyze, Assistant, Publish), each tool in exactly one home
  (`lib/registries/toolHomes.ts`); Notes only in World, Narrative Threads only in Analyze, the Idea Shelf under World →
  Notes (closes Phase 2 Issue 10); resizable panels saved per user and browser; Ctrl+\\ widens the AI sidebar; a
  "Versions" group for the Phase 3 tools; 1920–768 px with no horizontal scroll.
- Writing-first layout with Reading/Focus/Zen/Typewriter views, grouped tools (34 % fewer visible controls), Draft and
  Edit modes, accessibility baseline (axe: zero serious findings; contrast ≥ 4.5:1) *(verification open: author
  reviews 8.3–8.5, screen reader 8.9, multi-hour session 8.11)*.

#### Stage 9 — Regression, security and UAT (automated work done; UAT open)
- **Security fixes:** seven routes (I1–I7) through which one author could reach another author's data, including chapter
  version text (Critical); upload size limits enforced on the real body, including chunked uploads
  (`middleware/body_limit.py`); the author-style `author` field is length-bounded; CORS trusts only this pod's own
  proxy origins.
- Full regression, Phase 2 scenarios 14/14, performance baselines (`docs/testing/performance-baselines.md`).

#### Stage 10 — Production readiness (2026-09-30)
- **Sessions:** HttpOnly cookie sessions with CSRF protection, same-origin `/api` through Next.js
  (`BACKEND_INTERNAL_URL`), server-side revocation (sign-out ends that session; a password change ends all others),
  one-time voice WebSocket tickets. **Breaking:** every user signs in once more; `?token=` on the voice WebSocket is
  refused; login returns the session as a cookie, not in the body (Bearer still works for tooling).
- **Account page:** change password; delete account (immediate, irreversible hard delete); `/data-policy` page.
- **Backups:** hourly on-pod sets with integrity manifests and uploads, 24 recent + 7 daily retention, daily restore
  verification, a backup before every migration, the empty-database startup guard. Off-pod copy deferred (S10-B).
- **Monitoring:** built-in error tracking (`error_events`), `/api/ops/{status,metrics,errors}` behind `OPS_TOKEN`,
  JSON logs with request ids, a watchdog writing `/workspace/logs/alerts.jsonl`; `/api/health` probes vLLM live and
  answers 503 when degraded. Person-delivered alerts deferred (S10-D).
- **Operations:** exactly one backend worker enforced (`startup/worker_guard.py`); `--no-proxy-headers` with
  `CF-Connecting-IP` from trusted proxies for rate limiting; rollback runbook, `.next.prev` and
  `scripts/rollback_frontend.sh`; pinned model revisions; incident response; capacity planning; Dockerfiles and
  compose *(never built — MV-10.3)*.
- **Database:** `0024` `users.token_version`, `revoked_sessions`, `error_events`. **Settings:** session/CSRF cookie
  names, `SESSION_COOKIE_SECURE`, `WS_TICKET_TTL_SECONDS`, `OPS_TOKEN`, vLLM probe TTL/timeout, error-event retention,
  `RATE_LIMIT_CLIENT_ERRORS`, `ALLOW_MULTI_WORKER`, `TRUSTED_PROXY_CIDRS`; scripts: `NARRATIQ_OFFPOD_COMMAND`,
  `NARRATIQ_ALERT_COMMAND`, `NARRATIQ_BACKUP_KEEP_RECENT`, `NARRATIQ_BACKUP_KEEP_DAILY_DAYS`,
  `NARRATIQ_BACKUP_VERIFY_EVERY_HOURS`, `NARRATIQ_ACKNOWLEDGE_EMPTY_RESTART`. `NARRATIQ_PERIODIC_BACKUP_RETENTION_COUNT`
  was replaced.

---

### v3.3.0 RC · part 1a — Phase 3: Author-Centric AI Workflow (Stage 7)

*Original title: "Unreleased — Phase 3: Author-Centric AI Workflow (Stage 7)".*

Design reference: `docs/phases/phase-3-planned/phase-3-author-centric-ai-workflow.md`.
Deviations from that spec (all approved in the Stage 7 plan) are listed at the end.

#### Security
- **Cross-user data leak closed (C7-6).** Every `/api/ai/*` endpoint that takes a
  `story_id` (refine, tone, emotion, age-adapt, style, author-style, translate,
  suggestions and their `/stream` variants, compare-summary, merge-versions) now
  verifies ownership. Before, any signed-in user could pass another author's
  `story_id` and have that author's genre profile, character names or manuscript
  passages placed into their own prompt. A foreign and a non-existent id now return
  the same 404.
- New `services/ownership.py`: one rule for every user-owned id (story, chapter,
  pin, note card). Foreign and non-existent ids are indistinguishable — same 404
  body for direct lookups, one generic count-only warning for batch ids.
- Note-card update/delete now return 404 (was 403) for another author's card.

#### Added
- **Pins (P3-01)** — `routers/ai_workspace.py` (`/api/stories/{id}/ai/pins`…):
  create/list/get/patch/delete, applied, promote. Plan caps (D1) enforced under a
  per-user advisory lock; 409 with the oldest pin at the cap, never silent
  eviction; 413 when too large; identical content is deduplicated. Expiry is
  written at insert (free: 7 days, D3) and an hourly sweep in the existing cleanup
  loop deletes expired pins (`[pin_cleanup] cleanup_rows=…` is logged every run).
  Pin rows are excluded from logical backups (D9). Content is read and written only
  through `services/pin_store.py`.
- **Pins as context (P3-03), generate from a version (P3-06), avoid-set (P3-07),
  consistency (P3-08), voice (P3-10)** — optional `controls` on tone / emotion /
  age-adapt / style. All context is assembled in `services/generation_context.py`
  under one token budget (2,600); anything dropped is reported, never silent.
- **Consistency (P3-08)** — `services/consistency.py`: grounded block from
  characters, character intelligence, story facts, world rules, timeline and earlier
  chapter summaries (never later chapters); Tier-1 knowledge check; Tier-2 strict
  check for pro/studio plans only (D6).
- **Similarity (P3-11)** — `services/similarity.py` + `POST …/ai/similarity`:
  lexical first, BGE-M3/pgvector only for ambiguous cases; informative only.
- **Compare & merge (P3-04)** — `POST /api/ai/compare-summary`,
  `POST /api/ai/merge-versions` (fidelity guard: ≤12 % word change, every chosen
  block ≥0.9 similar, one retry, else the unsmoothed merge). Diff runs in the
  browser (`lib/diff.ts`).
- **Idea Shelf (P3-09)** — note cards gain `target_chapter_id`, `tags`, `status`,
  `source_pin_id` and eight idea types; list filters; "Ideas" tab inside Notes
  (D10); "N ideas waiting" markers in the Write binder with drag and
  Insert-at-cursor.
- **Preferences** — `GET/PATCH /api/stories/{id}/ai/preferences` (project
  preservation rules, voice level, strict mode, duplicate auto-retry).
- `GET /api/ai/limits` — resolved plan limits and usage (display only; the server
  enforces everything).
- Frontend: Versions tab, compare/merge dialog, "What the AI must keep" panel,
  shared warnings banner with one-click name restore, Pin / Idea Shelf / similarity
  badge on results, invert-locks, Insert-at-cursor when the source text changed.
  Session history is in memory only (never persisted). `NEXT_PUBLIC_P3_ENABLED=false`
  (at build time) switches the Phase 3 UI off.

#### Changed
- Stage 5 lock/preservation engine extended rather than duplicated (C7-5):
  locked ranges are validated (bounds, overlap, all-locked → 422); a lock-contract
  failure now returns `failed: true` instead of presenting the original text as a
  rewrite; new conservative checks for tense, point of view, dialogue meaning and
  timeline additions. Heuristic checks default to **warn only** — measured 0 false
  positives on 81 real rewrites (`tests/fixtures/preservation_checks_measurement.json`).
- `_extract_json` register: `smooth_merge` added as "handled" (validation-driven,
  bounded retry, deterministic fallback); the other new structured calls use
  `complete_structured()`.

#### Database (migrations 0019–0022, renumbered from the spec's 0016–0019 — C7-1)
- `0019` `ai_generation_pins` (+5 indexes, autovacuum tuning)
- `0020` `story_preservation_settings` +`preserve_rules`, `style_prefs`, `pin_prefs`
  (extends the Stage 5 table instead of a second preference table — C7-2)
- `0021` `note_cards` +4 Idea Shelf columns, +2 indexes
- `0022` `users.plan` (NULL = free)
All guarded, reversible, and round-trip tested on a populated database
(`backend/tests/run_migration_roundtrip.sh`); rollback keeps every idea card.

#### Configuration
- 30 new optional settings in `config.py` and `.env.example` (all defaulted; the spec's 29 plus `dialogue_similarity_min`).

#### Deviations from the Phase 3 spec
- No `/api/ai/regenerate-segments` endpoint and no JSON segment contract (C7-5):
  partial regeneration stays on the Stage 5 `locked_ranges` engine, which already
  guarantees locked text byte-for-byte.
- Controls are accepted by tone/emotion/age-adapt/style only; refine, translate and
  author-style keep their existing behaviour.
- Tense / POV / dialogue / timeline checks warn by default; they add prompt rules
  and a repair retry only when an author sets them to "Keep".

---

## v3.2.0 — October 2026 — Author-Inspired Style Rewrite & Copyright/Plagiarism Risk Detection

Released 2026-10-01 under task 11.7. The features were built in June 2026 (commit `9827587`) and kept
"Unreleased" until their safety claims were verified. Design and implementation reference:
`docs/specifications/author-style-and-copyright-risk-features.md`.

> ⚠️ **The copyright-risk disclaimer wording is pending legal review.** It has not been reviewed by a
> qualified legal professional (flagged 2026-10-01). The application's reported version
> (`backend/main.py`) is still `3.0.0`; aligning it is a Stage 12 release task.

### Fixed in this release (task 11.7)
- **The copyright-risk headline could under-report.** `analyze_copyright_risk` trusted the model's
  `overall_risk`, so a "low" headline could sit above a "high" finding. The headline is now the
  higher of the model's level and the most severe finding, computed in code.
- **The copyright-risk `note` was always empty.** `coerce_copyright_findings` dropped the model's
  one-sentence note, so the panel's summary line never appeared. It is now kept.
- **Prompt injection through manuscript text (Stage 9 finding P1) is mitigated** for every AI feature, not
  only these two. The author's material is fenced as data, the concrete task is restated after it, and
  rewrites that drop the selected passage are refused in code (`services/prompt_safety.py`). Measured
  before → after: author-style obeyed an injected instruction 15/15 → 0/15, Plot Assistant 3/3 → 0/3, all
  11 probed features 0. Legitimate rewrites are unaffected: 0/84 refused, names kept 1.00. A residual
  risk remains and is stated in `docs/testing/stage-09-security-findings.md`.
- **The safety claims are tested.** A 23-case redirect-bypass sweep covers living authors, case,
  spelling and homoglyph variants, embedded instructions, and template and script strings. The live
  prompt-injection probe now covers both features (`--only author-style copyright-risk`).

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

### Known issues at release
- **Residual prompt-injection risk.** It is much reduced, and caught in code for rewrites, but no prompt
  design can make a language model immune. See the Stage 11 section of
  `docs/testing/stage-09-security-findings.md`.
- **Disclaimer wording not legally reviewed** (see above).

### Tests
- Backend: `tests/test_author_style_and_copyright.py`. At release it has the original unit tests,
  the headline and note tests and the redirect-bypass sweep; Qwen is stubbed via `_complete_ex`.
- Backend: `tests/test_security_stage9.py`, the Stage 9 adversarial `author` cases.
- Frontend: extended `tests/transforms.spec.ts` for author-style routing + catalog.

No DB migrations required. No new required env vars.

---

## v3.1.0 — June 2026 — Phase 2: Manuscript Intelligence (recorded retroactively)

Phase 2 shipped in June 2026 (migrations `0008`–`0011` added 2026-06-11 and 2026-06-12) without a
CHANGELOG entry. This section was written on 2026-10-01 to satisfy the Phase 2 roadmap's §20.4
completion criterion 8 (task 11.6). Formal acceptance, evidence and deviations:
`docs/phases/phase-2-completed/phase-2-acceptance-record.md`.

### Added
- **P2-01 Emotional arc:** `GET /api/stories/{id}/emotional-arc`.
- **P2-02 Chapter continuation:** `POST …/chapters/{cid}/continue`, three options.
- **P2-03 Dialogue voice consistency:** `POST …/characters/{char_id}/voice-check`.
- **P2-04 Outline / beat sheet:** `POST …/chapters/{cid}/outline`.
- **P2-05 Continuity validator:** `POST …/continuity-check`.
- **P2-06 Story Bible:** five sections, a background job, DOCX export. (The roadmap's stale warning was not built in Phase 2; it was added in Stage 11, see Unreleased.)
- **P2-07 Narrative thread tracker:** a background scan, with list and update.
- **P2-08 Style drift:** early/late BGE-M3 centroids plus a Qwen description.
- **P2-09 Pacing goals:** `POST/GET …/pacing-goals`.
- **P2-10 Duplicate scenes:** pgvector similarity over chunks.
- **P2-11 Audio notes:** faster-whisper transcription, Qwen cleanup, then confirm into a note.

### Database
- `0008` `story_bibles` · `0009` `narrative_threads` · `0010` `pacing_goals` · `0011` `audio_uploads`.
  The roadmap's "0001–0006" numbering was never used.

### Models
- faster-whisper large-v3-turbo, CPU int8, lazy-loaded. It is downloaded from the
  `deepdml/faster-whisper-large-v3-turbo-ct2` mirror because the roadmap's repository now returns 401.

### Deviations (accepted 2026-10-01, see the acceptance record)
- **P2-05 runs synchronously.** It returns no job id, against rule R10.
- **numpy cosine on request-time vectors in three Phase 2 features** (voice check, thread clustering
  and style drift), against rule R12. This was fixed in Stage 11: all three now use pgvector.
- **Audio routes live under `/api/stories/{id}/audio…`**, not the roadmap's `/api/audio/…`.

---

## v3.0.0 — June 2026

**Production architecture completion. All 14 roadmap tasks implemented. Zero remaining placeholders.**

The authoritative architecture reference for this release is:
`docs/phases/phase-1-completed/phase-1-production-implementation-report.docx`

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

**`docs/phases/phase-1-completed/phase-1-production-implementation-report.docx`**

Covers: full architecture, all 19 database tables, all 17 completed features, API summary (15 routers), security architecture, background job architecture, production readiness assessment, remaining limitations, and future roadmap.
