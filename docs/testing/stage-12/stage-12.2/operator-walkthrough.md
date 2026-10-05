# Stage 12.2 — Documentation-only operator walkthrough (2026-10-05)

**Question answered:** can an operator deploy, back up, restore and roll back NarratIQ from the documentation alone?
**Method:** on a brand-new pod, follow the runbooks literally, with synthetic data only, and record every place the
documentation was wrong, missing or ambiguous. The documentation was corrected as each gap was found (listed below).

| | |
|---|---|
| Pod | `55zfw2ol0sx1gi`, 1× NVIDIA A40 (46068 MiB); `/workspace` is the MooseFS network volume |
| Starting state | **A third pod replacement.** Only a fresh clone existed: no PostgreSQL, Node, `backend/.env`, `frontend/.env.local`, `/workspace/backups`, `/workspace/models` or `/workspace/logs` |
| Code | HEAD `9f9cdad` (`main`), plus the uncommitted Stage 12.1/12.2 documentation changes |
| Data | One disposable synthetic author created through the public API, deleted through `DELETE /api/auth/account` at the end. No real author data was present at any point |
| External services | None used. No off-pod copy, no alert channel, no Docker |
| Logs | `logs/` next to this file. Secrets (`SECRET_KEY`, `OPS_TOKEN`, database password) are redacted |

## Result

| Operation | Runbook followed | Result | Time |
|---|---|---|---|
| **Deploy from scratch** | `runpod-deployment.md` Steps 3–4 (`bash start-narratiq.sh`) | **PASS.** `EXIT=0`, READY. Installed Node 20.20.2, PostgreSQL 16 + pgvector, vLLM 0.9.2, PyTorch cu128; downloaded 22 GB of pinned models; migrations to `0027`; backup loop and watchdog started | **12 min 19 s** (10:09:19 → 10:21:38 UTC) |
| **Verify** | Step 6 (`curl` checks), then `verify_runpod_setup.sh --expect-running` | **PASS.** vLLM `/health` 200 and serving `Qwen/Qwen2.5-7B-Instruct`; `/api/health` 200 `ok`/`ready`/`ready`; frontend 200; **public** `:3000/login` 200 and `:8000/api/health` 200; vLLM on `127.0.0.1:9001` only; setup check **39 passed / 0 failed** including a real completion | — |
| **Port contract** | `runpod-deployment.md` (3000 and 8000 exposed at pod creation, 9001 internal) | **PASS.** Both public proxy URLs answered; 9001 loopback only | — |
| **Synthetic data** | `how-to-run.md` sign-in (corrected, see D2) | Register 200 through the public frontend origin; the documented cookie-jar → Bearer method signed in (`/api/auth/me` 200); 1 story, 3 chapters, indexed (3 chunks, 3 summaries); one refine through the proxy 200 | — |
| **Backup** | `backup-and-restore.md` (manual `bash scripts/backup_database.sh`) | **PASS.** Six-file set with manifest and SHA256SUMS | 0.9 s |
| **Verify the backup** | §3 command block, verbatim (path substituted) | **PASS.** 57 tables, restore into `narratiq_restorecheck` 0.5 s | 0.7 s |
| **Restore** | §4 steps 1–8, verbatim. A chapter written *after* the backup was used as the control | **PASS.** Step 4's safety backup taken and marked `.keep`; step 6 `pg_restore` exit 0; step 8 **MATCH**; the post-backup chapter is gone (5 → 4 chapters); the last chapter's text reads correctly through the public URL | steps 1–8 about 5 s of commands |
| **Restart after restore** | §4 step 9 (`bash start-narratiq.sh`) | **PASS.** The startup backup correctly skipped ("a backup 0h old already exists … no schema change is pending"); READY | 240 s (vLLM reload 130 s) |
| **Prompt-version rollback** | `rollback.md` §5a | **PASS** after D5: log `[prompt_version] transform=tone version=v3`, then `version=v4` after reverting | 27 s and 28 s per backend-only restart |
| **Frontend rollback** | `rollback.md` §4 (`rollback_frontend.sh --dry-run`, swap, swap back) | **PASS.** Both build ids shown; swap → public `/login` 200 and `/api/auth/me` 200 on the previous build; swap back | 4 s and 5 s |
| **Cleanup** | `DELETE /api/auth/account` | **PASS.** `{"deleted":true,"rows_deleted":15}`; the old session gets 401; users, stories, chapters, chunks and summaries all 0 | — |
| **Empty-database guard after cleanup** | `backup-and-restore.md` §4a (new) | **Blocks, correctly.** `scripts/startup_backup.sh` alone: exit 1, "UNEXPECTED EMPTY DATABASE — STARTUP ABORTED", database unmodified (still at `0027`), running stack unaffected. Not overridden (see "State left behind") | — |

**Not repeated:** the full code + schema rollback. The A22 rehearsal (2026-10-03, `rollback.md` §6) remains valid: since
`f7a7a2e` no migration, requirements file, `package.json`/lock or `rollback_frontend.sh` changed (`git diff --stat`);
the one change to `start-narratiq.sh` (A25, finding its own checkout) was exercised twice here, from
`/workspace/Author_Narratiq`. The subset above exposed nothing that contradicts A22.

## Documentation defects found and fixed

| # | Where | Defect | Fix |
|---|---|---|---|
| D1 | `runpod-deployment.md` | Stale: `start-narratiq.sh:16`/`:501` (now `:21`/`:530`), `:17` (now `:22`), `verify_runpod_setup.sh:14` (now `:59`); "~17 GB" (measured 22 GB on this pod: Qwen 15 G, BGE-M3 4.3 G, Whisper 1.6 G, GOT-OCR 1.4 G); "runs `npm install`" (it runs `npm ci` only when `node_modules` is absent); "wipes `.next`" (it moves it to `.next.prev`); the startup backup, empty-database guard, backup loop and watchdog steps were missing; CORS "allows any `*.proxy.runpod.net`" (only this pod's own origins, Stage 9); the "wrong backend URL" fix named only `NEXT_PUBLIC_API_URL` (HTTP uses `BACKEND_INTERNAL_URL` since Stage 10); "symlink it" contradicted Storage options; `fuser` is not on the pod image; the footer said "not validated against a running pod" | All corrected; footer replaced with this walkthrough's reference |
| D2 | `how-to-run.md` | **The re-index example could not work:** it read `access_token` from the login body, which since Stage 10 contains only the user (the session is an HttpOnly cookie). Also "v3.0" title, Next.js 14.2.3, "14 migrations … 0018", Option C missing `BACKEND_INTERNAL_URL` (a local frontend would have proxied to the operator's own machine), the CORS claim, the health body | Cookie jar → Bearer method, **verified in this walkthrough**; the rest corrected |
| D3 | `backup-and-restore.md` | The empty-database guard was not documented in the restore runbook (an open checklist follow-up): when it blocks, what to do, the exact override phrase; the globals `.sha256` file was missing from §1; first hourly set lands an hour after start; 24 h freshness rule | New §4a; §1 and §2 corrected |
| D4 | `scripts/startup_backup.sh` message | When the guard blocked, it printed a one-line `pg_restore --clean` as the application user, which differs from the rehearsed §4 procedure (superuser, extension excluded) | The message now points to §4 and keeps the checksum check (its command was run and works). Decision logic unchanged |
| D5 | `rollback.md` §5a | "Restart the backend" had **no command** anywhere in the runbooks (no backend PID file; the documented manual start runs in the foreground and does not write `backend.log`); the log is JSON lines; a "no change needed" result logs no version — the first attempt here used an already-dark passage and found no log line | Backend-only restart block (stop by port, start detached into `backend.log`, wait for `"backend":"ready"`), JSON note, "use a passage that needs changing" |
| D6 | `rollback.md` §3, §4, §6 | "Every migration … has a real `downgrade()`" (`0026`'s is deliberately empty); "16 steps" (true at head `0024`); a fresh pod has no `.next.prev` until the second build | Corrected; rehearsal table updated |
| D7 | `storage-and-persistence.md` | §6 "recorded, not resolved" (it is resolved); §5.3/§4.1 superseded by §8; stale line references; "nothing automates" ignored the guard; `/workspace/logs` missing; **a pod replacement (not a stop) loses `/workspace` too** — this pod had none of the previous pod's backups | Corrected; replacement finding added above §6 |
| D8 | `incident-response.md`, `README.md`, `runpod-environment-variables.md` | Guard override phrase not stated; ~17 GB | Corrected |

**Automation note (not a documentation defect):** running §4 step 1 (`pkill -f 'uvicorn main:app'`) from an
automation tool whose own command line contained that text killed the tool's shell; the restore itself, run from a
script file, completed. CLAUDE.md already records this gotcha. An operator typing the command in a terminal is not
affected.

## State left behind (by design)

- Stack running and healthy on this pod; the live database is **empty** (schema at `0027`).
- `/workspace/backups` holds two sets (`20261005T102317Z`, `20261005T102349Z` marked `.keep`) containing the deleted
  synthetic author's rows. **The next `start-narratiq.sh` will therefore stop at the empty-database guard.** This was
  not bypassed: telling a deliberate deletion from data loss is an open owner decision (option a or b), and the
  acknowledgement phrase is for an operator's deliberate decision. To restart this pod, an operator chooses either
  to start once with `NARRATIQ_ACKNOWLEDGE_EMPTY_RESTART=yes-start-empty-intentionally` on the command line, or to
  retire those two synthetic sets; both are recorded options in `backup-and-restore.md` §4a.
- `narratiq_test` (allow-listed test database) created for the regression run.

## Verdict

An operator **can** deploy, verify, back up, verify a backup, restore, restart, and roll back the frontend and the
prompt version from the documentation alone, **after** the corrections above. Before them, two procedures could not
be completed as written (D2's token extraction and D5's missing restart command), and several statements were wrong
in ways that would mislead an operator during an incident (D1, D3, D7).
