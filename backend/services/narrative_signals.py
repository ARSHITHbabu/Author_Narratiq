"""
Narrative-structure signals (Stage 5, task 5.14 — Critical 5).

Deterministic, no LLM call. Flags three structural patterns from data NarratIQ
already holds, each citing the chapters it is based on:

  setup_without_payoff     a narrative thread the deterministic lifecycle
                           tracker (routers/narrative_threads.py) marks
                           dead_end; plus, when the Story Intelligence
                           foreshadowing registry is present and NOT stale,
                           its orphaned hints that carry a chapter number
  character_disappearance  a named character present in >= 2 chapters who then
                           does not appear for the rest of the manuscript
                           (same threshold as the thread scanner's dead-end
                           rule: max(3, 15% of chapters))
  purpose_gap              a run of >= 2 consecutive chapters whose indexed
                           summary records no chapter purpose

These are prompt INPUTS for check_continuity (the model must confirm each one,
and its findings still pass validate_continuity_citations) and a clearly
labelled "machine-detected" section of /manuscript-report. They are never
reported as continuity findings on their own.
"""
from typing import Iterable, Optional

MAX_SIGNALS = 12
_EMPTY_PURPOSES = {"", "-", "—", "none", "n/a", "na", "unknown", "unclear"}


def dead_end_threshold(total_chapters: int) -> int:
    return max(3, int(total_chapters * 0.15))


def _setup_signals(threads: Iterable[dict]) -> list[dict]:
    out = []
    for t in threads:
        if t.get("status") != "dead_end":
            continue
        intro, last = t.get("introduced_chapter"), t.get("last_seen_chapter")
        chapters = sorted({c for c in (intro, last) if isinstance(c, int) and c > 0})
        if not chapters:
            continue
        out.append({
            "kind": "setup_without_payoff",
            "subject": str(t.get("name") or "").strip(),
            "chapters": chapters,
            "detail": (f"Introduced in chapter {chapters[0]} and last seen in chapter {chapters[-1]}, "
                       "with no resolution after that."),
            "source": "narrative_threads",
        })
    return [s for s in out if s["subject"]]


def _hint_chapters(item: dict) -> list[int]:
    for key in ("chapter", "chapter_number", "introduced_chapter", "setup_chapter"):
        v = item.get(key)
        if isinstance(v, int) and v > 0:
            return [v]
    v = item.get("chapters")
    if isinstance(v, list):
        return sorted({c for c in v if isinstance(c, int) and c > 0})
    return []


def _foreshadowing_signals(orphaned_hints: Optional[list], valid_chapters: set[int]) -> list[dict]:
    out = []
    for item in orphaned_hints or []:
        if not isinstance(item, dict):
            continue          # no chapter to cite → not usable
        chapters = [c for c in _hint_chapters(item) if c in valid_chapters]
        subject = next((str(item[k]).strip() for k in ("hint", "description", "text", "name")
                        if isinstance(item.get(k), str) and item[k].strip()), "")
        if not chapters or not subject:
            continue
        out.append({
            "kind": "setup_without_payoff",
            "subject": subject[:200],
            "chapters": chapters,
            "detail": f"Foreshadowed in chapter {chapters[0]} with no payoff recorded later.",
            "source": "foreshadowing_registry",
        })
    return out


def _disappearance_signals(summaries: list[dict], total: int) -> list[dict]:
    seen: dict[str, dict] = {}
    for s in summaries:
        for name in s.get("characters_present") or []:
            if not isinstance(name, str) or not name.strip():
                continue
            key = name.strip().lower()
            rec = seen.setdefault(key, {"name": name.strip(), "chapters": set()})
            rec["chapters"].add(int(s["chapter"]))
    threshold = dead_end_threshold(total)
    out = []
    for rec in seen.values():
        chapters = sorted(rec["chapters"])
        if len(chapters) >= 2 and total - chapters[-1] >= threshold:
            out.append({
                "kind": "character_disappearance",
                "subject": rec["name"],
                "chapters": chapters,
                "detail": (f"Appears in {len(chapters)} chapters up to chapter {chapters[-1]}, "
                           f"then not in the remaining {total - chapters[-1]} chapters."),
                "source": "chapter_summaries",
            })
    return out


def _purpose_gap_signals(summaries: list[dict]) -> list[dict]:
    out, run = [], []
    for s in summaries + [None]:
        empty = s is not None and str(s.get("chapter_purpose") or "").strip().lower() in _EMPTY_PURPOSES
        if empty:
            run.append(int(s["chapter"]))
            continue
        if len(run) >= 2:
            out.append({
                "kind": "purpose_gap",
                "subject": f"Chapters {run[0]}–{run[-1]}",
                "chapters": list(run),
                "detail": "No clear chapter purpose was recorded for these consecutive chapters when they were indexed.",
                "source": "chapter_summaries",
            })
        run = []
    return out


def build_narrative_signals(
    summaries: Iterable[dict],
    threads: Iterable[dict] = (),
    orphaned_hints: Optional[list] = None,
) -> list[dict]:
    """
    summaries      — [{"chapter": int, "characters_present": [str], "chapter_purpose": str}]
    threads        — [{"name", "status", "introduced_chapter", "last_seen_chapter"}]
    orphaned_hints — foreshadowing-registry orphaned_hints; pass None when the
                     registry is absent or stale (stale rows are not trusted)

    Returns at most MAX_SIGNALS entries {kind, subject, chapters, detail, source},
    every one citing at least one real chapter.
    """
    summaries = sorted(summaries, key=lambda s: s["chapter"])
    if not summaries:
        return []
    total = max(int(s["chapter"]) for s in summaries)
    valid = {int(s["chapter"]) for s in summaries}
    signals = (_setup_signals(threads)
               + _foreshadowing_signals(orphaned_hints, valid)
               + _disappearance_signals(summaries, total)
               + _purpose_gap_signals(summaries))
    seen, unique = set(), []
    for sig in signals:
        key = (sig["kind"], sig["subject"].lower())
        if key not in seen:
            seen.add(key)
            unique.append(sig)
    return unique[:MAX_SIGNALS]


def format_signals_for_prompt(signals: list[dict]) -> str:
    if not signals:
        return ""
    lines = [f"- [{s['kind']}] {s['subject']} (chapters {', '.join(map(str, s['chapters']))}): {s['detail']}"
             for s in signals]
    return ("Narrative-structure signals (machine-detected — VERIFY each against the chapter data "
            "before reporting it; report only those you can confirm, citing chapters):\n" + "\n".join(lines))
