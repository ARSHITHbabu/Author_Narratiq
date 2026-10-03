# Stage 12.1 — PA-C6 / PA-H12 on a realistic long manuscript

The A13 follow-up: the 6-chapter fixture saturates recall at 1.0, so ranking had only been verified at rule level. Measured 2026-10-03 on the isolated `narratiq_test` database. No manuscript text left the pod: the fixture was written by the local vLLM.

## Fixture

- `backend/tests/fixtures/long_manuscript_pa.json`, built by `build_long_manuscript.py` from `long_manuscript_spec.py`.
- "The Saltmarsh Ledger": **40 chapters, 32,228 words, 144 chunks**, 8 characters.
- Prose is model-written from 40 beats. Planted **critical** and **decoy** paragraphs are inserted verbatim, and all 47 are verified placed.
- **14 scenarios:**
  - 12 PA-C6 (a specific fact);
  - 2 PA-H12 ("what major thing did X do"): `marr_major` and `ferris_major`.
- **Decoys** share vocabulary with the critical passage but answer differently: a suspicion, a rumour, a wrong person, an earlier false lead.

## Method

- **Indexing:** the production `summarize_and_embed_chapter`.
- **Retrieval:** the production Q&A path, `retrieve_chunks_from_store(top_k = 6 if a character is named, else 10; diversify_chapters=True)`. The name detector is the production one.
- **Acceptance criteria**, fixed before running from task 4.3's own wording:
  - **A:** the critical passage is delivered to the model.
  - **B:** the critical passage is ranked above every delivered decoy.
- **Scopes:**
  - full manuscript;
  - capped at the critical chapter (the D-1 default scope).
- **Script:** `backend/tests/measure_long_manuscript_ranking.py`.
- **Raw results:** `pa-long-manuscript-before.json`.

## Results

| Scope | A: delivered | B: above all decoys | Critical at rank 1 | Median latency |
|---|---:|---:|---:|---:|
| Full | **13/14** | **8/14** | 4/14 | 448 ms |
| Capped at critical chapter | **13/14** | **9/14** | 5/14 | 395 ms |

Failures:

| Scenario | Kind | Critical rank (full) | Decoys above |
|---|---|---:|---:|
| real_father | PA-C6 | 6 | 1 |
| lighthouse_dark | PA-C6 | 9 | 1 |
| rope_fire | PA-C6 | 9 | 2 |
| marisol_sinking | PA-C6 | 9 | 2 |
| customs_deal | PA-C6 | 2 (capped: 1, passes) | 1 |
| **marr_major** | PA-H12 | **not delivered** (not even in the cosine top 40) | 2 |

**Verdict:**
- **PA-C6:** recall holds (A: every PA-C6 critical passage is delivered). Ordering criterion B is **not met**: in 5 of 12 scenarios, one or more decoys are ranked above the critical passage.
- **PA-H12:** **1 of 2** passes. The abstract question "what major thing did Liesel Marr do" does not retrieve the poisoning passage.

## Root cause

**Embedding similarity, not a ranking-code defect.**
- **Production ranks track raw BGE-M3 cosine ranks.** The near-tie re-rank and the chapter quota did not cause any failure.
- **Decoys outscore the critical passages on cosine** because they share more surface vocabulary with the question. Example: the Marisol decoy scores 0.600; the critical passage 0.515.
- **The `marr_major` passage describes the act** (foxglove, a vial, Thorne's cup), with no word close to "major thing she did".

## Design option measured, not implemented

An offline blend tested whether chapter-summary relevance would help: chunk score = chunk cosine + w × chapter-summary cosine.

| w | A | B |
|---:|---:|---:|
| 0 (production) | 12/14 | 7/14 |
| 0.25 | 13/14 | 9/14 |
| 0.5 | 12/14 | 10/14 |
| 1.0 | 13/14 | 10/14 |

The w = 0 row is the offline pure-cosine replica (top 10 with no quota), so it differs slightly from the production row above.

The gain is partial and non-monotonic, and choosing w would be tuning to this fixture. **Not implemented.**
- **Options for the owner:**
  - a retrieval-design change (summary blend, query expansion, or a re-ranker);
  - accept the measured ordering as a known limitation. Recall is 13/14, and the model sees every delivered passage.

## Related objective evidence (PA-H10 / PA-H11 / PA-C9)

From `measure_long_manuscript_coverage.py`, raw results in `pa-long-manuscript-coverage-before.json`:

- **PA-H10 — revelations in the stored chapter summaries:** 4/7.
  - Missing: "on Marr's orders" (ch22), the "Ferris crest" (ch27), and the Jory Wake betrayal (ch34).
  - Investigating this found a **real defect**: `generate_chapter_summary` read only the first 8,000 characters of a chapter. It now covers the whole chapter in context-sized windows and merges them.
  - Live evidence: on a 4,034-word chapter the old code read 34 % of the text. A late revelation was captured 0/3 times before the fix and 3/3 after (`chapter-summary-truncation-before-after.json`).
  - The fixture chapters (~900 words) were never truncated, so their 3 omissions are the model's selection of what to summarise. They stay with the G7 human review.
- **PA-H11:** broad whole-story questions deliver passages from across the book (share of passages from chapters 21–40 per question: 0.7, 0.3, 0.6, 0.7 before; 0.8, 0.2, 0.6, 0.7 after; 7–9 distinct chapters each). The 0.2–0.3 question ("Summarize the main events") leans early, which is part of the G7 human review.
- **PA-C9:** chapters covered for a named character: Tobin 3/3, Crane 4/6, Ferris 4/5.

## Indexing time (defect found and fixed)

- **Before:** indexing 40 chapters took **2,653 s (44 min)**. One chapter alone took 29 s, of which embedding was 18.7 s.
- **Cause:**
  - the pod's cgroup CPU quota is **7.65 CPUs**, but torch sized its intra-op pool from the host (**48 threads**);
  - two BGE executor workers therefore ran ~96 threads on ~8 CPUs.
- **Micro-benchmark** (12 chunks, 2 workers): 48 threads **32.5 s**, 8 threads 7.1 s, 4 threads **2.4 s**.
- **Fix:** `ai_service.cpu_quota()` / `bge_cpu_threads()` set torch threads to quota ÷ BGE workers (4 on this pod) when BGE runs on CPU. Tests: `test_bge_cpu_threads.py`.
- **After:** the same 40 chapters indexed in **220 s** (from 2,653 s, 12× faster). Median Q&A retrieval latency 448 → **210 ms** (the question embedding uses the same pool).
- **Production effect:** the fix takes effect when the production backend next restarts. It was not restarted for this measurement.

## After the fixes (re-indexed with both fixes, same fixture)

Raw results: `pa-long-manuscript-after.json` and `pa-long-manuscript-coverage-after.json`.

| Scope | A: delivered | B: above all decoys | Rank 1 | Median latency |
|---|---:|---:|---:|---:|
| Full | 12/14 (before 13/14) | 7/14 (before 8/14) | 4/14 | 210 ms |
| Capped | 13/14 | 9/14 | 6/14 | 201 ms |

- **The embeddings are unchanged.** Every delivered passage has the same cosine score to three decimals before and after, so the thread fix did not alter vectors.
- **What moved:** the order within near-ties (< 0.02). That order comes from the importance tie-break, which counts `key_events` in the chapter summaries, and the model regenerated those on re-index.
- **The one scenario that changed outcome:** `second_ledger` (full scope). Its critical passage scored 0.486, against 0.490 and 0.494 for the passages around it, at the edge of the top 10. It fell out of the 10.
- **Conclusion:** on this manuscript, A is **12–13 of 14** and B is **7–8 of 14** from run to run. Both are bounded by embedding similarity, not by a code defect.
- **Coverage:** unchanged. PA-H10 is 4/7, missing the same three chapters; PA-C9 is unchanged.
