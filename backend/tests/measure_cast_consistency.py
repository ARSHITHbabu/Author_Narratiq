#!/usr/bin/env python3
"""
Stage 12 Tranche 2a — A11 measurement harness (CAST-H9 / CAST-H8), live model.

Measures cast extraction on the shared retrieval fixture (6 chapters) plus two
trap chapters with two DIFFERENT people called Tomas, one of whom is mostly
called just "Tomas". Two modes, N runs each:
  whole — the normal window budget (the fixture fits one window);
  split — the window budget forced down so the book is split into several
          windows and the cross-window merge (_merge_cast) actually runs.

Metrics (per run, then mean over runs):
  grounded       share of characters whose evidence_snippet is found in the
                 source text (>= 60% of its word 4-grams occur in the text)
  fact_recall    share of ground-truth facts present in the merged character
                 fields (description, backstory, arc_notes, goals, motivations)
  relationship   the "sister" relation sits with Hessa or the Cartographer and
                 nowhere else (1 = correct, 0 = missing or misattached)
  wrong_merges   the two Tomas characters collapsed into one record (count)
  cartographer   the dead, never-on-page Cartographer is present
  stability      mean pairwise similarity of each character's description
                 across runs (1 = identical every run)

  python3 tests/measure_cast_consistency.py --runs 5 --label before
Writes tests/fixtures/cast_consistency_<label>.json.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from difflib import SequenceMatcher
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

TRAP = [
    {"number": 7, "title": "The Customs House", "content": (
        "<p>At the customs house a young clerk named Tomas Reyne stamped the manifests without "
        "reading them. Tomas Reyne had forged the harbor records for the smugglers for years, and "
        "he kept a second ledger hidden in the hollow leg of his desk.</p>"
        "<p>When Mira asked about the old floodgate orders, the clerk went pale and said the pages "
        "had been torn out long before his time.</p>")},
    {"number": 8, "title": "The Lamp Room", "content": (
        "<p>Up in the lighthouse the keeper's son, Tomas Hale, trimmed the wick as he did every "
        "night. Tomas was nine years old and afraid of nothing except the sound of the sea at the "
        "bottom of the stairs.</p>"
        "<p>Tomas told Mira that he had seen lantern lights moving inside the sealed Cistern, and "
        "that his father had forbidden him to speak of it.</p>")},
]

# (character key, name tokens that identify it, facts as keyword alternatives)
TRUTH = {
    "mira":         ({"mira", "okoye"}, [["compass"], ["flood", "truth", "cartographer"]]),
    "hessa":        ({"hessa"}, [["map"], ["sister"]]),
    "corvin":       ({"corvin", "ashe"}, [["warden", "gate"], ["key"]]),
    "vell":         ({"vell", "ondrej"}, [["magistrate"], ["flood", "floodgate"], ["fak", "alive", "hiding"]]),
    "cartographer": ({"cartographer"}, [["sister", "hessa"], ["drown", "died", "dead", "flood"]]),
    "tomas_reyne":  ({"reyne"}, [["customs", "clerk"], ["forg", "ledger", "smuggl"]]),
    "tomas_hale":   ({"hale"}, [["lighthouse", "keeper"], ["son", "nine", "boy"]]),
}
TEXT_FIELDS = ("description", "backstory", "arc_notes", "goals", "motivations", "personality")


def _plain(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def _words(s: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", s.lower())


def grounded(snippet: str, source_words: list[str]) -> bool:
    w = _words(snippet)
    if len(w) < 4:
        return bool(w) and " ".join(w) in " ".join(source_words)
    grams = {tuple(w[i:i + 4]) for i in range(len(w) - 3)}
    src = {tuple(source_words[i:i + 4]) for i in range(len(source_words) - 3)}
    return len(grams & src) / len(grams) >= 0.6


def identify(ch: dict) -> list[str]:
    toks = set(_words(ch.get("name", ""))) | {t for a in ch.get("aliases") or [] for t in _words(a)}
    keys = [k for k, (ids, _f) in TRUTH.items() if toks & ids]
    if not keys and "tomas" in toks:
        keys = ["tomas_ambiguous"]
    return keys


def score_run(cast: list[dict], source_words: list[str]) -> dict:
    by_key: dict[str, list[dict]] = {}
    for ch in cast:
        for k in identify(ch):
            by_key.setdefault(k, []).append(ch)
    ground = [grounded(c.get("evidence_snippet", ""), source_words) for c in cast if c.get("evidence_snippet")]
    facts_hit = facts_total = 0
    for key, (_ids, facts) in TRUTH.items():
        blob = " ".join(" ".join(str(c.get(f, "")) for f in TEXT_FIELDS) for c in by_key.get(key, [])).lower()
        for alts in facts:
            facts_total += 1
            facts_hit += any(a in blob for a in alts)
    # relationship: "sister" must sit with hessa / cartographer only
    sister_ok_holders = {"hessa", "cartographer"}
    holders = {k for k, cs in by_key.items()
               for c in cs if "sister" in " ".join(str(c.get(f, "")) for f in TEXT_FIELDS).lower()}
    relationship = 1 if (holders & sister_ok_holders) and not (holders - sister_ok_holders) else 0
    # wrong merge: one record carries both Tomas identities, or only an ambiguous "Tomas"
    merged = 0
    for c in cast:
        k = identify(c)
        blob = " ".join(str(c.get(f, "")) for f in TEXT_FIELDS).lower()
        both = ("customs" in blob or "clerk" in blob) and ("lighthouse" in blob or "keeper" in blob)
        if ("tomas_reyne" in k and "tomas_hale" in k) or (k and k[0].startswith("tomas") and both):
            merged += 1
    if "tomas_reyne" not in by_key or "tomas_hale" not in by_key:
        merged = max(merged, 1 if "tomas_ambiguous" in by_key or len(by_key.get("tomas_reyne", []) + by_key.get("tomas_hale", [])) < 2 else merged)
    return {
        "characters": len(cast),
        "names": sorted(c.get("name", "") for c in cast),
        "grounded": round(sum(ground) / len(ground), 3) if ground else 0.0,
        "fact_recall": round(facts_hit / facts_total, 3),
        "relationship": relationship,
        "wrong_merges": merged,
        "cartographer": int("cartographer" in by_key),
        # A merge the MODEL made inside one window, flagged for the author
        # (Stage 12: possible_combined_with) rather than silently shown.
        "combined_flagged": sum(1 for c in cast if c.get("_possible_combined_with")),
        "descriptions": {k: (cs[0].get("description", "") if cs else "") for k, cs in by_key.items()},
        "presence": {c.get("name", ""): c.get("presence") for c in cast},
    }


def stability(runs: list[dict]) -> float:
    sims = []
    for key in TRUTH:
        ds = [r["descriptions"].get(key, "") for r in runs if r["descriptions"].get(key)]
        sims += [SequenceMatcher(None, a, b).ratio() for a, b in combinations(ds, 2)]
    return round(sum(sims) / len(sims), 3) if sims else 0.0


async def main(runs: int, label: str, split_budget: int):
    from services import ai_service
    from tests.fixtures.retrieval_fixture import CHAPTERS

    chapters = CHAPTERS + TRAP
    texts = [f"Chapter {c['number']}: {c['title']}\n{_plain(c['content'])}" for c in chapters]
    source_words = _words(" ".join(texts))
    report = {"label": label, "runs": runs, "split_budget_words": split_budget, "modes": {}}
    original_budget = ai_service._cast_window_word_budget
    for mode in ("whole", "split"):
        if mode == "split":
            ai_service._cast_window_word_budget = lambda: split_budget
        else:
            ai_service._cast_window_word_budget = original_budget
        windows = len(ai_service._build_cast_windows(texts, ai_service._cast_window_word_budget()))
        results = []
        failures = 0
        for i in range(runs):
            try:
                cast = await ai_service.extract_cast(texts)
            except ValueError as exc:            # unparseable / truncated model output
                failures += 1
                print(f"[{label}/{mode} run {i+1}] FAILED: {exc}", flush=True)
                continue
            results.append(score_run(cast, source_words))
            print(f"[{label}/{mode} run {i+1}] chars={results[-1]['characters']} grounded={results[-1]['grounded']} "
                  f"recall={results[-1]['fact_recall']} rel={results[-1]['relationship']} "
                  f"merges={results[-1]['wrong_merges']} carto={results[-1]['cartographer']}", flush=True)
        mean = lambda k: round(sum(r[k] for r in results) / len(results), 3) if results else None
        report["modes"][mode] = {
            "windows": windows,
            "failed_runs": failures,
            "mean": {k: mean(k) for k in ("grounded", "fact_recall", "relationship", "wrong_merges", "cartographer", "characters", "combined_flagged")},
            "stability": stability(results),
            "runs": results,
        }
    ai_service._cast_window_word_budget = original_budget
    out = Path(__file__).parent / "fixtures" / f"cast_consistency_{label}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps({m: {**v["mean"], "stability": v["stability"], "windows": v["windows"], "failed_runs": v["failed_runs"]}
                      for m, v in report["modes"].items()}, indent=2))
    print(f"wrote {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--label", default="before")
    ap.add_argument("--split-budget", type=int, default=300)
    a = ap.parse_args()
    asyncio.run(main(a.runs, a.label, a.split_budget))
