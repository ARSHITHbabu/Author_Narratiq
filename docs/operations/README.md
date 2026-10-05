# Operations

Everything needed to run, deploy, configure, back up, monitor and recover NarratIQ AI.

| Document | Read it when |
|---|---|
| [`how-to-run.md`](./how-to-run.md) | Starting the stack, per-service startup, verifying a running pod |
| [`runpod-deployment.md`](./runpod-deployment.md) | Creating a pod, storage layout, model weights, troubleshooting |
| [`runpod-environment-variables.md`](./runpod-environment-variables.md) | Deciding which variables to set in the RunPod UI, and why a stale one may be breaking the app |
| [`storage-and-persistence.md`](./storage-and-persistence.md) | What survives a pod restart or reset, and what does not |
| [`backup-and-restore.md`](./backup-and-restore.md) | Hourly backups, verification, retention, restoring a database |
| [`monitoring-and-alerting.md`](./monitoring-and-alerting.md) | Health, ops endpoints, error tracking, watchdog alerts, the required daily manual check (`scripts/daily_check.sh`, W-4) |
| [`incident-response.md`](./incident-response.md) | Severity levels, who does what, postmortems |
| [`rollback.md`](./rollback.md) | Rolling back code, schema, frontend build, models or prompt/config switches; removing newer config keys first |
| [`release-regression.md`](./release-regression.md) | The full regression every release must record against its exact commit (CI waiver W-1) |
| [`model-versions.md`](./model-versions.md) | Pinned model revisions and how to change them |
| [`capacity-planning.md`](./capacity-planning.md) | Measured capacity and onboarding limits |
| [`containers.md`](./containers.md) | Development containers (RunPod remains the production host) |

## The short version

```bash
bash /workspace/narratiq-ai/start-narratiq.sh
```

One command handles installs, model downloads, PostgreSQL + pgvector, migrations, all three services,
the backup loop and the watchdog. It is idempotent and safe to rerun. The script finds its own
checkout, so the repository can be at any path (since Stage 12 Tranche 3); see [`how-to-run.md`](./how-to-run.md).

You need **no** environment variables to start — the script generates every mandatory value. Only
`SECRET_KEY` and `HF_TOKEN` are worth setting by hand. A stale `VLLM_BASE_URL` pointing at port 8001
is the classic cause of "healthy backend, every AI call returns 503"; see
[`runpod-environment-variables.md`](./runpod-environment-variables.md).

## Related

- Architecture reference and config gotchas: [`CLAUDE.md`](../../CLAUDE.md)
- Past production outages: [`../incidents/`](../incidents/)
