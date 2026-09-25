"""
Stage 5 task 5.8 — emotion measurement harness.

The golden-set harness (measure_transform_golden_set.py) drives tone, style
and age-adapt only; emotion was never measured. This harness runs several
emotions x 2 intensities over the same golden-set passages with the
CURRENTLY CONFIGURED prompt_version and writes a JSON report.

Metrics (deterministic proxies — NOT a measurement of subjective quality):
  - text_similarity    : difflib ratio, original vs transformed (per trial)
  - content_similarity : BGE-M3 cosine, original vs transformed (optional)
  - distinctness       : for each passage + intensity, the mean pairwise
                         difflib similarity between the outputs for DIFFERENT
                         emotions. Lower = more distinct. The 5.8 box
                         "distinct emotions produce measurably distinct
                         outputs" is judged on this number.
  - shared_phrase_rate : share of 3-word phrases (not in the original) that
                         appear in the outputs of 2+ different emotions for
                         the same passage — high means the emotions collapse
                         into the same generic phrasing.

Runs against the live model on the pod (the real measurement is manual
verification MV-5.8). tests/test_measure_emotion_set.py proves the metric
and report logic against a mocked transform in the cloud.

Usage:
    cd backend && python3 tests/measure_emotion_set.py --label after_v3
    cd backend && python3 tests/measure_emotion_set.py --label after_v3 --no-embeddings
"""
import argparse
import asyncio
import itertools
import json
import statistics
import sys
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

EMOTIONS = ["joy", "sadness", "fear", "anger"]   # ids from frontend lib/transforms.ts EMOTIONS
INTENSITIES = ["low", "high"]                  # the two ends of the product's low|medium|high
PASSAGE_IDS = ["gothic-1", "tech-1", "adventure-1"]
N_TRIALS = 2


def text_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


def _trigrams(text: str) -> set[tuple[str, ...]]:
    words = [w.strip(".,;:!?\"'()").lower() for w in text.split()]
    words = [w for w in words if w]
    return {tuple(words[i:i + 3]) for i in range(len(words) - 2)}


def distinctness(outputs_by_emotion: dict[str, list[str]]) -> float:
    """Mean pairwise similarity between outputs of DIFFERENT emotions
    (every trial of one emotion against every trial of another)."""
    sims = []
    for e1, e2 in itertools.combinations(sorted(outputs_by_emotion), 2):
        for a in outputs_by_emotion[e1]:
            for b in outputs_by_emotion[e2]:
                sims.append(text_similarity(a, b))
    return round(statistics.mean(sims), 4) if sims else 0.0


def shared_phrase_rate(original: str, outputs_by_emotion: dict[str, list[str]]) -> float:
    """Share of NEW 3-word phrases used by two or more different emotions."""
    base = _trigrams(original)
    per_emotion = {e: set().union(*(_trigrams(o) for o in outs)) - base
                   for e, outs in outputs_by_emotion.items() if outs}
    all_new = set().union(*per_emotion.values()) if per_emotion else set()
    if not all_new:
        return 0.0
    shared = {g for g in all_new if sum(g in s for s in per_emotion.values()) >= 2}
    return round(len(shared) / len(all_new), 4)


async def run(transform, passages: list[dict], embed=None, n_trials: int = N_TRIALS) -> dict:
    """transform(text, emotion, intensity) -> result dict or str.
    embed(text) -> vector, or None to skip content similarity."""
    import numpy as np

    async def content_sim(a: str, b: str):
        if embed is None:
            return None
        ea, eb = np.array(await embed(a)), np.array(await embed(b))
        return float(ea @ eb / (np.linalg.norm(ea) * np.linalg.norm(eb)))

    report = {"scenarios": [], "distinctness": [], "summary": {}}
    for passage in passages:
        for intensity in INTENSITIES:
            by_emotion: dict[str, list[str]] = {}
            for emotion in EMOTIONS:
                outs = []
                for _ in range(n_trials):
                    result = await transform(passage["text"], emotion, intensity)
                    out = result["transformed"] if isinstance(result, dict) else result
                    outs.append(out)
                    report["scenarios"].append({
                        "passage_id": passage["id"], "emotion": emotion, "intensity": intensity,
                        "text_similarity": round(text_similarity(passage["text"], out), 4),
                        "content_similarity": await content_sim(passage["text"], out),
                        "unchanged": out.strip() == passage["text"].strip(),
                        "output": out,
                    })
                by_emotion[emotion] = outs
            report["distinctness"].append({
                "passage_id": passage["id"], "intensity": intensity,
                "mean_cross_emotion_similarity": distinctness(by_emotion),
                "shared_phrase_rate": shared_phrase_rate(passage["text"], by_emotion),
            })
    d = [x["mean_cross_emotion_similarity"] for x in report["distinctness"]]
    sp = [x["shared_phrase_rate"] for x in report["distinctness"]]
    ts = [x["text_similarity"] for x in report["scenarios"]]
    report["summary"] = {
        "scenarios": len(report["scenarios"]),
        "mean_text_similarity": round(statistics.mean(ts), 4) if ts else None,
        "unchanged_outputs": sum(x["unchanged"] for x in report["scenarios"]),
        "mean_cross_emotion_similarity": round(statistics.mean(d), 4) if d else None,
        "max_cross_emotion_similarity": max(d) if d else None,
        "mean_shared_phrase_rate": round(statistics.mean(sp), 4) if sp else None,
    }
    return report


async def _main(label: str, use_embeddings: bool) -> None:
    from config import settings
    from services.ai_service import rewrite_emotion, embed_text
    from tests.fixtures.transform_golden_set import PASSAGES

    passages = [p for p in PASSAGES if p["id"] in PASSAGE_IDS]
    print(f"Emotion measurement — prompt_version={settings.prompt_version}, label={label}")
    report = await run(lambda t, e, i: rewrite_emotion(t, e, i), passages,
                       embed=embed_text if use_embeddings else None)
    report["label"], report["prompt_version"] = label, settings.prompt_version
    out = Path(__file__).parent / "fixtures" / f"emotion_measurement_{label}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    print(f"Report written to {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--no-embeddings", action="store_true")
    args = ap.parse_args()
    asyncio.run(_main(args.label, not args.no_embeddings))
