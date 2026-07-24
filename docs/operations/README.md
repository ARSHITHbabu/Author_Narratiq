# Operations

Everything needed to run, deploy and configure NarratIQ AI. All three documents are **current**.

| Document | Read it when |
|---|---|
| [`how-to-run.md`](./how-to-run.md) | Starting the stack, per-service startup, verifying a running pod |
| [`runpod-deployment.md`](./runpod-deployment.md) | Creating a pod, storage layout, model weights, troubleshooting |
| [`runpod-environment-variables.md`](./runpod-environment-variables.md) | Deciding which variables to set in the RunPod UI, and why a stale one may be breaking the app |

## The short version

```bash
bash /workspace/narratiq-ai/start-narratiq.sh
```

One command handles installs, model downloads, PostgreSQL + pgvector, migrations and all three
services. It is idempotent and safe to rerun.

You need **no** environment variables to start — the script generates every mandatory value. Only
`SECRET_KEY` and `HF_TOKEN` are worth setting by hand. A stale `VLLM_BASE_URL` pointing at port 8001
is the classic cause of "healthy backend, every AI call returns 503"; see
[`runpod-environment-variables.md`](./runpod-environment-variables.md).

## Related

- Architecture reference and config gotchas: [`CLAUDE.md`](../../CLAUDE.md)
- Past production outages: [`../incidents/`](../incidents/)
