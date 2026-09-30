# Model versions

**Stage 10, task 10.5.** Every model NarratIQ runs, pinned to the exact Hugging Face commit verified on the pod. Before Stage 10 the downloads were unpinned, so a fresh pod silently took whatever each repository's main branch held that day.

Revisions were read on 2026-09-29 from each model directory's `.cache/huggingface/download/*.metadata` (every file in a model agreed on one commit) and, for the partial STT model, from the Hugging Face cache snapshot directory.

| Model | Repository | Revision | Local path | Used by |
|---|---|---|---|---|
| Qwen2.5-7B-Instruct | `Qwen/Qwen2.5-7B-Instruct` | `a09a35458c702b33eeacc393d103063234e8bc28` | `/workspace/models/Qwen2.5-7B-Instruct` | vLLM 0.9.2 (all generation) |
| BGE-M3 | `BAAI/bge-m3` | `5617a9f61b028005a4858fdac845db406aefb181` | `/workspace/models/bge-m3` | embeddings (1024-dim) |
| GOT-OCR2.0 | `stepfun-ai/GOT-OCR2_0` | `979938bf89ccdc949c0131ddd3841e24578a4742` | `/workspace/models/GOT-OCR2_0` | OCR |
| faster-whisper large-v3-turbo | `deepdml/faster-whisper-large-v3-turbo-ct2` | `4df90f75321148c3a29a9e2351b7ddf8f5b115a8` | `/workspace/models/faster-whisper-large-v3-turbo` | audio transcription |
| faster-whisper base | `Systran/faster-whisper-base` | `ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66` | HF cache | live voice partials |

Overrides (for a deliberate upgrade or a rollback — `docs/operations/rollback.md` §5): `NARRATIQ_QWEN_REVISION`, `NARRATIQ_BGE_REVISION`, `NARRATIQ_GOT_OCR_REVISION` (`scripts/download_models.sh`), `NARRATIQ_WHISPER_REVISION` (`start-narratiq.sh`). The partial STT model is pinned only for the default `STT_PARTIAL_MODEL=base`.

Check what is on disk:

```bash
for m in /workspace/models/*/; do
  echo "$(basename "$m"): $(head -qn1 "$m"/.cache/huggingface/download/*.metadata 2>/dev/null | sort -u)"
done
```

When a revision is changed on purpose, update this table in the same commit.
