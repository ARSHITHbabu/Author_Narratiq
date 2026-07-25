import logging

from sqlalchemy import create_engine, text, inspect as sa_inspect
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from config import settings

logger = logging.getLogger(__name__)

DATABASE_URL = settings.database_url

if DATABASE_URL.startswith("sqlite"):
    import warnings
    warnings.warn(
        "[NarratIQ] DATABASE_URL is SQLite. "
        "Set DATABASE_URL=postgresql+psycopg2://... for production. "
        "pgvector features (Vector columns, HNSW indexes) are unavailable on SQLite.",
        stacklevel=2,
    )


def _build_engine():
    kwargs: dict = {}
    if DATABASE_URL.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs.update({
            "pool_size": 10,
            "max_overflow": 20,
            "pool_pre_ping": True,
            "pool_recycle": 3600,
        })
    return create_engine(DATABASE_URL, **kwargs)


engine = _build_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_db_migrations(eng) -> None:
    """
    Apply lightweight column-addition migrations without Alembic.
    Safe to call on every startup — skips columns that already exist.
    New tables are created by Base.metadata.create_all before this runs.
    """
    inspector = sa_inspect(eng)
    existing_tables = set(inspector.get_table_names())

    def _add_col(table: str, col: str, col_def: str) -> None:
        if table not in existing_tables:
            return  # table will be created by create_all; no ALTER needed
        try:
            cols = {c["name"] for c in inspector.get_columns(table)}
            if col not in cols:
                with eng.connect() as conn:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}"))
                    conn.commit()
                logger.info("[DB migration] Added '%s' to %s.", col, table)
        except Exception as exc:
            logger.warning("[DB migration] Warning (%s.%s): %s", table, col, exc)

    is_postgres = eng.dialect.name == "postgresql"

    # character_profiles — new structured fields
    _add_col("character_profiles", "goals",  "TEXT DEFAULT ''")
    _add_col("character_profiles", "traits", "TEXT DEFAULT '[]'")

    # story_intakes — full Story-Intelligence snapshot (rich genre context).
    # JSON on PostgreSQL; SQLite stores JSON as TEXT transparently.
    _add_col("story_intakes", "analysis", "JSON" if is_postgres else "TEXT DEFAULT NULL")

    # story_bibles — generation lifecycle status (running|completed|partial|failed)
    _add_col("story_bibles", "status", "VARCHAR DEFAULT 'completed'")
    # story_bibles — which sections failed on the last run, for targeted regeneration.
    # Alembic 0016 adds this too; both paths are kept so a table provisioned by
    # create_all() (as the live one was) gets the column either way.
    _add_col("story_bibles", "failed_sections", "JSON" if is_postgres else "TEXT DEFAULT NULL")

    # chapter_chunks / chapter_summaries — character UUID index
    _add_col("chapter_chunks",     "character_ids", "TEXT DEFAULT '[]'")
    _add_col("chapter_summaries",  "character_ids", "TEXT DEFAULT '[]'")

    # Embedding columns — only add as TEXT on SQLite (legacy local dev).
    # On PostgreSQL, create_all() creates them as vector(1024) automatically;
    # adding them here as TEXT would create a type mismatch with HNSW indexes.
    if not is_postgres:
        _add_col("chapter_summaries",  "embedding",       "TEXT DEFAULT NULL")
        _add_col("character_profiles", "mention_embedding","TEXT DEFAULT NULL")
        _add_col("story_notes",        "embedding",        "TEXT DEFAULT NULL")
        _add_col("note_cards",         "embedding",        "TEXT DEFAULT NULL")
