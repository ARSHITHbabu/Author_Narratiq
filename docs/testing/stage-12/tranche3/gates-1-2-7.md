# Stage 12 remediation Tranche 3 (A24): Gates 1, 2 and 7 revalidated

| | |
|---|---|
| **Date** | 2026-10-03 |
| **Pod** | `x0smrkvs4n6wpk`: 1× NVIDIA A40 (46068 MiB), fresh reset (S12-D: no usable backup, empty database) |
| **Code** | commit `f7a7a2e` plus the uncommitted Tranche 3 changes |
| **Scope** | Current evidence for release Gates 1, 2 and 7 (Master Execution Plan §13). This is **evidence for task 12.1, not 12.1 itself**. No gate is closed here, and no human or external item is treated as passed. |

The definitions come from the Master Execution Plan §13:
* **Gate 1, Environment stable.** Ports 3000/8000 reachable externally; `/api/health` fully healthy; AI generation succeeds through the proxy; env vars clean; `verify_runpod_setup.sh` passes truthfully.
* **Gate 2, Core workflows functional.** Plot holes, outline, continuation and continuity return usable output or honest errors. Story Bible is never `completed` on partial content and never asserts unsupported facts. The voice agent never falsely reports success. OCR, notes and analytics are accessible.
* **Gate 7, Backup and recovery verified.** Automated backup running; restore rehearsed from a real backup into a clean database; RPO/RTO documented.

## Data used

A **disposable author** was created on the live stack **through the public API only**: register, a story with 4 chapters, 4 characters (including a `historical` presence), a note, indexing, and one audio upload. A restore of an empty database proves nothing, so this gave the backup real content to carry: chapters, embeddings, a note, an upload file. `seed_fixture.py` was not used on the live database because it refuses any database that is not allow-listed for tests, by design. The account is deleted at the end of Tranche 3 through `DELETE /api/auth/account`.

## Gate 1: Environment stable

**Technical evidence (agent-verified)**

| Check | Result |
|---|---|
| Fresh-pod bring-up, `start-narratiq.sh` | READY, exit 0, **14 min 35 s** (05:42:30 → 05:57:05 UTC). Installed Node 20.20.2, PostgreSQL 16 + pgvector 0.8.6, vLLM 0.9.2 and torch 2.7.0+cu128, downloaded the 4 pinned models, applied migrations to head `0027` |
| `scripts/verify_runpod_setup.sh --expect-running` | **39 passed, 0 failed**, exit 0 (`gate1-verify-runpod-setup.log`). Ports 3000/8000 exposed (RunPod API), both proxies HTTP 200, vLLM generation smoke test, pgvector query, no stale `NEXT_PUBLIC_API_URL` |
| `/api/health` | `ok`: backend, vLLM and BGE-M3 `ready`; GOT-OCR `lazy` |
| vLLM bind | `127.0.0.1:9001` only (`ss`); the RunPod proxy answers **404** for 9001 |
| AI generation **through the public proxy** | login 200, then `POST /api/ai/refine` 200 in 0.8 s, with a real rewrite returned |
| Environment | `backend/.env` holds the 7 generated keys only (SECRET_KEY, OPS_TOKEN, LOG_FORMAT, DATABASE_URL, VLLM_BASE_URL, VLLM_MODEL_NAME, CORS_ORIGINS) |

**Found and fixed:** `start-narratiq.sh` hardcoded `/workspace/narratiq-ai`, but this checkout is `/workspace/Author_Narratiq`. The bring-up used an approved temporary symlink. A25 made the script find its own checkout, verified without the symlink.

**Human / external, not closed here:** a copy of `SECRET_KEY` in a team secret store (task 2.2). This bring-up generated a **new** `SECRET_KEY`.

## Gate 2: Core workflows functional

**Technical evidence (agent-verified)**, on the live stack with the disposable author's story *after* it had been restored from backup (`gate2-live-workflows.json`):

| Workflow | Result |
|---|---|
| Plot holes | 200, 1.9 s: 4 chapters analysed, 0 issues, `degraded: false` |
| Outline | 200, 10.5 s, beats returned |
| Continuation | 200, 15.8 s, options returned |
| Continuity | 200: 4 chapters scanned, 0 issues, `degraded: false` |
| Story Bible | generated in ~44 s, `completed`, `failed_sections: []`, 5/5 sections; provenance logged per section (characters 28/28 entries cited, locations 12/12, timeline 13/13, world rules 6/6, themes 7/11) |
| OCR (GOT-OCR2.0, real model) | 200, 10.4 s. A printed test image ("The harbour lamp holds. / Wren keeps the keys.") was read exactly |
| Notes | 200, the restored note is present |
| Analytics | 200 |
| Audio (Tranche 3, A21) | `audio-transcription.spec.ts` 3/3 live: real transcript, appended to a note, still there after a reload |

The voice-agent honesty and OCR browser specs are part of the final live browser run in the Tranche 3 completion report.

**Human judgement, not closed here:** "Story Bible never asserts unsupported facts" needs the author's reading. The provenance figures above are evidence, not a verdict. Real-author UAT (9.6) and Gate 3b also stay with the product owner.

## Gate 7: Backup and recovery verified

**Technical evidence (agent-verified)**

| Step | Result |
|---|---|
| Backup | `backup_database.sh` → set `narratiq-20261003T060251Z`: dump 208 KB, manifest, uploads archive, globals, SHA256SUMS. Marked `.keep` |
| Verification | `verify_backup.py --set …` **PASS**: 57 tables and 30 rows checked, 1 upload file, scratch restore 0.5 s (`gate7-last-verify.json`) |
| **Restore into a clean database**, `backup-and-restore.md` §4 on the **live** database (no real authors on this pod) | Writes stopped. Set verified. Safety backup `narratiq-20261003T060338Z` taken (kept). Live database **dropped and recreated**, dump restored, uploads restored from the archive (the original folder was moved aside first, so the restore is proven). **Manifest MATCH: all 57 tables** (per-table content hashes, chapter text hash, embedding counts, uploads) (`gate7-restore-steps.log`) |
| Restart (§4 step 9) | `start-narratiq.sh` READY in **337 s**. Its pre-migration check found the 0-hour-old backup and skipped a duplicate. Health `ok` |
| Gate 2 on the restored data | all workflows above |

**RTO measured (target ≤ 2 h):**
* Restore steps 1–8: about 25 s of commands (plus an operator pause, see below).
* Step 9 restart: 337 s.
* About **6.3 min** in total to restore on a running pod.
* From a **fresh pod**: the bring-up (14 min 35 s) plus the restore gives about **21 min**, well inside 2 h. This is the first end-to-end fresh-pod RTO timing; Stage 10 had only timed the restore step.

**RPO:** unchanged by design. Hourly sets plus a backup before every migration. The loop restarted at 05:57 and again in step 9.

**Defect found in the runbook and fixed (A24):** §4 has the operator export `PGHOST`/`PGUSER`/`PGPASSWORD` for step 3's verification. Plain `su postgres -c` **keeps** those variables, so in the same shell step 6's `dropdb` ran as the owner `narratiq` and **succeeded**, and `createdb` then failed ("permission denied to create database"). The database was gone before the restore began. Here it held only the disposable data and the set had just been verified; the documented steps were resumed with the variables cleared. `backup-and-restore.md` §4 now says to `unset` them before step 5 and to export them again for step 8.

**Observed, unchanged:** the network volume does not enforce `chmod`, so backup files are mode 666 / 777. The scripts already warn about this on every run.

**External / human, not closed here:**
* The off-pod copy (S10-B, deferred): loss of the network volume still loses the backups.
* Person-delivered alerts (S10-D).
* After the disposable author is deleted, the database is empty again while backups holding that author's data exist. The guard was corrected in the Tranche 3 addendum: backups of an *empty* database no longer count as evidence. It still blocks this pod, correctly. Five backups hold author rows, and the database cannot show that they were deleted on purpose. A normal restart here needs `NARRATIQ_ACKNOWLEDGE_EMPTY_RESTART` (or an operator decision about those disposable sets) until deletion-intent state exists (see the addendum).
