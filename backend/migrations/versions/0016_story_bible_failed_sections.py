"""Story Bible failed sections — story_bibles.failed_sections

Records which sections did not produce genuine content on the last generation
run, so the UI can offer targeted regeneration instead of rebuilding the whole
bible. Shape: [{"section": ..., "failure": ..., "reason": ...}] — author-facing
fields only; exception detail stays in the logs.

Companion to 0015 (status). Together they make a 'partial' bible actionable:
0015 says the bible is incomplete, this says which parts and why.

Existing rows read as NULL and are coerced to [] by the response schema, so no
backfill is required.

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-25
"""
from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
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
    if _table_exists(bind, "story_bibles") and not _column_exists(bind, "story_bibles", "failed_sections"):
        op.add_column(
            "story_bibles",
            sa.Column("failed_sections", sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _column_exists(bind, "story_bibles", "failed_sections"):
        op.drop_column("story_bibles", "failed_sections")
