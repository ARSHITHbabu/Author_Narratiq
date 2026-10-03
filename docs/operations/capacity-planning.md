# Capacity planning

**Stage 10, task 10.8 (production gap PG-12).** The supported number of concurrent authors on one pod, measured — not estimated — against the latency targets approved on 2026-09-29 (decision S10-I, `docs/testing/performance-baselines.md` §6).

## 1. Result

| Plan mix | Supported **active** authors per pod | Evidence |
|---|---|---|
| Free / basic plans (no Tier-2 consistency) | **60** — validated | 60 authors × 4 min: 460 requests, **0 errors**; rewrite p95 **3.3 s**, Q&A p95 **5.5 s**, search p95 **0.59 s** — all within targets; vLLM never queued |
| 50 % pro/studio with Tier-2 strict consistency (D6) | **No level meets every target strictly. Up to 15 authors meet the rewrite and Q&A targets, with a search tail over target. 20 or more is far over** (measured 2026-10-03, Stage 12 Tranche 3) | 10 authors (6 min): rewrite p95 7.0 s, Q&A p95 3.1 s, search p50 0.16 s / **p95 3.6 s**. 15 authors (6 min): rewrite p95 7.4 s, Q&A p95 5.3 s, search p50 0.19 s / **p95 1.2 s**. 20 authors: rewrite p95 17.9 s, Q&A p95 25.9 s, search p95 9.7 s. 0 errors at every level. *Stage 10 (superseded): "between 10 and 60"* |
| 10 % pro/studio with Tier-2 | **60** — every target met (Stage 12 Tranche 3 ramp) | 60 authors × 3 min: 321 requests, 0 errors; rewrite p95 6.1 s, Q&A p95 8.0 s, search p95 0.84 s. A 3-minute ramp level, not a settled 4-minute validation like the free-plan figure |

An **active author** is one using AI tools continuously: one AI action every ~30 s (15–45 s), 70 % rewrite tools (tone / refine / style), 20 % Plot Assistant questions, 10 % semantic search, on an indexed manuscript. An author writing without AI costs almost nothing, so the number of *signed-in* authors a pod supports is several times higher; the active count is the one to plan by.

**Tier-2 in one sentence (2026-10-03):** with half of active authors on strict consistency, the pod serves up to about **15** active authors with acceptable rewrite and Q&A latency, but semantic search's p95 exceeds its 1 s target (median under 0.2 s). With 10 % on Tier-2, the free-plan figure of **60** holds. **The onboarding limit stays a product-owner decision (MV-10.8); these numbers do not set it.**

**Onboarding limit (proposed, product owner to accept — MV-10.8):** at most **60 authors simultaneously active**, i.e. with typical use (well under a third of signed-in authors active at the same moment) about **150–200 registered authors per pod**, while fewer than 10 % of them are on pro/studio with strict consistency on. Re-measure before exceeding either figure.

## 2. Measurements (1 × A40, vLLM 0.9.2, TP=1, BGE-M3 on CPU, one uvicorn worker)

Tool: `backend/scripts/perf/load_probe.py --phase ramp` against an isolated backend bound to `narratiq_test`. Stage 10 raw reports are kept with the Stage 10 report (not in the repository); Stage 12 Tranche 3 raw reports are in `docs/testing/performance/`.

| Run | Authors | Requests | Errors | Rewrite p50 / p95 | Q&A p50 / p95 | Search p50 / p95 | vLLM max waiting / running |
|---|---|---|---|---|---|---|---|
| Ramp (free) | 40 | 156 | 0 | 1.3 / 3.3 s | 2.8 / 3.8 s | 0.24 / 0.49 s | 0 / 8 |
| Ramp (free) | 60 | 226 | 0 | 1.4 / 3.7 s | 3.4 / 4.8 s | 0.28 / 0.70 s | 0 / 10 |
| Ramp (free) | 80 | 296 | 0 | 1.5 / 4.2 s | 3.2 / **9.7 s** | 0.34 / **1.8 s** | 0 / 13 |
| **Validation (free, settled, 4 min)** | **60** | **460** | **0** | **1.3 / 3.3 s** | **2.8 / 5.5 s** | **0.27 / 0.59 s** | 0 / 9 |
| Tier-2 50 % pro (settled) | 10 | 59 | 0 | 3.2 / 8.9 s | 2.8 / 4.4 s | 0.24 / 2.4 s | 0 / 3 |
| Tier-2 50 % pro (settled) | 60 | 267 | 0 | 6.2 / 16.6 s | 29.6 / **49.5 s** | 5.8 / **10.9 s** | 0 / 12 |
| *Stage 12 Tranche 3, 2026-10-03, pod `x0smrkvs4n6wpk`, same tool and architecture (BGE-M3 on CPU, one worker), nothing tuned:* | | | | | | | |
| Tier-2 50 % ramp (3 min/level) | 5 | 29 | 0 | 2.9 / 5.9 s | 1.5 / 1.5 s | 0.49 / **2.4 s** (4 samples) | 0 / 2 |
| Tier-2 50 % ramp | 10 | 52 | 0 | 3.0 / 7.1 s | 2.1 / 3.0 s | 0.26 / 0.74 s (4 samples) | 0 / 3 |
| Tier-2 50 % ramp | 20 | 92 | 0 | 9.2 / **17.9 s** | 8.9 / **25.9 s** | 4.8 / **9.7 s** | 0 / 5 |
| Tier-2 50 % ramp | 30 | 145 | 0 | 9.7 / **22.0 s** | 8.9 / **26.0 s** | 3.3 / **13.1 s** | 0 / 9 |
| Tier-2 50 % ramp | 40 | 184 | 0 | 7.4 / **21.9 s** | 16.8 / **48.7 s** | 7.5 / **10.7 s** | 0 / 11 |
| Tier-2 50 % ramp | 50 | 224 | 0 | 7.5 / **20.5 s** | 21.8 / **39.4 s** | 3.8 / **13.0 s** | 0 / 10 |
| **Tier-2 50 % validation (6 min, settled)** | **10** | 109 | 0 | 3.0 / 7.0 s | 1.5 / 3.1 s | 0.16 / **3.6 s** (9) | 0 / 3 |
| **Tier-2 50 % validation (6 min, settled)** | **15** | 165 | 0 | 3.1 / 7.4 s | 1.7 / 5.3 s | 0.19 / **1.2 s** (18) | 0 / 5 |
| Tier-2 10 % ramp | 20 | 111 | 0 | 2.9 / 4.7 s | 1.5 / 2.2 s | 0.17 / 0.52 s | 0 / 6 |
| Tier-2 10 % ramp | 40 | 220 | 0 | 2.8 / 5.2 s | 1.7 / 4.3 s | 0.28 / 0.83 s | 0 / 10 |
| Tier-2 10 % ramp | 60 | 321 | 0 | 3.0 / 6.1 s | 4.3 / 8.0 s | 0.29 / 0.84 s | 0 / 12 |

Targets used: approved concurrent p95 (S10-I) — rewrite ≤ 8 s, Q&A ≤ 10 s, search ≤ 1 s, no errors. Raw reports: `docs/testing/performance/stage-12-tranche3-{ramp-pro50,validate-pro50,ramp-pro10}.json`. Search samples are few at low levels (10 % of actions), so a single slow search decides the p95 there; the 6-minute validation exists to reduce that.

The first ramp's 10- and 20-author levels are excluded: they overlapped the background indexing of the 80 fresh test manuscripts and were slower than the 40- and 60-author levels, which is contamination, not capacity. The later runs wait 240 s after indexing ("settled").

## 3. What limits capacity

**Not the GPU.** vLLM never had a request waiting in any run (`num_requests_waiting` max 0; at most 13 running of a 256-sequence budget). Qwen2.5-7B on one A40 has large headroom.

**The CPU embedding path.** BGE-M3 runs on CPU through a 2-thread executor (`ai_service.py`) shared by Plot Assistant retrieval, semantic search, indexing and — the Tier-2 finding — the consistency check's similarity work. When it saturates, Q&A and search latency climbs steeply while vLLM idles (80 free authors; 60 authors with 50 % Tier-2). Tier-2's documented cost of "one extra LLM call, +861 ms" (D6) understates its capacity cost: at scale its embedding work is what hurts.

## 4. Scaling triggers

Scale out (a second pod or a larger one) **or** move BGE-M3 to the GPU when any of these holds for a working day:

* Plot Assistant p95 > 10 s or search p95 > 1 s (`/api/ops/metrics`, or a load probe);
* more than 40 authors routinely active at once (70 % of the validated figure — lead time);
* pro/studio Tier-2 users above 10 % of active authors;
* vLLM `num_requests_waiting` > 0 for 5 minutes (not seen yet — would mean the GPU became the limit).

**Cheapest next step, not taken in Stage 10 (production model placement is the product owner's decision):** `BGE_DEVICE=cuda`. Stage 9 measured ~2.3 GB VRAM for BGE-M3 against ~5.7 GB headroom on the A40. It targets exactly the bottleneck measured here; re-run the ramp afterwards to set new figures.

## 5. Re-measuring

```bash
# isolated backend on :8100 bound to narratiq_test (see docs/testing/stage-09-regression-results.md), then:
DATABASE_URL=…/narratiq_test python3 backend/scripts/perf/load_probe.py --base http://127.0.0.1:8100 \
  --phase ramp --ramp-levels 20,40,60,80 --ramp-seconds 180 --think 30 --settle 240 [--pro-share 0.5] --out ramp.json
```
