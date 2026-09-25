# Stage 2 — Manual Verification Guide

| | |
|---|---|
| Stage | 2 — Environment and Service Verification |
| Created | 2026-09-25 |
| Checklist | [`docs/NarratIQ_Master_Implementation_Checklist.md`](../../NarratIQ_Master_Implementation_Checklist.md), Stage 2 |
| Why this exists | The Stage 2 implementation was done in a cloud workspace with no RunPod pod, GPU, models, database or secret store. Everything below needs one of those, so it is listed here with exact steps instead of being ticked. |

Everything the cloud *could* verify is recorded in the Stage 2 section of the checklist (hermetic test
suite `scripts/tests/test_verify_runpod_setup.py`, 23 tests; the Next.js precedence builds in
[`runpod-environment-variables.md` §11 item 2](../../operations/runpod-environment-variables.md)).

**Safety rules for every item:** do not print `SECRET_KEY` or `RUNPOD_API_KEY`; do not stop or restart
the pod; nothing here reads or writes story, chapter or user data.

---

## A. RunPod / Infrastructure Verification

### MV-2.6-A — The RunPod port-list check works against the real API

| Field | Value |
|---|---|
| Related task | 2.6, subtask "Add a check that ports 3000/8000 appear in the RunPod port list" (implemented) and the 2.6 verification box |
| Requirement | The verifier reads the pod's exposed-port table and reports 3000 and 8000 correctly |
| What must be tested | The live RunPod GraphQL response is parsed correctly, and the pod-injected key is accepted as a Bearer header |
| Why the cloud could not verify it | No pod, no `RUNPOD_API_KEY`, and outbound calls to RunPod are out of scope for hermetic tests. The query shape is taken from the live 2026-07 incident query, which used `?api_key=` rather than the header; header acceptance and key permission are unproven |
| Required environment | The running RunPod pod, from its own terminal |
| Preconditions | `RUNPOD_POD_ID` and `RUNPOD_API_KEY` present in the pod environment (RunPod injects both). Check without printing: `[ -n "$RUNPOD_API_KEY" ] && echo key-present` |
| Test data | None |
| Procedure | 1. `cd /workspace/narratiq-ai` (the repo path)  2. `bash scripts/verify_runpod_setup.sh 2>&1 \| sed -n '/RunPod Port Exposure/,/Frontend API URL/p'` |
| Expected result | `[OK]  Port 3000 is exposed as an HTTP port on pod <id>` and the same for 8000 |
| Acceptable alternative | `[WARN] Could not determine the exposed-port list — …` or `RunPod API answered HTTP 401/403`. This means the header form or the key's permission is not accepted. Record the exact WARN text: the check then needs a follow-up, and the 2.6 verification box stays open |
| Failure indicators | `[FAIL] Port 3000 is NOT exposed…` on a pod where the site does work through the proxy (a parser or shape defect); the key text appearing anywhere in the output |
| Evidence to capture | The section's output lines (they contain no secret), and the pod's port list as shown in the RunPod UI (Edit Pod → Expose HTTP Ports) |
| Checklist affected | 2.6 verification box; Stage 2 gate line "Clean-start verification is a single repeatable command" |
| Status | **PENDING MANUAL VERIFICATION** |

### MV-2.6-B — The script passes on the healthy pod and fails correctly on a broken config

| Field | Value |
|---|---|
| Related task | 2.6 verification: "Script passes on the current pod and fails correctly on a deliberately broken config" |
| Requirement | Environment health is one command that tells the truth both ways |
| What must be tested | Exit 0 on the healthy running stack in strict mode; exit 1 with a specific failure when a config is broken |
| Why the cloud could not verify it | The cloud has no GPU, models, packages or database, so the script's other sections always fail there. The failure paths were proven against local stubs (tests N1–N6, H1), not on the pod |
| Required environment | The running RunPod pod after `bash start-narratiq.sh` has completed |
| Preconditions | All three services up |
| Test data | None |
| Procedure | **Step 1, healthy:** `bash scripts/verify_runpod_setup.sh --expect-running; echo "exit=$?"`  **Step 2, broken config (non-disruptive; the classic stale-port mistake, nothing is stopped):** `VLLM_PORT=8001 bash scripts/verify_runpod_setup.sh --expect-running; echo "exit=$?"`  **Step 3 (optional, disruptive — only the frontend process, never the pod):** `fuser -k 3000/tcp`, then re-run Step 1, then restore with `cd frontend && nohup npm start -- --port 3000 > /tmp/narratiq-logs/frontend.log 2>&1 &` |
| Expected result | Step 1: `FAILED : 0` and `exit=0`. Step 2: `[FAIL] vLLM (port 8001) — NOT RUNNING, but --expect-running was given` and `exit=1`. Step 3: `[FAIL] Frontend (port 3000) — NOT RUNNING…`, plus the proxy line `[FAIL] Frontend proxy (3000) is exposed but nothing answers behind it (HTTP 502)`, and `exit=1` |
| Failure indicators | Step 1 fails on any item while the app works in the browser (a false failure: capture it); Step 2 or 3 exits 0 (a false pass) |
| Evidence to capture | Full output of each step (it contains no secrets) |
| Checklist affected | 2.6 verification box, parent 2.6, Stage 2 gate line "Clean-start verification is a single repeatable command" |
| Status | **PENDING MANUAL VERIFICATION** |

### MV-2.5-A — The startup script's build ignores a stale OS `NEXT_PUBLIC_API_URL`

| Field | Value |
|---|---|
| Related task | 2.5 (supporting change `start-narratiq.sh:622`) |
| Requirement | The URL the startup script computes is the one baked into the frontend, even with a stale RunPod-UI value |
| What must be tested | A real `start-narratiq.sh` run with a deliberately stale OS variable |
| Why the cloud could not verify it | The same `VAR=value npm run build` form was proven in a scratch build (§11 item 2, build 4), but the full startup script needs the pod |
| Required environment | The pod, at a moment when a full `start-narratiq.sh` run is acceptable (it restarts the app services, not the pod) |
| Preconditions | Current services healthy; no author work in progress |
| Test data | None |
| Procedure | 1. `NEXT_PUBLIC_API_URL=https://STALE-SENTINEL.invalid bash start-narratiq.sh`  2. `grep -rl "STALE-SENTINEL" frontend/.next/static \| wc -l`  3. `grep -rl "${RUNPOD_POD_ID}-8000.proxy.runpod.net" frontend/.next/static \| wc -l` |
| Expected result | Step 2 prints `0`; step 3 prints `1` or more; the app works in the browser |
| Failure indicators | Step 2 is non-zero (the stale value was baked in) |
| Evidence to capture | Both counts; `tail -5 /tmp/narratiq-logs/frontend-build.log` |
| Checklist affected | None directly (2.5 is closed on the build evidence); failure would reopen 2.5 |
| Status | **PENDING MANUAL VERIFICATION** |

---

## B. Security / Secrets Verification

### MV-2.2-A — Is `SECRET_KEY` set in the RunPod UI on the current pod? (resolves a disputed record)

| Field | Value |
|---|---|
| Related task | 2.2, subtask "Confirm it is set in the RunPod UI…" (**unticked 2026-09-25 as disputed**) |
| Requirement | Know which `SECRET_KEY` is live, so stability across re-clones is known |
| What must be tested | Whether the OS environment on pod `shbr4txyem5s9w` holds `SECRET_KEY` |
| Why the cloud could not verify it | No access to the pod. Two same-day 2026-09-21 records disagree (the checklist says it was set; `runpod-environment-variables.md` §11 item 1 says it was not), and that pod was later reset |
| Required environment | The pod terminal, and the RunPod UI (Edit Pod → Environment Variables) |
| Preconditions | None |
| Test data | None |
| Procedure | 1. On the pod: `[ -n "${SECRET_KEY:-}" ] && echo "SECRET_KEY: set in OS env" \|\| echo "SECRET_KEY: NOT in OS env"` (prints no value)  2. In the RunPod UI, look for a `SECRET_KEY` entry (do not reveal or copy it on a shared screen) |
| Expected result | Both steps agree. If set: tick 2.2 subtask 2 with this evidence. If not set: decide whether to add it (recommended, §3.3) before re-ticking |
| Failure indicators | The value is printed anywhere |
| Evidence to capture | The one-line output of step 1; a yes/no from the UI |
| Checklist affected | 2.2 subtask 2; Stage 2 gate line "`SECRET_KEY` stable and stored" |
| Status | **PENDING MANUAL VERIFICATION** |

### MV-2.2-B — `SECRET_KEY` recorded in the team secret store

| Field | Value |
|---|---|
| Related task | 2.2 subtask "Record it in the team secret store"; parent 2.2 |
| Requirement | Logins survive a repository re-clone, and a pod reset |
| What must be tested | A copy of the live key exists outside the pod and matches it |
| Why the cloud could not verify it | Organisational action; no secret store is reachable, and the key must not pass through an AI transcript |
| Required environment | The pod, plus the author's password manager or secret store |
| Preconditions | MV-2.2-A done (you know which key is live) |
| Test data | None |
| Procedure | Follow [`runpod-environment-variables.md` §3.3, "Storing `SECRET_KEY` outside the pod"](../../operations/runpod-environment-variables.md) steps 1–3 exactly: copy via clipboard, never on screen, and verify by SHA-256 comparison. **Hash the live copy:** if MV-2.2-A found `SECRET_KEY` in the OS env, the pod-side hash is `printf '%s' "$SECRET_KEY" \| sha256sum` (the OS value wins over `backend/.env`); only otherwise hash the `backend/.env` line |
| Expected result | The two SHA-256 hashes match |
| Failure indicators | Hashes differ (a stray newline is the usual cause: re-check the `tr -d '\n'`); the value was displayed anywhere (then rotate it, per step 5) |
| Evidence to capture | The statement "hashes match on <date>", and the name of the store. **Not** the hash itself in any shared document |
| Checklist affected | 2.2 subtask 3; parent 2.2; Stage 2 gate line "`SECRET_KEY` stable and stored" |
| Status | **PENDING MANUAL VERIFICATION** |

---

## Browser / UX, AI quality, external services, production deployment

No Stage 2 item needs browser, AI-quality or deployment verification beyond the "the app works in the
browser" sanity check inside MV-2.6-B and MV-2.5-A.

---

## STAGE VERIFICATION SUMMARY

| | Count | Items |
|---|---:|---|
| **Cloud verified** | 4 | 2.5 override case (4 builds, `next@14.2.35`); 2.6 port-list check implemented and tested (23 hermetic tests: failure paths, strict mode, key never in output or argv, loopback-only); 2.6 false-pass fixes (no `ss`/`netstat`, vLLM `/health` 500, proxy `000`); startup build-line fix (scratch build 4) |
| **Manual verification pending** | 5 | MV-2.6-A, MV-2.6-B, MV-2.5-A, MV-2.2-A, MV-2.2-B |
| **Blocked** | 0 | — |
| **Failed** | 0 | — |

**Stage gate: OPEN — MANUAL VERIFICATION PENDING.** Two gate lines remain open: "`SECRET_KEY` stable and
stored" (MV-2.2-A, MV-2.2-B) and "Clean-start verification is a single repeatable command" (MV-2.6-A,
MV-2.6-B).
