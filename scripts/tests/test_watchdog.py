"""
Hermetic tests for scripts/watchdog.py (Stage 10, task 10.2).

The real script runs as a subprocess against a loopback stub standing in for
the backend. Nothing leaves 127.0.0.1. Standard library only.

Run:  python3 -m unittest discover -s scripts/tests -v
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_verify_runpod_setup import Stub  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "watchdog.py"
TOKEN = "ops-test-token"

HEALTHY = {"status": "ok", "backend": "ready", "vllm": "ready", "bge_m3": "ready"}
DEGRADED = {"status": "degraded", "backend": "ready", "vllm": "unavailable", "bge_m3": "ready"}


def metrics(**over):
    m = {"http": {"last_15m": {"requests": 10, "server_errors": 0, "ai_unavailable": 0}},
         "ai_parse": {}, "background_jobs": {"story_bibles": {"failed_last_60m": 0, "in_progress": 0}},
         "orphan_recovery": {"at": "t0", "total": 0, "by_table": {}},
         "backups": {"dir_exists": True, "latest_dump_age_hours": 0.5, "last_verify": {"result": "PASS"}}}
    m.update(over)
    return m


class WatchdogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="watchdog-"))
        self.stub = None
        self.hook_out = self.tmp / "hook.jsonl"

    def tearDown(self):
        if self.stub:
            self.stub.close()

    def serve(self, health, health_code=200, m=None):
        if self.stub:
            self.stub.close()
        routes = {("GET", "/api/health"): (health_code, health)}
        if m is not None:
            routes[("GET", "/api/ops/metrics")] = (200, m)
        self.stub = Stub(routes)

    def run_once(self, token=True, hook=False, backend=None):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("NARRATIQ_", "OPS_"))}
        env.update({
            "NARRATIQ_BACKEND_URL": backend or f"http://127.0.0.1:{self.stub.port}",
            "NARRATIQ_PERSISTENT_LOG_DIR": str(self.tmp),
            "NARRATIQ_WATCHDOG_METRICS_INTERVAL_SECONDS": "0",
            "RUNPOD_POD_ID": "testpod",
            "http_proxy": "http://127.0.0.1:9", "https_proxy": "http://127.0.0.1:9", "no_proxy": "127.0.0.1",
        })
        if token:
            env["OPS_TOKEN"] = TOKEN
        if hook:
            env["NARRATIQ_ALERT_COMMAND"] = f"cat >> {self.hook_out}"
        r = subprocess.run([sys.executable, str(SCRIPT), "--once"], env=env, capture_output=True,
                           text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def alerts(self):
        f = self.tmp / "alerts.jsonl"
        return [json.loads(line) for line in f.read_text().splitlines()] if f.exists() else []

    def test_healthy_stack_raises_nothing(self):
        self.serve(HEALTHY, m=metrics())
        self.run_once()
        self.run_once()
        self.assertEqual(self.alerts(), [])
        self.assertTrue((self.tmp / "watchdog.heartbeat").exists())

    def test_vllm_down_alerts_after_two_checks_then_resolves(self):
        self.serve(DEGRADED, health_code=503, m=metrics())
        self.run_once(hook=True)
        self.assertEqual(self.alerts(), [], "one failed check must not fire")
        self.run_once(hook=True)
        fired = self.alerts()
        self.assertEqual([(a["alert"], a["state"]) for a in fired], [("vllm_unavailable", "firing")])
        self.assertEqual(fired[0]["severity"], "critical")
        self.assertEqual(fired[0]["pod"], "testpod")
        # The provider-neutral hook received exactly the same event.
        self.assertEqual(json.loads(self.hook_out.read_text().splitlines()[0])["alert"], "vllm_unavailable")
        self.run_once()                                   # still down: no duplicate
        self.assertEqual(len(self.alerts()), 1)
        self.serve(HEALTHY, m=metrics())
        self.run_once()
        self.assertEqual([(a["alert"], a["state"]) for a in self.alerts()][-1], ("vllm_unavailable", "resolved"))

    def test_backend_unreachable(self):
        self.serve(HEALTHY)
        dead = "http://127.0.0.1:9"                       # discard port — nothing listens
        self.run_once(token=False, backend=dead)
        self.run_once(token=False, backend=dead)
        self.assertEqual([a["alert"] for a in self.alerts()], ["backend_unreachable"])

    def test_metric_rules(self):
        bad = metrics(
            http={"last_15m": {"requests": 50, "server_errors": 9, "ai_unavailable": 7}},
            background_jobs={"story_bibles": {"failed_last_60m": 4, "in_progress": 0}},
            orphan_recovery={"at": "t1", "total": 2, "by_table": {"story_bibles": 2}},
            backups={"dir_exists": True, "latest_dump_age_hours": 30, "last_verify": {"result": "FAIL"}})
        self.serve(HEALTHY, m=bad)
        self.run_once()
        self.run_once()
        fired = {a["alert"] for a in self.alerts() if a["state"] == "firing"}
        self.assertEqual(fired, {"ai_unavailable_rate", "server_error_rate", "background_job_failures",
                                 "orphan_recovery", "backup_stale", "backup_verify_failed"})

    def test_degraded_output_share_uses_deltas(self):
        m1 = metrics(ai_parse={"tone": {"calls": 100, "clean": 100}})
        self.serve(HEALTHY, m=m1)
        self.run_once()
        m2 = metrics(ai_parse={"tone": {"calls": 120, "clean": 105, "salvaged": 10, "failed": 5}})
        self.serve(HEALTHY, m=m2)
        self.run_once()
        self.serve(HEALTHY, m=metrics(ai_parse={"tone": {"calls": 140, "clean": 105, "salvaged": 25, "failed": 10}}))
        self.run_once()
        self.assertIn("degraded_output_rate", {a["alert"] for a in self.alerts()})

    def test_alert_text_is_fixed_and_content_free(self):
        self.serve(DEGRADED, health_code=503, m=metrics())
        self.run_once()
        self.run_once()
        a = self.alerts()[0]
        self.assertEqual(set(a), {"ts", "pod", "alert", "state", "severity", "message", "repeat"})
        self.assertNotIn(TOKEN, json.dumps(a))


if __name__ == "__main__":
    unittest.main()
