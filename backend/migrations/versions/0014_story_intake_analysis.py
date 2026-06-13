"""Story Intake rich analysis snapshot — story_intakes.analysis

Adds a JSON column holding the full detect_genre Story-Intelligence snapshot
(emotional_arc, pacing, narrative_pov, comparable_titles, marketing_category,
secondary_genres, content_warnings, intelligence_notes, writing_direction,
structure, conflict, themes...) so the shared genre-context builder can give AI
tools richer project context. Single column instead of many to avoid churn.

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-13
"""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
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
    if _table_exists(bind, "story_intakes") and not _column_exists(bind, "story_intakes", "analysis"):
        op.add_column("story_intakes", sa.Column("analysis", sa.JSON(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if _column_exists(bind, "story_intakes", "analysis"):
        op.drop_column("story_intakes", "analysis")
