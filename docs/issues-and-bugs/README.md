# Issues and Bugs

Defect reports produced by manual QA and production testing. These describe **problems that still
need action** — they are not implementation records. Completed work belongs in
[`../phases/`](../phases/).

## Status folders

| Folder | Meaning |
|---|---|
| [`open/`](./open/) | Reported, not yet fixed or not yet verified as fixed |
| `resolved/` | Created when the first report is closed out; move the document here and note the fixing commit |

## Open

### [`open/phase-1-ai-writing-tools-qa-issues.docx`](./open/phase-1-ai-writing-tools-qa-issues.docx)

Consolidated QA report on the AI writing tools. Roughly 40 issues grouped by transform category —
tone, emotion, audience adaptation, style — plus a UI/UX assessment.

The recurring theme is one root problem: **the transform engine rewrites instead of adjusting**, so
the author's voice, subtext and stylistic choices are replaced with generic AI prose. There is no
minimal-change or preservation mode. The report closes with a recommendation to redesign the author
workspace around a writing-first workflow rather than patching the right-hand panel.

Directly relevant to [Phase 3](../phases/phase-3-planned/), which specifies preservation rules and
sentence-level locks as the fix.

### [`open/phase-2-production-testing-issues.docx`](./open/phase-2-production-testing-issues.docx)

Fourteen defects found during production testing of the Phase 2 intelligence features. Several are
rated **High**:

- Plot hole detection fails on invalid AI output
- Chapter continuation generates nothing
- Continuity analysis never completes
- Chapter outline generation fails
- Voice agent transcribes correctly but does not execute the requested action, and reports success
  without verifying completion

Issues 2, 12, 13 and 14 share one root cause — unvalidated AI responses are not parsed defensively —
which is also called out in the root [README](../../README.md#known-issues).

## Adding a new report

1. Name it `phase-<n>-<topic>.docx` or `<topic>-issues.md` in `lowercase-kebab-case`.
2. Put it in `open/`.
3. Add a short entry to this file describing scope and severity.
4. When it is fixed, move it to `resolved/` with `git mv` and record the commit — do not delete it.
