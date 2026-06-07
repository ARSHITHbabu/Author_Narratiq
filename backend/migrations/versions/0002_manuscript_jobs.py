"""Add manuscript_jobs table for persistent upload job tracking

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-07

Replaces the in-memory _jobs dict in manuscript.py with a PostgreSQL table so
that upload job state survives backend restarts and supports multi-user safety
via user_id ownership enforcement.

This migration is a no-op on non-PostgreSQL databases.
Uses IF NOT EXISTS so it is safe to re-run (e.g. when create_all already
created the table before alembic upgrade head ran on an existing deployment).
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("""
        CREATE TABLE IF NOT EXISTS manuscript_jobs (
            job_id        VARCHAR       NOT NULL,
            story_id      VARCHAR       NOT NULL,
            user_id       VARCHAR       NOT NULL,
            status        VARCHAR       NOT NULL DEFAULT 'pending',
            stage         VARCHAR       NOT NULL DEFAULT '',
            percent       INTEGER       NOT NULL DEFAULT 0,
            message       TEXT          NOT NULL DEFAULT '',
            chapter_count INTEGER       NOT NULL DEFAULT 0,
            created_at    TIMESTAMP,
            updated_at    TIMESTAMP,
            PRIMARY KEY   (job_id),
            FOREIGN KEY   (story_id) REFERENCES stories(story_id) ON DELETE CASCADE,
            FOREIGN KEY   (user_id)  REFERENCES users(user_id)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_manuscript_jobs_story_id "
        "ON manuscript_jobs(story_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_manuscript_jobs_user_id "
        "ON manuscript_jobs(user_id)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ix_manuscript_jobs_user_id")
    op.execute("DROP INDEX IF EXISTS ix_manuscript_jobs_story_id")
    op.execute("DROP TABLE IF EXISTS manuscript_jobs")
