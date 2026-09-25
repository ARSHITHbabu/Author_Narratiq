"""
Hermetic tests for scripts/verify_runpod_setup.sh (Stage 2, tasks 2.5/2.6).

Runs the real script against local HTTP stubs standing in for vLLM, the backend,
the frontend, the RunPod GraphQL API and the RunPod proxy. Nothing leaves
127.0.0.1:
  * every outbound proxy variable points at a closed loopback port, so a request
    to a real host would fail instead of silently reaching the network;
  * a `curl` shim on PATH logs every URL the script requests, and each test
    asserts that every one of them is a loopback URL.

Standard library only (no pytest, no database) — deliberately kept out of
backend/tests, whose conftest requires a disposable test database.

Run:  python3 -m unittest discover -s scripts/tests -v
"""
import json
import os
import shutil
import socket
import stat
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "verify_runpod_setup.sh"

API_KEY = "rpa_TESTKEY_SENTINEL_d0e1f2a3b4c5"  # must never appear in any output or argv
POD_ID = "testpod123"


class Stub:
    """A tiny HTTP server: routes map (method, path) -> (status, body)."""

    def __init__(self, routes):
        self.routes = routes
        self.requests = []
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def _serve(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length).decode() if length else ""
                stub.requests.append({"method": self.command, "path": self.path,
                                      "headers": dict(self.headers), "body": body})
                status, payload = stub.routes.get((self.command, self.path), (404, ""))
                data = payload.encode() if isinstance(payload, str) else json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            do_GET = _serve
            do_POST = _serve

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def runpod_ports(*pairs):
    return {"data": {"pod": {"id": POD_ID, "runtime": {"ports": [
        {"privatePort": p, "publicPort": 60000 + i, "type": t} for i, (p, t) in enumerate(pairs)]}}}}


HEALTHY_BACKEND = {"status": "ok", "backend": "ready", "vllm": "ready", "bge_m3": "ready"}


class VerifyScriptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="verify-runpod-"))
        self.stubs = []
        # curl shim: log each URL argument, then run the real curl.
        real_curl = shutil.which("curl")
        self.assertIsNotNone(real_curl, "curl is required")
        shim_dir = self.tmp / "bin"
        shim_dir.mkdir()
        self.curl_log = self.tmp / "curl-urls.log"
        shim = shim_dir / "curl"
        shim.write_text(
            "#!/bin/bash\n"
            "for a in \"$@\"; do case \"$a\" in http://*|https://*) echo \"$a\" >> \"%s\" ;; esac; done\n"
            "printf '%%s\\n' \"$*\" >> \"%s\"\n"
            "exec \"%s\" \"$@\"\n" % (self.curl_log, self.tmp / "curl-argv.log", real_curl))
        shim.chmod(shim.stat().st_mode | stat.S_IEXEC)
        self.path = f"{shim_dir}:{os.environ.get('PATH', '')}"

    def tearDown(self):
        for s in self.stubs:
            s.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def stub(self, routes):
        s = Stub(routes)
        self.stubs.append(s)
        return s

    def healthy_stack(self, backend_health=None, vllm_health_status=200):
        vllm = self.stub({("GET", "/health"): (vllm_health_status, ""),
                          ("POST", "/v1/completions"): (200, {"choices": [{"text": "OK"}]})})
        backend = self.stub({("GET", "/api/health"): (200, backend_health or HEALTHY_BACKEND)})
        frontend = self.stub({("GET", "/"): (200, "<html></html>")})
        return vllm, backend, frontend

    def run_script(self, *args, vllm=None, backend=None, frontend=None, env_extra=None, allowed_external=()):
        env = {
            "PATH": self.path,
            "HOME": str(self.tmp),
            "MODEL_BASE_DIR": str(self.tmp / "models"),
            "VLLM_PORT": str(vllm.port if vllm else free_port()),
            "BACKEND_PORT": str(backend.port if backend else free_port()),
            "FRONTEND_PORT": str(frontend.port if frontend else free_port()),
            # Hermetic: any request to a non-loopback host goes to a closed port.
            "HTTPS_PROXY": "http://127.0.0.1:9", "https_proxy": "http://127.0.0.1:9",
            "HTTP_PROXY": "http://127.0.0.1:9", "http_proxy": "http://127.0.0.1:9",
            "ALL_PROXY": "http://127.0.0.1:9", "all_proxy": "http://127.0.0.1:9",
            "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost",
        }
        env.update(env_extra or {})
        proc = subprocess.run(["bash", str(SCRIPT), *args], env=env, capture_output=True,
                              text=True, timeout=300, cwd=str(self.tmp))
        out = proc.stdout + proc.stderr
        self.assert_only_loopback(allowed_external)
        self.assertNotIn(API_KEY, out, "RunPod API key leaked into script output")
        argv_log = self.tmp / "curl-argv.log"
        if argv_log.exists():
            self.assertNotIn(API_KEY, argv_log.read_text(), "RunPod API key appeared in curl argv")
        return proc.returncode, out

    def assert_only_loopback(self, allowed_external=()):
        if not self.curl_log.exists():
            return
        for url in self.curl_log.read_text().split():
            if url in allowed_external:
                continue  # requested, but routed into the closed loopback proxy port
            self.assertTrue(url.startswith(("http://127.0.0.1", "http://localhost")),
                            f"script requested a non-loopback URL: {url}")

    def runpod_env(self, api=None, proxy=None, key=True):
        env = {"RUNPOD_POD_ID": POD_ID}
        if key:
            env["RUNPOD_API_KEY"] = API_KEY
        if api:
            env["RUNPOD_API_URL"] = f"http://127.0.0.1:{api.port}/graphql"
        if proxy:
            env["RUNPOD_PROXY_URL_TEMPLATE"] = f"http://127.0.0.1:{proxy.port}/proxy-{{port}}"
        return env

    def proxy_stub(self, frontend_port, backend_port, code_fe=200, code_be=200):
        return self.stub({("GET", f"/proxy-{frontend_port}/"): (code_fe, "<html></html>"),
                          ("GET", f"/proxy-{backend_port}/api/health"): (code_be, HEALTHY_BACKEND)})

    # ── P1 / H1(c): healthy stack, strict mode ────────────────────────────────
    def test_p1_healthy_stack_strict_mode_reports_ok(self):
        vllm, backend, frontend = self.healthy_stack()
        api = self.stub({("POST", "/graphql"): (
            200, runpod_ports((22, "tcp"), (frontend.port, "http"), (backend.port, "http")))})
        proxy = self.proxy_stub(frontend.port, backend.port)
        code, out = self.run_script("--expect-running", vllm=vllm, backend=backend, frontend=frontend,
                                    env_extra=self.runpod_env(api, proxy))
        for line in [f"[OK]  vLLM is listening on {vllm.port} and reports healthy",
                     f"[OK]  Backend is listening on {backend.port} and /api/health reports ok",
                     "[OK]  Backend reports vLLM as ready (not degraded)",
                     "[OK]  Backend reports BGE-M3 as ready",
                     f"[OK]  Frontend is listening on {frontend.port} and returns HTTP 200",
                     f"[OK]  Frontend proxy ({frontend.port}) reachable — HTTP 200",
                     f"[OK]  Backend proxy ({backend.port}) reachable — HTTP 200",
                     f"[OK]  Port {frontend.port} is exposed as an HTTP port on pod {POD_ID}",
                     f"[OK]  Port {backend.port} is exposed as an HTTP port on pod {POD_ID}",
                     "[OK]  vLLM generation smoke test passed"]:
            self.assertIn(line, out)
        for section_word in ["vLLM", "Backend", "Frontend", "proxy", "Port "]:
            self.assertNotIn(f"[FAIL] {section_word}", out)
        self.assertEqual(sorted(r["path"] for r in proxy.requests),
                         sorted([f"/proxy-{frontend.port}/", f"/proxy-{backend.port}/api/health"]))
        # The key reached the API only as a header.
        graphql = [r for r in api.requests if r["path"] == "/graphql"]
        self.assertEqual(len(graphql), 1)
        self.assertEqual(graphql[0]["headers"].get("Authorization"), f"Bearer {API_KEY}")
        self.assertNotIn(API_KEY, graphql[0]["path"])
        self.assertEqual(json.loads(graphql[0]["body"])["variables"], {"id": POD_ID})

    # ── H1(a)/(b): stopped service, strict vs default mode ────────────────────
    def test_h1a_strict_mode_stopped_frontend_fails(self):
        vllm, backend, _ = self.healthy_stack()
        dead = free_port()
        code, out = self.run_script("--expect-running", vllm=vllm, backend=backend,
                                    env_extra={"FRONTEND_PORT": str(dead)})
        self.assertIn(f"[FAIL] Frontend (port {dead}) — NOT RUNNING, but --expect-running was given", out)
        self.assertEqual(code, 1)

    def test_h1a_strict_mode_via_env_var(self):
        vllm, backend, _ = self.healthy_stack()
        dead = free_port()
        code, out = self.run_script(vllm=vllm, backend=backend,
                                    env_extra={"FRONTEND_PORT": str(dead), "EXPECT_RUNNING": "1"})
        self.assertIn(f"[FAIL] Frontend (port {dead}) — NOT RUNNING", out)
        self.assertEqual(code, 1)

    def test_h1b_default_mode_stopped_frontend_only_warns(self):
        vllm, backend, _ = self.healthy_stack()
        dead = free_port()
        code, out = self.run_script(vllm=vllm, backend=backend, env_extra={"FRONTEND_PORT": str(dead)})
        self.assertIn(f"[WARN] Frontend (port {dead}) — NOT STARTED (run: bash start-narratiq.sh)", out)
        self.assertNotIn(f"[FAIL] Frontend (port {dead})", out)

    def test_h1_strict_mode_stale_vllm_port_fails(self):
        # The reviewer's non-disruptive MV-2.6-B case: point VLLM_PORT at a dead port.
        _, backend, frontend = self.healthy_stack()
        dead = free_port()
        code, out = self.run_script("--expect-running", backend=backend, frontend=frontend,
                                    env_extra={"VLLM_PORT": str(dead)})
        self.assertIn(f"[FAIL] vLLM (port {dead}) — NOT RUNNING", out)
        self.assertEqual(code, 1)

    def test_h1_proxy_502_is_fail_in_strict_mode_warn_in_default(self):
        vllm, backend, frontend = self.healthy_stack()
        proxy = self.proxy_stub(frontend.port, backend.port, code_fe=502)
        env = self.runpod_env(proxy=proxy, key=False)
        _, strict = self.run_script("--expect-running", vllm=vllm, backend=backend, frontend=frontend, env_extra=env)
        self.assertIn(f"[FAIL] Frontend proxy ({frontend.port}) is exposed but nothing answers behind it (HTTP 502)", strict)
        _, default = self.run_script(vllm=vllm, backend=backend, frontend=frontend, env_extra=env)
        self.assertIn(f"[WARN] Frontend proxy ({frontend.port}) exposed but nothing listening yet (HTTP 502)", default)
        self.assertNotIn(f"[FAIL] Frontend proxy ({frontend.port})", default)

    # ── N1 / N2: broken services ──────────────────────────────────────────────
    def test_n1_backend_reports_vllm_unavailable(self):
        vllm, backend, frontend = self.healthy_stack(
            backend_health={"status": "ok", "vllm": "unavailable", "bge_m3": "ready"})
        code, out = self.run_script(vllm=vllm, backend=backend, frontend=frontend)
        self.assertIn("[FAIL] Backend is up but reports vLLM NOT ready — every AI endpoint will return 503", out)
        self.assertEqual(code, 1)

    def test_n2_vllm_listening_but_health_500(self):
        vllm, backend, frontend = self.healthy_stack(vllm_health_status=500)
        code, out = self.run_script(vllm=vllm, backend=backend, frontend=frontend)
        # Before 2026-09-25 the probe used `curl -s` without -f, so an HTTP 500 counted as healthy.
        self.assertNotIn(f"[OK]  vLLM is listening on {vllm.port} and reports healthy", out)
        self.assertIn(f"[FAIL] vLLM is listening on {vllm.port} but /health did not respond with success", out)
        self.assertEqual(code, 1)

    # ── N3 / N4: RunPod port list ─────────────────────────────────────────────
    def test_n3_port_8000_missing_from_runpod_list_fails(self):
        api = self.stub({("POST", "/graphql"): (200, runpod_ports((22, "tcp"), (3000, "http")))})
        code, out = self.run_script(env_extra={**self.runpod_env(api), "FRONTEND_PORT": "3000",
                                               "BACKEND_PORT": "8000",
                                               "RUNPOD_PROXY_URL_TEMPLATE": "http://127.0.0.1:9/p-{port}"})
        self.assertIn(f"[OK]  Port 3000 is exposed as an HTTP port on pod {POD_ID}", out)
        self.assertIn(f"[FAIL] Port 8000 is NOT exposed as an HTTP port on pod {POD_ID}", out)
        self.assertEqual(code, 1)

    def test_n4_exact_port_matching_30000_is_not_3000(self):
        api = self.stub({("POST", "/graphql"): (200, runpod_ports((30000, "http"), (8000, "http")))})
        code, out = self.run_script(env_extra={**self.runpod_env(api), "FRONTEND_PORT": "3000",
                                               "BACKEND_PORT": "8000",
                                               "RUNPOD_PROXY_URL_TEMPLATE": "http://127.0.0.1:9/p-{port}"})
        self.assertIn(f"[FAIL] Port 3000 is NOT exposed as an HTTP port on pod {POD_ID}", out)
        self.assertIn(f"[OK]  Port 8000 is exposed as an HTTP port on pod {POD_ID}", out)
        self.assertEqual(code, 1)

    def test_n4b_tcp_only_exposure_is_not_http(self):
        api = self.stub({("POST", "/graphql"): (200, runpod_ports((3000, "tcp"), (8000, "http")))})
        _, out = self.run_script(env_extra={**self.runpod_env(api), "FRONTEND_PORT": "3000",
                                            "BACKEND_PORT": "8000",
                                            "RUNPOD_PROXY_URL_TEMPLATE": "http://127.0.0.1:9/p-{port}"})
        self.assertIn(f"[FAIL] Port 3000 is NOT exposed as an HTTP port on pod {POD_ID}", out)

    # ── N5 / N6: undeterminable answers degrade to WARN ───────────────────────
    def _assert_port_check_warns_only(self, api_routes):
        api = self.stub(api_routes)
        _, out = self.run_script(env_extra={**self.runpod_env(api),
                                            "RUNPOD_PROXY_URL_TEMPLATE": "http://127.0.0.1:9/p-{port}"})
        self.assertIn("could not determine the exposed-port list".lower(), out.lower())
        self.assertNotIn("[FAIL] Port ", out)

    def test_n5_graphql_errors_warn(self):
        self._assert_port_check_warns_only({("POST", "/graphql"): (200, {"errors": [{"message": "unauthorized"}]})})

    def test_n5_http_401_warns(self):
        self._assert_port_check_warns_only({("POST", "/graphql"): (401, "unauthorized")})

    def test_n5_non_json_warns(self):
        self._assert_port_check_warns_only({("POST", "/graphql"): (200, "<html>oops</html>")})

    def test_n5_unexpected_shape_warns(self):
        self._assert_port_check_warns_only({("POST", "/graphql"): (200, {"data": {"pod": {"ports": "3000/http"}}})})

    def test_n6_no_api_key_skips(self):
        _, out = self.run_script(env_extra=self.runpod_env(key=False, proxy=None) | {
            "RUNPOD_PROXY_URL_TEMPLATE": "http://127.0.0.1:9/p-{port}"})
        self.assertIn("[WARN] RUNPOD_POD_ID or RUNPOD_API_KEY not set — skipping the RunPod port-list check", out)

    # ── L1: test seams refuse non-https, non-loopback targets ─────────────────
    def test_l1_plain_http_api_url_refused(self):
        _, out = self.run_script(env_extra={**self.runpod_env(), "RUNPOD_API_URL": "http://example.com/graphql",
                                            "RUNPOD_PROXY_URL_TEMPLATE": "http://127.0.0.1:9/p-{port}"})
        self.assertIn("RUNPOD_API_URL must be https:// or http://127.0.0.1 — refusing to send the API key there", out)

    def test_l1_plain_http_proxy_template_refused(self):
        _, out = self.run_script(env_extra={"RUNPOD_POD_ID": POD_ID,
                                            "RUNPOD_PROXY_URL_TEMPLATE": "http://example.com/{port}"})
        self.assertIn("RUNPOD_PROXY_URL_TEMPLATE must be https:// or http://127.0.0.1", out)

    # ── B1: detection without ss/netstat (regression for the false pass) ──────
    def test_b1_listening_service_detected_without_ss_or_netstat(self):
        if shutil.which("ss") or shutil.which("netstat"):
            self.skipTest("ss/netstat present: this host exercises the ss/netstat branch instead")
        vllm, backend, frontend = self.healthy_stack()
        _, out = self.run_script(vllm=vllm, backend=backend, frontend=frontend)
        self.assertIn(f"[OK]  Frontend is listening on {frontend.port} and returns HTTP 200", out)
        self.assertNotIn("— NOT STARTED (run", out)

    # ── E1: NEXT_PUBLIC_API_URL drift ─────────────────────────────────────────
    def test_e1_os_next_public_api_url_drift_warns(self):
        env_local = REPO / "frontend" / ".env.local"
        current = env_local.read_text().strip().split("=", 1)[1] if env_local.exists() else None
        _, out = self.run_script(env_extra={"NEXT_PUBLIC_API_URL": "https://STALE-SENTINEL.invalid"})
        self.assertIn("[WARN] NEXT_PUBLIC_API_URL is set in the OS environment (https://STALE-SENTINEL.invalid)", out)
        if current is None:
            self.assertIn("differs from frontend/.env.local (<not set>)", out)

    def test_e1_no_os_override_is_ok(self):
        _, out = self.run_script()
        self.assertIn("[OK]  No OS-level NEXT_PUBLIC_API_URL override", out)

    # ── Production proxy URL shape (request is sent into the closed loopback proxy) ─
    def test_default_proxy_url_shape(self):
        fe, be = free_port(), free_port()
        expected = (f"https://{POD_ID}-{fe}.proxy.runpod.net/", f"https://{POD_ID}-{be}.proxy.runpod.net/api/health")
        _, out = self.run_script(env_extra={"RUNPOD_POD_ID": POD_ID, "FRONTEND_PORT": str(fe),
                                            "BACKEND_PORT": str(be)}, allowed_external=expected)
        self.assertEqual(sorted(self.curl_log.read_text().split()), sorted(expected))
        self.assertIn(f"[FAIL] Frontend proxy ({fe}) — no response", out)  # closed proxy: nothing left the host

    # ── CLI ───────────────────────────────────────────────────────────────────
    def test_unknown_argument_rejected(self):
        code, out = self.run_script("--bogus")
        self.assertEqual(code, 2)
        self.assertIn("Unknown argument: --bogus", out)


if __name__ == "__main__":
    unittest.main()
