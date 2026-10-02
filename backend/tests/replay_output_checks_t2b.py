#!/usr/bin/env python3
"""
Stage 12 Tranche 2b — A18 offline replay (no model calls).

Applies prompt_safety.output_obeyed_material to stored REAL outputs before it
is switched on, exactly as each feature will apply it:

  clean-prose baseline (scripts/security/clean_prose_feature_probe.py, run
  before the change): Q&A answers, plot suggestions (text + rationale),
  writing suggestions (observation + recommendation, and recommendation
  only), continuation options — every flag here is a false alarm;
  Stage 11 legitimate rewrite outputs (84) — must stay 0 for both checks;
  Stage 11 injection probe, Plot Assistant before / after the fence — the
  before-fix samples are the obeyed signature (must be flagged), the after-fix
  ones must not be.

  cd backend && python3 tests/replay_output_checks_t2b.py --clean /path/clean_prose_before.json
Writes tests/fixtures/output_checks_replay_t2b.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
DOCS = Path(__file__).resolve().parents[2] / "docs" / "testing" / "stage-11"


def items(feature: str, body: dict) -> list[tuple[str, str]]:
    """(label, text) pairs the production check sees for one response."""
    if not isinstance(body, dict):
        return []
    if feature in ("qa", "creative", "mixed"):
        out = [("answer", body["answer"])] if body.get("answer") else []
        out += [("plot_suggestion", f"{s.get('text', '')} {s.get('rationale', '')}") for s in body.get("suggestions") or []]
        return out
    if feature == "writing":
        out = []
        for s in body.get("suggestions") or []:
            out.append(("writing_item", f"{s.get('observation', '')} {s.get('recommendation', '')}"))
            out.append(("writing_recommendation", s.get("recommendation", "")))
        return out
    if feature == "continue":
        return [("continuation", s.get("text", "")) for s in body.get("suggestions") or [] if s.get("text")]
    return []


def main(clean_path: str | None):
    from services.prompt_safety import output_obeyed_material, rewrite_lost_source
    report: dict = {}
    if clean_path:
        d = json.load(open(clean_path))
        per: dict[str, dict] = {}
        flagged = []
        for row in d["rows"]:
            if row["status"] != 200:
                continue
            for label, text in items(row["feature"], row["body"]):
                k = per.setdefault(label, {"checked": 0, "flagged": 0})
                k["checked"] += 1
                if output_obeyed_material(row["source"], text):
                    k["flagged"] += 1
                    flagged.append({"passage": row["passage"], "feature": row["feature"], "label": label,
                                    "text": text[:400]})
        report["clean_prose"] = {"calls": d["summary"]["calls"], "per_output_kind": per, "flagged": flagged}

    legit = json.load(open(DOCS / "legit-rewrite-probe-guard-on.json"))
    from scripts_passages import PASSAGES  # type: ignore  # noqa: E402  (set up below)
    rows = [r for r in legit["rows"] if r.get("status") == 200 and r.get("output")]
    report["stage11_rewrites"] = {
        "outputs": len(rows),
        "output_obeyed_material": sum(output_obeyed_material(PASSAGES[r["passage"]], r["output"]) for r in rows),
        "rewrite_lost_source": sum(rewrite_lost_source(PASSAGES[r["passage"]], r["output"],
                                                       same_language=r["tool"] != "translate") for r in rows),
    }

    from prompt_injection_probe import CHAPTERS  # noqa: E402
    source = " ".join(c.replace("<p>", " ").replace("</p>", " ") for c in CHAPTERS)
    for label, f in (("before_fix", "injection-probe-before-fix.json"), ("after_fix", "injection-probe-after-fix.json")):
        pa = json.load(open(DOCS / f))["features"]["plot-assistant"]["samples"]
        answers = []
        for s in pa:
            try:
                answers.append(json.loads(s["output"]).get("answer") or "")
            except json.JSONDecodeError:            # stored samples are cut at 1500 chars
                txt = s["output"]
                i = txt.find('"answer":"')
                answers.append(json.loads('"' + txt[i + 10:].split('","suggestions"')[0] + '"') if i >= 0 else "")
        report[f"injection_plot_assistant_{label}"] = {
            "samples": len(answers), "flagged": sum(output_obeyed_material(source, a) for a in answers)}
    out = Path(__file__).parent / "fixtures" / "output_checks_replay_t2b.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps({k: (v if k != "clean_prose" else {**v, "flagged": len(v["flagged"])}) for k, v in report.items()},
                     indent=2))
    for fl in report.get("clean_prose", {}).get("flagged", []):
        print("FLAG", fl["passage"], fl["feature"], fl["label"], "|", fl["text"][:200])


if __name__ == "__main__":
    BACKEND = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(BACKEND / "scripts" / "security"))
    sys.path.insert(0, str(BACKEND / "scripts" / "perf"))
    sys.path.insert(0, str(BACKEND / "tests"))
    import legit_rewrite_probe
    sys.modules["scripts_passages"] = legit_rewrite_probe
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", default=None)
    main(ap.parse_args().clean)
