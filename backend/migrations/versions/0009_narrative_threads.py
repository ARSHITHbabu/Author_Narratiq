"""Phase 2 — narrative_threads table

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def _table_exists(bind, name: str) -> bool:
    return sa.inspect(bind).has_table(name)


def _index_exists(bind, table: str, index: str) -> bool:
    if not _table_exists(bind, table):
        return False
    return any(i["name"] == index for i in sa.inspect(bind).get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind, "narrative_threads"):
        op.create_table(
            "narrative_threads",
            sa.Column("thread_id",          sa.String(),  primary_key=True),
            sa.Column("story_id",           sa.String(),  sa.ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id",            sa.String(),  sa.ForeignKey("users.user_id"),    nullable=False),
            sa.Column("name",               sa.String(),  nullable=False),
            sa.Column("description",        sa.Text(),    nullable=True,  server_default=""),
            sa.Column("introduced_chapter", sa.Integer(), nullable=True),
            sa.Column("resolved_chapter",   sa.Integer(), nullable=True),
            sa.Column("last_seen_chapter",  sa.Integer(), nullable=True),
            sa.Column("status",             sa.String(),  nullable=True,  server_default="open"),
            sa.Column("created_at",         sa.DateTime(), nullable=True),
            sa.Column("updated_at",         sa.DateTime(), nullable=True),
        )

    if not _index_exists(bind, "narrative_threads", "ix_narrative_threads_story_id"):
        op.create_index("ix_narrative_threads_story_id", "narrative_threads", ["story_id"])
    if not _index_exists(bind, "narrative_threads", "ix_narrative_threads_status"):
        op.create_index("ix_narrative_threads_status",   "narrative_threads", ["status"])


def downgrade() -> None:
    bind = op.get_bind()
    if _index_exists(bind, "narrative_threads", "ix_narrative_threads_status"):
        op.drop_index("ix_narrative_threads_status",   table_name="narrative_threads")
    if _index_exists(bind, "narrative_threads", "ix_narrative_threads_story_id"):
        op.drop_index("ix_narrative_threads_story_id", table_name="narrative_threads")
    if _table_exists(bind, "narrative_threads"):
        op.drop_table("narrative_threads")
