"""Phase 3 — users.plan

Stage 7 task 7.5 (Phase 3 spec §13.4, §21). One nullable column. NULL resolves
to "free" in services/plans.get_limits(), so no backfill is required and no
code path can crash on an unset plan. Deliberately not a subscriptions table:
there is no billing provider yet (decision D2 — manual/admin assignment now).

Revision ID: 0022
Revises: 0021
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def _column_exists(bind) -> bool:
    return any(c["name"] == "plan" for c in sa.inspect(bind).get_columns("users"))


def upgrade() -> None:
    bind = op.get_bind()
    if not _column_exists(bind):
        op.add_column("users", sa.Column("plan", sa.String(), nullable=True, server_default="free"))


def downgrade() -> None:
    bind = op.get_bind()
    if _column_exists(bind):
        op.drop_column("users", "plan")
