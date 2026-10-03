# Stage 12 remediation, Tranche 3: evidence (2026-10-03)

Pod `x0smrkvs4n6wpk` (1× A40), fresh reset (S12-D). Code: commit `f7a7a2e` plus the uncommitted Tranche 3 changes. Measurements ran on the isolated stack bound to `narratiq_test`, except the Gate 1/2/7 work, which used a disposable author on the live stack (deleted afterwards).

| Item | Files |
|---|---|
| A19: prompt fence / injection re-measurement | `injection-probe-tranche3.json` (17 features, 0 obeyed), `legit-rewrite-probe-tranche3.json` (84/84, 0 refused), `clean-prose-probe-tranche3.json` (60/60, 0 refused). Write-up: `docs/testing/stage-09-security-findings.md`, Tranche 3 addendum |
| A20: MV-5.14-A/B/C (Stage 5 guide, section C) | `mv-5.14-a-before-fix.json` (failed: marked flashback reported 3/3), `mv-5.14-a.json` (after the fix: pass), `mv-5.14-b.json` + `mv-5.14-b-section.png` (pass), `mv-5.14-c.json` + `mv-5.14-c-section.png` (pass; one pair, one change). Harness: `backend/scripts/quality/mv514_live.py` |
| A21: audio transcription | `transcript-cleanup-before.json` / `-after.json` (the clean-up dropped dictated sentences 19/20 → 0/40 after the fix). Spec and fixture: `frontend/tests/browser/audio-transcription.spec.ts`, `frontend/tests/browser/fixtures/audio/` |
| A22: rollback rehearsal | `a22-rollback-old-ui.png` (the previous release's UI on the restored data). Record: `docs/operations/rollback.md` §6 |
| A23: Tier-2 capacity | `docs/testing/performance/stage-12-tranche3-{ramp-pro50,validate-pro50,ramp-pro10}.json`. Write-up: `docs/operations/capacity-planning.md` |
| A24: Gates 1, 2, 7 | `gates-1-2-7.md`, `gate1-verify-runpod-setup.log`, `gate2-live-workflows.json`, `gate7-restore-steps.log`, `gate7-last-verify.json` |
| Addendum: empty-database guard | `scripts/backup_evidence.py`, `scripts/tests/test_startup_backup_guard.py` (A–E, C2–C4, unit). Write-up: the Tranche 3 final addendum |
| Addendum: cast live variability | `cast-variability-probe.json` (25 live runs, raw model output plus final cast per run; 21/25 pass). Probe: `backend/scripts/quality/cast_variability_probe.py` |
