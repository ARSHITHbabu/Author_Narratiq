#!/usr/bin/env python3
"""Render the evidence table (markdown) from results.json."""
import json

R = json.load(open("/tmp/claude-0/-workspace/45a7b97a-8dc8-4ac2-84e3-53bd8b62825e/scratchpad/evidence/results.json"))


def short(fails, n=3):
    ids = []
    for f in fails:
        f = f.replace("FAILED ", "").replace("ERROR ", "")
        f = f.split(" - ")[0]
        if "›" in f:  # playwright line
            f = f.split("›", 1)[1].strip()
        ids.append(f.split("::")[-1])
    more = f" (+{len(ids)-n} more)" if len(ids) > n else ""
    return "<br>".join(f"`{i}`" for i in ids[:n]) + more


rows = ["| Item | Issue | Kind | Production file mutated | Mutation | Mapped tests | Baseline | Mutated | Restored | Verdict |",
        "|---|---|---|---|---|---|---|---|---|---|"]
for k, r in R.items():
    tests = "<br>".join(f"`{t.replace('tests/', '')}`" for t in r["tests"])
    if r.get("pytest_args"):
        tests += f"<br>(`{' '.join(r['pytest_args'])}`)"
    mut = r["mutated"]["summary"]
    if r["mutated"]["failures"]:
        mut += "<br>" + short(r["mutated"]["failures"])
    for p in r.get("probe_results", []):
        mut += f"<br>probe {', '.join('`'+t.replace('tests/','')+'`' for t in p['tests'])}: {p['summary']}"
        if p["failures"]:
            mut += " " + short(p["failures"])
    rows.append(" | ".join([
        f"| [{k}](patches/{k}.patch)", r["issue"], r["kind"], f"`{r['file']}`", r["desc"], tests,
        r["baseline"]["summary"], mut, r["restored"]["summary"], f"**{r['verdict']}** |"]))
print("\n".join(rows))
