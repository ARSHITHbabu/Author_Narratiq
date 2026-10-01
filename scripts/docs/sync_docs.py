#!/usr/bin/env python3
"""Keep generated Word copies in sync with their Markdown sources (PG-11, task 11.8).

Markdown is the source of truth; each managed `.docx` is generated from it with
pandoc. The manifest `docs/generated-docs.json` lists every managed pair and
records the SHA-256 of the Markdown source at the moment its Word copy was last
regenerated. That makes the check deterministic and independent of pandoc's
output (a .docx embeds timestamps, so comparing Word files byte-for-byte would
never be stable).

    python3 scripts/docs/sync_docs.py build    # regenerate every Word copy, refresh hashes
    python3 scripts/docs/sync_docs.py check    # exit 1 if any source changed since its last build

`check` needs only Python. `build` needs pandoc 3.7.0.2 (see docs/README.md,
"Regenerating Word copies"); it is located via $PANDOC, then `pandoc` on PATH,
then /workspace/tools/pandoc-3.7.0.2/bin/pandoc.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MANIFEST = REPO / "docs" / "generated-docs.json"
PANDOC_VERSION = "3.7.0.2"
PANDOC_FALLBACK = Path(f"/workspace/tools/pandoc-{PANDOC_VERSION}/bin/pandoc")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _pandoc() -> str:
    for cand in (os.environ.get("PANDOC"), shutil.which("pandoc"), str(PANDOC_FALLBACK)):
        if cand and Path(cand).exists():
            out = subprocess.run([cand, "--version"], capture_output=True, text=True, check=True).stdout
            found = out.split()[1] if out else "?"
            if found != PANDOC_VERSION:
                sys.exit(f"sync_docs: {cand} is pandoc {found}; {PANDOC_VERSION} is required "
                         "(a different version produces different Word output)")
            return cand
    sys.exit(f"sync_docs: pandoc {PANDOC_VERSION} not found. Install it as described in "
             "docs/README.md, 'Regenerating Word copies', or set $PANDOC.")


def check() -> int:
    stale = 0
    pairs = _load()["pairs"]
    for p in pairs:
        src, out = REPO / p["source"], REPO / p["output"]
        if not src.exists() or not out.exists():
            print(f"MISSING  {p['source'] if not src.exists() else p['output']}")
            stale += 1
        elif _sha256(src) != p["source_sha256"]:
            print(f"STALE    {p['output']} — {p['source']} changed since the Word copy was "
                  "generated; run `make docs`")
            stale += 1
        else:
            print(f"OK       {p['output']}")
    print(f"docs-check: {len(pairs)} pair(s) checked, {stale} failed (out of sync)")
    return 1 if stale else 0


def build() -> int:
    pandoc = _pandoc()
    data = _load()
    for p in data["pairs"]:
        src, out = REPO / p["source"], REPO / p["output"]
        # Run from the source's directory so relative image paths resolve.
        subprocess.run([pandoc, src.name, "--from=gfm", "--to=docx", "--toc", "-o", str(out)],
                       cwd=src.parent, check=True)
        p["source_sha256"] = _sha256(src)
        print(f"BUILT    {p['output']}")
    data["pandoc_version"] = PANDOC_VERSION
    MANIFEST.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return check()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd not in ("build", "check"):
        sys.exit("usage: sync_docs.py build|check")
    sys.exit(build() if cmd == "build" else check())
