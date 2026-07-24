"""
PRE-1 regression guard — retrieval call signatures and context assembly in
routers/writing_tools.py  (no DB, no LLM, no GPU).

Phase 2 Issues 12 (outline) and 13 (continuation) were caused by three defects
in the same two code paths:

  A. Four call sites passed `query=` to retrieve_relevant_chunks() (first
     parameter `question`) and retrieve_character_context() (parameters
     `story_id, question, db`).  Both raised TypeError at runtime, so chapter
     continuation and outline generation were completely non-functional.
  B. retrieve_character_context() returns list[str]; it was handed straight to
     generate_continuations(character_context: str), which interpolates it into
     the prompt — a Python list repr would have reached Qwen.
  C. The retrieved dicts were read with the keys `chapter_number` and `text`,
     which retrieve_relevant_chunks() does not produce (it returns `chapter`
     and `raw_summary`).  `.get()` defaults swallowed both misses, so the
     assembled story context was "[Ch] \n\n[Ch] ..." — no manuscript content at
     all, and no exception.  Fixing A and B without C would have shipped a
     feature that returned confident, fluent, entirely ungrounded prose.

Defect C is the reason these tests assert on prompt *content*, not just on the
absence of a TypeError.  A green "no exception raised" result is exactly what
the broken code produced.

Runs two ways, deliberately — the plain-python path needs no new dependency:

    python3 backend/tests/test_retrieval_signatures.py
    pytest  backend/tests/test_retrieval_signatures.py -q
"""
import asyncio
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from routers import writing_tools
from services import ai_service


# ── Fixtures ──────────────────────────────────────────────────────────────────

STORY_ID   = "story-abc-123"
CHAPTER_ID = "chapter-def-456"

# Shaped exactly like retrieve_relevant_chunks() builds its return value
# (ai_service.py — keys: chapter, raw_summary, key_events, characters,
# locations, score), in descending relevance as the SQL ORDER BY produces.
FAKE_SUMMARIES = [
    {
        "chapter": 3,
        "raw_summary": "Iris confronts Mara Eze in the flooded archive.",
        "key_events": ["confrontation"],
        "characters": ["Iris", "Mara Eze"],
        "locations": ["flooded archive"],
        "score": 0.91,
    },
    {
        "chapter": 1,
        "raw_summary": "Caleb Ferro discovers the ledger beneath the pier.",
        "key_events": ["discovery"],
        "characters": ["Caleb Ferro"],
        "locations": ["pier"],
        "score": 0.77,
    },
]

# Shaped like retrieve_character_context() — pre-formatted prompt blocks.
FAKE_CHAR_BLOCKS = [
    "## Character: Iris\nRole: protagonist | Status: alive",
    "## Character: Mara Eze\nRole: antagonist | Status: alive",
]


class _FakeQuery:
    """Minimal SQLAlchemy Query stand-in: .filter().first() → a fixed object."""

    def __init__(self, result):
        self._result = result

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._result


class _FakeChapter:
    chapter_id = CHAPTER_ID
    story_id = STORY_ID
    chapter_number = 4


class _FakeStory:
    story_id = STORY_ID
    user_id = "user-1"


class _FakeDB:
    def query(self, model):
        # writing_tools looks up Story first, then Chapter.
        name = getattr(model, "__name__", "")
        if name == "Story":
            return _FakeQuery(_FakeStory())
        return _FakeQuery(_FakeChapter())


class _FakeUser:
    user_id = "user-1"


class _Body:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _install_stubs(monkeypatch_like, *, summaries, char_blocks, captured):
    """Patch the two retrievers and both generators onto writing_tools.

    `captured` accumulates exactly what each stub received, so the tests can
    assert on the real arguments and on the final prompt content.
    """

    async def fake_chunks(**kwargs):
        captured["chunks_kwargs"] = kwargs
        return summaries

    async def fake_chars(**kwargs):
        captured["chars_kwargs"] = kwargs
        return char_blocks

    async def fake_continuations(**kwargs):
        captured["continuation_kwargs"] = kwargs
        return [
            {"direction": f"D{i}", "text": f"T{i}", "rationale": f"R{i}"}
            for i in range(3)
        ]

    async def fake_outline(**kwargs):
        captured["outline_kwargs"] = kwargs
        return [
            {
                "scene_number": i + 1,
                "beat_description": f"beat {i + 1}",
                "characters_present": ["Iris"],
                "location": "archive",
                "pacing_note": "tense",
            }
            for i in range(kwargs["scene_count"])
        ]

    monkeypatch_like(writing_tools, "retrieve_relevant_chunks", fake_chunks)
    monkeypatch_like(writing_tools, "retrieve_character_context", fake_chars)
    monkeypatch_like(writing_tools, "generate_continuations", fake_continuations)
    monkeypatch_like(writing_tools, "generate_chapter_outline", fake_outline)
    monkeypatch_like(writing_tools, "_get_genre_context", lambda *a, **k: "GENRE")

    # The @limiter.limit decorator demands a real starlette Request before it
    # will call through.  Disabling the limiter short-circuits that check
    # (slowapi guards it with `if self.enabled:`) so these tests exercise the
    # endpoint body without constructing an ASGI scope.  Rate limiting itself is
    # not under test here; production code is untouched.
    writing_tools.limiter.enabled = False


def _run_continuation(captured, *, summaries=None, char_blocks=None):
    _install_stubs(
        setattr,
        summaries=FAKE_SUMMARIES if summaries is None else summaries,
        char_blocks=FAKE_CHAR_BLOCKS if char_blocks is None else char_blocks,
        captured=captured,
    )
    return asyncio.run(
        writing_tools.generate_chapter_continuation(
            request=None,
            story_id=STORY_ID,
            chapter_id=CHAPTER_ID,
            body=_Body(tail_text="The tide kept rising.", continuation_length=200),
            current_user=_FakeUser(),
            db=_FakeDB(),
        )
    )


def _run_outline(captured, *, summaries=None, char_blocks=None):
    _install_stubs(
        setattr,
        summaries=FAKE_SUMMARIES if summaries is None else summaries,
        char_blocks=FAKE_CHAR_BLOCKS if char_blocks is None else char_blocks,
        captured=captured,
    )
    goal = "Iris must decide whether to open the ledger before the tide reaches the archive floor"
    return asyncio.run(
        writing_tools.generate_outline(
            request=None,
            story_id=STORY_ID,
            chapter_id=CHAPTER_ID,
            body=_Body(chapter_goal=goal, scene_count=4),
            current_user=_FakeUser(),
            db=_FakeDB(),
        )
    )


# ── 1. Signature binding — the TypeError guard (Defect A) ─────────────────────

def test_no_typeerror_binding_actual_call_sites():
    """The exact kwargs writing_tools.py passes must bind to the real signatures.

    bind() raises the identical TypeError the live call would, without executing
    anything — no DB, no BGE-M3, no vLLM.
    """
    inspect.signature(ai_service.retrieve_relevant_chunks).bind(
        question="q", story_id=STORY_ID, db=None, max_chapter_number=4
    )
    inspect.signature(ai_service.retrieve_character_context).bind(
        story_id=STORY_ID, question="q", db=None
    )


def test_query_keyword_is_rejected_by_both_retrievers():
    """Locks the defect itself: `query=` must remain invalid on both functions."""
    for fn, kwargs in (
        (ai_service.retrieve_relevant_chunks, {"query": "q", "story_id": STORY_ID, "db": None}),
        (ai_service.retrieve_character_context, {"query": "q", "story_id": STORY_ID, "db": None}),
    ):
        try:
            inspect.signature(fn).bind(**kwargs)
        except TypeError:
            continue
        raise AssertionError(f"{fn.__name__} unexpectedly accepted query= — signature drifted")


def test_retriever_parameter_names_are_stable():
    """Catches a rename on the ai_service side that would silently re-break callers."""
    chunks_params = list(inspect.signature(ai_service.retrieve_relevant_chunks).parameters)
    chars_params = list(inspect.signature(ai_service.retrieve_character_context).parameters)

    assert chunks_params[:3] == ["question", "story_id", "db"], chunks_params
    assert chars_params[:3] == ["story_id", "question", "db"], chars_params
    assert "query" not in chunks_params
    assert "query" not in chars_params


def test_generators_declare_character_context_as_str():
    """Defect B's contract: both generators take a str, never a list."""
    for fn in (ai_service.generate_continuations, ai_service.generate_chapter_outline):
        annotation = inspect.signature(fn).parameters["character_context"].annotation
        assert annotation is str, f"{fn.__name__}: character_context is {annotation!r}"


# ── 2. Retrieval receives the right question and story id ─────────────────────

def test_continuation_passes_question_and_story_id():
    captured = {}
    _run_continuation(captured)

    assert captured["chunks_kwargs"]["question"] == "The tide kept rising."
    assert captured["chunks_kwargs"]["story_id"] == STORY_ID
    assert captured["chunks_kwargs"]["max_chapter_number"] == 4
    assert "query" not in captured["chunks_kwargs"]

    assert captured["chars_kwargs"]["question"] == "The tide kept rising."
    assert captured["chars_kwargs"]["story_id"] == STORY_ID
    assert "query" not in captured["chars_kwargs"]


def test_outline_passes_question_and_story_id():
    captured = {}
    _run_outline(captured)

    for key in ("chunks_kwargs", "chars_kwargs"):
        assert captured[key]["story_id"] == STORY_ID
        assert "ledger" in captured[key]["question"]
        assert "query" not in captured[key]


# ── 3. Story context carries real summaries (Defect C) ────────────────────────

def test_continuation_story_context_contains_real_summaries():
    captured = {}
    _run_continuation(captured)
    story_context = captured["continuation_kwargs"]["story_context"]

    assert "Iris confronts Mara Eze in the flooded archive." in story_context
    assert "Caleb Ferro discovers the ledger beneath the pier." in story_context
    assert "[Ch3]" in story_context and "[Ch1]" in story_context

    # The exact broken output: a chapter label with no number and no text.
    assert "[Ch] " not in story_context, "regression: chapter_number/text keys are back"


def test_outline_story_context_contains_real_summaries():
    captured = {}
    _run_outline(captured)
    story_context = captured["outline_kwargs"]["story_context"]

    assert "flooded archive" in story_context
    assert "[Ch3]" in story_context
    assert "[Ch] " not in story_context


def test_missing_mandatory_key_raises_instead_of_degrading_silently():
    """Direct indexing is deliberate: an interface change must fail loudly.

    Under the old `.get()` form this returned 200 with an empty prompt.
    """
    captured = {}
    broken = [{"chapter_number": 3, "text": "wrong key names"}]
    try:
        _run_continuation(captured, summaries=broken)
    except KeyError:
        return
    raise AssertionError("mandatory key access silently degraded instead of raising KeyError")


# ── 4. Character context reaches generation as plain text (Defect B) ──────────

def test_character_context_is_joined_plain_text():
    captured = {}
    _run_continuation(captured)
    char_context = captured["continuation_kwargs"]["character_context"]

    assert isinstance(char_context, str), type(char_context)
    assert char_context == "\n\n".join(FAKE_CHAR_BLOCKS)
    assert "## Character: Iris" in char_context
    assert "## Character: Mara Eze" in char_context

    # List-repr artefacts that would appear if the list were interpolated raw.
    for artefact in ("['", "']", "\\n", "', '"):
        assert artefact not in char_context, f"list repr leaked into prompt: {artefact!r}"


def test_outline_character_context_is_joined_plain_text():
    captured = {}
    _run_outline(captured)
    char_context = captured["outline_kwargs"]["character_context"]

    assert isinstance(char_context, str)
    assert "## Character: Iris" in char_context
    assert "['" not in char_context


# ── 5. Empty retrieval degrades cleanly, never crashes ────────────────────────

def test_continuation_survives_empty_story_and_character_retrieval():
    """A story with no embedded summaries and no characters must still answer."""
    captured = {}
    result = _run_continuation(captured, summaries=[], char_blocks=[])

    assert captured["continuation_kwargs"]["story_context"] == ""
    assert captured["continuation_kwargs"]["character_context"] == ""
    assert len(result.suggestions) == 3


def test_outline_survives_empty_story_and_character_retrieval():
    captured = {}
    result = _run_outline(captured, summaries=[], char_blocks=[])

    assert captured["outline_kwargs"]["story_context"] == ""
    assert captured["outline_kwargs"]["character_context"] == ""
    assert len(result.outline) == 4


def test_empty_character_context_only():
    """Story context present, no characters — the common early-manuscript case."""
    captured = {}
    _run_continuation(captured, char_blocks=[])

    assert captured["continuation_kwargs"]["character_context"] == ""
    assert "Iris confronts" in captured["continuation_kwargs"]["story_context"]


# ── 6. Issues 12 and 13 — both endpoints produce their payloads ───────────────

def test_issue_13_continuation_returns_three_suggestions():
    captured = {}
    result = _run_continuation(captured)

    assert len(result.suggestions) == 3
    assert result.chapter_id == CHAPTER_ID
    # Real generated content, not the "Could not generate this suggestion" padding.
    assert all(s.text for s in result.suggestions)
    assert all("Could not generate" not in s.rationale for s in result.suggestions)


def test_issue_12_outline_returns_beat_sheet():
    captured = {}
    result = _run_outline(captured)

    assert len(result.outline) == 4
    assert result.chapter_id == CHAPTER_ID
    assert [b.scene_number for b in result.outline] == [1, 2, 3, 4]
    assert all(b.beat_description for b in result.outline)


# ── 7. Retrieval ordering assumption ──────────────────────────────────────────

def test_story_context_preserves_retrieval_order():
    """Context must be assembled in the retriever's order, not re-sorted.

    retrieve_relevant_chunks() ends its SQL with
        ORDER BY embedding <=> CAST(:q AS vector)  LIMIT :limit
    i.e. ascending cosine distance — most relevant first — so relevance order is
    guaranteed by the database, not by the caller.

    Documented limitation: there is no secondary sort key, so the relative order
    of rows with *identical* distances is undefined by PostgreSQL.  Exact ties
    are vanishingly rare with 1024-dim float embeddings and, being equally
    relevant by definition, harmless when they occur.  The caller must not
    reorder, and takes the first 4 as the most relevant 4.
    """
    captured = {}
    _run_continuation(captured)
    story_context = captured["continuation_kwargs"]["story_context"]

    # FAKE_SUMMARIES is ordered by descending score (0.91 then 0.77).
    assert story_context.index("[Ch3]") < story_context.index("[Ch1]")


def test_story_context_caps_at_four_summaries():
    captured = {}
    many = [
        {**FAKE_SUMMARIES[0], "chapter": n, "raw_summary": f"summary {n}"}
        for n in range(1, 8)
    ]
    _run_continuation(captured, summaries=many)
    story_context = captured["continuation_kwargs"]["story_context"]

    assert story_context.count("[Ch") == 4
    assert "summary 5" not in story_context


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
