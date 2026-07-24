# Documentation Recovery Changelog

Record of every documentation change made during the RunPod environment-variable recovery task,
against commit `9827587`.

**No application code was modified.** No Python, TypeScript, router, service, model, migration,
prompt, component, shell script, port, or package version was touched. Every change below is in a
Markdown or `.example` file.

**Verification legend**

| Mark | Meaning |
|---|---|
| **Confirmed** | Verified directly against code, a file, or read-only Git history, with a cited reference |
| **Inferred** | Reasoned from evidence but not directly executed or observed |

---

## Summary

| File | Type | Changes |
|---|---|---|
| `docs/RUNPOD_ENVIRONMENT_VARIABLE_RECOVERY.md` | **new** | Primary deliverable |
| `docs/DOCUMENTATION_RECOVERY_CHANGELOG.md` | **new** | This file |
| `.env.example` | rewritten | Removed a key that crashes the backend; corrected DB and port guidance |
| `RUNPOD_DEPLOYMENT.md` | rewritten | Rebuilt around `start-narratiq.sh`; corrected env var instructions |
| `HOW_TO_RUN.md` | rewritten | Added DB, env var and working-directory requirements |
| `README.md` | rewritten | Removed SQLite and AI-placeholder claims; corrected feature status |
| `CLAUDE.md` | 8 targeted edits | Corrected router paths, port, migrations, startup behaviour, slowapi |

---

## 1. `.env.example` — rewritten

### 1.1 Removed `TROCR_MODEL_ID` and `TROCR_MODEL_PATH`

- **Old:** `TROCR_MODEL_PATH=` (line 25) and `TROCR_MODEL_ID=microsoft/trocr-large-handwritten` (line 31)
- **New:** both removed; a header comment explains why
- **Evidence:** neither is a field on `Settings` (`backend/config.py:30-238`). The project migrated to
  GOT-OCR2.0 (`config.py:43`, commit `3496e0c`). `pydantic-settings` `BaseSettings` defaults to
  `extra="forbid"` and `config.py:238` does not override it.
- **Impact:** `RUNPOD_DEPLOYMENT.md` Step 5 Option B instructed `cp .env.example backend/.env`, which
  produced a backend that would not start:
  ```
  ValidationError: 1 validation error for Settings
  trocr_model_id
    Extra inputs are not permitted [type=extra_forbidden, ...]
  ```
- **Status: Confirmed.** Reproduced by loading an unmodified copy of `backend/config.py` against an
  unmodified copy of `.env.example` in an isolated temporary directory. The corrected file was then
  verified to load successfully. Nothing in the repository was modified during either check.
- **Also confirmed:** only **non-empty** undeclared values raise. `TROCR_MODEL_PATH=` (empty) and
  `HF_TOKEN=` (empty) are dropped by `pydantic-settings` and are harmless — which is why this was
  never noticed. Undeclared **OS environment** variables are always ignored, so `HF_TOKEN` in the
  RunPod UI is safe.

### 1.2 `DATABASE_URL` — SQLite → PostgreSQL

- **Old:** `DATABASE_URL=sqlite:///./narratiq.db`
- **New:** `DATABASE_URL=postgresql+psycopg2://narratiq:narratiq@localhost:5432/narratiq`, with a note
  that `start-narratiq.sh` force-overwrites it
- **Evidence:** `backend/requirements.txt:31` — "The app uses PostgreSQL 16 + pgvector exclusively.
  SQLite is no longer used." `backend/database.py:12-16` warns on SQLite; `backend/main.py:221-226`
  raises `RuntimeError` when the pgvector self-check fails. `start-narratiq.sh:433-434` writes the
  PostgreSQL URL. `config.py:32` still *defaults* to SQLite — that default is now unreachable in
  practice but was left untouched (code change).
- **Status: Confirmed.**

### 1.3 `VLLM_BASE_URL` — commented out

- **Old:** `VLLM_BASE_URL=http://127.0.0.1:8001/v1` (active)
- **New:** commented out, with a warning that a stale 8001 value silently breaks all AI
- **Evidence:** `config.py:59` defaults to 9001; `start-narratiq.sh:17,443` uses 9001 and
  force-overwrites the key. Commented out rather than corrected to 9001 because the script supplies
  it and the code default is already right — setting it can only introduce drift.
- **Status: Confirmed.**

### 1.4 Added the missing Phase 2 / Phase 3 variables

- **Old:** 12 variables, none of the hardening or voice settings
- **New:** all 56 `Settings` fields represented, commented out with defaults and guidance
- **Evidence:** `backend/config.py:30-238`
- **Status: Confirmed.**

### 1.5 Added precedence, path and `extra="forbid"` warnings

- **New:** header block documenting `env vars > .env > defaults`, the relative `env_file` path, and
  the `extra="forbid"` failure mode
- **Evidence:** `config.py:238`; `pydantic-settings==2.3.0` (`requirements.txt:11`)
- **Status: Confirmed** (precedence order is documented `pydantic-settings` behaviour and is
  corroborated by `start-narratiq.sh:499-502`, which writes `.env` *and* exports the same values —
  a belt-and-braces pattern that only makes sense if exports win).

### 1.6 Documented non-`Settings` variables

- **New:** trailing section for `HF_TOKEN`, `RUNPOD_POD_ID`, `NEXT_PUBLIC_API_URL`,
  `SLOWAPI_STORAGE_URI` — explaining that none belong in `backend/.env`
- **Evidence:** `scripts/download_models.sh:15,23,25`; `start-narratiq.sh:29`;
  `frontend/lib/api.ts:3`; `middleware/rate_limit.py:67`
- **Status: Confirmed.**

---

## 2. `RUNPOD_DEPLOYMENT.md` — rewritten

### 2.1 Step 5 "Set Environment Variables" — 10 variables → 2

- **Old (lines 96-107):** a block instructing the reader to paste ten variables into the RunPod UI:
  `MODEL_BASE_DIR`, `VLLM_BASE_URL` (**8001**), `VLLM_MODEL_NAME`, `GPU_MEMORY_UTILIZATION`,
  `MAX_MODEL_LEN`, `BGE_DEVICE`, `BACKEND_HOST`, `BACKEND_PORT`, `SECRET_KEY`, `HF_TOKEN`
- **New:** at most two (`SECRET_KEY`, `HF_TOKEN`), both optional, plus an explicit "do not set" list
  and an instruction to **delete** any stale `VLLM_BASE_URL`
- **Evidence:** `start-narratiq.sh` generates `SECRET_KEY` (`:361-367`) and force-overwrites
  `DATABASE_URL` (`:433`), `VLLM_BASE_URL` (`:440,443`), `VLLM_MODEL_NAME` (`:441,444`),
  `CORS_ORIGINS` (`:442,445`). GPU values are auto-detected at `:311-315` and passed as CLI flags;
  host/port are CLI flags at `:505-506`.
- **Significance:** this block is the origin of the user's forgotten variables. Read-only Git history
  shows it is byte-identical across every revision and was last touched in `3496e0c` (5 June 2026) —
  before the Postgres migration (`ffd1cb7`), before `SECRET_KEY` became mandatory (`2b8543d`), and
  before the port changed (`b0f64be`).
- **Status: Confirmed.**

### 2.2 Option B `cp .env.example backend/.env` removed

- **Old:** instructed copying `.env.example`, which crashed the backend (see §1.1)
- **New:** removed; `.env.example` itself has been corrected
- **Status: Confirmed.**

### 2.3 vLLM port 8001 → 9001 throughout

- **Old:** eight references to 8001, including the architecture diagram, the exposed-ports list, and
  every health-check command
- **New:** 9001 throughout, plus a dedicated "Port contradiction" section naming
  `start-narratiq.sh:17` as authoritative and `start.sh:25` / `verify_runpod_setup.sh:14` as legacy
- **Evidence:** `start-narratiq.sh:17`, `config.py:59`; changed in commit `b0f64be`
- **Status: Confirmed.** Per the task constraint, `start.sh` and `verify_runpod_setup.sh` were
  **not** edited — the contradiction is documented only.

### 2.4 Startup path — manual sequence → `start-narratiq.sh`

- **Old:** Steps 4–7 walked through `pip install -r requirements.vllm.txt`, manual model downloads
  and `bash start.sh`
- **New:** `bash start-narratiq.sh` as the single path; the manual three-terminal sequence is kept as
  a debugging fallback
- **Evidence:** `start-narratiq.sh` installs all dependencies (`:53-215`) and downloads models
  (`:227-288`). `start.sh` last modified 5 June 2026 and still targets SQLite-era assumptions.
- **Status: Confirmed.**

### 2.5 Added: PostgreSQL requirement, repo-path requirement, secure GitHub auth

- **New:** PostgreSQL 16 + pgvector stated as required with SQLite explicitly unsupported; the
  `/workspace/narratiq-ai` hardcoded-path requirement with a symlink workaround; GitHub
  authentication via `gh auth login` or SSH rather than tokens in clone URLs
- **Evidence:** `start-narratiq.sh:14-15`; `main.py:221-226`
- **Status: Confirmed.**

### 2.6 Added: `MODEL_BASE_DIR` Network Volume caveat

- **Old:** "point `MODEL_BASE_DIR` to it (e.g. `/runpod-volume/models`)"
- **New:** same, plus a warning that `start-narratiq.sh` overrides it, and a symlink workaround
- **Evidence:** `start-narratiq.sh:16` hardcodes `MODEL_DIR="/workspace/models"`; `:501` exports
  `MODEL_BASE_DIR="$MODEL_DIR"`, overriding any inherited value
- **Status: Confirmed** by reading; **Inferred** as to end-to-end Network Volume behaviour, which was
  not exercised.

### 2.7 Rewrote troubleshooting

- **New:** entries for `vllm: unavailable` (stale `VLLM_BASE_URL`), `extra_forbidden`,
  `SECRET_KEY must be at least 32 characters` (wrong working directory), and
  `pgvector query path self-check FAILED`. Removed the `flash-attn` entry — not in any requirements
  file.
- **Status: Confirmed.**

---

## 3. `HOW_TO_RUN.md` — rewritten

### 3.1 Added the PostgreSQL step

- **Old:** Terminal 2 ran `uvicorn` directly. No mention of a database anywhere in the file.
- **New:** `pg_ctlcluster 16 main start`, `pg_isready`, and `alembic upgrade head` before `uvicorn`
- **Evidence:** `start-narratiq.sh:377-480`
- **Status: Confirmed.**

### 3.2 Added the `cd backend` requirement

- **Old:** `cd /workspace/narratiq-ai/backend` was shown but not explained
- **New:** called out as mandatory, with the exact failure it prevents
- **Evidence:** `config.py:238` — `env_file: ".env"` is relative to the working directory; with
  `backend/.env` unloaded, `secret_key` has no value and the validator at `config.py:229-236` raises
- **Status: Confirmed.**

### 3.3 Corrected startup failure semantics

- **Old:** no description of which failures are fatal
- **New:** a table — missing weights and broken pgvector are hard `RuntimeError`s; unreachable vLLM
  is a warning and the backend continues degraded
- **Evidence:** `main.py:178-186`, `:221-226`, `:235-241`
- **Status: Confirmed.**

### 3.4 Added environment-variable guidance

- **Old:** none
- **New:** the two optional RunPod variables, plus an instruction to delete stale `VLLM_BASE_URL`
- **Status: Confirmed.**

### 3.5 Corrected `Next.js 13.x.x` → `14.2.3`

- **Evidence:** `frontend/package.json` — `"next": "14.2.3"`
- **Status: Confirmed.**

### 3.6 Added build-time semantics for `NEXT_PUBLIC_API_URL`

- **New:** changing it requires `npm run build`; a RunPod-set value overrides `.env.local`
- **Evidence:** `frontend/lib/api.ts:3` is the only `process.env` read in the entire frontend;
  `start-narratiq.sh:577-579` writes `.env.local` and `:590` rebuilds
- **Status:** build-time inlining is **Confirmed**; the claim that an OS variable overrides
  `.env.local` is **Inferred** from documented `@next/env`/dotenv behaviour and is flagged as
  requiring runtime verification in the recovery report §11.

### 3.7 Corrected the vLLM `tensor-parallel-size` guidance

- **Old:** default example used `--tensor-parallel-size 2`
- **New:** default `1`, with a table by GPU count and the 4-KV-head divisibility constraint
- **Evidence:** `start-narratiq.sh:311-315`; `config.py:9-13`
- **Status: Confirmed.**

---

## 4. `README.md` — rewritten

### 4.1 Removed the "AI Model Placeholders" section

- **Old:** "All AI functionality is connected via stub functions… Each function is marked with
  `# MODEL_PLACEHOLDER`", followed by a 12-row table of placeholders and a code sample showing how to
  "connect vLLM when ready"
- **New:** replaced with the real architecture; `ai_service.py` calls vLLM directly
- **Evidence:** a repository-wide search for `MODEL_PLACEHOLDER` returns **zero** matches.
  `ai_service.py:36-45` constructs a real `AsyncOpenAI` client; `:99-216` are real
  `chat.completions.create` calls.
- **Status: Confirmed.**

### 4.2 SQLite → PostgreSQL + pgvector

- **Old:** "Backend: FastAPI, SQLAlchemy, SQLite (dev)"; quick start ran `uvicorn` with no database;
  "Production DB: PostgreSQL (swap DATABASE_URL in .env)"
- **New:** PostgreSQL 16 + pgvector stated as required
- **Evidence:** `backend/requirements.txt:31`; `main.py:221-226`
- **Status: Confirmed.**

### 4.3 Corrected feature status

- **Old:** "Phase 2 (Not Yet Built — post-MVP)" listing plot hole detection, character consistency
  analysis, emotion flow graph and EPUB/Kindle export
- **New:** the first three are marked built, with only EPUB/Kindle listed as unbuilt
- **Evidence:** `routers/plot_holes.py:29` + `components/plot-holes/PlotHolesPanel.tsx`;
  `routers/analysis.py:51` (`/emotional-arc`) + `components/analysis/EmotionalArcPanel.tsx`;
  `routers/characters.py:1197` (voice consistency). `routers/export.py:46-51` accepts only `docx`
  and `pdf`, raising 400 otherwise — so EPUB/Kindle is genuinely absent.
- **Status: Confirmed.**

### 4.4 Corrected the project structure

- **Old:** 9 routers; a 3-column editor layout
- **New:** 23 routers grouped by domain; 7 author workspaces; `middleware/`, `startup/`,
  `migrations/`, `services/voice/`
- **Evidence:** `backend/routers/` contains 23 modules, all registered at `main.py:319-345`;
  `frontend/lib/registries/workspaces.ts:24-32`
- **Status: Confirmed.**

### 4.5 Corrected the model list

- **Old:** "Translation: Helsinki-NLP opus-mt + Qwen2.5-7B"
- **New:** translation is performed by Qwen; no Helsinki-NLP model exists in the project
- **Evidence:** `ai_service.py:728` (`translate_text`) calls `_complete`. No Helsinki reference
  anywhere; `scripts/download_models.sh` fetches only Qwen, BGE-M3 and GOT-OCR2.0.
- **Status: Confirmed.**

### 4.6 Added Known Issues and Documentation sections

- **New:** the five highest-priority known issues, and an index of the documentation set
- **Evidence:** `NarratIQ_Project_Recovery_Report.docx`, `issues_i_found_phase{1,2}.docx`, plus the
  code references cited in each entry
- **Status:** code-level items **Confirmed**; the QA-document items are **Inferred** — neither issues
  document carries a status field, so they are reported-but-unverified.

---

## 5. `CLAUDE.md` — 8 targeted edits

### 5.1 Backend startup behaviour

- **Old:** "Backend will refuse to start if vLLM is unreachable."
- **New:** full lifespan order; only missing weights and a broken pgvector path are hard failures;
  unreachable vLLM degrades
- **Evidence:** `main.py:178-186`, `:221-226`, `:235-241`
- **Status: Confirmed.**

### 5.2 Three non-existent router files

- **Old:** Key Files listed `backend/routers/voice.py`, `continuation.py`, `outline.py`
- **New:** corrected to `writing_tools.py:61` (continuation), `writing_tools.py:145` (outline) and
  `characters.py:1197,1293` (voice consistency), with a warning that `voice_agent.py` is a different
  feature
- **Evidence:** none of the three files exist in `backend/routers/`
- **Status: Confirmed.** A duplicate `characters.py` row introduced while editing was removed.

### 5.3 `config.py` port claim

- **Old:** "`vllm_base_url` defaults to port 8001 but the running instance uses **9001**"
- **New:** defaults to 9001, matching the script; changed in `b0f64be`
- **Evidence:** `config.py:59`
- **Status: Confirmed.**

### 5.4 "Config Gotchas" rewritten

- **Old:** described the port mismatch as a live configuration trap requiring `.env` intervention
- **New:** states no action is needed, names the two legacy files that still say 8001, and adds three
  genuine gotchas: environment precedence, the relative `.env` path, and `extra="forbid"`
- **Status: Confirmed.**

### 5.5 Migration chain

- **Old:** `0001 → … → 0011`, four descriptions
- **New:** `0001 → … → 0015`, all ten descriptions, plus a note that `0003`–`0006` never existed
- **Evidence:** `backend/migrations/versions/` contains 11 files; `0007` sets
  `down_revision = "0002"`
- **Status: Confirmed.** Also corrects `0009`, which the old text called `audio_uploads` — it is
  `narrative_threads`; `audio_uploads` is `0011`.

### 5.6 slowapi Redis claim (two locations)

- **Old:** "Redis-upgradeable via `SLOWAPI_STORAGE_URI`" and "move rate limits… with zero code changes"
- **New:** storage is unconditionally in-memory; `SLOWAPI_STORAGE_URI` is read by nothing; Redis
  requires editing `middleware/rate_limit.py:67`
- **Evidence:** `middleware/rate_limit.py:67` — `limiter = Limiter(key_func=get_remote_address)`,
  no `storage_uri`. No `slowapi_storage_uri` field on `Settings`. The name appears only in comments
  and docs.
- **Status: Confirmed.**

### 5.7 Environment-variable pointer

- **New:** a note in Service Commands that the script generates everything mandatory, with a link to
  the recovery report; plus build-time semantics for `NEXT_PUBLIC_API_URL`
- **Status: Confirmed.**

---

## 6. Deliberately not changed

| Item | Reason |
|---|---|
| `start.sh` (port 8001, legacy) | Shell script — code change, out of scope. Documented in the recovery report §10 |
| `scripts/verify_runpod_setup.sh` (port 8001) | Shell script — out of scope. Reports a false failure against a working stack; documented |
| `start-narratiq.sh` (hardcoded paths, `MODEL_BASE_DIR` override) | Shell script — out of scope. Documented with symlink workarounds |
| `backend/config.py` (`database_url` defaults to SQLite) | Application code — out of scope. Unreachable in practice; documented |
| `backend/alembic.ini:7` (hardcoded DB URL) | Application config — out of scope. Overridden at runtime by `migrations/env.py:15` |
| `middleware/rate_limit.py` (no `storage_uri`) | Application code — out of scope. Documented |
| `frontend/app/(dashboard)/projects/[id]/analytics/page.tsx:185-190` ("Coming Soon" for shipped features) | Application code — out of scope. Reported in `NarratIQ_Project_Recovery_Report.docx` |
| The `.docx` reports | Historical artefacts; left as-is |
| Git history | No mutating command was run. `git status --short` was empty before and after |

---

## 7. Recommended follow-up (requires code changes)

1. Align `start.sh:25` and `scripts/verify_runpod_setup.sh:14` to port 9001, or delete `start.sh`.
2. Make `start-narratiq.sh:16` honour `MODEL_BASE_DIR` so Network Volumes work as documented.
3. Change `config.py:32` `database_url` default away from SQLite, or remove the default so a missing
   value fails loudly rather than at the pgvector self-check.
4. Either implement `SLOWAPI_STORAGE_URI` in `middleware/rate_limit.py:67` or delete the name from
   the remaining comments.
5. Consider `extra="ignore"` on `Settings` so a stray `.env` key cannot prevent startup.

---

*All conclusions derive from static analysis of commit `9827587`. No service was started, no model
downloaded, and no migration run. The application has not been verified to work.*
