#!/usr/bin/env python3
"""For mapped-test guard gaps: does the WHOLE backend suite (DB-less, model-less) turn red?
Compares the FAILED/ERROR set under mutation against the unmutated baseline run."""
import importlib.util
import re
import subprocess
import sys

sys.path.insert(0, "/tmp/claude-0/-workspace/45a7b97a-8dc8-4ac2-84e3-53bd8b62825e/scratchpad")
import driver  # noqa: E402

SCR = driver.SCR


def failset(text):
    return {l.split(" - ")[0].strip() for l in text.splitlines() if l.startswith(("FAILED ", "ERROR "))}


spec = importlib.util.spec_from_file_location("muts", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
base_txt = open(f"{SCR}/fullsuite_baseline.txt").read()
base = failset(base_txt)
base_summary = [l for l in base_txt.splitlines() if re.search(r"\d+ passed", l)][-1]
out = open(f"{SCR}/evidence/fullsuite_gap_probes.log", "a")
out.write(f"Baseline full backend suite (no DB, live model blocked): {base_summary}\n")
for m in mod.MUTATIONS:
    if m["id"] not in sys.argv[2:]:
        continue
    assert driver.git("diff", "--quiet", check=False).returncode == 0
    driver.apply(m)
    try:
        p = subprocess.run([f"{SCR}/rt.sh", "tests/", "--continue-on-collection-errors", "-rfE", "-W", "ignore"],
                           capture_output=True, text=True, timeout=1800)
    finally:
        driver.git("checkout", "--", m["file"])
    assert driver.git("diff", "--quiet", check=False).returncode == 0
    txt = p.stdout + p.stderr
    open(f"{SCR}/evidence/raw/{m['id']}.fullsuite.txt", "w").write(txt)
    summ = [l for l in txt.splitlines() if re.search(r"\d+ passed", l)][-1]
    new = sorted(failset(txt) - base)
    gone = sorted(base - failset(txt))
    out.write(f"\n{m['id']}: {summ}\n  NEW failures vs baseline ({len(new)}):\n")
    for n in new:
        out.write(f"    {n}\n")
    if gone:
        out.write(f"  (baseline failures no longer failing: {gone})\n")
    out.flush()
    print(m["id"], summ, "NEW:", new, flush=True)
