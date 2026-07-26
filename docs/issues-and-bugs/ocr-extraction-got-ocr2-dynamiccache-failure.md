# OCR extraction fails: `'DynamicCache' object has no attribute 'seen_tokens'`

| | |
|---|---|
| **Recorded** | 2026-07-26 |
| **Found during** | Checklist task **3.10** (OCR upload interface renders — Phase 2 Issue 6) |
| **Status** | Open — **not** part of task 3.10; recorded so it is not lost |
| **Severity** | High — the OCR feature is reachable and correct in the UI, but no image can currently be read |
| **Area** | Backend / model runtime |

## Summary

Task 3.10 fixed the reason the OCR panel rendered empty. With the panel rendering,
extraction was exercised end to end and **fails inside the OCR model**. This is a
different defect from the one Phase 2 Issue 6 describes, in a different layer, and
was deliberately not chased inside task 3.10 (user direction, 2026-07-26).

## Reproduction

```bash
curl -s -X POST "http://localhost:8000/api/ocr/extract/{story_id}" \
  -H "Authorization: Bearer $TOKEN" -F "file=@some-image.png"
# → {"detail":"OCR processing failed unexpectedly. Please try again."}
```

Backend log (`/tmp/narratiq-logs/backend.log`, 2026-07-26 12:53–12:54):

```
[ocr] upload accepted: c9c6557f (0.0 MB, story=6aae9f61)
[ocr] Processing …png (1800×600px) with GOT-OCR2.0
[ocr] Loading GOT-OCR2.0 from /workspace/models/GOT-OCR2_0...
[ocr] GPU survey (1 GPU(s), need ≥2.5 GB): GPU 0 (NVIDIA A40): 4.26/44.4 GB free
[ocr] GOT-OCR2.0 → device: cuda:0
[ocr] GOT-OCR2.0 ready on GPU (cuda:0).
[ocr] Inference on GPU (cuda:0)…
[ERROR] routers.ocr: [ocr] unexpected pipeline error: 'DynamicCache' object has no attribute 'seen_tokens'
```

Everything up to inference works: upload accepted, size guard passed, file written,
model located, GPU selected, weights loaded. The failure is in the generate call.

## Likely cause

`seen_tokens` was removed from `transformers`' `DynamicCache`. GOT-OCR2.0 ships
custom modelling code (`trust_remote_code`) written against the older API, so the
vendored code and the installed `transformers` version disagree. This is the same
class of problem as the `ovis.py` `AutoConfig.register(exist_ok=True)` patch that
`start-narratiq.sh` already applies for vLLM.

Note the pod's GPU changed on 2026-07-26 (1 × A40, was 2 × RTX PRO 4500 Blackwell),
but nothing in this trace is GPU-specific — the model loads onto the A40 fine.

## What is NOT affected

- The OCR **interface** renders correctly, including for stories with no chapters (task 3.10).
- The OCR **injection** path is verified working for all four destinations —
  `story_notes`, `note_card`, `character_profile`, `chapter_draft` — exercised through
  `POST /api/ocr/confirm` with database-level confirmation of each target row.
- Upload validation, ownership checks, size limits and the idempotency guard all behave.

So the defect is isolated to image → text conversion.

## Candidate remedies (not evaluated)

1. Patch the vendored GOT-OCR2.0 modelling code to the current cache API, in the same
   style as the existing `ovis.py` patch in `start-narratiq.sh`.
2. Pin a `transformers` version compatible with the vendored code — needs checking
   against vLLM, which shares the environment.
3. Fall back to the Tesseract path when the vision model raises, so the feature
   degrades instead of failing (`services/ocr_service.py` already has engine selection).

Option 3 is the smallest honest improvement; options 1 and 2 are the real fix.

## Suggested destination

A task in **Stage 3** alongside the other Phase 2 defects, or Stage 10 production
readiness if it is judged non-blocking. It should not be folded into 3.10, whose
definition of done is the interface being reachable.
