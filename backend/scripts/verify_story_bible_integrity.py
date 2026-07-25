"""
Story Bible status-integrity verification (read-only).

Closes the database-state verification of checklist task 3.2. Asserts, against
the live database, that the invariants the task established actually hold:

  1. No bible contains a failure placeholder in its content — at ANY status.
     Since the pipeline stopped persisting placeholders, the check is stronger
     than the checklist's original wording ("no completed row contains a '['")
     and, crucially, safe: a bare '[' scan false-positives on ordinary prose
     such as "[Chapter 3]", "[Act I]" and Markdown links. Failure path SB-F15
     in docs/issues-and-bugs/story-bible-failure-path-audit.md.
  2. No bible is 'completed' while naming failed sections.
  3. No bible is 'partial' or 'failed' without any explanation.
  4. Every status value is one the system defines.

Read-only: SELECT statements only, no writes, no schema access beyond reads.

    cd backend && python3 scripts/verify_story_bible_integrity.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from database import engine

# Written by the pipeline before task 3.2 subtask 5. Matched exactly — never a
# bare '[', which genuine sections legitimately contain.
PLACEHOLDERS = ("[AI temporarily unavailable", "[Error generating ")
VALID_STATUSES = {"running", "completed", "partial", "failed"}


def check_rows(rows) -> list[str]:
    """Apply every invariant to (bible_id, status, content_json, failed_sections)
    tuples and return a list of violations. Pure — no database — so the checker
    itself can be unit-tested against known-bad rows rather than only ever being
    run against a table that happens to be empty."""
    failures: list[str] = []

    for bible_id, status, content_json, failed_sections in rows:
        short = (bible_id or "?")[:8]

        # 1 — no placeholder persisted as content
        for marker in PLACEHOLDERS:
            if marker in (content_json or ""):
                failures.append(f"{short}: content contains placeholder {marker!r} (status={status})")

        try:
            content = json.loads(content_json or "{}")
        except (json.JSONDecodeError, TypeError):
            failures.append(f"{short}: content_json is not valid JSON")
            content = {}

        failed = failed_sections or []
        named = {f.get("section") for f in failed if isinstance(f, dict)}

        # 2 — 'completed' must mean complete
        if status == "completed" and named:
            failures.append(f"{short}: status=completed but failed_sections names {sorted(named)}")

        # 3 — a non-complete bible must say why
        if status in ("partial", "failed") and not named:
            failures.append(f"{short}: status={status} but failed_sections is empty")

        # 3b — content and failures must not overlap
        overlap = named & {k for k, v in content.items() if v}
        if overlap:
            failures.append(f"{short}: sections both stored and failed: {sorted(overlap)}")

        # 4 — recognised status only
        if status not in VALID_STATUSES:
            failures.append(f"{short}: unrecognised status {status!r}")

    return failures


def main() -> int:
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT bible_id, status, content_json, failed_sections FROM story_bibles"
        )).fetchall()

    print(f"story_bibles rows: {len(rows)}")
    if not rows:
        print("\nNo bibles exist, so every check below passes VACUOUSLY.")
        print("This is not evidence the invariants hold in production — re-run")
        print("once a manuscript has been indexed and a bible generated.")
    else:
        by_status: dict[str, int] = {}
        for _, status, _, _ in rows:
            by_status[status] = by_status.get(status, 0) + 1
        print("by status:", ", ".join(f"{k}={v}" for k, v in sorted(by_status.items())))

    failures = check_rows(rows)

    print()
    if failures:
        print(f"FAIL — {len(failures)} integrity violation(s):")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("PASS — all Story Bible status-integrity invariants hold"
          + (" (vacuously — no rows)" if not rows else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
