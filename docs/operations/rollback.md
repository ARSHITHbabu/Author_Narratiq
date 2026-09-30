# Rollback runbook

**Stage 10, task 10.5 (production gap PG-06).** How to reverse a bad release — code, database schema, models, frontend — and how each path was rehearsed. Target: back to the previous release within the RTO in `backup-and-restore.md` §6, without losing author data.

Principle: **roll back the smallest thing that fixes the problem**, and take a backup first (`bash scripts/backup_database.sh`, then `touch /workspace/backups/narratiq-<stamp>.keep`).

---

## 1. Decide what to roll back

| Symptom after a release | Roll back |
|---|---|
| UI broken, API healthy | Frontend only (§4) — seconds |
| API errors, no new migration in the release | Code (§2) |
| API errors, the release added a migration | Code + schema (§2 then §3) |
| AI output clearly worse after a model change | Model (§5) |
| Data damaged | Restore (`backup-and-restore.md` §4) — last resort |

## 2. Code

Releases are git commits on `main` (tag them: `git tag release-YYYYMMDD`). On the pod:

```bash
cd /workspace/narratiq-ai
git fetch origin
git log --oneline -5                     # identify the previous good commit / tag
git checkout <previous-good-commit>      # run by the operator, deliberately
bash start-narratiq.sh                   # backs up, then rebuilds and restarts
```

`start-narratiq.sh` takes a pre-migration backup first and never downgrades the schema by itself — if the release added migrations, do §3 **before** starting the old code (old code on a newer schema is usually fine for additive migrations like 0024, but not guaranteed).

## 3. Database schema (Alembic)

Every migration from `0001` to head has a real `downgrade()`. Find what the release added: `ls backend/migrations/versions/` (compare with the previous commit) or `cd backend && alembic history | head`.

```bash
cd /workspace/narratiq-ai/backend
bash ../scripts/backup_database.sh                   # always first
python3 -m alembic downgrade <revision-of-the-previous-release>
python3 -m alembic current                           # confirm
```

What a downgrade loses: **only the objects that migration created** — e.g. downgrading `0024` drops `revoked_sessions` and `error_events` (error history) and removes `users.token_version`. Downgrade `0024` only **together with** the code rollback: Stage 10 code needs those objects. After rolling back to pre-Stage-10 code every author signs in once more — the old frontend keeps its token in localStorage and cannot use the new cookie sessions — and revocation no longer exists (the Stage 9 finding J1 returns). Author content is never in a table or column a Stage 7–10 migration drops, except the Phase 3 objects listed in the migration docstrings (pins, idea-shelf fields — the idea card itself survives, `run_migration_roundtrip.sh`).

**Rehearsed on a populated database** (`backend/tests/run_downgrade_walk.py`): head → 0016 one revision at a time, then back to head — 16 steps; after every step every table and column outside that migration's own objects is byte-identical (per-column hashes, vectors included), and the full walk returns every surviving table to its starting content. Plus the Phase 3 round trip `backend/tests/run_migration_roundtrip.sh`. Run both against `narratiq_test` before any release that adds a migration.

Note: `start-narratiq.sh` also runs `Base.metadata.create_all()` before `alembic upgrade head`; a table whose model still exists in the checked-out code is recreated empty by create_all even after its migration is downgraded. That is harmless (empty) and is why every migration is written to tolerate existing objects.

## 4. Frontend

`start-narratiq.sh` keeps the previous build in `frontend/.next.prev`.

```bash
bash scripts/rollback_frontend.sh --dry-run    # shows both build ids
bash scripts/rollback_frontend.sh              # swap and restart Next.js only
bash scripts/rollback_frontend.sh              # run again to swap back
```

Since Stage 10 (10.7) the build does not embed the pod's backend URL for HTTP (the browser calls `/api` on its own origin), so an old build also works on a new pod — except the voice WebSocket, which still uses `NEXT_PUBLIC_API_URL`; the script warns when that points at another pod. Phase 3 UI alone can also be switched off with a rebuild using `NEXT_PUBLIC_P3_ENABLED=false`.

## 5. Models

All models are pinned to exact Hugging Face commits (`docs/operations/model-versions.md`). To roll a model back (or forward):

```bash
mv /workspace/models/Qwen2.5-7B-Instruct /workspace/models/Qwen2.5-7B-Instruct.bad   # keep until verified
NARRATIQ_QWEN_REVISION=<previous commit> MODEL_BASE_DIR=/workspace/models bash scripts/download_models.sh
bash start-narratiq.sh
```

Changing **BGE-M3** changes every embedding's meaning: after a BGE-M3 change all chapters must be re-indexed (`POST /api/stories/{id}/chapters/sync-summaries` per story). Never mix embeddings from two BGE-M3 revisions in one database.

## 6. Full rehearsal record

| Path | Rehearsed | Where / result |
|---|---|---|
| Schema, populated DB, 0024 → 0016 → 0024 | yes, 2026-09-29 | `run_downgrade_walk.py` PASS (Stage 10 report) |
| Phase 3 round trip | yes, 2026-09-29 | `run_migration_roundtrip.sh` PASS |
| Frontend swap | see Stage 10 report | `rollback_frontend.sh` |
| Code checkout of the previous release on the live pod | **not performed** — needs the product owner to choose the release and run `git checkout` (this workflow does not run git write commands) | manual test in the Stage 10 report |
| Model revision rollback | procedure documented; not performed (re-downloading 15 GB to prove a no-op swap was judged not worth the pod time) | — |
