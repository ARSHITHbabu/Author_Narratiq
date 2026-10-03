# A15 sample — Light next to Strong (15 pairs)

For each pair: (1) is the **Light** rewrite an acceptable *light* edit? (2) Is Light **clearly lighter** than Strong? Answer each: yes / no. Tone and age adaptation are the transforms under question; style is included as a control (measured as working). Source: `strength_t2b_after_v4.json` (prompt v4).

## S1. tone → suspenseful — passage `adventure-3`

**Original**

> The children's version of the story left out the part where nobody survived the first crossing. This was, Mira thought, probably for the best.

**Light**

> The children's version of the tale omitted the chilling detail where everyone perished during the initial journey. Mira surmised that this omission was likely for the better.

**Strong**

> The children's version of the tale omitted the chilling detail where all souls perished during the initial journey. Mira mused that perhaps this omission served a greater good.

*Words kept — Light 0.542 · Strong 0.417*

**(1) Light acceptable?** yes / no — **(2) clearly lighter than Strong?** yes / no

---

## S2. tone → suspenseful — passage `adventure-4`

**Original**

> The old guide had warned them about the pass, the weather, and the wolves, in that order, as if the order mattered.

**Light**

> The old guide had foretold the perils of the pass, the treacherous weather, and the lurking wolves, in that specific sequence, as if the order held some ominous significance.

**Strong**

> The old guide had warned them about the pass, the weather, and the wolves, in that order, as if the order mattered—each word a harbinger of doom, each phrase a silent scream in the cold, empty air.

*Words kept — Light 0.773 · Strong 1.0*

**(1) Light acceptable?** yes / no — **(2) clearly lighter than Strong?** yes / no

---

## S3. tone → suspenseful — passage `gothic-1`

**Original**

> The house had not been opened in eleven years, and the air inside kept the shape of that absence — still, cold, faintly sweet with dust. Mira did not call out. There was no one left to answer.

**Light**

> The house, untouched for eleven years, held the silence of its absence—still, cold, faintly sweet with dust. Mira moved quietly, not calling out. There was no one left to answer.

**Strong**

> The house, untouched for eleven years, exhaled the silence of its solitude—still, cold, and faintly sweet with dust. Mira moved quietly, her breath a ghost in the air, knowing there was no one left to hear her.

*Words kept — Light 0.622 · Strong 0.622*

**(1) Light acceptable?** yes / no — **(2) clearly lighter than Strong?** yes / no

---

## S4. tone → suspenseful — passage `gothic-2`

**Original**

> She had learned, over the years, to say nothing when she was most afraid. The habit had outlived its reason. Even now, alone in the hall, she found herself arranging her face into something calm.

**Light**

> She had learned, over the years, to say nothing when she was most afraid. The habit lingered, a shadow from the past. Even now, alone in the hall, she forced a semblance of calm onto her features.

**Strong**

> She had learned, over the years, to say nothing when she was most afraid. The habit lingered, a shadow in the dark corners of her mind. Even now, alone in the dimly lit hall, she felt her muscles tense as she forced a semblance of calm onto her features.

*Words kept — Light 0.714 · Strong 0.714*

**(1) Light acceptable?** yes / no — **(2) clearly lighter than Strong?** yes / no

---

## S5. tone → suspenseful — passage `gothic-4`

**Original**

> He kept the key on a chain he never removed, not because he expected to need it again, but because a man who has once locked a door does not easily trust himself to leave it unlocked.

**Light**

> He kept the key on a chain he never took off, not anticipating another use for it, yet knowing that a man who had once locked a door found it hard to let it remain unlocked.

**Strong**

> He kept the key on a chain he never took off, not because he anticipated needing it again, but because a man who had once locked a door could not easily trust himself to leave it unlocked.

*Words kept — Light 0.568 · Strong 0.838*

**(1) Light acceptable?** yes / no — **(2) clearly lighter than Strong?** yes / no

---

## S6. tone → suspenseful — passage `tech-1`

**Original**

> The sensor array logged a spike at 03:14, four minutes early relative to the established cycle. Priya flagged the anomaly and ran the calibration a second time. The result did not change.

**Light**

> The sensor array recorded a spike at 03:14, four minutes ahead of schedule. Priya marked the irregularity and reran the calibration. The outcome remained unchanged.

**Strong**

> The sensor array spiked at 03:14, four minutes ahead of schedule. Priya's heart raced as she flagged the anomaly and reran the calibration. The result remained unchanged, leaving her more puzzled than before.

*Words kept — Light 0.485 · Strong 0.485*

**(1) Light acceptable?** yes / no — **(2) clearly lighter than Strong?** yes / no

---

## S7. age_adapt → children — passage `adventure-1`

**Original**

> The bridge gave way behind them with a sound like a held breath finally let go. Kael did not look back. There was nothing behind them worth the half-second it would cost.

**Light**

> The bridge broke behind them with a sound like a deep sigh. Kael did not turn around. There was nothing behind them worth the time it would take to look.

**Strong**

> The bridge broke behind them with a sound like a deep sigh. Kael did not turn around. There was nothing behind them worth the time it would take to look.

*Words kept — Light 0.667 · Strong 0.667*

**(1) Light acceptable?** yes / no — **(2) clearly lighter than Strong?** yes / no

---

## S8. age_adapt → children — passage `adventure-2`

**Original**

> Three arrows, three misses, and the fourth still in her quiver — Aanya was not going to get a fifth chance, and she knew it.

**Light**

> Aanya had three arrows, but she missed with each one. She had one arrow left in her quiver, and she knew she couldn't miss again.

**Strong**

> Aanya had three arrows, but she missed with each one. She had one arrow left in her quiver, and she knew this would be her last chance.

*Words kept — Light 0.375 · Strong 0.417*

**(1) Light acceptable?** yes / no — **(2) clearly lighter than Strong?** yes / no

---

## S9. age_adapt → children — passage `adventure-3`

**Original**

> The children's version of the story left out the part where nobody survived the first crossing. This was, Mira thought, probably for the best.

**Light**

> The story didn't include what happened during the first crossing because everyone got hurt. Mira thought it was better that way.

**Strong**

> Mira thought it was better to leave out the part where nobody survived the first crossing.

*Words kept — Light 0.333 · Strong 0.5*

**(1) Light acceptable?** yes / no — **(2) clearly lighter than Strong?** yes / no

---

## S10. age_adapt → children — passage `gothic-1`

**Original**

> The house had not been opened in eleven years, and the air inside kept the shape of that absence — still, cold, faintly sweet with dust. Mira did not call out. There was no one left to answer.

**Light**

> The house hadn't been opened for eleven years, and the air inside felt empty and cold, with a hint of dust. Mira didn't call out. There was no one left to answer.

**Strong**

> The old house hadn't been opened in many years, and the air inside felt empty and chilly, with a hint of dust. Mira didn't shout. There was no one there to hear her.

*Words kept — Light 0.649 · Strong 0.514*

**(1) Light acceptable?** yes / no — **(2) clearly lighter than Strong?** yes / no

---

## S11. age_adapt → children — passage `gothic-2`

**Original**

> She had learned, over the years, to say nothing when she was most afraid. The habit had outlived its reason. Even now, alone in the hall, she found herself arranging her face into something calm.

**Light**

> She learned to say nothing when she was very scared. This habit stayed with her even when it wasn't needed anymore. Now, all alone in the hall, she tried to look calm.

**Strong**

> She learned, over time, to keep quiet when she felt very scared. This habit stayed with her even though it wasn't needed anymore. Now, all alone in the hall, she tried to look peaceful on her face.

*Words kept — Light 0.514 · Strong 0.457*

**(1) Light acceptable?** yes / no — **(2) clearly lighter than Strong?** yes / no

---

## S12. age_adapt → children — passage `gothic-3`

**Original**

> The letter had said everything and nothing. Devika read it twice, then folded it back along its old creases, as if that alone could undo the reading.

**Light**

> The letter said everything and nothing. Devika read it twice, then folded it back along its old creases, as if that alone could undo the reading.

**Strong**

> Devika read the letter carefully, then folded it again, hoping the words would disappear.

*Words kept — Light 0.963 · Strong 0.296*

**(1) Light acceptable?** yes / no — **(2) clearly lighter than Strong?** yes / no

---

## S13. style → cinematic — passage `adventure-2`

**Original**

> Three arrows, three misses, and the fourth still in her quiver — Aanya was not going to get a fifth chance, and she knew it.

**Light**

> Three arrows, three misses, and the fourth still in her quiver—Aanya knew she wasn't getting a fifth chance.

**Strong**

> Three arrows, each one released with deadly precision, sailed past Aanya's target, leaving her quiver unscathed. Now, with four remaining, the tension in her grip tightened as she knew this would be her last shot—no fifth chance awaited her.

*Words kept — Light 0.708 · Strong 0.417*

**(1) Light acceptable?** yes / no — **(2) clearly lighter than Strong?** yes / no

---

## S14. style → cinematic — passage `adventure-3`

**Original**

> The children's version of the story left out the part where nobody survived the first crossing. This was, Mira thought, probably for the best.

**Light**

> The children's adaptation skipped over the harrowing detail where all had perished during the initial voyage. Mira mused that perhaps it was for the better.

**Strong**

> The children's adaptation omitted the grim detail of the first crossing ending in total loss of life. Mira pondered that perhaps such knowledge was better withheld from younger eyes.

*Words kept — Light 0.375 · Strong 0.375*

**(1) Light acceptable?** yes / no — **(2) clearly lighter than Strong?** yes / no

---

## S15. style → cinematic — passage `adventure-4`

**Original**

> The old guide had warned them about the pass, the weather, and the wolves, in that order, as if the order mattered.

**Light**

> The old guide had cautioned them about the pass, the weather, and the wolves, in that order, as if the sequence held significance.

**Strong**

> The old guide had intoned the warnings about the pass, the weather, and the wolves, each in that specific sequence, as if the order held some critical significance.

*Words kept — Light 0.864 · Strong 0.818*

**(1) Light acceptable?** yes / no — **(2) clearly lighter than Strong?** yes / no

---
