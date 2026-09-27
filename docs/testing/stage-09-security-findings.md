# Stage 9 — Security and Isolation Findings (tasks 9.4, 9.5)

| | |
|---|---|
| **Date** | 2026-09-27, pod `6uavswo19trx9n` |
| **Severity bar** | D-6 (confirmed for Stage 9 by the product owner): Critical and High must be resolved before the 9.4 gate passes; Medium and Low may be documented and deferred |
| **Tests** | `backend/tests/test_cross_user_isolation.py` (11), `backend/tests/test_security_stage9.py` (30); probes `backend/scripts/security/prompt_injection_probe.py`, `backend/scripts/pip_audit_severity_gate.py` (existing), `npm audit` |

## Findings and status

| # | Finding | Severity | Status |
|---|---|---|---|
| I1 | `GET /api/intake/{story_id}/genre-profile` — no ownership check; any signed-in user could read another story's genre, tone, audience and writing direction | High | **Fixed** (`owned_story`); regression test |
| I2 | `POST /api/intake/{story_id}/confirm` — no ownership check; wrote the GenreProfile and scheduled analysis passes on another author's story | High | **Fixed**; regression test (B's rows unchanged) |
| I3 | `PATCH /api/plot-assistant/{session_id}/use` — session looked up by id only | Medium | **Fixed** (scoped to the caller); regression test |
| I4 | `GET …/chapters/{chapter_id}/versions[/{version_id}]` — owned `story_id` + foreign `chapter_id` returned another author's **full chapter version text** | Critical | **Fixed** (`_check_chapter_in_story`); regression test |
| I5 | Voice agent trusted client `context.story_id` / `chapter_id` — could put another story's names into vocabulary/clarification and load another author's chapter text into the prompt | High | **Fixed** (ownership in `services/voice/agent.py`; story-scoped chapter load in `context.py`; WS cleanup scoped by user); regression test |
| I6 | OCR confirm and note PATCH/DELETE answered 403 for a foreign id vs 404 for a missing one (existence oracle) | Low | **Fixed** (same 404); regression test |
| I7 | `POST /api/ai/translate/stream` accepted any `story_id` without checking it (no data used, but violates C7-6) | Low | **Fixed**; regression test |
| — | **Every id-bearing route swept** (144 of the 160 HTTP route/method pairs; the other 16 take no id) with another author's ids (path, query and body): no B data returned, no B data reached a model prompt, B's rows byte-identical across every table, foreign ids indistinguishable from missing ids | — | **PASS** |
| — | `StoryContextEngine.tsx:186` `can = () => true` | — | Display-only; the server refuses the same actions (`test_story_context_engine_seam_is_display_only`). Collaboration is not built |
| X1 | Story Intelligence router (`routers/story_intel.py`) indexed the `User` row as a dict → **every** route returned 500 for everyone since `b0f64be` (2026-06-08). Failed closed (no leak); found by the sweep | Medium (functional) | **Fixed** (`user.user_id`); covered by the sweep (404 for foreign, reachable for the owner) |
| S1 | Upload size guard ran after FastAPI had already received and spooled the whole multipart body; chunked uploads carried no Content-Length at all; `/api/voice/transcribe` had no pre-check | High | **Fixed** — `middleware/body_limit.py` caps the body while it streams (Content-Length and counted bytes), 413 in the existing format; tests for honest, chunked and understated bodies on all four upload routes |
| S2 | CORS `allow_origin_regex=https://.*\.proxy\.runpod\.net` with credentials trusted every RunPod pod | Medium | **Fixed** — only this pod's own proxy hosts (`RUNPOD_POD_ID`); verified live (own pod 200, another pod refused) |
| S3 | `AuthorStyleRequest.author` unbounded | Low | **Fixed** (`max_length=100`); registry resolution tested with adversarial input — raw input never reaches the prompt |
| J1 | No server-side JWT revocation; logout is client-side; 7-day default lifetime | Medium | **Documented, deferred to Stage 10** by decision (no migration approved). Expiry, signature, `alg=none`, wrong key, orphaned user all refused on every authenticated route (test) |
| R1 | Rate limits: in-memory, per process; correct at D-3's single worker (429 + `Retry-After` verified). IP-keyed limits see the RunPod proxy address; several read routes and `/api/plot-assistant/` carry no limit | Low | Documented |
| P1 | **Prompt injection via manuscript text** — Plot Assistant (3/3 runs) answered with the injected instruction instead of the question; Refine (3/3) replaced the author's passage with the canary and an invented "system prompt". Tone, suggestions, continuation, plot holes, continuity, manuscript report and story bible resisted. No real system prompt was disclosed (the "system prompt" text was invented). The author is the only source of their manuscript today (no sharing), so this corrupts the author's own result rather than exposing anyone else | **Medium** (proposed) — **decision needed** | Open. Fix is a prompt/AI-strategy change (delimit manuscript text as data; a code check that rejects a transform output that drops the source passage) and needs approval |
| D1 | Dependencies — **installed runtime** (`pip-audit` of the pod environment): 3 Critical (vLLM 0.9.2 ×2, jupyter-server), 63 High. Groups: vLLM/xgrammar/transformers (model stack); pyasn1/ecdsa (via python-jose); starlette/python-multipart are **newer than pinned** at runtime; pod-image packages not used by NarratIQ (jupyter*, tornado, mistune, nbconvert, cryptography 3.4.8, pyjwt 2.3.0, urllib3) | Critical/High | **Open — decision needed** (dependency changes need approval). Mitigation measured: vLLM :9001 is **not** reachable through the RunPod proxy (same 404 as an unused port); JupyterLab :8888 is exposed by the pod image but refuses unauthenticated API calls (403) |
| D2 | `requirements.txt` does not describe the runtime: `start-narratiq.sh` installs its own list and vLLM pulls FastAPI 0.141 / Starlette 1.7 / python-multipart 0.0.32 unpinned (pinned: 0.111 / 0.37 / 0.0.9). Auditing `requirements.txt` alone reports 25 High that are not what runs | Medium | Open — Stage 10 (one source of truth for the runtime) |
| D3 | `npm audit` (frontend): 1 Critical (`next` 14.x; fix only in 16.x), 14 High (mostly lint/build tooling: eslint-config-next, typescript-eslint, glob, minimatch; plus axios, postcss, form-data, nanoid) | Critical/High | **Open — decision needed** (framework major upgrade) |

## What passes and what does not

* **9.5 (isolation): passes.** Every cross-user attempt returns 404 (or a validation error before any lookup), never data — after the I1–I7 fixes. The "add to CI" item stays open with task 6.1 (CI deferred).
* **9.4 gate "no finding above the agreed threshold remains open": NOT met.** Open at or above High: D1 and D3
  (dependency advisories) — and P1 if the owner rates it High. Everything else at High or above is fixed.
