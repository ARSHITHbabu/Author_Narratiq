"""Story preservation settings — story_preservation_settings table

Stage 5 task 5.3 (see the architecture comparison in the approved Stage 5
design doc): author-defined AI-transform preservation rules and the
translation name-consistency glossary (task 5.11), both as one small 1:1
companion table to `stories` — the same shape already chosen for
`genre_profiles`/`story_intakes`, not a many-row relational table, because a
preservation "rule set" is a handful of toggles plus one note per story, not
a variable-length collection.

Purely additive: a new table with no FK-breaking implications and no
backfill requirement. Every existing story simply has no row until an
author edits their preservation settings or a translation runs for the
first time — absent-row behaviour is defined in application code
(services/ai_service.py's preservation-clause builder) to match exactly
what every transform already implicitly tried to do before Stage 5
(preserve character names, preserve tone), so no story's behaviour changes
by the mere existence of this table.

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-21
"""
from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def _table_exists(bind, name: str) -> bool:
    return sa.inspect(bind).has_table(name)


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "story_preservation_settings"):
        op.create_table(
            "story_preservation_settings",
            sa.Column("setting_id", sa.String(), primary_key=True),
            sa.Column("story_id", sa.String(), sa.ForeignKey("stories.story_id"), nullable=False, unique=True),
            sa.Column("preserve_character_names", sa.Boolean(), server_default=sa.true()),
            sa.Column("preserve_tone", sa.Boolean(), server_default=sa.true()),
            sa.Column("author_notes", sa.Text(), server_default=""),
            sa.Column("translation_glossary", sa.JSON(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "story_preservation_settings"):
        op.drop_table("story_preservation_settings")
