# Monitoring, error tracking and alerting

**Stage 10, task 10.2 (production gap PG-03).** Everything here is built into NarratIQ and runs on the pod. Decisions S10-C/S10-D: **no external error-tracking, uptime or notification service is configured.** Alerts are generated and recorded locally, ready for a delivery channel to be attached later. Until one is, **an alert reaches a person only if someone reads the alert log** — this is the main open item of 10.2.

---

## 1. Signals

### `/api/health` (public)

| Field | Meaning |
|---|---|
| `status` | `ok`, or `degraded` when vLLM or the embeddings model is not ready |
| `backend` | always `ready` when the API answers |
| `vllm` | `ready` / `unavailable` — **probed live** (cached 10 s, 2 s timeout) |
| `bge_m3` | `ready` / `loading` |

HTTP **200** when ok, **503** when degraded. Before Stage 10 the `vllm` value was set once at startup, so vLLM dying later was invisible ("degraded mode": every AI call 503 while health said ready). Internal configuration (vLLM URL, model, GPU) is no longer public — it moved to `/api/ops/status`.

### `/api/ops/*` (ops token)

Header `X-Ops-Token: <OPS_TOKEN from backend/.env>`. With `OPS_TOKEN` unset they answer 404.

| Endpoint | Contents |
|---|---|
| `GET /api/ops/status` | vLLM/embeddings state, GPU, model configuration, uptime |
| `GET /api/ops/metrics` | request / 5xx / AI-unavailable / truncated-AI / client-error counts for the last 5, 15, 60 min; AI parse outcomes per feature (clean, salvaged, truncated, reprompted, failed); failed and in-progress background jobs per job table (last 60 min); the last startup's orphan-job recovery; error records in the last 60 min; backup freshness and last verification |
| `GET /api/ops/errors` | the newest scrubbed error records |
| `GET /api/stats` | account / story / chapter counts (was public; now needs the token) |

Counters live in process memory (decision D-3, one worker) and reset on restart; the watchdog alerts on changes, so a reset is harmless.

### Built-in error tracking (`error_events` table)

* Every **unhandled backend exception** becomes one record and an author-readable 500 (*"Something went wrong on our side, and this action did not finish. Your saved work is unaffected."*) carrying a `request_id` — never a stack trace.
* The frontend's error boundaries (`app/global-error.tsx`, `app/error.tsx`, the editor's `error.tsx`) report to `POST /api/client-errors` on NarratIQ's own backend (public, 30/min per IP, size-capped). They no longer show authors raw error messages or stack traces.
* **What a record can contain is limited by construction** (`services/error_tracking.py`): the route *template* (`/api/stories/{story_id}/…`, never an id), frame locations only (`file.py:120 in fn` — no source lines, no locals), and the exception message after scrubbing (quoted text, emails, tokens, `key=value` secrets, ids removed, then cut to 12 words). No user id, request body or header is stored. Tests plant manuscript text, an email and a token in an exception and assert none reaches the record.
* The same fault is counted on one row (fingerprint, 24 h window). Records older than 30 days are pruned hourly, with a hard cap of 5,000 rows.

### Logs

`LOG_FORMAT=json` (written to `backend/.env` by `start-narratiq.sh` when absent): one JSON object per line with `ts`, `level`, `module`, `event` and `request_id`. Every response carries `X-Request-ID`; an author's reported failure is traced by that id through the log and the error record. Log privacy rules (never manuscript text, tokens or passwords) are unchanged; the failed-login line no longer logs the email address.

## 2. The watchdog

`scripts/watchdog.py`, started by `start-narratiq.sh` (PID `/tmp/narratiq-logs/watchdog.pid`, log `/workspace/logs/watchdog.log`).

| Alert | Severity | Condition |
|---|---|---|
| `backend_unreachable` | critical | `/api/health` does not answer |
| `vllm_unavailable` | critical | health says `"vllm":"unavailable"` |
| `embeddings_not_ready` | high | health says `bge_m3` is not ready |
| `ai_unavailable_rate` | high | ≥ 5 AI-unavailable 503s in 15 min |
| `server_error_rate` | high | ≥ 5 server errors in 15 min |
| `degraded_output_rate` | medium | ≥ 30 % of AI parses salvaged/truncated/failed since the last check (≥ 10 calls) |
| `background_job_failures` | medium | ≥ 3 failed background jobs in 60 min |
| `orphan_recovery` | medium | the last backend start marked interrupted jobs as failed |
| `backup_stale` | high | newest on-pod dump older than 3 h |
| `backup_verify_failed` | high | the last automated restore verification failed |

A condition must hold for **2 consecutive checks** (30 s apart) before it fires; one-shot events (orphan recovery, failed verification) fire at once. An alert fires once, repeats every 6 h while true, and sends a `resolved` event when it clears. All thresholds are environment variables (`.env.example`).

**Where alerts go:** one JSON line per event in **`/workspace/logs/alerts.jsonl`** (persistent) and the watchdog log. If `NARRATIQ_ALERT_COMMAND` is set, that command also receives each event as JSON on stdin — the attachment point for a mail, push or chat channel later. Alert text is fixed wording; it never contains manuscript text, user data or secrets. A heartbeat file (`/workspace/logs/watchdog.heartbeat`) is touched every loop, ready for an external dead-man's switch.

Check what fired:

```bash
tail -n 20 /workspace/logs/alerts.jsonl
curl -s -H "X-Ops-Token: $(grep ^OPS_TOKEN= backend/.env | cut -d= -f2)" http://127.0.0.1:8000/api/ops/metrics | python3 -m json.tool
```

## 3. On-call path (today)

Owner of every stage and the only on-call person: the author/product owner (task 0.10). Until a delivery channel exists:

1. check `alerts.jsonl` at the start and end of every working session, and after any report from an author;
2. act by severity per `docs/operations/incident-response.md`.

## 4. Deferred (needs an external service — decision S10-D)

* Delivering alerts to a phone or mailbox (attach through `NARRATIQ_ALERT_COMMAND`).
* Uptime checks from **outside** the pod — the watchdog runs on the pod, so it cannot report the pod itself disappearing. The heartbeat file is ready for an external dead-man's switch.
* A hosted error-tracking UI — `GET /api/ops/errors` is the built-in equivalent.
