"""
Stage 5 task 5.12-H — "different authors must not converge on one voice."

Runs the SAME transform on two passages with deliberately distinct voices
(tests/fixtures/voice_convergence_fixture.py) and measures whether their
BGE-M3 content similarity and SequenceMatcher text similarity to EACH OTHER
increase after the transform (convergence, a failure) or stay roughly flat
(voices remain distinguishable).

Metric definitions (same terminology discipline as measure_transform_golden_set.py):
  - content_similarity: BGE-M3 cosine similarity between the TWO outputs
    (or two originals) — "semantic/content similarity between the two
    passages", not a direct measurement of "voice" itself.
  - text_similarity: SequenceMatcher ratio between the two outputs (or two
    originals) — "textual/edit similarity between the two passages".
  - convergence_delta: (paired output similarity) - (paired original
    similarity). A meaningfully positive delta is evidence of convergence;
    at/below zero means the transform did not measurably pull the two
    voices closer together than they already were.

Usage:
    cd backend && python3 tests/measure_voice_convergence.py --label after_v2
"""
import argparse
import asyncio
import json
import sys
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import settings  # noqa: E402
from services.ai_service import transform_tone, embed_text  # noqa: E402
from tests.fixtures.voice_convergence_fixture import VOICE_A, VOICE_B  # noqa: E402

N_TRIALS = 3
# "Suspenseful" was tried first and both voices were correctly judged
# already-suspenseful by the 5.5 no-change layer (a locked-door-in-rain scene
# reads that way inherently) — a genuine finding, but it makes this specific
# measurement a no-op. "Humorous" was verified to require a real rewrite for
# BOTH voices (see the session's own no-change-assessment check), so it's
# used here instead — the point of this measurement is convergence AFTER a
# real transform, not another no-change data point (that's already covered
# by task 5.5's own evidence).
TARGET_TONE = "humorous"


def text_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


async def content_similarity(a: str, b: str) -> float:
    import numpy as np
    ea = np.array(await embed_text(a))
    eb = np.array(await embed_text(b))
    return float(ea @ eb / (np.linalg.norm(ea) * np.linalg.norm(eb)))


async def run() -> dict:
    original_text_sim = text_similarity(VOICE_A["text"], VOICE_B["text"])
    original_content_sim = await content_similarity(VOICE_A["text"], VOICE_B["text"])

    trials = []
    for _ in range(N_TRIALS):
        result_a = await transform_tone(VOICE_A["text"], TARGET_TONE)
        result_b = await transform_tone(VOICE_B["text"], TARGET_TONE)
        out_a = result_a["transformed"] if isinstance(result_a, dict) else result_a
        out_b = result_b["transformed"] if isinstance(result_b, dict) else result_b
        trials.append({
            "output_a": out_a, "output_b": out_b,
            "text_similarity": text_similarity(out_a, out_b),
            "content_similarity": await content_similarity(out_a, out_b),
        })

    avg_text = sum(t["text_similarity"] for t in trials) / len(trials)
    avg_content = sum(t["content_similarity"] for t in trials) / len(trials)

    return {
        "prompt_version": settings.prompt_version,
        "target_tone": TARGET_TONE,
        "n_trials": N_TRIALS,
        "original_text_similarity": original_text_sim,
        "original_content_similarity": original_content_sim,
        "trials": trials,
        "avg_output_text_similarity": avg_text,
        "avg_output_content_similarity": avg_content,
        "text_similarity_convergence_delta": round(avg_text - original_text_sim, 4),
        "content_similarity_convergence_delta": round(avg_content - original_content_sim, 4),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    args = parser.parse_args()

    print(f"Voice-convergence measurement — prompt_version={settings.prompt_version}, label={args.label}")
    report = asyncio.run(run())

    out_path = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / f"voice_convergence_{args.label}.json"
    out_path.write_text(json.dumps(report, indent=2))
    print(f"\nWrote {out_path}")
    print(f"\noriginal: text_sim={report['original_text_similarity']:.3f} content_sim={report['original_content_similarity']:.3f}")
    print(f"outputs:  text_sim={report['avg_output_text_similarity']:.3f} content_sim={report['avg_output_content_similarity']:.3f}")
    print(f"convergence_delta: text={report['text_similarity_convergence_delta']:+.4f} content={report['content_similarity_convergence_delta']:+.4f}")
    print("(positive delta = outputs are MORE similar to each other than the originals were — evidence of convergence)")


if __name__ == "__main__":
    main()
