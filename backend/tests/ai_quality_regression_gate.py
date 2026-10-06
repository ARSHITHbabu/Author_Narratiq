"""
Stage 12.3 — task 6.5: variance-aware AI quality regression gate.

The invariant harness (tests/test_ai_quality_invariants.py) asserts each
invariant ONCE. With a non-deterministic model that cannot separate a real
regression from run-to-run variability: adventure-3's no-change case fails
about 1 run in 10 on unchanged code (awt-g-consistency.md addendum), so one red
run proves nothing. This gate runs every harness invariant N times through the
real API, treats each as a pass RATE, and compares it with a recorded baseline
of the same code path using a one-sided Fisher exact test.

Metric     : per-invariant pass count k of N trials (the harness's own assertions:
             locked segment byte-identical, no_change on already-suitable
             passages, no name violation, light strength not flagged,
             suggestions structurally valid).
Threshold  : ALARM when the observed rate is lower than the baseline's with
             one-sided Fisher exact p < ALPHA / (number of invariants)
             (Bonferroni, family-wise alpha 0.01). A rate equal to or above the
             baseline never alarms.
Sample size: N = 20 trials per invariant (default; --trials). With 11
             invariants (per-invariant alpha 0.0009) and a 20/20 baseline the gate
             alarms at <= 11/20 observed; 18/20 -> <= 7/20; 14/20 -> <= 3/20 (see
             `minimum_alarm_count`). It detects a collapse, not the documented
             1-in-10 wobble. N = 10 was rejected: a 14/20-like baseline (7/10)
             could then never alarm.
Variance   : modelled, not assumed away — the baseline is a recorded k/N of the
             same invariant on unchanged code, and the exact test accounts for
             the sampling noise of both runs.

Usage (live stack, allow-listed test database only):
  cd backend
  DATABASE_URL=…/narratiq_test python3 tests/ai_quality_regression_gate.py --record-baseline OUT.json
  DATABASE_URL=…/narratiq_test python3 tests/ai_quality_regression_gate.py --baseline B.json --out R.json
  # deliberate regression proof (in-process only; no source file is edited):
  DATABASE_URL=…/narratiq_test python3 tests/ai_quality_regression_gate.py --baseline B.json \\
      --inject-regression renamed-assessor-key --out R.json
Injections (2026-10-06 results in docs/testing/stage-12/stage-12.3/ai-quality-gate/):
  degraded-no-change          the Stage 12.1 "tightening" sentence — NO behaviour change on the
                              current code (20/20), so it cannot prove detection
  inverted-no-change-question question reworded to its opposite — the model still answers the
                              "already_suitable" field correctly; no behaviour change
  renamed-assessor-key        the prompt asks for a renamed JSON field the parser does not read
                              (prompt/code drift) — the assessor fails open; detected
Exit code: 0 no alarm, 1 ALARM (regression detected), 2 usage/setup error.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FAMILY_ALPHA = 0.01

# The deliberate degradation used by the Stage 12.1 proof (gate6-regression-
# detection.md): a realistic "tightening" of the no-change assessor that stops
# it protecting text that is already right. Applied by wrapping
# complete_structured for the no_change_assessment call only.
DEGRADED_NO_CHANGE = (" Passages almost never fully meet a target, so answer false "
                      "unless it is impossible to improve it at all.")


# ── statistics (exact, no external dependency) ──────────────────────────────

def fisher_one_sided_lower(k_obs: int, n_obs: int, k_base: int, n_base: int) -> float:
    """P(observed passes <= k_obs | both runs share one pass rate), conditioning
    on the total passes — the one-sided Fisher exact test for 'observed is worse'."""
    total = k_obs + k_base
    denom = math.comb(n_obs + n_base, total)
    lo = max(0, total - n_base)
    return sum(math.comb(n_obs, x) * math.comb(n_base, total - x)
               for x in range(lo, k_obs + 1)) / denom


def minimum_alarm_count(k_base: int, n_base: int, n_obs: int, alpha: float) -> int | None:
    """Largest observed pass count that still alarms (None if none can)."""
    hits = [k for k in range(n_obs + 1) if fisher_one_sided_lower(k, n_obs, k_base, n_base) < alpha]
    return max(hits) if hits else None


def evaluate(baseline: dict, observed: dict, alpha_family: float = FAMILY_ALPHA) -> dict:
    keys = [k for k in observed if k in baseline]
    alpha = alpha_family / max(1, len(keys))
    rows, alarm = [], False
    for key in keys:
        kb, nb = baseline[key]["passes"], baseline[key]["trials"]
        ko, no = observed[key]["passes"], observed[key]["trials"]
        p = fisher_one_sided_lower(ko, no, kb, nb)
        worse = ko / no < kb / nb
        flagged = worse and p < alpha
        alarm |= flagged
        rows.append({"invariant": key, "baseline": f"{kb}/{nb}", "observed": f"{ko}/{no}",
                     "p_one_sided": round(p, 6), "alpha_per_invariant": round(alpha, 6),
                     "alarm_at_or_below": minimum_alarm_count(kb, nb, no, alpha), "ALARM": flagged})
    return {"alarm": alarm, "family_alpha": alpha_family, "rows": rows}


# ── probes: the harness's own invariants, one Bernoulli outcome per call ─────

def _probes():
    from tests.fixtures.transform_golden_set import PASSAGES
    by_id = {p["id"]: p for p in PASSAGES}
    probes = []
    for pid in sorted(p["id"] for p in PASSAGES if "lock_scenario" in p["tags"]):
        probes.append((f"locked_segment:{pid}", "lock", by_id[pid]))
    for pid in sorted(p["id"] for p in PASSAGES if any(t.startswith("already_suitable") for t in p["tags"])):
        probes.append((f"no_change:{pid}", "no_change", by_id[pid]))
    for pid, name in (("gothic-1", "Mira"), ("gothic-3", "Devika")):
        probes.append((f"names_preserved:{pid}", ("names", name), by_id[pid]))
    probes.append(("light_not_flagged:tech-1", "light", by_id["tech-1"]))
    probes.append(("suggestions_valid:adventure-1", "suggestions", by_id["adventure-1"]))
    return probes


def _run_once(client, headers, db, user_id, kind, passage) -> tuple[int, bool, str]:
    from models import Character, Chapter
    r = client.post("/api/projects/", headers=headers, json={"title": "AI quality regression gate"})
    sid = r.json()["story_id"]
    text = passage["text"]
    if kind == "lock":
        target = passage["lock_target"]
        s = text.index(target)
        r = client.post("/api/ai/tone", headers=headers, json={
            "story_id": sid, "text": text, "tone": "suspenseful", "strength": "strong",
            "locked_ranges": [{"start": s, "end": s + len(target)}]})
        return r.status_code, (r.status_code == 200 and target in r.json()["transformed"]), ""
    if kind == "no_change":
        target_age = "adult" if "adult" in passage["tags"][-1] else "ya"
        r = client.post("/api/ai/age-adapt", headers=headers, json={
            "story_id": sid, "text": text, "target_age": target_age})
        b = r.json() if r.status_code == 200 else {}
        return r.status_code, (b.get("no_change") is True and b.get("transformed", "").strip() == text.strip()), str(b.get("reason"))[:120]
    if isinstance(kind, tuple) and kind[0] == "names":
        db.add(Character(story_id=sid, user_id=user_id, name=kind[1], role="protagonist"))
        db.commit()
        r = client.post("/api/ai/tone", headers=headers, json={
            "story_id": sid, "text": text, "tone": "suspenseful", "strength": "strong"})
        return r.status_code, (r.status_code == 200 and r.json()["preservation_violations"] == []), ""
    if kind == "light":
        r = client.post("/api/ai/tone", headers=headers, json={
            "story_id": sid, "text": text, "tone": "suspenseful", "strength": "light"})
        return r.status_code, (r.status_code == 200 and r.json()["strength_violation"] is False), ""
    if kind == "suggestions":
        ch = db.query(Chapter).filter(Chapter.story_id == sid).first()
        ch.content = text
        db.commit()
        r = client.post("/api/ai/suggestions", headers=headers, json={
            "story_id": sid, "chapter_id": ch.chapter_id, "text": text})
        body = r.json() if r.status_code == 200 else {}
        items = body.get("suggestions", body if isinstance(body, list) else [])
        ok = bool(items) and all(s.get("priority") in ("high", "medium", "low") and s.get("observation")
                                 and s.get("recommendation") for s in items)
        return r.status_code, ok, ""
    raise ValueError(kind)


# A careless rewording of the assessor's question that inverts what it asks
# ("could it be improved?" instead of "is it already suitable?") while the JSON
# key stays "already_suitable" — the kind of prompt edit that looks harmless.
INVERTED_QUESTION = ("Question: could this passage be improved further for", "Question: is this passage ALREADY")

# A prompt edit that renames the JSON field the assessor must return while the
# parser still reads "already_suitable" — prompt and code out of step, the
# classic prompt regression. The assessor then fails open (rewrite anyway).
RENAMED_KEY = ('"needs_rewrite": true/false', '"already_suitable": true/false')

INJECTIONS = ("degraded-no-change", "inverted-no-change-question", "renamed-assessor-key")


def _inject(name: str | None):
    if not name:
        return
    if name not in INJECTIONS:
        sys.exit(f"unknown --inject-regression {name!r}")
    from services import ai_service
    original = ai_service.complete_structured

    async def degraded(system, user, *a, label=None, **k):
        if label == "no_change_assessment":
            if name == "degraded-no-change":
                system = system + DEGRADED_NO_CHANGE
            else:
                new, old = INVERTED_QUESTION if name == "inverted-no-change-question" else RENAMED_KEY
                assert old in system, "assessor prompt changed; update INVERTED_QUESTION"
                system = system.replace(old, new)
        return await original(system, user, *a, label=label, **k)

    ai_service.complete_structured = degraded


def run(trials: int, only: list[str] | None, inject: str | None) -> dict:
    from fastapi.testclient import TestClient
    import main
    from database import SessionLocal
    from models import User, Story
    from routers.auth import create_token, hash_password

    _inject(inject)
    # Measurement only: many identical requests from one fixture user would hit the
    # per-user AI rate limit (RATE_LIMIT_REALTIME_AI) and turn 429s into fake failures.
    # The tests disable the limiter the same way (test_cast_t2a.py); production is untouched.
    from middleware.rate_limit import limiter
    limiter.enabled = False
    db = SessionLocal()
    tag = uuid.uuid4().hex[:8]
    user = User(email=f"ai-quality-gate-{tag}@narratiq-internal-test.com", username=f"aiqgate{tag}",
                hashed_password=hash_password("x"))
    db.add(user)
    db.commit()
    headers = {"Authorization": f"Bearer {create_token(user.user_id)}"}
    results: dict = {}
    try:
        with TestClient(main.app) as client:
            for key, kind, passage in _probes():
                if only and not any(key.startswith(o) for o in only):
                    continue
                outcomes = []
                for _ in range(trials):
                    status, ok, note = _run_once(client, headers, db, user.user_id, kind, passage)
                    if status != 200:
                        # An HTTP error is an infrastructure fault, never a quality signal:
                        # counting it as a failed invariant would fake a regression.
                        raise RuntimeError(f"{key}: HTTP {status} — run invalid, not recorded")
                    outcomes.append({"pass": ok, "note": note})
                results[key] = {"passes": sum(o["pass"] for o in outcomes), "trials": trials,
                                "sequence": "".join("P" if o["pass"] else "f" for o in outcomes),
                                "fail_notes": [o["note"] for o in outcomes if not o["pass"]][:5]}
                print(f"  {key:34s} {results[key]['passes']:2d}/{trials}  {results[key]['sequence']}", flush=True)
    finally:
        for s in db.query(Story).filter(Story.user_id == user.user_id).all():
            db.delete(s)
        db.delete(db.query(User).filter(User.user_id == user.user_id).first())
        db.commit()
        db.close()
    return results


def _meta(trials: int, inject: str | None) -> dict:
    from config import settings
    try:
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True).stdout.strip())
    except Exception:
        head, dirty = "unknown", None
    return {"date": datetime.now(timezone.utc).isoformat(timespec="seconds"), "git_head": head,
            "tree_dirty": dirty, "trials": trials, "injected_regression": inject,
            "prompt_version": settings.prompt_version, "model": settings.vllm_model_name}


def main_cli(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--trials", type=int, default=20)
    ap.add_argument("--only", nargs="*", help="invariant key prefixes to run")
    ap.add_argument("--record-baseline", metavar="OUT")
    ap.add_argument("--baseline", metavar="BASELINE")
    ap.add_argument("--inject-regression", choices=list(INJECTIONS))
    ap.add_argument("--out", metavar="REPORT")
    a = ap.parse_args(argv)
    if bool(a.record_baseline) == bool(a.baseline):
        print("give exactly one of --record-baseline / --baseline", file=sys.stderr)
        return 2
    if a.record_baseline and a.inject_regression:
        print("a baseline must not be recorded with an injected regression", file=sys.stderr)
        return 2
    t0 = time.time()
    observed = run(a.trials, a.only, a.inject_regression)
    meta = {**_meta(a.trials, a.inject_regression), "seconds": round(time.time() - t0)}
    if a.record_baseline:
        Path(a.record_baseline).write_text(json.dumps({"meta": meta, "invariants": observed}, indent=2) + "\n")
        print(f"baseline recorded: {a.record_baseline}")
        return 0
    base = json.loads(Path(a.baseline).read_text())
    verdict = evaluate(base["invariants"], observed)
    report = {"meta": meta, "baseline_meta": base.get("meta"), "verdict": verdict, "invariants": observed}
    if a.out:
        Path(a.out).write_text(json.dumps(report, indent=2) + "\n")
    for row in verdict["rows"]:
        print(f"  {'ALARM' if row['ALARM'] else 'ok   '} {row['invariant']:34s} base {row['baseline']:>5s} "
              f"obs {row['observed']:>5s}  p={row['p_one_sided']:.4g} (alpha {row['alpha_per_invariant']:.4g})")
    print("REGRESSION ALARM" if verdict["alarm"] else "no regression detected")
    return 1 if verdict["alarm"] else 0


if __name__ == "__main__":
    sys.exit(main_cli())
