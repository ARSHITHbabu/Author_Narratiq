#!/usr/bin/env python3
"""
Stage 12 Tranche 2b — A16 offline replay (no model calls).

False positives: every stored real rewrite output whose source passage is
known (golden-set reports, emotion set, the Tranche 2b strength and children
measurements) goes through check_new_entities. None of these outputs was
asked to add a person or place, so every flag is a false alarm until a manual
read shows otherwise; flagged items are listed for that read.

Detection: invented names (people and places, one and two words) are inserted
mid-sentence into the same outputs; the share found is the detection rate.
Sentence-initial insertions are measured separately — they are the
documented blind spot.

  cd backend && python3 tests/measure_new_entities_t2b.py
Writes tests/fixtures/new_entities_t2b.json.
"""
from __future__ import annotations

import glob
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

INVENTED = ["Bartholomew", "Quince", "Halvard", "Port Ennick", "Seraphine Vole", "Marrowgate",
            "Tobias Wren", "Ostrava Keep", "Ilse", "Dunmore", "Captain Fenwick", "Lady Arrow",
            "Kestrel Bay", "Odalys", "Brannigan", "Thessaly Marsh", "Corwen", "Nyx Halloway",
            "Saint Albric", "Greywater"]


def pairs():
    from tests.fixtures.transform_golden_set import PASSAGES
    from tests.measure_children_suitability_t2b import CHILDREN
    src = {p["id"]: p["text"] for p in PASSAGES}
    src.update(dict(CHILDREN))
    fx = Path(__file__).parent / "fixtures"
    out = []
    for f in sorted(glob.glob(str(fx / "transform_golden_*.json"))):
        for sc in json.load(open(f)).get("scenarios", []):
            for t in sc.get("trials", []):
                if sc["passage_id"] in src and isinstance(t, dict) and t.get("output"):
                    out.append((Path(f).name, src[sc["passage_id"]], t["output"]))
    for f in sorted(glob.glob(str(fx / "emotion_measurement_*.json"))):
        for sc in json.load(open(f)).get("scenarios", []):
            if sc["passage_id"] in src and sc.get("output"):
                out.append((Path(f).name, src[sc["passage_id"]], sc["output"]))
    for f in sorted(glob.glob(str(fx / "strength_t2b_*.json"))):
        for r in json.load(open(f)).get("rows", []):
            if r.get("output") and r["passage"] in src:
                out.append((Path(f).name, src[r["passage"]], r["output"]))
    for f in sorted(glob.glob(str(fx / "children_suitability_t2b_*.json"))):
        for r in json.load(open(f)).get("rows", []):
            key = r["case"].removeprefix("suitable-")
            if r.get("output") and key in src:
                out.append((Path(f).name, src[key], r["output"]))
    # identical outputs (no-change results) say nothing about the check
    return [(f, s, o) for f, s, o in out if o.strip() != s.strip()]


def _insert_mid(output: str, name: str, i: int) -> str | None:
    """Insert `with <name>` after a lowercase word in the middle of a sentence."""
    spots = [m.end() for m in re.finditer(r"(?<=[a-z]) (?=[a-z])", output)]
    if not spots:
        return None
    k = spots[(i * 7) % len(spots)]
    return output[:k] + f"with {name} " + output[k:]


def main():
    from services.transform_preservation import check_new_entities
    ps = pairs()
    flagged = []
    for f, s, o in ps:
        hits = check_new_entities(s, o)
        if hits:
            flagged.append({"file": f, "names": [h["name"] for h in hits], "source": s, "output": o})
    det_mid = det_start = n_mid = n_start = 0
    misses = []
    for i, (f, s, o) in enumerate(ps):
        name = INVENTED[i % len(INVENTED)]
        if name.split()[-1].lower() in s.lower() or name.split()[-1].lower() in o.lower():
            continue
        mid = _insert_mid(o, name, i)
        if mid:
            n_mid += 1
            got = [h["name"] for h in check_new_entities(s, mid)]
            if any(name.split()[-1] in g for g in got):
                det_mid += 1
            elif len(misses) < 10:
                misses.append({"name": name, "output": mid})
        n_start += 1
        start = f"{name} watched. " + o
        if any(name.split()[-1] in h["name"] for h in check_new_entities(s, start)):
            det_start += 1
    report = {
        "outputs_replayed": len(ps),
        "false_positive_outputs": len(flagged),
        "false_positive_rate": round(len(flagged) / len(ps), 4) if ps else None,
        "detection_mid_sentence": {"inserted": n_mid, "found": det_mid,
                                   "rate": round(det_mid / n_mid, 3) if n_mid else None},
        "detection_sentence_start (known blind spot)": {"inserted": n_start, "found": det_start,
                                                        "rate": round(det_start / n_start, 3) if n_start else None},
        "flagged": flagged, "missed_examples": misses,
    }
    (Path(__file__).parent / "fixtures" / "new_entities_t2b.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps({k: v for k, v in report.items() if k not in ("flagged", "missed_examples")}, indent=2))
    for fl in flagged[:40]:
        print("FLAG", fl["names"], "|", fl["output"][:200].replace("\n", " "))


if __name__ == "__main__":
    main()
