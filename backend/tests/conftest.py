"""
Session-start safety guard: refuse to run this suite against any database
that is not positively identified as a disposable test database.

See db_safety_guard.py for the policy and why it exists. This file only
wires that policy into pytest's earliest hook (`pytest_configure`), which
runs before collection and before any fixture — including every DB-touching
fixture in this suite — so a misconfigured DATABASE_URL is caught before a
single row is read or written.
"""
import sys
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _TESTS_DIR.parent
sys.path.insert(0, str(_TESTS_DIR))     # for db_safety_guard (sibling module)
sys.path.insert(0, str(_BACKEND_DIR))   # for `database`, matching every test file's own convention

from db_safety_guard import allowed_test_dbs, is_allowed_test_db_name, refusal_message  # noqa: E402


def pytest_configure(config) -> None:
    from database import engine  # imported here, not at module scope, so this guard

    # engine.url.database is SQLAlchemy's already-parsed bare database name —
    # this NEVER includes the username or password, unlike str(DATABASE_URL).
    db_name = engine.url.database
    allowed = allowed_test_dbs()

    if not is_allowed_test_db_name(db_name, allowed):
        import pytest
        pytest.exit(refusal_message(db_name, allowed), returncode=1)

    print(f"[conftest] DB safety guard: running against allow-listed test database {db_name!r}")
