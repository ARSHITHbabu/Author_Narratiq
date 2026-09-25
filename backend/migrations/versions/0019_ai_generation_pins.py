"""Phase 3 — ai_generation_pins (temporary, expiring AI generation pins)

Stage 7 task 7.4 / 7.5 (Phase 3 spec §13.1, P3-01, P3-06, P3-11). The spec
numbered this migration 0016; 0016–0018 were already used by Stages 3–5, so
the Phase 3 chain is renumbered 0019–0022 (conflict decision C7-1).

One table holds everything a pin needs, including the lineage columns (P3-06)
and the nullable `embedding vector(1024)` column used by similarity stage 2
(P3-11). NULL embedding simply disables stage 2 for that row, so
PIN_STORE_EMBEDDING=false needs no schema change.

Five deliberately-few indexes (high-churn table, every index is write cost).
No HNSW index on `embedding`: similarity candidates are <= 20 rows already
filtered by (story_id, tool), where an exact scan beats an ANN probe.

Autovacuum is tuned for insert/delete churn (spec §20.4) — applied even when
the table already exists, because start-narratiq.sh runs create_all() before
alembic and create_all() cannot set storage parameters.

Pins are EXCLUDED from logical backups by scripts/backup_database.sh
(decision D9): the table definition is dumped, its rows are not.

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

TABLE = "ai_generation_pins"
INDEXES = [
    ("ix_ai_generation_pins_expires_at",  ["expires_at"]),
    ("ix_ai_generation_pins_user_story",  ["user_id", "story_id", "created_at"]),
    ("ix_ai_generation_pins_chapter",     ["chapter_id"]),
    ("ix_ai_generation_pins_content_sha", ["content_sha256"]),
    ("ix_ai_generation_pins_root",        ["root_pin_id"]),
]


def _table_exists(bind, name: str) -> bool:
    return sa.inspect(bind).has_table(name)


def _index_exists(bind, table: str, index: str) -> bool:
    if not _table_exists(bind, table):
        return False
    return any(i["name"] == index for i in sa.inspect(bind).get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, TABLE):
        op.create_table(
            TABLE,
            sa.Column("pin_id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.user_id"), nullable=False),
            sa.Column("story_id", sa.String(), sa.ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=False),
            sa.Column("chapter_id", sa.String(), sa.ForeignKey("chapters.chapter_id", ondelete="SET NULL"), nullable=True),
            sa.Column("tool", sa.String(), nullable=False),
            sa.Column("scope", sa.String(), nullable=True),
            sa.Column("tool_params", sa.JSON(), nullable=True),
            sa.Column("source_from", sa.Integer(), nullable=True),
            sa.Column("source_to", sa.Integer(), nullable=True),
            sa.Column("source_excerpt", sa.Text(), nullable=True),
            sa.Column("source_sha256", sa.String(64), nullable=True),
            sa.Column("content", sa.Text(), nullable=True),
            sa.Column("content_uri", sa.Text(), nullable=True),
            sa.Column("content_sha256", sa.String(64), nullable=False),
            sa.Column("content_bytes", sa.Integer(), nullable=True),
            sa.Column("word_count", sa.Integer(), nullable=True),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("parent_pin_id", sa.String(), sa.ForeignKey(f"{TABLE}.pin_id", ondelete="SET NULL"), nullable=True),
            sa.Column("root_pin_id", sa.String(), nullable=True),
            sa.Column("lineage_depth", sa.Integer(), nullable=True),
            sa.Column("derived_from_pin_ids", sa.JSON(), nullable=True),
            sa.Column("derivation", sa.String(), nullable=True),
            sa.Column("embedding", Vector(1024), nullable=True),
            sa.Column("label", sa.String(), nullable=True),
            sa.Column("is_favourite", sa.Boolean(), nullable=True),
            sa.Column("applied_at", sa.DateTime(), nullable=True),
            sa.Column("promoted_card_id", sa.String(), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
    for name, cols in INDEXES:
        if not _index_exists(bind, TABLE, name):
            op.create_index(name, TABLE, cols)
    # Idempotent by nature — SET on an already-set parameter is a no-op.
    op.execute(
        f"ALTER TABLE {TABLE} SET (autovacuum_vacuum_scale_factor = 0.05, "
        f"autovacuum_vacuum_cost_delay = 2)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, TABLE):
        # Pins are temporary by contract; dropping them on rollback is the
        # documented, accepted data-loss asymmetry (spec §36.3).
        op.drop_table(TABLE)
