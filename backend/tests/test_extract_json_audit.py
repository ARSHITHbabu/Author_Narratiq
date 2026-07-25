"""
`_extract_json` caller audit and guard (no DB, no LLM, no GPU).

Task 3.5. The four features reported in Phase 2 were a sample, not the
population: a census found 14 feature call sites, of which FIVE still hard-failed
— none of them among the reported four. The worst was generate_chapter_summary,
which runs at INDEX time, so a schema hiccup made a chapter invisible to every
retrieval and grounding feature until it was re-indexed.

This suite:
  1. holds the register of every remaining direct caller (the grandfathered set)
     and FAILS when a new one appears — new features must use the structured
     wrapper, not raw _extract_json;
  2. pins the coercers for the five converted sites;
  3. gives generate_chapter_summary extra coverage, as a critical dependency;
  4. asserts parser metrics are recorded and carry no manuscript content.

Run from backend/:

    cd backend && python3 tests/test_extract_json_audit.py
    cd backend && pytest tests/test_extract_json_audit.py -q
"""
import asyncio
import inspect
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import ai_service
from services.ai_service import (
    coerce_chapter_summary,
    coerce_copyright_findings,
    coerce_manuscript_report,
    coerce_text_suggestions,
)

BACKEND = Path(__file__).resolve().parents[1]

# ── The register ──────────────────────────────────────────────────────────────
#
# Every direct _extract_json caller that remains, with its classification.
# Adding a caller means adding a row here AND justifying it in review — that is
# the point of the guard test below.
#
#   infrastructure  — the structured wrapper itself; the approved path
#   handled         — degrades deliberately, with a logged, deterministic result
#   silent-fallback — returns empty on failure without telling anyone. FLAGGED,
#                     deliberately NOT changed here: each belongs to a later
#                     task that owns the feature and its acceptance criteria.
REGISTER = {
    # file, line-agnostic key: (function, classification, destination)
    "complete_structured/attempt-1":        ("infrastructure", None),
    "complete_structured/retry":            ("infrastructure", None),
    "_complete_json":                       ("infrastructure", None),
    "extract_cast":                         ("silent-fallback", "Stage 4 — cast generation"),
    "generate_ocr_suggestions":             ("handled", None),
    "enrich_character_from_story":          ("silent-fallback", "Stage 4 — character intelligence"),
    "build_character_arc_timeline":         ("silent-fallback", "Stage 4 — character intelligence"),
    "_parse_suggestions":                   ("silent-fallback", "Stage 5 — generation quality"),
    "generate_chapter_outline":             ("silent-fallback", "Stage 5 — generation quality"),
    "extract_narrative_threads_from_summaries": ("silent-fallback", "Stage 7 — narrative threads"),
    "services/voice/planner.py":            ("handled", None),
    # services/voice/intent.py was here as a silent-fallback with destination
    # "task 3.6". Task 3.6 converted it to complete_structured(), so it is no
    # longer a direct caller — the register shrinking is the fix landing.
}

# ai_service sites converted by task 3.5. (voice/intent.py's classify() was
# converted by task 3.6 and is asserted in tests/test_voice_execution.py, which
# owns that module.)
CONVERTED = [
    "generate_suggestions",
    "generate_plot_suggestions",
    "analyze_copyright_risk",
    "_strategy_manuscript_summary_pass",
    "generate_chapter_summary",
]


def _call_sites():
    """Every direct _extract_json call in feature code, with its function."""
    sites = []
    for path in sorted(BACKEND.rglob("*.py")):
        rel = str(path.relative_to(BACKEND))
        if rel.startswith("tests/") or "__pycache__" in rel:
            continue
        fn = None
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            m = re.match(r"(?:async )?def (\w+)", line)
            if m:
                fn = m.group(1)
            if "_extract_json(" in line and not line.strip().startswith("def _extract_json"):
                sites.append((rel, i, fn))
    return sites


# ── 1. The guard ──────────────────────────────────────────────────────────────

def test_no_new_direct_extract_json_callers():
    """New features must go through complete_structured(). This test is the
    tripwire: a new direct caller fails here and has to be classified."""
    known = set()
    for rel, line, fn in _call_sites():
        if rel.startswith("services/voice/"):
            known.add(rel)
        elif fn == "complete_structured":
            known.add("complete_structured/attempt-1")
            known.add("complete_structured/retry")
        else:
            known.add(fn)

    unregistered = known - set(REGISTER)
    assert not unregistered, (
        f"unregistered _extract_json caller(s): {sorted(unregistered)} — "
        "use complete_structured(), or add a justified row to REGISTER"
    )


def test_converted_sites_no_longer_call_extract_json_directly():
    remaining = {fn for _, _, fn in _call_sites()}
    for fn in CONVERTED:
        assert fn not in remaining, f"{fn} still parses directly instead of using the contract"


def test_converted_sites_use_the_contract():
    for name in CONVERTED:
        src = inspect.getsource(getattr(ai_service, name))
        assert "complete_structured(" in src, f"{name} does not use the contract"
        assert "coerce=" in src, f"{name} passes no coercer"


def test_no_converted_site_hard_fails_on_a_parseable_partial():
    """The defect class: raising while usable findings sit in hand."""
    for name in CONVERTED:
        src = inspect.getsource(getattr(ai_service, name))
        if "raise ValueError" in src:
            assert "if result is None" in src or "result is None" in src, \
                f"{name} may still raise on a partial result"


def test_register_covers_every_remaining_caller():
    # 11 after task 3.6 converted voice/intent.py (was 12). A further shrink is
    # progress; a GROWTH is what the guard test above catches.
    assert len(_call_sites()) >= 11, "census shrank unexpectedly — re-audit"
    for key, (classification, destination) in REGISTER.items():
        assert classification in ("infrastructure", "handled", "silent-fallback")
        if classification == "silent-fallback":
            assert destination, f"{key} is flagged but has no destination task"


# ── 2. Coercers for the converted sites ───────────────────────────────────────

def test_suggestion_coercion_salvages_and_defaults():
    value, discarded = coerce_text_suggestions([
        {"text": "Raise the stakes in Ch3.", "rationale": "flat midpoint"},
        {"rationale": "no text"},
        "not an object",
    ])
    assert len(value) == 1 and discarded == 2
    assert value[0]["id"] == 1


def test_suggestion_coercion_accepts_the_alternate_field_name():
    value, _ = coerce_text_suggestions([{"suggestion": "Cut the prologue."}])
    assert value[0]["text"] == "Cut the prologue."


def test_copyright_coercion_keeps_findings_and_clamps_risk():
    value, discarded = coerce_copyright_findings(
        {"findings": [{"description": "Echoes a known work."}, {"description": ""}],
         "overall_risk": "CATASTROPHIC"}
    )
    assert len(value["findings"]) == 1 and discarded == 1
    assert value["overall_risk"] == ""


def test_manuscript_report_coercion_accepts_partial_composites():
    """Character arcs without pacing still tells the author something."""
    value, discarded = coerce_manuscript_report({"character_arcs": [{"name": "Devika"}]})
    assert "character_arcs" in value and discarded == 4
    assert coerce_manuscript_report({"unrelated": 1})[0] is None


# ── 3. generate_chapter_summary — extra scrutiny (critical dependency) ────────

FULL_SUMMARY = {
    "key_events": ["The archive burns"],
    "characters_present": ["Devika"],
    "locations": ["The Archive"],
    "timeline_markers": ["night"],
    "emotional_tone": "tense",
    "chapter_purpose": "Destroys the evidence",
    "raw_summary": "Devika burns the archive to stop the ledger being read.",
}


def test_chapter_summary_clean_parse_is_not_degraded():
    value, discarded = coerce_chapter_summary(FULL_SUMMARY)
    assert discarded == 0
    assert value["raw_summary"].startswith("Devika burns")
    assert value["key_events"] == ["The archive burns"]


def test_chapter_summary_requires_the_load_bearing_field():
    """raw_summary is what retrieval reads. Without it there is no summary,
    and indexing must fail rather than store an empty shell."""
    for missing in ({**FULL_SUMMARY, "raw_summary": ""},
                    {**FULL_SUMMARY, "raw_summary": "   "},
                    {k: v for k, v in FULL_SUMMARY.items() if k != "raw_summary"}):
        assert coerce_chapter_summary(missing)[0] is None


def test_chapter_summary_survives_missing_structured_fields():
    """A summary with prose but no lists is thin, not useless — it is kept and
    counted as degraded so the log records the reduced retrieval quality."""
    value, discarded = coerce_chapter_summary({"raw_summary": "She burns the archive."})
    assert value["raw_summary"] == "She burns the archive."
    assert value["key_events"] == [] and value["characters_present"] == []
    assert discarded == 6, "every missing field must be counted"


def test_chapter_summary_normalises_string_lists():
    """Models routinely return "a, b" where a list was asked for. Dropping that
    would silently lose the chapter's events."""
    value, _ = coerce_chapter_summary({
        **FULL_SUMMARY, "characters_present": "Devika, Arun", "key_events": "fire, flight",
    })
    assert value["characters_present"] == ["Devika", "Arun"]
    assert value["key_events"] == ["fire", "flight"]


def test_chapter_summary_rejects_non_objects():
    for bad in ([], "a summary", None, 42):
        assert coerce_chapter_summary(bad)[0] is None


def test_chapter_summary_returns_every_field_the_indexer_writes():
    """The ChapterSummary row's columns — a missing key would be an AttributeError
    at index time, on a background task, for one chapter only."""
    value, _ = coerce_chapter_summary(FULL_SUMMARY)
    for field in ("key_events", "characters_present", "locations", "timeline_markers",
                  "emotional_tone", "chapter_purpose", "raw_summary"):
        assert field in value, f"indexer field {field} missing from coerced summary"


def test_chapter_summary_still_hard_fails_when_nothing_is_usable():
    """Correct behaviour, not a leftover: a chapter with no usable summary must
    not be indexed as if it had one."""
    src = inspect.getsource(ai_service.generate_chapter_summary)
    assert "raise ValueError" in src
    assert "must not be indexed" in src, "the reason should be recorded at the site"


def test_chapter_summary_logs_degradation_for_retrieval_quality():
    src = inspect.getsource(ai_service.generate_chapter_summary)
    assert "meta.degraded" in src
    assert "retrieval quality" in src


# ── 4. Metrics and log hygiene ────────────────────────────────────────────────

def test_parser_metrics_record_each_outcome():
    ai_service._parse_metrics.clear()

    async def fake(system, user, **kwargs):
        return fake.responses.pop(0)

    original = ai_service._complete_ex
    ai_service._complete_ex = fake
    try:
        fake.responses = ['{"issues": [{"description": "d"}]}', "stop"], None
        # clean
        fake.responses = [('{"issues": [{"description": "d"}]}', "stop")]
        asyncio.run(ai_service.complete_structured(
            "s", "u", coerce=ai_service.coerce_plot_hole_result, label="metric_clean"))
        # salvaged
        fake.responses = [('{"issues": [{"description": "d"}, 5]}', "stop")]
        asyncio.run(ai_service.complete_structured(
            "s", "u", coerce=ai_service.coerce_plot_hole_result, label="metric_salvaged"))
        # failed (two attempts)
        fake.responses = [("nonsense", "stop"), ("still nonsense", "stop")]
        asyncio.run(ai_service.complete_structured(
            "s", "u", coerce=ai_service.coerce_plot_hole_result, label="metric_failed"))
    finally:
        ai_service._complete_ex = original

    m = ai_service.parser_metrics()
    assert m["metric_clean"][ai_service.PARSE_CLEAN] == 1
    assert m["metric_salvaged"][ai_service.PARSE_SALVAGED] == 1
    assert m["metric_salvaged"]["entries_discarded"] == 1
    assert m["metric_failed"][ai_service.PARSE_FAILED] == 1
    assert all(v["calls"] == 1 for v in m.values())


def test_metrics_snapshot_is_a_copy():
    ai_service._parse_metrics.clear()
    ai_service._record_parse_metric("x", ai_service.PARSE_CLEAN, attempts=1, discarded=0)
    snapshot = ai_service.parser_metrics()
    snapshot["x"]["calls"] = 999
    assert ai_service.parser_metrics()["x"]["calls"] == 1


def test_no_parse_failure_log_writes_model_output():
    """Model output is derived from the author's manuscript. A log line is the
    easiest place for it to leak out of the system."""
    src = (BACKEND / "services/ai_service.py").read_text(encoding="utf-8")
    for pattern in (r"raw\[:\d+\]", r"raw2\[:\d+\]", r"text\[:\d+\]", r"raw_response\[:\d+\]"):
        offenders = [ln.strip() for ln in src.splitlines()
                     if re.search(pattern, ln) and "logger" in ln]
        assert not offenders, f"log leaks model output: {offenders}"


def test_parse_metric_log_line_is_machine_readable():
    src = inspect.getsource(ai_service._record_parse_metric)
    for field in ("feature=%s", "outcome=%s", "attempts=%d", "discarded=%d"):
        assert field in src, f"metric log missing {field}"
    assert "raw" not in src.replace("bucket", ""), "metric log must not touch model output"


# ── Plain-python runner (no pytest required) ──────────────────────────────────

if __name__ == "__main__":
    tests = [
        (name, obj)
        for name, obj in sorted(globals().items())
        if name.startswith("test_") and callable(obj)
    ]
    failures = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception as exc:  # noqa: BLE001 — this is the test harness
            failures.append((name, exc))
            print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")

    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
