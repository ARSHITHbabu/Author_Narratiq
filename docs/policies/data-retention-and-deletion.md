# Data retention and deletion policy

**Stage 10, task 10.6 (production gap PG-07; decision S10-G).** Engineering source of truth. The author-facing version is published in the app at **`/data-policy`** (`frontend/app/data-policy/page.tsx`); keep the two in step.

Effective 2026-09-29.

---

## 1. Retention

| Data | Kept | Mechanism |
|---|---|---|
| Manuscripts, chapters, characters, relationships, notes, note cards / Idea Shelf, Story Bible, story intelligence, summaries, search index (chunks + embeddings) | Until the author deletes them, or the account | — |
| OCR page images, audio uploads (files) | 24 h after the author confirms the text; 72 h if never confirmed | hourly sweep in `main._cleanup_ocr_images` / `_cleanup_audio_files`; the DB row keeps the text the author accepted and loses only the file path |
| AI-generation pins | Plan TTL (decision D1/D3): free **7 days**, basic 30, pro 90, studio 180; hard ceiling 365 | `expires_at` set at insert; hourly sweep `_cleanup_expired_pins` |
| Unpinned AI results | **Never stored** server-side (Phase 3 rule R1) | browser memory only |
| Voice sessions / commands, activity events | With the story or account | cascade / account deletion |
| Built-in error records | 30 days, max 5,000 rows; contain no author content or user id by construction | hourly prune (`services/error_tracking.prune_events`) |
| Revoked-session records | Until the revoked token would have expired (≤ `JWT_EXPIRE_MINUTES`) | hourly sweep |
| On-pod backups | 24 hourly sets + one per day for 7 days | `scripts/backup_retention.py` (`docs/operations/backup-and-restore.md`) |
| Upload files no row refers to | Removed once older than 6 h | hourly `services/account_deletion.remove_orphan_upload_files` |

Backups never contain pin rows (decision D9).

## 2. Deletion

### Chapter
`DELETE /api/stories/{story_id}/chapters/{chapter_id}` — removes the chapter, its versions, chunks and embeddings, its summary, character mentions, character hints and arc snapshots. Timeline events keep their text and lose the chapter link; pins and note cards that pointed at it keep existing with the link cleared (they belong to the story, not the chapter).

*Defect fixed in Stage 10:* before this, deleting any chapter that had been indexed (i.e. had a summary) failed with a database integrity error.

### Manuscript (story)
`DELETE /api/projects/{story_id}` — removes the story and every row that references it (≈45 cascading relationships plus database-level cascades for pins, voice sessions/commands and activity events), including every embedding. Verified by test: after deleting a fully populated story no table holds a row referencing it.

### Account — immediate hard delete (S10-G)
`DELETE /api/auth/account` with `{"password": "...", "confirm": "DELETE"}` (the app's **Account** page).

1. The password is checked again; the typed word `DELETE` is required.
2. Every row belonging to the account is found by following foreign keys outward from the `users` row across the whole schema (`services/account_deletion.owned_rows`), so a table added later is covered automatically.
3. All of them — including every vector column, which lives in those rows — and the `users` row are deleted in **one transaction**: either the account is entirely gone or nothing is deleted (an error answers *"Nothing was deleted"*).
4. After the commit, the uploaded files those rows pointed to are removed. A file that cannot be removed at that moment is picked up by the hourly orphan-file sweep.
5. Every session ends (the account no longer exists); the browser's cookies are cleared.

Verified by test (`backend/tests/test_account_deletion_stage10.py`): a fully populated account — all nine embedding columns filled, OCR image and audio files on disk, voice sessions with and without a story, usage and activity rows, a revoked session — leaves **zero** rows referencing its user, stories or chapters in any of the 57 tables, zero vectors, no files, and another author's rows byte-identical.

## 3. What cannot currently be guaranteed

* **Backups.** Copies made before a deletion stay in on-pod backups until rotation removes them — **at most 7 days** plus the time to the next daily set. A restore from such a backup would bring deleted data back; restoring is a deliberate, manual operation (`backup-and-restore.md`), and whoever restores must re-apply deletions made after the backup's snapshot time.
* **Off-pod copies.** None exist (deferred, decision S10-B). When one is added, its retention must be added here and to `/data-policy`.
* **In-flight AI jobs.** A background job already running for the account when it is deleted fails when it tries to write (the rows it needs no longer exist); it cannot recreate account data.
* **Logs.** Backend logs never contain manuscript text; they can contain the first 8 characters of a user id. They live in `/tmp/narratiq-logs` (lost on restart) and `/workspace/logs` (not rotated automatically in Stage 10).
* **Aggregates without an account id** (e.g. `voice_usage_daily` rows with no user) are not personal data and are kept.

## 4. Sessions

Signing out ends that device's session only. Changing the password ends every other session (the device that changed it stays signed in). Account deletion ends all sessions.
