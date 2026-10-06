# A2 re-validation sample — Light next to Strong (post-fix, 15 pairs)

Seed `20261006` (`random.Random("20261006-a2")`). Source `backend/tests/fixtures/strength_t2b_after_v4_light_repair.json`. Rule: For each transform (tone 6, age_adapt 6, style 3): eligible (passage, run) = Light changed the text and did not fail, Strong did not fail (original A2 rule). Sample k passages, then one run per passage.

For each pair: (1) is the **Light** rewrite an acceptable *light* edit? (2) Is Light **clearly lighter** than Strong? Answer each: yes / no. Status: PENDING HUMAN REVIEW.

## R1. tone → suspenseful — passage `tech-1` (run 3)

**Original**

> The sensor array logged a spike at 03:14, four minutes early relative to the established cycle. Priya flagged the anomaly and ran the calibration a second time. The result did not change.

**Light**

> The sensor array recorded an unexpected spike at 03:14, four minutes ahead of schedule. Priya noted the irregularity and reran the calibration. The outcome remained unchanged.

**Strong**

> The sensor array recorded a spike at 03:14, four minutes ahead of schedule. Priya marked the anomaly and reran the calibration. The results remained unchanged.

*Words kept — Light 0.455 · Strong 0.515; new words — Light 0.444 · Strong 0.346*

**(1) Light acceptable?** ☐ yes ☐ no — **(2) clearly lighter than Strong?** ☐ yes ☐ no

---

## R2. tone → suspenseful — passage `gothic-1` (run 2)

**Original**

> The house had not been opened in eleven years, and the air inside kept the shape of that absence — still, cold, faintly sweet with dust. Mira did not call out. There was no one left to answer.

**Light**

> The house, untouched for eleven years, held the silence of that long absence—still, cold, faintly sweet with dust. Mira moved quietly, her voice a whisper in the empty air, knowing there was no one left to hear.

**Strong**

> The house, untouched for eleven years, held its breath—a stale, cold silence, faintly sweet with the scent of dust. Mira moved quietly, her footsteps barely breaking the oppressive stillness. There was no one left to hear her.

*Words kept — Light 0.649 · Strong 0.514; new words — Light 0.368 · Strong 0.5*

**(1) Light acceptable?** ☐ yes ☐ no — **(2) clearly lighter than Strong?** ☐ yes ☐ no

---

## R3. tone → suspenseful — passage `tech-3` (run 3)

**Original**

> The report was three pages, all of it technically accurate and none of it honest about what the numbers actually implied.

**Light**

> The report spanned three pages, each filled with figures that were technically precise yet utterly devoid of truth regarding what those numbers truly signified.

**Strong**

> The report, three pages long, dripped with cold, hard facts—each one meticulously crafted yet devoid of any genuine truth, hiding the shadows behind the figures.

*Words kept — Light 0.381 · Strong 0.286; new words — Light 0.667 · Strong 0.769*

**(1) Light acceptable?** ☐ yes ☐ no — **(2) clearly lighter than Strong?** ☐ yes ☐ no

---

## R4. tone → suspenseful — passage `gothic-2` (run 0)

**Original**

> She had learned, over the years, to say nothing when she was most afraid. The habit had outlived its reason. Even now, alone in the hall, she found herself arranging her face into something calm.

**Light**

> She had learned, over the years, to say nothing when she was most afraid. The habit lingered, a shadow from the past. Even now, alone in the hall, she forced her expression into something semblance of calm.

**Strong**

> She had learned, over the years, to say nothing when she was most afraid. The habit lingered like a shadow, long after its usefulness faded. Even now, alone in the dimly lit hall, she forced her features into an unyielding mask of composure.

*Words kept — Light 0.771 · Strong 0.743; new words — Light 0.27 · Strong 0.395*

**(1) Light acceptable?** ☐ yes ☐ no — **(2) clearly lighter than Strong?** ☐ yes ☐ no

---

## R5. tone → suspenseful — passage `adventure-3` (run 1)

**Original**

> The children's version of the story left out the part where nobody survived the first crossing. This was, Mira thought, probably for the best.

**Light**

> The children's version of the story skipped over the harrowing detail where no one emerged alive from the first crossing. Mira thought this omission might have been wise.

**Strong**

> The children's version of the tale conveniently omitted the grim detail of everyone perishing during the initial voyage. Mira pondered that perhaps it was for the better.

*Words kept — Light 0.583 · Strong 0.458; new words — Light 0.5 · Strong 0.593*

**(1) Light acceptable?** ☐ yes ☐ no — **(2) clearly lighter than Strong?** ☐ yes ☐ no

---

## R6. tone → suspenseful — passage `gothic-4` (run 1)

**Original**

> He kept the key on a chain he never removed, not because he expected to need it again, but because a man who has once locked a door does not easily trust himself to leave it unlocked.

**Light**

> He kept the key on a chain he never took off, not anticipating another use, but knowing that a man who had once locked a door could not easily trust himself to leave it unlocked.

**Strong**

> He kept the key on a chain he never took off, not because he anticipated needing it again, but because a man who had once locked a door found it hard to let it remain unlocked, even when there was no clear threat.

*Words kept — Light 0.703 · Strong 0.703; new words — Light 0.257 · Strong 0.395*

**(1) Light acceptable?** ☐ yes ☐ no — **(2) clearly lighter than Strong?** ☐ yes ☐ no

---

## R7. age_adapt → children — passage `adventure-2` (run 1)

**Original**

> Three arrows, three misses, and the fourth still in her quiver — Aanya was not going to get a fifth chance, and she knew it.

**Light**

> Three arrows, and three misses. Aanya had one arrow left in her quiver. She knew she couldn't miss this time.

**Strong**

> Three arrows, and Aanya missed with each one. She had one arrow left in her quiver. Aanya knew she couldn't miss again.

*Words kept — Light 0.458 · Strong 0.375; new words — Light 0.45 · Strong 0.591*

**(1) Light acceptable?** ☐ yes ☐ no — **(2) clearly lighter than Strong?** ☐ yes ☐ no

---

## R8. age_adapt → children — passage `adventure-1` (run 0)

**Original**

> The bridge gave way behind them with a sound like a held breath finally let go. Kael did not look back. There was nothing behind them worth the half-second it would cost.

**Light**

> The bridge broke behind them with a sound like a held breath finally let out. Kael did not turn around. There was nothing behind them worth the half-second it would take to look.

**Strong**

> The bridge broke behind them with a quiet sound. Kael didn't turn around. There was nothing behind them that needed looking at.

*Words kept — Light 0.848 · Strong 0.394; new words — Light 0.176 · Strong 0.409*

**(1) Light acceptable?** ☐ yes ☐ no — **(2) clearly lighter than Strong?** ☐ yes ☐ no

---

## R9. age_adapt → children — passage `tech-2` (run 3)

**Original**

> Access to the lab required two separate badge scans and a supervisor override after 22:00. Priya had never used the override before tonight.

**Light**

> The lab needed two badge scans and a supervisor's permission after 10:00 PM. Priya had never used the permission before tonight.

**Strong**

> Priya needed two special cards to get into the lab. After 10:00 PM, she also had to ask a grown-up to help her. Priya had never done this before tonight.

*Words kept — Light 0.667 · Strong 0.5; new words — Light 0.273 · Strong 0.625*

**(1) Light acceptable?** ☐ yes ☐ no — **(2) clearly lighter than Strong?** ☐ yes ☐ no

---

## R10. age_adapt → children — passage `tech-3` (run 0)

**Original**

> The report was three pages, all of it technically accurate and none of it honest about what the numbers actually implied.

**Light**

> The report was three pages long, all the information was correct, but it didn't tell the truth about what the numbers meant.

**Strong**

> The report had three pages. All the information was correct, but it didn't tell the whole truth about what the numbers meant.

*Words kept — Light 0.524 · Strong 0.524; new words — Light 0.5 · Strong 0.5*

**(1) Light acceptable?** ☐ yes ☐ no — **(2) clearly lighter than Strong?** ☐ yes ☐ no

---

## R11. age_adapt → children — passage `adventure-3` (run 3)

**Original**

> The children's version of the story left out the part where nobody survived the first crossing. This was, Mira thought, probably for the best.

**Light**

> The story for kids didn't include the part where nobody survived the first crossing. Mira thought this was probably better.

**Strong**

> Mira thought it was better to leave out the part where nobody survived the first crossing.

*Words kept — Light 0.667 · Strong 0.5; new words — Light 0.2 · Strong 0.25*

**(1) Light acceptable?** ☐ yes ☐ no — **(2) clearly lighter than Strong?** ☐ yes ☐ no

---

## R12. age_adapt → children — passage `gothic-4` (run 2)

**Original**

> He kept the key on a chain he never removed, not because he expected to need it again, but because a man who has once locked a door does not easily trust himself to leave it unlocked.

**Light**

> He kept the key on a chain he never took off, not because he thought he would need it again, but because a man who has locked a door before does not easily trust leaving it unlocked.

**Strong**

> He kept the key on a chain he never removed, not because he expected to need it again, but because a man who has once locked a door does not easily trust himself to leave it unlocked.

*Words kept — Light 0.811 · Strong 1.0; new words — Light 0.189 · Strong 0.0*

**(1) Light acceptable?** ☐ yes ☐ no — **(2) clearly lighter than Strong?** ☐ yes ☐ no

---

## R13. style → cinematic — passage `gothic-1` (run 2)

**Original**

> The house had not been opened in eleven years, and the air inside kept the shape of that absence — still, cold, faintly sweet with dust. Mira did not call out. There was no one left to answer.

**Light**

> The house hadn't seen a key in eleven years, and the air inside clung to that absence—still, cold, faintly sweet with dust. Mira didn't call out. There was no one left to answer.

**Strong**

> The house, untouched for eleven years, held the silence like a shroud—still, cold, faintly sweet with dust. Mira moved quietly inside, her voice a whisper against the echo of emptiness. There was no one left to answer.

*Words kept — Light 0.73 · Strong 0.595; new words — Light 0.206 · Strong 0.421*

**(1) Light acceptable?** ☐ yes ☐ no — **(2) clearly lighter than Strong?** ☐ yes ☐ no

---

## R14. style → cinematic — passage `gothic-4` (run 3)

**Original**

> He kept the key on a chain he never removed, not because he expected to need it again, but because a man who has once locked a door does not easily trust himself to leave it unlocked.

**Light**

> He kept the key on a chain he never took off, not because he anticipated needing it again, but because a man who had once locked a door did not quickly trust himself to leave it unlocked.

**Strong**

> He wore the key around his neck on a chain that never left his person, not out of anticipation for its next use, but because a man who had once locked a door found it hard to ever let another pass without guard.

*Words kept — Light 0.811 · Strong 0.514; new words — Light 0.189 · Strong 0.558*

**(1) Light acceptable?** ☐ yes ☐ no — **(2) clearly lighter than Strong?** ☐ yes ☐ no

---

## R15. style → cinematic — passage `tech-2` (run 1)

**Original**

> Access to the lab required two separate badge scans and a supervisor override after 22:00. Priya had never used the override before tonight.

**Light**

> Access to the lab demanded two badge scans and a supervisor override past 10 pm. Priya had never activated the override until tonight.

**Strong**

> Access to the lab demanded two distinct badge scans and a supervisor override past 22:00. For Priya, the override was a mystery, a riddle to be solved tonight alone.

*Words kept — Light 0.708 · Strong 0.708; new words — Light 0.261 · Strong 0.433*

**(1) Light acceptable?** ☐ yes ☐ no — **(2) clearly lighter than Strong?** ☐ yes ☐ no

---
