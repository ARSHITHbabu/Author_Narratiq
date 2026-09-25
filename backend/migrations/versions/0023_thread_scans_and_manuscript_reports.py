"""Stage 5 — narrative_thread_scans + manuscript_reports

Two defects from the author's 2026-09-22 live review (Stage 5 gate note):
  D1  the Narrative Threads scan had no observable outcome, so the panel could
      wait forever; narrative_thread_scans records the latest scan per story.
  D2  the Manuscript Report was never saved; manuscript_reports keeps the
      latest validated report per story.

Both tables are one-row-per-story (UNIQUE(story_id), written by upsert), so
row counts are bounded by the number of stories. Both cascade with the story.
Purely additive: no existing table or row is touched. Guarded like 0011 so it
tolerates start-narratiq.sh having run Base.metadata.create_all() first.

Revision ID: 0023
Revises: 0022
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def _table_exists(bind, name: str) -> bool:
    return sa.inspect(bind).has_table(name)


def upgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind, "narrative_thread_scans"):
        op.create_table(
            "narrative_thread_scans",
            sa.Column("scan_id",          sa.String(),  primary_key=True),
            sa.Column("story_id",         sa.String(),  sa.ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id",          sa.String(),  sa.ForeignKey("users.user_id"), nullable=False),
            sa.Column("status",           sa.String(),  nullable=False),
            sa.Column("threads_written",  sa.Integer(), nullable=True),
            sa.Column("chapters_scanned", sa.Integer(), nullable=True),
            sa.Column("batches_degraded", sa.Integer(), nullable=True),
            sa.Column("error_code",       sa.String(),  nullable=True),
            sa.Column("started_at",       sa.DateTime(), nullable=True),
            sa.Column("finished_at",      sa.DateTime(), nullable=True),
            sa.Column("updated_at",       sa.DateTime(), nullable=True),
            sa.UniqueConstraint("story_id", name="uq_narrative_thread_scans_story_id"),
        )

    if not _table_exists(bind, "manuscript_reports"):
        op.create_table(
            "manuscript_reports",
            sa.Column("report_id",          sa.String(),   primary_key=True),
            sa.Column("story_id",           sa.String(),   sa.ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id",            sa.String(),   sa.ForeignKey("users.user_id"), nullable=False),
            sa.Column("content_json",       sa.Text(),     nullable=False),
            sa.Column("chapters_analyzed",  sa.Integer(),  nullable=True),
            sa.Column("source_fingerprint", sa.String(64), nullable=False),
            sa.Column("degraded",           sa.Boolean(),  nullable=True),
            sa.Column("created_at",         sa.DateTime(), nullable=True),
            sa.Column("updated_at",         sa.DateTime(), nullable=True),
            sa.UniqueConstraint("story_id", name="uq_manuscript_reports_story_id"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    for table in ("manuscript_reports", "narrative_thread_scans"):
        if _table_exists(bind, table):
            op.drop_table(table)
