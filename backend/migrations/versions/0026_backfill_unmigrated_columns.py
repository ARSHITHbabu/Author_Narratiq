"""Record in Alembic the columns that only ever existed through create_all()

Found by the Stage 11 Phase 2 acceptance (task 11.6, roadmap rule R11, "Alembic
for all schema changes"): four columns declared in models.py have no Alembic
migration. A fresh database gets them from Base.metadata.create_all(); an older
one only from database.run_db_migrations(), the startup ALTER TABLE guard:

  character_profiles.goals         TEXT  default ''
  character_profiles.traits        JSON  default []
  chapter_chunks.character_ids     JSON  default []
  chapter_summaries.character_ids  JSON  default []

With this migration every column the ORM declares has an Alembic migration.
An existing database brought up to date with `alembic upgrade head` therefore
gets these columns without relying on the startup guard. (Base tables are still
created by create_all(), as start-narratiq.sh does before Alembic; that is the
project's established order and unchanged here.) Each add is guarded, so on a
database that already has the columns it is a no-op. Types follow models.py (JSON). A column the startup guard
created earlier as TEXT is left as it is: converting it would rewrite author
data, and that is not this migration's job.

Downgrade removes nothing. These columns predate the migration and hold author
data (character goals and traits), so dropping them on a downgrade would
destroy it. The downgrade is a deliberate no-op.

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None

_COLUMNS = [
    ("character_profiles", "goals",         lambda: sa.Column("goals", sa.Text(), nullable=True, server_default="")),
    ("character_profiles", "traits",        lambda: sa.Column("traits", sa.JSON(), nullable=True)),
    ("chapter_chunks",     "character_ids", lambda: sa.Column("character_ids", sa.JSON(), nullable=True)),
    ("chapter_summaries",  "character_ids", lambda: sa.Column("character_ids", sa.JSON(), nullable=True)),
]


def _table_exists(bind, name: str) -> bool:
    return sa.inspect(bind).has_table(name)


def _column_exists(bind, table: str, column: str) -> bool:
    if not _table_exists(bind, table):
        return False
    return any(c["name"] == column for c in sa.inspect(bind).get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    for table, column, make in _COLUMNS:
        if _table_exists(bind, table) and not _column_exists(bind, table, column):
            op.add_column(table, make())


def downgrade() -> None:
    # Intentionally empty. See the module docstring: these columns predate this
    # migration and hold author data.
    pass
