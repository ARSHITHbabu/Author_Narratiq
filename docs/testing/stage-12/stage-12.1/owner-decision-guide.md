# Stage 12.1 — Owner Decision & Human Review Guide

Prepared 2026-10-03 for the product owner. **No decision in this guide has been made by engineering.** Each item states the facts, the evidence and what each choice means, then asks for your decision. Work through it in order. Each section ends with the exact reply that records your decision.

Files referenced are in `docs/testing/stage-12/stage-12.1/` unless the path says otherwise.

| Order | Section | What you do | Time |
|---|---|---|---|
| 1 | Gate 3a — 4.9 relationship extraction | one decision | 5 min |
| 2 | Gate 3b — AI quality (A blind review · B Light strength · C children · D MV-5.14-D · E Story Bible · F translation) | read and judge | 2–3 h in total; can be split |
| 3 | Gate 4 — the remaining Critical/High issues | grouped decisions, after section 2 | 20 min |
| 4 | Gate 5 — security | five decisions (legal kept separate) | 15 min |
| 5 | Gate 6 — end-to-end testing | CI and UAT | 5 min |
| 6 | Gate 8 — deployment and rollback | two decisions | 5 min |
| 7 | Infrastructure waivers W-1…W-5 | one decision each | 15 min |

---

## AWT-G measurement (completed before this guide)

**Done:** the 5.12-G criterion is **not met** (0.0866 vs the 0.0643 baseline). The cause is non-deterministic borderline no-change decisions on the model server, not a code defect. Details: "AWT-G result" at the end of this file and `awt-g-consistency.md`. It feeds Section 3, group G2.

---

## Section 1 — Gate 3a: task 4.9, "Fix relationship extraction errors"

**The item** (checklist task 4.9, the one unticked box): *"Fix relationship extraction errors — NOT APPLICABLE — see note below, no such extraction pipeline exists."* It is the only thing holding task 4.9, the Stage 4 gate line "All 14 Cast Generation & Character Management issues closed or accepted", and Gate 3a open.

**The original issue:** CAST-H8, "Relationship understanding errors" (High). The QA report says AI-generated character material **misstates relationships** between characters.

**Why engineering recorded "not applicable":** no AI function extracts or creates relationships. Relationships are created by the author (plain create/edit, no AI). The only AI relationship function (`run_p24_relationship_intel`) analyses a relationship the author already made.

**What that note does not cover (stated so your decision is informed):**
1. AI-generated **character descriptions** do mention relationships. That is what CAST-H8 is about.
   - Tranche 2 (A11) added a guard: a kinship claim ("her sister") must be supported by the text near that character's name. The live measurement showed relationship facts in split manuscripts improving from 0 to 1.0 (`measure_cast_consistency.py`).
   - No test checks the descriptions' relationship statements in general.
2. The chapter summariser **does** produce per-chapter `relationship_changes`. They drive the Manuscript Report's Relationships section (MV-5.14-C passed: current names, chapter order, no raw ids; one pair on the fixture).

**If you accept "not applicable":**
- 4.9 closes, the Stage 4 Cast gate line can close, and Gate 3a has no remaining blocker.
- CAST-H8 moves to "accepted / not applicable".
- Risk: a description that misstates a relationship has no dedicated check beyond the A11 kinship guard. The author can edit every description.

**If you keep it open:**
- Gate 3a stays open.
- Engineering would need a defined requirement, for example "relationship statements in generated descriptions are verified against the text, measured on a fixture with known relationships". That is new measurement and possibly new work.

**Your decision:**
- *"4.9 relationship extraction: ACCEPT as not applicable"*, or
- *"4.9: KEEP OPEN — requirement: …"*

---

## Section 2 — Gate 3b: AI quality (your judgement only)

Everything here is built from **saved** outputs (no new generation), so you can review at your own pace. Folder: `gate3b-review/` (index: `gate3b-review/README.md`).

### 2A — Blind review (MV-5.BR)

**What:**
- 12 golden-set passages. Each has two rewrites in random order: one from the pre-Stage-12 prompts (v2), one from the current prompts (v4).
- File: `gate3b-review/blind-review.md`. **Do not open `blind-review-KEY.json`.**

**How:**
- For each item, read the original, then A and B.
- Judge which is the better rewrite for the request, in your voice.
- Choose **A**, **B** or **N** (no meaningful difference).

**Reply in one line:** `Blind: 1=A 2=N 3=B 4=… 12=…`. Engineering then reveals the key and tallies.

**Pass expectation (from MV-5.BR):** current version preferred or equal on style; no transform clearly worse. Whether that pass is good enough is your call.

### 2B — Light strength (A15; decides AWT-D, AWT-I, AWT-1.2, 1.6, 3.7)

**The measured issue:** at Light strength, Tone and age adaptation keep almost as few of the author's words as at Strong (median kept share: tone 0.57 Light vs 0.58 Strong; age 0.52 vs 0.48). Style, the control, behaves (0.71 vs 0.58).

**Sample to review first:** `gate3b-review/a15-sample-light-vs-strong.md`. 15 pairs (6 tone, 6 age adaptation, 3 style), each showing the original, the Light rewrite and the Strong rewrite. Answer two questions per pair:
1. Is the Light rewrite an **acceptable light edit**? (yes/no)
2. Is Light **clearly lighter** than Strong? (yes/no)

**What to judge:**
- **Tone:** at Light, a tone shift should come mostly from word choice in a few places, with your sentences intact. A full rephrase is not Light.
- **Age adaptation:** at Light, only words or details unsuitable for the target age should change. Rewriting every sentence is not Light.
- **Light vs Strong:** if you cannot tell Light from Strong, the strength control is not working for that transform.

**Reply:** `Light: S1=yes/no,yes/no S2=… S15=…`

**How engineering will use your labels (no decision is taken now):**
- If Light is **acceptable and lighter** for most tone and age pairs, the five AWT issues become **accepted limitation candidates** for your confirmation in Section 3.
- If Light is **not acceptable**, or **not lighter**, for most of them, they **require technical work**. Your labels give the threshold for a warning or retry, which A15 deliberately did not guess.

The full labelling set (90 outputs, `a15-light-labelling.md`) is only needed if the 15-pair sample is mixed.

### 2C — Children's rewrites

**Sample:** `gate3b-review/children-sample.md`, 16 rewrites (2 runs each of 8 grief or euphemism passages). Full set: `children-meaning-review.md` (80).

For each rewrite:
1. **Meaning kept?** Every difficult event is still there with the same meaning. A softer word is fine; a death that becomes "went away" is not.
2. **Appropriate for children?**

**Reply:** `Children: euphemism-1 r0=yes,yes r1=… …` (or list only the "no"s).

This closes the Tranche 2 item "Human — children's rewrite meaning review" (and feeds AWT-3.x in Section 3).

### 2D — MV-5.14-D: accept (or not) 5.14's three Story Audit items

**Existing criterion** (Stage 5 manual verification guide): *"For each of the three items, record one of: accept (tick it with the evidence), accept with a follow-up (tick and name the follow-up), or reject (keep it open, say what is missing)."*

| Item | Evidence to inspect |
|---|---|
| Critical 4 — timeline reasoning | `../tranche3/mv-5.14-a.json`: planted date reversal reported 3/3; marked flashback 0/3 after the Tranche 3 fix (`mv-5.14-a-before-fix.json`: 3/3 false reports before) |
| Critical 5 — narrative reasoning | `../tranche3/mv-5.14-b.json` and screenshot `mv-5.14-b-section.png`: "Tobias Wren — Character disappears, Ch1 Ch2" listed; every continuity finding cites real chapters |
| Medium 11 — relationship arcs | `../tranche3/mv-5.14-c.json` and screenshot `mv-5.14-c-section.png`: current names, chapter chip, no raw ids (one pair, one change on the fixture) |

**Note for your judgement:** some continuity runs on these tiny fixtures also produced weak findings, for example "Felix burned the rye" said to contradict his promise to help (`mv-5.14-a.json`, story b, run 2).

The report now also **shows** stakes, plot weight, themes and open tracker threads (fixed in 12.1). You can see them by generating a Manuscript Report on any story.

**Reply:** `MV-5.14-D: C4=accept|accept+follow-up "…"|reject "…"; C5=…; M11=…`

### 2E — Story Bible: "never asserts unsupported facts"

**Procedure:**
1. Pick a story you know well (or use the fixture story).
2. Generate its Story Bible (World → Story Bible → Generate).
3. Read each section and its citations against the story.
4. For any statement the text does not support, note the section and the statement.

**Evidence already recorded:** A24's live generation logged per-section citation coverage: characters 28/28, locations 12/12, timeline 13/13, world rules 6/6, **themes 7/11** (read themes most closely).

**Reply:** `Story Bible: no unsupported facts`, or a list of the ones you found.

### 2F — Translation (task 5.11; AWT-5.1–5.7)

**Requirement:** translations judged by a fluent speaker of the target language (task 5.11's open box: "Golden-set translation scenarios reviewed by a fluent speaker").

**Fluent judgement is necessary.** The automated measure covers only name and glossary consistency. AWT-5.7's source text describes a cross-language architectural risk, which checklist 5.11 narrowed to glossary consistency.

**Two decisions for you:**
1. **Who reviews, and in which languages?** If no fluent reviewer is available before release, the alternative is to accept translation as a known limitation.
2. **Does translation stay release-blocking?** It is Medium task priority but counted release-blocking.

**Reply:** `Translation: reviewer = … / accept as limitation / reclassify …`

---

## Section 3 — Gate 4: the remaining Critical/High issues (after Section 2)

Do this after Section 2. Your Section 2 answers decide several groups. The full per-issue table is `gate4-release-blocking-matrix.md`.

**Already fixed and verified (33, no decision needed):**
- **Critical:** AWT-C; PA-C2, C3, C4, C5, C7, C8; SEARCH-1, 2, 3; CAST-C3, C4; UI-C3, C4, C5, C7, C8.
- **High:** AWT-1.7, 2.4, 2.5, 3.4, 3.6, 4.3; SEARCH-4 to 9; CAST-H7, H9; SUG-H9; UI-H15.

**Remaining groups (one decision per group):**

| # | Group | Issues | Current state | Decided by | Meaning of your decision |
|---|---|---|---|---|---|
| G1 | Light strength | AWT-D, AWT-I (Critical); AWT-1.2, 1.6, 3.7 (High) | requires technical work, **or** accepted limitation | **your 2B labels** | accept → known limitation in release notes; reject → engineering sets thresholds from your labels and adds a warning/retry |
| G2 | Run-to-run consistency | AWT-G (Critical) | **criterion not met** (0.0866 vs the 0.0643 baseline); cause: model-serving non-determinism on borderline no-change decisions (3/12 scenarios); rewrites themselves stable (0.031) | your call | accept as documented model variability, or require work (verdict cache / margin-based assessor / serving configuration), each measured |
| G3 | Rewrite quality and voice (blind review) | AWT-A, B, E, F, H, J (Critical); tone 1.1, 1.3–1.5; emotion 2.1–2.3, 2.6, 2.7; audience 3.1–3.3, 3.5; style 4.1, 4.2, 4.4–4.10 (High) | human judgement | **your 2A result** (+ 2C for audience) | pass → close; fail → named transforms need work |
| G4 | Translation | AWT-5.1–5.7 | human judgement / reclassification | **your 2F answers** | review, limitation, or reclassify |
| G5 | Story Audit | AUDIT-C1–C5 (Critical); AUDIT-H6–H10 (High; H8–H10's display fixed in 12.1) | human judgement | **your 2D (MV-5.14-D)** plus the 5.14 author review | accept → close; reject → named follow-ups |
| G6 | Suggestions | SUG-C1, C2 (Critical); SUG-H3–H8, H10, H11 (High) | human judgement | 5.13 author review (use your own manuscript in the AI sidecar → Suggestions) | accept or name the weakness |
| G7 | Plot Assistant answers | PA-C1, C6, C9 (Critical); PA-H10–H14 (High) | human judgement; PA-C6/H12 also wait on the long-manuscript measurement (A13 follow-up) | your Plot Assistant use, or UAT | accept, or require the long-manuscript measurement first |
| G8 | Workspace and UI | UI-C1, C2, C6 (Critical); UI-H9–H14 (High) | human judgement (8.3/8.4/8.5 reviews, 8.11 multi-hour session) | your review, or UAT with authors | accept, or name the friction |
| G9 | Cast relationships | CAST-H8 | blocked by Section 1 | **your Section 1 decision** | follows 4.9 |
| G10 | Cast role variability | CAST-H6 (High) | open technical: a reluctant ally is labelled antagonist about 44 % of the time; a general prompt fix was measured **worse** and reverted | your call | accept as documented model variability (roles are editable; unknown roles fall back to "supporting"), or require deeper work (not a prompt tweak) |

Accepted already: CAST-H10 (presence variability, 2026-10-03).

**Reply per group:** `G1=…, G2=…, …`

---

## Section 4 — Gate 5: security (technical acceptance; legal is separate)

| # | Risk | Reachable in NarratIQ? | Mitigation present | If you accept | To eliminate |
|---|---|---|---|---|---|
| S1 | **Prompt injection, residual (P1)**: paraphrased or short obedience is not caught; a source with no names is never flagged; analyses rely on the structural fence only | yes, through the author's **own** text affecting **their own** results (no sharing) | fence on every model call (proven by test); output checks on rewrites, Q&A, suggestions and continue; 0 obeyed in 17 features on current code | the residual risk is documented as accepted | output checks for analyses; semantic obedience detection (research-grade) |
| S2 | **vLLM 0.9.2** (2 Critical, 10 High) plus xgrammar/transformers in the serving stack | **not externally**: bound to 127.0.0.1, the backend is the only client, the model is text-only | loopback bind re-verified 2026-10-03 | you already accepted it on 2026-10-02; confirm it still stands | upgrade vLLM/torch/transformers (a separate project) |
| S3 | **transformers ×4, ecdsa** (requirements, High) | no: they need untrusted model files; ecdsa needs EC keys (HS256 only) | pinned local models | documented as not reachable | wait for upstream fixes / the vLLM upgrade |
| S4 | **lxml XXE** (1 High); **urllib3** (6 High); **soupsieve** (2 High) | **no.** lxml is **proven by test** (the `.docx` parser disables entities); urllib3 is used only by `requests`/`sentry-sdk` (NarratIQ's HTTP client is `httpx`; urllib3 serves only trusted model downloads); soupsieve is used only by `beautifulsoup4`, which NarratIQ never imports | `python-docx` safe parser; `httpx` | documented as not reachable | minor-version hygiene upgrades (lxml 6.1, urllib3 2.8) |
| S5 | **Pod image packages**: jupyter-server, jupyterlab, jupyter-core, nbconvert, mistune, tornado, pyjwt 2.3, httplib2, setuptools, wheel (**2 Critical, 33 High**) | not NarratIQ code; JupyterLab answers 403 without auth | — | the pod template stays as is | remove Jupyter from the RunPod template (external) |
| S6 | **npm: postcss in Next.js** (production, High); **braces** advisory in tailwind/eslint (dev) | no: build-time only, on the repository's own files | — | documented as not reachable | Next.js 16 / tailwind 4 (major upgrades) |

**Legal (separate, not a security decision):** 11.7, the legal review of the copyright-risk disclaimer, plus your review of the saved adversarial author-style outputs (`../tranche3/injection-probe-tranche3.json`, author-style section). Technical result: 0/15 named a living author, 0 obeyed.

**Reply:** `S1=accept|…, S2=…, S3=…, S4=…, S5=…, S6=…; Legal 11.7: pending legal / reviewed`

---

## Section 5 — Gate 6: end-to-end testing

| Part | Status |
|---|---|
| **Automated end-to-end** | Green on a clean pod: backend 1,142/0; retrieval 146–147/147 (the one variable case is accepted presence variability); frontend unit 108, studio 106, a11y 13, variants 32; live browser 69/0/0 plus OCR → editor 2/2. The AI harness was proven to catch a deliberate regression. **No decision needed.** |
| **CI** ("CI blocks failing merges") | Not in place (6.1 deferred by you, 2026-09-22). See waiver **W-1** in Section 7 |
| **Real-author UAT** (9.6) | Not started; needs real authors (`docs/testing/stage-09-uat-guide.md`). **Cannot be waived by engineering.** Your options: run it, or record a decision to release without it |

**If CI is deferred (W-1), exactly this is waived:**
- automatic test runs on every change;
- blocking a failing change from merging into `main`;
- the CI halves of 6.4, 6.5, 6.7, 7.4, 8.9, 9.5 and 11.8.

**Not waived:** the tests themselves. They exist and pass, and the full regression runs with one command (`backend/tests/run_full_regression.sh`).

**Reply:** `UAT: run before release | release without UAT (decision) | …`

---

## Section 6 — Gate 8: deployment and rollback

**6.1 — MV-10.3 / Docker (and PG-04, "no containerisation").** PG-04 is the production gap; MV-10.3 is the check that would close it: build `backend/Dockerfile` and `frontend/Dockerfile` with `docker-compose.yml` on a Docker host and record the image digests.
- RunPod pods cannot run Docker; these files have never been built.
- Production deploys with `start-narratiq.sh`, proven three times on 2026-10-03, every dependency and model pinned.
- Gate 8's own exit criteria (clean-pod deploy, rollback rehearsed, port contract documented) **are met**. PG-04 is a listed dependency of the gate. Decide through waiver **W-2** in Section 7.

**6.2 — Presence labels lost on a rollback (10.5's "without data loss").**

| | |
|---|---|
| **What is lost** | Rolling back past migration `0027` drops the column `characters.presence`: each character's label **On page / Mentioned only / In the past**. Rolling forward recreates it **empty** |
| **What is preserved** | Everything else, verified in the rehearsal: 55 of 57 tables byte-identical, chapter text and embeddings equal. Characters keep name, role, status, aliases, description and profile; the one other difference was a system timestamp |
| **Manuscripts, chapters, author content** | **Preserved.** No chapter, note, character, embedding or upload was lost |
| **After a rollback** | Characters show no presence label until the author sets one again (profile panel). "By importance" ordering treats unlabelled characters as on page. Cast generation does **not** relabel existing characters. This only applies to rollbacks across Stage 12 |

**Reply:** `Rollback presence loss: accept as satisfying "without data loss" | require a data-preserving downgrade`

---

## Section 7 — Infrastructure waivers (none recorded yet)

Full drafts: `draft-waivers.md`. The "technical recommendation" lines are factual risk statements, not decisions.

### W-1 — CI
- **Requirement:** tests run on every change; failing changes cannot merge.
- **Why open:** deferred by you (2026-09-22).
- **Risk:** a regression merges without anyone running the suites.
- **Mitigation present:** the one-command full regression; every stage ran it before approval; the dependency gate script; `make docs-check`.
- **If waived:** release proceeds with manual test discipline only.
- **Closes when:** the workflow is restored and made a required check.
- **Technical view:** **low data risk.** The risk is to code quality, not author data. It is safe to defer if every release is preceded by the full regression run, with the result recorded.

### W-2 — Docker / MV-10.3 (PG-04)
- **Requirement:** a clean container build works, with image digests pinned.
- **Why open:** no Docker on RunPod.
- **Risk:** a single deployment path (the bootstrap script plus RunPod's image).
- **Mitigation present:** pinned dependencies and models; three successful from-scratch bring-ups; a documented rollback.
- **If waived:** the Docker files stay unverified.
- **Closes when:** `scripts/verify_containers.sh` passes on any Docker host.
- **Technical view:** **low data risk; operational only.** It is safe to defer while RunPod with `start-narratiq.sh` is the only production target.

### W-3 — Off-pod backup copy ⚠
- **Requirement:** backups stored off the pod, so losing the RunPod network volume does not lose them.
- **Why open:** no external storage provider approved (S10-B). The hook `NARRATIQ_OFFPOD_COMMAND` is ready.
- **Risk:** **losing the network volume loses the live database AND every backup, at the same moment. All author manuscripts would be unrecoverable.** This project has already had full pod or volume resets (2026-09-21: "the manuscript … recorded as lost"; 2026-10-03: this pod started empty with no usable backup).
- **Mitigation present:** hourly on-pod backups with verified restores. These cover a database or container loss, **not volume loss**. There is no mitigation against volume loss.
- **If waived:** authors' unpublished work depends entirely on one RunPod volume.
- **Closes when:** an approved destination plus `NARRATIQ_OFFPOD_COMMAND` (recommended: encrypt each set with a public key whose private key never leaves the owner), and one verified off-pod restore.
- **Technical view:** **not technically safe to defer once real author data is on the platform.** It is the only open item whose failure means permanent loss of authors' manuscripts, and this project has a recorded history of volume or pod loss. Deferring it is defensible only while the platform holds no real author data, or with a manual off-pod copy routine the owner commits to. The implementation is small (the hook exists); the blocker is choosing a provider.

### W-4 — Alerts delivered to a person
- **Requirement:** a person is notified when the service degrades or backups fail.
- **Why open:** no channel approved (S10-D). Alerts go to `alerts.jsonl`.
- **Risk:** an outage, a failed backup or a stale backup goes unnoticed. This **also weakens W-3**: a stopped backup loop would not be noticed.
- **Mitigation present:** the alert log, `/api/ops/metrics`, health checks.
- **If waived:** someone must check the logs regularly.
- **Closes when:** a channel is connected through `NARRATIQ_ALERT_COMMAND` and a test alert is confirmed by a person.
- **Technical view:** **moderate.** No direct data loss, but it removes early warning of backup failure. Safer to defer only with a stated manual check routine (for example daily), until a channel is approved.

### W-5 — `SECRET_KEY` in a team secret store
- **Requirement:** the key is stored off the pod.
- **Why open:** no store is reachable from the agent environment. A **new** key was generated on 2026-10-03.
- **Risk:** losing `backend/.env` signs every author out once. **No author data is lost.**
- **Mitigation present:** signing in again restores access.
- **If waived:** a one-time sign-out after any `.env` loss.
- **Closes when:** you copy the current key to a password manager (`runpod-environment-variables.md` §3.3). A 2-minute owner action.
- **Technical view:** **very low risk; trivially closable.** It is cheaper to close than to waive.

**Reply per waiver:** `W-1=accept|reject, W-2=…, W-3=…, W-4=…, W-5=…` (with any conditions).

---

## AWT-G result (measured 2026-10-03; full record `awt-g-consistency.md`)

- **Trials:** 12 scenarios × **10** trials = 120 transforms, with the existing golden-set tool unchanged (trial count set at runtime), prompt v4.
- **Result:** mean stdev text **0.0866**, content **0.0271**, against the v1 baseline of 0.0643 / 0.0163 that 5.12-G was ticked against. **Criterion not met.**
- **Cause:**
  - 3 of 12 scenarios flip between "returned unchanged" and "rewritten" (gothic-1 1/10 unchanged, tech-1 3/10, tech-4 4/10); they average 0.253.
  - The other 9 average **0.031**, within baseline.
  - The temperature-0 no-change assessor, called 20 times with identical input, said "needs change" 19/20, 15/20 and 3/20. The model server's greedy decoding is not bit-deterministic on borderline yes/no questions.
- **Classification:** **model-serving variability on borderline passages**, not a deterministic NarratIQ defect. No change made: a verdict cache would only make the metric look better.
- **Author impact:** a borderline passage may come back "unchanged, with a reason" one time and rewritten the next. Both are honest; nothing is replaced without the author choosing. No data risk.
- **Your decision (Section 3, G2):** accept as documented model variability, or require work: (a) a stable verdict per passage, (b) a margin-based assessor, or (c) a serving configuration test. Each would need its own measurement.
