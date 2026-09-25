"""
Relationship arcs across the manuscript (Stage 5, task 5.14 — Medium 11).

Deterministic, no LLM call. Aggregates the per-chapter
``ChapterSummary.relationship_changes`` (``[{"characters": [a, b], "change": str}]``,
written at indexing time) into one longitudinal entry per character pair, in
chapter order. Every change keeps the chapter it came from, so each entry is
cited by construction and cannot drift from the indexed summaries.

This is the only author-facing "relationships" view in the product.
RelationshipIntelligence (Story Intelligence pass P24) holds LLM-derived
relationship data but is not shown to authors; it is deliberately NOT mixed in
here, so the author never sees two answers to "how did A and B change?".
"""
import re
from typing import Iterable, Optional

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def _resolve(ref, names_by_id: dict[str, str]) -> Optional[str]:
    """Character reference → display name. Known id → current name. An
    id-shaped value that is not a current character (deleted/merged away) →
    None. Any other non-empty string is the name the summary itself used."""
    if not isinstance(ref, str):
        return None
    ref = ref.strip()
    if not ref:
        return None
    if ref in names_by_id:
        return names_by_id[ref]
    if _UUID_RE.match(ref):
        return None
    return ref


def build_relationship_arcs(
    summaries: Iterable[dict],
    names_by_id: dict[str, str],
) -> tuple[list[dict], int]:
    """
    summaries   — [{"chapter": int, "relationship_changes": list | None}]
    names_by_id — {character_id: current name}

    Returns (arcs, dropped). arcs = [{characters: [a, b] (sorted),
    changes: [{chapter, change}] (chapter order), first_chapter, last_chapter,
    chapter_count}], most-changed pairs first. dropped counts changes that
    could not be attributed to two distinct known characters.
    """
    pairs: dict[tuple[str, str], list[dict]] = {}
    dropped = 0
    for s in sorted(summaries, key=lambda x: x["chapter"]):
        for entry in s.get("relationship_changes") or []:
            if not isinstance(entry, dict):
                dropped += 1
                continue
            refs = entry.get("characters")
            change = str(entry.get("change") or "").strip()
            if not isinstance(refs, list) or len(refs) != 2 or not change:
                dropped += 1
                continue
            a, b = (_resolve(r, names_by_id) for r in refs)
            if not a or not b or a.lower() == b.lower():
                dropped += 1
                continue
            key = tuple(sorted((a, b), key=str.lower))
            pairs.setdefault(key, []).append({"chapter": int(s["chapter"]), "change": change})

    arcs = []
    for (a, b), changes in pairs.items():
        chapters = sorted({c["chapter"] for c in changes})
        arcs.append({
            "characters":    [a, b],
            "changes":       changes,
            "first_chapter": chapters[0],
            "last_chapter":  chapters[-1],
            "chapter_count": len(chapters),
        })
    arcs.sort(key=lambda x: (-len(x["changes"]), x["first_chapter"], x["characters"][0].lower()))
    return arcs, dropped
