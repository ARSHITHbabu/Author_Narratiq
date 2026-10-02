#!/usr/bin/env python3
"""
Stage 12 Tranche 2b — A14: children's adaptation "already suitable" decisions.

Passages:
  euphemism-*  a death or killing conveyed indirectly ("nobody survived") —
               a 7B suitability check tends to call these already suitable;
  grief-*      legitimate children's grief (a pet or a parent dies) — any
               rewrite must still contain the death (the story depends on it);
  adventure-3  the golden-set passage that motivated A14;
  suitable-*   the three golden-set passages that ARE already suitable for
               their target (adult / YA / adult) — must stay "no change".

Each runs N times through adapt_for_age (Light, the default) with the
CURRENTLY CONFIGURED prompt version and code. Records the no-change rate, the
output, and whether a death/loss term survives in a rewrite (automatic check;
outputs are also kept for a manual read).

  cd backend && python3 tests/measure_children_suitability_t2b.py --label before [--runs 10]
Writes tests/fixtures/children_suitability_t2b_<label>.json.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

CHILDREN = [
    ("euphemism-1", "Three boats went out before the storm and only two came back. The men on the "
                    "third boat didn't make it home, and Tavi's father had been one of them."),
    ("euphemism-2", "The old soldier never talked about the bridge. Of the forty men who crossed it "
                    "that night, nobody survived but him, and he still could not sleep in the dark."),
    ("euphemism-3", "The raiders came at dawn. By the time the bells stopped ringing, the whole "
                    "village had been put to the sword, and only the miller's girl was left hiding in the loft."),
    ("euphemism-4", "Her grandmother passed away the winter Nell turned eight. Nobody told her until "
                    "after the burial, and she never quite forgave them for that."),
    ("grief-1", "Biscuit the dog died on a Tuesday. Leo buried his red ball under the apple tree so "
                "Biscuit would have something to play with, and then he sat there until it got dark."),
    ("grief-2", "After Mum died, Dad stopped singing in the kitchen. Ellie missed the singing almost "
                "as much as she missed Mum, and some mornings she hummed the songs herself."),
    ("grief-3", "The baby bird was dead when they found it under the hedge. Priya cried, and her "
                "brother helped her make a small grave for it out of a shoebox and some moss."),
    ("grief-4", "Grandpa's funeral was on a grey morning in March. Sam held Grandma's hand the whole "
                "time, because she was shaking and he was not, and he wanted her to know he was there."),
]
DEATH_TERMS = re.compile(
    r"\b(die[ds]?|dying|dead|death|kill\w*|grave|funeral|buri(?:ed|al)|bury|passed away|survive[ds]?|"
    r"lost|gone|never came (?:back|home)|make it|made it|sword|missed|missing)\b", re.I)


async def main(label: str, runs: int):
    from config import settings
    from services import ai_service as ai
    from tests.fixtures.transform_golden_set import ALREADY_SUITABLE_FOR, PASSAGES
    by_id = {p["id"]: p["text"] for p in PASSAGES}
    cases = [(cid, text, "children") for cid, text in CHILDREN]
    cases.append(("adventure-3", by_id["adventure-3"], "children"))
    for pid, (_kind, target) in ALREADY_SUITABLE_FOR.items():
        cases.append((f"suitable-{pid}", by_id[pid], target))

    sem = asyncio.Semaphore(8)

    async def one(cid, text, target, i):
        async with sem:
            r = await ai.adapt_for_age(text, target)
        out = r["transformed"]
        return {"case": cid, "target": target, "run": i, "no_change": r["no_change"],
                "reason": r.get("reason", ""), "failed": r["failed"],
                "identical": out.strip() == text.strip(),
                "death_term_kept": bool(DEATH_TERMS.search(out)), "output": out}

    print(f"A14 — prompt_version={settings.prompt_version}, label={label}", flush=True)
    rows = await asyncio.gather(*[one(c, t, g, i) for c, t, g in cases for i in range(runs)])
    summary = {}
    for cid, _t, target in cases:
        rs = [r for r in rows if r["case"] == cid]
        changed = [r for r in rs if not r["identical"]]
        summary[cid] = {"target": target, "runs": len(rs),
                        "no_change": sum(r["no_change"] for r in rs),
                        "identical_to_original": sum(r["identical"] for r in rs),
                        "rewrites_keeping_a_death_term": f"{sum(r['death_term_kept'] for r in changed)}/{len(changed)}"}
    out = Path(__file__).parent / "fixtures" / f"children_suitability_t2b_{label}.json"
    out.write_text(json.dumps({"label": label, "prompt_version": settings.prompt_version, "runs": runs,
                               "summary": summary, "rows": rows}, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--runs", type=int, default=10)
    a = ap.parse_args()
    asyncio.run(main(a.label, a.runs))
