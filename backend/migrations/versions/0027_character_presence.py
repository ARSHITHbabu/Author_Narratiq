"""characters.presence — on-page vs referenced vs historical (Stage 12 A10)

Cast generation could not tell a character who appears in scenes from one who
is only talked about (an absent ruler) or remembered (a sister who died before
the story). `status` (active / deceased / unknown) is life status and stays
separate: "historical + deceased", "referenced + alive" and "on page +
deceased" are all representable.

Values: "on_page" | "referenced" | "historical"; NULL = not recorded (every
character created before this migration, and any created by hand without
choosing). Nothing is backfilled — guessing presence for existing characters
would be invention.

The add is guarded because start-narratiq.sh runs Base.metadata.create_all()
before Alembic, so a fresh database already has the column (the project's
established pattern, see 0011 / 0026).

Downgrade drops the column. Only presence labels are lost (cast generation
can produce them again); no other character data is touched.

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-02
"""
from alembic import op
import sqlalchemy as sa

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def _column_exists(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    if not insp.has_table(table):
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("characters") and not _column_exists(bind, "characters", "presence"):
        op.add_column("characters", sa.Column("presence", sa.String(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if _column_exists(bind, "characters", "presence"):
        op.drop_column("characters", "presence")
