"""
Stage 7 task 7.14 — Phase 3 product rules R1–R10 (spec §4, §46 item 2).

R1 and R6 are verified by BEHAVIOURAL tests (the spec requires test, not
inspection): R1 in test_generation_context.py::test_r1_regenerating_without_
pinning_writes_no_rows (+ the schema check below), R6 in
test_phase3_preservation.py::test_r6_* (100 randomised adversarial runs).
This file adds the static/structural checks for the remaining rules, so each
rule has an executable verification method.

    pytest backend/tests/test_phase3_rules.py -q
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent


def _src(rel: str) -> str:
    return (BACKEND / rel).read_text()


def _all_backend_py() -> dict[str, str]:
    return {str(p.relative_to(BACKEND)): p.read_text()
            for p in BACKEND.rglob("*.py") if "tests" not in p.parts and "migrations" not in p.parts}


def test_r1_no_table_stores_unpinned_generations_or_rejections():
    """R1/R5 — schema review: no generation-history, rejected-idea or
    avoid-set table exists. (Row-level R1 is the behavioural test.)"""
    import models
    tables = set(models.Base.metadata.tables)
    for forbidden in ("ai_generations", "rejected_ideas", "avoid_sets", "generation_history", "session_generations"):
        assert forbidden not in tables
    assert "ai_generation_pins" in tables


def test_r2_pin_expiry_is_non_null():
    import models
    assert models.AiGenerationPin.__table__.c.expires_at.nullable is False


def test_r3_applying_never_extends_or_copies_a_pin():
    src = _src("routers/ai_workspace.py")
    applied = src[src.index("def mark_pin_applied"):src.index("@router.post(\"/{story_id}/ai/pins/{pin_id}/promote\"")]
    assert "expires_at" not in applied and "content" not in applied.replace("applied_at", "")


def test_r4_pins_are_separate_from_the_idea_shelf_and_from_rag():
    """R4 — promotion is the only pin→card copy; no retriever reads pins."""
    for path, src in _all_backend_py().items():
        if "ai_generation_pins" in src and path not in (
            "models.py", "main.py", "services/similarity.py", "services/ownership.py", "services/pin_store.py",
            "routers/ai_workspace.py", "routers/ai_transform.py",
        ):
            raise AssertionError(f"unexpected reader of ai_generation_pins: {path}")
    rag = _src("services/ai_service.py")
    assert "ai_generation_pins" not in rag and "AiGenerationPin" not in rag


def test_r5_avoid_set_is_never_persisted():
    import models
    ctx = _src("services/generation_context.py")
    assert "db.add(" not in ctx
    for table in models.Base.metadata.tables.values():
        for col in table.columns:
            assert "avoid" not in col.name and "reject" not in col.name, (table.name, col.name)


def test_r7_single_context_composition_point():
    """R7 / §46 item 9 — Phase 3 prompt sections are only assembled in
    services/generation_context.py."""
    markers = ("PRIOR IDEAS", "ALREADY EXPLORED", "AUTHOR VOICE", "TASK MODIFIER")
    for path, src in _all_backend_py().items():
        for m in markers:
            if m in src:
                assert path == "services/generation_context.py", (path, m)


def test_r8_limits_are_configuration():
    from config import settings
    for key in ("plan_limits_json", "pin_cleanup_batch_size", "max_total_pin_age_days",
                "generation_context_token_budget", "similarity_lexical_hi"):
        assert hasattr(settings, key)


def test_r8_every_new_setting_is_in_env_example():
    """§46 item 8 — extra='forbid': every Phase 3 field must be documented."""
    env = (REPO / ".env.example").read_text()
    phase3 = _src("config.py")
    block = phase3[phase3.index("Phase 3 — generation management"):phase3.index("── JWT settings")]
    fields = re.findall(r"^\s{4}(\w+)\s*:", block, re.M)
    assert len(fields) >= 29
    for f in fields:
        assert f"# {f.upper()}=" in env, f


def test_r9_expiry_sweep_is_inside_the_existing_hourly_loop():
    main = _src("main.py")
    loop = main[main.index("async def _run_periodic_cleanup"):main.index("@asynccontextmanager")]
    assert loop.count("_cleanup_expired_pins()") == 2          # startup + hourly


def test_r10_no_new_infrastructure_dependency():
    reqs = (BACKEND / "requirements.txt").read_text().lower()
    for dep in ("redis", "boto3", "celery", "minio", "rq=="):
        assert dep not in reqs
    pkg = (REPO / "frontend" / "package.json").read_text()
    for dep in ('"diff"', "jsdiff", "diff-match-patch", "redis"):
        assert dep not in pkg


def test_46_item10_pin_content_only_through_pin_store():
    """No code outside PinContentStore touches a pin's `.content` attribute,
    and no raw SQL anywhere selects/filters ai_generation_pins.content."""
    for path, src in _all_backend_py().items():
        if path in ("services/pin_store.py", "models.py"):
            continue
        assert not re.search(r"\b(?:pin|base|oldest|base_pin|parent)\.content\b(?!_)", src), path
        for sql in re.findall(r'"""(.*?)"""', src, re.S):
            if "ai_generation_pins" in sql:
                cleaned = sql.replace("content_bytes", "").replace("content_sha256", "").replace("content_uri", "")
                assert not re.search(r"\bcontent\b", cleaned), (path, sql[:120])


def test_no_generation_content_in_log_lines():
    """Cross-cutting: Phase 3 modules log ids, sizes and counts — never text."""
    for rel in ("routers/ai_workspace.py", "services/generation_context.py", "services/similarity.py",
                "services/consistency.py", "services/version_tools.py", "services/pin_store.py"):
        for line in _src(rel).splitlines():
            if re.search(r"logger\.(info|warning|error|debug)\(", line):
                assert not re.search(r"\b(content|text|source_text|output|summary)\b\s*[,)]", line), (rel, line)
