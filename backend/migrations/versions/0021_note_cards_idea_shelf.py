"""Phase 3 — Idea Shelf columns on note_cards

Stage 7 task 7.11 (Phase 3 spec §13.3, §27.2, P3-09). The Idea Shelf is NOT a
new table: it extends note_cards (anti-pattern 7.3.1 — no second notes-like
entity). Four nullable columns, two indexes:

  target_chapter_id  FK chapters ON DELETE SET NULL — "this idea belongs in ch. 12"
  tags               JSON list of free-form author tags
  status             'open' | 'used' | 'archived', default 'open'
  source_pin_id      provenance back to a pin — deliberately NOT an enforced FK,
                     so an expiring pin can never cascade-delete a permanent idea

Existing cards read as open, untagged and unassigned with zero backfill.
retrieve_note_context() is unaffected (it reads title/content/embedding only).

Downgrade drops only these four columns and two indexes: every idea card
SURVIVES a rollback as an ordinary note card (spec §36.3) — permanent data is
never lost on rollback.

Revision ID: 0021
Revises: 0020
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

TABLE = "note_cards"
FK_NAME = "fk_note_cards_target_chapter_id"


def _column_exists(bind, column: str) -> bool:
    return any(c["name"] == column for c in sa.inspect(bind).get_columns(TABLE))


def _index_exists(bind, index: str) -> bool:
    return any(i["name"] == index for i in sa.inspect(bind).get_indexes(TABLE))


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(TABLE):
        return
    if not _column_exists(bind, "target_chapter_id"):
        op.add_column(TABLE, sa.Column("target_chapter_id", sa.String(), nullable=True))
        op.create_foreign_key(FK_NAME, TABLE, "chapters", ["target_chapter_id"], ["chapter_id"], ondelete="SET NULL")
    if not _column_exists(bind, "tags"):
        op.add_column(TABLE, sa.Column("tags", sa.JSON(), nullable=True))
    if not _column_exists(bind, "status"):
        # Constant default: metadata-only on PostgreSQL 11+, no table rewrite.
        op.add_column(TABLE, sa.Column("status", sa.String(), nullable=True, server_default="open"))
    if not _column_exists(bind, "source_pin_id"):
        op.add_column(TABLE, sa.Column("source_pin_id", sa.String(), nullable=True))
    if not _index_exists(bind, "ix_note_cards_target_chapter"):
        op.create_index("ix_note_cards_target_chapter", TABLE, ["target_chapter_id"])
    if not _index_exists(bind, "ix_note_cards_type_status"):
        op.create_index("ix_note_cards_type_status", TABLE, ["story_id", "card_type", "status"])


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(TABLE):
        return
    for index in ("ix_note_cards_type_status", "ix_note_cards_target_chapter"):
        if _index_exists(bind, index):
            op.drop_index(index, table_name=TABLE)
    # Dropping the column drops whatever FK constraint references it, whether
    # it was named by this migration or auto-named by create_all().
    for col in ("source_pin_id", "status", "tags", "target_chapter_id"):
        if _column_exists(bind, col):
            op.drop_column(TABLE, col)
