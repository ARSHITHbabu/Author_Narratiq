"""
Hermetic tests for scripts/rollback_frontend.sh (Stage 12 remediation A6).

The script must stop ONLY the server listening on FRONTEND_PORT, never every
Next.js process on the pod. Two loopback HTTP listeners stand in for "the
frontend" and "another Next.js server"; a fake `npm` on PATH stands in for
`npm start`. Nothing leaves 127.0.0.1. Standard library only.

Run:  python3 -m unittest discover -s scripts/tests -v
"""
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "rollback_frontend.sh"

# A listener whose command line looks like a Next.js server, so the old
# `pkill -f next-server` pattern would have matched (and killed) both.
SERVER = (
    "import http.server,sys\n"
    "class H(http.server.BaseHTTPRequestHandler):\n"
    "    def do_GET(self):\n"
    "        self.send_response(200); self.end_headers(); self.wfile.write(b'ok')\n"
    "    def log_message(self,*a): pass\n"
    "http.server.HTTPServer(('127.0.0.1', int(sys.argv[1])), H).serve_forever()\n"
)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_listening(port: int, up: bool = True, timeout: float = 10.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        with socket.socket() as s:
            listening = s.connect_ex(("127.0.0.1", port)) == 0
        if listening == up:
            return True
        time.sleep(0.1)
    return False


class RollbackFrontendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rollback-fe-"))
        self.fe = self.tmp / "frontend"
        (self.fe / ".next").mkdir(parents=True)
        (self.fe / ".next.prev").mkdir()
        (self.fe / ".next" / "BUILD_ID").write_text("NEW")
        (self.fe / ".next.prev" / "BUILD_ID").write_text("OLD")
        self.server_py = self.tmp / "next-server.py"
        self.server_py.write_text(SERVER)
        # Fake npm: `npm start -- --port N` starts a listener on N.
        bindir = self.tmp / "bin"
        bindir.mkdir()
        npm = bindir / "npm"
        npm.write_text(
            "#!/bin/bash\n"
            'port=""; while [ $# -gt 0 ]; do [ "$1" = "--port" ] && port="$2"; shift; done\n'
            f'exec {sys.executable} {self.server_py} "$port"\n'
        )
        npm.chmod(0o755)
        self.path = f"{bindir}:{os.environ['PATH']}"
        self.procs = []

    def tearDown(self):
        for p in self.procs:
            p.kill()
        subprocess.run(["pkill", "-f", str(self.server_py)], check=False)
        subprocess.run(["rm", "-rf", str(self.tmp)], check=False)

    def listener(self, port):
        p = subprocess.Popen([sys.executable, str(self.server_py), str(port)])
        self.procs.append(p)
        self.assertTrue(wait_listening(port), f"stub on {port} did not start")
        return p

    def run_script(self, port, *args):
        env = dict(os.environ, PATH=self.path, FRONTEND_DIR=str(self.fe),
                   FRONTEND_PORT=str(port), LOG_DIR=str(self.tmp / "logs"))
        env.pop("RUNPOD_POD_ID", None)
        # Output goes to a file, not a pipe: the restarted server is a
        # background child that inherits the script's stdout, and a pipe
        # would keep subprocess.run waiting for EOF until that server exits.
        out = self.tmp / "script.out"
        with open(out, "w") as fh:
            rc = subprocess.run(["bash", str(SCRIPT), *args], env=env,
                                stdout=fh, stderr=subprocess.STDOUT,
                                timeout=60).returncode
        return subprocess.CompletedProcess(args, rc, out.read_text(), "")

    def test_only_the_target_port_is_stopped_and_builds_swap(self):
        target, other = free_port(), free_port()
        old_target = self.listener(target)
        bystander = self.listener(other)

        r = self.run_script(target)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

        # The old target server is gone, a new one serves the port.
        old_target.wait(timeout=10)
        self.assertTrue(wait_listening(target))
        # The other "Next.js" server was not touched.
        self.assertIsNone(bystander.poll(), "bystander server was killed")
        self.assertTrue(wait_listening(other))
        # Builds swapped.
        self.assertEqual((self.fe / ".next" / "BUILD_ID").read_text(), "OLD")
        self.assertEqual((self.fe / ".next.prev" / "BUILD_ID").read_text(), "NEW")

    def test_dry_run_changes_nothing(self):
        target = free_port()
        srv = self.listener(target)
        r = self.run_script(target, "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("dry run", r.stdout)
        self.assertIsNone(srv.poll())
        self.assertEqual((self.fe / ".next" / "BUILD_ID").read_text(), "NEW")

    def test_missing_previous_build_refuses(self):
        (self.fe / ".next.prev" / "BUILD_ID").unlink()
        (self.fe / ".next.prev").rmdir()
        r = self.run_script(free_port())
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("nothing to roll back", r.stdout)

    def test_default_frontend_dir_is_this_checkout(self):
        text = SCRIPT.read_text()
        self.assertNotIn("/workspace/narratiq-ai/frontend", text)
        self.assertNotIn("pkill", text)


if __name__ == "__main__":
    unittest.main()
