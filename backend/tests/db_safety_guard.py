"""
Positive-allow-list test-database identification, used by conftest.py's
session-start guard.

Added 2026-09-22 after an incident where the full backend suite was run
against the shared development database, producing a misleading transient
row-count change while unrelated investigation was in progress (see
docs/incidents/2026-09-22-database-row-count-discrepancy.md). No real data
was lost in that incident — the fixture responsible cleans up correctly on
its own — but the suite must never again be ABLE to run against a database
holding real author data, even by mistake.

Policy (positive allow-list, never a blocklist): a database is safe to run
tests against only if its name is *explicitly* recognised — either built in
here, or added via the NARRATIQ_EXTRA_TEST_DBS env var. Anything else —
including the production name itself, an empty value, or a name that merely
*looks* test-like — is rejected. Ambiguous means unsafe, not safe-by-default.

This module never touches DATABASE_URL's credentials — callers pass in only
the already-parsed database *name* (e.g. from SQLAlchemy's `engine.url.database`,
which never includes the password), so a credential can never reach a log
line or an assertion message anywhere in this file or its tests.
"""
import os

# The only two names trusted out of the box. Both are created and destroyed
# only by this project's own tooling (backend/scripts/seed_fixture.py and the
# migration-verification steps in Stage 6), never by hand against real data.
BUILTIN_ALLOWED_TEST_DBS = frozenset({"narratiq_test", "narratiq_ci_verify"})

EXTRA_TEST_DBS_ENV_VAR = "NARRATIQ_EXTRA_TEST_DBS"


def parse_extra_allowed(raw: str | None) -> frozenset[str]:
    """Comma-separated env var value -> a set of extra allowed exact names. Never raises."""
    if not raw:
        return frozenset()
    return frozenset(n.strip() for n in raw.split(",") if n.strip())


def allowed_test_dbs(env: dict | None = None) -> frozenset[str]:
    env = os.environ if env is None else env
    return BUILTIN_ALLOWED_TEST_DBS | parse_extra_allowed(env.get(EXTRA_TEST_DBS_ENV_VAR))


def is_allowed_test_db_name(name: str | None, allowed: frozenset[str]) -> bool:
    """Exact match only. No prefix/substring/regex matching — an approximate
    match ('narratiq_test_backup_of_prod' vs 'narratiq_test') is exactly the
    kind of near-miss a positive allow-list exists to refuse, not accept."""
    return bool(name) and name in allowed


def refusal_message(db_name: str | None, allowed: frozenset[str]) -> str:
    """Never includes credentials — db_name must already be the bare database
    name (e.g. engine.url.database), never a full connection string."""
    return (
        "\n"
        "REFUSING TO RUN: the configured database is not on the test-database allow-list.\n"
        f"  Resolved database name: {db_name!r}\n"
        f"  Allow-listed names:     {sorted(allowed)!r}\n"
        "\n"
        "This suite creates and deletes rows as part of normal test execution, and must\n"
        "never run against a database holding real author data. To run tests locally,\n"
        "point DATABASE_URL at an isolated database whose name is on the allow-list above\n"
        "(e.g. 'narratiq_test'), or add its exact name to the NARRATIQ_EXTRA_TEST_DBS\n"
        "environment variable (comma-separated).\n"
        "\n"
        "See docs/incidents/2026-09-22-database-row-count-discrepancy.md for why this exists.\n"
    )
