#!/usr/bin/env python3
"""
Stage 12.1 (Gate 3b) — build the human review package from SAVED model outputs.

No model calls and no judgement: it lays out evidence the author must judge, so
the Gate 3b reviews can start without more engineering work.

  blind-review.md          MV-5.BR: each golden-set passage with two rewrites in
                           random order (A/B). One comes from the pre-Stage-12 v2
                           prompts, one from the current v4 prompts. The answer key
                           is in blind-review-KEY.json; do not open it until the
                           tally is done.
  a15-light-labelling.md   A15: 90 Light-strength outputs (30 each for tone, age
                           adaptation and style), each to be labelled acceptable /
                           not acceptable for "Light". That gives the human
                           thresholds A15 needs.
  children-meaning-review.md  Every children's rewrite of the grief and euphemism
                           fixtures, checked for: is every difficult event kept and
                           unchanged in meaning?

The seed is fixed, so rebuilding gives the same package.

  cd backend && python3 scripts/quality/build_gate3b_review_package.py \\
      ../docs/testing/stage-12/stage-12.1/gate3b-review
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))
FIX = BACKEND / "tests" / "fixtures"
SEED = 20261003


def _passages() -> dict[str, str]:
    from tests.fixtures.transform_golden_set import PASSAGES
    return {p["id"]: p["text"] for p in PASSAGES}


def _children_sources() -> dict[str, str]:
    sys.path.insert(0, str(BACKEND / "tests"))
    from measure_children_suitability_t2b import CHILDREN
    return dict(CHILDREN)


def _block(text: str) -> str:
    return "\n".join("> " + line if line else ">" for line in (text or "").strip().split("\n"))


def blind_review(out: Path, rng: random.Random) -> None:
    src = _passages()
    old = {s["passage_id"] + "|" + s["transform_type"]: s for s in json.loads((FIX / "transform_golden_after_v2.json").read_text())["scenarios"]}
    new = {s["passage_id"] + "|" + s["transform_type"]: s for s in json.loads((FIX / "transform_golden_tranche2b_v4.json").read_text())["scenarios"]}
    key, lines = {}, [
        "# Blind author review (MV-5.BR) — for the author only",
        "",
        "For each item, read the original, then versions A and B, and record **A**, **B** or **no difference** for "
        "\"which is the better rewrite for this request, in my voice?\". Do not open `blind-review-KEY.json` "
        "until every item is answered. Then reveal the labels and tally (MV-5.BR expected result: the current "
        "version preferred or equal on style; no transform clearly worse).",
        "",
        "Source: saved golden-set outputs (`transform_golden_after_v2.json` = pre-Stage-12 prompts, "
        "`transform_golden_tranche2b_v4.json` = current v4 prompts), one trial each, chosen with a fixed seed. "
        "An item where a version returned the passage unchanged shows that text as is.",
        "",
    ]
    for n, k in enumerate(sorted(set(old) & set(new)), start=1):
        pid, transform = k.split("|")
        o_trial = rng.choice(old[k]["trials"])["output"]
        n_trial = rng.choice(new[k]["trials"])["output"]
        pair = [("v2", o_trial), ("v4", n_trial)]
        rng.shuffle(pair)
        key[f"item-{n}"] = {"A": pair[0][0], "B": pair[1][0], "scenario": k}
        target = new[k].get("target") or ""
        lines += [f"## Item {n} — {transform} → {target}", "", "**Original**", "", _block(src.get(pid, "")), "",
                  "**Version A**", "", _block(pair[0][1]), "", "**Version B**", "", _block(pair[1][1]), "",
                  "**Your choice:** A / B / no difference — **Note:** ", "", "---", ""]
    (out / "blind-review.md").write_text("\n".join(lines))
    (out / "blind-review-KEY.json").write_text(json.dumps(key, indent=2))


def light_labelling(out: Path, rng: random.Random) -> None:
    src = _passages()
    rows = [r for r in json.loads((FIX / "strength_t2b_after_v4.json").read_text())["rows"]
            if r["strength"] == "light" and not r.get("failed") and not r.get("no_change")]
    lines = [
        "# A15 — label Light-strength outputs (for the author)",
        "",
        "For each rewrite requested at **Light** strength, mark **acceptable** if it is the small, careful edit "
        "you expect from Light, or **too much** if it changed more than Light should. Your labels set the "
        "warning/retry thresholds A15 is waiting for. The measured share of your words kept is shown under each item "
        "for reference only — label by reading, not by the number.",
        "",
        "Source: `backend/tests/fixtures/strength_t2b_after_v4.json` (prompt v4), sampled with a fixed seed.",
        "",
    ]
    n = 0
    for transform in ("tone", "age_adapt", "style"):
        pool = [r for r in rows if r["transform"] == transform]
        for r in rng.sample(pool, min(30, len(pool))):
            n += 1
            prof = r.get("profile") or {}
            lines += [f"## {n}. {transform} → {r['target']} (Light) — passage `{r['passage']}`", "",
                      "**Original**", "", _block(src.get(r["passage"], "")), "", "**Light rewrite**", "",
                      _block(r["output"]), "",
                      f"*Words kept: {prof.get('kept_share')} · new words: {prof.get('new_share')} · "
                      f"word order kept: {prof.get('word_order')}*", "",
                      "**Label:** acceptable / too much — **Note:** ", "", "---", ""]
    (out / "a15-light-labelling.md").write_text("\n".join(lines))


def children_review(out: Path) -> None:
    src = _children_sources()
    rows = json.loads((FIX / "children_suitability_t2b_after_v4.json").read_text())["rows"]
    lines = [
        "# Children's adaptation — meaning review (for the author or a reviewer)",
        "",
        "For each children's rewrite of a grief or euphemism passage, check: **is every difficult event still "
        "there, and does it still mean the same thing?** (A softer word is fine; an event that disappears, or a "
        "death that becomes \"went away\", is not.) Record **kept** or **changed**, with a note.",
        "",
        "Source: `backend/tests/fixtures/children_suitability_t2b_after_v4.json` (prompt v4, "
        "`CHILDREN_SUITABILITY_OVERRIDE` on). Every run is shown.",
        "",
    ]
    for case in sorted(src):
        lines += [f"## {case}", "", "**Original**", "", _block(src[case]), ""]
        for r in sorted((r for r in rows if r["case"] == case), key=lambda r: r["run"]):
            if r.get("failed"):
                lines += [f"*Run {r['run']}: the rewrite failed (nothing to review).*", ""]
                continue
            label = "returned unchanged (judged already suitable)" if r.get("no_change") else "rewrite"
            lines += [f"**Run {r['run']} — {label}**", "", _block(r["output"]), "",
                      "**Every difficult event kept, same meaning?** kept / changed — **Note:** ", ""]
        lines += ["---", ""]
    (out / "children-meaning-review.md").write_text("\n".join(lines))


def light_vs_strong_sample(out: Path) -> None:
    """Stage 12.1 owner guide: Light and Strong side by side (same passage, same
    run index) — 6 tone, 6 age adaptation, 3 style (the control, measured as
    working). Judges both "acceptable as Light?" and "clearly lighter than Strong?",
    which is what AWT-D/I, 1.2, 1.6 and 3.7 allege."""
    src = _passages()
    rows = json.loads((FIX / "strength_t2b_after_v4.json").read_text())["rows"]
    idx = {(r["transform"], r["passage"], r["run"], r["strength"]): r for r in rows}
    lines = [
        "# A15 sample — Light next to Strong (15 pairs)",
        "",
        "For each pair: (1) is the **Light** rewrite an acceptable *light* edit? (2) Is Light **clearly lighter** "
        "than Strong? Answer each: yes / no. Tone and age adaptation are the transforms under question; style "
        "is included as a control (measured as working). Source: `strength_t2b_after_v4.json` (prompt v4).",
        "",
    ]
    n = 0
    for transform, k in (("tone", 6), ("age_adapt", 6), ("style", 3)):
        keys = sorted({(t, pid, run) for (t, pid, run, st) in idx if t == transform and st == "light"
                       and (t, pid, run, "strong") in idx
                       and not idx[(t, pid, run, "light")].get("no_change")
                       and not idx[(t, pid, run, "light")].get("failed")
                       and not idx[(t, pid, run, "strong")].get("failed")})
        seen, chosen = set(), []
        for key in keys:                       # one run per passage, passages in a fixed order
            if key[1] not in seen:
                seen.add(key[1]); chosen.append(key)
        for t, pid, run in chosen[:k]:
            n += 1
            light, strong = idx[(t, pid, run, "light")], idx[(t, pid, run, "strong")]
            lp, sp = light.get("profile") or {}, strong.get("profile") or {}
            lines += [f"## S{n}. {t} → {light['target']} — passage `{pid}`", "", "**Original**", "", _block(src.get(pid, "")),
                      "", "**Light**", "", _block(light["output"]), "", "**Strong**", "", _block(strong["output"]), "",
                      f"*Words kept — Light {lp.get('kept_share')} · Strong {sp.get('kept_share')}*", "",
                      "**(1) Light acceptable?** yes / no — **(2) clearly lighter than Strong?** yes / no", "", "---", ""]
    (out / "a15-sample-light-vs-strong.md").write_text("\n".join(lines))


def children_sample(out: Path) -> None:
    """Stage 12.1 owner guide: 2 runs per children's case (16 of the 80)."""
    src = _children_sources()
    rows = json.loads((FIX / "children_suitability_t2b_after_v4.json").read_text())["rows"]
    lines = [
        "# Children's adaptation — review sample (16 of 80)",
        "",
        "For each rewrite: (1) **meaning kept** — every difficult event still there, same meaning? (2) **appropriate** "
        "for children? Answer each: yes / no, with a note if no. The full set of 80 is in `children-meaning-review.md`.",
        "",
    ]
    for case in sorted(src):
        runs = sorted((r for r in rows if r["case"] == case and not r.get("failed")), key=lambda r: r["run"])[:2]
        lines += [f"## {case}", "", "**Original**", "", _block(src[case]), ""]
        for r in runs:
            label = "returned unchanged (judged already suitable)" if r.get("no_change") else "children's rewrite"
            lines += [f"**Run {r['run']} — {label}**", "", _block(r["output"]), "",
                      "**(1) meaning kept?** yes / no — **(2) appropriate for children?** yes / no — **Note:** ", ""]
        lines += ["---", ""]
    (out / "children-sample.md").write_text("\n".join(lines))


def main(out_dir: str) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    blind_review(out, rng)
    light_labelling(out, rng)
    children_review(out)
    light_vs_strong_sample(out)
    children_sample(out)
    print("wrote", sorted(p.name for p in out.iterdir()))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/gate3b-review")
