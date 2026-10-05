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
| AI output clearly worse after a prompt change | Prompt version (§5a) — one restart, no code change |
| AI output clearly worse after a model change | Model (§5) |
| Data damaged | Restore (`backup-and-restore.md` §4) — last resort |

## 2. Code

Releases are git commits on `main`. Tag each release (`git tag v3.3.0`, or `release-YYYYMMDD`) — **as of 2026-10-05 the repository has no tags at all**, so the previous release must be identified by commit until one is tagged. On the pod:

```bash
cd /workspace/narratiq-ai                 # your checkout (any path since Stage 12 Tranche 3)
git fetch origin
git log --oneline -5                     # identify the previous good commit / tag
git checkout <previous-good-commit>      # run by the operator, deliberately
bash start-narratiq.sh                   # backs up, then rebuilds and restarts
```

`start-narratiq.sh` takes a pre-migration backup first and never downgrades the schema by itself — if the release added migrations, do §3 **before** starting the old code (old code on a newer schema is usually fine for additive migrations like 0024, but not guaranteed).

### 2a. Remove configuration keys the older code does not recognise

`backend/config.py` rejects any non-empty `backend/.env` key that is not one of its fields (`extra="forbid"`): **older
code refuses to start** if `.env`, or the environment, sets a key that was added after it. Before starting the older
code, remove every key the target release does not define, then restart.

Keys added since the A22 rollback target (`0032a81`, Stage 11), from a diff of the `Settings` fields:

| Key | Added | If set, remove before rolling back past |
|---|---|---|
| `AI_STREAM_ROUTES_ENABLED` | Stage 12 Tranche 1 (A3) | Tranche 1 |
| `CHILDREN_SUITABILITY_OVERRIDE` | Stage 12 Tranche 2b (A14) | Tranche 2b |
| `PROMPT_INJECTION_DATAMARK_QA` | Stage 12.2 (2026-10-05) | Stage 12.2 |
| `LIGHT_STRENGTH_REPAIR`, `LIGHT_NEW_SHARE_MAX` | Stage 12.3 (2026-10-05) | Stage 12.3 |

```bash
cd /workspace/narratiq-ai                 # your checkout
git show <target-commit>:backend/config.py > /tmp/target-config.py    # read-only
grep -E '^[A-Z_]+=' backend/.env | cut -d= -f1    # keys set now; drop any the target lacks
```

All three default correctly when unset, so on a pod that never set them (pod `55zfw2ol0sx1gi`, checked 2026-10-05)
nothing needs removing. Remove the same keys from the RunPod UI environment if they were set there. The general
rule for any future release: **list the keys it added, and remove them from `.env` and the pod environment before
starting older code.**

## 3. Database schema (Alembic)

Every migration from `0001` to head has a real `downgrade()`, except `0026`, whose downgrade is intentionally a no-op: the four columns it records predate it and hold author data, so they are kept. Find what the release added: `ls backend/migrations/versions/` (compare with the previous commit) or `cd backend && alembic history | head`.

```bash
cd /workspace/narratiq-ai/backend                    # your checkout's backend/
bash ../scripts/backup_database.sh                   # always first
python3 -m alembic downgrade <revision-of-the-previous-release>
python3 -m alembic current                           # confirm
```

**Downgrade with the code you are leaving, not the code you are going to:** the older release does not contain the newer migration files. So `alembic downgrade <previous head>` runs **before** `git checkout`.

What a downgrade loses: **only the objects that migration created** — e.g. downgrading `0024` drops `revoked_sessions` and `error_events` (error history) and removes `users.token_version`. Downgrade `0024` only **together with** the code rollback: Stage 10 code needs those objects. After rolling back to pre-Stage-10 code every author signs in once more — the old frontend keeps its token in localStorage and cannot use the new cookie sessions — and revocation no longer exists (the Stage 9 finding J1 returns). Author content is never in a table or column a Stage 7–10 migration drops, except the Phase 3 objects listed in the migration docstrings (pins, idea-shelf fields — the idea card itself survives, `run_migration_roundtrip.sh`).

**Rehearsed on a populated database** (`backend/tests/run_downgrade_walk.py`, 2026-09-29, when the head was `0024`): head → 0016 one revision at a time, then back to head — 16 steps then (22 at today's head `0027`); after every step every table and column outside that migration's own objects is byte-identical (per-column hashes, vectors included), and the full walk returns every surviving table to its starting content. Plus the Phase 3 round trip `backend/tests/run_migration_roundtrip.sh`. Run both against `narratiq_test` before any release that adds a migration.

Note: `start-narratiq.sh` also runs `Base.metadata.create_all()` before `alembic upgrade head`; a table whose model still exists in the checked-out code is recreated empty by create_all even after its migration is downgraded. That is harmless (empty) and is why every migration is written to tolerate existing objects.

**Rolling back across Stage 12 (`0027`):** downgrading `0027` drops `characters.presence`. Every character's *On page / Mentioned only / In the past* label is lost. Rolling forward again recreates the column **empty**; running cast generation again can label characters again. Nothing else about the character changes (rehearsed 2026-10-03, §6).

## 4. Frontend

`start-narratiq.sh` keeps the previous build in `frontend/.next.prev`. On a fresh pod there is none until the script has built the frontend a second time (the script then says "No previous build … nothing to roll back to").

```bash
bash scripts/rollback_frontend.sh --dry-run    # shows both build ids
bash scripts/rollback_frontend.sh              # swap and restart Next.js only
bash scripts/rollback_frontend.sh              # run again to swap back
```

**Not across a Next.js major version.** `.next.prev` is served by the current `node_modules`. After the Next.js 14 → 15 upgrade (Stage 12 A5), a Next.js 14 build cannot be served by the Next.js 15 packages. Rolling the frontend back past that boundary needs the full code rollback (§2), which reinstalls the old packages (`npm ci`) and rebuilds: about 3½ minutes in the 2026-10-03 rehearsal.

Since Stage 10 (10.7) the build does not embed the pod's backend URL for HTTP (the browser calls `/api` on its own origin), so an old build also works on a new pod — except the voice WebSocket, which still uses `NEXT_PUBLIC_API_URL`; the script warns when that points at another pod. Phase 3 UI alone can also be switched off with a rebuild using `NEXT_PUBLIC_P3_ENABLED=false`.

## 5. Models

All models are pinned to exact Hugging Face commits (`docs/operations/model-versions.md`). To roll a model back (or forward):

```bash
mv /workspace/models/Qwen2.5-7B-Instruct /workspace/models/Qwen2.5-7B-Instruct.bad   # keep until verified
NARRATIQ_QWEN_REVISION=<previous commit> MODEL_BASE_DIR=/workspace/models bash scripts/download_models.sh
bash start-narratiq.sh
```

Measured 2026-10-03: the pinned 15 GB Qwen download took **26 s** on the pod. The restored weights were byte-identical to the originals (SHA-256 over all four shards), and `start-narratiq.sh` was back to READY afterwards (§6).

### 5a. Prompt version (configuration rollback)

Prompt changes ship as versions (`services/prompt_registry.py`); the default is `PROMPT_VERSION=v4`. To go back one version without touching code, add `PROMPT_VERSION=v3` to `backend/.env` (or the environment) and restart **only the backend** (vLLM and the frontend keep running; about 25–30 s):

```bash
cd /workspace/narratiq-ai/backend                      # your checkout's backend/
echo 'PROMPT_VERSION=v3' >> .env
kill $(ss -ltnpH 'sport = :8000' | grep -o 'pid=[0-9]*' | cut -d= -f2 | sort -u)
while ss -ltnH 'sport = :8000' | grep -q .; do sleep 1; done
nohup python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1 \
  --no-access-log --no-proxy-headers >> /tmp/narratiq-logs/backend.log 2>&1 &
until curl -s localhost:8000/api/health | grep -q '"backend":"ready"'; do sleep 2; done
```

(The same four lines after `echo` restart the backend for any configuration change. `start-narratiq.sh` also works but restarts vLLM and rebuilds the frontend, about 4 minutes.) Every rewrite logs the version it actually used: `[prompt_version] transform=<tool> version=<v>` in `/tmp/narratiq-logs/backend.log` — one JSON object per line, so search for `prompt_version`. A request that comes back "no change needed" runs no rewrite and logs no version; check with a passage that needs changing. Remove the line (`sed -i '/^PROMPT_VERSION=v3$/d' .env`) and restart the same way to return to the default. An unknown value falls back to `PROMPT_VERSION_FALLBACK` (`v2`) and logs an error. Rehearsed 2026-10-03: about 70 s per restart; `version=v3`, then `version=v4` confirmed in the log.

Changing **BGE-M3** changes every embedding's meaning: after a BGE-M3 change all chapters must be re-indexed (`POST /api/stories/{id}/chapters/sync-summaries` per story). Never mix embeddings from two BGE-M3 revisions in one database.

## 6. Full rehearsal record

| Path | Rehearsed | Where / result |
|---|---|---|
| Schema, populated DB, 0024 → 0016 → 0024 | yes, 2026-09-29 | `run_downgrade_walk.py` PASS (Stage 10 report) |
| Phase 3 round trip | yes, 2026-09-29 | `run_migration_roundtrip.sh` PASS |
| Code checkout of the previous release on the live pod | not performed on the live checkout. It needs the product owner to choose the release and run `git checkout` (this workflow runs no git write commands). Rehearsed in isolation instead, row below | — |
| **Code + schema + frontend to the previous release, isolated** (current `f7a7a2e`+Tranche 3 → **`0032a81`**, Stage 11; Next.js 15 → **14.2.35**; `0027` → `0026`) | **yes, 2026-10-03** (Stage 12 Tranche 3, A22; MV-10.5) | Backup of the live DB → old code exported with `git archive` (read-only) → backup restored into scratch DB `narratiq_rollback` (57/57 tables equal to the manifest) → `alembic downgrade 0026` with the current code → old backend (its own `requirements.txt` in a venv, e.g. python-jose 3.4.0) on :8200 → old frontend `npm ci` + build on :3300. **Ready in 369 s** (backup 2 s, export 6 s, restore 1 s, downgrade 4 s, backend 132 s, frontend 224 s). Signed in through the **old UI**, opened the restored story (chapters present), and one model call (refine) through the old stack returned 200. **Roll-forward:** `alembic upgrade head` in 2 s. Then 55 of 57 tables byte-identical to the backup, chapter text and embeddings equal. `characters` differs only by the lost `presence` labels (§3). `voice_usage_daily` differs only by an `updated_at` stamp the old backend wrote at startup, with every counter 0. Live checkout, database and services untouched. RTO target ≤ 2 h: met |
| **Model revision rollback** | **yes, 2026-10-03** | Qwen moved aside as `.bad` (simulated bad model) → pinned revision `a09a354…` re-downloaded in **26 s**, byte-identical (SHA-256 over all shards) → `start-narratiq.sh` READY (see the Tranche 3 report for its time) |
| **Prompt version (config)** | **yes, 2026-10-03; again 2026-10-05** (Stage 12.2 operator walkthrough, following §5a literally) | `PROMPT_VERSION=v3` → log shows `version=v3` → removed → `version=v4`; ~70 s per backend restart (2026-10-03); 27–28 s with the backend-only restart above (2026-10-05) |
| **Frontend swap** | Stage 10 report; **again 2026-10-05** (Stage 12.2 walkthrough) | `rollback_frontend.sh --dry-run` showed both build ids → swap 4 s → public `/login` and `/api` 200 → swap back 5 s. `docs/testing/stage-12/stage-12.2/operator-walkthrough.md` |
