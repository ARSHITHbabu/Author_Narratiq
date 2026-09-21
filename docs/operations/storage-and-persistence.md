# Storage and Persistence

| | |
|---|---|
| **Document** | Storage and Persistence — mount points, filesystem characteristics, storage layout |
| **Created** | 2026-07-24 |
| **Scope** | Identifies the network volume, records the current storage layout, and predicts which paths survive a pod stop (§8). |
| **Source task** | `docs/NarratIQ_Master_Implementation_Checklist.md` — Stage 1, task 1.1, subtasks 5 and 6 |
| **Evidence basis** | Commands run on the live pod on 2026-07-24. Every claim below cites the command that produced it. |

## 1. Summary

The pod has exactly **two data-bearing filesystems**. Everything else mounted is NVIDIA driver bind-mounts and container metadata (`/etc/hosts`, `/etc/resolv.conf`, `/etc/hostname`).

| Mount point | Source | Type | Size | Used | Role |
|---|---|---|---|---|---|
| `/workspace` | `mfs#eu-se-1.runpod.net:9421` | `fuse` (MooseFS) | 756 T | 604 T (80%) | **Network volume** |
| `/` | `overlay` | `overlayfs` | 100 G | 16 G (16%) | Container layer |

**If you are about to stop this pod, read §8 first.** The PostgreSQL data directory is on the container layer.

## 2. The network volume

```
$ findmnt -no SOURCE,FSTYPE,TARGET,OPTIONS /workspace
mfs#eu-se-1.runpod.net:9421[/podvolumes/d12dtfg81gbe/2e5wiiphzhzf14]  fuse  /workspace
    rw,nosuid,nodev,relatime,user_id=0,group_id=0,allow_other
```

| Property | Value |
|---|---|
| **Mount point** | `/workspace` |
| **Backing service** | MooseFS (`mfs`) over the network, host `eu-se-1.runpod.net`, port `9421` |
| **Volume path** | `/podvolumes/d12dtfg81gbe/2e5wiiphzhzf14` |
| **Region** | `eu-se-1` |
| **Filesystem type** | `fuse` / `fuseblk` |
| **Mount options** | `rw,nosuid,nodev,relatime,user_id=0,group_id=0,allow_other` |
| **Block size** | 65536 |
| **Capacity** | 756 T total, 152 T available (shared pool, not a per-pod quota) |
| **Inodes** | 1,421,583,556 total; 23% used |

There is **no `/runpod-volume` mount** on this pod — `ls -ld /runpod-volume` returns *No such file or directory*. The network volume is mounted directly at `/workspace`. See §6.

The reported 756 T capacity is the size of RunPod's shared storage pool, not space reserved for this pod. **Do not use the 152 T "available" figure for capacity planning.**

## 3. The container layer

```
$ findmnt -no SOURCE,FSTYPE,TARGET /
overlay  overlay  /

$ stat -f -c 'type=%T bsize=%s' /
type=overlayfs bsize=4096
```

| Property | Value |
|---|---|
| **Mount point** | `/` |
| **Type** | `overlay` / `overlayfs` |
| **Capacity** | 100 G total, 85 G available, 16% used |
| **Inodes** | 750,147,136 total; 1% used |

This is the Docker overlay filesystem, assembled from the container image layers plus a writable upper directory.

## 4. Storage layout — what lives where

Produced with `df --output=source,fstype <path>` for each path.

| Path | Filesystem | Contents | Size |
|---|---|---|---|
| `/workspace/narratiq-ai` | **network volume** | Application repository | 3.2 G |
| `/workspace/models` | **network volume** | Model weights (Qwen2.5-7B-Instruct, BGE-M3, GOT-OCR2_0) | 22 G |
| `/workspace/backups` | **network volume** | Database backups (`pg_dump` archives, checksums, role definitions) | 2.0 M |
| `/workspace/narratiq-ai/backend/uploads` | **network volume** | Author uploads — `audio/`, `ocr/` | — |
| `/var/lib/postgresql/16/main` | **container layer** | **PostgreSQL data directory — every manuscript** | — |
| `/tmp/narratiq-logs` | **container layer** | Service logs (`vllm.log`, `backend.log`, `frontend.log`) | — |
| `/root` | **container layer** | Root home directory | — |

`/workspace/models` and `/workspace/narratiq-ai` are **real directories on the volume**, not symlinks (`ls -ld` shows `drwxrwxrwx`, no link target).

Upload paths are configured relative to the backend working directory (`.env.example:164-165`: `UPLOAD_DIR_AUDIO=uploads/audio`, `UPLOAD_DIR_OCR=uploads/ocr`) and therefore resolve under `/workspace/narratiq-ai/backend/` — on the network volume — provided the backend is started from `backend/` as `CLAUDE.md` requires.

### 4.1 The database is on the container layer

```
$ ps -o args= -C postgres | head -1
/usr/lib/postgresql/16/bin/postgres -D /var/lib/postgresql/16/main \
    -c config_file=/etc/postgresql/16/main/postgresql.conf

$ df --output=source,fstype /var/lib/postgresql/16/main
overlay overlay
```

PostgreSQL's data directory is on the **container layer**, not the network volume. Every story, chapter, character, note and embedding lives there.

This is the single most consequential fact in this document. The durability of the manuscripts is governed by the container layer, not by the network volume — the opposite of what the `/workspace`-centric layout suggests at a glance. The backup procedure (`scripts/backup_database.sh`) writes to `/workspace/backups`, which is a *different* filesystem from the data it protects; that separation is deliberate and should be preserved.

**The consequences for a pod stop are deliberately not analysed here** — that is checklist task 1.1, subtask 6.

## 5. Filesystem characteristics

### 5.1 The network volume does not enforce `chmod` — *Verified*

The FUSE mount accepts `chmod`, returns success, and then forces group and other bits to mirror the owner bits. Measured on 2026-07-24:

| Requested | Actual on `/workspace` | Actual on `/` (overlay) |
|---|---|---|
| `600` | `666` | `600` |
| `700` | `777` | — |
| `640` | `666` | `640` |
| `000` | `000` | — |

Only a full revocation (`000`) is honoured. Any file with permissions on the volume is world-readable and world-writable.

**Implications.**

- Restrictive file permissions are not an available control on `/workspace`. Code that sets them will appear to succeed. `scripts/backup_database.sh` sets them anyway and then verifies and warns when the mode does not take, rather than reporting a protection it did not achieve.
- This is systemic, not specific to backups: `backend/.env` — which holds `SECRET_KEY` and the database password — is already mode `666` on this volume, as is the entire repository.
- Confidentiality for anything on `/workspace` must come from encryption or from access control at the pod/account level, not from file modes.
- The container currently has a single user (`uid=0(root)`), so this has no in-container consequence today. It matters for whatever else can reach the volume.

### 5.2 Ownership is fixed at the mount — *Verified*

The mount carries `user_id=0,group_id=0`. All paths report `uid=0 gid=0` regardless of the creating process. `nosuid` and `nodev` are set.

### 5.3 Persistence — *Expected, not Verified*

`/workspace` is a RunPod network volume, and network volumes are designed to persist independently of the pod's container lifecycle. That is the **expected** behaviour and is why models and the repository are stored there.

**It has not been observed on this pod.** No pod stop has been performed and diffed since this document was written. Until it has, treat persistence as an expectation carried over from the RunPod storage model, not as a property of this deployment that anyone has checked.

Task 1.1 subtask 6 records the per-path expectation; task 1.5 supplies the observation that can upgrade these labels from Expected to Verified.

## 6. Discrepancy with `runpod-deployment.md` — recorded, not resolved

`docs/operations/runpod-deployment.md:45-55` describes a different arrangement from the one measured here:

> **Production (Network Volume).** Attach a RunPod Network Volume so the ~17 GB of weights persists.
> ```
> ln -s /runpod-volume/models /workspace/models
> ```

That procedure assumes the network volume mounts at `/runpod-volume` and is symlinked into `/workspace`. On this pod:

- `/runpod-volume` **does not exist**;
- `/workspace` **is itself** the network volume mount;
- `/workspace/models` is a real directory, not a symlink;
- the deployment document's stated model footprint (~17 GB) does not match the measured 22 G.

Following the deployment document as written would produce a broken symlink on this pod. This is **recorded, not fixed** — `runpod-deployment.md` is owned by checklist task 1.9, and cross-document reconciliation is Stage 11.

## 7. Reproducing these findings

```bash
findmnt -no SOURCE,FSTYPE,TARGET,OPTIONS /workspace     # network volume identity
findmnt -no SOURCE,FSTYPE,TARGET /                      # container layer
df -h /workspace /                                      # capacity
df -i /workspace /                                      # inodes
stat -f -c 'type=%T bsize=%s' /workspace /              # filesystem type
ps -o args= -C postgres | head -1                       # PGDATA location
df --output=source,fstype /var/lib/postgresql/16/main   # which filesystem holds it
findmnt -rno SOURCE,FSTYPE,TARGET                       # full mount list
```

To re-measure the `chmod` behaviour of §5.1, create a scratch file on `/workspace`, `chmod` it, and compare `stat -c %a` against what was requested. Remove the scratch file afterwards.

---

## 8. Pod-stop survival

> ### ✅ Evidence status: **Verified 2026-09-21** — a real manual pod restart was performed and observed
>
> **A manual pod restart was performed by the author on 2026-09-21** (pod `ckqiafptcbpcuq`, volume
> `/podvolumes/lcm4qhpt4448/ckqiafptcbpcuq`, unchanged across the restart). §8.2 below is updated from
> the prediction table to the actually-observed outcome. See §8.6 for the full account, including the
> unexpected-empty-database guard's behaviour, which had never been exercised end-to-end against a real
> restart before this event.

### 8.1 The model this prediction rests on

A RunPod pod stop releases the container. On start, the container filesystem is reconstructed from the image, so **writes made to `/` after the pod was created are not part of the image and are not reconstructed**. A network volume is a separate service with its own lifecycle and is re-attached to the new container.

Applied to §4: **paths under `/workspace` are predicted to survive; everything else is predicted to be lost.**

### 8.2 Survival table

| Path | Filesystem | Prediction | Evidence | If lost |
|---|---|---|---|---|
| `/workspace/narratiq-ai` | network volume | **Survives** | **Verified 2026-09-21** | Application code — would need re-clone |
| `/workspace/models` (22 G) | network volume | **Survives** | **Verified 2026-09-21** — all 4 model dirs present, correct sizes, no re-download triggered | 22 G re-download |
| `/workspace/backups` | network volume | **Survives** | **Verified 2026-09-21** — both pre-restart dumps present, SHA-256 unchanged | **The only database backup** |
| `/workspace/narratiq-ai/backend/uploads` | network volume | **Survives** | Predicted (unobserved) — not exercised this pass, no upload fixture existed | Author audio and OCR uploads |
| `/workspace/narratiq-ai/frontend/node_modules` (2.9 G) | network volume | **Survives** | **Verified 2026-09-21** — `npm install` step skipped (`node_modules — OK`) | `npm install` re-run |
| `/workspace/narratiq-ai/frontend/.next` (195 M) | network volume | **Survives** | **Verified 2026-09-21** (directory present pre-rebuild; the startup script unconditionally wipes and rebuilds it regardless of survival, so this is not evidence of use, only of presence) | `npm run build` re-run |
| `/workspace/narratiq-ai/backend/.env` | network volume | **Survives** | **Verified 2026-09-21** — `SECRET_KEY` confirmed byte-identical pre/post-restart via SHA-256 of the file line (safe comparison, plaintext never displayed) | `SECRET_KEY` — all sessions invalidated |
| **`/var/lib/postgresql/16/main`** | **container layer** | **LOST** | **Verified 2026-09-21** — `psql` absent post-restart, fresh empty cluster on re-install, 0 tables/0 rows, `alembic none` | **Every manuscript, chapter, character, note and embedding** |
| `/usr/local/lib/python3.11/dist-packages` | container layer | **LOST** | **Verified 2026-09-21** — vLLM, PyTorch cu128, transformers, numpy, backend packages all reported "not found"/reinstalled by the script | vLLM, PyTorch, FastAPI, sentence-transformers, faster-whisper, Alembic — all re-installed |
| PostgreSQL 16 binaries + pgvector (apt) | container layer | **LOST** | **Verified 2026-09-21** — `psql` not found, PGDG repo re-added, `postgresql-16 + pgvector` re-installed from scratch | Re-installed by apt |
| Node.js runtime (apt) | container layer | **LOST** | **Verified 2026-09-21** — `node` not found, Node 20.20.2 re-installed | Re-installed by apt |
| vLLM `ovis.py` patch | container layer | **LOST** | **Verified 2026-09-21** (implied — vLLM package itself was reinstalled from scratch, so the patch step reapplied against a fresh copy) | Re-applied by the startup script |
| `/tmp/narratiq-logs` | container layer | **LOST** | **Verified 2026-09-21** — directory absent pre-run, recreated by the script | Diagnostic history for this pod session |
| `/root` | container layer | Not directly tested | Not exercised this pass — no stray `/root` state was tracked before the restart to diff against | Shell history and any stray files |

Filesystem assignments in this table were already **measured**, not predicted, before this pass — each was confirmed with `df --output=source,fstype`. **The survival column is now Verified for every row actually exercised by this restart** (2026-09-21, checklist task 1.5 / the persistence-recovery verification session), superseding the earlier "Predicted (unobserved)" status throughout. `/root` and the uploads directory were not exercised and remain unverified, honestly.

### 8.3 The consequence that matters

**The database is destroyed by a pod stop, and its only backup is on a different filesystem that survives.** (Confirmed 2026-09-21 — see §8.6. Previously stated as a prediction; no longer.)

The recovery therefore depends on two things being true at once: that `/workspace` persists as expected, and that the backup in `/workspace/backups` is restorable. Both are now **proven**: the volume's persistence across a real restart, and the archive's restorability — test-restored on 2026-07-24 with exact row/content/embedding matches (checklist task 1.1), and again on 2026-09-21 into a disposable scratch database with exact row-count matches and the fixture intact (§8.6).

That asymmetry is why the checklist requires the backup to be copied off-pod before stopping the pod. A single wrong assumption about volume persistence would still lose every manuscript on a pod where no off-pod copy exists — this pass verified the on-pod half of that risk, not the off-pod one.

**Plan for the restore, do not hope to avoid it.** Task 1.5's line *"Confirm the database survived; if not, restore from task 1.1"* reads as a contingency; on this layout it is the expected path — and on 2026-09-21 it is exactly what happened.

### 8.4 What has to be re-created after a start

`start-narratiq.sh` is self-healing for container-layer losses. Every re-install step is guarded by a **presence check**, not by a first-run marker, so each guard re-triggers when the container layer comes back without its packages:

| Step | Guard | Behaviour after a stop |
|---|---|---|
| Node.js | `command -v node` (`:53`) | Absent → re-installs |
| PostgreSQL 16 + pgvector | `command -v psql` (`:63`) | Absent → re-installs |
| vLLM | `pip show vllm` version compare (`:97`) | Absent → re-installs |
| PyTorch cu128 | version check (`:112`) | Re-installs as needed |
| `ovis.py` patch | `grep AutoConfig.register` (`:124-126`) | Re-applies; the `sed` skips lines already carrying `exist_ok` |
| `npm install` | `[ ! -d node_modules ]` (`:205`) | `node_modules` is on the volume → **skipped**, correctly |
| `/tmp/narratiq-logs` | `mkdir -p` (`:21`) | Re-created unconditionally |

**Not handled by the startup script — the database.** Re-installing `postgresql-16` produces a **fresh, empty cluster**. `start-narratiq.sh` then runs `Base.metadata.create_all()` and `alembic upgrade head`, which build the *schema* — and leave every table empty. **Restoring the data from `/workspace/backups` is a manual step that nothing automates.** A stack that comes up "healthy" with zero manuscripts is the expected appearance of this failure.

One secondary risk: if Node.js re-installs at a different major version, the surviving `node_modules` on the volume may not match it. The guard skips `npm install` because the directory exists. If the frontend misbehaves after a restart, remove `frontend/node_modules` and re-run the startup script.

### 8.5 How to confirm these predictions — for task 1.5

Run immediately after the first start, before anything else writes:

```bash
# 1. Did the volume come back with its contents?
ls -la /workspace/ /workspace/backups/ /workspace/models/
cd /workspace/backups && sha256sum -c *.sha256      # backups intact?

# 2. Did the database survive, or is it a fresh empty cluster?
su postgres -c "psql -Atqc \"SELECT datname FROM pg_database ORDER BY 1\""
su postgres -c "psql -d narratiq -Atqc 'SELECT count(*) FROM stories'" 2>&1
#    → 1 (or the then-current count) = survived
#    → 0, or 'database narratiq does not exist' = lost, restore required

# 3. Did the container layer reset as predicted?
python3 -c "import vllm" 2>&1        # ModuleNotFoundError = reset as predicted
ls /tmp/narratiq-logs 2>&1           # absent/empty = reset as predicted

# 4. Confirm the mount is the same volume
findmnt -no SOURCE,FSTYPE,TARGET /workspace
```

Then update §8.2's Evidence column from *Predicted (unobserved)* to **Verified 〈date〉** for each row the results confirm — and **correct any row the results contradict**, rather than leaving the prediction standing. *(Done — see §8.6.)*

### 8.6 2026-09-21 — First real pod restart: observed behaviour

The author manually restarted the RunPod pod (pod `ckqiafptcbpcuq`, same network volume before and after — `findmnt` confirmed identical `/podvolumes/lcm4qhpt4448/ckqiafptcbpcuq`). This is the first time §8's predictions were checked against an actual restart rather than reasoned about. **Every prediction in §8.2 that was exercised held exactly as stated.**

**What survived (network volume):** the repository, all four model directories (Qwen2.5-7B-Instruct, BGE-M3, GOT-OCR2.0, faster-whisper-large-v3-turbo, ~22 G, no re-download triggered), `frontend/node_modules` (`npm install` skipped), both pre-restart backup dumps (`narratiq-20260921T105252Z.dump`, `narratiq-20260921T124933Z.dump`) with unchanged SHA-256 checksums, and `backend/.env` — **`SECRET_KEY` was confirmed byte-identical pre- and post-restart via a SHA-256 comparison of the file line, never displaying the plaintext.**

**What was lost (container layer):** `psql`, `node`, vLLM, PyTorch, transformers and every other pip/apt package were all absent and had to be reinstalled by `start-narratiq.sh` from a bare container. PostgreSQL came back as a **fresh, empty cluster** — no `narratiq` database existed until the script created one, and it held 0 tables until migrations ran.

**The unexpected-empty-database guard (`scripts/startup_backup.sh`), exercised end-to-end for the first time against a real restart, behaved exactly as designed:**
1. First `start-narratiq.sh` run: vLLM loaded, Postgres was installed and started, the `narratiq` role/database/`vector` extension were (re)created, but the database held 0 tables and 0 rows.
2. The guard detected this, found the newest valid prior backup (`narratiq-20260921T124933Z.dump`, correctly preferring it over the older `…T105252Z` one, by mtime), and **aborted before `Base.metadata.create_all()` or `alembic upgrade head` ran** — printing the exact restore command and requiring an explicit `NARRATIQ_ACKNOWLEDGE_EMPTY_RESTART=yes-start-empty-intentionally` to proceed empty on purpose. No dump was written (correctly — an empty-database dump would misrepresent itself as protection), and `BACKUP-RECORD.txt` recorded the abort.
3. **Manual recovery**, following the guard's own printed procedure: checksum-verified `narratiq-20260921T124933Z.dump`, then `pg_restore --clean --if-exists --no-owner --role=narratiq` into the now-provisioned empty `narratiq` database. (Two non-fatal warnings — `must be owner of extension vector` on the archive's `DROP EXTENSION`/`COMMENT` statements — are expected: the extension was created by the `postgres` superuser during setup, not by `narratiq`, so `narratiq` cannot drop/recreate it via `--clean`. The extension was already present and functional; `pg_restore` reported "errors ignored on restore: 2" and proceeded.) Row counts, Alembic head (`0016`), and the restored fixture data all matched the pre-restart state exactly.
4. Re-running `start-narratiq.sh` with data now present: the guard correctly recognised a fresh backup existed and no schema change was pending, skipped writing a redundant backup, and let `alembic upgrade head` run as a no-op. Backend, frontend and the periodic backup loop all started cleanly.
5. **The older, independently-protected backup (`narratiq-20260921T105252Z.dump`) was never touched** — read, never written — throughout the entire recovery, confirmed by an unchanged SHA-256 both before and after.
6. A **new post-recovery backup** (`narratiq-20260921T132802Z.dump`) was taken via the deliberate `scripts/backup_database.sh` path, checksum-verified, and restore-tested into a disposable scratch database (`narratiq_scratch_verify`) with matching row counts and the fixture intact — then the scratch database was dropped.
7. The temporary verification fixture (one user, one story, two chapters — self-labelled `[TEMP VERIFICATION FIXTURE - safe to delete]`) was deleted from the live database. A full scan of every `story_id`/`user_id`-bearing table in the schema confirmed **zero orphan rows** before and after.

**One cosmetic false alarm, not a real defect:** `start-narratiq.sh`'s own sanity check reported "Active next-server processes: 5 (expected: 1)" immediately after the frontend came up. Investigation found this is `pgrep -fc "next-server"` matching its own invocation's command-line text when the literal string `"next-server"` appears as a quoted argument in nearby shell invocations — a pre-existing artifact of the pattern-match approach, not a real duplicate-process condition. Steady-state process inspection confirmed exactly one `next-server` process, one listener on port 3000, and a healthy `HTTP 200` response throughout. Not fixed as part of this verification pass (out of scope — noted here for anyone chasing the same false alarm).

**Full post-recovery service verification, all confirmed live:** PostgreSQL 16.15 + pgvector 0.8.6; Alembic at head `0016`; vLLM 0.9.2 serving `Qwen/Qwen2.5-7B-Instruct` on 1× NVIDIA A40 (44.4 GB, `tensor_parallel=1`, `max_model_len=8192`) with a real completion returned; BGE-M3 loaded and producing correct 1024-dim normalized embeddings; backend `/api/health` reporting `ok`/`ready`/`ready` locally and via the external proxy; frontend reachable locally and externally (`HTTP 200`); pgvector self-distance query returning `0`; exactly one periodic-backup-loop process running (4 h interval, 12-backup retention).
