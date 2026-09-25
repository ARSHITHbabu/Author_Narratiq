"""
Phase 3 P3-04 — AI comparison summary and merge smoothing (spec §23.4, §23.5).

The DIFF itself is client-side (frontend/lib/diff.ts): both inputs are
already in the browser, and a live generation must never be uploaded just to
be compared (R1). The server only does the two optional AI steps:

  compare_summary   best-effort description of the trade-off between two
                    versions. Strict JSON via _extract_json with a {} fallback,
                    temperature 0.2, both texts capped at 3,000 chars. Nothing
                    stored. Framed as "describe", never "pick a winner".
  smooth_merge      the author chose blocks A/B; the model may touch only the
                    connective tissue between them. Validated deterministically
                    — total word-count delta <= 12 % and EVERY block's lexical
                    similarity to the author's chosen text >= 0.9 — with one
                    retry, then the unsmoothed merge is returned with a
                    warning. The author's chosen blocks are never silently
                    rewritten (R6).
"""
from __future__ import annotations

import logging

from services.similarity import lexical_score

logger = logging.getLogger(__name__)

MAX_WORD_DELTA = 0.12
MIN_BLOCK_SIMILARITY = 0.9


def _coerce_compare(parsed):
    if not isinstance(parsed, dict) or not str(parsed.get("summary") or "").strip():
        return None, 1

    def _strs(v) -> list[str]:
        return [str(x).strip()[:240] for x in (v or []) if str(x).strip()][:5] if isinstance(v, list) else []

    return {
        "summary": str(parsed.get("summary")).strip()[:800],
        "a_strengths": _strs(parsed.get("a_strengths")),
        "b_strengths": _strs(parsed.get("b_strengths")),
        "recommendation": str(parsed.get("recommendation") or "").strip()[:400],
        "available": True,
    }, 0


async def compare_summary(text_a: str, text_b: str) -> dict:
    """Best-effort: {"available": False} when no usable summary comes back.
    Uses complete_structured() (the repo's structured-output contract)."""
    from services.ai_service import complete_structured
    system = (
        "You compare two versions of the same passage for a novelist. Describe how they differ and "
        "what each does well. Do NOT pick a winner. Return ONLY JSON: "
        '{"summary": "2-3 sentences", "a_strengths": ["..."], "b_strengths": ["..."], '
        '"recommendation": "when an author might prefer each"}'
    )
    user = f"VERSION A:\n{text_a[:3000]}\n\nVERSION B:\n{text_b[:3000]}"
    try:
        value, _meta = await complete_structured(system, user, coerce=_coerce_compare, temperature=0.2,
                                                 max_tokens=400, label="compare_summary")
    except Exception as exc:
        if type(exc).__name__ == "AIServiceUnavailableError":
            raise
        logger.warning("[compare_summary] unavailable (%s)", type(exc).__name__)
        return {"available": False}
    return value or {"available": False}


def _split_trailing(text: str) -> tuple[str, str]:
    stripped = text.rstrip()
    return stripped, text[len(stripped):]


def validate_smoothing(original_blocks: list[str], smoothed_blocks: list[str]) -> tuple[bool, float, float]:
    """Deterministic merge-fidelity guard. Returns (ok, word_delta, min_block_similarity)."""
    if len(original_blocks) != len(smoothed_blocks) or any(not b.strip() for b in smoothed_blocks):
        return False, 1.0, 0.0
    ow = sum(len(b.split()) for b in original_blocks)
    sw = sum(len(b.split()) for b in smoothed_blocks)
    delta = abs(sw - ow) / max(1, ow)
    sims = [lexical_score(o, s) if o.strip() else 1.0 for o, s in zip(original_blocks, smoothed_blocks)]
    min_sim = min(sims) if sims else 1.0
    return (delta <= MAX_WORD_DELTA and min_sim >= MIN_BLOCK_SIMILARITY), round(delta, 4), round(min_sim, 4)


async def smooth_merge(blocks: list[str]) -> dict:
    """Returns {merged, smoothed, warnings, word_delta, min_block_similarity}."""
    from services.ai_service import _complete, _extract_json
    unsmoothed = "".join(blocks)
    if len(blocks) < 2:
        return {"merged": unsmoothed, "smoothed": False, "warnings": [], "word_delta": 0.0,
                "min_block_similarity": 1.0}
    cores, trails = zip(*(_split_trailing(b) for b in blocks))
    numbered = "\n".join(f'{i}: {c}' for i, c in enumerate(cores))
    system = (
        "An author assembled a passage from blocks taken from two drafts. Smooth ONLY the joins so the "
        "passage reads as one piece: you may adjust a few connecting words at the start or end of a block "
        "(pronouns, conjunctions, a repeated word). Do not change anything else, do not add or remove "
        "sentences, keep every block's meaning and wording. Return ONLY JSON: "
        '{"blocks": ["block 0 text", "block 1 text", ...]} with exactly ' + str(len(cores)) + " blocks."
    )
    last = (0.0, 0.0)
    for attempt in range(2):   # one retry, then give up — bounded
        try:
            raw = await _complete(system + ("" if attempt == 0 else
                                            " Your previous answer changed the blocks too much. Change even less."),
                                  numbered, temperature=0.2 if attempt == 0 else 0.1,
                                  max_tokens=int(sum(len(c.split()) for c in cores) * 2) + 200,
                                  response_format={"type": "json_object"})
        except Exception as exc:
            if type(exc).__name__ == "AIServiceUnavailableError":
                raise
            logger.warning("[smooth_merge] attempt %d failed (%s)", attempt + 1, type(exc).__name__)
            continue
        data = _extract_json(raw, {})
        out = data.get("blocks") if isinstance(data, dict) else None
        if not isinstance(out, list):
            continue
        out = [str(x) for x in out]
        ok, delta, min_sim = validate_smoothing(list(cores), out)
        last = (delta, min_sim)
        if ok:
            merged = "".join(o.strip() + t for o, t in zip(out, trails))
            return {"merged": merged, "smoothed": True, "warnings": [], "word_delta": delta,
                    "min_block_similarity": min_sim}
    return {
        "merged": unsmoothed, "smoothed": False, "word_delta": last[0], "min_block_similarity": last[1],
        "warnings": [{"kind": "merge_unsmoothed", "severity": "info",
                      "message": "Smoothing would have changed your chosen passages too much, so the "
                                 "merge is shown exactly as you assembled it."}],
    }
