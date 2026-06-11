"""Phase 2 — story_bibles table

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
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

    if not _table_exists(bind, "story_bibles"):
        op.create_table(
            "story_bibles",
            sa.Column("bible_id",     sa.String(),  primary_key=True),
            sa.Column("story_id",     sa.String(),  sa.ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id",      sa.String(),  sa.ForeignKey("users.user_id"),    nullable=False),
            sa.Column("title",        sa.String(),  nullable=True,  server_default="Story Bible"),
            sa.Column("content_json", sa.Text(),    nullable=False, server_default="{}"),
            sa.Column("version",      sa.Integer(), nullable=True,  server_default="1"),
            sa.Column("created_at",   sa.DateTime(), nullable=True),
            sa.Column("updated_at",   sa.DateTime(), nullable=True),
        )

    if not _index_exists(bind, "story_bibles", "ix_story_bibles_story_id"):
        op.create_index("ix_story_bibles_story_id", "story_bibles", ["story_id"])
    if not _index_exists(bind, "story_bibles", "ix_story_bibles_user_id"):
        op.create_index("ix_story_bibles_user_id",  "story_bibles", ["user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if _index_exists(bind, "story_bibles", "ix_story_bibles_user_id"):
        op.drop_index("ix_story_bibles_user_id",  table_name="story_bibles")
    if _index_exists(bind, "story_bibles", "ix_story_bibles_story_id"):
        op.drop_index("ix_story_bibles_story_id", table_name="story_bibles")
    if _table_exists(bind, "story_bibles"):
        op.drop_table("story_bibles")
