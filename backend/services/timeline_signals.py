"""
Timeline signals (Stage 5, task 5.14 — Critical 4).

Deterministic, no LLM call. Parses the time anchors NarratIQ already holds per
chapter — ``ChapterSummary.timeline_markers`` plus explicit anchors inside
``key_events`` — and emits CANDIDATE timeline conflicts, each citing the
chapters it is based on:

  date_reversal     the latest date anchored in a chapter is earlier than the
                    latest date anchored in an earlier chapter (story order)
  age_decrease      a character's stated age goes down between chapters
  weekday_mismatch  a weekday stated next to a full date that falls on a
                    different weekday
  season_reversal   within one stated year, a later chapter's season comes
                    before an earlier chapter's (spring < summer < autumn;
                    winter spans the year boundary and is never compared)

A chapter that carries a flashback / flash-forward cue ("years earlier",
"remembered", ...) — or that the Story Intelligence timeline (P26) marks as a
flashback or flash-forward in a NON-stale row — is never the later side of a
conflict. Flashbacks are legitimate storytelling, not errors.

Candidates are prompt INPUTS for check_continuity only: the model must confirm
or dismiss each one, and every finding it reports still passes
validate_continuity_citations. They are never shown to the author directly.
Nothing here logs manuscript text.
"""
import re
from datetime import date
from typing import Iterable, Optional

MAX_TIMELINE_SIGNALS = 8

_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}
_MONTHS.update({k[:3]: v for k, v in list(_MONTHS.items())})
_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_SEASON_ORDER = {"spring": 1, "summer": 2, "autumn": 3, "fall": 3}

_MONTH_RE = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_YEAR_RE = r"(1[5-9]\d\d|20\d\d|21\d\d)"
_ISO = re.compile(r"\b" + _YEAR_RE + r"-(\d{1,2})-(\d{1,2})\b")
_MDY = re.compile(r"\b" + _MONTH_RE + r"\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+" + _YEAR_RE + r"\b", re.I)
_DMY = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?" + _MONTH_RE + r"\.?,?\s+" + _YEAR_RE + r"\b", re.I)
_YEAR = re.compile(r"\b" + _YEAR_RE + r"\b")
_WEEKDAY = re.compile(r"\b(" + "|".join(_WEEKDAYS) + r")\b", re.I)
_SEASON = re.compile(r"\b(spring|summer|autumn|fall|winter)\b", re.I)
_AGE_A = re.compile(r"\b([A-Z][a-z]+)(?:,)?\s+(?:is|was|turns|turned|now|aged|age)\s+(\d{1,3})\b(?:\s*(?:years?\s+old|yrs?))?")
_AGE_B = re.compile(r"\b(\d{1,3})-year-old\s+([A-Z][a-z]+)\b")
_FLASH = re.compile(
    r"\b(flash[\s-]?back|flash[\s-]?forward|years?\s+(?:earlier|before|ago|prior)|"
    r"months?\s+(?:earlier|before|ago)|decades?\s+(?:earlier|before|ago)|"
    r"remember(?:ed|s|ing)?|recall(?:ed|s|ing)?|memor(?:y|ies)|in\s+the\s+past|"
    r"as\s+a\s+(?:child|boy|girl|teen(?:ager)?)|long\s+ago|back\s+then|"
    r"years?\s+later|in\s+the\s+future|dream(?:ed|s|t)?)\b", re.I)
_NOT_NAMES = {"The", "She", "He", "They", "It", "We", "I", "His", "Her", "This", "That",
              "Chapter", "Day", "Year", "Age", "Spring", "Summer", "Autumn", "Fall", "Winter"}


def _texts(summary: dict) -> list[str]:
    out = []
    for key in ("timeline_markers", "key_events"):
        v = summary.get(key)
        if isinstance(v, str):
            v = [v]
        for item in v or []:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
    return out


def _safe_date(y: int, m: int, d: int) -> Optional[date]:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _month(name: str) -> int:
    return _MONTHS[name.lower()[:3]]


def _full_dates(text: str) -> list[tuple[date, str]]:
    found = []
    for m in _ISO.finditer(text):
        dt = _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if dt:
            found.append((dt, m.group(0)))
    for m in _MDY.finditer(text):
        dt = _safe_date(int(m.group(3)), _month(m.group(1)), int(m.group(2)))
        if dt:
            found.append((dt, m.group(0)))
    for m in _DMY.finditer(text):
        dt = _safe_date(int(m.group(3)), _month(m.group(2)), int(m.group(1)))
        if dt:
            found.append((dt, m.group(0)))
    return found


def parse_anchors(summary: dict) -> dict:
    """Normalised anchors for one chapter summary.

    Returns {"dates": [(date, precision, quote)], "weekday_checks": [(weekday, date, quote)],
             "seasons": [(season, year|None)], "ages": {name: (age, quote)}, "flash": bool}
    precision is "day" (a full date) or "year" (a bare year → 1 Jan, compared only by year).
    """
    dates, weekday_checks, seasons, ages, flash = [], [], [], {}, False
    for text in _texts(summary):
        if _FLASH.search(text):
            flash = True
        full = _full_dates(text)
        for dt, quote in full:
            dates.append((dt, "day", quote))
        weekday = _WEEKDAY.search(text)
        if weekday and len(full) == 1:
            weekday_checks.append((weekday.group(1).lower(), full[0][0], text[:120]))
        full_years = {dt.year for dt, _ in full}
        years = [int(y) for y in _YEAR.findall(text)]
        for y in years:
            if y not in full_years:
                dates.append((date(y, 1, 1), "year", str(y)))
        for m in _SEASON.finditer(text):
            seasons.append((m.group(1).lower(), years[0] if len(set(years)) == 1 else None))
        for m in _AGE_A.finditer(text):
            if m.group(1) not in _NOT_NAMES and 0 < int(m.group(2)) < 130:
                ages[m.group(1)] = (int(m.group(2)), m.group(0))
        for m in _AGE_B.finditer(text):
            if m.group(2) not in _NOT_NAMES and 0 < int(m.group(1)) < 130:
                ages[m.group(2)] = (int(m.group(1)), m.group(0))
    return {"dates": dates, "weekday_checks": weekday_checks, "seasons": seasons,
            "ages": ages, "flash": flash}


def _latest(dates: list) -> Optional[tuple]:
    return max(dates, key=lambda d: d[0]) if dates else None


def build_timeline_signals(
    summaries: Iterable[dict],
    flash_chapters: Optional[Iterable[int]] = None,
) -> list[dict]:
    """
    summaries      — [{"chapter_number": int, "timeline_markers": [str], "key_events": [str]}]
    flash_chapters — chapter numbers a NON-stale Story Intelligence timeline
                     event marks is_flashback / is_flashforward (may be None)

    Returns at most MAX_TIMELINE_SIGNALS candidates
    {kind, chapters: [earlier, later], detail, confidence}, highest confidence
    first, then by chapter — a stable order.
    """
    rows = sorted(
        (s for s in summaries if isinstance(s.get("chapter_number"), int)),
        key=lambda s: s["chapter_number"],
    )
    flash_set = set(flash_chapters or ())
    parsed = [(s["chapter_number"], parse_anchors(s)) for s in rows]
    out: list[dict] = []

    # weekday_mismatch — within a single marker, so no ordering or flashback question.
    for ch, a in parsed:
        for weekday, dt, _quote in a["weekday_checks"]:
            actual = _WEEKDAYS[dt.weekday()]
            if weekday != actual:
                out.append({
                    "kind": "weekday_mismatch", "chapters": [ch, ch], "confidence": 0.9,
                    "detail": (f"Chapter {ch} gives {dt.isoformat()} as a {weekday.capitalize()}, "
                               f"but that date is a {actual.capitalize()}."),
                })

    # date_reversal / age_decrease / season_reversal against the latest
    # NON-flashback anchor seen so far.
    best_date: Optional[tuple] = None          # (date, precision, quote, chapter)
    ages_seen: dict[str, tuple] = {}           # name -> (age, chapter)
    seasons_seen: dict[int, tuple] = {}        # year -> (season, chapter)
    for ch, a in parsed:
        is_flash = a["flash"] or ch in flash_set
        latest = _latest(a["dates"])
        if latest and best_date and not is_flash:
            dt, prec, quote = latest
            prev_dt, prev_prec, prev_quote, prev_ch = best_date
            compare_by_year = "year" in (prec, prev_prec)
            earlier = dt.year < prev_dt.year if compare_by_year else dt < prev_dt
            if earlier:
                out.append({
                    "kind": "date_reversal", "chapters": [prev_ch, ch],
                    "confidence": 0.6 if compare_by_year else 0.8,
                    "detail": (f"Chapter {prev_ch} is anchored at {prev_quote!s} but the later "
                               f"chapter {ch} is anchored at {quote!s}, with no flashback cue."),
                })
        if latest and not is_flash and (best_date is None or latest[0] > best_date[0]):
            best_date = (*latest, ch)

        for name, (age, _quote) in a["ages"].items():
            prev = ages_seen.get(name)
            if prev and not is_flash and age < prev[0]:
                out.append({
                    "kind": "age_decrease", "chapters": [prev[1], ch], "confidence": 0.7,
                    "detail": f"{name} is {prev[0]} in chapter {prev[1]} but {age} in the later chapter {ch}.",
                })
            if not is_flash and (prev is None or age >= prev[0]):
                ages_seen[name] = (age, ch)

        for season, year in a["seasons"]:
            if year is None or season not in _SEASON_ORDER:
                continue
            prev = seasons_seen.get(year)
            if prev and not is_flash and _SEASON_ORDER[season] < _SEASON_ORDER[prev[0]]:
                out.append({
                    "kind": "season_reversal", "chapters": [prev[1], ch], "confidence": 0.5,
                    "detail": (f"Chapter {prev[1]} is set in {prev[0]} {year} but the later chapter {ch} "
                               f"is set in {season} {year}."),
                })
            if not is_flash and (prev is None or _SEASON_ORDER[season] >= _SEASON_ORDER[prev[0]]):
                seasons_seen[year] = (season, ch)

    out.sort(key=lambda s: (-s["confidence"], s["chapters"], s["kind"]))
    return out[:MAX_TIMELINE_SIGNALS]


def format_timeline_signals_for_prompt(signals: list[dict]) -> str:
    if not signals:
        return ""
    lines = [f"- [{s['kind']}] chapters {s['chapters'][0]} and {s['chapters'][1]}: {s['detail']}"
             for s in signals]
    return ("Timeline signals (machine-detected — VERIFY each against the chapter data before "
            "reporting it; a flashback, a time skip or a dream sequence is NOT a contradiction; "
            "report only those you can confirm, as type \"timeline\", citing both chapters):\n"
            + "\n".join(lines))
