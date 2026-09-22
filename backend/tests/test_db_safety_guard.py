"""
Tests for the database-isolation safety guard (db_safety_guard.py, conftest.py).

Added 2026-09-22 alongside the guard itself — see
docs/incidents/2026-09-22-database-row-count-discrepancy.md for why this
exists. These tests must prove, not just assert, that a shared/production-
looking database configuration is rejected — including one real subprocess-
level end-to-end check (test_conftest_rejects_production_looking_database)
that actually spawns pytest with a bad DATABASE_URL and confirms it aborts
before running anything.

Run: cd backend && pytest tests/test_db_safety_guard.py -q
"""
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db_safety_guard import (  # noqa: E402
    allowed_test_dbs, is_allowed_test_db_name, parse_extra_allowed, refusal_message,
    BUILTIN_ALLOWED_TEST_DBS,
)


# ── Pure policy logic ───────────────────────────────────────────────────────

def test_builtin_allowed_names_are_exactly_the_two_project_test_databases():
    assert BUILTIN_ALLOWED_TEST_DBS == {"narratiq_test", "narratiq_ci_verify"}


def test_builtin_test_db_name_is_allowed():
    assert is_allowed_test_db_name("narratiq_test", allowed_test_dbs({})) is True


def test_production_database_name_is_rejected():
    assert is_allowed_test_db_name("narratiq", allowed_test_dbs({})) is False


def test_empty_or_none_database_name_is_rejected():
    allowed = allowed_test_dbs({})
    assert is_allowed_test_db_name("", allowed) is False
    assert is_allowed_test_db_name(None, allowed) is False


def test_near_miss_name_is_rejected_not_approximately_matched():
    """A positive allow-list must reject a name that merely LOOKS like a test
    database — e.g. a hypothetical backup/staging copy of production named to
    resemble the allow-listed name. Prefix/substring matching would wrongly
    accept this; exact matching correctly refuses it."""
    allowed = allowed_test_dbs({})
    assert is_allowed_test_db_name("narratiq_test_backup_of_prod", allowed) is False
    assert is_allowed_test_db_name("narratiq_test2", allowed) is False
    assert is_allowed_test_db_name("my_narratiq_test", allowed) is False


def test_extra_allowed_dbs_env_var_extends_the_allowlist_additively():
    allowed = allowed_test_dbs({"NARRATIQ_EXTRA_TEST_DBS": "my_dev_test_db, another_one"})
    assert is_allowed_test_db_name("my_dev_test_db", allowed)
    assert is_allowed_test_db_name("another_one", allowed)
    # The built-ins are still present — this is additive, not a replacement.
    assert is_allowed_test_db_name("narratiq_test", allowed)
    # Still rejects anything not explicitly listed.
    assert not is_allowed_test_db_name("narratiq", allowed)


def test_extra_allowed_dbs_env_var_handles_empty_and_malformed_input():
    assert parse_extra_allowed(None) == frozenset()
    assert parse_extra_allowed("") == frozenset()
    assert parse_extra_allowed("  ,  ,") == frozenset()
    assert parse_extra_allowed("a,,b") == {"a", "b"}


def test_refusal_message_names_the_resolved_db_and_never_contains_a_password():
    msg = refusal_message("narratiq", allowed_test_dbs({}))
    assert "narratiq" in msg
    assert "REFUSING TO RUN" in msg
    # This guard is only ever given the already-parsed bare database name
    # (never a connection string), so there is structurally nothing resembling
    # a credential to leak — this pins that contract at the message layer too.
    for leaked in ("://", "@", "password", "narratiq:narratiq"):
        assert leaked not in msg


# ── Real end-to-end proof: a bad DATABASE_URL actually aborts pytest ───────

def test_conftest_rejects_production_looking_database():
    """Spawns a real, separate pytest process pointed at a database named
    exactly like production ('narratiq') and proves the session is refused
    before any test runs — not just that the policy function returns False.

    Uses an unreachable host, not localhost: the guard only parses the URL
    string (engine.url.database) and never connects, so this proves the
    guard rejects on name alone, with no real database required or contacted.
    """
    env = dict(os.environ)
    env["DATABASE_URL"] = "postgresql+psycopg2://x:x@narratiq-guard-test-unreachable-host/narratiq"
    env.pop("NARRATIQ_EXTRA_TEST_DBS", None)

    backend_dir = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_generation_limits.py", "-q"],
        cwd=str(backend_dir),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode != 0, (
        f"expected pytest to abort on a production-looking DATABASE_URL, "
        f"got exit code {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    combined = result.stdout + result.stderr
    assert "REFUSING TO RUN" in combined
    assert "'narratiq'" in combined
    # The credential ("x:x") must never appear in captured output.
    assert "x:x@" not in combined


def test_conftest_accepts_the_allowlisted_test_database_name():
    """Symmetric positive check: a URL whose database name IS allow-listed
    passes the guard and proceeds to normal collection (still an unreachable
    host, so the test run itself will fail once it needs a real connection —
    this only proves the GUARD let it through, not that the DB is reachable).
    """
    env = dict(os.environ)
    env["DATABASE_URL"] = "postgresql+psycopg2://x:x@narratiq-guard-test-unreachable-host/narratiq_test"

    backend_dir = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_generation_limits.py", "-q"],
        cwd=str(backend_dir),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    combined = result.stdout + result.stderr
    assert "REFUSING TO RUN" not in combined
    assert "DB safety guard: running against allow-listed test database 'narratiq_test'" in combined
