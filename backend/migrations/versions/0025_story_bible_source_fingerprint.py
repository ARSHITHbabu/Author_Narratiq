"""Story Bible source fingerprint — story_bibles.source_fingerprint

Phase 2 §19 P2-06 requires the Story Bible to warn when the manuscript changed
after it was generated ("stale detection"); it was never built (found by the
Stage 11 Phase 2 acceptance, task 11.6). This column stores the hash of the
indexed chapters the bible was generated from (services/source_fingerprint.py,
the same fingerprint the saved Manuscript Report uses since 0023). GET compares
it with the current hash and returns is_stale.

Nullable, no backfill: a bible generated before this migration has no
fingerprint and reads as staleness unknown (no warning) until it is regenerated.
Downgrade drops the column; nothing else depends on it.

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def _table_exists(bind, name: str) -> bool:
    return sa.inspect(bind).has_table(name)


def _column_exists(bind, table: str, column: str) -> bool:
    if not _table_exists(bind, table):
        return False
    return any(c["name"] == column for c in sa.inspect(bind).get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "story_bibles") and not _column_exists(bind, "story_bibles", "source_fingerprint"):
        op.add_column("story_bibles", sa.Column("source_fingerprint", sa.String(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if _column_exists(bind, "story_bibles", "source_fingerprint"):
        op.drop_column("story_bibles", "source_fingerprint")
