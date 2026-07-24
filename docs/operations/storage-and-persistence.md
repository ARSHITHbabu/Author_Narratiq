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

> ### ⚠ Evidence status: **Predicted (unobserved)**
>
> **No pod stop has been performed.** Every survival statement in this section is a prediction derived from the measured filesystem layout (§4) and RunPod's documented container/volume model. **Nothing here has been observed on this pod.**
>
> Checklist task 1.5 performs the first start after a stop and can convert these predictions into observations. Until it does, treat every row as a working assumption — and where the assumption is optimistic, assume the pessimistic case instead.

### 8.1 The model this prediction rests on

A RunPod pod stop releases the container. On start, the container filesystem is reconstructed from the image, so **writes made to `/` after the pod was created are not part of the image and are not reconstructed**. A network volume is a separate service with its own lifecycle and is re-attached to the new container.

Applied to §4: **paths under `/workspace` are predicted to survive; everything else is predicted to be lost.**

### 8.2 Survival table

| Path | Filesystem | Prediction | Evidence | If lost |
|---|---|---|---|---|
| `/workspace/narratiq-ai` | network volume | **Survives** | Predicted (unobserved) | Application code — would need re-clone |
| `/workspace/models` (22 G) | network volume | **Survives** | Predicted (unobserved) | 22 G re-download |
| `/workspace/backups` | network volume | **Survives** | Predicted (unobserved) | **The only database backup** |
| `/workspace/narratiq-ai/backend/uploads` | network volume | **Survives** | Predicted (unobserved) | Author audio and OCR uploads |
| `/workspace/narratiq-ai/frontend/node_modules` (2.9 G) | network volume | **Survives** | Predicted (unobserved) | `npm install` re-run |
| `/workspace/narratiq-ai/frontend/.next` (195 M) | network volume | **Survives** | Predicted (unobserved) | `npm run build` re-run |
| `/workspace/narratiq-ai/backend/.env` | network volume | **Survives** | Predicted (unobserved) | `SECRET_KEY` — all sessions invalidated |
| **`/var/lib/postgresql/16/main`** | **container layer** | **LOST** | Predicted (unobserved) | **Every manuscript, chapter, character, note and embedding** |
| `/usr/local/lib/python3.11/dist-packages` | container layer | **LOST** | Predicted (unobserved) | vLLM, PyTorch, FastAPI, sentence-transformers, faster-whisper, Alembic — all re-installed |
| PostgreSQL 16 binaries + pgvector (apt) | container layer | **LOST** | Predicted (unobserved) | Re-installed by apt |
| Node.js runtime (apt) | container layer | **LOST** | Predicted (unobserved) | Re-installed by apt |
| vLLM `ovis.py` patch | container layer | **LOST** | Predicted (unobserved) | Re-applied by the startup script |
| `/tmp/narratiq-logs` | container layer | **LOST** | Predicted (unobserved) | Diagnostic history for this pod session |
| `/root` | container layer | **LOST** | Predicted (unobserved) | Shell history and any stray files |

Filesystem assignments in this table are **measured**, not predicted — each was confirmed with `df --output=source,fstype`. It is only the survival column that is unobserved.

### 8.3 The consequence that matters

**The database is predicted to be destroyed by a pod stop, and its only backup is on a different filesystem that is predicted to survive.**

The recovery therefore depends on two things being true at once: that `/workspace` persists as expected, and that the backup in `/workspace/backups` is restorable. The second is **proven** — the archive was test-restored on 2026-07-24 with exact row, content and embedding matches (checklist task 1.1). The first is **not**.

That asymmetry is why the checklist requires the backup to be copied off-pod before task 1.3 stops anything. Until that copy exists, a single wrong assumption about volume persistence loses every manuscript.

**Plan for the restore, do not hope to avoid it.** Task 1.5's line *"Confirm the database survived; if not, restore from task 1.1"* reads as a contingency; on this layout it is the expected path.

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

Then update §8.2's Evidence column from *Predicted (unobserved)* to **Verified 〈date〉** for each row the results confirm — and **correct any row the results contradict**, rather than leaving the prediction standing.

