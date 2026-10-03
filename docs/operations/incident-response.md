# Incident response

**Stage 10, task 10.9 (production gap PG-13).** The next incident follows a process, not improvisation. Formalises what `docs/incidents/runpod-port-3000-404-incident-report.md` and `docs/incidents/2026-09-22-database-row-count-discrepancy.md` did well.

---

## 1. Severity levels

| Level | Definition | Examples | Respond |
|---|---|---|---|
| **SEV1** | Author data lost, exposed to another user, or at risk of loss; or the service is down for everyone | database empty after a restart; a cross-user data leak; backups failing **and** the pod at risk | immediately; stop writes if data is at risk |
| **SEV2** | A core writing path is down or unsafe for everyone | login down; AI unavailable (`vllm_unavailable`); saving fails; `backup_verify_failed` | same working session |
| **SEV3** | One feature degraded, or a workaround exists | one AI tool erroring; high degraded-output rate; background jobs failing | within 1 working day |
| **SEV4** | Cosmetic or single-author inconvenience | layout glitch, a confusing message | normal backlog |

When unsure, pick the higher level. A suspected data loss is SEV1 until disproved (as the 2026-09-22 row-count incident correctly was).

Watchdog alerts map to severities: `critical` → SEV1/SEV2, `high` → SEV2, `medium` → SEV3 (`docs/operations/monitoring-and-alerting.md`).

## 2. On-call and escalation

* **On call:** the author/product owner — owner of every stage (task 0.10). There is no second person today.
* **Detection:** watchdog alerts in `/workspace/logs/alerts.jsonl` (checked at the start and end of every session — no external delivery channel yet, decision S10-D), or an author report.
* **Escalation:** RunPod infrastructure problems (volume, proxy, GPU) → RunPod support; model or library defects → the upstream project. Record who was contacted in the report.

## 3. Process

1. **Declare** — note the time, severity and symptom in a new report (template below). Timestamps in UTC.
2. **Protect data first** — for SEV1: stop writes (`pkill -f 'uvicorn main:app'`), take a backup of whatever exists (`bash scripts/backup_database.sh`, mark it `.keep`), never restore over data you have not copied. Do **not** stop or restart the pod to test a theory.
3. **Diagnose with evidence** — `/api/health`, `/api/ops/metrics`, `/api/ops/errors`, `alerts.jsonl`, `/tmp/narratiq-logs/*.log` (request ids tie a report to log lines). Record commands and outputs.
4. **Mitigate** — the smallest safe change: rollback (`rollback.md`), restore (`backup-and-restore.md`), restart one service.
5. **Verify** — the symptom is gone, data checks pass (`verify_backup.py`, manifest comparison), the watchdog alert resolved.
6. **Write up** — within 2 working days for SEV1/SEV2, using the template. Blameless: causes and missing safeguards, not people.
7. **Follow up** — every preventive action becomes a tracked item (checklist task or issue) with an owner.

## 4. Postmortem template and filing

Template: [`docs/incidents/TEMPLATE.md`](../incidents/TEMPLATE.md) — the structure of the RunPod port-404 report. File each report as `docs/incidents/YYYY-MM-DD-short-slug.md`. Never include manuscript text, credentials or another author's data in a report.

## 5. Runbook — known issues

### RunPod proxy returns 404 on :3000 or :8000
From the 2026-07-24 incident report (§7). Triage:

| Signature | Meaning | Action |
|---|---|---|
| `curl localhost:3000` works, proxy URL 404 | port not exposed on the pod | RunPod UI → Edit pod → expose 3000/8000 (**requires a pod stop/start — take and verify a backup first**) |
| proxy 404 on both ports, `ss -tlnp` shows nothing | services not running | `bash start-narratiq.sh` |
| proxy 502/504 | service up but crashing or slow | `tail -50 /tmp/narratiq-logs/frontend.log` / `backend.log` |
| frontend loads, every API call fails | backend down or `BACKEND_INTERNAL_URL` wrong at build | `curl localhost:8000/api/health`; rebuild the frontend |

`scripts/verify_runpod_setup.sh` runs these checks.

### Database empty after a restart (SEV1)
The container layer (PostgreSQL data) does not survive a pod stop. `scripts/startup_backup.sh` detects an unexpectedly empty database with a prior backup **holding author data** and **aborts the start**. Since Stage 12 Tranche 3, a backup whose checksummed manifest shows an empty database is not counted (`scripts/backup_evidence.py`): a pod that was only ever empty restarts normally. A backup that cannot be proven empty still counts, and so does any older data backup. Follow `backup-and-restore.md` §4. Never set `NARRATIQ_ACKNOWLEDGE_EMPTY_RESTART` unless you have decided the data is intentionally gone.

### vLLM unavailable (SEV2)
`tail -50 /tmp/narratiq-logs/vllm.log`. Out of memory → check `nvidia-smi` for another process. Crash on start → clear `~/.cache/vllm/torch_compile_cache` and restart vLLM (CLAUDE.md). Authors can keep writing; AI tools answer "unavailable".

### Backup verification failed (SEV2)
Read `/workspace/backups/LAST-VERIFY.json` → `problems`. A checksum mismatch means the stored file changed (volume fault?) — take a new backup immediately and verify it. A content mismatch on a fresh set is a pipeline defect — keep the older verified sets (`.keep`) and investigate before rotation removes them.

### Disk full
`df -h /workspace /`. Backups: reduce `NARRATIQ_BACKUP_KEEP_RECENT` (never delete the newest verified set by hand). Logs: `/workspace/logs/*.log` can be truncated after copying what an open incident needs.

## 6. Tabletop exercise

Scenario and checklist: `docs/testing/manual-verification/stage-10-manual-verification-guide.md` (MV-10.9). The checklist box "A tabletop exercise runs cleanly through the process" needs the on-call person and stays open until it is run.
