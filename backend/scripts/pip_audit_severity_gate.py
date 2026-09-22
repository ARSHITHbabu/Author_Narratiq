#!/usr/bin/env python3
"""
Severity-aware wrapper around `pip-audit` (Stage 6 task 6.7).

pip-audit's own JSON output does NOT include a severity rating at all — this
was verified directly against this project's real dependencies before
writing this script, not assumed. Its findings carry only an id, aliases,
fix_versions and description. To honour "High/Critical findings may gate
after triage, while lower-severity findings should remain visible" as an
honest, real gate (not a fabricated one), this script cross-references each
finding's GHSA alias against the OSV.dev API, which DOES carry a qualitative
`database_specific.severity` rating for GitHub-reviewed advisories.

Behaviour:
  - Every finding is always printed (visible, never silently dropped),
    grouped by resolved severity, including UNKNOWN when OSV has no rating
    or the id has no GHSA alias to look up.
  - Exit code is non-zero ONLY if a CRITICAL or HIGH severity finding exists.
  - A network failure while querying OSV degrades a finding's severity to
    UNKNOWN rather than crashing the scan or silently passing it as safe —
    UNKNOWN findings are reported but do not gate the build, and the
    degraded lookups are called out explicitly in the summary.

Usage:
  pip-audit -r backend/requirements.txt --format json | \\
    python3 backend/scripts/pip_audit_severity_gate.py
"""
import json
import sys
import urllib.error
import urllib.request

OSV_URL = "https://api.osv.dev/v1/vulns/{id}"
GATING_SEVERITIES = {"CRITICAL", "HIGH"}


def _first_ghsa(aliases: list[str]) -> str | None:
    return next((a for a in aliases if a.startswith("GHSA-")), None)


def _lookup_severity(vuln_id: str, aliases: list[str]) -> tuple[str, bool]:
    """Returns (severity, lookup_failed). severity is 'UNKNOWN' when no GHSA
    alias exists or OSV has no database_specific.severity for it."""
    ghsa = _first_ghsa(aliases) or (vuln_id if vuln_id.startswith("GHSA-") else None)
    if not ghsa:
        return "UNKNOWN", False
    try:
        with urllib.request.urlopen(OSV_URL.format(id=ghsa), timeout=10) as r:
            data = json.load(r)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return "UNKNOWN", True
    return data.get("database_specific", {}).get("severity", "UNKNOWN"), False


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        print("[pip_audit_severity_gate] no input on stdin — nothing to triage.")
        return 0

    payload = json.loads(raw)
    findings = []
    for dep in payload.get("dependencies", []):
        for vuln in dep.get("vulns", []):
            findings.append({
                "package": dep["name"], "version": dep["version"],
                "id": vuln["id"], "aliases": vuln.get("aliases", []),
                "fix_versions": vuln.get("fix_versions", []),
            })

    if not findings:
        print("[pip_audit_severity_gate] no known vulnerabilities found.")
        return 0

    by_severity: dict[str, list[dict]] = {}
    lookup_failures = 0
    for f in findings:
        severity, failed = _lookup_severity(f["id"], f["aliases"])
        lookup_failures += failed
        by_severity.setdefault(severity, []).append(f)

    for severity in ("CRITICAL", "HIGH", "MODERATE", "LOW", "UNKNOWN"):
        group = by_severity.get(severity, [])
        if not group:
            continue
        print(f"\n== {severity} ({len(group)}) ==")
        for f in group:
            fix = f", fix: {', '.join(f['fix_versions'])}" if f["fix_versions"] else " (no fix available yet)"
            print(f"  {f['package']} {f['version']} — {f['id']}{fix}")

    if lookup_failures:
        print(f"\n[pip_audit_severity_gate] WARNING: {lookup_failures} OSV lookup(s) failed "
              f"(network) — those finding(s) are reported as UNKNOWN, not silently cleared.")

    gating = [f for sev in GATING_SEVERITIES for f in by_severity.get(sev, [])]
    if gating:
        print(f"\n[pip_audit_severity_gate] FAILING: {len(gating)} CRITICAL/HIGH finding(s) present.")
        return 1

    print("\n[pip_audit_severity_gate] no CRITICAL/HIGH findings — not gating "
          "(lower-severity and UNKNOWN findings above remain visible for tracking).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
