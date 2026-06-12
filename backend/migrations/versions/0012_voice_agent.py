"""Real-Time Voice Agent — voice_sessions, voice_commands, voice_workflows,
voice_tasks, voice_usage_daily

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def _table_exists(bind, name: str) -> bool:
    return sa.inspect(bind).has_table(name)


def _index_exists(bind, table: str, index: str) -> bool:
    if not _table_exists(bind, table):
        return False
    return any(i["name"] == index for i in sa.inspect(bind).get_indexes(table))


def _mkindex(bind, name: str, table: str, cols: list[str]) -> None:
    if not _index_exists(bind, table, name):
        op.create_index(name, table, cols)


def upgrade() -> None:
    bind = op.get_bind()

    # ── voice_sessions ────────────────────────────────────────────────────────
    if not _table_exists(bind, "voice_sessions"):
        op.create_table(
            "voice_sessions",
            sa.Column("session_id",    sa.String(), primary_key=True),
            sa.Column("user_id",       sa.String(), sa.ForeignKey("users.user_id"), nullable=False),
            sa.Column("story_id",      sa.String(), sa.ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=True),
            sa.Column("status",        sa.String(20), nullable=True, server_default="active"),
            sa.Column("context_state", sa.JSON(),   nullable=True),
            sa.Column("command_count", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("started_at",    sa.DateTime(), nullable=True),
            sa.Column("ended_at",      sa.DateTime(), nullable=True),
            sa.Column("error_message", sa.Text(),   nullable=True, server_default=""),
        )
    _mkindex(bind, "ix_voice_sessions_user_id",  "voice_sessions", ["user_id"])
    _mkindex(bind, "ix_voice_sessions_story_id", "voice_sessions", ["story_id"])

    # ── voice_commands ────────────────────────────────────────────────────────
    if not _table_exists(bind, "voice_commands"):
        op.create_table(
            "voice_commands",
            sa.Column("command_id",          sa.String(), primary_key=True),
            sa.Column("session_id",          sa.String(), sa.ForeignKey("voice_sessions.session_id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id",             sa.String(), sa.ForeignKey("users.user_id"), nullable=False),
            sa.Column("story_id",            sa.String(), sa.ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=True),
            sa.Column("raw_transcript",      sa.Text(),   nullable=True, server_default=""),
            sa.Column("cleaned_transcript",  sa.Text(),   nullable=True, server_default=""),
            sa.Column("resolved_references", sa.JSON(),   nullable=True),
            sa.Column("detected_intent",     sa.String(), nullable=True, server_default=""),
            sa.Column("capability",          sa.String(), nullable=True, server_default=""),
            sa.Column("target_router",       sa.String(), nullable=True, server_default=""),
            sa.Column("action_type",         sa.String(20), nullable=True, server_default=""),
            sa.Column("confidence",          sa.Float(),  nullable=True, server_default="0"),
            sa.Column("requires_confirmation", sa.Boolean(), nullable=True, server_default="false"),
            sa.Column("confirmed",           sa.Boolean(), nullable=True),
            sa.Column("parameters",          sa.JSON(),   nullable=True),
            sa.Column("status",              sa.String(30), nullable=True, server_default="success"),
            sa.Column("result_summary",      sa.Text(),   nullable=True, server_default=""),
            sa.Column("stt_ms",              sa.Integer(), nullable=True, server_default="0"),
            sa.Column("llm_ms",              sa.Integer(), nullable=True, server_default="0"),
            sa.Column("route_ms",            sa.Integer(), nullable=True, server_default="0"),
            sa.Column("exec_ms",             sa.Integer(), nullable=True, server_default="0"),
            sa.Column("latency_ms",          sa.Integer(), nullable=True, server_default="0"),
            sa.Column("created_at",          sa.DateTime(), nullable=True),
        )
    _mkindex(bind, "ix_voice_commands_session_id", "voice_commands", ["session_id"])
    _mkindex(bind, "ix_voice_commands_user_id",    "voice_commands", ["user_id"])
    _mkindex(bind, "ix_voice_commands_created_at",  "voice_commands", ["created_at"])

    # ── voice_workflows ───────────────────────────────────────────────────────
    if not _table_exists(bind, "voice_workflows"):
        op.create_table(
            "voice_workflows",
            sa.Column("workflow_id", sa.String(), primary_key=True),
            sa.Column("command_id",  sa.String(), sa.ForeignKey("voice_commands.command_id", ondelete="CASCADE"), nullable=False),
            sa.Column("session_id",  sa.String(), sa.ForeignKey("voice_sessions.session_id", ondelete="CASCADE"), nullable=False),
            sa.Column("node_count",  sa.Integer(), nullable=True, server_default="0"),
            sa.Column("status",      sa.String(30), nullable=True, server_default="planned"),
            sa.Column("graph_json",  sa.JSON(),    nullable=True),
            sa.Column("created_at",  sa.DateTime(), nullable=True),
            sa.Column("updated_at",  sa.DateTime(), nullable=True),
        )
    _mkindex(bind, "ix_voice_workflows_command_id", "voice_workflows", ["command_id"])
    _mkindex(bind, "ix_voice_workflows_session_id", "voice_workflows", ["session_id"])

    # ── voice_tasks ───────────────────────────────────────────────────────────
    if not _table_exists(bind, "voice_tasks"):
        op.create_table(
            "voice_tasks",
            sa.Column("task_id",     sa.String(), primary_key=True),
            sa.Column("workflow_id", sa.String(), sa.ForeignKey("voice_workflows.workflow_id", ondelete="CASCADE"), nullable=False),
            sa.Column("node_key",    sa.String(), nullable=False),
            sa.Column("capability",  sa.String(), nullable=True, server_default=""),
            sa.Column("action",      sa.String(), nullable=True, server_default=""),
            sa.Column("action_type", sa.String(20), nullable=True, server_default=""),
            sa.Column("depends_on",  sa.JSON(),   nullable=True),
            sa.Column("params",      sa.JSON(),   nullable=True),
            sa.Column("execution_locus", sa.String(20), nullable=True, server_default="server"),
            sa.Column("requires_confirmation", sa.Boolean(), nullable=True, server_default="false"),
            sa.Column("confirmed",   sa.Boolean(), nullable=True),
            sa.Column("status",      sa.String(30), nullable=True, server_default="pending"),
            sa.Column("result_summary", sa.Text(), nullable=True, server_default=""),
            sa.Column("latency_ms",  sa.Integer(), nullable=True, server_default="0"),
            sa.Column("created_at",  sa.DateTime(), nullable=True),
        )
    _mkindex(bind, "ix_voice_tasks_workflow_id", "voice_tasks", ["workflow_id"])

    # ── voice_usage_daily ─────────────────────────────────────────────────────
    if not _table_exists(bind, "voice_usage_daily"):
        op.create_table(
            "voice_usage_daily",
            sa.Column("id",                  sa.String(), primary_key=True),
            sa.Column("day",                 sa.String(10), nullable=False),
            sa.Column("user_id",             sa.String(), sa.ForeignKey("users.user_id"), nullable=True),
            sa.Column("sessions",            sa.Integer(), nullable=True, server_default="0"),
            sa.Column("commands",            sa.Integer(), nullable=True, server_default="0"),
            sa.Column("avg_session_seconds", sa.Float(),  nullable=True, server_default="0"),
            sa.Column("intent_distribution", sa.JSON(),   nullable=True),
            sa.Column("capability_usage",    sa.JSON(),   nullable=True),
            sa.Column("low_confidence",      sa.Integer(), nullable=True, server_default="0"),
            sa.Column("clarifications",      sa.Integer(), nullable=True, server_default="0"),
            sa.Column("failed_resolutions",  sa.Integer(), nullable=True, server_default="0"),
            sa.Column("failed_executions",   sa.Integer(), nullable=True, server_default="0"),
            sa.Column("abandoned_workflows", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("stt_p95_ms",          sa.Integer(), nullable=True, server_default="0"),
            sa.Column("e2e_p95_ms",          sa.Integer(), nullable=True, server_default="0"),
            sa.Column("voice_to_applied",    sa.Integer(), nullable=True, server_default="0"),
            sa.Column("created_at",          sa.DateTime(), nullable=True),
            sa.Column("updated_at",          sa.DateTime(), nullable=True),
            sa.UniqueConstraint("day", "user_id", name="uq_voice_usage_day_user"),
        )
    _mkindex(bind, "ix_voice_usage_daily_day",     "voice_usage_daily", ["day"])
    _mkindex(bind, "ix_voice_usage_daily_user_id", "voice_usage_daily", ["user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    for tbl in ["voice_usage_daily", "voice_tasks", "voice_workflows", "voice_commands", "voice_sessions"]:
        if _table_exists(bind, tbl):
            op.drop_table(tbl)
