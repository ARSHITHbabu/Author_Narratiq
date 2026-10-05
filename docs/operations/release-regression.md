# Release regression procedure (CI waiver condition W-1)

**Why this exists.** There is no CI (task 6.1). The product owner waived CI for v3.3.0 **with a condition**
(2026-10-05, W-1): *the complete regression suite is run and recorded against the exact release candidate commit,
for every release, until CI is implemented.* A release without a record made by this procedure does not meet the
waiver. Record: `docs/releases/<version>-regression.md`.

## 1. Preconditions

1. **The release candidate is a commit.** Record `git rev-parse HEAD` and confirm `git status --short` is empty —
   a run on an uncommitted tree does not count. (Commits and tags are made by the owner.)
2. A running stack (`start-narratiq.sh`, or the backend-only restart in `rollback.md` §5a) on that commit.
3. The allow-listed test database `narratiq_test` exists, is at Alembic head and holds the seeded fixture
   (`backend/scripts/seed_fixture.py --reset`; see `docs/testing/stage-09-regression-results.md`). Never point a
   suite at the live `narratiq` database (the conftest guard refuses).
4. Dev requirements installed (`pip install -r backend/requirements-dev.txt`) and Playwright's Chromium
   (`cd frontend && npx playwright install --with-deps chromium`).

## 2. Run the suites — one at a time

Learned on 2026-10-05: **suites that share `narratiq_test` or the GPU must not run concurrently.** The migration
round trip downgrades the test schema and deadlocks behind any open test session; live-model tests (cast
extraction, AI invariants) vary when vLLM is shared with probes; a Playwright web server can miss its 10-minute
start window under load. A failure seen only under concurrent load is re-run alone before it is recorded.

```bash
cd <checkout>
export TEST_DATABASE_URL=postgresql+psycopg2://narratiq:narratiq@localhost:5432/narratiq_test
OUTDIR=/tmp/narratiq-release-regression bash backend/tests/run_full_regression.sh \
    backend known-defects retrieval migration ai-harness fe-unit fe-studio fe-a11y fe-variants docs-sync
```

Then, also one at a time:

| Suite | How |
|---|---|
| Script tests (backup pipeline, startup guard, rollback script, verifier) | `python3 -m unittest discover -s scripts/tests` — the guard and pipeline tests need `narratiq_test` and a local PostgreSQL superuser; a run where they are *skipped* does not count |
| Live browser suite | Isolated stack exactly as in `docs/testing/stage-09-regression-results.md` "How the live browser suite was run": backend on :8100 bound to `narratiq_test` with raised test-only rate limits, frontend built with `NEXT_DIST_DIR=.next-e2e` on :3200, fixtures from `backend/scripts/seed_browser_fixtures.py`, `E2E_API_URL`/`E2E_BASE_URL` set, `--workers=1` |
| Prompt-injection probes | On the same isolated backend: `prompt_injection_probe.py`, `injection_coverage_probe.py`, `clean_prose_feature_probe.py`, `qa_injection_matrix.py` (default and `MATRIX_QUESTION="…in this chapter?"`), `qa_adversarial_probe.py` — all in `backend/scripts/security/` |
| Dependency audits | `pip-audit` on `backend/requirements.txt` and `npm audit` — compare with the owner-accepted advisories (S2–S6); anything new is a finding |

## 3. Pass rule

* Every automated suite: 0 failed (known xfails allowed and listed).
* Probes: 0 obeyed in every feature; chapter-scoped Q&A matrix 0 obeyed; clean prose 0 false refusals.
* Audits: no advisory beyond those accepted in S2–S6.
* A failure that reproduces when run alone blocks the release until fixed or decided by the owner. A failure that
  occurs only under load and passes alone is recorded with both results (for example the documented cast-extraction
  model variability, CAST-H10 class).

## 4. Record

`docs/releases/<version>-regression.md`: the commit hash, date, pod, each suite's command and result line
(`summary.txt`), every re-run and why, the probe JSON paths, the audit counts, and who ran it. The sign-off record
(`docs/releases/<version>-sign-off.md`) links it.
