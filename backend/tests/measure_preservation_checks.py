"""
Stage 7 task 7.3 — measure the conservative Phase 3 preservation checks
(tense, POV, dialogue meaning, timeline) against the golden set BEFORE relying
on their defaults (author's Stage 7 approval, item 4).

Three measurements:
  1. FALSE POSITIVES on the 72 stored real Qwen outputs from Stage 5
     (transform_golden_baseline_v1.json + transform_golden_after_v2.json) —
     legitimate tone/style/audience rewrites that should NOT trip tense/POV
     flags.
  2. FALSE POSITIVES on fresh live outputs (optional, --live): every golden
     passage × {tone, emotion, style, age_adapt}, generated now through the
     real vLLM via the Phase 3 path.
  3. RECALL on deliberately broken rewrites: each passage mechanically
     converted to present tense / first person / with an added time marker.

Writes tests/fixtures/preservation_checks_measurement.json. Pure measurement:
changes no code, no data.

    cd backend && python3 tests/measure_preservation_checks.py            # offline
    cd backend && python3 tests/measure_preservation_checks.py --live     # + real vLLM
"""
import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures.transform_golden_set import PASSAGES  # noqa: E402
from services.transform_preservation import DEFAULT_PRESERVE_RULES, verify_preservation  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"
KINDS = ("tense_shift", "pov_shift", "dialogue_changed", "timeline_added")
TEXT = {p["id"]: p["text"] for p in PASSAGES}


def _count(pairs):
    per_kind = {k: 0 for k in KINDS}
    flagged = []
    for pid, tool, src, out in pairs:
        ws = verify_preservation(src, out, dict(DEFAULT_PRESERVE_RULES), tool=tool)
        kinds = sorted({w["kind"] for w in ws})
        for k in kinds:
            per_kind[k] += 1
        if kinds:
            flagged.append({"passage": pid, "tool": tool, "kinds": kinds})
    n = len(pairs)
    return {"samples": n, "flagged_samples": len(flagged),
            "per_kind": per_kind, "per_kind_rate": {k: round(v / n, 4) if n else 0.0 for k, v in per_kind.items()},
            "flagged": flagged}


def stored_pairs():
    pairs = []
    for fname in ("transform_golden_baseline_v1.json", "transform_golden_after_v2.json"):
        for sc in json.loads((FIX / fname).read_text())["scenarios"]:
            for t in sc["trials"]:
                if t["output"] and not t.get("byte_identical"):
                    pairs.append((sc["passage_id"], sc["transform_type"], TEXT[sc["passage_id"]], t["output"]))
    return pairs


_PRESENT = {"was": "is", "were": "are", "had": "has", "did": "does", "said": "says", "went": "goes",
            "looked": "looks", "turned": "turns", "walked": "walks", "stood": "stands", "felt": "feels",
            "knew": "knows", "thought": "thinks", "came": "comes", "saw": "sees", "took": "takes"}


def to_present(text: str) -> str:
    return re.sub(r"\b(\w+)\b", lambda m: _PRESENT.get(m.group(1), _PRESENT.get(m.group(1).lower(), m.group(1))), text)


def to_first_person(text: str) -> str:
    rep = {"she": "I", "he": "I", "her": "my", "his": "my", "him": "me", "herself": "myself", "himself": "myself",
           "they": "we", "their": "our", "them": "us", "She": "I", "He": "I", "Her": "My", "His": "My", "They": "We"}
    return re.sub(r"\b(\w+)\b", lambda m: rep.get(m.group(1), m.group(1)), text)


# Longer passages that actually carry narration tense/pronoun signal — most
# golden passages name their characters instead of using pronouns, so the POV
# check (which needs >= 5 narration pronouns) correctly abstains on them.
SIGNAL_PASSAGES = [
    ("sig-1", "She walked to the gate and waited. Her breath clouded in the cold. She thought of him, of what he had said, "
              "and she turned the key over in her hand. They had promised to meet here. She looked down the road."),
    ("sig-2", "He was late again. He had told them he would come, and they had believed him. His coat was soaked through "
              "and his hands shook as he pushed the door. Nobody looked up when he came in."),
    ("sig-3", "They crossed the river at night. Their boots were heavy and their packs were heavier. She led them along "
              "the bank while he watched the far shore. They did not speak until the trees closed around them."),
    ("sig-4", "She opened the letter slowly. Her mother had written it years ago, and she had never read it. She sat by the "
              "window and held it to the light. The words were small and careful. She read them twice."),
    ("sig-5", "He climbed the tower stairs alone. His lantern threw long shadows on the stone. He counted each step as he "
              "went, and he stopped when he heard the bell. His heart was loud in his ears."),
    ("sig-6", "They waited in the kitchen for news. Her father paced while her brother stared at the clock. She made tea "
              "that nobody drank. When the phone rang they all stood up at once."),
]


def broken_pairs():
    out = {"tense": [], "pov": [], "timeline": []}
    for pid, src in SIGNAL_PASSAGES:
        out["tense"].append((pid, "tone", src, to_present(src)))
        out["pov"].append((pid, "tone", src, to_first_person(src)))
    for p in PASSAGES:
        src = p["text"]
        out["timeline"].append((p["id"], "tone", src, src + " Three days later, at dawn, it began again."))
    return out


async def live_pairs():
    from services.ai_service import adapt_for_age, rewrite_emotion, transform_style, transform_tone
    pairs = []
    for p in PASSAGES:
        src = p["text"]
        jobs = [
            ("tone", transform_tone(src, "dark")), ("emotion", rewrite_emotion(src, "fear", "medium")),
            ("style", transform_style(src, "noir")), ("age_adapt", adapt_for_age(src, "ya")),
        ]
        for tool, job in jobs:
            r = await job
            if not r["no_change"] and not r["failed"] and r["transformed"].strip() != src.strip():
                pairs.append((p["id"], tool, src, r["transformed"]))
    return pairs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="also generate fresh outputs with the real vLLM")
    args = ap.parse_args()
    report = {"rules": DEFAULT_PRESERVE_RULES, "stored_real_outputs": _count(stored_pairs()),
              "unchanged_signal_passages": _count([(pid, "tone", t, t) for pid, t in SIGNAL_PASSAGES])}
    if args.live:
        report["fresh_live_outputs"] = _count(asyncio.run(live_pairs()))
    recall = {}
    for kind, pairs in broken_pairs().items():
        r = _count(pairs)
        key = {"tense": "tense_shift", "pov": "pov_shift", "timeline": "timeline_added"}[kind]
        recall[kind] = {"samples": r["samples"], "detected": r["per_kind"][key],
                        "recall": round(r["per_kind"][key] / r["samples"], 4)}
    report["recall_on_broken_rewrites"] = recall
    out = FIX / "preservation_checks_measurement.json"
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "rules"}, indent=2)[:4000])
    print(f"\nwritten: {out}")


if __name__ == "__main__":
    main()
