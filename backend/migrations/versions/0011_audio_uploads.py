"""Phase 2 — audio_uploads table

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
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

    if not _table_exists(bind, "audio_uploads"):
        op.create_table(
            "audio_uploads",
            sa.Column("audio_id",          sa.String(),     primary_key=True),
            sa.Column("story_id",          sa.String(),     sa.ForeignKey("stories.story_id",   ondelete="CASCADE"),  nullable=False),
            sa.Column("user_id",           sa.String(),     sa.ForeignKey("users.user_id"),      nullable=False),
            sa.Column("note_id",           sa.String(),     sa.ForeignKey("story_notes.note_id", ondelete="SET NULL"), nullable=True),
            sa.Column("audio_path",        sa.Text(),       nullable=True),
            sa.Column("raw_transcript",    sa.Text(),       nullable=True,  server_default=""),
            sa.Column("cleaned_text",      sa.Text(),       nullable=True,  server_default=""),
            sa.Column("language_detected", sa.String(10),   nullable=True,  server_default=""),
            sa.Column("duration_seconds",  sa.Float(),      nullable=True,  server_default="0"),
            sa.Column("confidence",        sa.Float(),      nullable=True,  server_default="0"),
            sa.Column("word_count",        sa.Integer(),    nullable=True,  server_default="0"),
            sa.Column("status",            sa.String(20),   nullable=True,  server_default="processing"),
            sa.Column("confirmed",         sa.Boolean(),    nullable=True,  server_default="false"),
            sa.Column("created_at",        sa.DateTime(),   nullable=True),
            sa.Column("updated_at",        sa.DateTime(),   nullable=True),
        )

    if not _index_exists(bind, "audio_uploads", "ix_audio_uploads_story_id"):
        op.create_index("ix_audio_uploads_story_id", "audio_uploads", ["story_id"])
    if not _index_exists(bind, "audio_uploads", "ix_audio_uploads_user_id"):
        op.create_index("ix_audio_uploads_user_id",  "audio_uploads", ["user_id"])
    if not _index_exists(bind, "audio_uploads", "ix_audio_uploads_note_id"):
        op.create_index("ix_audio_uploads_note_id",  "audio_uploads", ["note_id"])


def downgrade() -> None:
    bind = op.get_bind()
    for idx, tbl in [
        ("ix_audio_uploads_note_id",  "audio_uploads"),
        ("ix_audio_uploads_user_id",  "audio_uploads"),
        ("ix_audio_uploads_story_id", "audio_uploads"),
    ]:
        if _index_exists(bind, tbl, idx):
            op.drop_index(idx, table_name=tbl)
    if _table_exists(bind, "audio_uploads"):
        op.drop_table("audio_uploads")
