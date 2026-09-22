# Incident Report — Unexplained drop in user/story/chapter row counts during Stage 6 CI setup

| Field | Value |
|---|---|
| **Incident** | A database snapshot taken mid-way through Stage 6 work showed 2 users / 2 stories / 9 chapters; a later snapshot, after removing 4 confirmed-harmless test-residue accounts, showed 1 user / 1 story / 3 chapters — a discrepancy of exactly 1 user, 1 story, 6 chapters |
| **Date** | 2026-09-22 |
| **Pod ID** | `aivwnipdrkn109` |
| **Severity** | Treated as P0 data-safety concern until investigated (per project policy: manuscript/data safety is priority #1) |
| **Status** | Investigated. Root cause **not proven** (no query-level logging existed to prove it), but strong converging evidence supports one specific, benign explanation over any deletion-of-real-data explanation. Stage 6 implementation paused pending author review of this report. |
| **Confidence** | High (~90%) that this was a self-cleaning test fixture caught mid-execution, not real author data — see evidence below. Not 100%, because the exact moment was not empirically re-observed (deliberately not reproduced against the live DB, per explicit instruction). |

---

## 1. Executive summary

**No evidence was found that any real author data was deleted.** The most likely explanation, supported by multiple independent pieces of evidence, is that the first snapshot was taken while a disposable, self-cleaning backend test fixture (`tests/fixtures/retrieval_fixture.py::build_fixture`) was transiently alive in the same shared database, and that fixture's own teardown correctly removed it before the second snapshot. The counts, the timing, and the fixture's own code all line up. However, this was reconstructed from static code inspection and log review after the fact — it was not caught live — so it is reported as strong evidence, not proof.

**Root cause of the underlying *process* mistake:** the investigating session ran the full backend `pytest` suite directly against the shared development database (the same database the author's real account and stories live in) instead of an isolated test database. Several backend tests create and delete their own disposable fixture rows in whatever database `DATABASE_URL` points to. This is by design and normally invisible — but it means a snapshot of that database taken while tests are running can show transient rows that look, at a glance, like real data disappearing. That is the actual mistake: not a deletion bug, but taking a live count against a database that a test run was actively (and correctly) mutating.

## 2. Timeline

| Time (UTC) | Event |
|---|---|
| 14:26:05 | Backend starts (fresh pod, empty database) |
| 14:35:14 | **Only** user registration ever logged by the app: `[auth] new user registered: 8f3d3fe8` |
| 14:35:23–14:49:56 | Author's own manual Stage 5 review testing (story "sample", 3 chapters, various AI tool calls) |
| 15:27:14 | Last backend log entry before this investigation began (hourly voice-analytics rollup; silence after this — consistent with the author's testing session ending) |
| ~15:3x (unlogged) | Investigating session runs `pytest tests/ -q` in the background **against the live `narratiq` database** (no `DATABASE_URL` override) |
| ~15:3x (unlogged, shortly after) | Investigating session runs `SELECT count(*) FROM users/stories/chapters` as a safety check before a migration test → **2 / 2 / 9** |
| ~15:41 (unlogged) | Full pytest run completes: 461 passed, 3 failed (pre-existing, documented), 2 errors (pre-existing collection issue, since fixed) |
| ~15:42 (unlogged) | A second, smaller pytest run (2 files only) also run against the live `narratiq` database |
| ~15:44 (unlogged) | `SELECT email FROM users` → 1 real account + 4 `voice-route-test-*@example.com` accounts (0 stories each — a separately pre-existing, already-documented test-residue pattern, confirmed harmless and removed) |
| 15:45 | After removing the 4 confirmed-empty accounts: **1 / 1 / 3** remain |
| 15:48:17 | Full database backup taken (`/workspace/backups/narratiq-20260922T154817Z.dump`) before any further investigation |

**No `DATABASE_URL` override was used for either pytest run — both ran against the live/dev `narratiq` database, not an isolated one.** This is the process mistake being corrected (see Safeguards, §5).

## 3. Evidence gathered

### 3.1 The application's own registration log rules out a second real account
`grep "new user registered" backend.log` for the entire pod lifetime returns **exactly one line**, at 14:35:14, matching the user ID (`8f3d3fe8...`) of the account still present now. If a second real account had ever been created through the app's own registration endpoint, it would have logged here. It did not.

### 3.2 A specific test fixture matches the missing counts exactly
`backend/tests/fixtures/retrieval_fixture.py::build_fixture()` creates, per call:
- **exactly 1** `User` row (`retrieval-fixture-{random-tag}@narratiq-internal-test.com`)
- **exactly 1** `Story` row (`"[4.2/4.15-FIXTURE] The Salt Road ({tag})"`)
- **exactly 6** `Chapter` rows (`CHAPTERS` list in the same file has 6 entries)

This is used by 7 different test files (`test_cast_classification_accuracy.py`, `test_cast_hint_sync_integration.py`, `test_chapter_arc_fields.py`, `test_plot_importance_ranking.py`, `test_recall_measurement.py`, `test_semantic_search_stability.py`, `test_story_bible_quality.py`), several of which run early in pytest's default alphabetical collection order — consistent with the timing above. Each chapter is passed through `embed_and_store_chunks()` (a real BGE-M3 embedding call per chapter, CPU-bound in this environment), which gives the fixture a non-trivial, multi-second-to-tens-of-seconds window of being "alive" in the database before its own teardown runs — a large enough window for an unrelated concurrent query to land inside it.

Its teardown (`cleanup_fixture()`) deletes by exact `story_id`/`user_id`, and asserts zero orphan rows remain afterward — the same disciplined pattern used by every other DB-touching fixture in this suite (`test_character_merge.py`, `test_retrieval_scope.py`, etc.), none of which were found to perform any unscoped delete.

### 3.3 No code path was found capable of deleting a User by anything other than an exact, self-generated ID
- All 30 backend test files were searched for unscoped `DELETE`/`TRUNCATE`/`drop_all` — **none found**.
- The application has exactly one deletion endpoint that touches stories (`DELETE /api/projects/{story_id}` in `routers/projects.py`), and it is ownership-scoped (`Story.user_id == current_user.user_id`) — cannot touch another user's story.
- **There is no user/account-deletion endpoint anywhere in the application.** The only way a `User` row can be removed is direct database access or a test fixture's own scoped cleanup.
- `User.stories` has **no ORM cascade delete** configured (`relationship("Story", back_populates="user")`, no `cascade=`) — deleting a story does not delete its owner, and the ORM does not cascade-delete a user's stories automatically either.
- The only automatic background cleanup job (`_run_periodic_cleanup`, logged at startup as "cleanup scheduler started") is scoped **exclusively to OCR uploads** (`_OCR_CONFIRMED_TTL_HOURS` / `_OCR_UNCONFIRMED_TTL_HOURS`) — it cannot touch users, stories, or chapters.

### 3.4 What could not be checked
- **No SQL statement logging was enabled** on this Postgres instance (`log_statement` not configured), so there is no query-level audit trail to definitively prove which process executed the row-creating/deleting statements.
- `activity_events` (the app's own audit-trail table, built in Stage 5/migration 0013) is **completely empty** — it is not currently wired to log story/user creation or deletion at all, so it provided no help here. This is itself a real, separate gap (see §5.4).
- The exact single test file responsible was not pinpointed with certainty — several of the 7 consumers of the shared fixture are plausible given alphabetical execution order; the investigation did not re-run tests live to catch it in the act, per instruction not to attempt destructive reproduction against the live database.

## 4. What is NOT the cause (ruled out)

- **A real author-created second account, deleted by the author:** contradicted by §3.1 — the backend's own registration log shows only one registration ever.
- **An unscoped/buggy delete in application code:** searched and not found; the one deletion endpoint is properly ownership-scoped.
- **ORM cascade over-deletion (deleting a user wiping stories, or vice versa unexpectedly):** the actual cascade configuration was inspected directly and does not support this — `Story.chapters` cascades from Story (expected, safe), `User.stories` does not cascade at all.
- **The periodic OCR cleanup job:** scoped only to OCR uploads, cannot reach these tables.
- **The investigating session's own migration round-trip test:** run exclusively against an isolated, separately created `narratiq_ci_verify` database, dropped afterward — never touched `narratiq`.

## 5. Safeguards proposed (to be implemented as part of, or before, Stage 6 resumes)

1. **Never run the backend test suite against the shared/live database again.** An isolated `narratiq_test` database has already been created for this session's remaining work. This should become an enforced convention, not just a personal habit — see #2.
2. **Add a `conftest.py`-level safety guard** that refuses to run any DB-touching test unless `DATABASE_URL` resolves to a database whose name is not exactly the production database name (or matches an allow-listed test-DB pattern), aborting with a clear error otherwise. This is the same class of protection the Stage 6 plan already commits to building into `seed_fixture.py` (task 6.2) — this incident is a concrete argument for extending that same guard to the whole test suite, not just the fixture-seeding script.
3. **Document, in `backend/tests/` and in CI, that DB-touching tests must run against an isolated database** — CI's own Postgres service container already satisfies this by construction (task 6.1); this makes the same requirement explicit and enforced for local runs too.
4. **Wire `activity_events` to actually log story/account lifecycle events** (creation, deletion) — it exists, has the right shape, and is currently empty. This would have made this investigation conclusive instead of circumstantial, and is separately relevant to 6.3/6.4's "Activity timeline" checklist row, which cannot be meaningfully tested while the table is never written to.
5. **Consider enabling minimal SQL statement logging** (e.g., `log_statement = 'mod'`, logging only data-modifying statements) on the development Postgres instance, so a future discrepancy has a real audit trail instead of requiring static-code reconstruction after the fact.

## 6. Backup taken

`/workspace/backups/narratiq-20260922T154817Z.dump` (302K, SHA-256 checksummed, verified readable — 336 catalogue entries, 53 table-data entries) — taken before any further investigation that could modify state, per instruction. This backup is **on-pod only**; per the backup script's own warning, it is not safe until a copy exists off-pod.
