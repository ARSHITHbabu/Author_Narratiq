"""Story Bible generation status — story_bibles.status

Adds a generation-lifecycle column (running | completed | failed) so the UI can
show in-progress / failed / completed states and survive reloads & navigation.
Existing rows default to 'completed' (they are already-generated bibles).

Revision ID: 0015
Revises: 0014
Create Date: 2026-06-13
"""
from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
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
    if _table_exists(bind, "story_bibles") and not _column_exists(bind, "story_bibles", "status"):
        op.add_column(
            "story_bibles",
            sa.Column("status", sa.String(), nullable=False, server_default="completed"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _column_exists(bind, "story_bibles", "status"):
        op.drop_column("story_bibles", "status")
