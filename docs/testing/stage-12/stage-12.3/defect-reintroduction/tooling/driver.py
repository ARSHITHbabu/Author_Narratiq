#!/usr/bin/env python3
"""Defect-reintroduction driver (task 6.6 verification). Runs in the isolated worktree only.

usage: driver.py <mutations_module.py> [id ...]
Each mutation: baseline mapped tests -> apply edit(s) -> save git diff as .patch ->
run mapped tests (expect red) -> git checkout -- file -> assert clean -> rerun (expect green).
"""
import importlib.util
import json
import os
import re
import subprocess
import sys
import time

WT = "/workspace/Author_Narratiq/.claude/worktrees/agent-ab67cbede685e063d"
SCR = "/tmp/claude-0/-workspace/45a7b97a-8dc8-4ac2-84e3-53bd8b62825e/scratchpad"
OUT = f"{SCR}/evidence"
os.makedirs(f"{OUT}/patches", exist_ok=True)
SK = open(f"{SCR}/sk").read().strip()
ENV = dict(os.environ,
           DATABASE_URL="postgresql+psycopg2://narratiq:narratiq@localhost:5432/narratiq_ci_verify",
           SKIP_LLM_TESTS="1", SECRET_KEY=SK,
           VLLM_BASE_URL="http://127.0.0.1:9/v1")  # dead port: no test may reach the live model
LOG = open(f"{OUT}/results.log", "a")


def log(s=""):
    print(s, flush=True)
    LOG.write(s + "\n")
    LOG.flush()


def git(*args, check=True):
    return subprocess.run(["git", "-C", WT, *args], capture_output=True, text=True, check=check)


def run_tests(m, label, tests=None, extra=None):
    tests = tests or m["tests"]
    extra = m.get("pytest_args", []) if extra is None else extra
    if m.get("runner") == "playwright-unit":
        cmd = ["npx", "playwright", "test", "--project=unit", f"--output={SCR}/pw-out", *tests]
        cwd = f"{WT}/frontend"
    else:
        cmd = ["python3", "-m", "pytest", *tests, *extra, "-q", "-p", "no:cacheprovider", "-rfE",
               "--no-header", "-W", "ignore"]
        cwd = f"{WT}/backend"
    t0 = time.time()
    p = subprocess.run(cmd, cwd=cwd, env=ENV, capture_output=True, text=True, timeout=1800)
    out = p.stdout + p.stderr
    if m.get("runner") == "playwright-unit":
        fails = [l.strip() for l in out.splitlines() if re.match(r"\s*\d+\) \[unit\]", l)]
        summ = " | ".join(l.strip() for l in out.splitlines() if re.match(r"\s*\d+ (passed|failed|flaky|skipped)", l))
    else:
        fails = [l.strip()[:220] for l in out.splitlines() if l.startswith(("FAILED ", "ERROR "))]
        summ = next((l.strip("= ").strip() for l in reversed(out.splitlines())
                     if re.search(r"\d+ (passed|failed|error)", l)), "NO SUMMARY")
    log(f"  [{label}] exit={p.returncode} ({time.time()-t0:.1f}s) :: {summ}")
    for f in fails:
        log(f"      {f}")
    with open(f"{OUT}/raw/{m['id']}.{label}.txt", "w") as fh:
        fh.write(f"$ (cwd {cwd}) {' '.join(cmd)}\n\n{out}")
    return {"exit": p.returncode, "summary": summ, "failures": fails}


def apply(m):
    path = f"{WT}/{m['file']}"
    src = open(path, encoding="utf-8").read()
    for old, new in m["edits"]:
        n = src.count(old)
        assert n == 1, f"{m['id']}: anchor occurs {n}x in {m['file']}: {old[:80]!r}"
        src = src.replace(old, new, 1)
    open(path, "w", encoding="utf-8").write(src)


def main():
    spec = importlib.util.spec_from_file_location("muts", sys.argv[1])
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    only = set(sys.argv[2:])
    os.makedirs(f"{OUT}/raw", exist_ok=True)
    results_path = f"{OUT}/results.json"
    results = json.load(open(results_path)) if os.path.exists(results_path) else {}
    assert git("diff", "--quiet", check=False).returncode == 0, "worktree not clean at start"
    for m in mod.MUTATIONS:
        if only and m["id"] not in only:
            continue
        log("=" * 100)
        log(f"{m['id']} ({m['issue']}) — {m['file']}")
        log(f"  mutation: {m['desc']}")
        log(f"  mapped tests: {' '.join(m['tests'])} {' '.join(m.get('pytest_args', []))}")
        r = {k: m[k] for k in ("id", "issue", "file", "desc", "tests", "kind")}
        r["pytest_args"] = m.get("pytest_args", [])
        r["baseline"] = run_tests(m, "baseline")
        apply(m)
        diff = git("diff", "--", m["file"]).stdout
        assert diff, "mutation produced no diff"
        open(f"{OUT}/patches/{m['id']}.patch", "w").write(diff)
        try:
            r["mutated"] = run_tests(m, "mutated")
            for i, probe in enumerate(m.get("probes", [])):
                r.setdefault("probe_results", []).append(
                    {"tests": probe, **run_tests(m, f"mutated-probe{i}", tests=probe, extra=[])})
        finally:
            git("checkout", "--", m["file"])
        clean = git("diff", "--quiet", check=False).returncode == 0
        log(f"  restored: git checkout -- {m['file']}; git diff --quiet -> {'clean' if clean else 'DIRTY'}")
        assert clean
        r["restored"] = run_tests(m, "restored")
        red = r["mutated"]["exit"] != 0 and bool(r["mutated"]["failures"])
        green = r["baseline"]["exit"] == 0 and r["restored"]["exit"] == 0
        r["verdict"] = ("RED AS EXPECTED" if red and green else
                        "GUARD GAP (mapped tests stayed green)" if not red and green else
                        "INCONCLUSIVE")
        log(f"  VERDICT: {r['verdict']}")
        results[m["id"]] = r
        json.dump(results, open(results_path, "w"), indent=2)


if __name__ == "__main__":
    main()
