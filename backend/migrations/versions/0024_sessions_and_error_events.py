"""Stage 10 — session revocation + built-in error tracking

  10.7 / S10-F  users.token_version  — bumped on password change and account
                                       deletion; ends every session at once.
                revoked_sessions     — one row per signed-out session (jti),
                                       swept once the token would have expired.
  10.2 / S10-C  error_events         — scrubbed, de-duplicated error records.
                                       No user id, request body or manuscript
                                       text by construction.

Purely additive: no existing row is modified (token_version defaults to 0 for
every existing account). Guarded like 0023 so it tolerates start-narratiq.sh
having run Base.metadata.create_all() first. Foreign-key / cascade changes for
account deletion (10.6) are deliberately NOT here — they live in 0025.

Revision ID: 0024
Revises: 0023
Create Date: 2026-09-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def _table_exists(bind, name: str) -> bool:
    return sa.inspect(bind).has_table(name)


def _column_exists(bind, table: str, column: str) -> bool:
    return any(c["name"] == column for c in sa.inspect(bind).get_columns(table))


def _index_exists(bind, table: str, name: str) -> bool:
    return any(i["name"] == name for i in sa.inspect(bind).get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()

    if not _column_exists(bind, "users", "token_version"):
        op.add_column("users", sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"))

    if not _table_exists(bind, "revoked_sessions"):
        op.create_table(
            "revoked_sessions",
            sa.Column("jti",        sa.String(),   primary_key=True),
            sa.Column("user_id",    sa.String(),   sa.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("revoked_at", sa.DateTime(), nullable=False),
        )
    for name, col in (("ix_revoked_sessions_user_id", "user_id"), ("ix_revoked_sessions_expires_at", "expires_at")):
        if not _index_exists(bind, "revoked_sessions", name):
            op.create_index(name, "revoked_sessions", [col])

    if not _table_exists(bind, "error_events"):
        op.create_table(
            "error_events",
            sa.Column("event_id",    sa.String(),   primary_key=True),
            sa.Column("source",      sa.String(),   nullable=False),
            sa.Column("kind",        sa.String(),   nullable=False),
            sa.Column("route",       sa.String(),   nullable=True),
            sa.Column("method",      sa.String(),   nullable=True),
            sa.Column("status_code", sa.Integer(),  nullable=True),
            sa.Column("request_id",  sa.String(),   nullable=True),
            sa.Column("message",     sa.Text(),     nullable=True),
            sa.Column("stack",       sa.Text(),     nullable=True),
            sa.Column("fingerprint", sa.String(64), nullable=False),
            sa.Column("occurrences", sa.Integer(),  nullable=False, server_default="1"),
            sa.Column("first_seen",  sa.DateTime(), nullable=False),
            sa.Column("last_seen",   sa.DateTime(), nullable=False),
        )
    for name, col in (("ix_error_events_fingerprint", "fingerprint"), ("ix_error_events_last_seen", "last_seen")):
        if not _index_exists(bind, "error_events", name):
            op.create_index(name, "error_events", [col])


def downgrade() -> None:
    bind = op.get_bind()
    for table in ("error_events", "revoked_sessions"):
        if _table_exists(bind, table):
            op.drop_table(table)
    if _column_exists(bind, "users", "token_version"):
        op.drop_column("users", "token_version")
