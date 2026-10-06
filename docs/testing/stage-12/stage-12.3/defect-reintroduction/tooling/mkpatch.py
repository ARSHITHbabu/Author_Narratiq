#!/usr/bin/env python3
"""Build browser-only mutation patches WITHOUT touching the worktree: edit a scratch copy,
diff it against the worktree file, then `git apply --check` the result (read-only)."""
import os
import subprocess

WT = "/workspace/Author_Narratiq/.claude/worktrees/agent-ab67cbede685e063d"
OUT = "/tmp/claude-0/-workspace/45a7b97a-8dc8-4ac2-84e3-53bd8b62825e/scratchpad/evidence/browser-prepared"
os.makedirs(OUT, exist_ok=True)

PATCHES = {
    "P2-01-toolbar-escape-dismiss": ("frontend/lib/selectionOwnership.ts", [
        ("  if (input.dismissed) return 'hidden'\n",
         "  // REINTRODUCED P2-1: Escape/dismissal no longer hides the toolbar\n")]),
    "P2-11-toolbar-with-sidebar-open": ("frontend/lib/selectionOwnership.ts", [
        ("  if (input.sidebarVisible) return 'sidebar'\n",
         "  // REINTRODUCED P2-11: the open AI sidebar no longer takes ownership of the selection\n")]),
    "P2-03-analytics-not-scrollable": ("frontend/app/(dashboard)/projects/[id]/analytics/page.tsx", [
        ('<div className="flex-1 min-h-0 overflow-y-auto focus-visible:outline-none',
         '<div className="flex-1 focus-visible:outline-none')]),
    "P2-06-ocr-upload-hidden-without-chapter": ("frontend/components/ocr/OCRPanel.tsx", [
        ("  const extractionFailed = result !== null && !result.raw_text && !result.cleaned_text\n",
         "  const extractionFailed = result !== null && !result.raw_text && !result.cleaned_text\n"
         "  if (!chapterId) return null  // REINTRODUCED P2-6: OCR withheld when there is no chapter\n")]),
    "P2-07-notes-failure-shown-as-empty": ("frontend/components/notes/NotesPanel.tsx", [
        ("        if (isCancellation(e) || seq !== seqRef.current) return   // cancelled ≠ failed\n"
         "        setNotesSection((s) => ({ ...s, status: 'error' }))\n",
         "        if (isCancellation(e) || seq !== seqRef.current) return   // cancelled ≠ failed\n"
         "        setNotesSection({ data: [], status: 'ready' })  // REINTRODUCED P2-7: failure rendered as 'no notes'\n"),
        ("        if (isCancellation(e) || seq !== seqRef.current) return\n"
         "        setCardsSection((s) => ({ ...s, status: 'error' }))\n",
         "        if (isCancellation(e) || seq !== seqRef.current) return\n"
         "        setCardsSection({ data: [], status: 'ready' })  // REINTRODUCED P2-7\n")]),
}

for name, (rel, edits) in PATCHES.items():
    src = open(f"{WT}/{rel}", encoding="utf-8").read()
    new = src
    for old, rep in edits:
        assert new.count(old) == 1, (name, old[:60], new.count(old))
        new = new.replace(old, rep, 1)
    tmp = f"{OUT}/.{name}.tmp"
    open(tmp, "w", encoding="utf-8").write(new)
    d = subprocess.run(["diff", "-u", "--label", f"a/{rel}", "--label", f"b/{rel}", f"{WT}/{rel}", tmp],
                       capture_output=True, text=True).stdout
    os.remove(tmp)
    hdr = f"diff --git a/{rel} b/{rel}\n"
    path = f"{OUT}/{name}.patch"
    open(path, "w", encoding="utf-8").write(hdr + d)
    chk = subprocess.run(["git", "-C", WT, "apply", "--check", path], capture_output=True, text=True)
    print(name, "git apply --check:", "OK" if chk.returncode == 0 else chk.stderr)
