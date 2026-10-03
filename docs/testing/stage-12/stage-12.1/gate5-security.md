# Gate 5 — Security checks: Stage 12.1 record

Exit criteria (Master Execution Plan §13):
- cross-user isolation verified (PG-14);
- auth and JWT lifecycle verified;
- upload guards not bypassable;
- rate limits effective at the target worker count;
- the `_AUTHOR_STYLES` safety registry holds under adversarial input;
- dependency scan clean.

## 1. Evidence per criterion

| Criterion | Evidence | Current? | Result |
|---|---|---|---|
| Cross-user isolation (PG-14) | `backend/tests/test_cross_user_isolation.py` (I1–I7 fixes, Stage 9) plus `test_security_stage9.py`; both in the backend suite: 1,142 passed / 0 failed (Tranche 3 final isolated run, 2026-10-03) | yes | **pass** |
| Auth / JWT lifecycle | Stage 10 task 10.7 (HttpOnly cookie, CSRF, revocation, `token_version`) and its tests in the same suite; Gate 1 2026-10-03: login and generation through the public proxy | yes | **pass** |
| Upload guards | `test_security_stage9.py` size and type checks; A8 import refuses unsupported or empty files; A21 audio upload live | yes | **pass** |
| Rate limits at the target worker count (1, D-3) | Stage 10 task 10.4 (closed); single-worker guard `startup/worker_guard.py`; isolated test stacks raise the limits deliberately, never the live one | yes | **pass** |
| `_AUTHOR_STYLES` safety under adversarial input | A19 (2026-10-03, current code): author-style 0/15 living authors named, 0 obeyed; probe output `docs/testing/stage-12/tranche3/injection-probe-tranche3.json` | yes | technically **pass**; the owner's review of the saved outputs and the legal review (11.7) are still open |
| Prompt injection (P1, part of 9.4) | A19: 0 obeyed in 17 features; 0 false refusals (84 rewrites, 60 clean-prose calls); replay and call-site regression tests | yes | technically **pass**; **the residual-risk rating is the owner's** |
| Dependency scan clean | §2 below | fresh 2026-10-03 | **not clean.** Every Critical/High is classified, with owner decisions needed |

## 2. Fresh dependency audits (2026-10-03, existing tooling)

Raw output is in this folder: `pip-audit-requirements*.{json,txt}`, `pip-audit-installed*.{json,txt}`, `npm-audit.json`, `npm-audit-prod.json`.

### 2.1 Backend `requirements.txt` (`pip-audit -r` + `pip_audit_severity_gate.py`)

**5 High, 0 Critical.** Unchanged from Tranche 1.

| Finding | Classification | Evidence |
|---|---|---|
| transformers 4.57.6 ×4 (PYSEC-2026-2289/2290/3929/4174) | **Unreachable.** The advisories need untrusted model, config or template files; every model is a local, revision-pinned download. The version is pinned by vLLM 0.9.2 | Tranche 1 addendum in `stage-09-security-findings.md` |
| ecdsa 0.19.2 (PYSEC-2026-1325, no fix) | **Unreachable.** JWTs use HS256 only; no EC key is ever parsed | same |

### 2.2 Installed Python runtime (`pip-audit` on the pod environment)

**4 Critical, 59 High.** The `requirements.vllm.txt` scan could not be resolved by `pip-audit -r` (dependency install failed in its temporary environment, `pip-audit-vllm.err`), so the installed environment, which includes vLLM, was audited instead (the Stage 9 D1 method).

| Group | Findings | Classification |
|---|---|---|
| vLLM 0.9.2 (2 Critical, 10 High), xgrammar (2 High), transformers (4 High) | model-serving stack | **Accepted limitation (owner decision 2026-10-02).** vLLM listens on 127.0.0.1 only (re-verified at Gate 1); the backend is its only client; the model is text-only. The upgrade is a separate future project |
| jupyter-server, jupyterlab, jupyter-core, nbconvert, mistune, tornado, pyjwt 2.3.0, httplib2, wheel, setuptools | pod image / system packages; not NarratIQ dependencies (pyjwt: NarratIQ uses `python-jose`) | **External: pod template.** JupyterLab answers 403 without authentication (Tranche 1); recommend removing Jupyter from the pod template |
| **lxml 5.3.0 (PYSEC-2026-87, XXE)** | used by `python-docx`, which parses author-uploaded `.docx` manuscripts | **Proven unreachable.** `python-docx` builds its parsers with `resolve_entities=False`; a crafted `.docx` with an external entity did not leak the file. See `lxml-xxe-reachability.md` |
| urllib3 2.2.3 (6 High) | `requests` / `sentry-sdk` only; NarratIQ's HTTP client is `httpx` | **Unreachable from author input.** Used only for trusted model downloads at bring-up. Hygiene upgrade candidate (minor version) |
| soupsieve 2.6 (2 High) | `beautifulsoup4` only; NarratIQ never imports it | **Unreachable** |

### 2.3 Frontend (`npm audit`)

| Scope | Result | Classification |
|---|---|---|
| Production dependencies (`--omit=dev`) | **0 Critical, 1 High** (32 Moderate) | `postcss` inside `next`: used at build time on the repository's own CSS. **Unreachable**, unchanged since Tranche 1. Moderates: TipTap 2.x and others, as Tranche 1 |
| All dependencies | 0 Critical, **8 High** (Tranche 1: 1) | The 7 new Highs come from one newly published advisory: `braces` (stack-exhaustion denial of service on deeply nested patterns), pulled in via `micromatch` / `chokidar` / `fast-glob` into **tailwindcss 3.x and eslint-config-next**, which are build and lint tooling only. Inputs are the repository's own files. **Unreachable at runtime.** The fix needs tailwindcss 4 (a major upgrade, not done per instruction) |

**Nothing applicable and technically actionable was found** that could be fixed without a major upgrade. The one exposure that looked reachable (lxml XXE through `.docx` import) was disproved by test.

## 3. Owner decisions needed for Gate 5

1. **P1 residual prompt-injection risk:** rate or accept it (`stage-09-security-findings.md`, Tranche 2b and Tranche 3 addenda).
2. **Dependency findings:** accept the classification above, or require upgrades.
   - transformers / ecdsa: unreachable.
   - vLLM: already accepted on 2026-10-02.
   - The new `braces` advisory in build tooling, and `postcss`: unreachable.
3. **Pod template:** remove JupyterLab and the other image packages (external).
4. **11.7:** the owner's review of the adversarial author-style outputs, and the legal review of the copyright disclaimer.

**Gate 5 status: TECHNICALLY PASSED — OWNER DECISION REQUIRED.**
