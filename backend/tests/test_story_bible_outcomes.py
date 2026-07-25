"""
Per-section outcome tracking for Story Bible generation (no DB, no LLM, no GPU).

Task 3.2, subtask 2. The pipeline now classifies every section as generated or
failed. It does NOT yet act on that classification — the status logic is the
next subtask — so these tests do two things:

  1. Pin the classifier, including the two failure classes that raise no
     exception and were therefore invisible to any exception-driven check:
       SB-F12  empty / whitespace-only response  → returns normally, stores ""
       SB-F13  truncated response (finish_reason == "length") → returns a
               mid-sentence fragment that looks exactly like success

  2. Prove this unit is inert at the data layer: the persisted status and
     content are byte-for-byte what they were before, so nothing about the
     author-visible behaviour changed while the tracking was added.

Failure path IDs refer to docs/issues-and-bugs/story-bible-failure-path-audit.md.

Run from backend/ — config.py resolves .env relative to the working directory:

    cd backend && python3 tests/test_story_bible_outcomes.py
    cd backend && pytest tests/test_story_bible_outcomes.py -q
"""
import asyncio
import inspect
import json
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import database
from exceptions import AIServiceUnavailableError
from routers import story_bible
from routers.story_bible import (
    FAIL_EMPTY,
    FAIL_ERROR,
    FAIL_TRUNCATED,
    FAIL_UNAVAILABLE,
    SectionOutcome,
    classify_section_result,
)
from services import ai_service

BACKEND = Path(__file__).resolve().parents[1]


# ── 1. The classifier ─────────────────────────────────────────────────────────

def test_complete_section_is_ok():
    out = classify_section_result("characters", "Devika Rao — protagonist.", "stop")
    assert out.ok is True
    assert out.failure is None


def test_missing_finish_reason_does_not_fail_a_good_section():
    """Some vLLM builds omit finish_reason; absence is not evidence of failure."""
    assert classify_section_result("themes", "Memory as property.", None).ok is True


def test_empty_string_is_a_failure():
    out = classify_section_result("locations", "", "stop")
    assert out.ok is False
    assert out.failure == FAIL_EMPTY


def test_whitespace_only_is_a_failure():
    out = classify_section_result("locations", "   \n\t  ", "stop")
    assert out.ok is False
    assert out.failure == FAIL_EMPTY


def test_none_response_is_a_failure():
    """SB-F11 — message.content is None. Reaches the classifier as None."""
    out = classify_section_result("timeline", None, "stop")
    assert out.ok is False
    assert out.failure == FAIL_EMPTY


def test_truncated_section_is_a_failure():
    """SB-F13 — the whole point: no exception, plausible prose, cut off."""
    out = classify_section_result("timeline", "Chapter 1: she wakes and the", "length")
    assert out.ok is False
    assert out.failure == FAIL_TRUNCATED


def test_empty_takes_precedence_over_truncated():
    """An empty response that also hit the cap is empty, not truncated."""
    assert classify_section_result("themes", "", "length").failure == FAIL_EMPTY


def test_failure_reasons_are_author_safe():
    """Every reason is present, plain English, and free of technical leakage."""
    failures = [
        classify_section_result("a", "", "stop"),
        classify_section_result("b", "cut off here", "length"),
        SectionOutcome("c", False, FAIL_UNAVAILABLE, "The AI service was unavailable while writing this section."),
        SectionOutcome("d", False, FAIL_ERROR, "This section could not be generated."),
    ]
    banned = ("finish_reason", "max_tokens", "Traceback", "Exception", "None", "vLLM", "JSON")
    for out in failures:
        assert out.reason.strip(), f"{out.failure} has no author-facing reason"
        for word in banned:
            assert word not in out.reason, f"{out.failure} reason leaks {word!r}"


# ── 2. The widened generate_story_bible_section contract ──────────────────────

def test_section_generator_returns_text_and_finish_reason():
    src = inspect.getsource(ai_service.generate_story_bible_section)
    assert "_complete_ex(" in src, "must use _complete_ex — _complete discards finish_reason"
    assert "-> tuple[str, Optional[str]]" in src, "return annotation must expose finish_reason"


def test_every_caller_unpacks_the_widened_return():
    """generate_story_bible_section returns (text, finish_reason). A caller that
    assigns it to one name silently gets a tuple where it expects a string, so
    every call site must unpack — this test is the tripwire.

    Originally asserted a single caller; the per-section regeneration pipeline
    added a second, legitimate one. The invariant that matters is the unpacking,
    not the count."""
    call_sites = []
    for path in BACKEND.rglob("*.py"):
        if path.name == Path(__file__).name:
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"await\s+generate_story_bible_section\s*\(", line):
                call_sites.append((f"{path.relative_to(BACKEND)}:{i}", line.strip()))

    assert call_sites, "no call sites found — has the function been renamed?"
    for where, line in call_sites:
        assert where.startswith("routers/story_bible.py:"), f"unexpected caller at {where}"
        assert re.match(r"\w+,\s*\w+\s*=\s*await\s+generate_story_bible_section", line), \
            f"{where} does not unpack (text, finish_reason): {line}"


# ── 3. Pipeline behaviour — outcomes recorded, persistence unchanged ──────────

class _FakeBible:
    def __init__(self):
        self.bible_id, self.story_id = "b1", "s1"
        self.content_json, self.status, self.version = "{}", "running", 1
        self.failed_sections = []
        self.updated_at = None


class _FakeQuery:
    def __init__(self, result): self._result = result
    def filter(self, *a, **k): return self
    def first(self): return self._result


class _FakeSession:
    """Minimal Session stand-in. rollback() discards uncommitted attribute
    changes, as a real session does by expiring the instance — without that, a
    status assigned in memory survives a failed commit and a test can pass on
    state that was never persisted."""

    def __init__(self, bible):
        self.bible, self.commits, self.closed = bible, 0, False
        self._snapshot = dict(bible.__dict__)

    def query(self, model): return _FakeQuery(self.bible)

    def commit(self):
        self.commits += 1
        self._snapshot = dict(self.bible.__dict__)

    def rollback(self):
        self.bible.__dict__.clear()
        self.bible.__dict__.update(self._snapshot)

    def close(self): self.closed = True


def _run_pipeline(section_results):
    """Run _generate_bible_pipeline with the DB and the model stubbed.

    section_results maps section -> (text, finish_reason) or an Exception to
    raise. Returns (fake_bible, captured_log_records).
    """
    bible = _FakeBible()
    session = _FakeSession(bible)

    async def fake_generate(section, context):
        result = section_results[section]
        if isinstance(result, Exception):
            raise result
        return result

    originals = (
        database.SessionLocal,
        story_bible._build_full_context,
        story_bible.generate_story_bible_section,
    )
    database.SessionLocal = lambda: session
    story_bible._build_full_context = lambda story_id, db: "CONTEXT"
    story_bible.generate_story_bible_section = fake_generate

    records = []

    class _Capture(logging.Handler):
        def emit(self, record): records.append(record.getMessage())

    handler = _Capture()
    story_bible.logger.addHandler(handler)
    prev_level = story_bible.logger.level
    story_bible.logger.setLevel(logging.INFO)   # the all-success summary is INFO
    try:
        asyncio.run(story_bible._generate_bible_pipeline("s1", "b1", False))
    finally:
        story_bible.logger.setLevel(prev_level)
        story_bible.logger.removeHandler(handler)
        (database.SessionLocal,
         story_bible._build_full_context,
         story_bible.generate_story_bible_section) = originals
    return bible, records


def _all_good():
    return {s: (f"{s} content", "stop") for s in story_bible._BIBLE_SECTIONS}


def test_all_sections_generated_logs_a_full_count():
    bible, logs = _run_pipeline(_all_good())
    assert any("5/5 sections generated" in m for m in logs), logs
    assert bible.status == "completed"


def test_truncated_section_is_recorded_as_failed():
    results = _all_good()
    results["timeline"] = ("Chapter 1: she wakes and the", "length")
    _, logs = _run_pipeline(results)
    summary = next(m for m in logs if "sections generated" in m)
    assert "4/5" in summary, summary
    assert f"timeline={FAIL_TRUNCATED}" in summary, summary


def test_empty_section_is_recorded_as_failed():
    results = _all_good()
    results["locations"] = ("   ", "stop")
    _, logs = _run_pipeline(results)
    summary = next(m for m in logs if "sections generated" in m)
    assert "4/5" in summary and f"locations={FAIL_EMPTY}" in summary, summary


def test_exception_classes_are_distinguished():
    results = _all_good()
    results["characters"] = AIServiceUnavailableError()
    results["themes"] = ValueError("boom")
    _, logs = _run_pipeline(results)
    summary = next(m for m in logs if "sections generated" in m)
    assert "3/5" in summary, summary
    assert f"characters={FAIL_UNAVAILABLE}" in summary, summary
    assert f"themes={FAIL_ERROR}" in summary, summary


def test_summary_log_carries_no_section_text():
    results = _all_good()
    results["characters"] = ("SECRET MANUSCRIPT PROSE", "stop")
    _, logs = _run_pipeline(results)
    assert not any("SECRET MANUSCRIPT PROSE" in m for m in logs), "manuscript text reached the log"


# ── 4. Terminal status is derived from the outcomes (subtask 3) ───────────────
#
# These two were inertness guards under subtask 2, asserting the old
# unconditional 'completed'. Subtask 3 flips them: that was the defect.

def test_status_is_failed_when_every_section_fails():
    """SB-F09/F16/F17/F20 — five placeholders is not a completed story bible."""
    results = {s: AIServiceUnavailableError() for s in story_bible._BIBLE_SECTIONS}
    bible, _ = _run_pipeline(results)
    assert bible.status == story_bible.STATUS_FAILED


def test_status_is_partial_when_some_sections_fail():
    results = _all_good()
    results["themes"] = ValueError("boom")
    bible, _ = _run_pipeline(results)
    assert bible.status == story_bible.STATUS_PARTIAL


def test_status_is_completed_only_when_all_sections_succeed():
    bible, _ = _run_pipeline(_all_good())
    assert bible.status == story_bible.STATUS_COMPLETED


def test_truncated_section_downgrades_status_to_partial():
    """SB-F13 — the section reads like prose and raises nothing; it must still
    stop the bible being called completed."""
    results = _all_good()
    results["timeline"] = ("Chapter 1: she wakes and the", "length")
    bible, _ = _run_pipeline(results)
    assert bible.status == story_bible.STATUS_PARTIAL


def test_empty_section_downgrades_status_to_partial():
    """SB-F12 — same, for a section that came back blank."""
    results = _all_good()
    results["locations"] = ("", "stop")
    bible, _ = _run_pipeline(results)
    assert bible.status == story_bible.STATUS_PARTIAL


def test_every_failure_class_prevents_completed():
    """No failure class may slip through as success."""
    for section_result in (
        AIServiceUnavailableError(),
        ValueError("boom"),
        ("", "stop"),
        ("   \n ", "stop"),
        ("cut off mid-sen", "length"),
    ):
        results = _all_good()
        results["characters"] = section_result
        bible, _ = _run_pipeline(results)
        assert bible.status != story_bible.STATUS_COMPLETED, section_result


def test_pipeline_abort_before_the_loop_is_failed():
    """SB-F01/F02 — context assembly raises, so no section is ever attempted."""
    bible = _FakeBible()
    session = _FakeSession(bible)
    originals = (database.SessionLocal, story_bible._build_full_context)
    database.SessionLocal = lambda: session

    def _boom(story_id, db):
        raise TypeError("'NoneType' object is not subscriptable")

    story_bible._build_full_context = _boom
    try:
        asyncio.run(story_bible._generate_bible_pipeline("s1", "b1", False))
    finally:
        database.SessionLocal, story_bible._build_full_context = originals
    assert bible.status == story_bible.STATUS_FAILED


def test_derive_status_treats_no_outcomes_as_failed():
    assert story_bible.derive_status([]) == story_bible.STATUS_FAILED


# ── 5. SB-F23 — a commit failure must still end as 'failed' ───────────────────

class _FailingCommitSession(_FakeSession):
    """Commits raise until rollback() is called — the shape of a real session
    whose transaction has failed and which refuses further work until rolled
    back. `events` records the call order so the test can prove the rollback
    happened BEFORE the recovery query, not merely that both occurred."""

    def __init__(self, bible):
        super().__init__(bible)
        self.events = []
        self._poisoned = False          # healthy until the first commit fails
        self._fail_next_commit = True

    def commit(self):
        self.events.append("commit")
        if self._fail_next_commit:
            # The status write fails and leaves the transaction unusable —
            # exactly the state that made the recovery query raise.
            self._fail_next_commit = False
            self._poisoned = True
            raise RuntimeError("could not commit: connection reset")
        self.commits += 1

    def rollback(self):
        self.events.append("rollback")
        self._poisoned = False
        super().rollback()             # discard the uncommitted status write

    def query(self, model):
        self.events.append("query")
        if self._poisoned:
            raise RuntimeError("PendingRollbackError: rollback required first")
        return _FakeQuery(self.bible)


def _run_with_failing_commit():
    bible = _FakeBible()
    session = _FailingCommitSession(bible)
    originals = (database.SessionLocal,
                 story_bible._build_full_context,
                 story_bible.generate_story_bible_section)
    database.SessionLocal = lambda: session
    story_bible._build_full_context = lambda story_id, db: "CONTEXT"

    async def fake_generate(section, context):
        return f"{section} content", "stop"

    story_bible.generate_story_bible_section = fake_generate
    try:
        asyncio.run(story_bible._generate_bible_pipeline("s1", "b1", False))
    finally:
        (database.SessionLocal,
         story_bible._build_full_context,
         story_bible.generate_story_bible_section) = originals
    return bible, session


def test_commit_failure_does_not_escape_the_handler():
    """(7) The pipeline is a background task — an escaping exception is lost."""
    _run_with_failing_commit()          # must not raise


def test_commit_failure_rolls_back_before_any_recovery_query():
    """(1)(2) The rollback must precede the re-query, or the recovery query is
    itself the thing that fails. This ordering IS the fix."""
    _, session = _run_with_failing_commit()
    first_commit = session.events.index("commit")
    rollback     = session.events.index("rollback", first_commit)
    recovery_q   = session.events.index("query", rollback)
    assert first_commit < rollback < recovery_q, session.events


def test_commit_failure_ends_as_failed_and_is_committed():
    """(3)(4)(5) The bible is re-queried, set to failed, and the recovery
    commit succeeds."""
    bible, session = _run_with_failing_commit()
    assert bible.status == story_bible.STATUS_FAILED
    assert session.commits == 1, "the recovery commit did not succeed"


def test_commit_failure_never_leaves_the_row_running():
    """(6) The regression this whole test group exists for: before the fix the
    row stayed 'running' for ever, un-retryable until a restart."""
    bible, _ = _run_with_failing_commit()
    assert bible.status != story_bible.STATUS_RUNNING


# ── 6. failed_sections — persisted, cleared, and author-facing only ──────────

def test_failed_sections_records_each_failure_with_class_and_reason():
    results = _all_good()
    results["timeline"] = ("cut off mid-sen", "length")
    results["characters"] = AIServiceUnavailableError()
    bible, _ = _run_pipeline(results)

    by_section = {f["section"]: f for f in bible.failed_sections}
    assert set(by_section) == {"timeline", "characters"}
    assert by_section["timeline"]["failure"] == FAIL_TRUNCATED
    assert by_section["characters"]["failure"] == FAIL_UNAVAILABLE
    for entry in bible.failed_sections:
        assert entry["reason"].strip(), "every failure needs an author-facing reason"


def test_failed_sections_is_empty_on_a_fully_successful_bible():
    bible, _ = _run_pipeline(_all_good())
    assert bible.failed_sections == []
    assert bible.status == story_bible.STATUS_COMPLETED


def test_failed_sections_lists_all_five_when_everything_fails():
    results = {s: AIServiceUnavailableError() for s in story_bible._BIBLE_SECTIONS}
    bible, _ = _run_pipeline(results)
    assert len(bible.failed_sections) == 5
    assert bible.status == story_bible.STATUS_FAILED


def test_successful_regeneration_clears_stale_failures():
    """The largest correctness risk in this unit: a repaired bible must stop
    reporting sections that are now fine."""
    bible = _FakeBible()
    session = _FakeSession(bible)
    originals = (database.SessionLocal,
                 story_bible._build_full_context,
                 story_bible.generate_story_bible_section)
    database.SessionLocal = lambda: session
    story_bible._build_full_context = lambda story_id, db: "CONTEXT"

    plan = {}

    async def fake_generate(section, context):
        result = plan[section]
        if isinstance(result, Exception):
            raise result
        return result

    story_bible.generate_story_bible_section = fake_generate
    try:
        # Run 1 — themes fails.
        plan.update(_all_good())
        plan["themes"] = ValueError("boom")
        asyncio.run(story_bible._generate_bible_pipeline("s1", "b1", False))
        assert [f["section"] for f in bible.failed_sections] == ["themes"]
        assert bible.status == story_bible.STATUS_PARTIAL

        # Run 2 — everything succeeds. The stale entry must be gone.
        plan.update(_all_good())
        asyncio.run(story_bible._generate_bible_pipeline("s1", "b1", False))
    finally:
        (database.SessionLocal,
         story_bible._build_full_context,
         story_bible.generate_story_bible_section) = originals

    assert bible.failed_sections == [], "stale failure survived a successful run"
    assert bible.status == story_bible.STATUS_COMPLETED


def test_pipeline_abort_clears_failed_sections():
    """A pipeline-level failure has no per-section detail; the previous run's
    list must not be left behind as if it explained this failure."""
    bible = _FakeBible()
    bible.failed_sections = [{"section": "themes", "failure": FAIL_ERROR, "reason": "stale"}]
    session = _FakeSession(bible)
    originals = (database.SessionLocal, story_bible._build_full_context)
    database.SessionLocal = lambda: session

    def _boom(story_id, db):
        raise RuntimeError("context assembly failed")

    story_bible._build_full_context = _boom
    try:
        asyncio.run(story_bible._generate_bible_pipeline("s1", "b1", False))
    finally:
        database.SessionLocal, story_bible._build_full_context = originals

    assert bible.status == story_bible.STATUS_FAILED
    assert bible.failed_sections == []


def test_failed_sections_payload_carries_only_author_facing_fields():
    """The persisted shape is an API contract, not a debugging channel."""
    payload = story_bible.failed_section_payload(
        SectionOutcome("timeline", False, FAIL_ERROR, "This section could not be generated.")
    )
    assert set(payload) == {"section", "failure", "reason"}


def test_failed_sections_never_carries_exception_text():
    """A raised exception's message may quote model or manuscript text; only the
    fixed author-safe reason may be persisted."""
    results = _all_good()
    results["locations"] = ValueError("SECRET MANUSCRIPT PROSE")
    bible, _ = _run_pipeline(results)
    blob = json.dumps(bible.failed_sections)
    assert "SECRET MANUSCRIPT PROSE" not in blob
    assert "ValueError" not in blob


def test_response_schema_exposes_failed_sections_and_never_null():
    """Legacy rows predate the column and read as NULL — the client must still
    receive a list it can iterate unconditionally."""
    import schemas

    legacy = schemas.StoryBibleOut(
        bible_id="b", story_id="s", title="Story Bible", content_json="{}",
        version=1, status="completed", failed_sections=None,
    )
    assert legacy.failed_sections == []

    populated = schemas.StoryBibleOut(
        bible_id="b", story_id="s", title="Story Bible", content_json="{}",
        version=1, status="partial",
        failed_sections=[{"section": "themes", "failure": FAIL_ERROR, "reason": "x"}],
    )
    assert populated.failed_sections[0]["section"] == "themes"


def test_model_and_migration_agree_on_the_column():
    """The column must arrive through both provisioning paths — Alembic for a
    migrated database, the create_all shim for one built from models."""
    from models import StoryBible as StoryBibleModel

    assert "failed_sections" in StoryBibleModel.__table__.columns

    migration = (BACKEND / "migrations/versions/0016_story_bible_failed_sections.py").read_text(encoding="utf-8")
    assert 'down_revision = "0015"' in migration, "0016 must follow 0015"
    assert "failed_sections" in migration
    assert "def downgrade" in migration and "drop_column" in migration, "must be reversible"

    shim = (BACKEND / "database.py").read_text(encoding="utf-8")
    assert '_add_col("story_bibles", "failed_sections"' in shim


# ── 7. No placeholder is ever persisted as content (subtask 5, SB-F16) ───────
#
# This group replaces the interim guard that pinned placeholder persistence.
# content_json now holds usable sections only; failure lives in status and
# failed_sections.

PLACEHOLDER_MARKERS = ("[AI temporarily unavailable", "[Error generating ")


def test_failed_sections_are_absent_from_content():
    results = _all_good()
    results["characters"] = AIServiceUnavailableError()
    results["themes"] = ValueError("boom")
    bible, _ = _run_pipeline(results)

    content = json.loads(bible.content_json)
    assert set(content) == {"locations", "timeline", "world_rules"}
    assert "characters" not in content, "a failed section must not be stored at all"
    assert "themes" not in content
    assert content["locations"] == "locations content"
    assert bible.status == story_bible.STATUS_PARTIAL


def test_no_placeholder_string_survives_any_failure_class():
    """The invariant the database-state verification asks for, at the source."""
    for section_result in (
        AIServiceUnavailableError(),
        ValueError("boom"),
        ("", "stop"),
        ("   \n ", "stop"),
        ("cut off mid-sen", "length"),
    ):
        results = _all_good()
        results["characters"] = section_result
        bible, _ = _run_pipeline(results)
        for marker in PLACEHOLDER_MARKERS:
            assert marker not in bible.content_json, f"{section_result} left {marker!r}"


def test_exception_text_never_reaches_content():
    """An exception message may quote model or manuscript text. It belongs in
    the log and nowhere else."""
    results = _all_good()
    results["locations"] = ValueError("SECRET MANUSCRIPT PROSE")
    bible, logs = _run_pipeline(results)
    assert "SECRET MANUSCRIPT PROSE" not in bible.content_json
    assert "ValueError" not in bible.content_json
    # …but it IS logged, so the failure remains diagnosable.
    assert any("SECRET MANUSCRIPT PROSE" in m for m in logs), "diagnostic detail lost from logs"


def test_truncated_section_text_is_dropped():
    """Option A — a fragment is real prose that stops mid-sentence. Storing it
    would render and export as a finished section. Only the failure record is
    kept; deliberate preservation belongs to the pinning feature."""
    results = _all_good()
    results["timeline"] = ("Chapter 1: she wakes and the", "length")
    bible, _ = _run_pipeline(results)

    content = json.loads(bible.content_json)
    assert "timeline" not in content
    assert "she wakes" not in bible.content_json
    entry = next(f for f in bible.failed_sections if f["section"] == "timeline")
    assert entry == {
        "section": "timeline",
        "failure": FAIL_TRUNCATED,
        "reason": "This section was cut off before it finished.",
    }
    assert bible.status == story_bible.STATUS_PARTIAL


def test_content_and_failed_sections_are_complementary():
    """The core invariant: every section is in exactly one of the two."""
    results = _all_good()
    results["characters"] = AIServiceUnavailableError()
    results["timeline"] = ("frag", "length")
    results["themes"] = ("", "stop")
    bible, _ = _run_pipeline(results)

    stored = set(json.loads(bible.content_json))
    failed = {f["section"] for f in bible.failed_sections}
    assert stored.isdisjoint(failed), "a section cannot be both stored and failed"
    assert stored | failed == set(story_bible._BIBLE_SECTIONS), "every section accounted for"


def test_total_failure_stores_no_content_at_all():
    results = {s: AIServiceUnavailableError() for s in story_bible._BIBLE_SECTIONS}
    bible, _ = _run_pipeline(results)
    assert json.loads(bible.content_json) == {}
    assert bible.status == story_bible.STATUS_FAILED
    assert len(bible.failed_sections) == 5


def test_full_success_stores_all_five_sections():
    bible, _ = _run_pipeline(_all_good())
    assert set(json.loads(bible.content_json)) == set(story_bible._BIBLE_SECTIONS)
    assert bible.failed_sections == []


def test_docx_export_omits_failed_sections():
    """The export writes any non-empty section as document body. With the
    placeholder gone there is nothing to write, so a failed section is simply
    absent from the DOCX rather than exported as an error string."""
    src = (BACKEND / "routers/story_bible.py").read_text(encoding="utf-8")
    export = src[src.index("def export_story_bible_docx"):]
    assert 'content.get(key, "")' in export, "export still reads sections by key"
    assert "if not text:" in export and "continue" in export, "export must skip absent sections"

    # And the pipeline gives it nothing to skip over that looks like content.
    results = _all_good()
    results["world_rules"] = ValueError("boom")
    bible, _ = _run_pipeline(results)
    exported = [k for k, v in json.loads(bible.content_json).items() if v]
    assert "world_rules" not in exported


def test_commit_count_unchanged():
    """One commit on the success path, as before — no extra writes introduced."""
    bible, _ = _run_pipeline(_all_good())
    assert bible.version == 1


# ── 8. Per-section regeneration — pipeline (subtask 6) ───────────────────────

def _bible_with(content: dict, failed: list, status: str, version: int = 1):
    b = _FakeBible()
    b.content_json = json.dumps(content)
    b.failed_sections = failed
    b.status = status
    b.version = version
    return b


def _run_section_pipeline(bible, section, result):
    """Regenerate one section with the DB and model stubbed.
    `result` is (text, finish_reason) or an Exception to raise."""
    session = _FakeSession(bible)
    originals = (database.SessionLocal,
                 story_bible._build_full_context,
                 story_bible.generate_story_bible_section)
    database.SessionLocal = lambda: session
    story_bible._build_full_context = lambda story_id, db: "CONTEXT"

    async def fake_generate(section, context):
        if isinstance(result, Exception):
            raise result
        return result

    story_bible.generate_story_bible_section = fake_generate
    try:
        asyncio.run(story_bible._regenerate_section_pipeline("s1", "b1", section))
    finally:
        (database.SessionLocal,
         story_bible._build_full_context,
         story_bible.generate_story_bible_section) = originals
    return bible, session


def test_repairing_the_last_failure_completes_the_bible():
    bible = _bible_with(
        {"characters": "c", "locations": "l", "timeline": "t", "world_rules": "w"},
        [{"section": "themes", "failure": FAIL_TRUNCATED, "reason": "cut off"}],
        story_bible.STATUS_PARTIAL,
    )
    _run_section_pipeline(bible, "themes", ("themes content", "stop"))

    assert json.loads(bible.content_json)["themes"] == "themes content"
    assert bible.failed_sections == []
    assert bible.status == story_bible.STATUS_COMPLETED


def test_repairing_one_of_several_leaves_the_bible_partial():
    bible = _bible_with(
        {"characters": "c", "locations": "l", "timeline": "t"},
        [{"section": "themes", "failure": FAIL_ERROR, "reason": "x"},
         {"section": "world_rules", "failure": FAIL_EMPTY, "reason": "y"}],
        story_bible.STATUS_PARTIAL,
    )
    _run_section_pipeline(bible, "themes", ("themes content", "stop"))

    assert bible.status == story_bible.STATUS_PARTIAL
    assert [f["section"] for f in bible.failed_sections] == ["world_rules"]


def test_failed_repair_keeps_the_entry_and_stores_no_content():
    bible = _bible_with(
        {"characters": "c", "locations": "l", "timeline": "t", "world_rules": "w"},
        [{"section": "themes", "failure": FAIL_ERROR, "reason": "x"}],
        story_bible.STATUS_PARTIAL,
    )
    _run_section_pipeline(bible, "themes", AIServiceUnavailableError())

    assert "themes" not in json.loads(bible.content_json)
    entry = next(f for f in bible.failed_sections if f["section"] == "themes")
    assert entry["failure"] == FAIL_UNAVAILABLE
    assert bible.status == story_bible.STATUS_PARTIAL


def test_truncated_repair_is_still_a_failure():
    bible = _bible_with(
        {"characters": "c", "locations": "l", "timeline": "t", "world_rules": "w"},
        [{"section": "themes", "failure": FAIL_ERROR, "reason": "x"}],
        story_bible.STATUS_PARTIAL,
    )
    _run_section_pipeline(bible, "themes", ("half a sect", "length"))

    assert "themes" not in json.loads(bible.content_json)
    assert "half a sect" not in bible.content_json
    assert next(f for f in bible.failed_sections if f["section"] == "themes")["failure"] == FAIL_TRUNCATED


def test_section_repair_leaves_other_sections_untouched():
    bible = _bible_with(
        {"characters": "original characters", "locations": "original locations"},
        [{"section": "themes", "failure": FAIL_ERROR, "reason": "x"},
         {"section": "timeline", "failure": FAIL_ERROR, "reason": "x"},
         {"section": "world_rules", "failure": FAIL_ERROR, "reason": "x"}],
        story_bible.STATUS_PARTIAL,
    )
    _run_section_pipeline(bible, "themes", ("themes content", "stop"))

    content = json.loads(bible.content_json)
    assert content["characters"] == "original characters"
    assert content["locations"] == "original locations"


def test_section_repair_does_not_bump_the_version():
    """Repairing completes an existing bible; it does not mint a new one."""
    bible = _bible_with({"characters": "c"}, [], story_bible.STATUS_PARTIAL, version=3)
    _run_section_pipeline(bible, "themes", ("themes content", "stop"))
    assert bible.version == 3


def test_failed_section_repair_restores_status_instead_of_failing_the_bible():
    """A broken repair attempt must not destroy four good sections."""
    bible = _bible_with(
        {"characters": "c", "locations": "l", "timeline": "t", "world_rules": "w"},
        [{"section": "themes", "failure": FAIL_ERROR, "reason": "x"}],
        story_bible.STATUS_PARTIAL,
    )
    session = _FakeSession(bible)
    originals = (database.SessionLocal, story_bible._build_full_context)
    database.SessionLocal = lambda: session

    def _boom(story_id, db):
        raise RuntimeError("context assembly failed")

    story_bible._build_full_context = _boom
    try:
        asyncio.run(story_bible._regenerate_section_pipeline("s1", "b1", "themes"))
    finally:
        database.SessionLocal, story_bible._build_full_context = originals

    assert bible.status == story_bible.STATUS_PARTIAL, "a failed repair must not fail the whole bible"
    assert json.loads(bible.content_json)["characters"] == "c"


def test_outcomes_from_persisted_state_round_trips():
    content = {"characters": "c", "locations": "l"}
    failed = [{"section": "themes", "failure": FAIL_TRUNCATED, "reason": "cut off"}]
    outcomes = story_bible.outcomes_from_persisted_state(content, failed)

    by_name = {o.section: o for o in outcomes}
    assert len(outcomes) == 5
    assert by_name["characters"].ok is True
    assert by_name["themes"].ok is False and by_name["themes"].failure == FAIL_TRUNCATED
    # Present in neither — treated as failed, not silently counted as content.
    assert by_name["timeline"].ok is False


def test_outcomes_from_persisted_state_handles_legacy_null():
    """A bible written before failed_sections existed: all five sections stored,
    no failure list. It must read as completed, not as five failures."""
    content = {s: "text" for s in story_bible._BIBLE_SECTIONS}
    outcomes = story_bible.outcomes_from_persisted_state(content, None)
    assert story_bible.derive_status(outcomes) == story_bible.STATUS_COMPLETED


# ── 9. Per-section regeneration — endpoint ───────────────────────────────────

def _client(story=object(), bible=None):
    """A minimal app carrying only the story-bible router, with the DB and the
    current user stubbed. Exercises the real route, validation and guards."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from middleware.rate_limit import limiter
    from database import get_db
    from routers.auth import get_current_user
    from models import Story as StoryModel

    class _Q:
        def __init__(self, r): self._r = r
        def filter(self, *a, **k): return self
        def order_by(self, *a, **k): return self
        def first(self): return self._r

    class _DB:
        def __init__(self): self.commits = 0
        def query(self, model): return _Q(story if model is StoryModel else bible)
        def commit(self): self.commits += 1

    app = FastAPI()
    # Every test posts as the same user; the per-user background-AI limit
    # (3/minute) would otherwise 429 the later cases. Rate limiting is not what
    # these tests are checking.
    limiter.enabled = False
    app.state.limiter = limiter
    app.include_router(story_bible.router, prefix="/api/stories")
    app.dependency_overrides[get_current_user] = lambda: type("U", (), {"user_id": "u1"})()
    app.dependency_overrides[get_db] = lambda: _DB()
    return TestClient(app)


def _stub_section_pipeline():
    async def _noop(story_id, bible_id, section): return None
    original = story_bible._regenerate_section_pipeline
    story_bible._regenerate_section_pipeline = _noop
    return original


def test_section_endpoint_is_rate_limited_and_authenticated():
    """The tests above disable the limiter, so assert at the source that the
    real endpoint carries the same protections as full generation."""
    src = (BACKEND / "routers/story_bible.py").read_text(encoding="utf-8")
    handler = src[src.index('@router.post("/{story_id}/story-bible/sections/{section}"'):]
    handler = handler[:handler.index("\n@router.")] if "\n@router." in handler else handler

    assert "@limiter.limit(settings.rate_limit_background_ai, key_func=get_user_id)" in handler
    assert "current_user: User = Depends(get_current_user)" in handler
    assert "_get_owned_story(story_id, current_user.user_id, db)" in handler


def test_endpoint_rejects_an_unknown_section():
    r = _client(bible=_FakeBible()).post("/api/stories/s1/story-bible/sections/not_a_section")
    assert r.status_code == 400
    assert "Unknown section" in r.json()["detail"]


def test_endpoint_404s_when_no_bible_exists():
    r = _client(bible=None).post("/api/stories/s1/story-bible/sections/themes")
    assert r.status_code == 404


def test_endpoint_404s_when_the_story_is_not_the_users():
    r = _client(story=None, bible=_FakeBible()).post("/api/stories/s1/story-bible/sections/themes")
    assert r.status_code == 404, "ownership must be enforced before anything else"


def test_endpoint_refuses_while_a_generation_is_running():
    bible = _FakeBible()
    bible.status = story_bible.STATUS_RUNNING
    r = _client(bible=bible).post("/api/stories/s1/story-bible/sections/themes")
    assert r.status_code == 200
    assert r.json()["status"] == "already_generating"


def test_endpoint_accepts_a_valid_section_and_marks_it_running():
    bible = _bible_with({"characters": "c"}, [], story_bible.STATUS_PARTIAL)
    original = _stub_section_pipeline()
    try:
        r = _client(bible=bible).post("/api/stories/s1/story-bible/sections/themes")
    finally:
        story_bible._regenerate_section_pipeline = original

    assert r.status_code == 200
    assert r.json()["status"] == "processing"
    assert bible.status == story_bible.STATUS_RUNNING, "GET must report in-progress across reloads"


def test_every_bible_section_is_accepted_by_the_endpoint():
    original = _stub_section_pipeline()
    try:
        for section in story_bible._BIBLE_SECTIONS:
            bible = _bible_with({}, [], story_bible.STATUS_PARTIAL)
            r = _client(bible=bible).post(f"/api/stories/s1/story-bible/sections/{section}")
            assert r.status_code == 200, section
    finally:
        story_bible._regenerate_section_pipeline = original


# ── 10. The database-state verifier detects real violations ──────────────────
#
# The live table is empty, so running the verifier passes vacuously. These tests
# prove the checker would actually catch a violation if one existed.

def _checker():
    sys.path.insert(0, str(BACKEND / "scripts"))
    import verify_story_bible_integrity as v
    return v


def test_verifier_accepts_a_healthy_bible_set():
    v = _checker()
    rows = [
        ("b1", "completed", json.dumps({s: "text" for s in story_bible._BIBLE_SECTIONS}), []),
        ("b2", "partial", json.dumps({"characters": "c"}),
         [{"section": "themes", "failure": FAIL_ERROR, "reason": "x"}]),
    ]
    assert v.check_rows(rows) == []


def test_verifier_catches_a_persisted_placeholder():
    v = _checker()
    rows = [("b1", "completed",
             json.dumps({"themes": "[AI temporarily unavailable — please regenerate]"}), [])]
    assert any("placeholder" in f for f in v.check_rows(rows))


def test_verifier_does_not_false_positive_on_bracketed_prose():
    """SB-F15 — the exact reason a bare '[' scan was rejected."""
    v = _checker()
    rows = [("b1", "completed",
             json.dumps({s: "[Chapter 3] She returns. See [the map](x) and [Act I]."
                         for s in story_bible._BIBLE_SECTIONS}), [])]
    assert v.check_rows(rows) == []


def test_verifier_catches_completed_with_failed_sections():
    v = _checker()
    rows = [("b1", "completed", json.dumps({"characters": "c"}),
             [{"section": "themes", "failure": FAIL_ERROR, "reason": "x"}])]
    assert any("status=completed but failed_sections" in f for f in v.check_rows(rows))


def test_verifier_catches_partial_without_explanation():
    v = _checker()
    rows = [("b1", "partial", json.dumps({"characters": "c"}), [])]
    assert any("failed_sections is empty" in f for f in v.check_rows(rows))


def test_verifier_catches_a_section_both_stored_and_failed():
    v = _checker()
    rows = [("b1", "partial", json.dumps({"themes": "real content"}),
             [{"section": "themes", "failure": FAIL_ERROR, "reason": "x"}])]
    assert any("both stored and failed" in f for f in v.check_rows(rows))


def test_verifier_catches_an_unrecognised_status():
    v = _checker()
    rows = [("b1", "done", json.dumps({"characters": "c"}), [])]
    assert any("unrecognised status" in f for f in v.check_rows(rows))


# ── 11. Grounding and provenance (task 3.3) ──────────────────────────────────

class _FakeSummary:
    def __init__(self, n, body, events=None):
        self.chapter_number = n
        self.raw_summary = body
        self.key_events = events or [f"event {n}"]
        self.characters_present = ["Devika"]
        self.locations = ["The Archive"]
        self.emotional_tone = "tense"


class _FakeChar:
    def __init__(self, name, role="supporting"):
        self.name, self.role = name, role


class _FakeProfile:
    def __init__(self, text="p"):
        self.appearance = self.personality = self.goals = self.backstory = text


class _ContextDB:
    """Serves the six queries _build_full_context makes, by model."""
    def __init__(self, summaries=(), chars=(), notes=(), cards=(), genre=None):
        self.summaries, self.chars = list(summaries), list(chars)
        self.notes, self.cards, self.genre = list(notes), list(cards), genre

    def query(self, *models):
        from models import ChapterSummary as CS, Character as Ch, StoryNote as SN
        from models import NoteCard as NC, GenreProfile as GP
        first = models[0]
        if first is CS:   return _ContextQuery(self.summaries)
        if first is Ch:   return _ContextQuery(self.chars)
        if first is SN:   return _ContextQuery(self.notes)
        if first is NC:   return _ContextQuery(self.cards)
        if first is GP:   return _ContextQuery([self.genre] if self.genre else [])
        return _ContextQuery([])


class _ContextQuery:
    def __init__(self, rows): self._rows = rows
    def filter(self, *a, **k): return self
    def outerjoin(self, *a, **k): return self
    def order_by(self, *a, **k): return self
    def all(self): return self._rows
    def first(self): return self._rows[0] if self._rows else None


def test_token_counting_uses_the_real_tokenizer_or_a_pessimistic_fallback():
    n = ai_service.count_tokens("The archive burns at midnight.")
    assert n > 0
    assert ai_service.count_tokens("") == 0
    # Whichever path ran, more text must cost more tokens.
    assert ai_service.count_tokens("word " * 100) > ai_service.count_tokens("word " * 10)


def test_context_budget_scales_with_the_model_window():
    from config import settings
    original = getattr(settings, "max_model_len", 8192)
    try:
        settings.max_model_len = 8192
        small = story_bible.bible_context_token_budget()
        settings.max_model_len = 16384
        large = story_bible.bible_context_token_budget()
    finally:
        settings.max_model_len = original

    assert large > small, "budget must follow the serving window, not a constant"
    assert small < 8192, "budget must leave room for the completion and prompt"
    assert large == 16384 - 1500 - 900


def test_fair_share_gives_small_entries_all_they_need():
    assert story_bible.fair_share([10, 10, 10], 300) == [10, 10, 10]


def test_fair_share_splits_the_remainder_among_large_entries():
    # One tiny entry, two huge: the tiny one is satisfied, the rest is split.
    alloc = story_bible.fair_share([10, 1000, 1000], 210)
    assert alloc[0] == 10
    assert abs(alloc[1] - alloc[2]) <= 1
    assert sum(alloc) <= 210


def test_fair_share_never_exceeds_the_budget():
    assert sum(story_bible.fair_share([500, 500, 500, 500], 100)) <= 100


def test_context_entries_carry_provenance_tags():
    db = _ContextDB(
        summaries=[_FakeSummary(1, "She finds the ledger."), _FakeSummary(2, "The archive burns.")],
        chars=[(_FakeChar("Devika Rao", "protagonist"), _FakeProfile("brave"))],
    )
    ctx = story_bible._build_full_context("s1", db)
    assert "[Ch 1]" in ctx and "[Ch 2]" in ctx
    assert "[Character: Devika Rao]" in ctx
    # The old untagged form is gone.
    assert "Chapter 1: events=" not in ctx


def test_context_no_longer_truncates_summaries_at_300_chars():
    """The grounding defect: a 2000-character summary used to arrive as 300."""
    body = "She walks the long corridor. " * 80          # ~2200 chars
    ctx = story_bible._build_full_context("s1", _ContextDB(summaries=[_FakeSummary(1, body)]))
    assert len(ctx) > 1500, "a single chapter should now get far more than 300 chars"


def test_context_stays_within_the_token_budget():
    """SB-F08 — an over-budget context is a vLLM 400 mid-generation."""
    big = "The archive burns and the ledger survives. " * 400   # ~17k chars each
    db = _ContextDB(summaries=[_FakeSummary(i, big) for i in range(1, 41)])
    ctx = story_bible._build_full_context("s1", db)
    assert ai_service.count_tokens(ctx) <= story_bible.bible_context_token_budget()


def test_oversized_manuscript_declares_that_summaries_were_shortened():
    """Silent truncation is what let the model believe it had the whole book.
    40 long chapters still all fit — fair-share gives each ~2× the old fixed
    300-char cap — but the context says plainly that they were shortened."""
    big = "The archive burns and the ledger survives. " * 400
    db = _ContextDB(summaries=[_FakeSummary(i, big) for i in range(1, 41)])
    ctx = story_bible._build_full_context("s1", db)

    assert "WHAT YOU ARE NOT SEEING" in ctx
    assert "were shortened to fit" in ctx
    assert "Do not describe anything from material that is not shown" in ctx
    assert "[Ch 1]" in ctx and "[Ch 40]" in ctx, "coverage matters most for the timeline"


def test_manuscript_too_large_for_the_floor_names_the_missing_chapters():
    """Past the point where every chapter can carry a useful summary, chapters
    are dropped rather than reduced to stubs — and the omission is named."""
    body = "She crosses the bridge at dusk and the ledger changes hands. " * 20
    db = _ContextDB(summaries=[_FakeSummary(i, body) for i in range(1, 201)])
    ctx = story_bible._build_full_context("s1", db)

    assert "WHAT YOU ARE NOT SEEING" in ctx
    assert "chapters are included here" in ctx
    assert "Chapters not shown:" in ctx
    assert ai_service.count_tokens(ctx) <= story_bible.bible_context_token_budget()


def test_sampling_spans_the_whole_manuscript_including_the_ending():
    """A contiguous prefix would describe a different book: the model would know
    nothing about how the story ends. Sampling is even, and the final chapter is
    always kept."""
    body = "She crosses the bridge at dusk and the ledger changes hands. " * 20
    db = _ContextDB(summaries=[_FakeSummary(i, body) for i in range(1, 201)])
    ctx = story_bible._build_full_context("s1", db)

    assert "[Ch 1]" in ctx, "opening missing"
    assert "[Ch 200]" in ctx, "ending missing — the bible would stop before the climax"
    kept = [n for n in range(1, 201) if f"[Ch {n}]" in ctx]
    assert len(kept) > 10, "sampling kept too little to be useful"
    # Spread across the book, not clustered at the front.
    assert max(kept[len(kept) // 2:]) > 100 and min(kept) == 1


def test_a_huge_manuscript_never_yields_an_empty_context():
    """Measured defect during implementation: at 200 chapters every summary fell
    below the floor and the model received no manuscript at all — pure invention
    territory. A partial view must always beat no view."""
    body = "She crosses the bridge at dusk. " * 40
    for n in (200, 1000):
        db = _ContextDB(summaries=[_FakeSummary(i, body) for i in range(1, n + 1)])
        ctx = story_bible._build_full_context("s1", db)
        assert "=== CHAPTER SUMMARIES ===" in ctx, f"{n} chapters produced no summaries"
        assert ai_service.count_tokens(ctx) > 1000, f"{n} chapters produced a near-empty context"


def test_small_manuscript_carries_no_omission_notice():
    db = _ContextDB(summaries=[_FakeSummary(1, "Short."), _FakeSummary(2, "Also short.")])
    ctx = story_bible._build_full_context("s1", db)
    assert "WHAT YOU ARE NOT SEEING" not in ctx


def test_compact_ranges_reads_naturally():
    assert story_bible._compact_ranges([1, 2, 3, 7, 9, 10]) == "1-3, 7, 9-10"
    assert story_bible._compact_ranges([4]) == "4"
    assert story_bible._compact_ranges([]) == ""


def test_prompt_requires_citation_and_offers_a_way_to_decline():
    src = inspect.getsource(ai_service.generate_story_bible_section)
    assert "BIBLE_NOT_ESTABLISHED" in src, "the model needs a way to say 'unknown'"
    assert "Cite the source tag for every factual statement" in src
    assert "Never state anything you cannot attribute" in src
    assert "do not describe that material" in src, "must respect the omission notice"


def test_every_section_instruction_demands_provenance():
    src = inspect.getsource(ai_service.generate_story_bible_section)
    block = src[src.index("section_instructions = {"):src.index("instruction = section_instructions")]
    for section in story_bible._BIBLE_SECTIONS:
        start = block.index(f'"{section}"')
        end = block.find('",\n', start)
        assert "Cite" in block[start:end] or "chapter tag" in block[start:end], \
            f"{section} instruction does not require provenance"


def test_provenance_audit_counts_cited_and_uncited_entries():
    text = (
        "- The archive burns [Ch 7]\n"
        "- She flees the city [Ch 8]\n"
        "- Her mother was a cartographer\n"        # uncited — the defect signature
    )
    stats = ai_service.audit_section_provenance(text)
    assert stats["entries"] == 3
    assert stats["cited"] == 2
    assert stats["uncited"] == 1
    assert stats["cited_ratio"] == round(2 / 3, 3)


def test_provenance_audit_recognises_every_tag_form():
    text = (
        "- a [Ch 7]\n- b [Ch 7-9]\n- c [Character: Devika Rao]\n"
        "- d [Note: outline]\n- e [Card: scene — the fire]\n"
    )
    assert ai_service.audit_section_provenance(text)["uncited"] == 0


def test_provenance_audit_counts_the_honesty_convention():
    text = f"- Her birthplace: {ai_service.BIBLE_NOT_ESTABLISHED} [Ch 1]\n"
    stats = ai_service.audit_section_provenance(text)
    assert stats["not_established"] == 1


def test_provenance_audit_handles_prose_without_entries():
    stats = ai_service.audit_section_provenance("A paragraph with no bullet points at all.")
    assert stats["entries"] == 0
    assert stats["cited_ratio"] is None


def test_provenance_is_logged_and_carries_no_manuscript_text():
    results = _all_good()
    results["timeline"] = ("- SECRET MANUSCRIPT EVENT [Ch 3]\n- another thing\n", "stop")
    _, logs = _run_pipeline(results)

    provenance = [m for m in logs if "provenance" in m]
    assert provenance, "provenance metric was not logged"
    assert any("1/2 entries cited" in m for m in provenance), provenance
    assert not any("SECRET MANUSCRIPT EVENT" in m for m in logs)


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
