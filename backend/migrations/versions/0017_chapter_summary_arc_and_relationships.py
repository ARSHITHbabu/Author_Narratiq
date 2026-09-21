"""Chapter summary arc/relationship depth — chapter_summaries.character_arc_notes, .relationship_changes

Stage 4 task 4.5. ChapterSummary already captures key_events, characters_present,
locations, timeline_markers, emotional_tone and chapter_purpose, but has nowhere
to record per-chapter character-arc progression or relationship-state changes —
signal task 4.3's ranking and task 3.3's Story Bible grounding both need and
neither existing field can safely hold without conflating it with an unrelated
concern (e.g. stuffing arc notes into chapter_purpose, a free-text field with an
existing meaning, would break every current reader of that field).

Both new columns are nullable JSON with no default write requirement — existing
rows read as NULL/None and are treated as "no data yet" by callers, so no
backfill is required and no existing behaviour changes until code starts
writing to them.

Shape:
  character_arc_notes:   {"<character_id>": "<progression note>", ...}
  relationship_changes:  [{"characters": [id, id], "change": "..."}]

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-21
"""
from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
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
    if _table_exists(bind, "chapter_summaries"):
        if not _column_exists(bind, "chapter_summaries", "character_arc_notes"):
            op.add_column(
                "chapter_summaries",
                sa.Column("character_arc_notes", sa.JSON(), nullable=True),
            )
        if not _column_exists(bind, "chapter_summaries", "relationship_changes"):
            op.add_column(
                "chapter_summaries",
                sa.Column("relationship_changes", sa.JSON(), nullable=True),
            )


def downgrade() -> None:
    bind = op.get_bind()
    if _column_exists(bind, "chapter_summaries", "relationship_changes"):
        op.drop_column("chapter_summaries", "relationship_changes")
    if _column_exists(bind, "chapter_summaries", "character_arc_notes"):
        op.drop_column("chapter_summaries", "character_arc_notes")
