"""Phase 3 — per-story AI preferences on story_preservation_settings

Stage 7 task 7.3 / 7.4 (Phase 3 spec §13.2, P3-05, P3-10). The spec proposed
a new `story_ai_preferences` table; Stage 5 had already built
`story_preservation_settings` (0018) for the same purpose. Per conflict
decision C7-2 this migration EXTENDS the existing table instead, so there is
one per-story AI-behaviour row, not two overlapping sources of truth.

Three nullable JSON preference bags, fetched whole by story_id and never
queried by predicate (so no index). NULL/absent keys resolve to server
defaults in services/generation_context — no backfill, and every existing
story behaves exactly as before until an author changes a preference.

Revision ID: 0020
Revises: 0019
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

TABLE = "story_preservation_settings"
COLUMNS = ("preserve_rules", "style_prefs", "pin_prefs")


def _column_exists(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    if not insp.has_table(table):
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    for col in COLUMNS:
        if sa.inspect(bind).has_table(TABLE) and not _column_exists(bind, TABLE, col):
            op.add_column(TABLE, sa.Column(col, sa.JSON(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    for col in reversed(COLUMNS):
        if _column_exists(bind, TABLE, col):
            op.drop_column(TABLE, col)
