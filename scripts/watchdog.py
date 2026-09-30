#!/usr/bin/env python3
"""
NarratIQ pod watchdog (Stage 10, task 10.2; decisions S10-C/S10-D).

Runs next to the stack (started by start-narratiq.sh) and turns the backend's
own signals into alerts, so a degraded pod is noticed by monitoring rather
than by an author.

Checks
  every CHECK_INTERVAL (30 s)   GET /api/health
      backend_unreachable   the API does not answer at all
      vllm_unavailable      health says "vllm":"unavailable" (the backend now
                            probes vLLM live, so this catches vLLM dying after
                            startup — the "degraded mode" PG-03 describes)
      embeddings_not_ready  health says "bge_m3" is not ready
  every METRICS_INTERVAL (60 s) GET /api/ops/metrics   (needs OPS_TOKEN)
      ai_unavailable_rate   AI-unavailable 503s in the last 15 min ≥ threshold
      server_error_rate     5xx in the last 15 min ≥ threshold
      degraded_output_rate  share of AI parses that were salvaged/truncated/
                            failed since the previous check ≥ threshold
      background_job_failures  failed background jobs in the last 60 min ≥ threshold
      orphan_recovery       the last startup marked stuck jobs as failed
      backup_stale          newest on-pod dump older than BACKUP_MAX_AGE_HOURS
      backup_verify_failed  the last automated restore verification failed

A condition must hold for FAIL_THRESHOLD consecutive checks before it fires
(one blip is not an incident). Each alert fires once, repeats every
REPEAT_HOURS while still true, and sends a "resolved" message when it clears.

Where alerts go — provider-neutral, NO external service is configured here:
  * one JSON line per event appended to ALERT_LOG (default
    /workspace/logs/alerts.jsonl — on the persistent volume) and to stdout;
  * if NARRATIQ_ALERT_COMMAND is set, that command is run with the event JSON
    on stdin (e.g. a future mail or push script). A failing hook never stops
    the watchdog. Alert text is fixed and content-free: it never contains
    manuscript text, user data or secrets.
  * a heartbeat file (HEARTBEAT_FILE) is touched every loop, ready for an
    external dead-man's switch when one is chosen (deferred, S10-D).

Standard library only.  Usage:
    python3 scripts/watchdog.py            # run forever
    python3 scripts/watchdog.py --once     # one evaluation (tests, cron)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ENV = os.environ


def _f(name: str, default: float) -> float:
    try:
        return float(ENV.get(name, default))
    except ValueError:
        return default


BACKEND_URL = ENV.get("NARRATIQ_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
OPS_TOKEN = ENV.get("OPS_TOKEN", "")
CHECK_INTERVAL = _f("NARRATIQ_WATCHDOG_INTERVAL_SECONDS", 30)
METRICS_INTERVAL = _f("NARRATIQ_WATCHDOG_METRICS_INTERVAL_SECONDS", 60)
FAIL_THRESHOLD = int(_f("NARRATIQ_WATCHDOG_FAIL_THRESHOLD", 2))
REPEAT_HOURS = _f("NARRATIQ_WATCHDOG_REPEAT_HOURS", 6)
AI_UNAVAILABLE_15M = _f("NARRATIQ_ALERT_AI_UNAVAILABLE_15M", 5)
SERVER_ERRORS_15M = _f("NARRATIQ_ALERT_SERVER_ERRORS_15M", 5)
DEGRADED_RATE = _f("NARRATIQ_ALERT_DEGRADED_RATE", 0.30)
DEGRADED_MIN_CALLS = _f("NARRATIQ_ALERT_DEGRADED_MIN_CALLS", 10)
JOB_FAILURES_60M = _f("NARRATIQ_ALERT_JOB_FAILURES_60M", 3)
BACKUP_MAX_AGE_HOURS = _f("NARRATIQ_ALERT_BACKUP_MAX_AGE_HOURS", 3)
LOG_DIR = Path(ENV.get("NARRATIQ_PERSISTENT_LOG_DIR", "/workspace/logs"))
ALERT_LOG = Path(ENV.get("NARRATIQ_ALERT_LOG", str(LOG_DIR / "alerts.jsonl")))
STATE_FILE = Path(ENV.get("NARRATIQ_WATCHDOG_STATE", str(LOG_DIR / "watchdog-state.json")))
HEARTBEAT_FILE = Path(ENV.get("NARRATIQ_WATCHDOG_HEARTBEAT", str(LOG_DIR / "watchdog.heartbeat")))
ALERT_COMMAND = ENV.get("NARRATIQ_ALERT_COMMAND", "")
POD = ENV.get("RUNPOD_POD_ID", "local")

# Fixed, content-free wording per alert.
MESSAGES = {
    "backend_unreachable": ("critical", "The NarratIQ backend is not answering on /api/health."),
    "vllm_unavailable": ("critical", "vLLM is unavailable: AI features are returning errors to authors."),
    "embeddings_not_ready": ("high", "The embeddings model is not ready: search and retrieval are degraded."),
    "ai_unavailable_rate": ("high", "Many AI requests failed as unavailable in the last 15 minutes."),
    "server_error_rate": ("high", "The backend returned many server errors in the last 15 minutes."),
    "degraded_output_rate": ("medium", "A high share of AI outputs were degraded (salvaged, truncated or failed)."),
    "background_job_failures": ("medium", "Several background jobs failed in the last hour."),
    "orphan_recovery": ("medium", "The last backend start found interrupted jobs and marked them failed."),
    "backup_stale": ("high", "No recent on-pod database backup: the newest dump is too old or missing."),
    "backup_verify_failed": ("high", "The last automated backup restore verification failed."),
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get(path: str, headers: dict | None = None, timeout: float = 5.0):
    req = urllib.request.Request(BACKEND_URL + path, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:        # 503 degraded still carries a JSON body
        try:
            return e.code, json.loads(e.read() or b"null")
        except ValueError:
            return e.code, None
    except (urllib.error.URLError, OSError, ValueError):
        return None, None


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, ValueError):
        return {"streak": {}, "firing": {}, "last_parse": None, "last_orphan_at": None, "last_metrics": 0}


def save_state(state: dict) -> None:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state))
        tmp.replace(STATE_FILE)
    except OSError as exc:
        print(f"[watchdog] could not save state: {exc}", file=sys.stderr)


def emit(event: dict) -> None:
    line = json.dumps(event, sort_keys=True)
    print(f"[watchdog] {line}", flush=True)
    try:
        ALERT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with ALERT_LOG.open("a") as fh:
            fh.write(line + "\n")
    except OSError as exc:
        print(f"[watchdog] could not write alert log: {exc}", file=sys.stderr)
    if ALERT_COMMAND:
        try:
            subprocess.run(ALERT_COMMAND, shell=True, input=line.encode(), timeout=20, check=False)
        except Exception as exc:                # noqa: BLE001 — a broken hook must not stop monitoring
            print(f"[watchdog] alert command failed: {type(exc).__name__}", file=sys.stderr)


def settle(state: dict, conditions: dict[str, bool], evaluated: set[str]) -> None:
    """Apply one round of condition results: count streaks, fire, repeat, resolve."""
    now = time.time()
    for name in evaluated:
        active = conditions.get(name, False)
        streak = state["streak"].get(name, 0) + 1 if active else 0
        state["streak"][name] = streak
        severity, message = MESSAGES[name]
        firing = state["firing"].get(name)
        needed = 1 if name in ("orphan_recovery", "backup_verify_failed") else FAIL_THRESHOLD
        if active and streak >= needed:
            if firing is None or now - firing >= REPEAT_HOURS * 3600:
                emit({"ts": _now(), "pod": POD, "alert": name, "state": "firing",
                      "severity": severity, "message": message,
                      "repeat": firing is not None})
                state["firing"][name] = now
        elif not active and firing is not None:
            emit({"ts": _now(), "pod": POD, "alert": name, "state": "resolved",
                  "severity": severity, "message": "Resolved: " + message})
            del state["firing"][name]


def _degraded_share(prev: dict | None, cur: dict) -> tuple[float, int]:
    bad_keys = ("salvaged", "truncated", "failed")
    calls = bad = 0
    for feature, counts in (cur or {}).items():
        before = (prev or {}).get(feature, {})
        d_calls = counts.get("calls", 0) - before.get("calls", 0)
        if d_calls < 0:                       # backend restarted: counters reset
            d_calls, before = counts.get("calls", 0), {}
        calls += d_calls
        bad += sum(counts.get(k, 0) - before.get(k, 0) for k in bad_keys)
    return (bad / calls if calls else 0.0), calls


def check_once(state: dict) -> dict:
    conditions: dict[str, bool] = {}
    evaluated = {"backend_unreachable", "vllm_unavailable", "embeddings_not_ready"}
    code, body = _get("/api/health")
    conditions["backend_unreachable"] = code is None or not isinstance(body, dict)
    if isinstance(body, dict):
        conditions["vllm_unavailable"] = body.get("vllm") != "ready"
        conditions["embeddings_not_ready"] = body.get("bge_m3") != "ready"
    else:
        # Unknown while the backend itself is down — do not double-alert.
        evaluated -= {"vllm_unavailable", "embeddings_not_ready"}

    if OPS_TOKEN and time.time() - state.get("last_metrics", 0) >= METRICS_INTERVAL - 1:
        code, m = _get("/api/ops/metrics", headers={"X-Ops-Token": OPS_TOKEN}, timeout=10)
        if code == 200 and isinstance(m, dict):
            state["last_metrics"] = time.time()
            h15 = m.get("http", {}).get("last_15m", {})
            conditions["ai_unavailable_rate"] = h15.get("ai_unavailable", 0) >= AI_UNAVAILABLE_15M
            conditions["server_error_rate"] = h15.get("server_errors", 0) >= SERVER_ERRORS_15M
            share, calls = _degraded_share(state.get("last_parse"), m.get("ai_parse") or {})
            state["last_parse"] = m.get("ai_parse") or {}
            conditions["degraded_output_rate"] = calls >= DEGRADED_MIN_CALLS and share >= DEGRADED_RATE
            failures = sum(v.get("failed_last_60m", 0) for v in (m.get("background_jobs") or {}).values())
            conditions["background_job_failures"] = failures >= JOB_FAILURES_60M
            orphan = m.get("orphan_recovery") or {}
            new_orphans = bool(orphan.get("total")) and orphan.get("at") != state.get("last_orphan_at")
            conditions["orphan_recovery"] = new_orphans
            if orphan.get("at"):
                state["last_orphan_at"] = orphan.get("at")
            b = m.get("backups") or {}
            age = b.get("latest_dump_age_hours")
            conditions["backup_stale"] = bool(b.get("dir_exists")) and (age is None or age > BACKUP_MAX_AGE_HOURS)
            verify = b.get("last_verify") or {}
            conditions["backup_verify_failed"] = verify.get("result") == "FAIL"
            evaluated |= {"ai_unavailable_rate", "server_error_rate", "degraded_output_rate",
                          "background_job_failures", "orphan_recovery", "backup_stale",
                          "backup_verify_failed"}
    settle(state, conditions, evaluated)
    try:
        HEARTBEAT_FILE.parent.mkdir(parents=True, exist_ok=True)
        HEARTBEAT_FILE.write_text(_now() + "\n")
    except OSError:
        pass
    return conditions


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--once", action="store_true", help="evaluate once and exit")
    args = ap.parse_args()
    if not OPS_TOKEN:
        print("[watchdog] OPS_TOKEN not set: only /api/health is watched "
              "(rate, job and backup alerts are off).", flush=True)
    state = load_state()
    while True:
        check_once(state)
        save_state(state)
        if args.once:
            return 0
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    sys.exit(main())
