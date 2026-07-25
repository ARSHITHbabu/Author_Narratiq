# Story Bible — Section Generation Failure Path Audit

| | |
|---|---|
| **Document** | Story Bible section-generation failure path audit |
| **Audit date** | 2026-07-25 |
| **Repository revision** | `cb0144a537a3bc19b104f220996925cfcbe5c491` (short `cb0144a`, branch `main`, working tree clean) |
| **Schema revision** | Alembic `0015` (`0015_story_bible_status`) |
| **Produced for** | Master Implementation Checklist — Stage 3, Task 3.2, subtask 1 (*"Enumerate every section-generation failure path"*) |
| **Source defect** | Phase 2 Issue 8 (partial); `README.md` known issue 2 |
| **Status** | Canonical reference for the remaining Stage 3.2 subtasks |
| **Scope** | Analysis only — this audit changed no code, schema, API, frontend or status logic |

> **Checklist naming note.** Task 3.2 refers to `_generate_bible_background`. No such function exists at this revision; the background pipeline is **`_generate_bible_pipeline`** (`backend/routers/story_bible.py:117`). The line references cited by the checklist (`:136–147`) are still exactly correct. The checklist text is stale by a rename and is deliberately **not** corrected here — it will be corrected when the checklist itself is next updated.

---

## 1. Scope and method

**Question this audit answers:** by what paths can a Story Bible section fail to contain genuinely generated content, and what does the system currently tell the author in each case?

**Method.** Every path below was read from the working tree at `cb0144a` and is cited as `file:line`. Paths were derived from the *exception surface of the call chain* (`_generate_bible_pipeline` → `generate_story_bible_section` → `_complete` → `_complete_ex` → `AsyncOpenAI`) and from the *layers the data crosses*, not from the `except` clauses that happen to exist today. That distinction matters: the two failure modes that no current code notices (SB-F12, SB-F13) raise no exception at all, so an audit driven by existing `except` blocks would have missed both.

**Files read**

| File | Region |
|---|---|
| `backend/routers/story_bible.py` | whole file (342 lines) |
| `backend/services/ai_service.py` | `:36–45` client, `:99–205` completion primitives, `:3727–3768` `generate_story_bible_section` |
| `backend/exceptions.py` | whole file |
| `backend/startup/orphan_recovery.py` | whole file |
| `backend/models.py` | `:297–303` `CharacterProfile`, `:1063–1080` `StoryBible` |
| `backend/schemas.py` | `:1382–1397` |
| `backend/middleware/concurrency.py` | whole file |
| `backend/migrations/versions/0015_story_bible_status.py` | whole file |
| `frontend/components/story-bible/StoryBiblePanel.tsx` | whole file |
| `frontend/lib/useStoryBible.ts` | whole file |

**Claims verified by execution rather than by reading.** Four assertions in this audit would have been assumptions otherwise; each was checked against the installed runtime (Python 3.11.10, `openai` 1.90.0, SQLAlchemy 2.0.30):

| Claim | Check | Result |
|---|---|---|
| `APITimeoutError` reaches the `AIServiceUnavailableError` branch (SB-F07) | `issubclass(APITimeoutError, APIConnectionError)` | **True** |
| `CancelledError` escapes both `except Exception` handlers (SB-F26) | `issubclass(asyncio.CancelledError, Exception)` | **False** — it is a `BaseException` |
| A failed commit poisons the session so the error handler cannot write a status (SB-F23) | handler shape replayed against a scratch session with a forced commit failure | **`PendingRollbackError`; row left `running`** |
| `status` accepts a new `partial` value without a migration (§8.3) | `information_schema` + `pg_constraint` on the live database | **`character varying`, no `CHECK`** |

**Definitions used throughout**

- **Genuine content** — text produced by the model, for the requested section, from the manuscript context, complete as generated. Section 6 expands this.
- **Terminal status** — the value in `story_bibles.status` once the pipeline is no longer running.
- **Correct status** — what the status *should* be under the contract Task 3.2 establishes (Section 8.2).

---

## 2. Production baseline

Required as evidence before the fix. Measured **twice, independently**: directly against the live database, and by decoding the on-pod backups. Both agree.

### 2.1 Live database — 2026-07-25, read-only

PostgreSQL 16.14 is running and reachable at `localhost:5432/narratiq`, schema at Alembic `0015`. All queries below were `SELECT` only.

| Measure | Value |
|---|---|
| **Total `story_bibles` rows** | **0** |
| Rows by status | *(none)* |
| **`completed` bibles containing an AI-unavailable placeholder** | **0** |
| **`completed` bibles containing an error placeholder** | **0** |
| `completed` bibles with empty `content_json` | 0 |
| Rows stuck in `running` | 0 |
| **Percentage affected** | **0% of 0 records** |

⚠ **The live database is empty of manuscript data as well:** `stories = 0`, `chapters = 0`, `chapter_summaries = 0`, `chapter_chunks = 0`, `characters = 0`, `users = 0`. The schema exists at `0015`, but the 1 story / 4 chapters / 8 characters / 21 chunks recovered on 2026-07-24 are **no longer in the live database** — they survive only in `/workspace/backups`. This is a container-lifecycle consequence, not a Story Bible defect, and is reported outside this audit for a decision on restoring.

⚠ **Schema drift observed while checking constraints.** The live `story_bibles.status` column is `character varying`, **nullable, with no server default**. Migration `0015` creates it `nullable=False, server_default='completed'`. The live table therefore came from `Base.metadata.create_all()` (where `models.py:1076` sets a *Python-side* default only), not from the migration. Consequences: (a) the SB-F22 backfill concern does not apply to this database; (b) a row inserted outside the ORM can hold `status = NULL`, which no code handles; (c) any status work must not assume the migration's constraints are present in a `create_all`-provisioned environment.

### 2.2 Backup corroboration — 2026-07-24 10:38:24 UTC

Recovered read-only by parsing the pg_dump custom-format archive directly (TOC + per-table compressed data blocks). No backup file was modified; the dump's SHA-256 still matches `BACKUP-RECORD.txt` (`f1b07d30…c233ac5`).

| Measure | Value |
|---|---|
| Backup analysed | `narratiq-20260724T103824Z.dump` (PostgreSQL 16.14, archive format 1.15) |
| Cross-check backup | `narratiq-20260724T104320Z.dump` (10:43:20 UTC) — identical result |
| Schema revision in dump | `alembic_version = 0015` |
| **Total `story_bibles` rows** | **0** (data block is 5 bytes: the `\.` terminator alone) |
| **Placeholder-bearing `completed` bibles** | **0** — no rows exist |
| Manuscript data at that time | 1 story, 4 chapters, 21 chapter chunks, 8 characters, 67 character mentions, 1 user |

### 2.3 Interpretation — a meaningful zero, not a missing measurement

1. **No historical data repair is needed.** The later 3.2 subtasks require **no backfill migration and no clean-up script** for mis-marked `completed` rows: none has ever been persisted in any environment still measurable. This removes a data-migration risk from the fix.
2. **It does not mean the defect is theoretical.** Phase 2 Issue 8 was reported from manual QA and the defect is proven by code reading (and, for SB-F23, by execution — Section 5, L6). It means only that no *surviving* row demonstrates it.
3. **The fix cannot be validated against existing data.** With zero bibles and zero manuscripts live, every later verification step in Task 3.2 needs a **fixture manuscript created first**. Plan for that when the unit tests and the re-run of the QA scenario are scoped.
4. **Re-measure if data is restored.** These numbers are as of 2026-07-25. Restoring a backup before the fix ships invalidates them — re-run Section 9.1.

---

## 3. Summary — every enumerated path

`✗` = the author is told something untrue. `✓` = current behaviour is correct.

| ID | Layer | Trigger | Terminal status today | Correct status | |
|---|---|---|---|---|---|
| SB-F01 | L1 Context | DB error assembling context | `failed` | `failed` | ✓ |
| SB-F02 | L1 Context | NULL profile text field → `TypeError` | `failed` | `failed` | ✓ |
| SB-F03 | L1 Context | Context effectively empty despite the ≥1-summary gate | `completed` | `failed` | ✗ |
| SB-F04 | L1 Context | Per-summary 300-char truncation (grounding) | `completed` | — (Task 3.3) | — |
| SB-F05 | L2 Invocation | vLLM unreachable (`APIConnectionError`) | `completed` | `partial`/`failed` | ✗ |
| SB-F06 | L2 Invocation | vLLM 429/500/502/503/504 | `completed` | `partial`/`failed` | ✗ |
| SB-F07 | L2 Invocation | Request timeout (120 s × 2) | `completed` | `partial`/`failed` | ✗ |
| SB-F08 | L2 Invocation | Other 4xx — e.g. 400 context-length, 404 model | `completed` | `partial`/`failed` | ✗ |
| SB-F09 | L2 Invocation | Backend in degraded mode, all 5 sections fail | `completed` | `failed` | ✗ |
| SB-F10 | L3 Validation | Empty `choices` → `IndexError` | `completed` | `partial`/`failed` | ✗ |
| SB-F11 | L3 Validation | `message.content is None` → `AttributeError` | `completed` | `partial`/`failed` | ✗ |
| SB-F12 | L3 Validation | **Empty / whitespace-only response — no exception** | `completed` | `partial`/`failed` | ✗ |
| SB-F13 | L3 Validation | **Truncation (`finish_reason="length"`) — no signal** | `completed` | `partial`/`failed` | ✗ |
| SB-F14 | L3 Validation | Model refusal / meta-commentary as section body | `completed` | heuristic only | ✗ |
| SB-F15 | L3 Validation | Model emits its own `[...]` text → defeats a naive marker scan | `completed` | — (detector risk) | ⚠ |
| SB-F16 | L4 Assembly | Placeholder string stored as if it were section text | `completed` | n/a — root cause | ✗ |
| SB-F17 | L4 Assembly | **No per-section outcome is recorded anywhere** | `completed` | n/a — root cause | ✗ |
| SB-F18 | L4 Assembly | `json.dumps` failure | `failed` | `failed` | ✓ |
| SB-F19 | L5 Persistence | **Bible row gone at write time → silent no-op** | *(row absent)* | log + no-op | ⚠ |
| SB-F20 | L5 Persistence | Status written from loop completion, not from outcomes | `completed` | per Section 8.2 | ✗ |
| SB-F21 | L5 Persistence | Retry overwrites a bad generation in place, no history | `completed` | — (record only) | ⚠ |
| SB-F22 | L5 Persistence | Pre-0015 rows backfilled to `completed` | `completed` | — (0 rows affected) | ⚠ |
| SB-F23 | L6 Commit | **Commit failure — the failure handler itself fails → row stuck `running`** | `running` (forever) | `failed` | ✗ |
| SB-F24 | L6 Commit | Connection lost after COMMIT is applied | `completed` | `completed` | ✓ |
| SB-F25 | L7 Lifecycle | Task garbage-collected (`create_task` reference dropped) | `running` → restart | `failed` | ⚠ |
| SB-F26 | L7 Lifecycle | **`CancelledError` — `BaseException`, caught by neither handler** | `running` → restart | `failed` | ⚠ |
| SB-F27 | L7 Lifecycle | Process kill / OOM / container destroy | `running` → restart | `failed` | ⚠ |
| SB-F28 | L7 Lifecycle | Returned `job_id` is never persisted or queried | — | — (observability) | ⚠ |
| SB-F29 | L7 Lifecycle | Duplicate-guard race between check and write | `completed` | — (record only) | ⚠ |
| SB-F30 | L7 Lifecycle | `running` also means "queued on the semaphore" | `running` | — (UI honesty) | ⚠ |
| SB-F31 | L8 Recovery | Startup sweep `running → failed` | `failed` | `failed` | ✓ |
| SB-F32 | L8 Recovery | Sweep is unconditional across workers | `failed` | — (single worker today) | ⚠ |

**Counts:** 32 paths. **14 produce a false `completed`** (the reported defect). **4 are already correct.** **3 leave a row stuck in `running`** until a restart. **11 are recorded context, detector risks or observability gaps** that the 3.2 status work should not silently inherit.

---

## 4. The defect in one paragraph

`_generate_bible_pipeline` records failure in the **content** and never in the **state**. Each section's exception is converted to a human-readable string that is stored in the same field a real section would occupy (`:136–140`), the loop always completes, and control falls unconditionally to `:147` `bible.status = "completed"`. There is no variable anywhere in the function from which a partial outcome *could* be derived — this is SB-F17, and it is the specific gap the next subtask must close. Two further paths (SB-F12 empty response, SB-F13 truncation) produce no exception at all, so they would still slip through even if every `except` clause set a failure status.

---

## 5. Layer-by-layer enumeration

### L1 — Context construction
`_build_full_context()` — `story_bible.py:47–114`. Runs once, before any AI call, at `:128`.

**SB-F01 — Database error while assembling context.**
Trigger: connection loss, pool exhaustion, query error on any of the six queries (`:53–110`). Exception: `SQLAlchemyError`. Persisted: nothing — the failure precedes generation. Path: outer handler `:153–162`. Status today: `failed`. Correct: `failed`. **Already correct**, provided the session is still usable (contrast SB-F23).

**SB-F02 — NULL text field on a character profile.**
Trigger: `p.appearance[:150]` / `personality` / `goals` / `backstory` at `:87–90` when the column is NULL. `models.py:297–303` declares these `Column(Text, default="")` — a *Python-side* default, applied only on ORM insert, with no `nullable=False` and no server default, so a row written by raw SQL, a data import or a future migration can legitimately hold NULL. Exception: `TypeError: 'NoneType' object is not subscriptable`. Status today: `failed` — **the correct status, but the wrong blast radius**: one NULL field on one character fails the entire bible before a single section is attempted, and the author is told only "Something interrupted generation." Recorded; a defensive read is a candidate for the assembly subtask, not for this one.

**SB-F03 — Effectively empty context.**
Trigger: the POST gate at `:201–210` requires ≥1 `ChapterSummary` **row**, not ≥1 row with content. Summaries whose `raw_summary`, `key_events` and `characters_present` are NULL or blank pass the gate and produce header-only lines. No exception. Result: the model is asked to write a comprehensive bible from almost nothing and interpolates. Status today: `completed`. Correct: `failed` — a bible generated from no manuscript evidence is not genuine content. This is the boundary where Task 3.2 (status) meets Task 3.3 (grounding); the *status* half belongs to 3.2.

**SB-F04 — Per-summary 300-character truncation.**
`:71` `str(s.raw_summary or '')[:300]`. Documented context starvation, already assigned to **Task 3.3**. No status implication. Recorded here only so the next subtask does not treat it as in scope. See also the interaction warning in SB-F08.

### L2 — AI invocation
`generate_story_bible_section()` — `ai_service.py:3727–3768`, calling `_complete()` `:99–120` → `_complete_ex()` `:123–164`. Client: `AsyncOpenAI(timeout=120.0, max_retries=1)` at `:36–45`. Parameters: `temperature=0.2, max_tokens=1500`.

**SB-F05 — vLLM unreachable.** `APIConnectionError` → `AIServiceUnavailableError` (`:157–159`) → caught at `story_bible.py:136` → body becomes `"[AI temporarily unavailable — please regenerate]"` → **`completed`**. This is the reported defect, path 1.

**SB-F06 — vLLM returns 429/500/502/503/504.** `APIStatusError` → `AIServiceUnavailableError` (`:160–163`) → same handler, same placeholder, **`completed`**.

**SB-F07 — Request timeout.** The client's 120 s timeout with `max_retries=1` raises `APITimeoutError`, which subclasses `APIConnectionError` in the OpenAI SDK, so it lands on the same branch as SB-F05 → **`completed`**. Worth stating explicitly for the later UX work: five sections × two attempts × 120 s is a **~20-minute** worst-case wall clock, all of it while the panel shows "This usually takes 1–3 minutes."

**SB-F08 — Any other `APIStatusError`.** `:164` re-raises anything outside the 5xx/429 set, so it reaches the **generic** handler at `story_bible.py:139` and is stored as `f"[Error generating {section}: {exc}]"` → **`completed`**. The two realistic instances are **400 context-length exceeded** and **404 unknown model name** (a stale `VLLM_MODEL_NAME`). ⚠ **Interaction warning for Task 3.3:** raising the context budget makes a 400 materially more likely, and today a 400 is silently written into the bible as if it were a section. 3.3 should not land before this path returns an honest status.

**SB-F09 — Backend running in degraded mode.** `main.py` allows startup with `llm_ready = False`. The POST handler does not consult it, so generation starts, all five sections take the SB-F05 branch, and the row is marked **`completed`** holding five identical placeholders. This is the worst instance of the class: a bible with zero real content, reported as ready, with a success toast (Section 7).

### L3 — AI output validation
There is no validation layer for this feature. `_complete_ex` returns `resp.choices[0].message.content.strip()` (`:156`) and `generate_story_bible_section` returns it unexamined.

**SB-F10 — Empty `choices` array.** `IndexError` → generic handler → error string persisted → **`completed`**.

**SB-F11 — `message.content is None`.** `.strip()` raises `AttributeError` → generic handler → error string persisted → **`completed`**. Reachable when the model emits only a tool call or an empty assistant message.

**SB-F12 — Empty or whitespace-only response. No exception is raised anywhere.**
`content[section] = ""` is stored as a legitimate value. Consequences: status **`completed`**; the panel renders *"Not yet generated."* for that section (`StoryBiblePanel.tsx:23`) directly beneath a bible presented as complete; the DOCX export **silently omits the section entirely** (`story_bible.py:315–317` `if not text: continue`) so the exported document has no indication anything is missing. **No current code path can detect this**, and no exception-driven fix will catch it.

**SB-F13 — Truncated generation. No exception, and the signal is discarded.**
`generate_story_bible_section` calls `_complete()`, which drops `finish_reason` (`:116–120`). A section that hit `max_tokens=1500` returns a **mid-sentence fragment** that is persisted as a genuine section under status **`completed`**. 1500 tokens is roughly 1,000–1,100 words for a *whole cast bible* or a *whole timeline* — this is not an edge case on a real manuscript, it is the expected outcome at moderate scale. The machinery to detect it already exists and was built under Task 3.1: `_complete_ex()` exposes `finish_reason`, and `AIResponseTruncatedError` (`exceptions.py`) is the established contract. **The Story Bible does not use either.** Adopting `_complete_ex` here is the single highest-value change available to the 3.2 status work.

**SB-F14 — Refusal or meta-commentary as the section body.**
"I don't have enough information to write this section." is well-formed prose of plausible length; it is structurally indistinguishable from a real section. Detectable only by content heuristics. **Recommended out of scope for 3.2** (a heuristic that mislabels a real section as failed is worse than the current state) and recorded as an input to Task 3.3, which introduces an explicit "not established in the manuscript" convention.

**SB-F15 — ⚠ Detector risk: a naive `[` scan is unsafe.**
The 3.2 verification checkbox proposes *"no `story_bibles` row with `status='completed'` contains a `[` placeholder marker."* Both current markers begin `[`, but so do ordinary generated lines — `[Chapter 3]`, `[Act I]`, bracketed asides, and any Markdown link. A `content_json LIKE '%[%'` scan will produce false positives on genuine bibles and, if the placeholder wording ever changes, false negatives on broken ones. **Recommendation for the verification subtask:** assert against the *status and `failed_sections` fields*, and if a content scan is retained, match the exact placeholder strings (`[AI temporarily unavailable` and `[Error generating `) rather than a bare `[`. Better still: once SB-F16 is fixed, no placeholder is ever persisted, and the correct assertion becomes "no placeholder string exists in any row, at any status."

**Structured-output subclasses — applicability.** Malformed structured output, empty JSON objects and parser-failure-returning-empty were called out as required coverage. They are enumerated here for completeness with their real applicability at this revision:

| Subclass | Applies to Story Bible sections? | Notes |
|---|---|---|
| Malformed JSON from the model | **No** | Sections are free prose. `generate_story_bible_section` requests no JSON and never calls `_extract_json`. |
| Parser failure returning empty content | **No** | No parser is invoked on a section. The equivalent symptom — empty content — is SB-F12. |
| Empty JSON object `{}` | **At the row level only** | `content_json` defaults to `"{}"` at row creation (`:224`, `models.py:1070`). Reachable as a persisted terminal state only via SB-F22 (legacy rows). Under the current pipeline the dict always receives five keys before the write. |
| Missing expected field | **Partly** | The dict is keyed by `_BIBLE_SECTIONS`, so a key is never *absent* — but a key present with a placeholder, empty or truncated value is the same defect wearing a different mask (SB-F12, SB-F13, SB-F16). The frontend reads with `content[activeSection] ?? ''` (`StoryBiblePanel.tsx:177`), which cannot distinguish absent from empty. |
| Null response | **Yes** | SB-F11. |

If a future change makes bible sections structured (a plausible direction for Task 3.3 provenance), the first three rows become live and this table must be revisited.

### L4 — Section assembly
`story_bible.py:130–142`.

**SB-F16 — Failure is written into the content field.** `:138` and `:140` assign human-readable failure text to `content[section]`, the same field a genuine section occupies. Once that assignment happens the information that this section failed exists **nowhere else** — not in a variable, not in a counter, not in a log field the persistence layer can read. This is the root cause of the whole class.

**SB-F17 — No per-section outcome is tracked.** After the loop, `content` holds five keys whether five sections succeeded or zero did. `:144–152` therefore has no data from which `partial` could be derived, which is precisely why `:147` hard-codes `completed`. **This is the gap the next subtask exists to close**; the required shape is specified in Section 8.

**SB-F18 — `json.dumps` failure** (`:142`). Practically unreachable — every value is a `str`. Reaches the outer handler → `failed`. Recorded for completeness; no action.

### L5 — Persistence
`story_bible.py:144–152`. *(Addition requested: AI generation succeeds, persistence does not.)*

**SB-F19 — The bible row no longer exists at write time.**
`:144` re-queries the row by `bible_id` in a **new** query after generation, and `:145` guards with `if bible:`. If the story was deleted mid-generation (`story_bibles.story_id` is `ON DELETE CASCADE`, `models.py:1067`), or the row was removed by any other means, the guard is falsy and the function **does nothing at all** — no commit, no log line, no error, no metric. Several minutes of GPU work are discarded in silence and the `except` block is never entered. Observable behaviour today: nothing whatsoever; the author sees the panel return to its idle state because the GET now 404s.
Correct behaviour: the row is genuinely gone, so no status applies — but the event must be **logged at warning level**. A silent branch is how this class of defect stays invisible.

**SB-F20 — Terminal status is derived from loop completion, not from outcomes.**
`:147` sets `completed` unconditionally, guarded only by "the row still exists". Every ✗ row in Section 3 passes through this line. Correct behaviour is specified in Section 8.2.

**SB-F21 — A retry overwrites a bad generation in place.**
`bump_version` (`:214`) is true only when the previous status was `completed`; after a failure, `:148–149` leaves the version unchanged and `:146` overwrites `content_json`. So a placeholder-filled v1 is replaced by v2's content **under the same version number**, and no record of the bad generation survives. Not a status defect and not in scope for 3.2 — recorded because a reviewer looking for evidence of past failures will find none, which is a second reason the Section 2 baseline reads zero.

**SB-F22 — Pre-0015 rows read as `completed` by construction.**
`0015_story_bible_status.py` adds the column with `server_default="completed"` and no conditional backfill, so every row that predates the migration — including any holding `content_json = '{}'` — reports `completed`. Deliberate and documented at `models.py:1072–1076`. **Live impact today: zero** (Section 2.1: no rows exist), and in fact the live column carries no server default at all because the table was provisioned by `create_all()` rather than the migration (Section 2.1, schema-drift note). Two consequences: this path is unreachable in the current environment, but a `status = NULL` row is reachable via non-ORM insert and is handled nowhere — the status contract should treat NULL as `failed`, not as `completed`. Re-check both if a database is restored from an older source before the fix ships.

### L6 — Transaction commit
*(Addition requested: commit and save-operation failures.)*

**SB-F23 — ⚠ Commit failure leaves the row stuck in `running` forever. New finding.**
Trigger: `db.commit()` at `:151` fails — database restart, disk full, connection reset, lock timeout, constraint violation.
What happens next, in order:
1. The exception propagates to the outer handler at `:153`.
2. The handler logs, then **immediately issues `db.query(StoryBible)…` at `:156` on a session whose transaction has already failed**. SQLAlchemy requires an explicit rollback before that session can be reused, so this raises `PendingRollbackError`.
3. The inner `except` at `:161` catches it and calls `db.rollback()` — *after* the status write it was supposed to protect, which therefore never happens.
4. `finally` (`:163–165`) discards the in-memory guard and closes the session.

**Confirmed by execution, not only by reading.** The exact handler shape at `:153–162` was replayed against a scratch SQLAlchemy session with a forced commit failure:

```
1. commit failed as expected: IntegrityError
2. HANDLER ITSELF FAILED:     PendingRollbackError
3. terminal status in DB:     running
```

**Terminal state: `status = 'running'`, permanently.** The panel renders "Story Bible generation is in progress" and `useStoryBible.ts:29–30` polls every 4 seconds indefinitely. The **only** thing that ever clears it is the startup sweep (SB-F31) — so recovery time equals time-to-next-restart, which is unbounded. The generation is also un-retryable in the meantime: the duplicate guard at `:194` sees `running` and returns `already_generating` to every retry attempt.
Correct behaviour: `failed`. Fix direction for the status subtask: **`db.rollback()` as the first statement of the outer handler**, before re-querying. Note this is a defect in the *error handler itself* — it is invisible to any test that only forces section-level failures, and must be tested by forcing a commit failure specifically.

**SB-F24 — Connection lost after COMMIT is applied but before acknowledgement.** The database holds `completed`; the pipeline believes it failed and attempts a `failed` write that itself fails. Terminal state depends on the race; both outcomes are recoverable by regenerating. Low likelihood, no action, recorded for completeness.

### L7 — Background execution lifecycle
`story_bible.py:232–241` (dispatch), `:117–165` (task body). *(Addition requested: cancellation, shutdown, termination, restarts, timeouts.)*

**SB-F25 — The task may be garbage-collected mid-execution.**
`asyncio.create_task(...)` at `:233` discards the returned `Task`. The asyncio documentation is explicit that the event loop keeps only a weak reference, so a task with no strong reference can be collected while it is still running. Result: generation stops silently, the row stays `running`. Recoverable only at restart. Low observed frequency, real class.

**SB-F26 — `CancelledError` is caught by neither handler.**
Since Python 3.8 `asyncio.CancelledError` inherits from `BaseException`, so **neither** `except Exception` at `:139` **nor** the outer one at `:153` catches it. On cancellation the `finally` block still runs (`_generating.discard`, `db.close()`), but no status is written. Terminal state: `running`, cleared only by the startup sweep. Reachable on uvicorn graceful shutdown, deployment, or any explicit task cancellation.

**SB-F27 — Process kill, OOM, container destroy.**
Identical terminal state to SB-F26 — `running`, cleared at next startup. **Not hypothetical on this deployment: it has happened twice**, once on 2026-07-24 (container destroyed and rebuilt, PostgreSQL lost, database restored from backup) and again between that recovery and this audit (Section 2).

**SB-F28 — The `job_id` is decorative.**
`:232` mints a UUID and `:237–241` returns it; it is never persisted, never logged against the row, and no endpoint accepts it. Callers must poll `GET /story-bible` and infer state from `status`. Observability gap, not a status defect — but it means a failed generation cannot be correlated to its log lines after the fact.

**SB-F29 — Check-then-write race in the duplicate guard.**
`:194` reads status and `:216`/`:227` writes it, with no lock and no atomic conditional update between them. Two concurrent POSTs can both observe a non-running state and both dispatch a pipeline against the same `bible_id`; the second writer wins and the first's work is silently overwritten. `_generating` (`:33`) narrows the window but is a **per-process** set — it provides no protection across uvicorn workers. Current deployment runs `--workers 1` (`CLAUDE.md`), so this is latent. Recorded, not in scope.

**SB-F30 — `running` conflates "generating" with "queued".**
The semaphore is acquired at `:131`, *after* the row is already marked `running` by the POST handler. With `BG_AI_CONCURRENCY=3`, a fourth bible sits queued while telling the author it is being written. UI honesty note for the panel subtask.

### L8 — Recovery and startup
`startup/orphan_recovery.py:78–87`, called first in `lifespan()`.

**SB-F31 — The `running → failed` sweep is correct and already implemented. Do not re-solve.**
Every `running`-stuck row (SB-F23, SB-F25, SB-F26, SB-F27) is marked `failed` at next startup, which surfaces the panel's retry affordance (`StoryBiblePanel.tsx:98–113`). ⚠ Caveat the status work must account for: this is the **only** mechanism that clears a stuck `running`, and it runs **only at startup**. There is no age-based sweep and no timeout while the process lives, so mean time to recovery equals time to next restart — unbounded on a long-running pod. An in-process watchdog is a legitimate improvement but is **new scope**, not part of 3.2.

**SB-F32 — The sweep is unconditional.** It marks *every* `running` row failed, including a generation genuinely in flight in another worker. Harmless at `--workers 1`; would need a heartbeat or ownership column at higher worker counts. Recorded, not in scope.

---

## 6. What counts as non-genuine content

Broader than "empty string". Any of the following in a section body means the section did **not** produce genuine content, and a bible containing one must never read `completed`:

| # | Class | Detectable how | Paths |
|---|---|---|---|
| 1 | Placeholder written by our own error handler | Exact string match — but see SB-F15 | SB-F05…SB-F11 |
| 2 | Empty string | `len(text.strip()) == 0` | SB-F12 |
| 3 | Whitespace-only | same as 2 after `strip()` | SB-F12 |
| 4 | `None` returned from the model | `content is None` before `.strip()` | SB-F11 |
| 5 | **Truncated mid-generation** | `finish_reason == "length"` via `_complete_ex` | SB-F13 |
| 6 | Trivially short output — a heading with no body | Minimum-length threshold (needs a chosen value) | SB-F12 boundary |
| 7 | Refusal / meta-commentary | Content heuristic only — **recommended out of scope** | SB-F14 |
| 8 | Ungrounded content generated from an empty context | Context-size precondition at `:128` | SB-F03 |
| 9 | Missing key in `content_json` | `set(content) != set(_BIBLE_SECTIONS)` | not currently reachable |
| 10 | `content_json` is `{}` or unparseable | JSON parse + emptiness check | SB-F22 (legacy rows) |

Classes 1–5 and 8–10 are deterministic and belong in code. **Class 7 is not deterministic and should not be attempted in Task 3.2** — a heuristic that mislabels a genuine section as failed erodes the trust the status field is being built to earn. Class 6 needs a threshold decision from the user before it can be implemented.

---

## 7. What the author is told today

Consolidating the author-visible half, because "the status is wrong" understates it:

| Surface | Behaviour when every section is a placeholder | Reference |
|---|---|---|
| `GET /story-bible` | `200` with `status: "completed"` | `story_bible.py:244–264` |
| Completion toast | **"Story Bible is ready."** — an explicit success notification, fired app-wide on the `running → completed` transition | `useStoryBible.ts:44–47` |
| Panel | Renders the placeholder strings as section text, with the Regenerate/Download/Refresh header of a finished bible | `StoryBiblePanel.tsx:138–178` |
| Empty section (SB-F12) | Renders *"Not yet generated."* inside a bible labelled complete | `StoryBiblePanel.tsx:23` |
| DOCX export | Placeholder text is exported as document content; empty sections are **silently dropped** with no note | `story_bible.py:314–329` |
| Stuck `running` (SB-F23/25/26/27) | Spinner and "This usually takes 1–3 minutes" indefinitely; polls every 4 s; retry is refused by the duplicate guard | `StoryBiblePanel.tsx:85–95`, `useStoryBible.ts:29–30`, `story_bible.py:194` |

The success **toast** is the sharpest instance: the system does not merely fail to report a problem, it actively asserts success. That is the same false-success class the checklist calls out for the voice agent in Task 3.7.

---

## 8. Inputs to the remaining Stage 3.2 subtasks

Derived from the enumeration; recorded so the next units are written against evidence rather than re-derived.

### 8.1 Required tracking (subtask 2 — "Track per-section success/failure")

Per section, the outcome must capture at minimum: the section key, an outcome (`ok` / `failed`), the failure class (invocation error, empty, truncated, exception), and a short reason safe for the UI. Two constraints from this audit:

- The outcome must be decided from the **response**, not only from whether an exception was raised — otherwise SB-F12 and SB-F13 remain invisible. This requires switching `generate_story_bible_section` to `_complete_ex()` so `finish_reason` reaches the caller.
- The outcome must exist **outside** `content`, so the persistence layer at `:144–152` can read it. Storing failure inside `content` is SB-F16, the defect itself.

### 8.2 Status decision table (subtask 3)

| Sections producing genuine content | Terminal status |
|---|---|
| 5 of 5 | `completed` |
| 1–4 of 5 | `partial` |
| 0 of 5 | `failed` |
| Pipeline aborted before the loop (SB-F01, SB-F02) | `failed` |
| Context precondition unmet (SB-F03) | `failed` |
| Commit failure (SB-F23) | `failed` — **requires the rollback fix**, otherwise unreachable |
| Interrupted (SB-F25, SB-F26, SB-F27) | `running` → `failed` at next startup (existing behaviour, SB-F31) |

"Genuine" is Section 6, classes 1–5 and 8–10.

### 8.3 Schema (subtask 4 — `failed_sections`)

- `status` needs **no migration**: it is an unconstrained `String` (`models.py:1076`); `partial` is a new value, not a new type. **Verified live on 2026-07-25** — `information_schema` reports `character varying`, and `pg_constraint` reports **no `CHECK` constraints** on `story_bibles`. The column is also nullable in the live schema, so the status logic must treat `NULL` explicitly (Section 5, SB-F22).
- `failed_sections` **does** need a migration — nullable JSON, defaulting to empty, following the reversible idempotent pattern of `0015`.
- Both `StoryBibleOut` (`schemas.py:1382–1391`) and the frontend `status` union (`StoryBiblePanel.tsx:32`, `useStoryBible.ts`) must learn `partial`. The panel currently falls through to the "completed" branch for any unrecognised status — so shipping the backend before the frontend renders a partial bible as if it were complete. **Sequence backend and frontend accordingly, or ship them together.**

### 8.4 Never persist a placeholder (subtask 5)

Once outcomes are tracked, `:138` and `:140` should stop writing prose into `content`. A failed section should be **absent** from `content_json` and named in `failed_sections`. This also retires the detector risk in SB-F15 — with no placeholder ever written, the database-state check becomes "no placeholder string exists in any row", which cannot false-positive on genuine bracketed prose.

### 8.5 Verification checkbox (Task 3.2 verification, item 3)

Do not implement the `[`-marker scan as literally worded — see SB-F15. Assert on `status` + `failed_sections`, and if a content scan is kept, match the exact placeholder strings.

### 8.6 Cross-task dependencies

- **Task 3.3** must not land before SB-F08 returns an honest status: raising the context budget makes a 400 context-length error materially more likely, and today that error is written into the bible as if it were a section.
- **Task 3.7** (voice agent false success) is the same defect class — success asserted from plan completion rather than from a verified outcome. Whatever contract 3.2 establishes should be the one 3.7 reuses.
- **SB-F23's rollback fix** is arguably a prerequisite of the status work rather than a separate concern: without it, `failed` is unreachable on the commit path, so the status contract would be incomplete on the very path most likely to lose data. Flagged for the user's decision when subtask 3 is planned.

---

## 9. Re-verification

### 9.1 Re-running the production baseline

Run these against the live database (reachable at `localhost:5432/narratiq`); they are the exact queries used for Section 2.1:

```sql
SELECT status, count(*) FROM story_bibles GROUP BY status;
SELECT count(*) FROM story_bibles
 WHERE status = 'completed'
   AND (content_json LIKE '%[AI temporarily unavailable%'
     OR content_json LIKE '%[Error generating %');
SELECT count(*) FROM story_bibles WHERE status = 'completed' AND content_json IN ('{}', '');
```

Read-only. Match the exact placeholder strings, never a bare `[` (SB-F15). Record the result in Section 2.1 with its date.

If the PostgreSQL client binaries are unavailable (they are not on `PATH` on this pod), connect through the backend's own SQLAlchemy engine using `backend/.env`. If no database is reachable at all, the equivalent numbers can be recovered from a custom-format dump by parsing its TOC and per-table data blocks directly — the method used for Section 2.2, reproducible from the dump file alone.

### 9.2 When this audit must be revisited

- `_generate_bible_pipeline`, `generate_story_bible_section`, `_complete` / `_complete_ex`, or `orphan_recovery.py` change materially.
- Bible sections become structured output (activates rows 1–3 of the Section 5 L3 applicability table).
- Deployment moves beyond `--workers 1` (activates SB-F29, SB-F32).
- The OpenAI client's `timeout` / `max_retries` change (SB-F07).

All line references are pinned to `cb0144a`. They will drift; the path IDs will not.

---

## 10. Explicitly out of scope for Task 3.2

Recorded so they are neither silently fixed nor silently lost: SB-F04 (context truncation → Task 3.3), SB-F14 (refusal detection → Task 3.3), SB-F21 (no generation history), SB-F28 (`job_id` observability), SB-F29 (multi-worker race), SB-F30 (`running` vs queued), SB-F32 (unconditional sweep), an in-process watchdog for stuck `running` rows (SB-F31 caveat), and the SB-F02 blast-radius reduction. None is a status-integrity defect; each is a real, separately-scoped improvement.
