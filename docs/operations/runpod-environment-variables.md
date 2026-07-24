# RunPod Environment Variable Recovery

**Purpose:** determine exactly which environment variables must be entered by hand in the RunPod
**Environment Variables** UI before running `start-narratiq.sh`, after a long gap away from the project.

**Method:** static analysis of the repository at commit `9827587` (branch `main`), plus read-only Git
history. No service was started, no model downloaded, no migration run. Where a conclusion could not
be verified by reading alone, it is marked **UNVERIFIED** and listed in
[§11 Uncertainties](#11-uncertainties--runtime-verification-required).

---

## 1. Executive summary

**The short answer: you almost certainly need to enter *fewer* variables than you remember — and one
of the variables you probably still have set is actively breaking the application.**

Three findings drive everything else in this document.

### 1.1 `start-narratiq.sh` is now self-bootstrapping

It generates or force-overwrites every operationally important variable itself. As of commit
`c3ec72d` (11 June 2026) it **overwrites `DATABASE_URL`, `VLLM_BASE_URL`, `VLLM_MODEL_NAME` and
`CORS_ORIGINS` in `backend/.env` on every single run**. Setting those in RunPod is redundant.

### 1.2 RunPod environment variables silently override `backend/.env`

`backend/config.py:238` uses `pydantic-settings` with `model_config = {"env_file": ".env"}`.
In `pydantic-settings` 2.3.0 the source precedence is:

```
init args  >  OS environment variables  >  .env file  >  field defaults
```

So a value left in the RunPod UI **wins over** the value `start-narratiq.sh` writes to
`backend/.env`. This is not theoretical:

> If `VLLM_BASE_URL=http://127.0.0.1:8001/v1` is still set in your RunPod pod — and
> `docs/operations/runpod-deployment.md` Step 5 told you to set exactly that — then the backend will target port
> **8001** while vLLM actually listens on **9001**. The script will report success, `/api/health`
> will return `"status": "ok"`, and every AI feature will fail with a 503.

The backend does **not** refuse to start when vLLM is unreachable (`backend/main.py:235-241` catches
the failure and continues in degraded mode), so this failure is quiet.

**Recommended action: delete `VLLM_BASE_URL` from the RunPod UI entirely.** Do not "fix" it to 9001 —
let the script and the code default supply it.

### 1.3 Copying `.env.example` to `backend/.env` currently crashes the backend

`docs/operations/runpod-deployment.md` Step 5 Option B instructs `cp .env.example backend/.env`. That produces a
backend that will not start. `.env.example:31` contains `TROCR_MODEL_ID=...`, a key left over from the
TrOCR → GOT-OCR2.0 migration that is no longer a field on the `Settings` class. `pydantic-settings`
`BaseSettings` defaults to `extra='forbid'` and `config.py:238` does not override it, so an
undeclared key with a non-empty value raises at import:

```
pydantic_core._pydantic_core.ValidationError: 1 validation error for Settings
trocr_model_id
  Extra inputs are not permitted [type=extra_forbidden, ...]
```

**VERIFIED** by loading an unmodified copy of `backend/config.py` against an unmodified copy of
`.env.example` in an isolated temporary directory. Nothing in the repository was touched.

Note the asymmetry, which is why this was never noticed:
- An undeclared key in the **`.env` file** with a value → **crash**.
- An undeclared key in the **`.env` file** with an empty value (`TROCR_MODEL_PATH=`, `HF_TOKEN=`) →
  ignored, no crash (`pydantic-settings` drops empty dotenv values).
- An undeclared key in the **OS environment** (i.e. the RunPod UI) → ignored, no crash.

So `HF_TOKEN` set in the RunPod UI is harmless even though `Settings` has no such field.
`.env.example` has been corrected as part of this task.

### 1.4 Bottom line

| Question | Answer |
|---|---|
| Variables that are strictly **required** in RunPod | **None.** The script generates everything mandatory. |
| Variables **worth** setting | **1–3**, depending on your situation (see §3). |
| Variables you likely set originally | **5–6 of the 10** in `docs/operations/runpod-deployment.md` Step 5 (see §4). |
| Variables that are now **harmful** if still set | `VLLM_BASE_URL` (and any stale `CORS_ORIGINS`, `NEXT_PUBLIC_API_URL`). |

---

## 2. How the variables reach the application

Understanding this chain is the whole task, because the same variable name means different things
depending on where it is set.

```
┌─ RunPod UI "Environment Variables" ──────────────────────────────┐
│  Injected into the pod's shell at container start.               │
│  Inherited by every process, including start-narratiq.sh.        │
└───────────────────────────┬──────────────────────────────────────┘
                            │ inherited
                            ▼
┌─ start-narratiq.sh shell ────────────────────────────────────────┐
│  Reads:   RUNPOD_POD_ID (:29), STT_PARTIAL_MODEL (:263),         │
│           HF_TOKEN (via scripts/download_models.sh)              │
│  Writes:  backend/.env      (SECRET_KEY, DATABASE_URL,           │
│                              VLLM_BASE_URL, VLLM_MODEL_NAME,     │
│                              CORS_ORIGINS)                       │
│           frontend/.env.local (NEXT_PUBLIC_API_URL)              │
│  Exports: VLLM_BASE_URL, VLLM_MODEL_NAME, MODEL_BASE_DIR,        │
│           CORS_ORIGINS   (:499-502 — overrides inherited values  │
│                           for the uvicorn child only)            │
└───────────────┬──────────────────────────┬───────────────────────┘
                │                          │
                ▼                          ▼
┌─ uvicorn (backend) ─────────┐  ┌─ next build (frontend) ─────────┐
│ pydantic-settings resolves: │  │ NEXT_PUBLIC_API_URL is INLINED  │
│  env vars > .env > defaults │  │ into the JS bundle at BUILD time│
└─────────────────────────────┘  └─────────────────────────────────┘
```

### 2.1 Precedence — which source wins

**Backend (`pydantic-settings` 2.3.0):**

| Rank | Source | Notes |
|---|---|---|
| 1 | OS environment variable | Includes anything set in the RunPod UI, and anything `export`ed by the script |
| 2 | `backend/.env` | Written by `start-narratiq.sh` |
| 3 | Field default in `config.py` | |

Two consequences worth internalising:

- **Via `start-narratiq.sh`,** the script's own `export` at `:499-502` runs *after* it inherits the
  RunPod values, so for `VLLM_BASE_URL`, `VLLM_MODEL_NAME`, `MODEL_BASE_DIR` and `CORS_ORIGINS` the
  script's value wins for the backend it launches. A stale RunPod value is masked in this path.
- **Running `uvicorn main:app` by hand** (as `docs/operations/how-to-run.md` Terminal 2 describes) does *not* get
  those exports. The RunPod value is inherited directly and beats `backend/.env`. **This is where a
  stale `VLLM_BASE_URL=…:8001/v1` bites.**

That difference explains a confusing symptom: *the app works when started with the script, but AI
features fail when the backend is restarted manually.*

**`.env` file location is relative.** `config.py:238` specifies `env_file: ".env"`, resolved against
the **current working directory**. The backend must be started from `backend/`. Started from the repo
root, `backend/.env` is silently not found and the app falls back to OS env vars plus defaults — which
means no `SECRET_KEY` and an immediate `ValidationError`.

**Frontend (Next.js):** `NEXT_PUBLIC_API_URL` is the only variable the entire frontend reads
(`frontend/lib/api.ts:3`). Next.js loads `.env.local` via `@next/env`, which does **not** overwrite
variables already present in the real environment. So a `NEXT_PUBLIC_API_URL` set in the RunPod UI
**overrides** the `frontend/.env.local` that `start-narratiq.sh:577-579` writes. Because the value is
inlined into the JS bundle at build time, a stale pod ID there produces a frontend that is baked to
call a dead URL. **UNVERIFIED** — this follows from documented `@next/env`/dotenv behaviour but was
not executed here. **Do not set `NEXT_PUBLIC_API_URL` in RunPod.**

---

## 3. Confirmed required variables

### 3.1 Strictly required: none

There is exactly one mandatory setting in the whole application — `SECRET_KEY`
(`config.py:33`, no default; validator at `config.py:229-236` rejects anything under 32 characters).
`start-narratiq.sh:361-367` generates one automatically when `backend/.env` does not already contain
it. So a pod with **zero** environment variables set will boot successfully.

### 3.2 Recommended: 1–3 variables

| Variable | Set it when | Why |
|---|---|---|
| `SECRET_KEY` | You want logins to survive a re-clone | See §3.3 |
| `HF_TOKEN` | Downloads are rate-limited, or you use gated models | See §3.4 |
| `MODEL_BASE_DIR` | You use a RunPod **Network Volume** | See §3.5 |

### 3.3 `SECRET_KEY`

| Field | Value |
|---|---|
| Required | No — generated if absent |
| Why | Signs JWTs. `config.py:33`, consumed in `backend/routers/auth.py` |
| Read by | `backend/config.py:33` (application code) |
| Read by `start-narratiq.sh`? | No — it greps the **file** `backend/.env`, never the environment |
| Generated / overwritten? | **Generated only if `backend/.env` lacks the key** (`:361-367`). Append-only; never overwritten |
| Secret? | **Yes.** Never commit or paste into docs |
| Format | ≥32 chars. Generate: `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| Example | `SECRET_KEY=<64-hex-characters>` |
| Effect of changing | **Invalidates every active JWT session.** All users must log in again. Account rows are unaffected |

**The reason to set this in RunPod:** `backend/.env` is gitignored (`.gitignore`), so a fresh
`git clone` has no `.env`. The script then generates a *new* `SECRET_KEY`, invalidating all existing
logins. Setting `SECRET_KEY` in the RunPod UI makes it survive re-clones — and because OS env beats
`.env`, your value wins over the generated one.

> **Interaction worth knowing:** if `SECRET_KEY` is set in RunPod *and* `backend/.env` does not exist,
> the script still generates and writes a second key to `backend/.env`. The RunPod value takes
> precedence, so the generated one is inert — confusing, but harmless.

### 3.4 `HF_TOKEN`

| Field | Value |
|---|---|
| Required | No |
| Why | Hugging Face auth for model downloads — raises rate limits, enables gated repos |
| Read by | `scripts/download_models.sh:15,23,25` — **shell script only** |
| Read by application code? | **No.** There is no `hf_token` field on `Settings` |
| Read by `start-narratiq.sh`? | Indirectly — inherited by `download_models.sh` at `:283`. The script itself only prints a tip at `:278` |
| Generated / overwritten? | Never |
| Secret? | **Yes** |
| Format | `hf_` + alphanumerics |
| Example | `HF_TOKEN=hf_your_token_here` |
| Effect of changing | None on data. Only affects future downloads |

All three primary models (Qwen2.5-7B-Instruct, BGE-M3, GOT-OCR2.0) are **public** — the token is a
convenience, not a requirement. It matters most on first boot, when ~17 GB is pulled.

### 3.5 `MODEL_BASE_DIR`

| Field | Value |
|---|---|
| Required | No — defaults to `/workspace/models` |
| Why | Root directory for model weights |
| Read by | `config.py:37` (application), `scripts/download_models.sh:14`, `scripts/verify_runpod_setup.sh:10`, `start.sh:21` |
| Read by `start-narratiq.sh`? | **No — and this is the catch.** The script hardcodes `MODEL_DIR="/workspace/models"` at `:16` and then `export`s `MODEL_BASE_DIR="$MODEL_DIR"` at `:501`, **overwriting** whatever you set |
| Generated / overwritten? | Overwritten in the script's own shell at `:501` |
| Secret? | No |
| Format | Absolute path |
| Example | `MODEL_BASE_DIR=/runpod-volume/models` |
| Effect of changing | Points the app at a different weights directory. Wrong value → hard `RuntimeError` at startup (`main.py:178-186`) |

> **Important limitation.** Setting `MODEL_BASE_DIR=/runpod-volume/models` in the RunPod UI **will not
> work with `start-narratiq.sh`**, because `:16` and `:501` hardcode `/workspace/models`. Network
> Volume users must either symlink `/workspace/models → /runpod-volume/models` or edit the script.
> Editing the script is out of scope for this documentation-only task; the contradiction is recorded
> in §10.

---

## 4. Most Likely Original RunPod Variables

You recall entering roughly five or six variables. The only artefact that ever told you what to paste
is **`docs/operations/runpod-deployment.md` Step 5 → "Option A — Set as RunPod pod environment variables
(recommended)"** (lines 96–107), which lists **ten**. Git history shows that block is byte-identical
across every revision and has not been touched since `3496e0c` (5 June 2026) — it predates the
self-bootstrapping script entirely.

Ranking within that block by how likely you were to actually type each one:

| Rank | Variable | Confidence | Evidence |
|---|---|---|---|
| 1 | `SECRET_KEY` | **Confirmed** | Shown as a fill-in placeholder `<generate a random 64-char hex string>`, and named first under Option B's "Edit at minimum". Between `31da24e` and `2b8543d` it was the only setting with no working default — the app could not start without it |
| 2 | `MODEL_BASE_DIR` | **Highly likely** | Second item in "Edit at minimum". The Network Volume section (§"Production") explicitly instructs setting it to `/runpod-volume/models`, which no script does for you |
| 3 | `HF_TOKEN` | **Highly likely** | Shown as a fill-in placeholder `<your HF token, optional for public models>`. Never set by any script — only ever inherited |
| 4 | `VLLM_BASE_URL` | **Highly likely** | In the Step 5 block with a concrete value. **This is the damaging one** — the doc hands out `http://127.0.0.1:8001/v1`, which became wrong at commit `b0f64be` when the default moved to 9001 |
| 5 | `VLLM_MODEL_NAME` | **Possible** | Immediately adjacent to `VLLM_BASE_URL` in the block; typically pasted as a pair |
| 6 | `CORS_ORIGINS` | **Possible** | Not in the Step 5 block, but Step 11 ("Expose the RunPod Port") separately instructs updating `CORS_ORIGINS` with the pod proxy URL |
| — | `GPU_MEMORY_UTILIZATION`, `MAX_MODEL_LEN`, `BGE_DEVICE`, `BACKEND_HOST`, `BACKEND_PORT` | **Unlikely** | Present in the Step 5 block, but `.env.example:40-41` tells you in capitals to "LEAVE THESE COMMENTED OUT to let start.sh auto-detect". A reader following both documents would skip them |
| — | `DATABASE_URL` | **Unlikely** | Appears nowhere in Step 5. Postgres arrived later (`ffd1cb7`), and the script has written this value itself ever since |

**Best reconstruction of your original set (5–6 entries):**

```
SECRET_KEY, MODEL_BASE_DIR, HF_TOKEN, VLLM_BASE_URL, VLLM_MODEL_NAME  [, CORS_ORIGINS]
```

**Alternative scenario:** if you pasted the Step 5 block wholesale rather than selectively, you would
have **ten** entries, not five or six. Your recollection of "five or six" argues for selective entry,
but check the actual UI — it is the ground truth and will settle this in seconds.

### 4.1 What to do with them now

| Original variable | Action today | Reason |
|---|---|---|
| `SECRET_KEY` | **Keep** | Preserves existing logins across re-clones |
| `HF_TOKEN` | **Keep** | Still genuinely used by `download_models.sh` |
| `MODEL_BASE_DIR` | **Keep only if** using a Network Volume — and see the §3.5 caveat | Script overrides it anyway |
| `VLLM_BASE_URL` | **DELETE** | Stale `8001` silently breaks all AI on a manual backend restart |
| `VLLM_MODEL_NAME` | **Delete** | Script force-overwrites it every run |
| `CORS_ORIGINS` | **Delete** | Script rebuilds it from the live pod ID every run; a stale pod ID here causes CORS failures |

---

## 5. Variables generated or overwritten by `start-narratiq.sh`

**Do not set these in RunPod.** Anything you put here is either ignored or actively harmful.

| Variable | File written | Line | Behaviour | Idempotent? |
|---|---|---|---|---|
| `SECRET_KEY` | `backend/.env` | 361-367 | Generated **only if absent** from the file. Never overwritten | Yes — stable across runs |
| `DATABASE_URL` | `backend/.env` | 433-434 | **Force-overwritten** every run: `sed -i '/^DATABASE_URL=/d'` then append | Yes |
| `VLLM_BASE_URL` | `backend/.env` | 440,443 | **Force-overwritten** → `http://127.0.0.1:9001/v1` | Yes |
| `VLLM_MODEL_NAME` | `backend/.env` | 441,444 | **Force-overwritten** → `Qwen/Qwen2.5-7B-Instruct` | Yes |
| `CORS_ORIGINS` | `backend/.env` | 442,445 | **Force-overwritten** from live `RUNPOD_POD_ID` | Yes |
| `NEXT_PUBLIC_API_URL` | `frontend/.env.local` | 577-579 | **File truncated and rewritten** (`cat > .env.local`) | Yes |
| `MODEL_BASE_DIR` | (shell export only) | 501 | Exported as `/workspace/models`, overriding any inherited value | Yes |

The hardcoded database credentials are `narratiq` / `narratiq` on `localhost:5432`
(`start-narratiq.sh:418-419,434`). These are local-only and never exposed off the pod, but they are
not a secret you should rely on. A second hardcoded copy of the same URL sits in
`backend/alembic.ini:7`; it is overridden at runtime by `backend/migrations/env.py:15`, which reads
`settings.database_url`.

---

## 6. Optional variables with safe defaults

All 56 `Settings` fields are environment variables (`FIELD_NAME` uppercase, no prefix). Every one
except `SECRET_KEY` has a working default. **Do not add these to RunPod unless you have a specific
reason** — the smallest sufficient set is the goal.

Most likely to be worth overriding:

| Variable | Default | When to change |
|---|---|---|
| `JWT_EXPIRE_MINUTES` | `10080` (7 days) | Set `60` in production for short-lived tokens |
| `LOG_FORMAT` | `text` | Set `json` for a log aggregator |
| `LOG_LEVEL` | `INFO` | `DEBUG` when diagnosing |
| `BGE_DEVICE` | `cpu` | `cuda` only with spare VRAM above `GPU_MEMORY_UTILIZATION` |
| `WHISPER_DEVICE` / `WHISPER_COMPUTE_TYPE` | `cpu` / `int8` | `cuda` / `float16` with spare VRAM |
| `VOICE_AGENT_ENABLED` | `True` | `False` to disable the voice agent entirely (kill-switch) |
| `BG_AI_CONCURRENCY` / `EMBEDDING_CONCURRENCY` | `3` / `2` | Tune background load |
| `MAX_AUDIO_UPLOAD_MB` / `MAX_OCR_UPLOAD_MB` / `MAX_MANUSCRIPT_UPLOAD_MB` | `100` / `50` / `25` | Adjust upload caps |
| `RATE_LIMIT_*` | see `config.py:87-92` | Six independent limits |
| `VOICE_ADMIN_EMAILS` | `[]` | JSON list; grants access to `/api/voice/analytics/*` |

Full field-by-field listing: `backend/config.py:30-238`.

Format notes: list-typed fields (`CORS_ORIGINS`, `VOICE_ADMIN_EMAILS`) must be **JSON**, e.g.
`CORS_ORIGINS=["https://abc123-3000.proxy.runpod.net","http://localhost:3000"]`. Booleans accept
`true`/`false`.

---

## 7. Obsolete, unused, or duplicated variables

| Variable | Status | Evidence |
|---|---|---|
| `TROCR_MODEL_ID` | **Obsolete and harmful in `.env`** | Project migrated to GOT-OCR2.0 (`config.py:43`). Not a `Settings` field → `extra_forbidden` crash. Removed from `.env.example` by this task |
| `TROCR_MODEL_PATH` | **Obsolete** | Same migration. Harmless only because its value is empty |
| `SLOWAPI_STORAGE_URI` | **Never read by any code** | Appears only in prose: `config.py:86`, `middleware/rate_limit.py:6`, `CLAUDE.md:200,236`. The limiter is built with no storage argument at `middleware/rate_limit.py:67` (`Limiter(key_func=get_remote_address)`). Rate limiting is unconditionally in-memory; CLAUDE.md's "zero code changes" Redis claim is false |
| `HF_HUB_ENABLE_HF_TRANSFER` | **Never read in this repo** | Only in comments (`requirements.setup.txt:13`, `docs/operations/runpod-deployment.md:131`). Would be honoured by the `huggingface_hub` library if exported, but nothing here sets it |
| `HUGGING_FACE_HUB_TOKEN`, `HF_HOME`, `TRANSFORMERS_CACHE` | **Zero occurrences** | Note `start-narratiq.sh:264` hardcodes `$HOME/.cache/huggingface/hub/…` rather than honouring `HF_HOME` |
| `VLLM_PORT` | **Shell-only; no `Settings` field** | `start.sh:25` (default 8001), `verify_runpod_setup.sh:14` (default 8001). `start-narratiq.sh:17` hardcodes 9001 and does not read the variable |
| `GOT_OCR_MODEL_PATH` | **Shell-only; no `Settings` field** | `verify_runpod_setup.sh:13` only |
| `BACKEND_DIR` | **Shell-only** | `start.sh:27`. `start-narratiq.sh:14` hardcodes it |
| `GPU_MEMORY_UTILIZATION`, `TENSOR_PARALLEL_SIZE`, `MAX_MODEL_LEN` | **Vestigial for the current script** | `Settings` fields and `start.sh` overrides, but `start-narratiq.sh:311-315` auto-detects from GPU count and passes CLI flags directly to vLLM — it never reads these |
| `BACKEND_HOST`, `BACKEND_PORT` | **Vestigial for the current script** | `start-narratiq.sh:505-506` passes `--host`/`--port` as CLI flags |
| `NARRATIQ_URL`, `FRONTEND_URL`, `BACKEND_URL` | **Test-only** | `backend/scripts/smoke_test.py:33`, `scripts/smoke_test_browser.js:18-19` |
| `NCCL_P2P_DISABLE`, `NCCL_SHM_DISABLE` | **Set, never read by the app** | `start-narratiq.sh:318`, consumed by NCCL itself |

---

## 8. What `start-narratiq.sh` does, step by step

Rerunning the script is **safe**. Every step is idempotent. It is designed for a brand-new pod and
skips completed work on later runs.

| Step | Lines | Checks / installs | Reads | Writes | On missing value | Idempotent |
|---|---|---|---|---|---|---|
| Detect pod URLs | 29-36 | — | `RUNPOD_POD_ID` | — | Falls back to `local` → `http://localhost:*` | Yes |
| 1a Node.js | 53-60 | `command -v node`; installs Node 20 | — | — | — | Yes — skipped if present |
| 1b PostgreSQL | 63-83 | `command -v psql`; adds PGDG repo, installs PG16 + pgvector | — | `/etc/apt/sources.list.d/pgdg.list` | — | Yes |
| 1c vLLM | 97-104 | Version equality against `0.9.2` | — | — | — | Yes |
| 1d PyTorch | 109-118 | Requires a `cu128` build; force-reinstalls 2.7.0 | — | — | — | Yes |
| 1e Patches | 123-140 | `sed` guards on `ovis.py` and `prometheus_fastapi_instrumentator` | — | site-packages | — | Yes — only patches unguarded lines |
| 1f NumPy | 143-151 | Pins `≤2.2` | — | — | — | Yes |
| 1g transformers | 154-161 | Pins `<5.0` | — | — | — | Yes |
| 1f Backend deps | 165-201 | ~25 pip packages + HF tooling | — | — | — | Yes |
| 1g npm | 205-215 | Only when `node_modules` absent | — | `node_modules` | — | Yes |
| 2 Models | 227-288 | `config.json` presence for Qwen / BGE-M3 / GOT-OCR2.0; `model.bin` for Whisper; HF cache for partial STT | `STT_PARTIAL_MODEL` (default `base`), `HF_TOKEN` (via `download_models.sh`) | `$MODEL_DIR/*`, HF cache | Downloads (~17 GB, 10–20 min) | Yes — skips existing files |
| 3 vLLM launch | 296-336 | Kills old process, clears torch compile cache, autodetects GPU count | — | `$LOG_DIR/vllm.log` | TP/len/util derived from GPU count | Yes |
| 4 vLLM health | 342-355 | Polls `/health` for 6 min | — | — | **Exits 1** | Yes |
| **4b `SECRET_KEY`** | 358-367 | `grep -q "^SECRET_KEY=" backend/.env` | the **file**, not the env | `backend/.env` (append) | **Generates a 64-hex key** | Yes — stable once written |
| **4c PostgreSQL** | 370-480 | Starts cluster; creates role + DB + `vector` extension; verifies credentials | — | `backend/.env` | Creates everything | Yes — `CREATE` errors suppressed, `ALTER USER` re-applies password |
| ↳ `DATABASE_URL` | 433-434 | — | — | `backend/.env` | **Force-overwrite** | Yes |
| ↳ vLLM + CORS | 440-446 | — | `RUNPOD_POD_ID` (via `FRONTEND_PUBLIC_URL`) | `backend/.env` | **Force-overwrite** ×3 | Yes |
| ↳ Schema | 467-480 | `Base.metadata.create_all()` then `alembic upgrade head` | `DATABASE_URL` | Postgres | — | Yes |
| 5 Backend | 486-529 | Kills old uvicorn, waits for port, polls `/api/health` 90 s | — | `$LOG_DIR/backend.log` | **Warns only** — continues | Yes |
| ↳ exports | 499-502 | — | — | shell env | Overrides inherited values | Yes |
| 6 Frontend | 535-616 | Kills every `next-server`, frees port 3000, wipes `.next`, rebuilds, starts one server | — | `frontend/.env.local`, `.next` | **Exits 1** if build fails | Yes |
| Done | 621-635 | Prints URLs, log paths, PIDs | — | — | — | — |

### 8.1 Points of special note

- **`SECRET_KEY` checks the file, not the environment** (`:361`). A `SECRET_KEY` present only in the
  RunPod UI does not prevent generation of a second key into `backend/.env`. Precedence still gives
  your RunPod value the win, so the generated one is inert.
- **Hugging Face auth** flows RunPod UI → script env → `download_models.sh:15`. The script itself
  only echoes a tip at `:278`.
- **Persistent volume paths are not honoured** — `MODEL_DIR` is hardcoded at `:16`. See §3.5 and §10.
- **Frontend URL is build-time.** `:577-579` writes `.env.local`, then `:590` rebuilds. Changing the
  backend URL later requires a **rebuild**, not a restart.
- **CORS is rebuilt from the live pod ID** each run (`:445`), so it self-heals when the pod ID
  changes — unless a stale `CORS_ORIGINS` in the RunPod UI overrides it on a manual restart.
- **Rate limits, upload caps and logging** are never touched by the script. Pure `config.py` defaults
  unless you override them.
- **Voice-agent variables** are never touched by the script, with one exception: `STT_PARTIAL_MODEL`
  is *read* at `:263` to decide which small Whisper model to pre-stage. It is never written.

---

## 9. RunPod copy-paste blocks

### 9.1 Enter these in the RunPod Environment Variables UI

```env
SECRET_KEY=replace_with_64_hex_chars_from_secrets_token_hex_32
HF_TOKEN=hf_your_token_here
```

> `SECRET_KEY` — optional but recommended; keeps logins working across re-clones.
> Generate with `python3 -c "import secrets; print(secrets.token_hex(32))"`.
> `HF_TOKEN` — optional; all required models are public. Raises download rate limits.
>
> **A pod with neither variable set will still start correctly.**

### 9.2 Optional

```env
# Only when using a RunPod Network Volume — see the caveat in §3.5:
# start-narratiq.sh hardcodes /workspace/models and will override this.
MODEL_BASE_DIR=/runpod-volume/models

# Production hardening
JWT_EXPIRE_MINUTES=60
LOG_FORMAT=json
LOG_LEVEL=INFO

# Only with spare VRAM above GPU_MEMORY_UTILIZATION
BGE_DEVICE=cuda
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=float16

# Disable the voice agent entirely
VOICE_AGENT_ENABLED=false
```

### 9.3 Do not manually add these

`start-narratiq.sh` generates or force-overwrites all of the following. Setting them in RunPod is at
best ignored and at worst silently breaks the application.

```text
DATABASE_URL          # generated: postgresql+psycopg2://narratiq:narratiq@localhost:5432/narratiq
VLLM_BASE_URL         # force-overwritten each run → http://127.0.0.1:9001/v1
                      # ⚠ a stale 8001 here breaks all AI on a manual backend restart — DELETE IT
VLLM_MODEL_NAME       # force-overwritten each run → Qwen/Qwen2.5-7B-Instruct
CORS_ORIGINS          # rebuilt from the live RUNPOD_POD_ID each run
                      # ⚠ a stale pod ID here causes CORS failures — DELETE IT
NEXT_PUBLIC_API_URL   # written to frontend/.env.local and baked in at build time
                      # ⚠ a value here overrides the file and bakes a dead URL — DELETE IT
RUNPOD_POD_ID         # injected by RunPod automatically — never set by hand
GPU_MEMORY_UTILIZATION / TENSOR_PARALLEL_SIZE / MAX_MODEL_LEN
                      # auto-detected from GPU count; passed as CLI flags to vLLM
BACKEND_HOST / BACKEND_PORT
                      # passed as CLI flags to uvicorn
TROCR_MODEL_ID / TROCR_MODEL_PATH
                      # obsolete (GOT-OCR2.0 migration). TROCR_MODEL_ID in backend/.env
                      # crashes the backend with extra_forbidden
SLOWAPI_STORAGE_URI   # never read by any code — rate limiting is always in-memory
```

---

## 10. Port contradiction — documented, not fixed

Per the constraints of this task, **no code or script was modified**. The contradiction is recorded
here and must be resolved separately.

| Source | Port | Status |
|---|---|---|
| `start-narratiq.sh:17` | **9001** | **Authoritative** — the startup path actually in use |
| `backend/config.py:59` | **9001** | Consistent with the script |
| `start.sh:25` | 8001 | **Legacy** — superseded, last touched 5 June 2026 |
| `scripts/verify_runpod_setup.sh:14` | 8001 | Legacy — will report a **false failure** against a working 9001 stack |
| `.env.example:34-35` | 8001 | **Corrected by this task** (documentation file) |
| `docs/operations/runpod-deployment.md` | 8001 | **Corrected by this task** (documentation file) |
| `CLAUDE.md:242` | claims `config.py` defaults to 8001 | **Corrected by this task** — the default became 9001 at commit `b0f64be` |

**Which path is authoritative:** `start-narratiq.sh` (port 9001). `start.sh` is abandoned; its last
commit is `3496e0c` (5 June 2026), before the Postgres migration, before `SECRET_KEY` became
mandatory, and before the port changed.

**Recommended follow-up (separate task, requires code changes — not performed here):**
1. Align `start.sh:25` and `scripts/verify_runpod_setup.sh:14` to 9001, or delete `start.sh`.
2. Decide whether `start-narratiq.sh:16` should honour `MODEL_BASE_DIR` instead of hardcoding
   `/workspace/models`, so Network Volumes work as `docs/operations/runpod-deployment.md` promises.
3. Either implement `SLOWAPI_STORAGE_URI` in `middleware/rate_limit.py:67` or remove the claim from
   `CLAUDE.md`.

---

## 11. Uncertainties — runtime verification required

Nothing in this document was validated against a running system. The following need confirmation on a
provisioned pod.

| # | Item | Confidence | How to verify |
|---|---|---|---|
| 1 | Which variables are *actually* still in your RunPod UI | **Unknown — ground truth** | Open the pod's Environment Variables panel and read them. This settles §4 immediately |
| 2 | Next.js `.env.local` vs OS env precedence for `NEXT_PUBLIC_API_URL` | **UNVERIFIED** — follows from documented `@next/env` behaviour | After `npm run build`, grep the bundle: `grep -ro "proxy.runpod.net" frontend/.next/static \| head` |
| 3 | Whether the app runs at all | **Unverified** | No service was started. Nothing here asserts the application works |
| 4 | `MODEL_BASE_DIR` override behaviour on a Network Volume | Inferred from `:16`/`:501` | Set it, run the script, then check `echo $MODEL_BASE_DIR` and where weights land |
| 5 | `pydantic-settings` precedence (env > `.env`) | **High** — documented behaviour of 2.3.0, matches the script's export-and-write belt-and-braces design | `VLLM_BASE_URL=http://127.0.0.1:9999/v1 python3 -c "from config import settings; print(settings.vllm_base_url)"` from `backend/` |
| 6 | `extra_forbidden` crash from `.env.example` | **VERIFIED** — reproduced against an unmodified copy of `config.py` in an isolated directory | Already confirmed; `.env.example` has been corrected |
| 7 | Whether existing user accounts survive | Inferred | Accounts live in Postgres and are unaffected by `SECRET_KEY`; only JWT sessions are invalidated |

---

## 12. Full recovery workflow

Commands are given for reference. **None were executed as part of this task.**

### 1. Create the RunPod pod
Template: a PyTorch/CUDA image on Ubuntu 22.04. The script installs everything else.

### 2. Configure storage and GPU
- **GPU:** one card with ≥24 GB VRAM runs Qwen2.5-7B at `TP=1`, `max-model-len 8192`.
  Two or four cards raise this automatically (`start-narratiq.sh:311-315`; `TP` must divide the
  model's 4 KV heads, so 1, 2 or 4 — never 3).
- **Disk:** ≥60 GB. Models alone are ~17 GB; `verify_runpod_setup.sh:158` requires 30 GB free.
- **Exposed HTTP ports:** `8000` (backend) and `3000` (frontend). Port `9001` (vLLM) is internal.
- **Network Volume:** optional — read the §3.5 caveat first.

### 3. Add environment variables
Paste the §9.1 block. **Delete any pre-existing `VLLM_BASE_URL`, `VLLM_MODEL_NAME`, `CORS_ORIGINS`
or `NEXT_PUBLIC_API_URL` entries left over from an earlier deployment.**

### 4. Open the workspace
Use the pod's **Connect** button → Jupyter terminal or the web terminal.

### 5. Configure GitHub access
Never place a password or token in a clone URL — it is written to shell history and to
`.git/config`. Use one of:

```bash
# Option A — GitHub CLI (interactive, recommended)
gh auth login

# Option B — SSH key
ssh-keygen -t ed25519 -C "runpod"
cat ~/.ssh/id_ed25519.pub    # add this to GitHub → Settings → SSH and GPG keys
ssh -T git@github.com        # verify

# Option C — credential helper, entered at the interactive prompt only
git config --global credential.helper store
```

For a public repository, plain HTTPS needs no authentication at all.

### 6. Clone the repository
```bash
cd /workspace
git clone https://github.com/ARSHITHbabu/Author_Narratiq.git narratiq-ai
# SSH alternative:
# git clone git@github.com:ARSHITHbabu/Author_Narratiq.git narratiq-ai
```

### 7. Confirm the repository path
**This matters.** `start-narratiq.sh:14-15` hardcodes `/workspace/narratiq-ai`. Cloning to any other
directory makes the script fail immediately.

```bash
ls /workspace/narratiq-ai/start-narratiq.sh   # must exist
```

If the directory is named differently, symlink rather than editing the script:
```bash
ln -s /workspace/Author_Narratiq /workspace/narratiq-ai
```

### 8. Run the startup script
```bash
cd /workspace/narratiq-ai
bash start-narratiq.sh
```
First run: 20–40 minutes (dependency installs plus ~17 GB of model downloads).
Later runs: 3–5 minutes. Rerunning is safe.

### 9. Monitor the logs
```bash
tail -f /tmp/narratiq-logs/vllm.log
tail -f /tmp/narratiq-logs/backend.log
tail -f /tmp/narratiq-logs/frontend.log
```

### 10. Verify vLLM
```bash
curl http://localhost:9001/health
curl -s http://localhost:9001/v1/models | python3 -m json.tool   # expect Qwen/Qwen2.5-7B-Instruct
```

### 11. Verify the backend
```bash
curl -s http://localhost:8000/api/health | python3 -m json.tool
```
Expect `"status": "ok"`, `"vllm": "ready"`, `"bge_m3": "ready"`.

> `"vllm": "unavailable"` with everything else healthy is the signature of the stale-`VLLM_BASE_URL`
> problem in §1.2 — check the RunPod UI. Confirm what the backend actually resolved:
> ```bash
> cd /workspace/narratiq-ai/backend
> python3 -c "from config import settings; print(settings.vllm_base_url)"
> ```

### 12. Verify the frontend
```bash
curl -so /dev/null -w "%{http_code}\n" http://localhost:3000   # expect 200 or 3xx
```

### 13. Retrieve the public URLs
The script prints them on completion. To rebuild them yourself:
```bash
echo "Frontend: https://${RUNPOD_POD_ID}-3000.proxy.runpod.net"
echo "Backend : https://${RUNPOD_POD_ID}-8000.proxy.runpod.net"
```
Open the frontend URL in a browser. If the browser console shows calls to a *different* pod's URL,
a stale `NEXT_PUBLIC_API_URL` was baked into the bundle — remove it from the RunPod UI and rerun the
script so the frontend is rebuilt.

---

*Generated by static analysis of commit `9827587`. No application code, shell script, or Git history
was modified. No service was started.*
