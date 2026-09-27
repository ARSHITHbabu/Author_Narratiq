# Stage 9 — User Acceptance Testing Guide (task 9.6)

| | |
|---|---|
| **Checklist task** | 9.6 — User acceptance testing with real authors |
| **Also closes, from the same sessions** | Stage 5 MV-5.BR, MV-5.AR, MV-5.14-D · Stage 7 golden-set voice review (7.12) · Stage 8 MV-8.4, MV-8.5, MV-8.6, MV-8.7 (task 8.11) · the author-judgement rows of `stage-09-qa-rerun-results.md` |
| **Severity bar** | D-6: Critical and High findings are release-blocking; Medium and Low go to post-launch |
| **Status** | **PENDING — needs real authors.** Nothing in this guide has been run. No checklist box is ticked from it until the evidence below exists |

## Why this exists

Most of the 154 Phase 1 issues were found by an author, not by a test suite. Automated Stage 9 runs show that
the code does what the fixes intended; only an author can say that the product now writes, remembers and
feels right. The four questions in checklist task 9.6 are the acceptance criteria.

## Before the session (operator)

1. **Environment.** The pod is running the build that is being accepted (`bash /workspace/narratiq-ai/start-narratiq.sh`;
   `curl -s localhost:8000/api/health` reports `vllm`, `embeddings` and `pgvector` healthy). Record the commit (`git log -1 --oneline`).
2. **Backup first.** `bash /workspace/narratiq-ai/scripts/backup_database.sh`. Record the dump file name and its
   checksum. Nothing in UAT may run without a backup taken the same day.
3. **Accounts.** Each author registers their own account through the app. Never share an account; cross-user
   isolation is part of what is being accepted.
4. **Manuscripts.** Authors use their own manuscripts (at least 5 chapters, ideally a complete draft), pasted
   or uploaded through the app. Manuscripts never leave the pod. If an author prefers not to, use the fixture
   story (`backend/scripts/seed_fixture.py`, cast Devika, Mara, Sant, Vance), and mark their answers
   "fixture" — fixture answers do not count toward question 2 (whole-story knowledge).
5. **Recruit** at least two authors who write long-form fiction; one should not have seen NarratIQ before.
6. **Friction log** — one row per observation: time · workspace · what the author was trying to do · what
   happened · severity (blocker / annoying / minor) · the author's own words.

## Session plan (about 3½ hours, with breaks)

The Stage 8 multi-hour session (MV-8.7) is the backbone. The Stage 9 additions are in bold.

| Time | Activity | Feeds |
|---|---|---|
| 0:00–0:10 | Orientation: the workspace rail, Ctrl/⌘K, Draft/Edit. No other tips | 8.11 |
| 0:10–0:30 | **Import the manuscript; run Sync Summaries; wait for indexing to finish** | Q2, Q3 |
| 0:30–1:15 | Drafting: write a new scene in Draft mode | 8.5, 8.11, Q4 |
| 1:15–1:25 | Break | |
| 1:25–2:10 | Editing: revise an earlier chapter with the AI panel — **Refine, Tone, Emotion, Audience, Style (incl. Thriller), Author-inspired style, Translate** — lock a sentence, pin a version, compare two versions | **Q1**, 5.AR, 7.12 |
| 2:10–2:40 | Planning: **Plot Assistant (five questions below)**, a pacing goal, two Idea Shelf cards aimed at a chapter | **Q2** |
| 2:40–3:05 | **Story Bible: generate, then check every section against the manuscript** | **Q3** |
| 3:05–3:25 | Analysis: Continuity, Plot Holes, Emotional Arc, Manuscript Report; act on one finding in Write | 5.14-D, Q4 |
| 3:25–3:35 | Audio note (record 30 s, confirm the transcript into a note) — the one feature row with no automated test | 6.4 manual row |
| 3:35–3:45 | Debrief (questions below) | all |

### Q1 — Does the transform preserve my voice?

For each transform, the author picks a passage of their own (150–400 words) and answers on a 1–5 scale:
*"This still sounds like me."* Also record: did anything locked change? Was anything invented that is not in
the story? Any score of 1–2, or any locked-text change, is a finding (locked-text change = Critical).

### Q2 — Does the Plot Assistant know my whole story?

Ask these five, adapted to the manuscript: (1) what happened to a minor character last seen early on; (2) why
a named event in the middle happened; (3) who knows a specific secret at chapter N; (4) the same question with
"search the entire manuscript" switched on (D-1), from an early chapter; (5) something that does **not**
happen in the story. Expected: 1–4 answered with correct chapters; 4 differs from the spoiler-safe answer only
by later-chapter knowledge; 5 is answered "not in the manuscript", not invented.

### Q3 — Is the Story Bible accurate?

For each section (characters, locations, timeline, world rules, themes): count statements that are
**wrong**, **unsupported** (not in the manuscript) and **missing** (an obvious major item left out). Any
invented character, or a wrong fact about a main character, is a High finding.

### Q4 — Is the workspace comfortable for a full writing day?

Debrief questions (from MV-8.7): where did you lose time finding something? Did the screen feel crowded, and
when? Did you get tired of anything? Does this feel like a writing studio or a tool dashboard? What would you
change first?

## Folded-in author items (run in the same sessions)

| Item | Where it is defined | What to record |
|---|---|---|
| MV-5.BR — blind review / Gate 3b | `manual-verification/stage-05-manual-verification-guide.md` | The tally; which version preferred per transform |
| MV-5.AR — per-task author reviews 5.7, 5.10, 5.11 (fluent speaker), 5.13, 5.15, 5.16 | same | A dated note per box |
| MV-5.14-D — accept 5.14's three items | same (needs MV-5.14-A/B/C) | accept / accept with follow-up / reject, per item |
| 7.12 — golden-set voice matching review | checklist task 7.12 | Pass / fail with a sentence |
| MV-8.4 — screen-reader pass | `manual-verification/stage-08-manual-verification-guide.md` | Anything unlabelled or confusing |
| MV-8.5 — author reviews 8.3, 8.4, 8.5 | same | Yes/no plus a sentence each |
| MV-8.6 — real-browser layout | same | Pass/fail per step |
| MV-8.7 — multi-hour session | same (this guide's session plan) | Friction log, debrief answers |

## After the session (operator)

1. Triage every friction-log row and every Q1–Q3 finding with the D-6 bar; add each to
   `docs/issues-and-bugs/triage-register.md` with a new ID (`UAT-<n>`), severity and owner.
2. Record per author: Q1 scores per transform, Q2 answers correct / incorrect / invented, Q3 counts per
   section, Q4 answers.
3. For each Phase 1 issue marked "Author judgement required" in `stage-09-qa-rerun-results.md`, record
   whether the author confirmed it resolved.
4. Send the evidence back in the project thread. The checklist is updated only from that evidence:
   9.6's boxes, 9.2's "every release-blocking issue passes" for the author-judged issues, and the folded-in
   Stage 5, 7 and 8 items.

## Acceptance

9.6 is done when: every author completed the session; no Critical finding is open; every High finding is
fixed or explicitly accepted by the product owner under D-6; and each author answers Q1–Q4 without a
blocking objection.
