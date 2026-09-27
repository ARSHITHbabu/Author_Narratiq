# Performance Baselines (Stage 9 task 9.3, production gap PG-12)

| | |
|---|---|
| **Measured** | 2026-09-27, pod `6uavswo19trx9n` — 1× NVIDIA A40 48 GB, 96 vCPU, 503 GB RAM |
| **Stack** | vLLM 0.9.2 / Qwen2.5-7B-Instruct (TP=1, max_model_len 8192, gpu_memory_utilization 0.88); BGE-M3 **on CPU** (`bge_device="cpu"`, the default); PostgreSQL 16 + pgvector 0.8; one uvicorn worker (decision D-3) |
| **Where** | A backend bound to the allow-listed `narratiq_test` database (port 8100), synthetic authors created and deleted by the probes. `RATE_LIMIT_*` were raised on that test backend so the limiter did not distort latency; limits themselves are verified in `backend/tests/test_security_stage9.py` |
| **Tools (no new dependencies)** | `backend/scripts/perf/load_probe.py`, `hnsw_bench.py`, `plot_hole_cap_probe.py` — httpx (already pinned) + asyncio |
| **Raw results** | `docs/testing/performance/stage-09-*.json`, `stage-09-concurrency.txt` |
| **Status** | Baselines **recorded**. Targets below are **proposed, not approved** — the product owner approves them separately (Stage 9 instruction 5). "Latency targets defined and met" is not ticked |

## 1. Single-author latency per AI endpoint (5 sequential calls, 6-chapter indexed story)

| Endpoint | p50 | p95 | Notes |
|---|---:|---:|---|
| Tone | 0.74 s | 0.76 s | Fast because the no-change layer declines the already-tense probe passage; a real rewrite is closer to Style/Emotion |
| Style | 0.95 s | 0.96 s | |
| Plot Assistant (Q&A) | 1.66 s | 2.23 s | |
| Emotion | 3.19 s | 3.46 s | |
| Age-adapt | 3.08 s | 3.11 s | |
| Translate | 3.30 s | 3.35 s | |
| Author-inspired style | 3.90 s | 4.46 s | |
| Continuity check | 3.14 s | 3.26 s | 6 chapters |
| Plot holes | 3.26 s | 3.35 s | 6 chapters |
| Refine | 6.42 s | 9.70 s | Widest spread (2.5–9.7 s) |
| Suggestions | 5.33 s | 5.40 s | |
| Outline | 7.59 s | 8.16 s | |
| Continuation (3 options) | 14.37 s | 16.47 s | Longest foreground call |
| Semantic search | 0.23 s | 0.25 s | Embedding + pgvector |
| Chapter indexing (sync-summaries) | 67 s for 6 chapters | — | ~11 s per chapter, background |

## 2. Concurrent authors (one synthetic author per client, same request)

| Concurrent | Tone p50 / p95 | Plot Assistant p50 / p95 | Errors |
|---:|---|---|---|
| 1 | 0.72 / 0.72 s | 1.42 / 1.42 s | 0 |
| 3 | 0.77 / 0.77 s | 2.45 / 2.57 s | 0 |
| 6 | 0.84 / 0.84 s | 4.21 / 4.53 s | 0 |
| 10 | 0.88 / 0.92 s | 6.77 / 7.38 s | 0 |

**vLLM queue depth** (sampled every 0.5 s from `:9001/metrics` across every phase, 1,668 samples): max
`num_requests_waiting` **0**, max `num_requests_running` **3**. The model server was never the bottleneck.

**Plot Assistant scales roughly linearly with concurrency (~0.6 s per extra author).** The likely cause, from
the code: every request embeds its query with BGE-M3 **on CPU** through a 2-thread executor
(`services/ai_service.py:42`, `_bge_executor = ThreadPoolExecutor(max_workers=2)`), so concurrent requests
queue for embedding, not for the model. Supporting evidence: tone (no retrieval) barely moves under the same
load, and vLLM never queued. Moving BGE-M3 to the GPU (`BGE_DEVICE=cuda`; ~2.3 GB against ~5.7 GB of VRAM
headroom next to vLLM's 0.88 share) is the obvious remedy — a configuration change that needs approval and a
re-measurement, not done in Stage 9.

## 3. Background jobs vs `BG_AI_CONCURRENCY=3` (Story Bible, 3-chapter indexed stories)

| Simultaneous jobs | Accepted | Completed | Completion times (s) |
|---:|---:|---:|---|
| 1 | 1 | 1 | 67.7 |
| 3 | 3 | 3 | 53.2, 55.2, 57.2 |
| 6 | 6 | 6 | 44.3, 48.4, 50.5 · 77.0, 83.1, 83.1 |

At 6 jobs the semaphore visibly admits three and queues three; every job completes, none fails or hangs.
`EMBEDDING_CONCURRENCY=2` was exercised by the same runs (indexing) without error.

## 4. pgvector at realistic corpus size

Synthetic corpus: 100 stories × 580 chunks (≈ a 200k-word novel each) = **57,440** 1024-dim vectors.
Query = the app's own shape (`WHERE story_id = … ORDER BY embedding <=> … LIMIT 8`).

| Target story | p50 | p95 | Rows returned | Recall@8 vs exact |
|---|---:|---:|---:|---:|
| 580 chunks | 7.9 ms | 8.4 ms | 8 | 1.00 |
| 20 chunks | 7.0 ms | 7.6 ms | 8 | 1.00 |

**Finding:** the planner does **not** use the HNSW index for story-filtered retrieval — it runs a sequential scan
of `chapter_chunks` filtered by `story_id`, then sorts (exact, so recall is perfect). There is **no B-tree index
on `chapter_chunks.story_id`**, so the cost grows with the whole table (all authors), not with the story. At
57k chunks this is 8 ms and irrelevant next to model latency; it becomes worth an index somewhere in the
hundreds of thousands of chunks. Adding `ix_chapter_chunks_story_id` would be a migration — proposed, not done.
(`hnsw.ef_search` 40, `hnsw.iterative_scan` off.)

## 5. The 60-chapter plot-hole cap (decision D-8)

| Chapters | Status | Latency | Chapters analysed | Cap note shown to the author |
|---:|---:|---:|---:|---|
| 60 | 200 | 9.4 s | 60 | No (none needed) |
| 61 | 200 | 8.4 s | 60 | **Yes** — "60-chapter cap applied — chapters 61+ not scanned…" |

The 60-chapter prompt fits the 8,192-token context with realistic summaries; the cap is honest (stated, not
silent).

## 6. Proposed latency targets (for approval — not approved)

Derived from the single-author p95 above × ~1.5 for headroom, rounded; the 10-author row reflects the measured
embedding bottleneck and should tighten if BGE-M3 moves to the GPU.

| Class | Endpoints | Proposed p95, 1 author | Proposed p95, 10 concurrent authors |
|---|---|---:|---:|
| Interactive rewrite | tone, style, emotion, age-adapt, translate, author-style | ≤ 6 s | ≤ 8 s |
| Refine | refine | ≤ 12 s | — (measure) |
| Q&A | Plot Assistant | ≤ 3 s | ≤ 10 s (≤ 4 s with GPU embeddings — to verify) |
| Generation | suggestions, outline | ≤ 12 s | — (measure) |
| Long generation | continuation | ≤ 25 s | — (measure) |
| Analysis | continuity, plot holes (≤ 60 chapters) | ≤ 15 s | — |
| Search | semantic search | ≤ 0.5 s | ≤ 1 s |
| Background | Story Bible, 3 simultaneous authors | all complete, ≤ 120 s | — |
| Retrieval SQL | story-filtered chunk retrieval | ≤ 50 ms at 100k chunks | — |
| Phase 3 spec (already defined) | context assembly on a 200k-word story; pins list at 1k pins | p95 < 400 ms; p95 < 50 ms | — (not separately measured in Stage 9) |

Every measured value above meets the proposed targets. The Phase 3 spec's two targets were not isolated in this
probe and remain to be measured if the owner adopts them.

## How to re-run

```
# isolated backend on the test database (limits raised for measurement only)
cd backend && DATABASE_URL=…/narratiq_test RATE_LIMIT_AUTH=1000/minute RATE_LIMIT_REALTIME_AI=1000/minute \
  RATE_LIMIT_HEAVY_AI=1000/minute RATE_LIMIT_BACKGROUND_AI=1000/minute \
  python3 -m uvicorn main:app --host 127.0.0.1 --port 8100 --workers 1 &
DATABASE_URL=…/narratiq_test python3 backend/scripts/perf/load_probe.py --base http://127.0.0.1:8100 --out perf.json
DATABASE_URL=…/narratiq_test python3 backend/scripts/perf/hnsw_bench.py --stories 100 --chunks 580 --out hnsw.json
DATABASE_URL=…/narratiq_test python3 backend/scripts/perf/plot_hole_cap_probe.py --base http://127.0.0.1:8100 --out cap.json
```
