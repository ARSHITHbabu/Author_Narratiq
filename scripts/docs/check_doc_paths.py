#!/usr/bin/env python3
"""Check that every repository path a document names actually exists.

Stage 11 (tasks 11.1, 11.2, 11.9): "every file, router and migration named in
CLAUDE.md exists" and "no document references an unresolvable file", made
executable instead of a one-off manual read.

What is checked, per Markdown file:
  * relative Markdown links  [text](path)       — must resolve from the file's dir
  * backtick-quoted paths    `backend/main.py`  — must resolve from the repo
    root, backend/, frontend/ or the file's own directory
Backtick spans are treated as paths only when they look like one (a known
extension or a slash). `file.py::symbol` and `file.py:123` resolve to the file.
`{a,b}` brace groups are expanded. Absolute runtime paths (/workspace, /tmp,
~/.cache), URL routes, globs and a short list of runtime-created or
deliberately-retired names are skipped; see SKIP_* below. Backtick names
between `<!-- doc-paths:legacy-start -->` and `<!-- doc-paths:legacy-end -->`
are quoted history (e.g. the archive's old-path mapping table) and are not
checked; Markdown links there still are.

Usage:
    python3 scripts/docs/check_doc_paths.py [FILE.md ...]
With no arguments the default active-document set is checked. Exit code 1 if
any path is unresolved.
"""
from __future__ import annotations

import itertools
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

DEFAULT_FILES = [
    "CLAUDE.md",
    "README.md",
    "docs/README.md",
    "docs/phases/README.md",
    "docs/operations/README.md",
    "docs/archive/README.md",
    "docs/specifications/narratiq-ai-product-and-technical-documentation.md",
    "docs/phases/phase-2-completed/phase-2-acceptance-record.md",
    "docs/phases/phase-2-completed/phase-2-implementation-report.md",
]

PATH_EXT = (".py", ".ts", ".tsx", ".js", ".md", ".sh", ".json", ".docx",
            ".yml", ".yaml", ".txt", ".toml", ".css", ".ini", ".example", ".mjs")
# Absolute runtime locations: they exist on the pod, not in the repository.
SKIP_PREFIXES = ("/workspace", "/tmp", "/runpod-volume", "~", "/etc", "/usr",
                 "/var", "http://", "https://", "/api", "$")
# Names a document is allowed to mention although no repo file exists:
# runtime-created directories, files inside installed packages, and names that
# are mentioned precisely to say they do not exist / were retired.
SKIP_NAMES = {
    "uploads/audio", "uploads/ocr", "ovis.py", ".env", "backend/.env",
    "frontend/.env.local", ".env.local", ".next", ".next.prev",
    "start.sh",                                   # retired by D-2
    "NarratIQ_Project_Recovery_Report.docx",      # retired by D-7 (task 11.9)
    "continuation.py", "outline.py", "voice.py",  # named only to say they do not exist
}

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
TICK_RE = re.compile(r"`([^`\n]+)`")


_SKIP_DIRS = {"node_modules", ".git", "__pycache__", "uploads", ".venv", "venv"}
_NAMES: set[str] | None = None


def _repo_file_names() -> set[str]:
    """Every file name in the repository's own tree, built once. Dependency and
    build directories (node_modules, .next*, .git) are skipped — a document
    naming a file must mean one of OURS."""
    global _NAMES
    if _NAMES is None:
        import os
        _NAMES = set()
        for root, dirs, files in os.walk(REPO):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith(".next")]
            _NAMES.update(files)
    return _NAMES


def _expand_braces(s: str) -> list[str]:
    parts = re.split(r"(\{[^{}]*\})", s)
    choices = [p[1:-1].split(",") if p.startswith("{") and p.endswith("}") else [p] for p in parts]
    return ["".join(c) for c in itertools.product(*choices)]


def _looks_like_path(s: str) -> bool:
    if " " in s or s.startswith(("-", "/")) or "=" in s or "<" in s or "*" in s or "…" in s:
        return False                       # flags, URL routes, assignments, globs
    base = re.split(r"::|:(?=\d)", s)[0]
    if base.startswith(".") and "/" not in base:
        return False                       # a bare extension such as `.docx`
    if base.endswith(PATH_EXT):
        return True
    # Extension-less: a path only if its first segment is a real top-level
    # directory, so model ids (`owner/name`), package imports (`next/dynamic`)
    # and rates (`5/minute`) are not mistaken for paths.
    first = base.split("/")[0]
    return "/" in base and any((r / first).is_dir() for r in (REPO, REPO / "backend", REPO / "frontend"))


def _resolves(raw: str, doc: Path) -> bool:
    base = re.split(r"::|:(?=\d)", raw)[0].rstrip("/")
    if not base or base.startswith(SKIP_PREFIXES) or base in SKIP_NAMES:
        return True
    if any(base.endswith("/" + n) or base == n for n in SKIP_NAMES):
        return True
    for cand in _expand_braces(base):
        roots = [REPO, REPO / "backend", REPO / "frontend", doc.parent]
        if not any((r / cand).exists() for r in roots):
            # A bare filename (e.g. `ai_service.py`) may live anywhere under a
            # source tree; accept it if exactly that name exists somewhere.
            if "/" not in cand and cand in _repo_file_names():
                continue
            return False
    return True


def check(doc: Path) -> list[tuple[int, str, str]]:
    bad = []
    in_code = False
    legacy = False   # inside <!-- doc-paths:legacy-start/end -->: names quoted as history
    for n, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
        if "<!-- doc-paths:legacy-start -->" in line:
            legacy = True
        if "<!-- doc-paths:legacy-end -->" in line:
            legacy = False
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        for m in LINK_RE.finditer(line):
            target = m.group(1).split("#")[0]
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            if not (doc.parent / target).exists():
                bad.append((n, "link", target))
        for m in TICK_RE.finditer(line):
            span = m.group(1).strip()
            if not legacy and _looks_like_path(span) and not _resolves(span, doc):
                bad.append((n, "path", span))
    return bad


def main(argv: list[str]) -> int:
    files = argv or DEFAULT_FILES
    total = 0
    for f in files:
        doc = (REPO / f) if not Path(f).is_absolute() else Path(f)
        if not doc.exists():
            print(f"MISSING DOCUMENT {f}")
            total += 1
            continue
        for n, kind, target in check(doc):
            print(f"{doc.relative_to(REPO)}:{n}: unresolved {kind}: {target}")
            total += 1
    print(f"check_doc_paths: {len(files)} document(s) checked, {total} failed (unresolved references)")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
