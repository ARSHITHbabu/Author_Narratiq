# Stage 12.1 — final owner decision package (2026-10-03)

Supersedes the open items of `stage-12.1-decision-sheet.md`. Evidence is already recorded; nothing is regenerated. **Technical recommendations are engineering advice, not decisions.** Subjective readings are marked **HUMAN DECISION REQUIRED**.

**Already decided (applied at closure):**
- 4.9 Option B (CAST-H8 not applicable);
- the Story Bible example-leak fix;
- translation stays open;
- AWT-G recording direction;
- **task 4.1 manual box: TICK** (live automated browser check, 3/3).

**Author-data rule used throughout:** every AI transform, suggestion and analysis is advisory. Nothing replaces chapter text until the author presses Replace or Apply. "Data loss" below therefore means loss of stored manuscript data, not a poor suggestion.

## A — Human AI quality

**A1 — Blind rewrite review (MV-5.BR).**
- **Covers:** AWT-A, B, E, F, H, J (Critical); 22 High (tone, emotion, audience, style).
- **Evidence:** golden-set measurements show v4 ≥ v2 on the automated proxies (5.16; Tranche 2). The blind preference itself has never been collected.
- **Risk:** rewrites that read worse than the old prompts, or unlike the author's voice. Advisory only.
- **Author data at risk:** no.
- **Recommendation: MUST COMPLETE BEFORE RELEASE. HUMAN DECISION REQUIRED.**
- **Reason:** "blind author review passes" is a Gate 3b exit criterion in its own words. No metric can stand in for it. It takes about 30 minutes: 12 pairs.
- **If you accept without reviewing:** Gate 3b would be ticked against a criterion that was never performed. I advise against this.

**A2 — Light vs Strong.**
- **Covers:** AWT-D, AWT-I (Critical); AWT-1.2, 1.6, 3.7 (High).
- **Evidence:** median share of the author's words kept: tone 0.57 at Light vs 0.58 at Strong; age adaptation 0.52 vs 0.48. Style works (0.71 vs 0.58).
- **Risk:** an author who asks for a light touch gets a near-full rewrite for tone and age adaptation. Advisory only.
- **Author data at risk:** no.
- **Recommendation: HUMAN DECISION REQUIRED (15-pair sample).**
- **Technical view:** the measurement already shows Light is barely distinguishable from Strong for these two transforms. **Do not accept this as "working".** Your labels can only decide whether it is an acceptable limitation, or whether to add a warning or retry threshold.
- **If you accept as a limitation:** the five issues close as a known limitation, which must be published in 12.2. The strength control for tone and age adaptation stays nominal.

**A3 — Children's rewrites.**
- **Covers:** the Tranche 2 meaning review; with A1, AWT-3.1/3.2/3.3/3.5.
- **Evidence:** false "already suitable" 8/10 → 0/10 (A14). **Meaning preservation is not measured by any automated check.**
- **Risk:** a death or grief event softened into a different meaning ("went away") in a children's version.
- **Author data at risk:** no, the author sees the rewrite before Replace.
- **Recommendation: HUMAN DECISION REQUIRED, before release** (16 rewrites, about 15 minutes).
- **Reason:** the issue is meaning, and only a reader can judge it.
- **If you accept unread:** the audience items close without any evidence on meaning.

**A4 — MV-5.14-D (5.14's three Story Audit items).**
- **Covers:** AUDIT-C1–C5 (Critical); AUDIT-H6–H10 (High).
- **Evidence:**
  - **C4 timeline:** the planted reversal was reported 3/3; the marked-flashback false report is fixed (3/3 → 0/3).
  - **C5 narrative:** every finding cites real chapters, and the "character disappears" finding was listed.
  - **M11 relationship arcs:** correct names, chapter chip and no raw ids, but only **one pair on the fixture**.
  - Weak findings appear on tiny fixtures ("Felix burned the rye").
- **Risk:** irrelevant or weak continuity findings waste the author's time. All findings are citation-checked.
- **Author data at risk:** no.
- **Recommendation: ACCEPT WITH FOLLOW-UP** for C4, C5 and M11. Follow-up: measure finding relevance, and relationship arcs with several pairs, on a real-length manuscript.
- **Reason:** each item's own technical criterion was met live. What remains is usefulness on real books.
- **If you accept:** 5.14 closes, and its three items are ticked with the follow-up recorded. G5 is decided by the separate `G5=` line in the template.

**A5 — Story Bible semantic accuracy** ("never asserts unsupported facts").
- **Evidence:**
  - citation coverage: characters 28/28, locations 12/12, timeline 13/13, world rules 6/6, **themes 7/11**;
  - the copied-example hallucination is fixed (0 leaks in 10 × 5 sections).
  - No reading against the manuscript has been done since the fix.
- **Risk:** the bible presents itself as facts about the author's book, so an unsupported statement misinforms the author.
- **Author data at risk:** no (separate table; regenerable).
- **Recommendation: HUMAN DECISION REQUIRED, before release** (one bible, about 20 minutes; read themes most closely).
- **Reason:** citations prove a source exists, not that the source supports the claim.
- **If you accept unread:** the Gate 2 phase-text item closes on citation coverage alone.

**A6 — Remaining per-task author reviews.**

| Box (checklist line) | Overlaps | Recommendation |
|---|---|---|
| 5.7 "Author review on tone transforms" (L1831) | A1 | follows A1 |
| 5.13 "suggestions identify real weaknesses" (L1955) | G6 | follows G6 |
| 5.15 "numbers are interpretable" (L2003) | none | HUMAN DECISION REQUIRED (look at the Analytics numbers once) |
| 5.16 "Conduct blind author review" / "passes" (L2018, L2021) and the Stage 5 gate line (L2033) | A1 | follow A1 |
| 7.12 "golden-set author review confirms style match" (L2492) and 7.x "all eleven capabilities" (L2538) | A1 (style) | HUMAN DECISION REQUIRED (style match). L2538 is also open on the P3-02 ⌘Z browser check |
| 8.3 / 8.4 / 8.5 author reviews (L2627, L2644, L2659) | G8 | follow G8 |

**Recommendation:** answer them together with A1, G6 and G8. **DEFER** any you do not personally do. None is technically substitutable.

## B — Known limitations

**B1 — AWT-G** (Critical, run-to-run consistency).
- **Evidence:**
  - 120 transforms: mean stdev **0.0866** vs the **0.0643** baseline, so the **criterion is NOT met**;
  - the variability sits in the "already suitable" decision (19/20, 15/20, 3/20; and `adventure-3` 9/10 in today's regression); the rewrites themselves are stable (0.031).
- **Risk:** the same request can say "already suitable" once and rewrite the next time.
- **Author data at risk:** no (Replace is required).
- **Recommendation: ACCEPT as a documented known limitation.**
- **Reason:** no code defect exists, and the only lever is a model or serving change, which is a separate project. Your direction forbids metric workarounds.
- **If you accept:** the Critical closes as an *accepted limitation*, with the original criterion recorded as **not met**. It must be in the 12.2 known-limitations list. The `adventure-3` invariant can fail about 1 run in 10.

**B2 — CAST-H6** (High, role classification).
- **Evidence:**
  - a reluctant ally is labelled antagonist 11/25;
  - the prompt fix was worse (22/25) and was reverted;
  - roles are editable, and invalid roles fall back to "supporting".
- **Risk:** a wrong role suggestion for a morally ambiguous character.
- **Author data at risk:** no. The author confirms or edits roles, and existing characters are never relabelled.
- **Recommendation: ACCEPT** as a documented limitation.
- **Reason:** advisory and correctable. Deeper work would be new design with an uncertain gain.
- **If you accept:** CAST-H6 closes as accepted, with a known-limitations entry: "review AI-suggested roles".

**B3 — PA-C6** (Critical, Plot Assistant context prioritisation).
- **Evidence:**
  - critical evidence reaches the model 12/12 (11/12 after a re-index);
  - ranked above every decoy only **7/12** (6/12), or 8/12 chapter-capped, so the **criterion is NOT met**;
  - cause: BGE-M3 semantic similarity, not a deterministic NarratIQ code defect;
  - no fixture-specific weighting was implemented;
  - **the effect of ordering on answer quality was not measured.**
- **Risk:** a similar-sounding passage sits above the decisive one, and the answer may weigh it.
- **Author data at risk:** no.
- **Recommendation: ACCEPT as a known limitation for this release, with a post-release follow-up.** The follow-up: a retrieval-design change (re-ranker, query expansion or summary blend) measured on a second, held-out manuscript.
- **Reason:** recall is intact, and the fix is design work, not a defect correction.
- **If you accept:** the Critical closes as accepted, with the criterion recorded as not met, a known-limitations entry, and a follow-up box.

**B4 — PA-H12** (High, minor vs major events).
- **Evidence:** 1/2 abstract scenarios pass. "What major thing did Liesel Marr do" never retrieves the poisoning passage (not in the top 40).
- **Risk:** abstract "what was important" questions can miss the key event entirely. A specific question works.
- **Author data at risk:** no.
- **Recommendation: ACCEPT with the same follow-up as B3.**
- **Reason:** same root cause, and High rather than Critical.
- **If you accept:** as for B3. The known-limitations text should say "ask specific questions".

## C — Usage reviews

| Group | Issues | Technical evidence | Sufficient? | Recommendation |
|---|---|---|---|---|
| **G6 Suggestions** | SUG-C1, C2 (Critical); H3–H8, H10, H11 (High) | praise and empty items filtered; duplicates removed; recall 0.933 is a **keyword proxy**; 11 categories | **No.** "Reads like a developmental editor" is not measurable by the proxy | **HUMAN DECISION REQUIRED**: about 30 minutes using Suggestions on your own chapters; otherwise DEFER to UAT |
| **G7 Plot Assistant** | PA-C1, PA-C9 (Critical); PA-H10, H11, H13 (High) | PA-C1 technically verified (live 3/3); long-manuscript coverage: revelations 4/7 in summaries, character coverage 3/3, 4/6, 4/5 | **Technical part yes; answer soundness no** | **HUMAN DECISION REQUIRED**: about 30 minutes of questions on a story you know; otherwise DEFER to UAT. PA-H14 is UAT-only (F) |
| **G8 Studio UI** | UI-C1, C2, C6 (Critical); H9, H10, H11, H13, H14 (High) | controls reduced 34 % / 25 %; modes tested; palette reach; axe clean | **No.** Focus, congestion and discoverability are perceptual | **HUMAN DECISION REQUIRED**: MV-8.5 steps 1–4 (about 45 minutes); otherwise DEFER. UI-H12 needs the multi-hour session (F) |

## D — Security, rollback and UAT

| # | Risk | Reachable? | Author data at risk? | Recommendation | Consequence of accepting |
|---|---|---|---|---|---|
| **S1** | Residual prompt injection (P1/A18): paraphrased obedience not caught; nameless sources never flagged; analyses rely on the fence | Yes, but only an author's **own** text affecting **their own** results (no sharing) | No: the output is advisory, and there is no cross-user path | **ACCEPT** | A18 owner box ticked; residual risk published. Follow-up box (probe coverage) stays open |
| **S2** | vLLM 0.9.2 (2 Critical / 10 High), xgrammar 2 High, transformers 4 High | Not externally: 127.0.0.1 only, the backend is the only client, the model is text-only | No | **CONFIRM** the 2026-10-02 acceptance | That acceptance covered the vLLM serving stack at 0.9.2 under the loopback bind. **Nothing material has changed:** same pinned version and the same 2 Critical / 10 High; loopback re-verified 2026-10-03; no new reachable path |
| **S3** | transformers ×4, ecdsa (requirements, High) | No (needs untrusted model files; HS256 only) | No | **ACCEPT** | Documented as unreachable |
| **S4** | lxml XXE, urllib3 ×6, soupsieve ×2 | No (lxml **proven** by test; the others are unused or used only for trusted downloads) | No | **ACCEPT** (hygiene upgrades post-release) | Documented as unreachable |
| **S5** | Pod-image Jupyter stack (2 Critical / 33 High) | Not NarratIQ code; JupyterLab returns 403 without auth | Low but non-zero: it is on the same pod | **ACCEPT now; remove Jupyter from the template** when convenient (external) | Pod template unchanged |
| **S6** | npm postcss (production, build time) and braces (dev) | No (build time, own files) | No | **ACCEPT** | Documented; fixed by the Next 16 / Tailwind 4 majors later |

**Rollback presence-label loss (10.5 "without data loss").**
- **Lost:** only `characters.presence` (On page / Mentioned only / In the past), when rolling back past migration `0027`. It comes back empty when rolling forward.
- **Preserved (verified):** 55/57 tables byte-identical; all chapters, notes, characters (name, role, status, aliases, description, profile), embeddings and uploads. The other difference was a system timestamp.
- **Effect:** labels must be re-set by hand; "by importance" ordering treats unlabelled characters as on page. It only affects a rollback across Stage 12.
- **Recommendation: ACCEPT.**
- **Reason:** no manuscript data is lost; the label is an author-editable classification. A data-preserving downgrade costs migration work for a rare path.
- **If you accept:** 10.5 "without data loss" is ticked with this exception recorded.

**Real-author UAT (9.6).**
- **Unverified without it:**
  - whether real authors find the rewrites, suggestions, Plot Assistant and Studio useful (PA-H14; most of G6–G8);
  - the 9.3 Tier-2 confirmation;
  - learnability and the onboarding journey;
  - multi-hour fatigue (UI-H12, 8.11).
- **Engineering cannot run or waive UAT.**
- **Recommendation: MUST COMPLETE BEFORE RELEASE** if NarratIQ is released to authors. Releasing without it is your decision.
- **If you choose to release without it:** UAT boxes stay open, and the release decision is recorded in 12.3.

**Legal 11.7:** separate, stays open.

## E — Waivers

**W-1 — CI.**
- **Risk:** a regression merges unnoticed.
- **Current mitigation:** the one-command full regression, run before every approval.
- **Blocks safe release?** No.
- **Recommendation: ACCEPT (waive)**, on condition that every release records a full regression run.

**W-2 — Docker / MV-10.3 (PG-04).**
- **Risk:** a single deployment path.
- **Current mitigation:** pinned dependencies and models; 3 from-scratch bring-ups; rollback rehearsed.
- **Blocks safe release?** No, while RunPod is the only target.
- **Recommendation: ACCEPT (waive).**

**W-3 — Off-pod backup ⚠.**
- **Risk:** **losing the RunPod network volume loses the production database and every on-volume backup at the same moment.** All authors' manuscripts would be **permanently unrecoverable**.
- **History:** this project has already lost data this way twice:
  - 2026-09-21, "manuscript … recorded as lost";
  - 2026-10-03, this pod started empty with no usable backup.
- **Current mitigation:** hourly on-pod backups with verified restores. These cover database or container failure **only, not volume loss**. **There is no mitigation for volume loss.**
- **Blocks safe release?** **YES, once real author data is on the platform.**
- **Recommendation: MUST COMPLETE BEFORE RELEASE.**
  - Choose a destination.
  - Set `NARRATIQ_OFFPOD_COMMAND`, ideally with public-key encryption.
  - Do one verified off-pod restore.
- **Engineering work once you name the provider is small;** the hook already exists.
- **A waiver is defensible only if no real author data will be stored before it is in place.**

**W-4 — Alerts to a person.**
- **Risk:** outages and **failed or stopped backups go unnoticed**, which also weakens W-3.
- **Current mitigation:** `alerts.jsonl`, `/api/ops/metrics`, the health check.
- **Blocks safe release?** Not alone.
- **Recommendation: ACCEPT (waive) only with a committed daily manual check**, until a channel is approved.

**W-5 — `SECRET_KEY` copy.**
- **Risk:** losing `backend/.env` signs every author out once. No data is lost.
- **Current mitigation:** signing in again.
- **Blocks safe release?** No.
- **Recommendation: CLOSE IT. This is an owner action, not engineering:**
  1. On the pod: `grep ^SECRET_KEY= /workspace/Author_Narratiq/backend/.env`
  2. Paste the value into your password manager or team secret store, as "NarratIQ production SECRET_KEY (pod x0smrkvs4n6wpk, generated 2026-10-03)".
  3. Reply `W-5=closed (copied)`. Do not paste the key into this chat.

## F — Cannot be closed now (stay open whatever the answers)

| Needs | Items |
|---|---|
| **Fluent speaker** | AWT-5.1–5.7; task 5.11 "golden-set translation reviewed by a fluent speaker" |
| **Real authors** | UAT 9.6; PA-H14; 9.3 Tier-2 confirmation; MV-10.8 onboarding limit (owner, informed by UAT) |
| **Multi-hour session** | 8.11 / MV-8.7; UI-H12 |
| **Legal review** | 11.7 copyright-risk disclaimer (9.4 legal half) |
| **External infrastructure** | 6.1 CI; MV-10.3 Docker build; 10.1 off-pod copy (W-3); 10.2 alert channel (W-4); Jupyter removal from the pod template. A waiver records a decision; the item stays not done |
| **Owner decision not inferable** | telling intentional deletion apart from data loss at startup (option a or b); the MV-10.8 onboarding limit |
| **Follow-ups (non-blocking)** | injection-probe coverage; the 4.9 relationship-accuracy follow-up; the B3/B4 retrieval-design follow-up (if accepted) |
| **Technical, ticked at closure from evidence** | the A13 long-manuscript measurement follow-up (measured: `pa-long-manuscript-measurement.md`); the 4.1 manual box (your TICK) |
