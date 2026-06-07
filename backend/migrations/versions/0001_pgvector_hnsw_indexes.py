"""Create HNSW indexes on all vector embedding columns

Revision ID: 0001
Revises:
Create Date: 2026-06-07

This migration is a no-op on non-PostgreSQL databases.
Indexes are created with IF NOT EXISTS so re-runs are safe.
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# HNSW parameters: m=16 (standard default), ef_construction=64 (build quality vs speed)
_HNSW_PARAMS = "WITH (m = 16, ef_construction = 64)"

_UP_INDEXES = [
    ("ix_chapter_chunks_embedding_hnsw",           "chapter_chunks",    "embedding"),
    ("ix_chapter_summaries_embedding_hnsw",        "chapter_summaries", "embedding"),
    ("ix_character_profiles_embedding_hnsw",       "character_profiles", "embedding"),
    ("ix_character_profiles_mention_embedding_hnsw", "character_profiles", "mention_embedding"),
    ("ix_story_notes_embedding_hnsw",              "story_notes",       "embedding"),
    ("ix_note_cards_embedding_hnsw",               "note_cards",        "embedding"),
]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for idx_name, table, col in _UP_INDEXES:
        op.execute(
            f"CREATE INDEX IF NOT EXISTS {idx_name} "
            f"ON {table} USING hnsw ({col} vector_cosine_ops) {_HNSW_PARAMS}"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for idx_name, _, _ in _UP_INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {idx_name}")
