"""Global Activity Timeline — activity_events

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
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
    if not _table_exists(bind, "activity_events"):
        op.create_table(
            "activity_events",
            sa.Column("event_id",      sa.String(), primary_key=True),
            sa.Column("story_id",      sa.String(), sa.ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id",       sa.String(), sa.ForeignKey("users.user_id"), nullable=False),
            sa.Column("category",      sa.String(20), nullable=False),
            sa.Column("type",          sa.String(60), nullable=False),
            sa.Column("title",         sa.String(), nullable=True, server_default=""),
            sa.Column("summary",       sa.Text(),   nullable=True, server_default=""),
            sa.Column("ref_type",      sa.String(40), nullable=True, server_default=""),
            sa.Column("ref_id",        sa.String(), nullable=True, server_default=""),
            sa.Column("metadata_json", sa.JSON(),   nullable=True),
            sa.Column("created_at",    sa.DateTime(), nullable=True),
        )
    if not _index_exists(bind, "activity_events", "ix_activity_events_story_id"):
        op.create_index("ix_activity_events_story_id", "activity_events", ["story_id"])
    if not _index_exists(bind, "activity_events", "ix_activity_events_user_id"):
        op.create_index("ix_activity_events_user_id", "activity_events", ["user_id"])
    if not _index_exists(bind, "activity_events", "ix_activity_events_created_at"):
        op.create_index("ix_activity_events_created_at", "activity_events", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "activity_events"):
        op.drop_table("activity_events")
